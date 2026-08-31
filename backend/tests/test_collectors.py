import asyncio
import pytest
from app.collectors.base import SourceAdapter
from app.collectors.github import GitHubCollector
from app.collectors.hackernews import HackerNewsCollector
from app.collectors.http import validate_public_url
from app.collectors.mock import MockCollector
from app.collectors.registry import CollectorRegistry
from app.core.errors import AppError
from app.schemas.domain import RadarCreate, RawItem
from app.services.ai_service import plan_queries


def test_ssrf_rejects_loopback_and_localhost():
    with pytest.raises(AppError):
        validate_public_url("http://127.0.0.1/secret")
    with pytest.raises(AppError):
        validate_public_url("http://localhost/admin")
    with pytest.raises(AppError):
        validate_public_url("ftp://example.com/file")


def test_ssrf_rejects_resolved_private_ip():
    def resolver(host, port):
        return [(0, 0, 0, "", ("10.0.0.8", 0))]

    with pytest.raises(AppError) as blocked:
        validate_public_url("https://internal.example", resolver=resolver)
    assert blocked.value.code == "BLOCKED_HOST"


def test_github_collector_maps_raw_items(monkeypatch):
    async def fake_json(url, **kwargs):
        return {"items": [{"id": 1, "full_name": "acme/agent", "html_url": "https://github.com/acme/agent", "description": "AI agent", "owner": {"login": "acme"}, "created_at": "2026-01-01T00:00:00Z", "stargazers_count": 12, "language": "Python", "topics": ["ai"]}]}

    monkeypatch.setattr("app.collectors.github.fetcher.get_json", fake_json)
    items = asyncio.run(GitHubCollector().search("AI Agent"))
    assert items[0].source == "github"
    assert items[0].external_id == "1"
    assert items[0].url == "https://github.com/acme/agent"
    assert items[0].author == "acme"
    assert "ai" in items[0].metadata["topics"]


def test_hackernews_collector_maps_raw_items(monkeypatch):
    async def fake_json(url, **kwargs):
        return {"hits": [{"objectID": "42", "title": "Show HN: n8n", "url": "https://news.ycombinator.com/item?id=42", "author": "pg", "created_at": "2026-01-01T00:00:00.000Z", "points": 10, "num_comments": 3}]}

    monkeypatch.setattr("app.collectors.hackernews.fetcher.get_json", fake_json)
    items = asyncio.run(HackerNewsCollector().search("Show HN"))
    assert items[0].source == "hackernews"
    assert items[0].external_id == "42"
    assert items[0].title.startswith("Show HN")


class BoomCollector(SourceAdapter):
    slug = "boom"

    async def search(self, query: str) -> list[RawItem]:
        raise RuntimeError("source down")


def test_registry_isolates_collector_failure():
    registry = CollectorRegistry([BoomCollector(), MockCollector()])

    async def scenario():
        failed_items, error = await registry.search("boom", "x")
        ok_items, ok_error = await registry.search("mock", "x")
        unknown_items, unknown_error = await registry.search("nope", "x")
        assert failed_items == []
        assert error["error_code"] == "COLLECTOR_FAILED"
        assert ok_items and ok_error is None
        assert unknown_items == []
        assert unknown_error["error_code"] == "UNKNOWN_SOURCE"

    asyncio.run(scenario())


def test_plan_queries_uses_selected_sources():
    queries = asyncio.run(plan_queries(RadarCreate(name="AI", goal="寻找 AI Agent 开源项目", keywords=["AI Agent"], locations=["远程"], sources=["github", "hackernews"])))
    assert queries
    assert {item.source for item in queries} <= {"github", "hackernews"}
    assert "github" in {item.source for item in queries}
