"""Offline catalog/contract tests; never a paid-provider integration test."""
import pytest


def test_catalog_covers_real_namespaces_once_and_separates_readiness():
    from app.collectors.tikhub_catalog import LIVE_VERIFIED, NOT_APPLICABLE, PLATFORMS, source_catalog
    expected = {'bilibili', 'douyin', 'instagram', 'kuaishou', 'lemon8', 'linkedin', 'pipixia', 'reddit', 'telegram', 'threads', 'tiktok', 'toutiao', 'twitter', 'wechat_channels', 'wechat_mp', 'wechat_search', 'weibo', 'xiaohongshu', 'xigua', 'youtube', 'zhihu'}
    assert {p['namespace'] for p in PLATFORMS} == expected
    assert len(PLATFORMS) == len(expected)
    assert {'instagram', 'xigua'} == set(NOT_APPLICABLE)  # proven unusable in real attempts, reason recorded
    assert 'xigua' not in LIVE_VERIFIED and 'instagram' not in LIVE_VERIFIED
    from types import SimpleNamespace
    settings = SimpleNamespace(tikhub_api_key='', firecrawl_api_key='', app_env='local', paid_api_enabled=False)
    items = source_catalog(settings)
    assert len({p['id'] for p in items}) == len(items) == 25
    paid = [p for p in items if p['provider'] == 'tikhub']
    assert len(paid) == 21
    assert not any(p['available'] for p in paid)
    assert all(p['status'] == '未配置' for p in paid if p['selectable'])
    assert {p['id']: p['status'] for p in paid if p['id'] in {'wechat_mp', 'wechat_channels'}} == {
        'wechat_mp': '已覆盖 · 搜一搜垂类', 'wechat_channels': '可用 · 搜一搜视频 + 分享链'}
    assert {p['id'] for p in paid if p['selectable']} >= {'telegram', 'linkedin', 'toutiao'}
    assert next(p for p in paid if p['id'] == 'telegram')['mode'] == 'channel_search'
    assert next(p for p in paid if p['id'] == 'linkedin')['mode'] == 'hiring_signal'
    assert next(p for p in paid if p['id'] == 'toutiao')['mode'] == 'link_import'
    assert all(p['status'] == '不适用' for p in paid if p['id'] in NOT_APPLICABLE)
    assert all('api_capabilities' in p and 'implemented_capabilities' in p for p in paid)
    settings.tikhub_api_key = 'test-only'
    assert not any(p['available'] for p in source_catalog(settings) if p['provider'] == 'tikhub')
    assert all('付费关闭' in p['status'] for p in source_catalog(settings) if p['provider'] == 'tikhub' and p['selectable'])


def test_limited_mode_platforms_carry_real_evidence_and_scope():
    from app.collectors.tikhub_catalog import MODE_VERIFICATION, PENDING_REASONS, SPECIAL_MODES
    assert PENDING_REASONS == {}  # 三个平台已按受限模式接入，不再列待接入
    assert set(SPECIAL_MODES) == {'toutiao', 'telegram', 'linkedin'}
    for slug in ('toutiao', 'telegram', 'linkedin'):
        entry = MODE_VERIFICATION['platforms'][slug]
        assert entry['status'] == 'verified' and entry['request_id']
        assert SPECIAL_MODES[slug]['mode'] == entry['mode']
        assert '不是' in SPECIAL_MODES[slug]['limits'] or '只支持' in SPECIAL_MODES[slug]['limits'] or '只搜' in SPECIAL_MODES[slug]['limits']


def test_wechat_mp_and_channels_are_covered_by_search_verticals():
    from types import SimpleNamespace
    from app.collectors.tikhub_catalog import COVERED_BY_SEARCH, source_catalog
    assert set(COVERED_BY_SEARCH) == {'wechat_mp', 'wechat_channels'}
    settings = SimpleNamespace(tikhub_api_key='test-only', firecrawl_api_key='', app_env='local',
                               paid_api_enabled=True, local_manual_tikhub_enabled=True)
    items = {item['id']: item for item in source_catalog(settings)}
    expected = {'wechat_mp': ('article', '已覆盖 · 搜一搜垂类'), 'wechat_channels': ('video', '可用 · 搜一搜视频 + 分享链')}
    for slug, (vertical, status) in expected.items():
        item = items[slug]
        assert item['status'] == status
        assert item['covered_by'] == 'wechat_search' and item['vertical'] == vertical
        assert item['selectable'] is False
        assert item['covered_request_id'] and item['detail'].find(item['covered_request_id']) >= 0
    assert '分享链' in items['wechat_channels']['detail']
    assert items['wechat_channels']['share_link']['verified'] is True
    assert items['wechat_channels']['share_link']['share_url'] == 'https://weixin.qq.com/sph/A6BpEUvSmC'


def test_wechat_search_exposes_real_verticals_and_native_time_dial():
    from types import SimpleNamespace
    from app.collectors.tikhub_catalog import source_catalog
    settings = SimpleNamespace(tikhub_api_key='test-only', firecrawl_api_key='', app_env='local',
                               paid_api_enabled=True, local_manual_tikhub_enabled=True)
    item = {item['id']: item for item in source_catalog(settings)}['wechat_search']
    assert [v['id'] for v in item['verticals']] == ['all', 'article', 'video']
    states = {v['id']: v for v in item['verticals']}
    assert states['article']['verified'] is True and states['article']['total'] == 35
    assert states['video']['status'] == 'verified' and states['video']['verified'] is True
    assert states['video']['request_id'] == '39e3aaec-3344-4114-95e4-bef1647fb045'
    assert states['video']['share_request_id'] == '5504d38b-26a3-4778-8415-2ae62ff8f120'
    assert states['video']['share_url'] == 'https://weixin.qq.com/sph/A6BpEUvSmC'
    assert item['modes'][1]['id'] == 'video_share_link' and item['modes'][1]['extra_calls_per_item'] == 2
    assert item['share_link']['verified'] is True
    assert item['native_time_filter']['verified'] is True
    assert item['supports_scope_selector'] is True
    assert '原生' in item['time_policy'] and 'half_year' in item['time_policy']


def test_verified_platforms_show_live_verified_when_priced_and_enabled(monkeypatch):
    from types import SimpleNamespace
    from app.collectors.tikhub_catalog import LIVE_VERIFIED, source_catalog
    settings = SimpleNamespace(tikhub_api_key='test-only', firecrawl_api_key='', app_env='local',
                               paid_api_enabled=True, local_manual_tikhub_enabled=True)
    monkeypatch.setattr('app.services.price_evidence.verified_tikhub_price', lambda endpoint: (0.01, {'source_url': 'https://api.tikhub.io/x'}))
    items = {item['id']: item for item in source_catalog(settings)}
    for slug in LIVE_VERIFIED - {'wechat_channels'}:
        assert items[slug]['status'] == '可运行 · 已实测', slug
        assert items[slug]['live_verified'] is True
    assert items['wechat_channels']['status'] == '可用 · 搜一搜视频 + 分享链'
    assert items['instagram']['status'] == '不适用' and items['instagram']['live_verified'] is False
    assert items['toutiao']['status'] == '可运行 · 已实测'
    assert items['toutiao']['request_id'] == '4866abbb-6eba-4276-93f5-16154f4dd00d'


@pytest.mark.parametrize('namespace', ['bilibili', 'douyin', 'instagram', 'kuaishou', 'lemon8', 'linkedin', 'pipixia', 'reddit', 'telegram', 'threads', 'tiktok', 'toutiao', 'twitter', 'wechat_channels', 'wechat_mp', 'wechat_search', 'weibo', 'xiaohongshu', 'xigua', 'youtube', 'zhihu'])
def test_each_platform_endpoint_and_integration_contract(namespace):
    from app.collectors.tikhub_catalog import PLATFORMS, NOT_APPLICABLE, INTEGRATED, MODE_VERIFICATION
    from app.collectors.registry import registry
    platform = next(p for p in PLATFORMS if p['namespace'] == namespace)
    adapter = registry.get(platform['id'])
    if platform['id'] not in INTEGRATED:
        assert adapter is None  # No invented parser or misleading runnable placeholder.
        return
    assert adapter is not None
    if platform['id'] != 'toutiao':
        assert not adapter.capabilities().detail and not adapter.capabilities().comments
    else:
        assert adapter.capabilities().detail is True  # 按链接导入走详情端点
    expected_path = MODE_VERIFICATION['platforms'][platform['id']]['endpoint'] if platform['id'] in MODE_VERIFICATION['platforms'] else platform['search_endpoint']
    assert adapter.path == expected_path
    operation = next(op for op in platform['operations'] if op['path'] == adapter.path)
    method = getattr(adapter, 'method', getattr(getattr(adapter, 'contract', None), 'method', 'GET'))
    assert operation['method'] == method
    if platform['id'] == 'toutiao':
        return  # 详情端点参数在官方 OpenAPI 的 query 中已由 test_tikhub_modes 覆盖
    if hasattr(adapter, 'request_args'):
        args = adapter.request_args('contract-query')
    elif platform['id'] == 'tikhub':
        args = {'keyword': 'contract-query', 'offset': 0}
    else:
        contract = adapter.contract
        args = {**dict(contract.constants), contract.query_parameter: 'contract-query'}
    if method == 'POST':
        schema = operation['body_schema']
        assert set(schema.get('required', [])) <= args.keys()
        assert args.keys() <= schema['properties'].keys()
    else:
        parameters = {p['name']: p for p in operation['parameters']}
        assert {k for k, p in parameters.items() if p.get('required')} <= args.keys()
        assert args.keys() <= parameters.keys()


@pytest.mark.asyncio
@pytest.mark.parametrize('hours,expected', [(24,'a_day'), (168,'a_week'), (720,'a_month')])
async def test_zhihu_native_time_mapping(hours, expected, monkeypatch):
    from app.collectors.tikhub_cn import ZhihuCollector
    from app.collectors.http import fetcher
    from app.core.config import get_settings
    from urllib.parse import parse_qs, urlparse
    monkeypatch.setattr(get_settings(), 'tikhub_api_key', 'offline-fixture')
    urls = []
    async def fake(url, **kwargs):
        urls.append(url)
        return {'code':200, 'data': {'data':[]}}
    monkeypatch.setattr(fetcher, 'get_json', fake)
    await ZhihuCollector().search_configured('contract-query', {'freshness_hours':str(hours)})
    assert parse_qs(urlparse(urls[0]).query)['time_interval'] == [expected]


def test_new_sources_pass_schemas_and_price_path_but_unusable_ones_do_not():
    from pydantic import ValidationError
    from app.schemas.domain import RadarCreate
    from pydantic import TypeAdapter
    from app.api.intelligence import EvidenceSource, BILLABLE_SOURCES, _source_status
    from app.services.price_evidence import tikhub_endpoint
    assert RadarCreate(name='Contract test', goal='Find real client work', sources=['reddit', 'youtube', 'wechat_search']).sources == ['reddit', 'youtube', 'wechat_search']
    assert TypeAdapter(EvidenceSource).validate_python('youtube') == 'youtube'
    assert TypeAdapter(EvidenceSource).validate_python('wechat_search') == 'wechat_search'
    assert 'reddit' in BILLABLE_SOURCES and 'youtube' in BILLABLE_SOURCES
    assert tikhub_endpoint('reddit') == '/api/v1/reddit/app/fetch_dynamic_search'
    assert tikhub_endpoint('youtube') == '/api/v1/youtube/web_v2/get_general_search_v2'
    assert tikhub_endpoint('wechat_search') == '/api/v1/wechat_search/v2/fetch_search'
    assert _source_status()['reddit']['estimated_request_cost_usd'] is None  # Not advertised as free.
    with pytest.raises(ValidationError):
        RadarCreate(name='Contract test', goal='Find real client work', sources=['instagram'])
