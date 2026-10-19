"""Offline contract/parser tests for the four limited-mode sources.

Fixtures are reduced copies of real paid responses (2026-10-18); request ids
and prices live in tikhub-mode-verification.json.
"""
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.errors import AppError
from app.schemas.domain import RadarCreate

FIXTURES = Path(__file__).parent / "fixtures" / "tikhub_live"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_channel_and_link_parsers_are_strict():
    from app.collectors.tikhub_modes import parse_telegram_channels, parse_toutiao_links

    assert parse_telegram_channels("@Foo, https://t.me/bar\nbaz") == ["Foo", "bar", "baz"]
    assert parse_telegram_channels("bad name!, @ok_name") == ["bad", "ok_name"]
    with pytest.raises(AppError) as error:
        parse_telegram_channels("a,b,c,d")
    assert error.value.code == "TELEGRAM_CHANNELS_LIMIT"

    links = parse_toutiao_links("https://www.toutiao.com/article/7450114952884503059/\n"
                                "https://m.toutiao.com/article/7450114952884503059/?source=x")
    assert links == [{"id": "7450114952884503059", "url": "https://www.toutiao.com/article/7450114952884503059/"}]
    assert parse_toutiao_links("https://example.com/article/123") == []
    with pytest.raises(AppError) as error:
        parse_toutiao_links("https://www.toutiao.com/article/7450114952884503059/," * 4)
    assert error.value.code in {"TOUTIAO_LINKS_LIMIT", "TOUTIAO_LINK_INVALID"}


@pytest.mark.asyncio
async def test_telegram_maps_real_channel_search_and_requires_channels(monkeypatch):
    from app.collectors.tikhub_modes import TelegramChannelCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tikhub_api_key", "offline-fixture")
    urls: list[str] = []

    async def fake_get(url, **kwargs):
        assert kwargs.get("billable_provider") == "tikhub"
        urls.append(url)
        return load("telegram_channel_search.json")

    monkeypatch.setattr(fetcher, "get_json", fake_get)
    items = await TelegramChannelCollector().search_configured("video", {"telegram_channels": "@telegram,@durov"})
    assert len(urls) == 2
    assert parse_qs(urlparse(urls[0]).query) == {"channel": ["telegram"], "query": ["video"], "limit": ["20"]}
    assert len(items) == 12  # 6 fixture messages per channel
    first = items[0]
    assert first.url == "https://t.me/telegram/411"
    assert first.platform == "telegram" and first.source == "telegram"
    assert first.published_at == datetime(2025, 10, 14, 16, 9, 25, tzinfo=UTC)
    assert first.metadata["channel"] == "telegram"
    assert first.metadata["content_kind"] == "channel_post"
    assert "指定频道" in first.metadata["mode_note"]

    with pytest.raises(AppError) as error:
        await TelegramChannelCollector().search_configured("video", {})
    assert error.value.code == "TELEGRAM_CHANNELS_REQUIRED"


@pytest.mark.asyncio
async def test_linkedin_maps_jobs_as_hiring_signal_not_buyer(monkeypatch):
    from app.collectors.tikhub_modes import LinkedInJobsCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tikhub_api_key", "offline-fixture")
    calls: list[str] = []

    async def fake_get(url, **kwargs):
        assert kwargs.get("billable_provider") == "tikhub"
        calls.append(url)
        return load("linkedin_search_jobs.json")

    monkeypatch.setattr(fetcher, "get_json", fake_get)
    items = await LinkedInJobsCollector().search_configured("video editor", {})
    assert len(calls) == 1
    query = parse_qs(urlparse(calls[0]).query)
    assert query["keywords"] == ["video editor"] and query["geo_code"] == ["92000000"]
    assert len(items) == 6
    first = items[0]
    assert first.title == "Toplinestudios · Freelance Video Editor"
    assert first.url == "https://www.linkedin.com/jobs/view/4478226804"
    assert first.metadata["lead_kind"] == "hiring_signal"
    assert first.metadata["company"] == "Toplinestudios"
    assert first.metadata["job_title"] == "Freelance Video Editor"
    assert first.metadata["location"] == "Pakistan"
    assert first.published_at == datetime(2026, 10, 18, 17, 10, 4, tzinfo=UTC)
    assert "招聘信号" in first.content and "不是买方" in first.content
    assert first.metadata["content_kind"] == "job_posting"


@pytest.mark.asyncio
async def test_linkedin_retries_once_on_transient_400(monkeypatch):
    from app.collectors.tikhub_modes import LinkedInJobsCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tikhub_api_key", "offline-fixture")
    attempts = []

    async def flaky_get(url, **kwargs):
        attempts.append(url)
        if len(attempts) == 1:
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError("400", request=request, response=httpx.Response(400, request=request))
        return load("linkedin_search_jobs.json")

    monkeypatch.setattr(fetcher, "get_json", flaky_get)
    items = await LinkedInJobsCollector().search_configured("video editor", {})
    assert len(attempts) == 2 and len(items) == 6


@pytest.mark.asyncio
async def test_toutiao_imports_links_and_requires_them(monkeypatch):
    from app.collectors.tikhub_modes import ToutiaoLinkCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tikhub_api_key", "offline-fixture")
    calls: list[str] = []

    async def fake_get(url, **kwargs):
        assert kwargs.get("billable_provider") == "tikhub"
        calls.append(url)
        return load("toutiao_article.json")

    monkeypatch.setattr(fetcher, "get_json", fake_get)
    link = "https://www.toutiao.com/article/7450114952884503059/"
    items = await ToutiaoLinkCollector().search_configured("视频制作", {"toutiao_links": link})
    assert len(calls) == 1
    assert parse_qs(urlparse(calls[0]).query) == {"aweme_id": ["7450114952884503059"]}
    assert len(items) == 1
    item = items[0]
    assert item.title == "“海阳船”再发“海阳箭”——谷神星一号海遥四运载火箭发射成功"
    assert item.author == "闪电新闻"
    assert item.url == link
    assert item.published_at == datetime(2024, 12, 19, 13, 31, 15, tzinfo=UTC)
    assert "齐鲁网" in item.content
    assert "按链接导入" in item.metadata["mode_note"]

    with pytest.raises(AppError) as error:
        await ToutiaoLinkCollector().search_configured("视频制作", {})
    assert error.value.code == "TOUTIAO_LINKS_REQUIRED"


@pytest.mark.asyncio
async def test_wechat_video_search_builds_share_links_via_detail(monkeypatch):
    from app.collectors.tikhub_catalog_adapter import CatalogCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tikhub_api_key", "offline-fixture")
    calls: list[str] = []

    async def fake_post(url, payload, **kwargs):
        assert kwargs.get("billable_provider") == "tikhub"
        calls.append(url)
        if url.endswith("/fetch_search"):
            return load("wechat_video_search.json")
        if url.endswith("/fetch_video_detail"):
            assert payload["export_id"].startswith("export/")
            return load("wechat_video_detail.json")
        if url.endswith("/fetch_video_share_url"):
            assert payload["object_id"].isdigit()
            return load("wechat_share_url.json")
        raise AssertionError(url)

    monkeypatch.setattr(fetcher, "post_json", fake_post)
    items = await CatalogCollector("wechat_search").search_configured(
        "求视频制作", {"wechat_business_type": "video", "wechat_share_links": "2"})
    assert len(calls) == 5  # 1 search + 2 calls per top-2 item
    assert len(items) == 2
    assert all(item.url == "https://weixin.qq.com/sph/A6BpEUvSmC" for item in items)
    assert items[0].metadata["share_url_verified"] is True
    assert items[0].metadata["share_chain"] == "export_id->detail.id->share_url"
    assert items[0].metadata["extra_provider_calls"] == 2


@pytest.mark.asyncio
async def test_wechat_video_without_share_url_never_fabricates_a_link(monkeypatch):
    from app.collectors.tikhub_catalog_adapter import CatalogCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "tikhub_api_key", "offline-fixture")

    async def fake_post(url, payload, **kwargs):
        if url.endswith("/fetch_search"):
            return load("wechat_video_search.json")
        if url.endswith("/fetch_video_detail"):
            return load("wechat_video_detail.json")
        return {"code": 200, "data": {"object_id": payload.get("object_id"), "share_url": None, "debug_id": "x"}}

    monkeypatch.setattr(fetcher, "post_json", fake_post)
    with pytest.raises(AppError) as error:
        await CatalogCollector("wechat_search").search_configured(
            "求视频制作", {"wechat_business_type": "video", "wechat_share_links": "1"})
    assert error.value.code == "WECHAT_SHARE_URL_UNAVAILABLE"
    assert "不展示假链接" in error.value.message


def test_wechat_share_count_is_bounded():
    from app.collectors.tikhub_modes import parse_wechat_share_count

    assert parse_wechat_share_count(None) == 1
    assert parse_wechat_share_count("3") == 3
    with pytest.raises(AppError) as error:
        parse_wechat_share_count("4")
    assert error.value.code == "WECHAT_SHARE_COUNT_INVALID"


def test_provider_plan_counts_every_paid_call():
    from app.services.provider_plan import planned_provider_calls

    assert planned_provider_calls("wechat_search", {"wechat_business_type": "video", "wechat_share_links": "3"}) == 7
    assert planned_provider_calls("wechat_search", {"wechat_business_type": "article"}) == 1
    assert planned_provider_calls("telegram", {"telegram_channels": "@alpha,@beta"}) == 2
    assert planned_provider_calls("toutiao", {"toutiao_links": "https://www.toutiao.com/article/1/"}) == 1
    assert planned_provider_calls("linkedin", {}) == 1
    assert planned_provider_calls("reddit", {}) == 1


def test_hiring_signal_is_not_assessed_as_buyer():
    from app.collectors.tikhub_modes import parse_linkedin_jobs
    from app.services.hunt_conditions import assess_hiring_signal

    item = parse_linkedin_jobs(load("linkedin_search_jobs.json"), "video editor")[0]
    assessment = assess_hiring_signal(item)
    assert assessment["status"] == "hiring_signal"
    assert assessment["evidence"]["公司"] == "Toplinestudios"
    assert assessment["evidence"]["职位"] == "Freelance Video Editor"
    assert "不是买方直接需求" in " ".join(assessment["missing"])
    assert "买方采购原文" not in " ".join(assessment["evidence"].values())


def test_hiring_signal_survives_buyer_business_terms_but_excluded_terms_still_apply():
    from datetime import timedelta
    from app.collectors.tikhub_modes import parse_linkedin_jobs
    from app.schemas.collection import CollectionPolicy
    from app.services.collection_filter import filter_page

    item = parse_linkedin_jobs(load("linkedin_search_jobs.json"), "video editor")[0]
    assert item.published_at is not None
    policy = CollectionPolicy(required_terms=["电商", "广告"], excluded_terms=[], match_mode="all",
                              time_basis="published", include_unknown_dates=False, sort="latest",
                              activity_filter="any", min_interactions=0)
    kept, counts = filter_page([item], policy, freshness_hours=168, now=item.published_at + timedelta(hours=1))
    assert kept == [item] and counts["terms"] == 0
    policy.excluded_terms = ["Video Editor"]
    kept, counts = filter_page([item], policy, freshness_hours=168, now=item.published_at + timedelta(hours=1))
    assert kept == [] and counts["terms"] == 1


def test_new_sources_are_accepted_by_radar_schema_and_price_path():
    from app.services.price_evidence import tikhub_endpoint

    assert RadarCreate(name="Contract test", goal="Find real client work", sources=["telegram", "linkedin", "toutiao"]).sources
    assert tikhub_endpoint("telegram") == "/api/v1/telegram/web/fetch_channel_search"
    assert tikhub_endpoint("linkedin") == "/api/v1/linkedin/web_v2/search_jobs"
    assert tikhub_endpoint("toutiao") == "/api/v1/toutiao/web/get_article_info"
