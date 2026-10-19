"""Synthetic contract fixtures, derived only from official OpenAPI prose.
Not a live provider test; no paid calls. Unspecified fields must stay unknown.
"""
from urllib.parse import parse_qs, urlparse
import pytest
from app.core.config import get_settings


def test_reddit_live_verified_fields_and_unknown_date():
    from app.collectors.tikhub_catalog_adapter import parse_reddit
    items = parse_reddit({'code': 200, 'data': {'children': [
        {'post': {'id': 't3_abc123', 'postTitle': 'Rust borrow checker', 'score': 0, 'createdAt': '2026-10-16T17:14:28.093000+0000'}},
        {'post': {'id': 't3_noname', 'postTitle': 'No timestamp stays unknown', 'score': 1}},
    ], 'pageInfo': {}}}, 'rust')
    assert len(items) == 2
    first = items[0]
    assert first.external_id == 't3_abc123'
    assert first.url == 'https://www.reddit.com/comments/abc123/'
    assert first.published_at is not None and first.published_at.tzinfo is not None
    assert first.source == 'reddit'
    assert first.metadata['validation_status'] == 'live_verified'
    # 未知 createdAt 的条目保持未知，并被时间过滤剔除
    unknown = items[1]
    assert unknown.published_at is None and unknown.metadata['date_status'] == 'unknown'
    from app.services.collection_filter import filter_page
    from app.schemas.collection import CollectionPolicy
    accepted, counts = filter_page(items, CollectionPolicy(time_basis='published', include_unknown_dates=False), freshness_hours=168)
    assert [item.external_id for item in accepted] == ['t3_abc123'] and counts['unknown_date'] == 1


@pytest.mark.parametrize('payload', [{}, {'code': 200, 'data': {}}, {'data': {'children': {}}}, {'data': {'children': [{'post': {'id':'bad/path', 'postTitle':'bad'}}]}}])
def test_reddit_shape_drift_fails_closed(payload):
    from app.collectors.tikhub_catalog_adapter import parse_reddit
    with pytest.raises(Exception):
        parse_reddit(payload, 'rust')


@pytest.mark.asyncio
async def test_reddit_one_billed_request_exact_mapping(monkeypatch):
    from app.collectors.tikhub_catalog_adapter import CatalogCollector
    from app.collectors.http import fetcher
    monkeypatch.setattr(get_settings(), 'tikhub_api_key', 'test-not-a-secret')
    calls = []
    async def fake(url, **kwargs):
        calls.append((url, kwargs))
        return {'code':200, 'data':{'children':[], 'pageInfo':{}}}
    monkeypatch.setattr(fetcher, 'get_json', fake)
    adapter = CatalogCollector('reddit')
    assert await adapter.search_configured('求网站', {'freshness_hours':'720'}) == []
    assert len(calls) == 1
    url, kwargs = calls[0]
    assert urlparse(url).path == '/api/v1/reddit/app/fetch_dynamic_search'
    assert parse_qs(urlparse(url).query) == {'query':['求网站'], 'search_type':['post'], 'sort':['NEW'], 'time_range':['month'], 'need_format':['true'], 'allow_nsfw':['0'], 'safe_search':['strict']}
    assert kwargs['billable_provider'] == 'tikhub'
    assert kwargs['billable_source'] == 'reddit'
    assert adapter.capabilities().search and not adapter.capabilities().detail
    with pytest.raises(Exception):
        await adapter.search_page('rust', 'unverified-cursor')
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_reddit_paid_disabled_blocks_before_any_transport(monkeypatch):
    from app.collectors.tikhub_catalog_adapter import CatalogCollector
    from app.collectors.http import fetcher
    from app.core.errors import AppError
    import httpx
    monkeypatch.setattr(get_settings(), 'tikhub_api_key', 'offline-only')
    monkeypatch.setattr(get_settings(), 'paid_api_enabled', False)
    monkeypatch.setattr('app.collectors.http.validate_public_url', lambda url: 'api.tikhub.io')
    requests = []
    def forbidden(request):
        requests.append(request)
        raise AssertionError('A paid transport must never be reached')
    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        monkeypatch.setattr(fetcher, '_client', client)
        with pytest.raises(AppError) as exc:
            await CatalogCollector('reddit').search('rust')
    assert exc.value.code == 'PAID_API_DISABLED'
    assert requests == []
