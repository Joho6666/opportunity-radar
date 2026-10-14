import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from sqlalchemy import text
from app.core.config import get_settings
from app.core.errors import AppError
from app.services.billing_gateway import paid_context, reserve, finish


@pytest.fixture
def billing(monkeypatch):
    from app.database.client import create_database_engine
    from app.repositories.postgres import PostgresRepository
    if not get_settings().database_url:
        pytest.skip("DATABASE_URL not configured")
    repo = PostgresRepository(create_database_engine())
    uid = str(uuid4())
    repo.get_profile(uid)
    with repo.engine.begin() as conn:
        conn.execute(text("INSERT INTO billing_authorizations(user_id,scope,enabled,providers,run_requests,daily_requests,run_micros,daily_micros) VALUES(CAST(:uid AS uuid),'evidence',true,'[\"tikhub\",\"llm\",\"embedding\"]',2,3,100000,150000)"), {"uid": uid})
    settings = get_settings()
    monkeypatch.setattr(settings, "paid_api_enabled", True)
    monkeypatch.setattr(settings, "tikhub_price_per_request", .05)
    monkeypatch.setattr(settings, "llm_price_input_per_mtok", 1)
    monkeypatch.setattr(settings, "llm_price_output_per_mtok", 2)
    return repo, uid


def test_global_disabled_precedes_any_network(monkeypatch):
    monkeypatch.setattr(get_settings(), "paid_api_enabled", False)
    with pytest.raises(AppError, match="") as err:
        reserve("tikhub", "douyin")
    assert err.value.code == "PAID_API_DISABLED"


def test_scope_and_schedule_fail_closed(billing):
    repo, uid = billing
    for scope, scheduled in [("unknown",False),("evidence",True)]:
        with paid_context(repo,uid,scope,str(uuid4()),scheduled):
            with pytest.raises(AppError) as err:
                reserve("tikhub","douyin")
            assert err.value.code == "PAID_CALL_UNAUTHORIZED"


def test_concurrent_daily_limit_is_atomic(billing):
    repo, uid = billing
    def call(_):
        with paid_context(repo,uid,"evidence",str(uuid4())):
            try:
                reserve("tikhub","douyin")
                return True
            except AppError:
                return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(call, range(12))) == 3
    with repo.engine.connect() as conn:
        assert conn.execute(text("SELECT sum(reserved_micros) FROM billing_calls WHERE user_id=CAST(:uid AS uuid)"),{"uid":uid}).scalar() == 150000


def test_failed_call_keeps_reservation_and_run_cap(billing):
    repo, uid = billing
    with paid_context(repo,uid,"evidence",str(uuid4())):
        for _ in range(2):
            finish(reserve("tikhub","douyin"),ok=False)
        with pytest.raises(AppError) as err:
            reserve("tikhub","douyin")
        assert err.value.code == "PAID_QUOTA_EXHAUSTED"


def test_no_memory_fallback(billing):
    from app.repositories.memory import MemoryRepository
    with paid_context(MemoryRepository(),"x","evidence","run"):
        with pytest.raises(AppError) as err:
            reserve("tikhub","douyin")
        assert err.value.code == "BILLING_CONTEXT_REQUIRED"


def test_actual_cost_unknown_is_not_zero(billing):
    repo, uid = billing
    with paid_context(repo,uid,"evidence",str(uuid4())):
        reservation=reserve("llm","classification",100)
        finish(reservation,{"usage":{"prompt_tokens":12,"completion_tokens":5,"total_tokens":17}})
    with repo.engine.connect() as conn:
        row=conn.execute(text("SELECT actual_micros,actual_tokens,status FROM billing_calls WHERE id=CAST(:id AS uuid)"),{"id":reservation[1]}).one()
    assert row == (None,17,"succeeded")


def test_repeat_finish_preserves_reported_usage(billing):
    repo, uid = billing
    with paid_context(repo, uid, "evidence", str(uuid4())):
        reservation = reserve("tikhub", "douyin")
        finish(reservation, {"usage": {"cost_usd": .06, "total_tokens": 17}}, ok=False)
        finish(reservation, ok=False)
    with repo.engine.connect() as conn:
        row = conn.execute(text("SELECT actual_micros,actual_tokens,status FROM billing_calls WHERE id=CAST(:id AS uuid)"), {"id": reservation[1]}).one()
    assert row == (60000, 17, "failed")


def test_malformed_usage_does_not_prevent_safe_finalization(billing):
    repo, uid = billing
    with paid_context(repo, uid, "evidence", str(uuid4())):
        reservation = reserve("tikhub", "douyin")
        finish(reservation, {"usage": "unexpected provider shape"}, ok=False)
    with repo.engine.connect() as conn:
        row = conn.execute(text("SELECT actual_micros,actual_tokens,status FROM billing_calls WHERE id=CAST(:id AS uuid)"), {"id": reservation[1]}).one()
    assert row == (None, None, "failed")


def test_http_error_preserves_provider_reported_cost(billing, monkeypatch):
    import httpx
    from app.collectors.http import HttpFetcher
    repo, uid = billing
    monkeypatch.setattr("app.collectors.http.validate_public_url", lambda _: "public.example")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(503, json={"usage": {"cost_usd": .06}}))) as client:
            with paid_context(repo, uid, "evidence", str(uuid4())):
                with pytest.raises(httpx.HTTPStatusError):
                    await HttpFetcher(client=client).get_json("https://public.example", billable_provider="tikhub", billable_source="douyin")
    asyncio.run(run())
    with repo.engine.connect() as conn:
        assert conn.execute(text("SELECT actual_micros FROM billing_calls WHERE user_id=CAST(:uid AS uuid)"), {"uid": uid}).scalar_one() == 60000


@pytest.fixture
def batch_billing(billing, monkeypatch):
    repo, uid = billing
    batch_id = str(uuid4())
    # Model an active server-selected batch without creating a new batch per request.
    monkeypatch.setitem(get_settings().__dict__, "paid_batch_id", batch_id)
    with repo.engine.begin() as conn:
        conn.execute(text("UPDATE billing_authorizations SET daily_requests=100,run_requests=100,daily_micros=1000000,run_micros=1000000 WHERE user_id=CAST(:uid AS uuid)"), {"uid": uid})
        conn.execute(text("INSERT INTO billing_batches(id,user_id,enabled,providers,sources,request_limit,cost_limit_micros,request_limit_micros) VALUES(:id,CAST(:uid AS uuid),true,'[\"tikhub\"]','[\"douyin\"]',5,500000,100000)"), {"id": batch_id, "uid": uid})
    return repo, uid, batch_id


def test_batch_limit_survives_day_change_and_new_repository(batch_billing):
    from app.repositories.postgres import PostgresRepository
    repo, uid, batch_id = batch_billing
    for _ in range(5):
        with paid_context(repo, uid, "evidence", str(uuid4())):
            reserve("tikhub", "douyin")
    with repo.engine.begin() as conn:
        conn.execute(text("UPDATE billing_calls SET created_at=now()-interval '2 days' WHERE user_id=CAST(:uid AS uuid)"), {"uid": uid})
    with paid_context(PostgresRepository(repo.engine), uid, "evidence", str(uuid4())):
        with pytest.raises(AppError) as err:
            reserve("tikhub", "douyin")
    assert err.value.code == "PAID_BATCH_EXHAUSTED"


def test_batch_concurrency_is_atomic(batch_billing):
    repo, uid, batch_id = batch_billing
    def call(_):
        with paid_context(repo, uid, "evidence", str(uuid4())):
            try:
                reserve("tikhub", "douyin")
                return True
            except AppError:
                return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(call, range(12))) == 5


def test_batch_source_and_single_request_cost_are_enforced(batch_billing, monkeypatch):
    repo, uid, batch_id = batch_billing
    with paid_context(repo, uid, "evidence", str(uuid4())):
        with pytest.raises(AppError) as err:
            reserve("tikhub", "weibo")
        assert err.value.code == "PAID_BATCH_UNAUTHORIZED"
        monkeypatch.setattr(get_settings(), "tikhub_price_per_request", .11)
        with pytest.raises(AppError) as err:
            reserve("tikhub", "douyin")
        assert err.value.code == "PAID_BATCH_EXHAUSTED"


def test_debug_batch_cannot_enable_radar_even_with_prior_grant(batch_billing):
    repo, uid, _ = batch_billing
    with repo.engine.begin() as conn:
        conn.execute(text("INSERT INTO billing_authorizations SELECT user_id,'radar:test',enabled,providers,allow_scheduled,run_requests,daily_requests,run_micros,daily_micros,updated_at FROM billing_authorizations WHERE user_id=CAST(:uid AS uuid)"), {"uid":uid})
    with paid_context(repo, uid, "radar:test", str(uuid4())):
        with pytest.raises(AppError) as err:
            reserve("tikhub", "douyin")
    assert err.value.code == "PAID_BATCH_UNAUTHORIZED"


def test_batch_cost_includes_actual_overrun(batch_billing):
    repo, uid, _ = batch_billing
    with paid_context(repo, uid, "evidence", str(uuid4())):
        finish(reserve("tikhub", "douyin"), {"usage": {"cost_usd": .46}})
        with pytest.raises(AppError) as err:
            reserve("tikhub", "douyin")
    assert err.value.code == "PAID_BATCH_EXHAUSTED"


def test_status_reports_cumulative_batch_balance(batch_billing, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    from app.main import app
    repo, uid, batch_id = batch_billing
    with paid_context(repo, uid, "evidence", str(uuid4())):
        reserve("tikhub", "douyin")
    monkeypatch.setitem(app.dependency_overrides, get_repository, lambda: repo)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: CurrentUser(id=uid))
    with TestClient(app) as client:
        data = client.get("/api/billing/status").json()
    assert data["batch"]["id"] == batch_id
    assert data["batch"]["remaining_requests"] == 4
    assert data["batch"]["remaining_cost_usd"] == pytest.approx(.45)


def test_settings_repr_does_not_disclose_credentials():
    from app.core.config import Settings
    assert "SECRET_VALUE" not in repr(Settings(tikhub_api_key="SECRET_VALUE"))


def test_unknown_endpoint_cannot_fall_back_to_flat_price(billing, monkeypatch):
    repo, uid = billing
    monkeypatch.setattr(get_settings(),"tikhub_endpoint_prices_json",'{"/search":0.02}')
    with paid_context(repo,uid,"evidence",str(uuid4())):
        with pytest.raises(AppError) as err:
            reserve("tikhub","douyin",endpoint="/unknown")
        assert err.value.code == "BILLING_PRICE_REQUIRED"
        reservation=reserve("tikhub","douyin",endpoint="/search")
    with repo.engine.connect() as conn:
        assert conn.execute(text("SELECT reserved_micros FROM billing_calls WHERE id=CAST(:id AS uuid)"),{"id":reservation[1]}).scalar_one() == 20000


def test_paid_response_archived_before_schema_failure(billing, monkeypatch):
    import httpx
    from app.collectors.http import HttpFetcher
    repo, uid = billing
    monkeypatch.setattr("app.collectors.http.validate_public_url", lambda _: "public.example")
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": "schema drift", "request_id": "r1", "authorization": "SECRET"}))) as client:
            with paid_context(repo, uid, "evidence", str(uuid4())):
                await HttpFetcher(client=client).get_json("https://public.example/search?keyword=PPT", billable_provider="tikhub", billable_source="douyin")
    asyncio.run(run())
    with repo.engine.connect() as conn:
        row = conn.execute(text("SELECT query,status_code,payload FROM provider_responses WHERE user_id=CAST(:uid AS uuid)"), {"uid": uid}).first()
    assert row is not None
    assert row[0:2] == ("PPT", 200)
    assert row.payload["data"] == "schema drift" and "SECRET" not in str(row.payload)


def test_all_paid_adapters_block_without_network(monkeypatch):
    from app.collectors.tikhub import TikHubCollector
    from app.collectors.tikhub_cn import DOMESTIC_COLLECTORS
    from app.collectors.web_search import WebSearchCollector
    monkeypatch.setattr(get_settings(),"paid_api_enabled",False)
    monkeypatch.setattr(get_settings(),"tikhub_api_key","test-only")
    monkeypatch.setattr(get_settings(),"firecrawl_api_key","test-only")
    monkeypatch.setattr("app.collectors.http.validate_public_url",lambda _: "api.example.com")
    for adapter in [TikHubCollector(),WebSearchCollector(),*(cls() for cls in DOMESTIC_COLLECTORS)]:
        with pytest.raises(AppError) as err:
            asyncio.run(adapter.search("test"))
        assert err.value.code == "PAID_API_DISABLED"


def test_llm_and_both_embeddings_refuse_without_network(monkeypatch):
    from app.ai.provider import OpenAICompatibleProvider
    from app.services.embedding_service import embed_texts,embed_texts_async
    settings=get_settings()
    monkeypatch.setattr(settings,"paid_api_enabled",False)
    monkeypatch.setattr(settings,"llm_api_key","offline-only")
    monkeypatch.setattr(settings,"llm_base_url","https://public.example/v1")
    with pytest.raises(AppError) as err:
        asyncio.run(OpenAICompatibleProvider().structured_output("test","classification"))
    assert err.value.code == "PAID_API_DISABLED"
    assert embed_texts(["test"]) is None
    assert asyncio.run(embed_texts_async(["test"])) is None


def test_paid_transport_has_zero_automatic_retries(billing,monkeypatch):
    import httpx
    from app.collectors.http import HttpFetcher
    repo,uid=billing;requests=[]
    monkeypatch.setattr("app.collectors.http.validate_public_url",lambda _:"public.example")
    async def run():
        def fail(request):requests.append(request);return httpx.Response(503)
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            with paid_context(repo,uid,"evidence",str(uuid4())):
                with pytest.raises(httpx.HTTPStatusError):
                    await HttpFetcher(client=client,retries=9).get_json("https://public.example",billable_provider="tikhub",billable_source="douyin")
    asyncio.run(run());assert len(requests) == 1


def test_reported_overrun_consumes_real_cost_and_stops_next_request(billing):
    repo,uid=billing
    with paid_context(repo,uid,"evidence",str(uuid4())):
        reservation=reserve("tikhub","douyin")
        finish(reservation,{"usage":{"cost_usd":0.16}})
        with pytest.raises(AppError) as err:reserve("tikhub","douyin")
        assert err.value.code == "PAID_QUOTA_EXHAUSTED"
    with repo.engine.connect() as conn:
        assert conn.execute(text("SELECT reserved_micros,actual_micros FROM billing_calls WHERE id=CAST(:id AS uuid)"),{"id":reservation[1]}).one() == (50000,160000)


def test_status_caps_every_scope_at_shared_account_balance(billing, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    from app.main import app

    repo, uid = billing
    monkeypatch.setattr(get_settings(), "paid_daily_request_limit", 2)
    monkeypatch.setattr(get_settings(), "paid_daily_cost_limit", 0.12)
    with repo.engine.begin() as conn:
        conn.execute(text("INSERT INTO billing_authorizations(user_id,scope,enabled,providers,run_requests,daily_requests,run_micros,daily_micros) VALUES(CAST(:uid AS uuid),'assistant',true,'[\"llm\"]',3,5,100000,200000)"), {"uid": uid})
    with paid_context(repo, uid, "evidence", str(uuid4())):
        finish(reserve("tikhub", "douyin"), {"usage": {"cost_usd": 0.08}})

    monkeypatch.setitem(app.dependency_overrides, get_repository, lambda: repo)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: CurrentUser(id=uid))
    with TestClient(app) as client:
        response = client.get("/api/billing/status")
    assert response.status_code == 200
    result = response.json()
    assert result["requests_today"] == 1
    assert result["reserved_cost_usd"] == pytest.approx(0.05)
    assert result["consumed_cost_usd"] == pytest.approx(0.08)
    assert result["account_remaining_requests"] == 1
    assert result["account_remaining_cost_usd"] == pytest.approx(0.04)
    assert {policy["scope"] for policy in result["authorizations"]} == {"evidence", "assistant"}
    for policy in result["authorizations"]:
        assert policy["remaining_requests"] == 1
        assert policy["remaining_cost_usd"] == pytest.approx(0.04)
