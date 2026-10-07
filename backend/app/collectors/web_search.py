from datetime import UTC, datetime

from .base import CollectorCapabilities, SourceAdapter
from .http import fetcher
from ..core.config import get_settings
from ..schemas.domain import RawItem


class WebSearchCollector(SourceAdapter):
    slug = "web_search"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, historical=True)

    async def search(self, query: str) -> list[RawItem]:
        key = get_settings().firecrawl_api_key
        if not key:
            return []
        payload = await fetcher.post_json(
            "https://api.firecrawl.dev/v1/search",
            {"query": query, "limit": 10},
            headers={"Authorization": f"Bearer {key}"},
        )
        items: list[RawItem] = []
        for result in payload.get("data", []):
            url = result.get("url") or ""
            if not url:
                continue
            published = _extract_date(result)
            items.append(
                RawItem(
                    external_id=url,
                    title=result.get("title") or url,
                    content=result.get("description") or result.get("markdown") or "",
                    url=url,
                    author=None,
                    source=self.slug,
                    published_at=published,
                    updated_at_source=_extract_date(result, ("lastmod", "last_modified", "modified", "updated", "updatedAt")),
                    platform="web",
                    engagement={"score": result.get("score")} if result.get("score") is not None else {},
                    metadata={**result, "query": query},
                )
            )
        return items


DATE_KEYS = ("publishedAt", "published_at", "published", "datePublished", "date", "createdAt", "created_at", "docDate")


def _extract_date(source: dict, keys=DATE_KEYS) -> datetime | None:
    """Recursive date lookup: Firecrawl nests dates in metadata in varying shapes."""
    for key in keys:
        value = source.get(key)
        parsed = _parse(value)
        if parsed:
            return parsed
    for value in source.values():
        if isinstance(value, dict):
            parsed = _extract_date(value, keys)
            if parsed:
                return parsed
    return None


def _parse(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None
