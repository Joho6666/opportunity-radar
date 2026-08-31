from __future__ import annotations

import logging
from .base import SourceAdapter
from .github import GitHubCollector
from .hackernews import HackerNewsCollector
from .mock import MockCollector
from .rss import RssCollector
from .web_search import WebSearchCollector

logger = logging.getLogger(__name__)

ALIASES = {"public_web": "web_search", "hn": "hackernews", "web": "web_search"}


class CollectorRegistry:
    def __init__(self, adapters: list[SourceAdapter] | None = None) -> None:
        self._adapters = {adapter.slug: adapter for adapter in (adapters or default_collectors())}

    def get(self, slug: str) -> SourceAdapter | None:
        key = ALIASES.get(slug, slug)
        return self._adapters.get(key)

    def slugs(self) -> list[str]:
        return sorted(self._adapters)

    async def search(self, slug: str, query: str):
        adapter = self.get(slug)
        if adapter is None:
            logger.warning("unknown collector slug skipped", extra={"slug": slug})
            return [], {"source": slug, "error_code": "UNKNOWN_SOURCE", "message": f"未知数据源: {slug}"}
        try:
            items = await adapter.search(query)
            return items, None
        except Exception as exc:
            logger.exception("collector failed", extra={"slug": slug})
            return [], {"source": slug, "error_code": "COLLECTOR_FAILED", "message": f"{type(exc).__name__}: {exc}"[:400]}


def default_collectors() -> list[SourceAdapter]:
    return [MockCollector(), GitHubCollector(), HackerNewsCollector(), RssCollector(), WebSearchCollector()]


registry = CollectorRegistry()
