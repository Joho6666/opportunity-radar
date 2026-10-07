from __future__ import annotations

import logging
import time

from .base import CollectorCapabilities, SourceAdapter
from .github import GitHubCollector
from .hackernews import HackerNewsCollector
from .mock import MockCollector
from .rss import RssCollector
from .web_search import WebSearchCollector

logger = logging.getLogger(__name__)

ALIASES = {"public_web": "web_search", "hn": "hackernews", "web": "web_search"}

# slugs that must never reach production deployments; kept available for tests
TEST_ONLY_SLUGS = {"mock"}


class CollectorRegistry:
    def __init__(self, adapters: list[SourceAdapter] | None = None, include_mock: bool | None = None) -> None:
        adapters = adapters if adapters is not None else default_collectors(include_mock=include_mock)
        self._adapters = {adapter.slug: adapter for adapter in adapters}
        self._health_recorder = None

    def set_health_recorder(self, recorder) -> None:
        """recorder(slug, ok, items, latency_ms, error_code, error_message) — wired by the app."""
        self._health_recorder = recorder

    def get(self, slug: str) -> SourceAdapter | None:
        key = ALIASES.get(slug, slug)
        return self._adapters.get(key)

    def capabilities(self, slug: str) -> CollectorCapabilities | None:
        adapter = self.get(slug)
        return adapter.capabilities() if adapter else None

    def slugs(self) -> list[str]:
        return sorted(self._adapters)

    async def search(self, slug: str, query: str):
        adapter = self.get(slug)
        if adapter is None:
            logger.warning("unknown collector slug skipped", extra={"slug": slug})
            self._record_health(slug, ok=False, items=0, latency_ms=0, error_code="UNKNOWN_SOURCE", error_message=f"未知数据源: {slug}")
            return [], {"source": slug, "error_code": "UNKNOWN_SOURCE", "message": f"未知数据源: {slug}"}
        started = time.perf_counter()
        try:
            items = await adapter.search(query)
            self._record_health(slug, ok=True, items=len(items), latency_ms=int((time.perf_counter() - started) * 1000))
            return items, None
        except Exception as exc:
            logger.exception("collector failed", extra={"slug": slug})
            error_code = "RATE_LIMITED" if "429" in str(exc) else "COLLECTOR_FAILED"
            message = f"{type(exc).__name__}: {exc}"[:400]
            self._record_health(slug, ok=False, items=0, latency_ms=int((time.perf_counter() - started) * 1000), error_code=error_code, error_message=message)
            return [], {"source": slug, "error_code": error_code, "message": message}

    def _record_health(self, slug: str, ok: bool, items: int, latency_ms: int, error_code: str | None = None, error_message: str | None = None) -> None:
        if self._health_recorder is None:
            return
        try:
            self._health_recorder(slug, ok, items, latency_ms, error_code, error_message)
        except Exception:
            logger.exception("source health recording failed", extra={"slug": slug})


def default_collectors(include_mock: bool | None = None) -> list[SourceAdapter]:
    """Mock stays registered by default so local demo mode works; compose/CI set
    INCLUDE_MOCK_COLLECTOR=false to exclude it."""
    import os

    if include_mock is None:
        include_mock = os.getenv("INCLUDE_MOCK_COLLECTOR", "true").lower() != "false"
    collectors: list[SourceAdapter] = [GitHubCollector(), HackerNewsCollector(), RssCollector(), WebSearchCollector()]
    if include_mock:
        collectors.append(MockCollector())
    return collectors


registry = CollectorRegistry()
