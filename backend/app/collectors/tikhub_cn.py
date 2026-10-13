"""Domestic platforms through TikHub's paid API: 小红书, 微博, 知乎, 抖音.

One search call per run (no paging), so each run costs exactly one TikHub request per
platform. Parsers are pure functions over TikHub's JSON so they can be tested on saved
responses without network or cost.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from urllib.parse import urlencode

from .base import CollectorCapabilities, SourceAdapter
from .http import fetcher
from .text import clean_text
from ..core.config import get_settings
from ..schemas.domain import RawItem

CHINA = timezone(timedelta(hours=8))


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


def _count(value) -> int | None:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_weibo_time(value: str | None, now: datetime | None = None) -> datetime | None:
    """'10月12日 10:55', '2025年10月12日 10:55', '今天 08:30', '5分钟前', '刚刚' (Beijing time)."""
    if not value:
        return None
    now = (now or datetime.now(UTC)).astimezone(CHINA)
    text = value.strip()
    if text == "刚刚":
        return now.astimezone(UTC)
    if m := re.fullmatch(r"(\d+)\s*秒前", text):
        return (now - timedelta(seconds=int(m.group(1)))).astimezone(UTC)
    if m := re.fullmatch(r"(\d+)\s*分钟前", text):
        return (now - timedelta(minutes=int(m.group(1)))).astimezone(UTC)
    if m := re.fullmatch(r"(\d+)\s*小时前", text):
        return (now - timedelta(hours=int(m.group(1)))).astimezone(UTC)
    if m := re.fullmatch(r"(今天|昨天)\s*(\d{1,2}):(\d{2})", text):
        day = now - timedelta(days=1 if m.group(1) == "昨天" else 0)
        return day.replace(hour=int(m.group(2)), minute=int(m.group(3)), second=0, microsecond=0).astimezone(UTC)
    if m := re.fullmatch(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*(?:(\d{1,2}):(\d{2}))?", text):
        year = int(m.group(1)) if m.group(1) else now.year
        try:
            parsed = datetime(year, int(m.group(2)), int(m.group(3)), int(m.group(4) or 0), int(m.group(5) or 0), tzinfo=CHINA)
        except ValueError:
            return None
        if not m.group(1) and parsed > now + timedelta(days=1):  # "12月30日" seen in January means last year
            parsed = parsed.replace(year=year - 1)
        return parsed.astimezone(UTC)
    return None


def parse_xiaohongshu(payload: dict, query: str) -> list[RawItem]:
    items = []
    for wrapper in ((payload.get("data") or {}).get("data") or {}).get("items") or []:
        note = wrapper.get("note") or {}
        note_id = str(note.get("id") or "")
        if not note_id:
            continue
        title, desc = clean_text(note.get("title")), clean_text(note.get("desc"))
        user = note.get("user") or {}
        token = note.get("xsec_token")
        url = f"https://www.xiaohongshu.com/explore/{note_id}" + (f"?{urlencode({'xsec_token': token, 'xsec_source': 'pc_search'})}" if token else "")
        items.append(RawItem(
            external_id=note_id, title=(title or desc)[:160] or f"小红书笔记 {note_id}", content=desc or title, url=url,
            author=user.get("nickname"), source="xiaohongshu", platform="xiaohongshu",
            published_at=_epoch(note.get("timestamp")), updated_at_source=_epoch(note.get("update_time")),
            engagement={"likes": _count(note.get("liked_count")), "comments": _count(note.get("comments_count")), "collects": _count(note.get("collected_count"))},
            metadata={"query": query, "acquisition_tool": "tikhub", "original_platform": "xiaohongshu", "note_type": str(note.get("type") or "")},
        ))
    return items


def parse_weibo(payload: dict, query: str, now: datetime | None = None) -> list[RawItem]:
    items = []
    for post in ((payload.get("data") or {}).get("parsed_data") or {}).get("results") or []:
        weibo_id = str(post.get("weibo_id") or "")
        content = clean_text(post.get("content"))
        if not weibo_id or not content:
            continue
        link = post.get("post_url") or ""
        url = ("https:" + link if link.startswith("//") else link) or f"https://m.weibo.cn/detail/{weibo_id}"
        interaction = post.get("interaction") or {}
        items.append(RawItem(
            external_id=weibo_id, title=content[:160], content=content, url=url.split("?")[0],
            author=post.get("user_nick") or post.get("user_name"), source="weibo", platform="weibo",
            published_at=parse_weibo_time(post.get("publish_time"), now),
            engagement={"reposts": _count(interaction.get("repost_count")), "comments": _count(interaction.get("comment_count")), "likes": _count(interaction.get("like_count"))},
            metadata={"query": query, "acquisition_tool": "tikhub", "original_platform": "weibo", "publish_time_raw": str(post.get("publish_time") or "")},
        ))
    return items


def parse_zhihu(payload: dict, query: str) -> list[RawItem]:
    items = []
    for entry in (payload.get("data") or {}).get("data") or []:
        if entry.get("type") != "search_result":
            continue
        obj = entry.get("object") or {}
        object_id = str(obj.get("id") or "")
        kind = obj.get("type")
        if not object_id or kind not in {"article", "answer"}:
            continue
        question = obj.get("question") or {}
        title = clean_text(obj.get("title") or question.get("name"))
        body = clean_text(obj.get("excerpt") or obj.get("content"))
        if kind == "article":
            url = f"https://zhuanlan.zhihu.com/p/{object_id}"
        else:
            url = f"https://www.zhihu.com/question/{question.get('id')}/answer/{object_id}" if question.get("id") else f"https://www.zhihu.com/answer/{object_id}"
        items.append(RawItem(
            external_id=f"{kind}:{object_id}", title=title[:160] or body[:160], content=body or title, url=url,
            author=(obj.get("author") or {}).get("name"), source="zhihu", platform="zhihu",
            published_at=_epoch(obj.get("created_time")), updated_at_source=_epoch(obj.get("updated_time")),
            engagement={"likes": _count(obj.get("voteup_count")), "comments": _count(obj.get("comment_count"))},
            metadata={"query": query, "acquisition_tool": "tikhub", "original_platform": "zhihu", "zhihu_type": str(kind)},
        ))
    return items


def parse_douyin(payload: dict, query: str) -> list[RawItem]:
    items = []
    for card in (payload.get("data") or {}).get("data") or []:
        aweme = card.get("aweme_info") or {}
        aweme_id = str(aweme.get("aweme_id") or "")
        desc = clean_text(aweme.get("desc"))
        if not aweme_id or not desc:
            continue
        stats = aweme.get("statistics") or {}
        author = aweme.get("author") or {}
        comments = [clean_text(c.get("text")) for c in card.get("comment_list") or [] if c.get("text")]
        items.append(RawItem(
            external_id=aweme_id, title=desc[:160], content=desc, url=f"https://www.douyin.com/video/{aweme_id}",
            author=author.get("nickname"), source="douyin", platform="douyin",
            published_at=_epoch(aweme.get("create_time")),
            engagement={"likes": _count(stats.get("digg_count")), "comments": _count(stats.get("comment_count")), "shares": _count(stats.get("share_count")), "plays": _count(stats.get("play_count"))},
            metadata={"query": query, "acquisition_tool": "tikhub", "original_platform": "douyin", "top_comments": " | ".join(comments[:3])[:500]},
        ))
    return items


class _TikHubCnCollector(SourceAdapter):
    path = ""
    method = "GET"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, detail=True)

    def request_args(self, query: str) -> dict:
        raise NotImplementedError

    def parse(self, payload: dict, query: str) -> list[RawItem]:
        raise NotImplementedError

    async def search(self, query: str) -> list[RawItem]:
        settings = get_settings()
        query = query.strip()
        if not query:
            raise RuntimeError("TIKHUB_QUERY_REQUIRED")
        if not settings.tikhub_api_key:
            raise RuntimeError("TIKHUB_API_KEY is not configured")
        url = settings.tikhub_base_url.rstrip("/") + self.path
        headers = {"Authorization": f"Bearer {settings.tikhub_api_key}", "Accept": "application/json"}
        args = self.request_args(query)
        if self.method == "POST":
            payload = await fetcher.post_json(url, args, headers=headers, timeout=90)
        else:
            payload = await fetcher.get_json(url + "?" + urlencode(args), headers=headers, timeout=90)
        if payload.get("code") not in (None, 200):
            raise RuntimeError(f"TikHub returned code {payload.get('code')}: {payload.get('message', '')}")
        return self.parse(payload, query)


class XiaohongshuCollector(_TikHubCnCollector):
    slug = "xiaohongshu"
    path = "/api/v1/xiaohongshu/app_v2/search_notes"

    def request_args(self, query: str) -> dict:
        return {"keyword": query, "page": 1, "sort_type": "time_descending"}

    def parse(self, payload: dict, query: str) -> list[RawItem]:
        return parse_xiaohongshu(payload, query)


class WeiboCollector(_TikHubCnCollector):
    slug = "weibo"
    path = "/api/v1/weibo/web_v2/fetch_realtime_search"

    def request_args(self, query: str) -> dict:
        return {"query": query, "page": 1}

    def parse(self, payload: dict, query: str) -> list[RawItem]:
        return parse_weibo(payload, query)


class ZhihuCollector(_TikHubCnCollector):
    slug = "zhihu"
    path = "/api/v1/zhihu/web/fetch_article_search_v3"

    def request_args(self, query: str) -> dict:
        return {"keyword": query, "offset": "0", "limit": "20"}

    def parse(self, payload: dict, query: str) -> list[RawItem]:
        return parse_zhihu(payload, query)


class DouyinCollector(_TikHubCnCollector):
    slug = "douyin"
    path = "/api/v1/douyin/search/fetch_general_search_v1"
    method = "POST"

    def request_args(self, query: str) -> dict:
        # publish_time "7": last week only; older posts are rarely still open requests.
        return {"keyword": query, "cursor": 0, "sort_type": "0", "publish_time": "7"}

    def parse(self, payload: dict, query: str) -> list[RawItem]:
        return parse_douyin(payload, query)


DOMESTIC_COLLECTORS = (XiaohongshuCollector, WeiboCollector, ZhihuCollector, DouyinCollector)
