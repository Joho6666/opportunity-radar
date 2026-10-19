from datetime import UTC, datetime
from urllib.parse import urlencode

from .base import CollectorCapabilities, SourceAdapter
from .http import fetcher
from .text import clean_text
from ..core.config import get_settings
from ..schemas.domain import RawItem


def parse_tiktok_search(payload: dict, query: str) -> list[RawItem]:
    """TikTok 网页综合搜索（data.data[].item）；字段对照 2026-10-16 真实响应。"""
    data = payload.get("data") or {}
    wrappers = data.get("data") if isinstance(data, dict) else []
    items: list[RawItem] = []
    for wrapper in wrappers or []:
        item = wrapper.get("item") if isinstance(wrapper, dict) else None
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if not item_id:
            continue
        author = item.get("author") or {}
        unique_id = author.get("uniqueId") or author.get("unique_id") or ""
        url = f"https://www.tiktok.com/@{unique_id}/video/{item_id}" if unique_id else f"https://www.tiktok.com/video/{item_id}"
        desc = clean_text(item.get("desc"))
        stats = item.get("stats") or {}
        items.append(RawItem(
            external_id=item_id,
            title=desc[:160] or f"TikTok video {item_id}",
            content=desc,
            url=url,
            author=unique_id or author.get("nickname"),
            source="tikhub",
            published_at=_parse_epoch(item.get("createTime")),
            platform="tiktok",
            engagement={
                "likes": (stats or {}).get("diggCount"),
                "comments": (stats or {}).get("commentCount"),
                "shares": (stats or {}).get("shareCount"),
                "plays": (stats or {}).get("playCount"),
                "collects": (stats or {}).get("collectCount"),
            },
            metadata={
                "content_kind": "video",
                "query": query,
                "nickname": author.get("nickname", ""),
                "acquisition_tool": "tikhub",
                "original_platform": "tiktok",
                "validation_status": "live_verified",
                "date_status": "native_create_time" if item.get("createTime") else "unknown",
            },
        ))
    return items


class TikHubCollector(SourceAdapter):
    """Minimal TikTok public-search adapter backed by TikHub."""

    slug = "tikhub"
    path = "/api/v1/tiktok/web/fetch_general_search"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, timeline=False, comments=False, detail=False, historical=False, realtime=False)

    async def search(self, query: str) -> list[RawItem]:
        settings = get_settings()
        query = query.strip()
        if not query:
            raise RuntimeError("TIKHUB_QUERY_REQUIRED")
        if not settings.tikhub_api_key:
            raise RuntimeError("TIKHUB_API_KEY is not configured")
        endpoint = settings.tikhub_base_url.rstrip("/") + self.path
        payload = await fetcher.get_json(
            endpoint + "?" + urlencode({"keyword": query.strip(), "offset": 0}),
            billable_provider="tikhub", billable_source=self.slug,
            headers={"Authorization": f"Bearer {settings.tikhub_api_key}", "Accept": "application/json"},
        )
        if payload.get("code") not in (None, 200):
            raise RuntimeError(f"TikHub returned code {payload.get('code')}: {payload.get('message', '')}")
        items = parse_tiktok_search(payload, query)
        for item in items:
            item.metadata["provider_endpoint"] = endpoint
        return items


def _parse_epoch(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC) if value else None
    except (TypeError, ValueError, OverflowError):
        return None
