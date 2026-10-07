from datetime import UTC, datetime
from urllib.parse import quote
from .base import CollectorCapabilities, SourceAdapter
from .http import fetcher
from ..schemas.domain import RawItem


class HackerNewsCollector(SourceAdapter):
    slug = "hackernews"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, timeline=True, comments=True, realtime=True)

    async def search(self, query: str) -> list[RawItem]:
        q = quote(query.strip())
        tags = "show_hn" if not query.strip() or "show hn" in query.lower() else "story"
        payload = await fetcher.get_json(f"https://hn.algolia.com/api/v1/search?query={q}&tags={tags}&hitsPerPage=10")
        items: list[RawItem] = []
        for hit in payload.get("hits", []):
            object_id = str(hit.get("objectID") or "")
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={object_id}"
            title = hit.get("title") or url
            content = hit.get("story_text") or hit.get("comment_text") or title
            published = hit.get("created_at")
            updated = hit.get("updated_at")
            items.append(
                RawItem(
                    external_id=object_id or url,
                    title=title,
                    content=content,
                    url=url,
                    author=hit.get("author"),
                    source=self.slug,
                    published_at=_parse_dt(published),
                    updated_at_source=_parse_dt(updated),
                    platform="hackernews",
                    engagement={"points": hit.get("points"), "num_comments": hit.get("num_comments")},
                    metadata={"points": hit.get("points"), "num_comments": hit.get("num_comments"), "query": query},
                )
            )
        return items


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None
