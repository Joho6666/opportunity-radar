import asyncio

from app.collectors.base import CollectorCapabilities, SourceAdapter
from app.collectors.github import GitHubCollector
from app.collectors.hackernews import HackerNewsCollector
from app.collectors.mock import MockCollector
from app.collectors.registry import CollectorRegistry, default_collectors
from app.collectors.rss import RssCollector
from app.collectors.web_search import WebSearchCollector
from app.schemas.domain import RawItem


def test_every_default_collector_declares_capabilities():
    for adapter in default_collectors():
        caps = adapter.capabilities()
        assert isinstance(caps, CollectorCapabilities)
        assert caps.search is True


def test_capability_matrix_is_source_appropriate():
    assert GitHubCollector().capabilities().change_detection is True
    assert HackerNewsCollector().capabilities().comments is True
    assert RssCollector().capabilities().historical is True
    assert WebSearchCollector().capabilities().search is True
    assert MockCollector().capabilities().realtime is False


def test_healthcheck_defaults_to_true_without_network():
    async def scenario():
        results = await asyncio.gather(*(adapter.healthcheck() for adapter in default_collectors()))
        return results

    assert all(asyncio.run(scenario()))


def test_registry_exposes_capabilities_lookup():
    registry = CollectorRegistry([GitHubCollector()])
    caps = registry.capabilities("github")
    assert caps is not None and caps.search is True
    assert registry.capabilities("nope") is None


def test_registry_records_health_on_success_and_failure():
    class Boom(SourceAdapter):
        slug = "boom"

        async def search(self, query: str) -> list[RawItem]:
            raise RuntimeError("429 too many requests")

    registry = CollectorRegistry([Boom(), MockCollector()])
    calls: list[tuple] = []

    def recorder(slug, ok, items, latency_ms, error_code=None, error_message=None):
        calls.append((slug, ok, items, error_code))

    registry.set_health_recorder(recorder)

    async def scenario():
        await registry.search("mock", "q")
        await registry.search("boom", "q")

    asyncio.run(scenario())
    assert calls[0][:3] == ("mock", True, 4)
    assert calls[1][0] == "boom" and calls[1][1] is False
    assert calls[1][3] == "RATE_LIMITED"
