"""Real infrastructure contracts; HTTP behavior uses offline seams."""
import asyncio
import os
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import text
from app.core.config import get_settings, validate_runtime
from app.core.errors import AppError
from app.collectors.http import validate_public_url, HttpFetcher
from app.collectors.transport import PublicNetworkBackend
from app.repositories.memory import MemoryRepository
from app.schemas.domain import RadarCreate, QueryPlanItem
from app.schemas.evidence import EvidenceReview
from app.schemas.pipeline import PipelinePatch
from app.services.acquisition_metrics import acquisition_metrics
from test_acquisition_workflow import build

@pytest.fixture
def pg_repo():
    from app.database.client import create_database_engine
    from app.repositories.postgres import PostgresRepository
    if not get_settings().database_url:
        if os.getenv("REQUIRE_POSTGRES_TESTS") == "true":pytest.fail("PostgreSQL required")
        pytest.skip("DATABASE_URL not configured")
    return PostgresRepository(create_database_engine())

def test_domestic_radar_survives_postgres_roundtrip(pg_repo):
    uid=str(uuid4());sources=["douyin","xiaohongshu","weibo","zhihu","tikhub"]
    radar=pg_repo.create_radar(uid,RadarCreate(name="国内",goal="寻找真实公开的企业制作需求",sources=sources))
    pg_repo.save_radar(radar.model_copy(update={"queries":[QueryPlanItem(source=x,query="制作需求",priority=50) for x in sources]}))
    read=pg_repo.get_radar(uid,radar.id)
    assert set(read.sources) == set(sources)
    assert set(q.source for q in read.queries) == set(sources)


def test_collection_policy_persists_and_keyword_edits_invalidate_query_plan(pg_repo, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    from app.main import app
    uid=str(uuid4())
    value=RadarCreate(name="配置持久化",goal="寻找公开的真实文档制作需求",sources=["rss"],keywords=["PPT"],collection_policy={"required_terms":["PPT"],"excluded_terms":["教程"],"time_basis":"published","include_unknown_dates":False,"sort":"hot","activity_filter":"discussion","min_interactions":3})
    radar=pg_repo.create_radar(uid,value)
    assert pg_repo.get_radar(uid,radar.id).collection_policy == value.collection_policy
    pg_repo.save_radar(radar.model_copy(update={"queries":[QueryPlanItem(source="rss",query="old keyword",priority=50)]}))
    monkeypatch.setitem(app.dependency_overrides,get_repository,lambda:pg_repo)
    monkeypatch.setitem(app.dependency_overrides,get_current_user,lambda:CurrentUser(id=uid))
    with TestClient(app) as client:
        response=client.put("/api/radars/"+radar.id,json={**value.model_dump(),"keywords":["Word"],"freshness_hours":24})
        assert response.status_code == 200
    read=pg_repo.get_radar(uid,radar.id)
    assert read.queries == [] and read.keywords == ["Word"]
    assert read.freshness_hours == 24 and read.collection_policy == value.collection_policy


def test_postgres_refreshes_public_counters_without_duplicate_lead(pg_repo):
    from datetime import UTC,datetime
    from app.schemas.domain import RawItem
    from app.services.evidence_from_raw import raw_items_to_evidence_batch
    uid=str(uuid4());now=datetime.now(UTC)
    item=RawItem(external_id=uid,title="找人做PPT",content="找人做PPT，预算3000元",url="https://example.test/"+uid,source="rss",author="public-user",published_at=now,engagement={"comments":1})
    first=pg_repo.upsert_evidence_batch(uid,raw_items_to_evidence_batch(source="rss",query="PPT",items=[item],batch_id="obs1"))
    row=first.records[0]
    pg_repo.review_evidence(uid,row.evidence_id,EvidenceReview(verification_status="verified",notes="人工核实"))
    second=pg_repo.upsert_evidence_batch(uid,raw_items_to_evidence_batch(source="rss",query="PPT",items=[item.model_copy(update={"engagement":{"comments":40}})],batch_id="obs2"))
    read=pg_repo.get_evidence(uid,row.evidence_id)
    assert second.inserted == 0 and second.duplicates == 1
    assert read.ranking["signals"]["comments"] == 40
    assert read.notes == "人工核实" and read.verification_status == "verified" and read.captured_at == row.captured_at


def test_postgres_manual_radar_never_becomes_due(pg_repo):
    from datetime import UTC,datetime,timedelta
    uid=str(uuid4())
    radar=pg_repo.create_radar(uid,RadarCreate(name="手动",goal="寻找公开真实可核实的需求",frequency="manual"))
    pg_repo.save_radar(radar.model_copy(update={"next_run_at":datetime.now(UTC)-timedelta(days=1)}))
    assert (uid,radar.id) not in pg_repo.list_due_radars(datetime.now(UTC))


def test_same_request_cannot_change_collection_filters(pg_repo, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user,get_repository
    from app.core.security import CurrentUser
    from app.main import app
    from app.collectors.registry import registry
    uid=str(uuid4());calls=[]
    async def search(*args,**kwargs):
        calls.append(1)
        return [],None
    monkeypatch.setattr(registry,"search",search)
    monkeypatch.setitem(app.dependency_overrides,get_repository,lambda:pg_repo)
    monkeypatch.setitem(app.dependency_overrides,get_current_user,lambda:CurrentUser(id=uid))
    request={"request_id":str(uuid4()),"freshness_hours":24,"policy":{"sort":"hot"}}
    with TestClient(app) as client:
        first=client.post("/api/intelligence/evidence/collect?source=github&query=PPT",json=request)
        replay=client.post("/api/intelligence/evidence/collect?source=github&query=PPT",json=request)
        conflict=client.post("/api/intelligence/evidence/collect?source=github&query=PPT",json={**request,"freshness_hours":72})
    assert first.status_code == replay.status_code == 200 and first.json() == replay.json()
    assert conflict.status_code == 409 and calls == [1]


def test_filtered_domestic_empty_page_keeps_cursor_bound_to_policy(pg_repo, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user,get_repository
    from app.core.security import CurrentUser
    from app.main import app
    from app.collectors.registry import registry
    from app.services.billing_gateway import _context
    uid=str(uuid4());calls=[]
    async def search(*args,**kwargs):
        calls.append(1)
        _context.get()["next_cursor"]='{"position":2,"search_id":"s","search_session_id":"t"}'
        return [],None
    monkeypatch.setattr(registry,"search",search)
    monkeypatch.setattr(get_settings(),"paid_api_enabled",True)
    monkeypatch.setattr(get_settings(),"tikhub_api_key","offline-fixture")
    monkeypatch.setitem(app.dependency_overrides,get_repository,lambda:pg_repo)
    monkeypatch.setitem(app.dependency_overrides,get_current_user,lambda:CurrentUser(id=uid))
    request={"manual_confirmed":True,"request_id":str(uuid4()),"freshness_hours":24,"policy":{"required_terms":["PPT"]}}
    with TestClient(app) as client:
        first=client.post("/api/intelligence/evidence/collect?source=xiaohongshu&query=PPT",json=request)
        assert first.status_code == 200 and first.json()["next_cursor"]
        changed={**request,"request_id":str(uuid4()),"cursor":first.json()["next_cursor"],"freshness_hours":72}
        response=client.post("/api/intelligence/evidence/collect?source=xiaohongshu&query=PPT",json=changed)
    assert response.status_code == 400 and calls == [1]

def test_rls_denies_other_tenants_and_billing_writes(pg_repo):
    uid,other=str(uuid4()),str(uuid4())
    for user in (uid,other):pg_repo.get_profile(user)
    role="contract_"+uuid4().hex
    with pg_repo.engine.connect() as conn:
        tx=conn.begin()
        try:
            conn.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN')
            conn.exec_driver_sql(f'GRANT USAGE ON SCHEMA public,auth TO "{role}"')
            conn.exec_driver_sql(f'GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA public TO "{role}"')
            conn.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
            conn.execute(text("SELECT set_config('request.jwt.claim.sub',:uid,true)"),{"uid":uid})
            assert [str(x) for x in conn.execute(text("SELECT user_id FROM profiles")).scalars()] == [uid]
            assert conn.execute(text("UPDATE profiles SET display_name='bad' WHERE user_id=CAST(:uid AS uuid) RETURNING user_id"),{"uid":other}).first() is None
            with pytest.raises(Exception,match="row-level security"):
                with conn.begin_nested():
                    conn.execute(text("INSERT INTO billing_authorizations(user_id,scope,enabled,run_requests,daily_requests,run_micros,daily_micros) VALUES(CAST(:uid AS uuid),'evidence',true,1,1,1,1)"),{"uid":uid})
            for table in ("billing_calls","billing_authorizations","evidence_reviews","collection_receipts","schema_migrations","billing_batches","provider_responses","collection_requests","collector_cursors"):
                assert conn.execute(text(f'SELECT count(*) FROM {table}')).scalar() == 0
        finally:tx.rollback()


def test_debug_receipt_rls_reads_only_owner_and_never_writes(pg_repo):
    from app.services.collection_control import claim_request, issue_cursor
    uid, other = str(uuid4()), str(uuid4())
    for user in (uid, other):
        pg_repo.get_profile(user)
        claim_request(pg_repo, user, "receipt-test", "fixture")
        issue_cursor(pg_repo, user, "xiaohongshu", "PPT", '{"position":2}')
    role = "contract_" + uuid4().hex
    with pg_repo.engine.connect() as conn:
        tx = conn.begin()
        try:
            for user in (uid, other):
                call = str(uuid4())
                conn.execute(text("INSERT INTO billing_batches(id,user_id,providers,sources,request_limit,cost_limit_micros,request_limit_micros) VALUES(CAST(:uid AS text),CAST(:uid AS uuid),'[]','[]',1,1,1)"), {"uid":user})
                conn.execute(text("INSERT INTO billing_calls(id,user_id,scope,run_id,provider,source,scheduled,reserved_micros) VALUES(CAST(:call AS uuid),CAST(:uid AS uuid),'evidence',CAST(:call AS text),'tikhub','xiaohongshu',false,1)"), {"call":call,"uid":user})
                conn.execute(text("INSERT INTO provider_responses(call_id,user_id,endpoint,status_code,payload) VALUES(CAST(:call AS uuid),CAST(:uid AS uuid),'/search',200,'{}')"), {"call":call,"uid":user})
            conn.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN')
            conn.exec_driver_sql(f'GRANT USAGE ON SCHEMA public,auth TO "{role}"')
            conn.exec_driver_sql(f'GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA public TO "{role}"')
            conn.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
            conn.execute(text("SELECT set_config('request.jwt.claim.sub',:uid,true)"), {"uid":uid})
            for table in ("billing_batches", "provider_responses", "collection_requests"):
                assert [str(value) for value in conn.execute(text(f"SELECT user_id FROM {table}")).scalars()] == [uid]
                assert conn.execute(text(f"UPDATE {table} SET user_id=user_id RETURNING user_id")).first() is None
            assert conn.execute(text("SELECT count(*) FROM collector_cursors")).scalar_one() == 0
            with pytest.raises(Exception, match="row-level security"):
                with conn.begin_nested():
                    conn.execute(text("INSERT INTO collection_requests(id,user_id,fingerprint,status,result) VALUES('forged',CAST(:uid AS uuid),'bad','succeeded','{}')"), {"uid":uid})
        finally:
            tx.rollback()

def test_review_sync_and_duplicate_pipeline_update(pg_repo):
    uid=str(uuid4());evidence,item=build(pg_repo,uid)
    patch=PipelinePatch(status="ready_to_contact",notes="人工记录")
    pg_repo.update_pipeline(uid,item.id,patch);pg_repo.update_pipeline(uid,item.id,patch)
    with pg_repo.engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM opportunity_actions WHERE opportunity_id=CAST(:id AS uuid)"),{"id":item.id}).scalar() == 1
    pg_repo.review_evidence(uid,evidence.evidence_id,EvidenceReview(category="seller"))
    assert pg_repo.get_opportunity(uid,item.id).verification_status == "disputed"
    with pytest.raises(AppError):pg_repo.update_pipeline(uid,item.id,PipelinePatch(status="contacted"))

def test_metrics_unknown_values_and_collection_identity():
    repo=MemoryRepository();empty=acquisition_metrics(repo,"u")
    assert empty["actual_revenue"] is None and empty["reply_rate"] is None
    assert empty["collected"] == empty["buyer_evidence"] == 0
    build(repo,"u");repo.record_collection("u","r1","rss",7,1,6);repo.record_collection("u","r1","rss",7,1,6)
    repo.record_collection("other","r2","rss",999,999)
    metrics=acquisition_metrics(repo,"u")
    assert metrics["collected"] == 7 and metrics["effective_evidence"] == 1
    assert metrics["verified_buyer"] == 1 and metrics["contacted"] == metrics["won"] == 0
    assert metrics["actual_revenue"] is None
    assert metrics["source_yield"]["rss"]["collected"] == 7


def test_collect_same_request_returns_receipt_without_second_acquisition(pg_repo, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    from app.main import app
    from app.collectors.registry import registry
    from app.schemas.domain import RawItem
    uid, request_id = str(uuid4()), str(uuid4())
    pg_repo.get_profile(uid)
    calls = []
    async def search(source, query, **kwargs):
        calls.append(query)
        return [RawItem(external_id=request_id, title="需求", content="找人做PPT，预算1200元，本周交付", url="https://example.test/"+request_id, source="github", platform="github")], None
    monkeypatch.setattr(registry, "search", search)
    monkeypatch.setitem(app.dependency_overrides, get_repository, lambda: pg_repo)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: CurrentUser(id=uid))
    with TestClient(app) as client:
        first = client.post("/api/intelligence/evidence/collect?source=github&query=PPT", json={"request_id": request_id})
        again = client.post("/api/intelligence/evidence/collect?source=github&query=PPT", json={"request_id": request_id})
        conflict = client.post("/api/intelligence/evidence/collect?source=github&query=Word", json={"request_id": request_id})
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert calls == ["PPT"]
    assert conflict.status_code == 409
    assert pg_repo.collection_counts(uid)["collected"] == 1


def test_simultaneous_request_claims_have_one_owner(pg_repo):
    from concurrent.futures import ThreadPoolExecutor
    from app.services.collection_control import claim_request
    uid, request_id = str(uuid4()), str(uuid4())
    pg_repo.get_profile(uid)
    def claim(_):
        try:
            assert claim_request(pg_repo, uid, request_id, "same-fingerprint") is None
            return "owner"
        except AppError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(claim, range(8)))
    assert results.count("owner") == 1
    assert results.count("COLLECTION_IN_PROGRESS") == 7


def test_paid_collection_requires_request_identity(pg_repo, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    from app.main import app
    from app.collectors.registry import registry
    uid = str(uuid4())
    monkeypatch.setitem(app.dependency_overrides, get_repository, lambda: pg_repo)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: CurrentUser(id=uid))
    monkeypatch.setattr(get_settings(), "paid_api_enabled", True)
    monkeypatch.setattr(get_settings(), "tikhub_api_key", "offline-only")
    async def never(*args, **kwargs):
        pytest.fail("No acquisition without request identity")
    monkeypatch.setattr(registry, "search", never)
    with TestClient(app) as client:
        response = client.post("/api/intelligence/evidence/collect?source=douyin&query=PPT", json={"manual_confirmed":True})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "REQUEST_ID_REQUIRED"


def test_recent_source_update_survives_freshness_filter(pg_repo, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    from app.main import app
    from app.collectors.registry import registry
    from app.schemas.domain import RawItem
    uid = str(uuid4()); now = datetime.now(UTC)
    async def search(source, query, **kwargs):
        return [RawItem(external_id=uid, title="需求更新", content="需要修改企业官网，预算3000元", url="https://example.test/"+uid, source="github", platform="github", published_at=now-timedelta(days=400), updated_at_source=now-timedelta(days=1), metadata={"next_cursor": "20"})], None
    monkeypatch.setattr(registry, "search", search)
    monkeypatch.setitem(app.dependency_overrides, get_repository, lambda: pg_repo)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: CurrentUser(id=uid))
    with TestClient(app) as client:
        result = client.post("/api/intelligence/evidence/collect?source=github&query=官网", json={})
    assert result.status_code == 200
    assert result.json()["inserted"] == 1 and result.json()["stale"] == 0


@pytest.mark.parametrize("all_stale", [False, True])
def test_empty_domestic_page_has_tenant_bound_continuation(pg_repo, monkeypatch, all_stale):
    from datetime import UTC, datetime, timedelta
    from app.schemas.domain import RawItem
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    from app.main import app
    from app.collectors.registry import registry
    from app.collectors.tikhub_cn import XiaohongshuCollector
    from app.services.collection_control import resolve_cursor
    uid = str(uuid4()); pg_repo.get_profile(uid)
    monkeypatch.setattr(get_settings(), "paid_api_enabled", True)
    monkeypatch.setattr(get_settings(), "tikhub_api_key", "offline-only")
    async def page(self, query, cursor=None):
        items = [RawItem(external_id="stale", title="历史需求", content="2019年的旧需求，找人做PPT", url="https://example.test/stale", source="xiaohongshu", published_at=datetime.now(UTC)-timedelta(days=400))] if all_stale else []
        return items, '{"position":2,"search_id":"private-session","search_session_id":"session"}'
    monkeypatch.setattr(XiaohongshuCollector, "search_page", page)
    monkeypatch.setitem(app.dependency_overrides, get_repository, lambda: pg_repo)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: CurrentUser(id=uid))
    with TestClient(app) as client:
        result = client.post("/api/intelligence/evidence/collect?source=xiaohongshu&query=PPT", json={"manual_confirmed": True, "request_id":str(uuid4())})
    assert result.status_code == 200
    body = result.json()
    assert body["fetched"] == int(all_stale) and body["stale"] == int(all_stale)
    assert body["inserted"] == 0 and body["next_cursor"]
    assert "private-session" not in str(body)
    assert 'private-session' in resolve_cursor(pg_repo, uid, "xiaohongshu", "PPT", body["next_cursor"])
    with pytest.raises(AppError): resolve_cursor(pg_repo, str(uuid4()), "xiaohongshu", "PPT", body["next_cursor"])
    with pytest.raises(AppError): resolve_cursor(pg_repo, uid, "xiaohongshu", "Word", body["next_cursor"])


def test_collection_failure_is_replayed_without_network(pg_repo, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    from app.main import app
    from app.collectors.registry import registry
    uid = str(uuid4()); pg_repo.get_profile(uid); calls = []
    async def fail(*args, **kwargs):
        calls.append(1)
        return [], {"error_code": "PROVIDER_SCHEMA_CHANGED"}
    monkeypatch.setattr(registry, "search", fail)
    monkeypatch.setitem(app.dependency_overrides, get_repository, lambda: pg_repo)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: CurrentUser(id=uid))
    with TestClient(app) as client:
        for _ in range(2):
            result = client.post("/api/intelligence/evidence/collect?source=github&query=PPT", json={"request_id": str(uid)})
            assert result.status_code == 502
    assert calls == [1]


def test_billing_refusal_keeps_its_http_status(pg_repo, monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    from app.main import app
    from app.collectors.registry import registry
    from app.collectors.base import SourceAdapter
    class Denied(SourceAdapter):
        slug = "github"
        async def search(self, query):
            raise AppError("PAID_QUOTA_EXHAUSTED", "quota reached", 429)
    uid=str(uuid4())
    monkeypatch.setitem(registry._adapters,"github",Denied())
    monkeypatch.setitem(app.dependency_overrides,get_repository,lambda:pg_repo)
    monkeypatch.setitem(app.dependency_overrides,get_current_user,lambda:CurrentUser(id=uid))
    with TestClient(app) as client:
        result=client.post("/api/intelligence/evidence/collect?source=github&query=PPT",json={})
    assert result.status_code == 429

@pytest.mark.parametrize("url",["http://[::ffff:127.0.0.1]","http://169.254.169.254/latest","https://user:pass@example.com","file:///etc/passwd"])
def test_ssrf_unsafe_urls(url):
    with pytest.raises(AppError):validate_public_url(url)

def test_connection_time_dns_rebinding_and_pinned_ip(monkeypatch):
    from httpcore._backends.anyio import AnyIOBackend
    async def run():
        loop=asyncio.get_running_loop()
        async def resolution(*args,**kwargs):return [(2,1,6,"",("127.0.0.1",443))]
        monkeypatch.setattr(loop,"getaddrinfo",resolution)
        with pytest.raises(AppError):await PublicNetworkBackend().connect_tcp("safe.example",443)
        async def resolution(*args,**kwargs):return [(2,1,6,"",("8.8.8.8",443))]
        monkeypatch.setattr(loop,"getaddrinfo",resolution);captured=[]
        async def connect(self,host,*args,**kwargs):captured.append(host);return "stream"
        monkeypatch.setattr(AnyIOBackend,"connect_tcp",connect)
        assert await PublicNetworkBackend().connect_tcp("safe.example",443) == "stream"
        assert captured == ["8.8.8.8"]
    asyncio.run(run())

def test_redirects_are_not_followed_and_free_retry_is_bounded(monkeypatch):
    monkeypatch.setattr("app.collectors.http.validate_public_url",lambda _:"public.example");requests=[]
    async def run():
        def respond(req):requests.append(req);return httpx.Response(302,headers={"Location":"http://127.0.0.1"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with pytest.raises(httpx.HTTPStatusError):await HttpFetcher(client=client,min_interval=0).get_json("https://public.example")
        assert len(requests) == 1;requests.clear()
        def fail(req):requests.append(req);return httpx.Response(503)
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            with pytest.raises(httpx.HTTPStatusError):await HttpFetcher(client=client,retries=1,min_interval=0).get_json("https://public.example")
        assert len(requests) == 2
    asyncio.run(run())

def test_worker_and_api_share_production_guard(monkeypatch):
    monkeypatch.setattr(get_settings(),"app_env","production");monkeypatch.setattr(get_settings(),"auth_disabled",True)
    with pytest.raises(RuntimeError):validate_runtime()

def test_redis_queue_duplicate_job_contract(monkeypatch):
    url=os.getenv("TEST_REDIS_URL")
    if not url:pytest.skip("TEST_REDIS_URL not configured")
    from arq import create_pool
    from app.workers.queue import redis_settings
    monkeypatch.setattr(get_settings(),"redis_url",url)
    async def run():
        pool=await create_pool(redis_settings());key="contract:"+uuid4().hex
        try:
            assert await pool.ping()
            first=await pool.enqueue_job("contract_only",_job_id=key)
            second=await pool.enqueue_job("contract_only",_job_id=key)
            assert first is not None and second is None
            assert (await first.info()).function == "contract_only"
        finally:
            await pool.zrem("arq:queue",key)
            await pool.delete("arq:job:"+key)
            await pool.aclose()
    asyncio.run(run())


def test_manual_crash_recovery_pauses_radar_without_replaying(pg_repo):
    uid=str(uuid4());radar=pg_repo.create_radar(uid,RadarCreate(name="恢复",goal="寻找真实公开的企业制作需求"));run=pg_repo.create_run(radar.id)
    with pytest.raises(AppError):pg_repo.recover_run(uid,run.id,"进程终止，人工确认任务已停止")
    with pg_repo.engine.begin() as conn:
        conn.execute(text("UPDATE radar_runs SET started_at=now()-interval '20 minutes',status='running' WHERE id=CAST(:id AS uuid)"),{"id":run.id})
    recovered=pg_repo.recover_run(uid,run.id,"进程终止，人工确认任务已停止")
    assert recovered.status == "failed" and recovered.error_code == "MANUAL_RECOVERY"
    assert pg_repo.get_radar(uid,radar.id).status == "paused"
    assert pg_repo.claim_run(uid,run.id) is None

@pytest.mark.parametrize("goal,text,service",[
    ("寻找PPT Word PDF简历及论文规范辅导需求","找人做PPT，预算1200元，本周交付，需要排版与动画。","PPT"),
    ("寻找AI视频广告商品宣传网站及小程序项目","需要制作商品视频，预算3000元，本周交付品牌宣传片。","AI视频"),
])
def test_two_offline_business_radars_closed_loop(goal,text,service):
    from app.services.radar_run_service import RadarRunService
    from app.schemas.domain import RawItem,ProfileUpsert
    from app.schemas.pipeline import QuoteRequest
    from app.services.acquisition_service import quote_draft,outreach_draft
    from app.api.intelligence import convert_evidence
    from app.schemas.evidence import EvidenceConversion
    from app.core.security import CurrentUser
    class Fixed:
        async def search(self,*args):
            from datetime import UTC,datetime
            return [RawItem(external_id="synthetic-1",title="合成回归样本",content=text,url="https://example.test/synthetic",source="rss",published_at=datetime.now(UTC))],None
    repo=MemoryRepository();uid="isolated-synthetic-scenario"
    repo.save_profile(uid,ProfileUpsert(display_name="合成场景",skills=[{"name":service}],goals=["client"]))
    radar=repo.create_radar(uid,RadarCreate(name=service,goal=goal,keywords=[service],sources=["rss"]))
    run=asyncio.run(RadarRunService(repo,Fixed()).run(uid,radar.id,repo.create_run(radar.id).id))
    evidence=repo.list_evidence(uid)[0]
    assert evidence.category == "buyer" and evidence.verification_status == "unverified"
    repo.review_evidence(uid,evidence.evidence_id,EvidenceReview(verification_status="verified",notes="测试中的模拟审核，不是真实客户"))
    item=asyncio.run(convert_evidence(evidence.evidence_id,EvidenceConversion(title=service,summary=text),CurrentUser(uid),repo))
    draft=quote_draft(item,QuoteRequest(hourly_rate=100,estimated_hours=5,scope="测试交付范围，不能作为真实报价",service_type=service))
    assert len(draft["plans"]) == 3 and item.source_url in outreach_draft(item)
    repo.update_pipeline(uid,item.id,PipelinePatch(status="ready_to_contact",quote_draft=draft))
    for stage in ("contacted","replied","quoted","won"):
        repo.update_pipeline(uid,item.id,PipelinePatch(status=stage,actual_revenue=100 if stage == "won" else None))
    assert acquisition_metrics(repo,uid)["won"] == 1
    rerun=asyncio.run(RadarRunService(repo,Fixed()).run(uid,radar.id,repo.create_run(radar.id).id))
    assert rerun.stats.opportunities_found == 0 and len(repo.list_opportunities(uid)) == 1


def test_source_edit_preserves_revision_and_requires_new_review(pg_repo):
    from app.schemas.evidence import EvidenceBatch
    uid=str(uuid4());evidence,item=build(pg_repo,uid)
    changed=EvidenceBatch(batch_id="source-edit",items=[{"source":evidence.source,"url":str(evidence.url),"raw_text":"需求已取消，不再找人做PPT。","category":"market"}])
    result=pg_repo.upsert_evidence_batch(uid,changed)
    assert result.inserted == 0 and result.records[0].evidence_id == evidence.evidence_id
    assert result.records[0].verification_status == "disputed"
    assert pg_repo.get_opportunity(uid,item.id).verification_status == "disputed"
    with pg_repo.engine.connect() as conn:
        assert conn.execute(text("SELECT previous->>'raw_text' FROM evidence_revisions WHERE evidence_id=CAST(:id AS uuid)"),{"id":evidence.evidence_id}).scalar() == evidence.raw_text


def test_prod_jwt_requires_expiration_and_valid_user_id(monkeypatch):
    from jose import jwt
    from app.core.security import current_user
    from starlette.requests import Request
    settings=get_settings();monkeypatch.setattr(settings,"auth_disabled",False);monkeypatch.setattr(settings,"app_env","production")
    request=Request({"type":"http","headers":[],"client":("127.0.0.1",1)})
    for claims in ({"sub":str(uuid4()),"aud":"authenticated"},{"sub":"bad","aud":"authenticated","exp":4102444800}):
        token=jwt.encode(claims,settings.supabase_jwt_secret,algorithm="HS256")
        with pytest.raises(AppError):asyncio.run(current_user(request,"Bearer "+token))


def test_migration_ledger_second_execution_is_noop(pg_repo):
    from pathlib import Path
    from app.database.migrate import migrate
    assert migrate(get_settings().database_url,Path('../supabase/migrations')) == 0


def test_applied_migration_checksum_cannot_silently_change(pg_repo,tmp_path):
    from pathlib import Path
    from app.database.migrate import migrate
    original=Path('../supabase/migrations/202610130006_evidence_revisions.sql')
    (tmp_path/original.name).write_text(original.read_text()+'\n-- unapproved modification\n')
    with pytest.raises(RuntimeError,match='Applied migration changed'):
        migrate(get_settings().database_url,tmp_path)
