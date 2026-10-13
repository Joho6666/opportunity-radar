from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_repository
from app.collectors.registry import registry
from app.core.config import get_settings
from app.core.security import CurrentUser
from app.main import app
from app.repositories.memory import MemoryRepository
from app.schemas.domain import RawItem


def _setup(monkeypatch, search_result=None, *, tikhub_key="", firecrawl_key=""):
    repository = MemoryRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="collect-user")
    if search_result is None:
        search_result = [RawItem(external_id="1", title="title", content="A sufficiently long evidence text.", url="https://example.test/1", source="github", platform="github", metadata={"keep": "yes"})]

    async def fake_search(source, query):
        fake_search.calls.append((source, query))
        return search_result, None

    fake_search.calls = []
    monkeypatch.setattr(registry, "search", fake_search)
    settings = get_settings()
    monkeypatch.setattr(settings, "tikhub_api_key", tikhub_key)
    monkeypatch.setattr(settings, "firecrawl_api_key", firecrawl_key)
    return repository, fake_search


def test_runtime_reports_storage_and_source_configuration(monkeypatch):
    _setup(monkeypatch)
    client = TestClient(app)
    try:
        response = client.get("/api/intelligence/evidence/runtime")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()
    assert payload["storage_mode"] == "memory"
    assert payload["sources"]["github"]["configured"] is True
    assert payload["sources"]["tikhub"]["configured"] is False
    assert payload["sources"]["web_search"]["configured"] is False
    assert "api_key" not in str(payload).lower()


def test_collect_converts_items_persists_and_rejects_short_text(monkeypatch):
    items = [
        RawItem(external_id="1", title="title", content="A sufficiently long evidence text.", url="https://example.test/1", source="github", platform="github", metadata={"keep": "yes"}),
        RawItem(external_id="2", title="short", content="tiny", url="https://example.test/2", source="github", platform="github"),
    ]
    repository, fake_search = _setup(monkeypatch, items)
    client = TestClient(app)
    try:
        response = client.post("/api/intelligence/evidence/collect?source=github&query=agents", json={"manual_confirmed": False})
        replay = client.post("/api/intelligence/evidence/collect?source=github&query=agents", json={"manual_confirmed": False})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["fetched"] == 2
    assert response.json()["inserted"] == 1
    assert response.json()["rejected"] == 1
    assert response.json()["records"][0]["metadata"]["keep"] == "yes"
    assert replay.json()["duplicates"] == 1
    assert len(fake_search.calls) == 2
    assert len(repository.list_evidence("collect-user")) == 1


def test_billable_missing_key_and_missing_confirmation_block_registry(monkeypatch):
    _, fake_search = _setup(monkeypatch)
    client = TestClient(app)
    try:
        missing_key = client.post("/api/intelligence/evidence/collect?source=tikhub&query=video", json={"manual_confirmed": True})
        not_confirmed = client.post("/api/intelligence/evidence/collect?source=github&query=repo", json={"manual_confirmed": False})
        paid_not_confirmed = client.post("/api/intelligence/evidence/collect?source=web_search&query=repo", json={"manual_confirmed": False})
    finally:
        app.dependency_overrides.clear()
    assert missing_key.status_code == 400
    assert missing_key.json()["error"]["code"] == "SOURCE_NOT_CONFIGURED"
    assert not_confirmed.status_code == 200
    assert paid_not_confirmed.status_code == 400
    assert paid_not_confirmed.json()["error"]["code"] == "MANUAL_CONFIRMATION_REQUIRED"
    assert fake_search.calls == [("github", "repo")]


def test_empty_success_and_provider_failure_are_explicit(monkeypatch):
    _, fake_search = _setup(monkeypatch, [])
    client = TestClient(app)
    try:
        empty = client.post("/api/intelligence/evidence/collect?source=github&query=none", json={})
        async def failed(source, query):
            return [], {"error_code": "COLLECTOR_FAILED", "message": "secret provider detail"}
        monkeypatch.setattr(registry, "search", failed)
        failed_response = client.post("/api/intelligence/evidence/collect?source=github&query=fail", json={})
    finally:
        app.dependency_overrides.clear()
    assert empty.status_code == 200
    assert empty.json()["fetched"] == empty.json()["inserted"] == empty.json()["duplicates"] == 0
    assert failed_response.status_code == 502
    assert failed_response.json()["error"]["code"] == "COLLECTOR_FAILED"
    assert "secret provider detail" not in str(failed_response.json())


def test_collect_drops_stale_posts_and_requires_confirmation_for_domestic_sources(monkeypatch):
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    items = [
        RawItem(external_id="new", title="t", content="找人做小程序，预算 3000，月底交付", url="https://example.test/new", source="douyin", platform="douyin", published_at=now - timedelta(days=2)),
        RawItem(external_id="old", title="t", content="2019 年的老帖子，内容足够长", url="https://example.test/old", source="douyin", platform="douyin", published_at=now - timedelta(days=400)),
        RawItem(external_id="undated", title="t", content="没有发布时间的帖子也保留", url="https://example.test/undated", source="douyin", platform="douyin"),
    ]
    repository, fake_search = _setup(monkeypatch, items, tikhub_key="k")
    client = TestClient(app)
    try:
        refused = client.post("/api/intelligence/evidence/collect?source=douyin&query=剪辑", json={"manual_confirmed": False})
        response = client.post("/api/intelligence/evidence/collect?source=douyin&query=剪辑", json={"manual_confirmed": True})
    finally:
        app.dependency_overrides.clear()
    assert refused.status_code == 400 and refused.json()["error"]["code"] == "MANUAL_CONFIRMATION_REQUIRED"
    body = response.json()
    assert body["fetched"] == 3 and body["stale"] == 1 and body["inserted"] == 2
    assert {r["external_id"] for r in body["records"]} == {"new", "undated"}
    assert fake_search.calls == [("douyin", "剪辑")]
