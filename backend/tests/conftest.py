"""Unit and contract tests are offline. Live probes are separate scripts."""
import httpx
import pytest
from starlette.testclient import _TestClientTransport

@pytest.fixture(autouse=True)
def offline_http(monkeypatch):
    original_sync=httpx.Client.request
    def guarded_sync(self,*args,**kwargs):
        if not isinstance(self._transport,(httpx.MockTransport,_TestClientTransport)):
            raise AssertionError("Live HTTP is forbidden in pytest; use MockTransport")
        return original_sync(self,*args,**kwargs)
    monkeypatch.setattr(httpx.Client,"request",guarded_sync)
    original = httpx.AsyncClient.request
    async def guarded(self, *args, **kwargs):
        if not isinstance(self._transport, httpx.MockTransport):
            raise AssertionError("Live HTTP is forbidden in pytest; use MockTransport")
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(httpx.AsyncClient, "request", guarded)

@pytest.fixture(autouse=True)
def configured_test_auth(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(),"supabase_jwt_secret","offline-test-jwt-secret-not-for-deployment")

@pytest.fixture(autouse=True)
def explicit_mock_collector(monkeypatch):
    from app.collectors.registry import registry
    from app.collectors.mock import MockCollector
    monkeypatch.setitem(registry._adapters,"mock",MockCollector())
