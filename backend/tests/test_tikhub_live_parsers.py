"""Real-response contract tests for every live-verified TikHub search platform.

Fixtures are trimmed from the paid verification calls on 2026-10-16 (see
backend/app/collectors/tikhub-live-verification.json for endpoints and request
ids). They are not live calls; they lock the field mapping the parsers must
keep. Unknown publish dates must stay unknown and be dropped by filters.
"""
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

FIXTURES = Path(__file__).parent / 'fixtures' / 'tikhub_live'
NOW = datetime(2026, 10, 17, 1, 0, tzinfo=UTC)


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def fresh_items(items):
    from app.schemas.collection import CollectionPolicy
    from app.services.collection_filter import filter_page
    accepted, counts = filter_page(items, CollectionPolicy(time_basis='published', include_unknown_dates=False), freshness_hours=168, now=NOW)
    return accepted, counts


# ---------------------------------------------------------------- bilibili
def test_bilibili_search_maps_video_fields():
    from app.collectors.tikhub_catalog_adapter import parse_bilibili
    items = parse_bilibili(fixture('bilibili_search.json'), '视频制作')
    assert len(items) == 3
    first = items[0]
    assert first.external_id == 'BV1PLJ86VERM'
    assert first.title.startswith('flux3 klein')
    assert first.url == 'https://www.bilibili.com/video/av117451668848937'
    assert first.author == '积木comfyui'
    assert first.published_at == datetime.fromtimestamp(1792170329, tz=UTC)
    assert first.engagement == {'likes': 0, 'comments': 0, 'collects': 1, 'views': 13, 'danmaku': 0}
    assert first.metadata['content_kind'] == 'video'
    assert first.source == 'bilibili'
    accepted, counts = fresh_items(items)
    assert len(accepted) == 3 and counts['unknown_date'] == 0


def test_bilibili_time_window_args(monkeypatch):
    import asyncio
    from app.collectors.tikhub_catalog_adapter import CatalogCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), 'tikhub_api_key', 'test-not-a-secret')
    calls = []

    async def fake_get(url, **kwargs):
        calls.append(url)
        return {'code': 200, 'data': {'data': {'result': []}}}

    monkeypatch.setattr(fetcher, 'get_json', fake_get)
    items = asyncio.run(CatalogCollector('bilibili').search_configured('视频制作', {'freshness_hours': '168'}))
    assert items == []
    query = parse_qs(urlparse(calls[0]).query)
    assert query['keyword'] == ['视频制作'] and query['order'] == ['pubdate'] and query['page'] == ['1']
    begin, end = int(query['pubtime_begin_s'][0]), int(query['pubtime_end_s'][0])
    assert end - begin == 168 * 3600 and end <= int(datetime.now(UTC).timestamp())


# ---------------------------------------------------------------- kuaishou
def test_kuaishou_search_maps_feed_fields():
    from app.collectors.tikhub_catalog_adapter import parse_kuaishou
    items = parse_kuaishou(fixture('kuaishou_search.json'), '视频制作')
    assert len(items) == 3
    first = items[0]
    assert first.external_id == '5215168567722067033'
    assert first.author == '布布爱剪辑'
    assert first.title.startswith('“人物定格回忆录”的教程')
    assert first.published_at == datetime.fromtimestamp(1780503363192 // 1000, tz=UTC)  # ms timestamp, second precision
    assert first.engagement == {'likes': 63251, 'views': 1380962, 'comments': 3482, 'shares': 19039}
    # share_info photoId is the canonical public short-video id
    assert first.url == 'https://www.kuaishou.com/short-video/3xzpgzu7hnnb9iy'
    assert first.metadata['content_kind'] == 'video'


# ---------------------------------------------------------------- lemon8
def test_lemon8_scans_frames_for_items():
    from app.collectors.tikhub_catalog_adapter import parse_lemon8
    items = parse_lemon8(fixture('lemon8_search.json'), 'video editing')
    assert len(items) == 3
    first = items[0]
    assert first.external_id == '7458665034407871019'
    assert first.author == 'MALARIALEXIS'
    assert first.published_at == datetime.fromtimestamp(1736605814, tz=UTC)
    assert first.url.startswith('https://www.lemon8-app.com/@malarialexis/7458665034407871019')
    assert first.engagement['likes'] == 3337


def test_lemon8_empty_frames_are_not_errors():
    from app.collectors.tikhub_catalog_adapter import parse_lemon8
    assert parse_lemon8({'code': 200, 'data': [{'message': 'success', 'data': None, 'code': 0}, 62, {'ack': -1}]}, 'q') == []


# ---------------------------------------------------------------- pipixia
def test_pipixia_search_maps_cells():
    from app.collectors.tikhub_catalog_adapter import parse_pipixia
    items = parse_pipixia(fixture('pipixia_search.json'), '视频制作')
    assert len(items) == 3
    first = items[0]
    assert first.external_id == '7690783384380905771'
    assert first.published_at == datetime.fromtimestamp(1790650045, tz=UTC)
    assert first.author == '麻雀捉螳螂'
    assert first.url.startswith('https://h5.pipix.com/ppx/item/7690783384380905771')
    assert first.engagement == {'likes': 0, 'comments': 0, 'shares': 0, 'views': 359, 'collects': 0, 'plays': 114}


# ---------------------------------------------------------------- threads
def test_threads_search_maps_nested_thread_items():
    from app.collectors.tikhub_catalog_adapter import parse_threads
    items = parse_threads(fixture('threads_search.json'), 'video editing')
    assert len(items) == 3
    first = items[0]
    assert first.external_id == '4009256930203649015'
    assert first.title.startswith('I’m looking for a video editor')
    assert first.url == 'https://www.threads.com/@kartik.does/post/Dejve-iD8P3'
    assert first.author == 'kartik.does'
    assert first.published_at == datetime.fromtimestamp(1792160692, tz=UTC)


# ---------------------------------------------------------------- twitter
def test_twitter_search_maps_timeline_tweets():
    from app.collectors.tikhub_catalog_adapter import parse_twitter
    items = parse_twitter(fixture('twitter_search.json'), 'video editing')
    assert len(items) == 3
    first = items[0]
    assert first.external_id == '2109763754971857009'
    assert first.url == 'https://x.com/HurricaneCrypt0/status/2109763754971857009'
    assert first.published_at == datetime(2026, 10, 12, 21, 50, 51, tzinfo=UTC)
    assert first.engagement == {'likes': 120, 'comments': 8, 'shares': 28, 'views': 6399}


# ---------------------------------------------------------------- youtube
def test_youtube_relative_time_is_conservative_and_unknown_is_none():
    from app.collectors.tikhub_catalog_adapter import parse_youtube
    items = parse_youtube(fixture('youtube_search.json'), 'video editing', now=NOW)
    assert len(items) == 3
    first = items[0]
    assert first.external_id == 'lkz8huDV-iU'
    # "5 hours ago" upper bound: never pretend the content is newer than it can be
    assert first.published_at == NOW - timedelta(hours=6)
    assert first.engagement['views'] == 3803
    assert first.metadata['date_status'] == 'provider_relative_upper_bound'
    # "4 years ago" / "1 year ago" stay far outside a 168h window
    accepted, counts = fresh_items(items)
    assert [item.external_id for item in accepted] == ['lkz8huDV-iU'] and counts['stale'] == 2


def test_youtube_missing_relative_time_stays_unknown_and_filtered():
    from app.collectors.tikhub_catalog_adapter import parse_youtube
    items = parse_youtube(fixture('youtube_missing_date.json'), 'video editing', now=NOW)
    assert items[0].published_at is None
    accepted, counts = fresh_items(items)
    assert accepted == [] and counts['unknown_date'] == 1


def test_youtube_upload_date_tiers(monkeypatch):
    import asyncio
    from app.collectors.tikhub_catalog_adapter import CatalogCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), 'tikhub_api_key', 'test-not-a-secret')
    calls = []

    async def fake_get(url, **kwargs):
        calls.append(parse_qs(urlparse(url).query))
        return {'code': 200, 'data': {'videos': []}}

    monkeypatch.setattr(fetcher, 'get_json', fake_get)
    for hours, expected in ((1, 'last_hour'), (24, 'today'), (168, 'this_week'), (720, 'this_month'), (8760, 'this_year')):
        asyncio.run(CatalogCollector('youtube').search_configured('video editing', {'freshness_hours': str(hours)}))
        assert calls[-1]['upload_date'] == [expected]
        assert calls[-1]['type'] == ['video']
    asyncio.run(CatalogCollector('youtube').search_configured('video editing', {'freshness_hours': '90000'}))
    assert 'upload_date' not in calls[-1]


# ---------------------------------------------------------------- wechat_search
def test_wechat_search_maps_article_items_and_strips_highlights():
    from app.collectors.tikhub_catalog_adapter import parse_wechat_search
    items = parse_wechat_search(fixture('wechat_search.json'), '视频制作')
    assert len(items) == 3
    first = items[0]
    assert first.external_id == '9942943906819879871'
    assert '<em' not in first.title and '<em' not in first.content
    assert first.author == '呆头鹅Ai矩阵获客系统'
    assert first.published_at == datetime.fromtimestamp(1792170582, tz=UTC)
    assert first.url.startswith('http://mp.weixin.qq.com/s?')
    assert first.engagement == {}


def test_wechat_search_missing_timestamp_stays_unknown_and_filtered():
    from app.collectors.tikhub_catalog_adapter import parse_wechat_search
    items = parse_wechat_search(fixture('wechat_search_missing_date.json'), '视频制作')
    assert items[0].published_at is None and items[0].author is None
    accepted, counts = fresh_items(items)
    assert accepted == [] and counts['unknown_date'] == 1


def test_wechat_search_posts_article_scope_with_native_week_dial(monkeypatch):
    import asyncio
    from app.collectors.tikhub_catalog_adapter import CatalogCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), 'tikhub_api_key', 'test-not-a-secret')
    calls = []

    async def fake_post(url, payload, **kwargs):
        calls.append((urlparse(url).path, payload, kwargs.get('billable_source')))
        return {'code': 200, 'data': {'results': {'data': [{'items': []}]}}}

    monkeypatch.setattr(fetcher, 'post_json', fake_post)
    assert asyncio.run(CatalogCollector('wechat_search').search_configured('视频制作', {'freshness_hours': '168'})) == []
    path, body, source = calls[0]
    assert path == '/api/v1/wechat_search/v2/fetch_search' and source == 'wechat_search'
    assert body == {'keyword': '视频制作', 'business_type': 'article', 'sort': 'latest', 'publish_time': 'week', 'offset': 0}


def test_wechat_search_scope_selector_changes_business_type(monkeypatch):
    import asyncio
    from app.collectors.tikhub_catalog_adapter import CatalogCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings
    from app.core.errors import AppError
    monkeypatch.setattr(get_settings(), 'tikhub_api_key', 'test-not-a-secret')
    bodies = []

    async def fake_post(url, payload, **kwargs):
        bodies.append(payload)
        return {'code': 200, 'data': {'business_type': payload['business_type'], 'results': {'data': []}}}

    monkeypatch.setattr(fetcher, 'post_json', fake_post)
    for scope in ('article', 'video', 'all'):
        asyncio.run(CatalogCollector('wechat_search').search_configured('求视频制作', {'freshness_hours': '24', 'wechat_business_type': scope}))
        assert bodies[-1]['business_type'] == scope
        assert bodies[-1]['publish_time'] == 'day'
    with pytest.raises(AppError) as caught:
        asyncio.run(CatalogCollector('wechat_search').search_configured('求视频制作', {'wechat_business_type': 'account'}))
    assert caught.value.status_code == 400
    assert 'wechat_business_type' in caught.value.message
    assert caught.value.code == 'INVALID_WECHAT_SCOPE'
    assert len(bodies) == 3  # invalid scope never reaches the paid provider


def test_wechat_search_video_scope_rows_have_no_original_link():
    from app.collectors.tikhub_catalog_adapter import parse_wechat_search, wechat_search_rows
    payload = fixture('wechat_search_video.json')
    rows = wechat_search_rows(payload)
    assert len(rows) == 10
    assert all(kind == 'video' for _, kind in rows)
    first, _ = rows[0]
    assert first['docID'] and first['pubTime'] and first['source']['title'] and first['duration']
    assert not any(row.get('doc_url') or row.get('url') or row.get('share_url') for row, _ in rows)
    assert parse_wechat_search(payload, '求视频制作', 'video') == []  # no link => no verifiable evidence
    assert parse_wechat_search(fixture('wechat_search.json'), '找人做视频', 'article')[0].metadata['content_kind'] == 'article'


# ---------------------------------------------------------------- reddit (updated mapping)
def test_reddit_live_fields_replace_the_old_title_only_mapping():
    from app.collectors.tikhub_catalog_adapter import parse_reddit
    items = parse_reddit(fixture('reddit_search.json'), 'video editing')
    assert len(items) == 3
    first = items[0]
    assert first.external_id == 't3_1x7m2ee'
    assert first.title.startswith('I Tried Beating Zero Company')
    assert first.published_at == datetime.fromisoformat('2026-10-16T17:14:28.093000+00:00')
    assert first.url.startswith('https://www.reddit.com/r/')
    assert first.author == 'Numbuh_17'
    assert first.engagement == {'likes': 2, 'comments': 0}
    assert first.metadata['date_status'] == 'native_created_at'


# ---------------------------------------------------------------- douyin v3 (tikhub_cn)
def test_douyin_v3_maps_flat_items_and_beijing_time():
    from app.collectors.tikhub_cn import parse_douyin
    items = parse_douyin(fixture('douyin_v3_search.json'), '视频制作')
    assert len(items) == 3
    first = items[0]
    assert first.external_id == '7696095129496752467'
    assert first.url == 'https://www.douyin.com/video/7696095129496752467'
    # createTime strings are Beijing time; epoch cross-check: 1791886783 == 2026-10-13T10:19:43Z
    assert first.published_at == datetime(2026, 10, 13, 10, 19, 43, tzinfo=UTC)
    assert first.author == '四川腊肉香肠野生笋茶叶各类土特产'
    assert first.engagement == {'likes': 8217, 'fans': 16567}
    assert first.metadata['date_status'] == 'provider_string_asia_shanghai'


def test_douyin_v3_date_type_mapping_and_no_pagination(monkeypatch):
    import asyncio
    from app.collectors import tikhub_cn
    from app.core.config import get_settings
    calls = []

    async def fake_post(url, payload, **kwargs):
        calls.append((urlparse(url).path, payload, kwargs.get('billable_source')))
        return {'code': 200, 'data': {'data': []}}

    monkeypatch.setattr(get_settings(), 'tikhub_api_key', 'test-not-a-secret')
    monkeypatch.setattr(tikhub_cn.fetcher, 'post_json', fake_post)
    for hours, expected in ((24, '3'), (72, '3'), (168, '7'), (720, '30'), (8760, '0')):
        asyncio.run(tikhub_cn.DouyinCollector().search_configured('视频制作', {'freshness_hours': str(hours)}))
        path, body, source = calls[-1]
        assert path == '/api/v1/douyin/search/fetch_video_search_v3'
        assert body == {'query': '视频制作', 'date_type': expected, 'label_type': 0, 'duration_type': 0}
        assert source == 'douyin'
    with pytest.raises(ValueError):
        asyncio.run(tikhub_cn.DouyinCollector().search_page('视频制作', '20'))


def test_douyin_v3_missing_date_is_unknown_not_fresh():
    from app.collectors.tikhub_cn import parse_douyin
    items = parse_douyin(fixture('douyin_v3_missing_date.json'), '视频制作')
    assert items[0].published_at is None
    accepted, counts = fresh_items(items)
    assert accepted == [] and counts['unknown_date'] == 1


def test_douyin_v3_caps_first_screen_and_records_provider_total():
    from app.collectors.tikhub_cn import parse_douyin
    rows = [{"itemId": str(7690000000000000000 + i), "title": f"第{i}条视频制作需求", "createTime": "2026-10-13 18:19:43"} for i in range(60)]
    items = parse_douyin({"data": {"data": rows}}, "视频制作")
    assert len(items) == 50  # 单次 1000 条整批结果只取平台排序首屏
    assert items[0].metadata['provider_total_items'] == 60


# ---------------------------------------------------------------- weibo / zhihu / tiktok live checks
def test_weibo_live_fixture_keeps_relative_time_approximation():
    from app.collectors.tikhub_cn import parse_weibo
    items = parse_weibo(fixture('weibo_search.json'), '视频制作', now=NOW)
    assert len(items) == 3
    assert items[0].external_id == '5354811530150538'
    assert items[0].url == 'https://weibo.com/6242834432/RmZTH0Da2'
    assert items[0].published_at == NOW - timedelta(minutes=15)  # provider-stated age "15分钟前"


def test_zhihu_live_fixture_maps_article_and_answer():
    from app.collectors.tikhub_cn import parse_zhihu
    items = parse_zhihu(fixture('zhihu_search.json'), '视频制作')
    kinds = {item.metadata['content_kind'] for item in items}
    assert kinds == {'article', 'answer'}
    article = next(item for item in items if item.metadata['content_kind'] == 'article')
    assert article.url == 'https://zhuanlan.zhihu.com/p/2094519486510585204'
    assert article.published_at == datetime.fromtimestamp(1792152399, tz=UTC)
    answer = next(item for item in items if item.metadata['content_kind'] == 'answer')
    assert answer.url.startswith('https://www.zhihu.com/question/')


def test_tiktok_live_fixture_maps_item_and_stats():
    from app.collectors.tikhub import TikHubCollector, parse_tiktok_search
    items = parse_tiktok_search(fixture('tiktok_search.json'), 'video editing')
    assert len(items) == 3
    first = items[0]
    assert first.external_id == '7657590655010508054'
    assert first.platform == 'tiktok' and first.author == 'hoor_edits9'
    assert first.engagement['likes'] == 365000 and first.engagement['plays'] == 5600000
    assert TikHubCollector.path == '/api/v1/tiktok/web/fetch_general_search'


# ---------------------------------------------------------------- ledger consistency
def test_live_verification_ledger_matches_fixtures_and_catalog():
    from app.collectors import tikhub_catalog
    ledger = json.loads((Path(tikhub_catalog.__file__).with_name('tikhub-live-verification.json')).read_text())
    mode_ledger = json.loads((Path(tikhub_catalog.__file__).with_name('tikhub-mode-verification.json')).read_text())
    verified = set()
    repo_root = Path(__file__).parents[2]
    for slug, entry in ledger['platforms'].items():
        if entry['status'] == 'verified':
            verified.add(slug)
            assert entry['request_id'], slug
            if entry.get('fixture'):
                assert (repo_root / entry['fixture']).exists()
        else:
            assert entry['status'] == 'not_applicable' and entry['reason'] and entry['attempts']
    for slug, entry in mode_ledger['platforms'].items():
        request_id = entry.get('request_id') or entry.get('share_request_id') or entry.get('search_request_id')
        assert entry['status'] == 'verified' and request_id, slug
        verified.add(slug)
    assert verified == set(tikhub_catalog.LIVE_VERIFIED)
    assert set(tikhub_catalog.NOT_APPLICABLE) == {slug for slug, entry in ledger['platforms'].items() if entry['status'] == 'not_applicable'}
    for slug in tikhub_catalog.INTEGRATED:
        assert slug in verified, slug
