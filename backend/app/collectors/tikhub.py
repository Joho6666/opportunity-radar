from datetime import UTC, datetime
from urllib.parse import urlencode

from .base import CollectorCapabilities, SourceAdapter
from .http import fetcher
from ..core.config import get_settings
from ..schemas.domain import RawItem


class TikHubCollector(SourceAdapter):
    """Minimal TikTok public-search adapter backed by TikHub."""

    slug = "tikhub"
    path = "/api/v1/tiktok/web/fetch_general_search"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, timeline=False, comments=False, detail=True, historical=False, realtime=False)

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
        data = payload.get("data") or {}
        wrappers = data.get("data") if isinstance(data, dict) else []
        items: list[RawItem] = []
        for wrapper in wrappers or []:
            item = wrapper.get("item") or {}
            item_id = str(item.get("id") or "")
            if not item_id:
                continue
            author = item.get("author") or {}
            unique_id = author.get("uniqueId") or author.get("unique_id") or ""
            url = f"https://www.tiktok.com/@{unique_id}/video/{item_id}" if unique_id else f"https://www.tiktok.com/video/{item_id}"
            desc = str(item.get("desc") or "").strip()
            items.append(RawItem(
                external_id=item_id,
                title=desc[:160] or f"TikTok video {item_id}",
                content=desc,
                url=url,
                author=unique_id or author.get("nickname"),
                source=self.slug,
                published_at=_parse_epoch(item.get("createTime")),
                platform="tiktok",
                engagement={
                    "likes": (item.get("stats") or {}).get("diggCount"),
                    "comments": (item.get("stats") or {}).get("commentCount"),
                    "shares": (item.get("stats") or {}).get("shareCount"),
                    "plays": (item.get("stats") or {}).get("playCount"),
                },
                metadata={
                    "content_kind": "video",
                    "query": query,
                    "nickname": author.get("nickname", ""),
                    "acquisition_tool": "tikhub",
                    "original_platform": "tiktok",
                    "provider_endpoint": endpoint,
                },
            ))
        return items


def _parse_epoch(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=UTC) if value else None
    except (TypeError, ValueError, OverflowError):
        return None
