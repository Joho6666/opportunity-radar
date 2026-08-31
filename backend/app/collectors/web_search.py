from .base import SourceAdapter
from .http import fetcher
from ..core.config import get_settings
from ..schemas.domain import RawItem


class WebSearchCollector(SourceAdapter):
    slug = "web_search"

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
            items.append(
                RawItem(
                    external_id=url,
                    title=result.get("title") or url,
                    content=result.get("description") or result.get("markdown") or "",
                    url=url,
                    author=None,
                    source=self.slug,
                    published_at=None,
                    metadata={**result, "query": query},
                )
            )
        return items
