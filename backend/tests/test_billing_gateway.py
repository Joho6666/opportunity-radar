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
