from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from .base import CollectorCapabilities, SourceAdapter
from .http import fetcher, validate_public_url
from ..core.config import get_settings
from ..core.errors import AppError
from ..schemas.domain import RawItem

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None


class RssCollector(SourceAdapter):
    slug = "rss"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, timeline=True, historical=True)

    async def search(self, query: str) -> list[RawItem]:
        feeds = _feeds_for(query)
        items: list[RawItem] = []
        for feed_url in feeds:
            try:
                validate_public_url(feed_url)
                response = await fetcher.request("GET", feed_url)
            except AppError:
                continue
            parsed = feedparser.parse(response.text) if feedparser else {"entries": []}
            for entry in parsed.get("entries", [])[:10]:
                url = entry.get("link") or feed_url
                title = entry.get("title") or url
                content = entry.get("summary") or entry.get("description") or title
                if query and query.lower() not in f"{title} {content}".lower() and not query.startswith("http"):
                    continue
                items.append(
                    RawItem(
                        external_id=entry.get("id") or url,
                        title=title,
                        content=content,
                        url=url,
                        author=_author(entry),
                        source=self.slug,
                        published_at=_published(entry),
                        updated_at_source=_updated(entry),
                        platform="rss",
                        engagement={},
                        metadata={"feed": feed_url, "query": query},
                    )
                )
        return items


def _feeds_for(query: str) -> list[str]:
    if query.startswith("http://") or query.startswith("https://"):
        return [query]
    configured = [item.strip() for item in get_settings().rss_feeds.split(",") if item.strip()]
    return configured or ["https://hnrss.org/newest"]


def _author(entry) -> str | None:
    if entry.get("author"):
        return entry.get("author")
    authors = entry.get("authors") or []
    if authors and isinstance(authors[0], dict):
        return authors[0].get("name")
    return None


def _published(entry) -> datetime | None:
    value = entry.get("published") or entry.get("updated")
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None


def _updated(entry) -> datetime | None:
    value = entry.get("updated")
    if not value or value == entry.get("published"):
        return None
    try:
        return parsedate_to_datetime(value).astimezone(UTC)
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
