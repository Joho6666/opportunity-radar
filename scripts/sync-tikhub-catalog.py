#!/usr/bin/env python3
"""Refresh public OpenAPI evidence only. Never calls a billable data endpoint."""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'demo', 'health', 'hybrid', 'ios_shortcut', 'tikhub'}
NAMES = {'bilibili': '哔哩哔哩', 'douyin': '抖音', 'instagram': 'Instagram', 'kuaishou': '快手', 'lemon8': 'Lemon8', 'linkedin': 'LinkedIn', 'pipixia': '皮皮虾', 'reddit': 'Reddit', 'telegram': 'Telegram', 'threads': 'Threads', 'tiktok': 'TikTok', 'toutiao': '今日头条', 'twitter': 'X / Twitter', 'wechat_channels': '微信视频号', 'wechat_mp': '微信公众号', 'wechat_search': '微信搜一搜', 'weibo': '微博', 'xiaohongshu': '小红书', 'xigua': '西瓜视频', 'youtube': 'YouTube', 'zhihu': '知乎'}
SEARCH = {
 'bilibili': '/api/v1/bilibili/web/fetch_general_search',
 'douyin': '/api/v1/douyin/search/fetch_video_search_v3',
 'instagram': '/api/v1/instagram/v2/search_reels',
 'kuaishou': '/api/v1/kuaishou/app/search_video_v2',
 'lemon8': '/api/v1/lemon8/app/fetch_search',
 'linkedin': '/api/v1/linkedin/web_v2/search_jobs',
 'pipixia': '/api/v1/pipixia/app/fetch_search',
 'reddit': '/api/v1/reddit/app/fetch_dynamic_search',
 'telegram': '/api/v1/telegram/web/fetch_channel_search',
 'threads': '/api/v1/threads/web/search_posts',
 'tiktok': '/api/v1/tiktok/web/fetch_general_search',
 'twitter': '/api/v1/twitter/web/fetch_search_timeline',
 'wechat_channels': '/api/v1/wechat_channels/v2/fetch_search_channel_videos',
 'wechat_search': '/api/v1/wechat_search/v2/fetch_search',
 'weibo': '/api/v1/weibo/web_v2/fetch_realtime_search',
 'xiaohongshu': '/api/v1/xiaohongshu/app_v2/search_notes',
 'xigua': '/api/v1/xigua/app/v2/search_video',
 'youtube': '/api/v1/youtube/web_v2/get_general_search_v2',
 'zhihu': '/api/v1/zhihu/web/fetch_article_search_v3',
}

def normalize(raw):
    spec = json.loads(raw)
    namespaces = {p.split('/')[3] for p in spec['paths'] if p.startswith('/api/v1/')}
    assert namespaces - EXCLUDED == set(NAMES), f'New/removed namespace: {namespaces - EXCLUDED ^ set(NAMES)}'
    platforms = []
    for namespace, name in sorted(NAMES.items()):
        operations = []
        for path, methods in spec['paths'].items():
            if not path.startswith(f'/api/v1/{namespace}/'):
                continue
            for method, op in methods.items():
                if method not in {'get', 'post', 'put', 'delete', 'patch'}:
                    continue
                record = {'path': path, 'method': method.upper(), 'summary': op.get('summary', '')}
                if path == SEARCH.get(namespace):
                    record.update(description=op.get('description', ''), parameters=op.get('parameters', []), request_body=op.get('requestBody'), responses=op.get('responses', {}))
                    body = op.get('requestBody', {}).get('content', {}).get('application/json', {}).get('schema', {})
                    if '$ref' in body:
                        record['body_schema'] = spec['components']['schemas'][body['$ref'].split('/')[-1]]
                operations.append(record)
        paths = [op['path'].lower() for op in operations]
        capabilities = {
            'keyword_search': namespace in SEARCH,
            'search_scope': 'channel_only' if namespace in {'telegram', 'wechat_channels'} else 'jobs_only' if namespace == 'linkedin' else 'content' if namespace in SEARCH else 'none',
            'detail': any(any(w in p for w in ('detail', 'article_content', 'post_info', 'get_article_info', 'get_video_info', 'fetch_one_video')) for p in paths),
            'comments': any('comment' in p for p in paths),
        }
        platforms.append({'namespace': namespace, 'id': 'tikhub' if namespace == 'tiktok' else namespace, 'name': name, 'api_capabilities': capabilities, 'search_endpoint': SEARCH.get(namespace), 'operations': operations})
    return {'source': 'https://api.tikhub.io/openapi.json', 'downloaded_at': datetime.now(UTC).isoformat(), 'version': spec['info']['version'], 'sha256': hashlib.sha256(raw).hexdigest(), 'excluded_namespaces': sorted(EXCLUDED), 'platform_count': len(platforms), 'platforms': platforms, 'response_envelope': spec['components']['schemas']['ResponseModel'], 'warning': 'Official API capabilities are not application integrations. Generic ResponseModel.data is unconstrained; no paid endpoint was called.'}

if __name__ == '__main__':
    request = Request('https://api.tikhub.io/openapi.json', headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
    raw = urlopen(request, timeout=90).read()
    evidence = normalize(raw)
    target = ROOT / 'backend/app/collectors/tikhub-platforms.json'
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: evidence[k] for k in ('version', 'downloaded_at', 'sha256', 'platform_count')}, ensure_ascii=False))
    print(', '.join(p['namespace'] for p in evidence['platforms']))
