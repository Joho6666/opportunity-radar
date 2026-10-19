"""Live-verified TikHub search adapters for non-domestic platforms.

Every parser here is derived from a real paid response archived on 2026-10-16
(see tikhub-live-verification.json for endpoints, request ids and evidence).
Contracts carry exactly the request arguments the verification calls used; a
native time dial is only wired where a real response proved it works. Response
shape drift raises PROVIDER_SCHEMA_CHANGED; unknown publish dates stay None and
are dropped by collection filters instead of being treated as fresh.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import re
from urllib.parse import urlencode

from .base import CollectorCapabilities, SourceAdapter
from .http import fetcher
from .text import clean_text
from ..core.config import get_settings
from ..core.errors import AppError
from ..schemas.domain import RawItem


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ''


def _count(value) -> int | None:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _epoch(value) -> datetime | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number > 10**12:  # milliseconds
        number //= 1000
    try:
        return datetime.fromtimestamp(number, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _iso_time(value) -> datetime | None:
    """ISO-8601 with the +0000 offsets Reddit returns."""
    text = _text(value).replace('+0000', '+00:00')
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _twitter_time(value) -> datetime | None:
    try:
        return datetime.strptime(_text(value), '%a %b %d %H:%M:%S %z %Y').astimezone(UTC)
    except (ValueError, TypeError):
        return None


_RELATIVE_AGE = re.compile(r'(\d+)\s*(second|minute|hour|day|week|month|year)s?\s+ago')
_RELATIVE_UNIT_SECONDS = {'second': 1, 'minute': 60, 'hour': 3600, 'day': 86400, 'week': 604800, 'month': 2592000, 'year': 31536000}


def relative_age_upper_bound(value, now: datetime | None = None) -> datetime | None:
    """Conservative age for provider-relative text ("5 hours ago").

    The bucket's upper boundary is used, so the derived publish time is never
    newer than reality; unknown text returns None and stays unknown.
    """
    match = _RELATIVE_AGE.search(_text(value))
    if not match:
        return None
    seconds = (int(match.group(1)) + 1) * _RELATIVE_UNIT_SECONDS[match.group(2)]
    return (now or datetime.now(UTC)) - timedelta(seconds=seconds)


def _envelope(payload, label: str) -> dict:
    if not isinstance(payload, dict):
        raise AppError('PROVIDER_RESPONSE_INVALID', f'{label} 返回非 JSON 对象。', 502)
    if payload.get('code') not in (None, 200):
        raise AppError('PROVIDER_RESPONSE_INVALID', f'{label} 返回非成功响应。', 502)
    return payload


def _rows(payload: dict, label: str, *path: str) -> list:
    value = payload
    for key in path:
        if not isinstance(value, dict) or not isinstance(value.get(key), (list, dict)):
            raise AppError('PROVIDER_SCHEMA_CHANGED', f'{label} 响应缺少预期结构 {"/".join(path)}。', 502)
        value = value[key]
    if not isinstance(value, list):
        raise AppError('PROVIDER_SCHEMA_CHANGED', f'{label} 预期条目列表，收到不兼容响应。', 502)
    return value


def _metadata(query, platform, kind, **extra):
    return {'query': query, 'acquisition_tool': 'tikhub', 'original_platform': platform,
            'content_kind': kind, 'validation_status': 'live_verified', **extra}


# ---------------------------------------------------------------- bilibili
def parse_bilibili(payload: dict, query: str) -> list[RawItem]:
    payload = _envelope(payload, 'Bilibili')
    items = []
    for row in _rows(payload, 'Bilibili', 'data', 'data', 'result'):
        if not isinstance(row, dict) or row.get('type') != 'video':
            continue
        bvid, aid = _text(row.get('bvid')), row.get('aid')
        title = clean_text(row.get('title'))
        if not title or not (bvid or aid):
            continue
        link = _text(row.get('arcurl')).replace('http://', 'https://')
        url = link if link.startswith('https://') else f'https://www.bilibili.com/video/{bvid or aid}'
        items.append(RawItem(
            external_id=bvid or str(aid), title=title[:160], content=clean_text(row.get('description')) or title,
            url=url, author=_text(row.get('author')) or None, source='bilibili', platform='bilibili',
            published_at=_epoch(row.get('pubdate')),
            engagement={'likes': _count(row.get('like')), 'comments': _count(row.get('review')),
                        'collects': _count(row.get('favorites')), 'views': _count(row.get('play')), 'danmaku': _count(row.get('video_review'))},
            metadata=_metadata(query, 'bilibili', 'video', mid=row.get('mid'), duration=row.get('duration'),
                               date_status='native_pubdate' if row.get('pubdate') else 'unknown'),
        ))
    return items


# ---------------------------------------------------------------- kuaishou
_SHARE_PHOTO_ID = re.compile(r'(?:^|&)photoId=([A-Za-z0-9_-]+)')


def parse_kuaishou(payload: dict, query: str) -> list[RawItem]:
    payload = _envelope(payload, '快手')
    items = []
    for wrapper in _rows(payload, '快手', 'data', 'mixFeeds'):
        feed = wrapper.get('feed') if isinstance(wrapper, dict) else None
        if not isinstance(feed, dict):
            continue
        photo_id = feed.get('photo_id')
        caption = clean_text(feed.get('caption') or feed.get('captionToComment'))
        if photo_id is None or not caption:
            continue
        match = _SHARE_PHOTO_ID.search(_text(feed.get('share_info')))
        share_id = match.group(1) if match else None
        if share_id:
            url, url_source = f'https://www.kuaishou.com/short-video/{share_id}', 'share_info'
        else:
            url, url_source = f'https://www.kuaishou.com/short-video/{photo_id}', 'photo_id'
        items.append(RawItem(
            external_id=str(photo_id), title=caption[:160], content=caption,
            url=url, author=_text(feed.get('user_name')) or None, source='kuaishou', platform='kuaishou',
            published_at=_epoch(feed.get('timestamp')),
            engagement={'likes': _count(feed.get('like_count')), 'views': _count(feed.get('view_count')),
                        'comments': _count(feed.get('comment_count')), 'shares': _count(feed.get('share_count'))},
            metadata=_metadata(query, 'kuaishou', 'video', user_id=feed.get('user_id'), location=feed.get('location'),
                               url_source=url_source, date_status='native_timestamp_ms' if feed.get('timestamp') else 'unknown'),
        ))
    return items


# ---------------------------------------------------------------- lemon8
def parse_lemon8(payload: dict, query: str) -> list[RawItem]:
    payload = _envelope(payload, 'Lemon8')
    data = payload.get('data')
    if not isinstance(data, list):
        raise AppError('PROVIDER_SCHEMA_CHANGED', 'Lemon8 响应缺少帧列表。', 502)
    items = []
    for frame in data:
        rows = frame.get('data', {}).get('items') if isinstance(frame, dict) and isinstance(frame.get('data'), dict) else None
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get('item_id') or item.get('group_id') or '')
            title = clean_text(item.get('title')) or clean_text(item.get('short_content'))
            content = clean_text(item.get('content')) or clean_text(item.get('description')) or title
            url = next((_text(item.get(key)) for key in ('share_url', 'article_url', 'display_url') if _text(item.get(key)).startswith('http')), '')
            if not item_id or not content or not url:
                continue
            author = item.get('author') if isinstance(item.get('author'), dict) else {}
            items.append(RawItem(
                external_id=item_id, title=(title or content)[:160], content=content, url=url,
                author=_text(author.get('name')) or _text(author.get('user_unique_name')) or None,
                source='lemon8', platform='lemon8', published_at=_epoch(item.get('publish_time')),
                engagement={'likes': _count(item.get('like_count')), 'views': _count(item.get('read_count')),
                            'comments': _count(item.get('comment_count')), 'shares': _count(item.get('share_count')),
                            'collects': _count(item.get('favorite_count')), 'reposts': _count(item.get('repost_count'))},
                metadata=_metadata(query, 'lemon8', 'note', article_class=item.get('article_class'), language=item.get('language'),
                                   date_status='native_publish_time' if item.get('publish_time') else 'unknown'),
            ))
    return items


# ---------------------------------------------------------------- pipixia
def parse_pipixia(payload: dict, query: str) -> list[RawItem]:
    payload = _envelope(payload, '皮皮虾')
    items = []
    for cell in _rows(payload, '皮皮虾', 'data', 'data', 'data'):
        item = cell.get('item') if isinstance(cell, dict) else None
        if not isinstance(item, dict):
            continue
        item_id, content = item.get('item_id'), clean_text(item.get('content'))
        if item_id is None or not content:
            continue
        share = item.get('share') if isinstance(item.get('share'), dict) else {}
        link = _text(share.get('share_url'))
        url = link if link.startswith('http') else f'https://h5.pipix.com/ppx/item/{item_id}'
        stats = item.get('stats') if isinstance(item.get('stats'), dict) else {}
        author = item.get('author') if isinstance(item.get('author'), dict) else {}
        items.append(RawItem(
            external_id=str(item_id), title=content[:160], content=content, url=url,
            author=_text(author.get('name')) or None, source='pipixia', platform='pipixia',
            published_at=_epoch(item.get('create_time')),
            engagement={'likes': _count(stats.get('like_count')), 'comments': _count(stats.get('comment_count')),
                        'shares': _count(stats.get('share_count')), 'views': _count(stats.get('view_count')),
                        'collects': _count(stats.get('favorite_count')), 'plays': _count(stats.get('play_count'))},
            metadata=_metadata(query, 'pipixia', 'video', duration=item.get('duration'), item_type=item.get('item_type'),
                               date_status='native_create_time' if item.get('create_time') else 'unknown'),
        ))
    return items


# ---------------------------------------------------------------- threads
def parse_threads(payload: dict, query: str) -> list[RawItem]:
    payload = _envelope(payload, 'Threads')
    items = []
    for result in _rows(payload, 'Threads', 'data', 'results'):
        node = result.get('node') if isinstance(result, dict) else None
        thread = node.get('thread') if isinstance(node, dict) else None
        thread_items = thread.get('thread_items') if isinstance(thread, dict) else None
        if not isinstance(thread_items, list):
            continue
        for entry in thread_items:
            post = entry.get('post') if isinstance(entry, dict) else None
            if not isinstance(post, dict):
                continue
            pk, code = post.get('pk'), _text(post.get('code'))
            caption = post.get('caption') if isinstance(post.get('caption'), dict) else {}
            text = clean_text(caption.get('text'))
            if not text or not (pk or code):
                continue
            user = post.get('user') if isinstance(post.get('user'), dict) else {}
            username = _text(user.get('username'))
            if username and code:
                url = f'https://www.threads.com/@{username}/post/{code}'
            elif code:
                url = f'https://www.threads.com/t/{code}'
            else:
                continue
            items.append(RawItem(
                external_id=str(pk or code), title=text[:160], content=text, url=url,
                author=username or None, source='threads', platform='threads',
                published_at=_epoch(post.get('taken_at')),
                engagement={'likes': _count(post.get('like_count'))},
                metadata=_metadata(query, 'threads', 'post', media_type=post.get('media_type'),
                                   date_status='native_taken_at' if post.get('taken_at') else 'unknown'),
            ))
    return items


# ---------------------------------------------------------------- twitter
def parse_twitter(payload: dict, query: str) -> list[RawItem]:
    payload = _envelope(payload, 'X')
    items = []
    for tweet in _rows(payload, 'X', 'data', 'timeline'):
        if not isinstance(tweet, dict) or tweet.get('type') != 'tweet':
            continue
        tweet_id, text, screen = _text(tweet.get('tweet_id')), clean_text(tweet.get('text')), _text(tweet.get('screen_name'))
        if not tweet_id or not text or not screen:
            continue
        user_info = tweet.get('user_info') if isinstance(tweet.get('user_info'), dict) else {}
        shares = sum(v for v in (_count(tweet.get('retweets')), _count(tweet.get('quotes'))) if v)
        items.append(RawItem(
            external_id=tweet_id, title=text[:160], content=text,
            url=f'https://x.com/{screen}/status/{tweet_id}', author=screen, source='twitter', platform='twitter',
            published_at=_twitter_time(tweet.get('created_at')),
            engagement={'likes': _count(tweet.get('favorites')), 'comments': _count(tweet.get('replies')),
                        'shares': shares, 'views': _count(tweet.get('views'))},
            metadata=_metadata(query, 'twitter', 'post', language=tweet.get('lang'), display_name=_text(user_info.get('name')),
                               date_status='native_created_at' if tweet.get('created_at') else 'unknown'),
        ))
    return items


# ---------------------------------------------------------------- youtube
def parse_youtube(payload: dict, query: str, now: datetime | None = None) -> list[RawItem]:
    payload = _envelope(payload, 'YouTube')
    items = []
    for video in _rows(payload, 'YouTube', 'data', 'videos'):
        if not isinstance(video, dict):
            continue
        video_id, title = _text(video.get('video_id')), clean_text(video.get('title'))
        if not video_id or not title:
            continue
        link = _text(video.get('url'))
        url = link if link.startswith('http') else f'https://www.youtube.com/watch?v={video_id}'
        published = relative_age_upper_bound(video.get('published_time'), now)
        views = _count(re.sub(r'[^0-9]', '', _text(video.get('view_count'))) or None)
        items.append(RawItem(
            external_id=video_id, title=title[:160], content=clean_text(video.get('description_snippet')) or title,
            url=url, author=_text(video.get('author')) or None, source='youtube', platform='youtube',
            published_at=published,
            engagement={'views': views},
            metadata=_metadata(query, 'youtube', 'video', channel_id=video.get('channel_id'), duration=video.get('duration'),
                               published_time_raw=_text(video.get('published_time')),
                               date_status='provider_relative_upper_bound' if published else 'unknown'),
        ))
    return items


# ---------------------------------------------------------------- wechat_search
WECHAT_BUSINESS_TYPES = {'all': 'all', 'article': 'article', 'video': 'video'}
WECHAT_CONTENT_KIND = {'all': 'mixed', 'article': 'article', 'video': 'video'}
# Only scopes proven by a real paid response may be advertised as verified.
WECHAT_VERIFIED_SCOPES = frozenset({'article'})  # 2026-10-18: 综合未单独实测；视频垂类无原文链接


def wechat_business_type(config: dict) -> str:
    value = config.get('wechat_business_type') or 'article'
    if value not in WECHAT_BUSINESS_TYPES:
        raise AppError('INVALID_WECHAT_SCOPE', 'wechat_business_type 仅支持 all / article / video。', 400)
    return value


def wechat_search_rows(payload: dict) -> list[tuple[dict, str]]:
    """Both documented frame shapes: article frames use items[], Channels use subBoxes[].items[].

    Channels rows carry title/author/pubTime/duration but no per-item original
    link (the paid response has exportId/jumpInfo only), so they cannot become
    verifiable evidence. They are still surfaced here for audits and tests.
    """
    payload = _envelope(payload, '微信搜一搜')
    raw_data = payload.get('data')
    data: dict = raw_data if isinstance(raw_data, dict) else {}
    results = data.get('results')
    if not isinstance(results, dict):
        raise AppError('PROVIDER_SCHEMA_CHANGED', '微信搜一搜响应缺少 results 结构。', 502)
    frames = results.get('data')
    if not isinstance(frames, list):
        raise AppError('PROVIDER_SCHEMA_CHANGED', '微信搜一搜响应缺少结果帧列表。', 502)
    rows: list[tuple[dict, str]] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        for row in frame.get('items') or []:
            if isinstance(row, dict):
                rows.append((row, 'article'))
        for box in frame.get('subBoxes') or []:
            for row in (box.get('items') if isinstance(box, dict) else None) or []:
                if isinstance(row, dict):
                    rows.append((row, 'video'))
    return rows


def parse_wechat_search(payload: dict, query: str, scope: str | None = None) -> list[RawItem]:
    raw_data = payload.get('data') if isinstance(payload, dict) else None
    data: dict = raw_data if isinstance(raw_data, dict) else {}
    echoed = _text(data.get('business_type'))
    effective = scope if scope in WECHAT_BUSINESS_TYPES else (echoed if echoed in WECHAT_BUSINESS_TYPES else 'article')
    kind = WECHAT_CONTENT_KIND[effective]
    items = []
    for row, row_kind in wechat_search_rows(payload):
        doc_id = str(row.get('docID') or row.get('doc_id') or row.get('id') or row.get('object_id') or '')
        title, desc = clean_text(row.get('title')), clean_text(row.get('desc') or row.get('content') or row.get('summary'))
        url = next((_text(row.get(key)) for key in ('doc_url', 'url', 'jump_url', 'share_url', 'play_url') if _text(row.get(key)).startswith('http')), '')
        # A search hit without an original link is not evidence; drop it instead
        # of fabricating a URL or storing an unusable empty link.
        if not doc_id or not url or not (title or desc):
            continue
        raw_source = row.get('source')
        source: dict = raw_source if isinstance(raw_source, dict) else {}
        published = (_epoch(row.get('timestamp')) or _epoch(row.get('date')) or _epoch(row.get('publish_time'))
                     or _epoch(row.get('pubTime')) or _epoch(row.get('create_time')))
        author = (_text(source.get('title')) or _text(source.get('nickname')) or _text(row.get('nickname'))
                  or _text(row.get('author')) or None)
        items.append(RawItem(
            external_id=doc_id, title=(title or desc)[:160], content=desc or title, url=url,
            author=author, source='wechat_search', platform='wechat_search',
            published_at=published,
            metadata=_metadata(query, 'wechat_search', kind, wechat_business_type=effective, row_kind=row_kind,
                               relative_time_raw=_text(source.get('dateTime')) or _text(row.get('dateTime')),
                               published_epoch=int(row.get('timestamp') or row.get('date') or row.get('publish_time') or row.get('pubTime') or 0) or None,
                               date_status='native_timestamp' if published else 'unknown'),
        ))
    return items


# ---------------------------------------------------------------- reddit
def parse_reddit(payload, query):
    payload = _envelope(payload, 'Reddit')
    data = payload.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('children'), list):
        raise AppError('PROVIDER_RESPONSE_INVALID', 'Reddit compact children 结构不匹配。', 502)
    items = []
    for wrapper in data['children']:
        post = wrapper.get('post') if isinstance(wrapper, dict) else None
        if not isinstance(post, dict):
            raise AppError('PROVIDER_RESPONSE_INVALID', 'Reddit post 结构不匹配。', 502)
        post_id, title = post.get('id'), post.get('postTitle')
        if not isinstance(post_id, str) or not re.fullmatch(r't3_[A-Za-z0-9]+', post_id) or not isinstance(title, str) or not title.strip():
            raise AppError('PROVIDER_RESPONSE_INVALID', 'Reddit post id/title 结构不匹配。', 502)
        body = clean_text((post.get('content') or {}).get('markdown')) if isinstance(post.get('content'), dict) else ''
        permalink = _text(post.get('permalink'))
        url = f'https://www.reddit.com{permalink}' if permalink.startswith('/') else f'https://www.reddit.com/comments/{post_id[3:]}/'
        subreddit = post.get('subreddit') if isinstance(post.get('subreddit'), dict) else {}
        author = post.get('authorInfo') if isinstance(post.get('authorInfo'), dict) else {}
        published = _iso_time(post.get('createdAt'))
        items.append(RawItem(external_id=post_id, title=title[:160], content=body or title, url=url,
                             author=_text(author.get('name')) or None,
                             source='reddit', platform='reddit', published_at=published,
                             engagement={'likes': _count(post.get('score')), 'comments': _count(post.get('commentCount'))},
                             metadata=_metadata(query, 'reddit', 'post', subreddit=_text(subreddit.get('prefixedName')),
                                                content_completeness='full_text' if body else 'title_only',
                                                date_status='native_created_at' if published else 'unknown')))
    return items


# ---------------------------------------------------------------- contracts
@dataclass(frozen=True)
class SearchContract:
    path: str
    method: str
    query_parameter: str
    constants: tuple = ()
    time_mode: str | None = None  # only where a real paid response verified the dial
    config_arguments: str | None = None  # per-radar argument sourced from source_config


CONTRACTS = {
    'reddit': SearchContract('/api/v1/reddit/app/fetch_dynamic_search', 'GET', 'query',
                             (('search_type', 'post'), ('sort', 'NEW'), ('need_format', 'true'), ('allow_nsfw', '0'), ('safe_search', 'strict')),
                             'reddit_time_range'),
    'bilibili': SearchContract('/api/v1/bilibili/web/fetch_general_search', 'GET', 'keyword',
                               (('order', 'pubdate'), ('page', 1), ('page_size', 20), ('duration', 0)), 'bilibili_window'),
    'kuaishou': SearchContract('/api/v1/kuaishou/app/search_video_v2', 'GET', 'keyword', (('pcursor', ''),)),
    'lemon8': SearchContract('/api/v1/lemon8/app/fetch_search', 'GET', 'query',
                             (('max_cursor', ''), ('filter_type', ''), ('order_by', 'recent'), ('search_tab', 'main'))),
    'pipixia': SearchContract('/api/v1/pipixia/app/fetch_search', 'GET', 'keyword', (('offset', '0'), ('search_type', '1'))),
    'threads': SearchContract('/api/v1/threads/web/search_posts', 'GET', 'query'),
    'twitter': SearchContract('/api/v1/twitter/web/fetch_search_timeline', 'GET', 'keyword', (('search_type', 'Latest'),)),
    'youtube': SearchContract('/api/v1/youtube/web_v2/get_general_search_v2', 'GET', 'keyword', (('type', 'video'),), 'youtube_upload_date'),
    'wechat_search': SearchContract('/api/v1/wechat_search/v2/fetch_search', 'POST', 'keyword',
                                    (('business_type', 'article'), ('sort', 'latest'), ('offset', 0)),
                                    'wechat_publish_time', 'wechat_business_type'),
}
PARSERS = {'reddit': parse_reddit, 'bilibili': parse_bilibili, 'kuaishou': parse_kuaishou, 'lemon8': parse_lemon8,
           'pipixia': parse_pipixia, 'threads': parse_threads, 'twitter': parse_twitter, 'youtube': parse_youtube,
           'wechat_search': parse_wechat_search}
REDDIT_TIME_VALUES = {24: 'day', 168: 'week', 720: 'month'}
YOUTUBE_UPLOAD_DATE = {1: 'last_hour', 24: 'today', 168: 'this_week', 720: 'this_month', 8760: 'this_year'}
# Official 搜一搜 time dropdown: all/day/week/half_year. 72h uses week and is
# narrowed locally, never widened, so a bucket can only over-fetch the window.
WECHAT_PUBLISH_TIME = {24: 'day', 72: 'week', 168: 'week', 720: 'half_year'}


def time_arguments(contract: SearchContract, hours: int) -> dict:
    if contract.time_mode == 'reddit_time_range':
        return {'time_range': REDDIT_TIME_VALUES.get(hours, 'all')}
    if contract.time_mode == 'bilibili_window':
        now = int(datetime.now(UTC).timestamp())
        return {'pubtime_begin_s': now - hours * 3600, 'pubtime_end_s': now}
    if contract.time_mode == 'youtube_upload_date' and hours in YOUTUBE_UPLOAD_DATE:
        return {'upload_date': YOUTUBE_UPLOAD_DATE[hours]}
    if contract.time_mode == 'wechat_publish_time':
        return {'publish_time': WECHAT_PUBLISH_TIME.get(hours, 'all')}
    return {}


class CatalogCollector(SourceAdapter):
    def __init__(self, slug):
        self.slug = slug
        self.contract = CONTRACTS[slug]
        self.path = self.contract.path

    def capabilities(self):
        return CollectorCapabilities(search=True, detail=False, comments=False)

    async def search(self, query):
        return await self.search_configured(query, {})

    async def _wechat_share_items(self, payload, query, config, settings):
        """搜索行 -> exportId -> detail.id -> 分享链；失败不伪造 URL。"""
        from .tikhub_modes import WECHAT_DETAIL_PATH, WECHAT_SHARE_PATH, parse_wechat_share_count
        count = parse_wechat_share_count(config.get('wechat_share_links'))
        rows = [row for row, kind in wechat_search_rows(payload) if kind == 'video' and isinstance(row, dict)]
        headers = {'Authorization': f'Bearer {settings.tikhub_api_key}', 'Accept': 'application/json'}
        base = settings.tikhub_base_url.rstrip('/')
        items, failures = [], []
        for row in rows:
            if len(items) >= count:
                break
            export_id = _text(row.get('exportId'))
            try:
                nonce = json.loads(((row.get('jumpInfo') or {}).get('extInfo') or '{}')).get('feedNonceId')
            except (TypeError, ValueError, AttributeError):
                nonce = None
            if not export_id.startswith('export/'):
                failures.append('搜索行缺少 exportId')
                continue
            detail_payload = await fetcher.post_json(
                base + WECHAT_DETAIL_PATH,
                {'export_id': export_id, **({'object_nonce_id': str(nonce)} if nonce else {}), 'raw': False},
                headers=headers, timeout=90, billable_provider='tikhub', billable_source=self.slug)
            detail = detail_payload.get('data') if isinstance(detail_payload, dict) else None
            object_id = str((detail or {}).get('id') or '')
            if not object_id.isdigit():
                failures.append('详情未返回纯数字 object_id')
                continue
            share_payload = await fetcher.post_json(
                base + WECHAT_SHARE_PATH, {'object_id': object_id, 'raw': False},
                headers=headers, timeout=60, billable_provider='tikhub', billable_source=self.slug)
            share = share_payload.get('data') if isinstance(share_payload, dict) else None
            share_url = _text((share or {}).get('share_url'))
            if not (share_url.startswith('https://weixin.qq.com/sph/') or share_url.startswith('http://weixin.qq.com/sph/')):
                failures.append('分享链接口未返回 weixin.qq.com/sph/ 短链')
                continue
            detail = detail if isinstance(detail, dict) else {}
            source = row.get('source') if isinstance(row.get('source'), dict) else {}
            title = clean_text(detail.get('title')) or clean_text(row.get('title'))
            content = clean_text(detail.get('description')) or title
            published = _epoch(detail.get('create_time')) or _epoch(row.get('pubTime')) or _epoch(row.get('dateTime'))
            metadata = _metadata(query, 'wechat_search', 'video', wechat_business_type='video', row_kind='video',
                                 mode='video_share_link', mode_note='搜索后逐条生成视频号分享链；每条额外 2 次付费调用（详情 + 分享链），单条约 30 秒。',
                                 share_url_verified=True, share_chain='export_id->detail.id->share_url',
                                 provider_request_id=(payload or {}).get('request_id'),
                                 share_request_ids=[(detail_payload or {}).get('request_id'), (share_payload or {}).get('request_id')],
                                 extra_provider_calls=2, export_id_used=bool(export_id))
            items.append(RawItem(
                external_id=object_id, title=(title or content)[:160], content=content or title, url=share_url,
                author=clean_text(detail.get('nickname')) or _text(source.get('title')) or None,
                source='wechat_search', platform='wechat_search', published_at=published, metadata=metadata,
            ))
        if not items and rows:
            raise AppError('WECHAT_SHARE_URL_UNAVAILABLE',
                           f'视频号分享链未生成（{failures[0] if failures else "首屏无可解析视频"}）；不展示假链接。', 502)
        if items and failures:
            items[0].metadata['share_failures'] = failures[:3]
        return items

    async def search_configured(self, query, config):
        query = query.strip()
        if not query:
            raise AppError('TIKHUB_QUERY_REQUIRED', '关键词不能为空。', 400)
        settings = get_settings()
        if not settings.tikhub_api_key:
            raise AppError('SOURCE_NOT_CONFIGURED', 'TikHub 未配置。', 400)
        contract = self.contract
        try:
            hours = int(config.get('freshness_hours', '168'))
        except (ValueError, TypeError):
            raise AppError('INVALID_FRESHNESS', '无效时间窗口。', 400)
        scope = wechat_business_type(config) if contract.config_arguments == 'wechat_business_type' else None
        args = {**dict(contract.constants), contract.query_parameter: query, **time_arguments(contract, hours)}
        if scope:
            args['business_type'] = scope
        endpoint = settings.tikhub_base_url.rstrip('/') + contract.path
        kwargs = {'headers': {'Authorization': f'Bearer {settings.tikhub_api_key}', 'Accept': 'application/json'},
                  'timeout': 90, 'billable_provider': 'tikhub', 'billable_source': self.slug}
        if contract.method == 'GET':
            payload = await fetcher.get_json(endpoint + '?' + urlencode(args), **kwargs)
        else:
            payload = await fetcher.post_json(endpoint, args, **kwargs)
        if self.slug == 'wechat_search' and scope == 'video':
            return await self._wechat_share_items(payload, query, config, settings)
        items = PARSERS[self.slug](payload, query, scope) if self.slug == 'wechat_search' else PARSERS[self.slug](payload, query)
        for item in items:
            item.metadata['provider_endpoint'] = endpoint
            if scope:
                item.metadata['wechat_business_type'] = scope
                item.metadata['scope_verified'] = scope in WECHAT_VERIFIED_SCOPES
                if scope not in WECHAT_VERIFIED_SCOPES:
                    item.metadata['validation_status'] = 'contract_only'
        return items


def catalog_collectors():
    return [CatalogCollector(slug) for slug in CONTRACTS]
