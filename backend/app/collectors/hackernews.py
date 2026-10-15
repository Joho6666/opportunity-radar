from datetime import UTC, datetime
from urllib.parse import quote
from .base import CollectorCapabilities, SourceAdapter
from .http import fetcher
from .text import clean_text
from ..schemas.domain import RawItem


class HackerNewsCollector(SourceAdapter):
    slug = "hackernews"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, timeline=True, comments=True, realtime=True)

    async def search(self, query: str) -> list[RawItem]:
        items, next_cursor = await self.search_page(query)
        for item in items: item.metadata["next_cursor"] = next_cursor
        return items

    async def search_page(self, query: str, cursor: str | None = None) -> tuple[list[RawItem], str | None]:
        page = int(cursor or 0)
        if not 0 <= page <= 100:
            raise ValueError("Invalid page")
        comments = query.startswith("comments:")
        if comments:
            query = query.removeprefix("comments:").strip()
        q = quote(query.strip())
        tags = "comment" if comments else "show_hn" if not query.strip() or "show hn" in query.lower() else "story"
        # search_by_date: newest first. Relevance order surfaced decade-old threads as "new" evidence.
        payload = await fetcher.get_json(f"https://hn.algolia.com/api/v1/search_by_date?query={q}&tags={tags}&hitsPerPage=10&page={page}")
        items: list[RawItem] = []
        for hit in payload.get("hits", []):
            object_id = str(hit.get("objectID") or "")
            url = (None if comments else hit.get("url")) or f"https://news.ycombinator.com/item?id={object_id}"
            title = clean_text(hit.get("title") or hit.get("story_title")) or url
            content = clean_text(hit.get("story_text") or hit.get("comment_text")) or title
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
                    metadata={"points": hit.get("points"), "num_comments": hit.get("num_comments"), "query": query, "content_kind": "comment" if comments else "post", "parent_id": hit.get("parent_id"), "story_id": hit.get("story_id")},
                )
            )
        next_cursor = str(page + 1) if page + 1 < min(int(payload.get("nbPages") or 0), 101) else None
        return items, next_cursor


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None
