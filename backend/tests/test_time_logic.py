"""P0-1 / P0-2 regression tests: freshness must use activity time, not created_at."""

import asyncio
from datetime import UTC, datetime, timedelta

from app.collectors.github import GitHubCollector
from app.collectors.web_search import WebSearchCollector
from app.schemas.domain import RawItem
from app.services.radar_run_service import activity_time

NOW = datetime.now(UTC)


def test_activity_time_prefers_latest_platform_activity():
    created = NOW - timedelta(days=365 * 6)
    pushed = NOW - timedelta(hours=2)
    item = RawItem(external_id="1", title="t", content="c", url="https://github.com/a/b", source="github", published_at=created, updated_at_source=pushed)
    assert activity_time(item) == pushed


def test_activity_time_none_when_undated():
    item = RawItem(external_id="1", title="t", content="c", url="https://x/1", source="web_search")
    assert activity_time(item) is None


def test_old_repo_with_recent_push_is_not_freshness_killed():
    """2019 年创建、今天爆发的仓库不能因 created_at 太旧被丢弃。"""
    created = NOW - timedelta(days=365 * 7)
    pushed = NOW - timedelta(hours=1)
    item = RawItem(external_id="1", title="old repo", content="c", url="https://github.com/a/b", source="github", published_at=created, updated_at_source=pushed)
    stamp = activity_time(item)
    assert stamp is not None and stamp >= NOW - timedelta(hours=72)


def test_old_repo_without_activity_stamp_still_ages_out():
    created = NOW - timedelta(days=365 * 7)
    item = RawItem(external_id="1", title="dormant repo", content="c", url="https://github.com/a/c", source="github", published_at=created)
    stamp = activity_time(item)
    assert stamp == created  # falls back to published_at and WILL be filtered


def test_github_collector_maps_all_three_timestamps(monkeypatch):
    created = "2019-03-01T00:00:00Z"
    pushed = "2026-10-06T08:00:00Z"
    updated = "2026-10-06T09:00:00Z"

    async def fake_json(url, **kwargs):
        return {"items": [{"id": 7, "full_name": "acme/old-but-hot", "html_url": "https://github.com/acme/old-but-hot", "description": "suddenly trending", "owner": {"login": "acme"}, "created_at": created, "updated_at": updated, "pushed_at": pushed, "stargazers_count": 999, "forks_count": 12, "open_issues_count": 3, "language": "Python", "topics": ["ai"]}]}

    monkeypatch.setattr("app.collectors.github.fetcher.get_json", fake_json)
    items = asyncio.run(GitHubCollector().search("hot repos"))
    item = items[0]
    assert item.published_at is not None and item.published_at.year == 2019
    assert item.updated_at_source is not None and item.updated_at_source.year == 2026
    assert item.metadata["created_at"] == created
    assert item.metadata["pushed_at"] == pushed
    assert item.engagement["stars"] == 999
    assert item.platform == "github"


def _with_firecrawl_key(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setattr("app.collectors.web_search.get_settings", lambda: Settings(firecrawl_api_key="test-key"))


def test_web_search_extracts_nested_dates(monkeypatch):
    _with_firecrawl_key(monkeypatch)
    payload = {
        "data": [
            {"url": "https://blog.example/post", "title": "AI video tools", "description": "guide", "metadata": {"publishedAt": "2026-10-05T10:00:00Z"}},
        ]
    }

    async def fake_post_json(url, body, **kwargs):
        return payload

    monkeypatch.setattr("app.collectors.web_search.fetcher.post_json", fake_post_json)
    items = asyncio.run(WebSearchCollector().search("ai video"))
    assert items[0].published_at is not None
    assert items[0].published_at.year == 2026


def test_web_search_undated_still_returns_items(monkeypatch):
    _with_firecrawl_key(monkeypatch)
    payload = {"data": [{"url": "https://nodate.example/x", "title": "no date", "description": "d"}]}

    async def fake_post_json(url, body, **kwargs):
        return payload

    monkeypatch.setattr("app.collectors.web_search.fetcher.post_json", fake_post_json)
    items = asyncio.run(WebSearchCollector().search("q"))
    assert len(items) == 1
    assert items[0].published_at is None  # passes freshness gate as undatable
