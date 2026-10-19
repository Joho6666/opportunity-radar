"""One public-evidence catalog; listed does not mean integrated or authorized.

Live verification evidence lives in tikhub-live-verification.json: a platform is
"已实测" only when a real paid call on 2026-10-16 returned a parseable response
(request id recorded). Instagram and 西瓜视频 were proven unusable in three real
attempts and are marked 不适用 with the reason instead of a placeholder parser.
"""
import json
from pathlib import Path

EVIDENCE = json.loads(Path(__file__).with_name('tikhub-platforms.json').read_text())
VERIFICATION = json.loads(Path(__file__).with_name('tikhub-live-verification.json').read_text())
MODE_VERIFICATION = json.loads(Path(__file__).with_name('tikhub-mode-verification.json').read_text())
PLATFORMS = EVIDENCE['platforms']
INTEGRATED = {'xiaohongshu', 'douyin', 'weibo', 'zhihu', 'tikhub', 'reddit',
              'bilibili', 'kuaishou', 'lemon8', 'pipixia', 'threads', 'twitter', 'youtube', 'wechat_search',
              'telegram', 'linkedin', 'toutiao'}
LIVE_VERIFIED = frozenset(slug for slug, entry in VERIFICATION['platforms'].items() if entry['status'] == 'verified') | \
                frozenset(slug for slug, entry in MODE_VERIFICATION['platforms'].items() if entry['status'] == 'verified')
NOT_APPLICABLE = {slug: entry['reason'] for slug, entry in VERIFICATION['platforms'].items() if entry['status'] == 'not_applicable'}
TIKHUB_SOURCES = frozenset(INTEGRATED)
PENDING_REASONS: dict[str, str] = {}
SPECIAL_MODES = {
    'telegram': {
        'mode': 'channel_search', 'mode_label': '指定频道内搜索',
        'requires': ['telegram_channels'], 'requires_label': '频道用户名（1–3 个）',
        'limits': '只搜指定公开频道，不是全站关键词搜索；每个频道 1 次请求，最多 3 个频道。',
    },
    'linkedin': {
        'mode': 'hiring_signal', 'mode_label': '招聘信号（潜在客户线索）',
        'requires': [], 'requires_label': '',
        'limits': '只搜职位；结果是“在招视频相关岗位”的招聘信号，不是买方直接需求；每次运行只发 1 个职位搜索请求，首屏 25 条。',
    },
    'toutiao': {
        'mode': 'link_import', 'mode_label': '按链接导入',
        'requires': ['toutiao_links'], 'requires_label': '头条文章链接（1–3 条）',
        'limits': '只支持按文章链接导入，不支持关键词搜索；每条链接 1 次请求，最多 3 条。',
    },
}
WECHAT_SHARE = {
    'mode': 'video_share_link', 'mode_label': '视频号搜索 + 分享链',
    'chain': 'exportId → fetch_video_detail.id → fetch_video_share_url',
    'calls_per_item': 2, 'timeout_seconds': 30,
    'limits': '搜索首屏取前 N 条（默认 1，最多 3），每条额外 2 次付费调用（详情 + 分享链），单条约 30 秒；拿不到短链就不生成假链接。',
}
COVERED_BY_SEARCH = {
    'wechat_mp': {'vertical': 'article', 'label': '公众号文章'},
    'wechat_channels': {'vertical': 'video', 'label': '视频号视频'},
}
WECHAT_VERTICAL_LABELS = {'all': '综合', 'article': '公众号文章', 'video': '视频号视频'}
_WECHAT_EVIDENCE = VERIFICATION['platforms'].get('wechat_search', {})
_WECHAT_VERTICAL_EVIDENCE = _WECHAT_EVIDENCE.get('verticals', {})


def _vertical_state(scope):
    if scope == 'all':
        # 平台端点有真实调用 ≠ 综合垂类已实测：历史请求的 business_type 是 article。
        entry = _WECHAT_EVIDENCE if _WECHAT_EVIDENCE.get('all_scope_verified') else {}
    else:
        entry = _WECHAT_VERTICAL_EVIDENCE.get(scope, {})
    status = entry.get('status') or ('verified' if entry.get('request_id') else 'untested')
    return {'status': status, 'verified': status == 'verified', 'request_id': entry.get('request_id'),
            'verified_at': entry.get('verified_at'), 'total': entry.get('total'), 'parsed': entry.get('parsed'),
            'rows': entry.get('rows'), 'keyword': entry.get('keyword'), 'fields': entry.get('fields'), 'reason': entry.get('reason'),
            'share_url': entry.get('share_url'), 'detail_request_id': entry.get('detail_request_id'),
            'share_request_id': entry.get('share_request_id')}


WECHAT_VERTICALS = [{'id': scope, 'label': label, **_vertical_state(scope)}
                    for scope, label in WECHAT_VERTICAL_LABELS.items()]
TIME_POLICY = {
    'xiaohongshu': '原生一天/一周/半年；30天取半年首屏后按发布时间本地过滤。',
    'douyin': '原生近3天/近7天/近一月（date_type）；再按发布时间本地精确过滤。',
    'weibo': '实时搜索无原生时间档；中文相对时间按发布时点换算后本地过滤。',
    'zhihu': '文章搜索原生一天/一周/一月；再按发布时间本地精确过滤。',
    'tikhub': '综合搜索无原生时间过滤；按 epoch 发布时间本地过滤。',
    'reddit': '原生 day/week/month（time_range）；再按 createdAt 本地精确过滤。',
    'bilibili': '原生发布时间窗口（pubtime_begin_s/pubtime_end_s，秒级时间戳）；再按 pubdate 本地精确过滤。',
    'kuaishou': '无原生时间档；按毫秒 timestamp 本地过滤，未知日期剔除。',
    'lemon8': '无原生时间档；按 publish_time 本地过滤，未知日期剔除。',
    'pipixia': '无原生时间档；按 create_time 本地过滤，未知日期剔除。',
    'threads': '无原生时间档；按 taken_at 本地过滤，未知日期剔除。',
    'twitter': '无原生时间档（Latest 排序非时间档）；按 created_at 本地过滤。',
    'youtube': '原生 last_hour/today/this_week/this_month/this_year（upload_date）；相对时间按桶上限保守换算，未知剔除。',
    'wechat_search': '原生发布时间档 all/day/week/half_year（官方 OpenAPI 定义，按窗口传参）；再按 timestamp 本地精确过滤，未知日期剔除。',
    'telegram': '无原生时间过滤；消息 date 为 ISO 时间，按发布时间本地精确过滤，未知日期剔除。',
    'linkedin': '无原生时间过滤；职位 posted_time 按 UTC 解析后本地过滤，未知日期剔除。',
    'toutiao': '文章正文头部的发布时间戳（秒）解析后本地过滤，未知日期剔除。',
}


def source_catalog(settings):
    items = []
    from ..services.price_evidence import verified_tikhub_price, tikhub_endpoint
    paid_off = not settings.paid_api_enabled or (settings.app_env.lower() == 'local' and not settings.local_manual_tikhub_enabled)
    wechat_quote = verified_tikhub_price(tikhub_endpoint('wechat_search'))
    for platform in PLATFORMS:
        slug = platform['id']
        implemented = slug in INTEGRATED
        covered = COVERED_BY_SEARCH.get(slug)
        configured = bool(settings.tikhub_api_key)
        quote = verified_tikhub_price(tikhub_endpoint(slug)) if implemented else None
        ready = implemented and configured and not paid_off and quote is not None and quote[0] <= 0.1
        verified = slug in LIVE_VERIFIED
        covered_state = _vertical_state(covered['vertical']) if covered else None
        if slug in NOT_APPLICABLE:
            status = '不适用'
            detail = NOT_APPLICABLE[slug]
        elif covered:
            state = covered_state or {}
            request_id = state.get('request_id')
            if state.get('status') == 'fields_incomplete':
                status = '不可用 · 字段缺链接'
                detail = (f"已用微信搜一搜 {covered['vertical']} 垂类真实调用（请求ID：{request_id}，总量 {state.get('total')}，"
                          f"首屏 {state.get('rows')} 条），但返回只有标题/作者/发布时间，没有原文链接，"
                          f"无法形成可核验证据，故标为不可用；不单独接入、不假装接通。")
            elif state.get('verified') and covered['vertical'] == 'video':
                status = '可用 · 搜一搜视频 + 分享链'
                detail = (f"不单独接入：在「微信搜一搜」卡片选择「视频号视频」并设置分享链条数。"
                          f"真实链路：搜索（{state.get('request_id')}）→ 详情（{state.get('detail_request_id')}）"
                          f"→ 分享链（{state.get('share_request_id')}）：{state.get('share_url')}。"
                          f"每条额外 2 次付费调用（详情+分享链，各 USD 0.01），单条约 30 秒；拿不到短链就不展示假链接。")
            elif state.get('verified'):
                status = '已覆盖 · 搜一搜垂类'
                detail = (f"不单独接入：走微信搜一搜 {covered['vertical']} 垂类（business_type={covered['vertical']}），"
                          f"同一 TikHub 端点与单价，在「微信搜一搜」卡片选择「{covered['label']}」。"
                          f"真实调用请求ID：{request_id}；返回总量 {state.get('total')}。")
            else:
                status = '待接入'
                detail = f"搜一搜 {covered['vertical']} 垂类尚无真实响应证据，暂不可用。"
        elif not implemented:
            status = '待接入'
            detail = PENDING_REASONS.get(slug, '官方有关键词搜索，但尚无真实响应证据，待接入。')
        elif not configured:
            status = '未配置'
            detail = '未配置 TikHub 密钥；不发起付费请求。'
        elif paid_off:
            status = '付费关闭'
            detail = '已有真实搜索验证；手动付费调用关闭。'
        elif slug in SPECIAL_MODES and ready and verified:
            entry = MODE_VERIFICATION['platforms'][slug]
            status = '可运行 · 已实测'
            detail = (f"{SPECIAL_MODES[slug]['mode_label']}；真实调用请求ID：{entry.get('request_id')}；"
                      f"单价 USD {quote[0] if quote else 0:g}。{SPECIAL_MODES[slug]['limits']}")
        elif slug in SPECIAL_MODES and not ready:
            status = '已配置 · 价格未核验' if quote is None else '已配置 · 未实测'
            detail = ('已接通受限模式；官方精确单价尚未核验，收费请求保持阻止。' if quote is None
                      else '已有适配器；尚未完成真实付费实测。')
        elif ready and verified:
            status = '可运行 · 已实测'
            detail = '已完成真实搜索验证（含官方计价格与请求ID记录）。'
        else:
            status = '已配置 · 未实测'
            detail = '已有适配器；官方精确价格或真实响应证据不完整，收费请求保持阻止。' if quote is None else '已有适配器；尚未完成真实付费实测。'
        if implemented:
            detail += TIME_POLICY.get(slug, '')
        caps = platform['api_capabilities']
        official = ('关键词搜索' if caps['keyword_search'] else '无关键词内容搜索') + (' / 详情接口' if caps['detail'] else '') + (' / 评论接口' if caps['comments'] else '')
        item = {'id': slug, 'namespace': platform['namespace'], 'name': platform['name'], 'provider': 'tikhub',
                'available': ready,  # Ready for manual authorization, not permission to bypass billing.
                'price_usd': quote[0] if quote else None,
                'configured': configured, 'paid_enabled': not paid_off, 'selectable': implemented,
                'status': status, 'detail': detail + ' 官方能力：' + official + '。应用未接通正文补抓/评论补抓；只取首屏，未知日期不冒充新内容。',
                'api_capabilities': caps, 'implemented_capabilities': {'search': implemented, 'detail': False, 'comments': False},
                'validation_status': 'live_verified' if verified else 'contract_only' if implemented else 'not_integrated',
                'live_verified': verified,
                'search_endpoint': platform['search_endpoint'], 'time_policy': TIME_POLICY.get(slug, '待接入，不作时间范围承诺。'),
                'mode': 'keyword_search', 'mode_label': '关键词搜索', 'requires': [], 'limits': ''}
        if slug in SPECIAL_MODES:
            mode = SPECIAL_MODES[slug]
            entry = MODE_VERIFICATION['platforms'].get(slug, {})
            item.update(mode=mode['mode'], mode_label=mode['mode_label'], requires=mode['requires'],
                        limits=mode['limits'], verified=bool(entry.get('status') == 'verified'),
                        request_id=entry.get('request_id'), mode_endpoint=entry.get('endpoint'),
                        implemented_capabilities={'search': slug != 'toutiao', 'detail': slug == 'toutiao', 'comments': False})
        if covered:
            item['selectable'] = False
            item['covered_by'] = 'wechat_search'
            item['vertical'] = covered['vertical']
            item['covered_request_id'] = covered_state.get('request_id')
            item['validation_status'] = 'covered_vertical' if covered_state and covered_state.get('verified') else 'not_integrated'
            item['live_verified'] = bool(covered_state and covered_state.get('verified'))
            item['price_usd'] = wechat_quote[0] if wechat_quote else None
            item['time_policy'] = TIME_POLICY['wechat_search']
            item['api_capabilities'] = {'keyword_search': True, 'detail': False, 'comments': False}
        if slug == 'wechat_search':
            share_price = verified_tikhub_price('/api/v1/wechat_channels/v2/fetch_video_share_url')
            share_entry = MODE_VERIFICATION['platforms']['wechat_channels']
            item['supports_scope_selector'] = True
            item['scope_config_key'] = 'wechat_business_type'
            item['verticals'] = WECHAT_VERTICALS
            item['native_time_filter'] = {'supported': True, 'verified': bool(_WECHAT_EVIDENCE.get('native_time_verified')),
                                          'values': ['all', 'day', 'week', 'half_year']}
            item['modes'] = [
                {'id': 'article_search', 'label': '公众号文章关键词搜索', 'verified': WECHAT_VERTICALS[1]['verified'],
                 'price_usd': wechat_quote[0] if wechat_quote else None,
                 'request_id': WECHAT_VERTICALS[1]['request_id'], 'requires': []},
                {'id': 'video_share_link', 'label': WECHAT_SHARE['mode_label'], 'verified': share_entry['status'] == 'verified',
                 'price_usd': wechat_quote[0] if wechat_quote else None,
                 'extra_price_usd': share_price[0] if share_price else None,
                 'extra_calls_per_item': WECHAT_SHARE['calls_per_item'], 'request_id': share_entry.get('share_request_id'),
                 'requires': [], 'limits': WECHAT_SHARE['limits']},
            ]
            item['share_link'] = {**WECHAT_SHARE, 'verified': share_entry['status'] == 'verified',
                                  'extra_price_usd': share_price[0] if share_price else None,
                                  'search_request_id': share_entry.get('search_request_id'),
                                  'detail_request_id': share_entry.get('detail_request_id'),
                                  'share_request_id': share_entry.get('share_request_id'),
                                  'share_url': share_entry.get('share_url')}
            item['extra_call_price_usd'] = share_price[0] if share_price else None
            item['extra_calls_per_item'] = WECHAT_SHARE['calls_per_item']
            item['request_id'] = WECHAT_VERTICALS[1]['request_id']
            item['mode_label'] = '公众号文章 / 视频号分享链'
            item['detail'] += (f" 视频号分享链已实测：搜索 {share_entry.get('search_request_id')} → 详情 "
                               f"{share_entry.get('detail_request_id')} → 分享链 {share_entry.get('share_request_id')}；"
                               f"每条额外 2 次调用、约 30 秒，拿不到短链就不展示假链接。")
        if slug == 'wechat_channels':
            share_price = verified_tikhub_price('/api/v1/wechat_channels/v2/fetch_video_share_url')
            item['mode'] = WECHAT_SHARE['mode']
            item['mode_label'] = WECHAT_SHARE['mode_label']
            item['verified'] = covered_state.get('status') == 'verified' if covered_state else False
            item['request_id'] = covered_state.get('share_request_id') if covered_state else None
            item['share_link'] = {**WECHAT_SHARE, 'verified': item['verified'],
                                  'extra_price_usd': share_price[0] if share_price else None,
                                  'search_request_id': covered_state.get('request_id') if covered_state else None,
                                  'detail_request_id': covered_state.get('detail_request_id') if covered_state else None,
                                  'share_request_id': covered_state.get('share_request_id') if covered_state else None,
                                  'share_url': covered_state.get('share_url') if covered_state else None}
            item['extra_call_price_usd'] = share_price[0] if share_price else None
            item['extra_calls_per_item'] = WECHAT_SHARE['calls_per_item']
            item['available'] = bool(item['verified'] and share_price and configured and not paid_off)
        items.append(item)
    for slug, name in [('github', 'GitHub'), ('hackernews', 'Hacker News'), ('rss', 'RSS'), ('web_search', '网页搜索')]:
        paid = slug == 'web_search'
        configured = bool(settings.firecrawl_api_key) if paid else True
        items.append({'id': slug, 'name': name, 'provider': 'firecrawl' if paid else 'public', 'available': not paid,
                      'selectable': True, 'configured': configured, 'paid_enabled': not paid_off if paid else False,
                      'status': ('未配置 · 付费关闭' if paid_off else '未配置') if paid and not configured else ('已配置 · 付费关闭' if paid_off else '已配置 · 需逐次授权') if paid else '公开来源 · 待运行',
                      'detail': '仅取回首屏，再按原始发布时间和业务词本地过滤；未知日期剔除。' + (' RSS 需填写公网订阅地址。' if slug == 'rss' else '')})
    return sorted(items, key=lambda item: ({'xiaohongshu': 0, 'douyin': 1}.get(item['id'], 2), item['id']))
