import httpx
from .base import SourceAdapter
from ..core.config import get_settings
from ..schemas.domain import RawItem


class PublicWebCollector(SourceAdapter):
    slug = "public_web"
    async def search(self, query: str) -> list[RawItem]:
        key = get_settings().firecrawl_api_key
        if not key:
            return []
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post("https://api.firecrawl.dev/v1/search", headers={"Authorization": f"Bearer {key}"}, json={"query": query, "limit": 10})
            response.raise_for_status()
        return [RawItem(external_id=result.get("url", ""), title=result.get("title", ""), content=result.get("description", ""), url=result["url"], source=self.slug, metadata=result) for result in response.json().get("data", [])]
