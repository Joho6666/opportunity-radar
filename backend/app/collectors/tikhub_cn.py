"""Domestic platforms through TikHub's paid API: 小红书, 微博, 知乎, 抖音.

Each search_page performs at most one billed request; continuation requires an explicit
cursor where the provider supports it. Parsers are pure functions over TikHub's JSON so
they can be tested on saved responses without network or cost. Field mappings were
verified against real paid responses on 2026-10-16 (see tikhub-live-verification.json).
"""
from __future__ import annotations

import re
import json
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
        try:
            return day.replace(hour=int(m.group(2)), minute=int(m.group(3)), second=0, microsecond=0).astimezone(UTC)
        except ValueError:
            return None
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


def _rows(payload: dict, *path: str) -> list[dict]:
    from ..core.errors import AppError
    value = payload
    for key in path:
        if not isinstance(value,dict) or key not in value:
            raise AppError("PROVIDER_SCHEMA_CHANGED","响应缺少预期的数据结构。",502)
        value = value[key]
    if not isinstance(value,list) or any(not isinstance(row,dict) for row in value):
        raise AppError("PROVIDER_SCHEMA_CHANGED","预期条目列表，收到不兼容响应。",502)
    return value


def parse_xiaohongshu(payload: dict, query: str) -> list[RawItem]:
    items = []
    for wrapper in _rows(payload,"data","data","items"):
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
            metadata={"query": query, "acquisition_tool": "tikhub", "original_platform": "xiaohongshu", "content_kind":"note", "note_type": str(note.get("type") or "")},
        ))
    return items


def parse_weibo(payload: dict, query: str, now: datetime | None = None) -> list[RawItem]:
    items = []
    for post in _rows(payload,"data","parsed_data","results"):
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
            metadata={"query": query, "acquisition_tool": "tikhub", "original_platform": "weibo", "content_kind":"post", "publish_time_raw": str(post.get("publish_time") or "")},
        ))
    return items


def parse_zhihu(payload: dict, query: str) -> list[RawItem]:
    items = []
    for entry in _rows(payload,"data","data"):
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
            metadata={"query": query, "acquisition_tool": "tikhub", "original_platform": "zhihu", "content_kind":kind, "zhihu_type": str(kind)},
        ))
    return items


def _beijing_time(value) -> datetime | None:
    """Douyin v3 createTime is a Beijing-time string; epoch cross-checked on a real item."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=CHINA)
    except ValueError:
        return None
    return parsed.astimezone(UTC)


def parse_douyin(payload: dict, query: str) -> list[RawItem]:
    """抖音 v3 搜索：data.data[] 为扁平视频条目（itemId/title/url/likes/createTime）。

    v3 单次返回的是筛选条件下的整批结果（实测可达 1000 条），应用只取平台排序的
    首屏 50 条（与其它来源的首屏语义一致），其余交给本地时间/业务词过滤。
    """
    rows = _rows(payload, "data", "data")
    total = len(rows)
    items = []
    for item in rows[:50]:
        item_id = str(item.get("itemId") or item.get("item_id") or "")
        title = clean_text(item.get("title"))
        if not item_id or not title:
            continue
        link = str(item.get("url") or "")
        url = link if link.startswith("https://") else f"https://www.douyin.com/video/{item_id}"
        items.append(RawItem(
            external_id=item_id, title=title[:160], content=title, url=url,
            author=clean_text(item.get("nickname")) or None, source="douyin", platform="douyin",
            published_at=_beijing_time(item.get("createTime")),
            engagement={"likes": _count(item.get("likes")), "fans": _count(item.get("fans"))},
            metadata={"content_kind":"video","query": query, "acquisition_tool": "tikhub", "original_platform": "douyin",
                      "provider_total_items": total,
                      "date_status": "provider_string_asia_shanghai" if item.get("createTime") else "unknown",
                      "validation_status": "live_verified"},
        ))
    return items


class _TikHubCnCollector(SourceAdapter):
    path = ""
    method = "GET"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, detail=False)

    def request_args(self, query: str) -> dict:
        raise NotImplementedError

    def parse(self, payload: dict, query: str) -> list[RawItem]:
        raise NotImplementedError

    async def search(self, query: str) -> list[RawItem]:
        items, _ = await self.search_page(query)
        return items

    async def search_configured(self, query: str, source_config: dict[str, str]) -> list[RawItem]:
        items, _ = await self.search_page(query, source_config=source_config)
        return items

    async def search_page(self, query: str, cursor: str | None = None, *, source_config: dict[str, str] | None = None) -> tuple[list[RawItem], str | None]:
        settings = get_settings()
        query = query.strip()
        if not query:
            raise RuntimeError("TIKHUB_QUERY_REQUIRED")
        if not settings.tikhub_api_key:
            from ..core.errors import AppError
            raise AppError("TIKHUB_NOT_CONFIGURED", "TikHub 未配置；不会发送请求。", 409)
        url = settings.tikhub_base_url.rstrip("/") + self.path
        headers = {"Authorization": f"Bearer {settings.tikhub_api_key}", "Accept": "application/json"}
        args = self.request_args(query)
        hours = int((source_config or {}).get("freshness_hours", "168"))
        if self.slug == "xiaohongshu":
            args["time_filter"] = "一天内" if hours <= 24 else "一周内" if hours <= 168 else "半年内"
        elif self.slug == "douyin":
            # v3 native publish-time tiers: 0=any, 3=last 3 days, 7=last 7 days, 30=last month.
            args["date_type"] = "3" if hours <= 72 else "7" if hours <= 168 else "30" if hours <= 720 else "0"
        elif self.slug == "zhihu":
            args["time_interval"] = "a_day" if hours <= 24 else "a_week" if hours <= 168 else "a_month" if hours <= 720 else "three_months" if hours <= 2160 else "all"
        # TikHub has no native 30-day option for some platforms: fetch a wider first page,
        # then apply the exact published-at cutoff in collection_filter.
        if self.slug == "douyin":
            if cursor is not None:
                # v3 returns one bounded batch; a guessed continuation could repeat the first page and bill again.
                raise ValueError("抖音 v3 搜索不支持翻页")
        elif cursor is not None:
            state = json.loads(cursor) if cursor.startswith("{") else {}
            position = int(state.get("position", cursor) if state else cursor)
            if not 0 <= position <= 10000:
                raise ValueError("Invalid cursor")
            key = "page" if self.slug in {"xiaohongshu", "weibo"} else "offset" if self.slug == "zhihu" else "cursor"
            args[key] = str(position) if self.slug == "zhihu" else position
            for key in ("search_id", "search_session_id", "backtrace", "search_hash_id"):
                if key in state:
                    args[key] = state[key]
        if self.method == "POST":
            payload = await fetcher.post_json(url, args, headers=headers, timeout=90, billable_provider="tikhub", billable_source=self.slug)
        else:
            payload = await fetcher.get_json(url + "?" + urlencode(args), headers=headers, timeout=90, billable_provider="tikhub", billable_source=self.slug)
        if payload.get("code") not in (None, 200):
            raise RuntimeError("PROVIDER_REJECTED_REQUEST")
        if not isinstance(payload.get("data"), dict):
            raise RuntimeError("PROVIDER_SCHEMA_CHANGED")
        data = payload["data"]
        if self.slug == "xiaohongshu" and isinstance(data.get("data"), dict):
            data = data["data"]
        next_cursor = data.get("next_cursor")
        if next_cursor is None and data.get("has_more") and self.slug in {"xiaohongshu","weibo"}:
            next_cursor = str(int(args["page"]) + 1)
        if next_cursor is None and data.get("has_more") and data.get("cursor") is not None:
            next_cursor = str(data["cursor"])
        if self.slug == "zhihu" and isinstance(data.get("paging"), dict) and not data["paging"].get("is_end", True):
            from urllib.parse import urlparse, parse_qs
            next_cursor = parse_qs(urlparse(data["paging"].get("next", "")).query).get("offset", [None])[0]
        if next_cursor is not None and self.slug in {"xiaohongshu"}:
            state = {"position": int(next_cursor)}
            for key in ("search_id", "search_session_id", "backtrace"):
                if data.get(key) is not None:
                    state[key] = data[key]
            if isinstance(data.get("log_pb"), dict) and "search_id" not in state:
                state["search_id"] = data["log_pb"].get("impr_id", "")
            required = ("search_id","search_session_id") if self.slug == "xiaohongshu" else ("search_id","backtrace")
            # A guessed continuation could repeat the first page and incur another
            # charge. Keep first-page evidence, but do not offer incomplete sessions.
            next_cursor = json.dumps(state, separators=(",", ":")) if all(state.get(key) for key in required) else None
        return self.parse(payload, query), str(next_cursor) if next_cursor is not None else None


class XiaohongshuCollector(_TikHubCnCollector):
    slug = "xiaohongshu"
    path = "/api/v1/xiaohongshu/app_v2/search_notes"

    def request_args(self, query: str) -> dict:
        return {"keyword": query, "page": 1, "sort_type": "time_descending", "time_filter": "一周内", "note_type": "不限", "search_id": "", "search_session_id": "", "source": "explore_feed", "ai_mode": 0}

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
        return {"keyword": query, "offset": "0", "limit": "20", "search_source": "Filter", "sort": "created_time", "time_interval": "a_month"}

    def parse(self, payload: dict, query: str) -> list[RawItem]:
        return parse_zhihu(payload, query)


class DouyinCollector(_TikHubCnCollector):
    slug = "douyin"
    # v1 返回 400（历史探测）；v3 已实测可用并带原生发布时间档。
    path = "/api/v1/douyin/search/fetch_video_search_v3"
    method = "POST"

    def request_args(self, query: str) -> dict:
        return {"query": query, "date_type": "7", "label_type": 0, "duration_type": 0}

    def parse(self, payload: dict, query: str) -> list[RawItem]:
        return parse_douyin(payload, query)


DOMESTIC_COLLECTORS = (XiaohongshuCollector, WeiboCollector, ZhihuCollector, DouyinCollector)
