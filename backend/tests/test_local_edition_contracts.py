import asyncio
from uuid import uuid4
import os
from urllib.parse import urlsplit

import pytest
from starlette.requests import Request

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import current_user
from app.repositories.memory import MemoryRepository
from app.schemas.domain import RadarCreate, RawItem
from app.services.ai_service import plan_queries
from app.services.radar_run_service import RadarRunService


LOCAL_USER = "11111111-1111-4111-8111-111111111111"
PROXY_SECRET = "a" * 64


def _local_settings(**overrides):
    values = {
        "app_env": "local",
        "database_url": "postgresql+psycopg://postgres:secret@127.0.0.1:54330/opportunity_radar",
        "redis_url": "redis://127.0.0.1:6380/0",
        "use_in_memory_store": False,
        "auth_disabled": False,
        "local_user_id": LOCAL_USER,
        "local_proxy_token": PROXY_SECRET,
        "local_session_secret": "b" * 64,
        "paid_api_enabled": False,
        "enable_ai_classification": False,
        "local_classifier_mode": "off",
        "allow_retention_delete": False,
    }
    values.update(overrides)
    return Settings(**values)


def _request(*, headers=(), client_host="127.0.0.1"):
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/local/overview",
        "raw_path": b"/api/local/overview",
        "query_string": b"",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers],
        "client": (client_host, 50000),
        "server": ("127.0.0.1", 8015),
    })


@pytest.mark.asyncio
async def test_local_api_requires_loopback_host_and_server_proxy_secret(monkeypatch):
    monkeypatch.setattr("app.core.security.get_settings", lambda: _local_settings())
    valid = _request(headers=[("host", "127.0.0.1:8015"), ("x-or-local-proxy", PROXY_SECRET)])
    assert (await current_user(valid)).id == LOCAL_USER

    for request, expected in (
        (_request(headers=[("host", "127.0.0.1:8015")], client_host="192.0.2.4"), "LOCAL_MODE_REMOTE_FORBIDDEN"),
        (_request(headers=[("host", "evil.example"), ("x-or-local-proxy", PROXY_SECRET)]), "LOCAL_HOST_REJECTED"),
        (_request(headers=[("host", "127.0.0.1:8015"), ("x-or-local-proxy", "wrong")]), "LOCAL_PROXY_AUTH_REQUIRED"),
        (_request(headers=[("host", "127.0.0.1:8015"), ("x-or-local-proxy", PROXY_SECRET), ("x-forwarded-for", "127.0.0.1")]), "LOCAL_MODE_REMOTE_FORBIDDEN"),
    ):
        with pytest.raises(AppError) as caught:
            await current_user(request)
        assert caught.value.code == expected


def test_local_runtime_fails_closed_for_auth_storage_paid_ai_and_mock(monkeypatch):
    from app.core.config import validate_runtime

    monkeypatch.setattr("app.core.config.get_settings", lambda: _local_settings())
    monkeypatch.setenv("INCLUDE_MOCK_COLLECTOR", "false")
    validate_runtime()
    for overrides, message in (
        ({"auth_disabled": True}, "AUTH_DISABLED"),
        ({"database_url": ""}, "PostgreSQL and Redis"),
        ({"database_url": "postgresql://postgres:secret@db/opportunity_radar"}, "loopback-only"),
        ({"paid_api_enabled": True}, "remain disabled"),
        ({"local_user_id": "not-a-uuid"}, "LOCAL_USER_ID"),
    ):
        monkeypatch.setattr("app.core.config.get_settings", lambda overrides=overrides: _local_settings(**overrides))
        with pytest.raises(RuntimeError, match=message):
            validate_runtime()
    monkeypatch.setattr("app.core.config.get_settings", lambda: _local_settings())
    monkeypatch.setenv("INCLUDE_MOCK_COLLECTOR", "true")
    with pytest.raises(RuntimeError, match="mock collectors"):
        validate_runtime()


def test_general_radar_query_plan_keeps_the_user_topic_without_sales_terms():
    radar = RadarCreate(name="AI 观察", goal="AI agent release notes", mode="general", sources=["github"], keywords=["AI agent"])
    plans = asyncio.run(plan_queries(radar))
    assert [item.query for item in plans] == ["AI agent"]
    assert all("有偿" not in item.query and "找客户" not in item.query for item in plans)


def test_general_radar_collects_saves_and_deduplicates_without_acquisition_analysis():
    repo = MemoryRepository()
    radar = repo.create_radar(LOCAL_USER, RadarCreate(
        name="AI 项目更新", goal="AI agent release notes", mode="general",
        sources=["github"], keywords=["AI agent"], frequency="manual",
    ))

    class Collector:
        def __init__(self):
            self.queries = []

        async def search(self, slug, query, cursor=None, *, paged=False, source_config=None):
            self.queries.append((slug, query))
            return [RawItem(
                external_id="project-1", title="AI agent release notes", content="The project published a new agent workflow and API update.",
                # Pydantic HttpUrl canonicalizes a bare host to a trailing slash.
                url="https://example.org", source="github", published_at=None,
                metadata={"content_kind": "article"}, engagement={"stars": 12},
            )], None

    collector = Collector()
    service = RadarRunService(repo, collector)
    first = repo.create_run(radar.id)
    result = asyncio.run(service.run(LOCAL_USER, radar.id, first.id))

    assert result.status == "completed"
    assert collector.queries == [("github", "AI agent")]
    assert result.stats.opportunities_found == 0
    assert result.stage_stats["embedding_calls"] == 0
    assert not repo.llm_calls
    assert LOCAL_USER not in repo.profiles
    evidence = repo.list_intelligence_feed(LOCAL_USER, radar_id=radar.id)
    assert len(evidence) == 1
    assert evidence[0].radars[0]["radar_id"] == radar.id
    assert evidence[0].published_at is None
    assert evidence[0].intelligence_ranking["version"] == "general-v1"
    assert "新鲜度未参与排序" in " ".join(evidence[0].intelligence_ranking["reasons"])

    saved = repo.update_evidence_state(LOCAL_USER, evidence[0].evidence_id, saved=True)
    assert saved.is_saved
    repeated = repo.create_run(radar.id)
    second_result = asyncio.run(service.run(LOCAL_USER, radar.id, repeated.id))
    after_repeat = repo.list_intelligence_feed(LOCAL_USER, radar_id=radar.id)
    assert second_result.stats.duplicates_removed == 1
    assert len(after_repeat) == 1
    assert after_repeat[0].is_saved


def test_local_queue_does_not_run_synchronously_when_redis_is_missing(monkeypatch):
    from app.workers import queue

    monkeypatch.setattr("app.workers.queue.get_settings", lambda: _local_settings(redis_url=""))
    calls = []

    async def execute_inline(*args):
        calls.append(args)

    monkeypatch.setattr(queue, "execute_radar_run", execute_inline)
    with pytest.raises(AppError) as caught:
        asyncio.run(queue.enqueue_radar_run(LOCAL_USER, str(uuid4()), str(uuid4())))
    assert caught.value.code == "LOCAL_REDIS_REQUIRED"
    assert calls == []


def test_postgres_local_feed_persists_ranking_bookmark_and_multi_radar_attribution():
    """Opt-in only: require a dedicated loopback QA database, never DATABASE_URL/.env."""
    database_url = os.getenv("LOCAL_CONTRACT_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("LOCAL_CONTRACT_DATABASE_URL not configured")
    parsed = urlsplit(database_url.replace("postgresql+psycopg://", "postgresql://"))
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or not parsed.path.lstrip("/").startswith("opportunity_radar_contract_"):
        pytest.fail("LOCAL_CONTRACT_DATABASE_URL must target a dedicated loopback opportunity_radar_contract_* database")

    from sqlalchemy import create_engine
    from app.repositories.postgres import PostgresRepository
    from app.schemas.evidence import EvidenceBatch

    user_id = str(uuid4())
    repository = PostgresRepository(create_engine(database_url, pool_pre_ping=True))
    first_radar = repository.create_radar(user_id, RadarCreate(
        name="Local AI watch", goal="Track public AI agent releases", mode="general", sources=["rss"],
    ))
    second_radar = repository.create_radar(user_id, RadarCreate(
        name="Local open-source watch", goal="Track public AI agent releases", mode="general", sources=["github"],
    ))
    evidence = repository.upsert_evidence_batch(user_id, EvidenceBatch(
        batch_id=f"local-contract-{uuid4()}",
        items=[{
            "source": "rss", "url": f"https://example.org/local-contract/{uuid4()}",
            "raw_text": "A public AI agent project published a new release and usage guide.",
            "category": "content", "published_at": None,
        }],
    )).records[0]
    ranking = {
        "version": "general-v1", "score": 74,
        "dimensions": {"topic_relevance": 82, "freshness": None, "novelty": 90, "source_quality": 55, "engagement": None},
        "reasons": ["主题匹配：AI agent", "新颖度较高", "发布时间未知，未计入时效分"],
    }
    repository.link_evidence_to_radar(user_id, first_radar.id, evidence.evidence_id, None, 74, ranking["reasons"], ranking)
    repository.link_evidence_to_radar(user_id, second_radar.id, evidence.evidence_id, None, 68, ["GitHub 主题匹配"], {**ranking, "score": 68})
    repository.update_evidence_state(user_id, evidence.evidence_id, saved=True, read=True)

    reopened = PostgresRepository(create_engine(database_url, pool_pre_ping=True))
    stored = reopened.get_evidence(user_id, evidence.evidence_id)
    assert stored.is_saved is True and stored.is_read is True
    assert len(stored.radars) == 2
    assert stored.intelligence_ranking == ranking
    assert reopened.list_intelligence_feed(user_id, saved=True, unread=False, limit=10)[0].evidence_id == evidence.evidence_id
    assert reopened.list_intelligence_feed(user_id, saved=False, limit=10) == []

    with pytest.raises(AppError) as hidden:
        reopened.get_evidence(str(uuid4()), evidence.evidence_id)
    assert hidden.value.code == "EVIDENCE_NOT_FOUND"
