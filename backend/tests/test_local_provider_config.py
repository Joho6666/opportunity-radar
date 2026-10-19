"""界面内 Provider 配置：密钥掩码、私密落盘、免重启生效、预算上限、测试连接。"""
import asyncio
import json
import stat

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_repository
from app.api.local import router as local_router
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.core.security import CurrentUser
from app.repositories.memory import MemoryRepository

USER = "11111111-1111-4111-8111-111111111111"
# 仅用于测试的占位密钥，不代表任何真实凭据。
FAKE_KEY = "sk-localtest-abcdefghijklmnopqrst-9341"
ENV_KEY = "sk-env-existing-key-0000"


def api_client(repo, uid=USER):
    api = FastAPI()
    api.include_router(local_router)
    api.add_exception_handler(AppError, app_error_handler)
    api.dependency_overrides[get_current_user] = lambda: CurrentUser(id=uid)
    api.dependency_overrides[get_repository] = lambda: repo
    return TestClient(api)


@pytest.fixture
def provider_path(tmp_path, monkeypatch):
    from app.core import provider_config

    settings = get_settings()
    base = {key: getattr(settings, key) for key in ("tikhub_api_key", "local_manual_tikhub_enabled", "paid_api_enabled", "paid_daily_cost_limit", "paid_daily_request_limit")}
    config_dir = tmp_path / "config"
    config_dir.mkdir(mode=0o700)
    target = config_dir / "provider-config.json"
    monkeypatch.setenv("OR_PROVIDER_CONFIG_PATH", str(target))
    provider_config.reset_provider_overlay_cache()
    yield target
    provider_config.reset_provider_overlay_cache()
    for key, value in base.items():
        setattr(settings, key, value)


def test_saved_key_is_masked_and_private_on_disk(provider_path):
    client = api_client(MemoryRepository())
    saved = client.put("/api/local/providers/tikhub", json={"api_key": FAKE_KEY, "enabled": True})
    assert saved.status_code == 200, saved.text
    state = saved.json()["tikhub"]
    assert state["configured"] is True and state["enabled"] is True and state["key_source"] == "ui"
    assert state["masked_key"] == "sk-***9341"
    assert FAKE_KEY not in saved.text
    assert stat.S_IMODE(provider_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(provider_path.parent.stat().st_mode) == 0o700
    readback = client.get("/api/local/providers")
    assert readback.status_code == 200
    assert FAKE_KEY not in readback.text
    assert readback.json()["tikhub"]["masked_key"] == "sk-***9341"
    assert readback.json()["tikhub"]["restart_required"] is False
    # 落盘文件（0600）保存明文，是唯一保存位置；接口任何响应都不回传明文。
    assert json.loads(provider_path.read_text())["tikhub_api_key"] == FAKE_KEY


def test_key_and_budget_take_effect_without_service_restart(provider_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "local")
    client = api_client(MemoryRepository())
    assert client.put("/api/local/providers/tikhub", json={"api_key": FAKE_KEY, "enabled": True}).status_code == 200
    budget = client.put("/api/local/providers/tikhub/budget", json={"single_run_limit_usd": 0.05, "daily_limit_usd": 0.5, "daily_request_limit": 10, "confirm_required": False})
    assert budget.status_code == 200, budget.text
    assert budget.json()["tikhub"]["budgets"] == {"single_run_limit_usd": 0.05, "daily_limit_usd": 0.5, "daily_request_limit": 10, "confirm_required": False}
    effective = get_settings()  # 新的 get_settings() 调用立即拿到新配置，无需重启进程
    assert effective.tikhub_api_key == FAKE_KEY
    assert effective.paid_api_enabled is True and effective.local_manual_tikhub_enabled is True
    assert effective.paid_daily_cost_limit == 0.5
    assert effective.paid_daily_request_limit == 10
    listed = client.get("/api/local/providers").json()["tikhub"]["budgets"]
    assert listed["daily_limit_usd"] == 0.5 and listed["confirm_required"] is False


@pytest.mark.parametrize("body", [
    {"daily_limit_usd": 1.5},
    {"daily_limit_usd": 0},
    {"daily_limit_usd": -1},
    {"daily_request_limit": 21},
    {"daily_request_limit": 0},
    {"single_run_limit_usd": 1.5},
    {"single_run_limit_usd": 0.2, "daily_limit_usd": 0.1},
    {"confirm_required": "yes"},
    {"unknown_field": 1},
])
def test_budget_bounds_rejected_and_nothing_written(provider_path, body):
    client = api_client(MemoryRepository())
    response = client.put("/api/local/providers/tikhub/budget", json=body)
    assert response.status_code == 422, response.text
    assert not provider_path.exists()


@pytest.mark.parametrize("key", ["short", "has space 12345678", "x" * 201, 12345, ""])
def test_invalid_key_rejected(provider_path, key):
    client = api_client(MemoryRepository())
    response = client.put("/api/local/providers/tikhub", json={"api_key": key})
    assert response.status_code == 422, response.text
    assert not provider_path.exists()


def test_delete_masks_existing_env_key_and_stops_paid_calls(provider_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(settings, "tikhub_api_key", ENV_KEY)
    monkeypatch.setattr(settings, "local_manual_tikhub_enabled", True)
    monkeypatch.setattr(settings, "paid_api_enabled", True)
    client = api_client(MemoryRepository())
    listed = client.get("/api/local/providers").json()["tikhub"]
    assert listed["key_source"] == "env" and listed["configured"] is True
    assert listed["masked_key"] == "sk-***0000" and ENV_KEY not in json.dumps(listed)
    removed = client.delete("/api/local/providers/tikhub")
    assert removed.status_code == 200, removed.text
    after = client.get("/api/local/providers").json()["tikhub"]
    assert after["configured"] is False and after["key_source"] == "none" and after["masked_key"] == ""
    assert get_settings().tikhub_api_key == "" and get_settings().paid_api_enabled is False


def test_budget_only_update_keeps_env_key_effective(provider_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "local")
    monkeypatch.setattr(settings, "tikhub_api_key", ENV_KEY)
    client = api_client(MemoryRepository())
    assert client.put("/api/local/providers/tikhub/budget", json={"daily_request_limit": 5}).status_code == 200
    listed = client.get("/api/local/providers").json()["tikhub"]
    assert listed["key_source"] == "env" and listed["configured"] is True
    assert get_settings().tikhub_api_key == ENV_KEY  # 只调预算不得吞掉 local.env 密钥
    assert get_settings().paid_daily_request_limit == 5


def test_connection_endpoint_records_result_without_leaking_key(provider_path, monkeypatch):
    client = api_client(MemoryRepository())
    assert client.put("/api/local/providers/tikhub", json={"api_key": FAKE_KEY, "enabled": True}).status_code == 200
    calls = {}

    async def fake_verify(api_key, base_url, **kwargs):
        calls["key"], calls["base"] = api_key, base_url
        return {"ok": True, "http_status": 200, "latency_ms": 42, "tested_at": "2026-10-16T00:00:00+00:00", "message": "连接成功"}

    monkeypatch.setattr("app.api.local.verify_tikhub_key", fake_verify)
    response = client.post("/api/local/providers/tikhub/test")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and body["http_status"] == 200 and body["persisted"] is True
    assert body["masked_key"] == "sk-***9341" and FAKE_KEY not in response.text
    assert calls["key"] == FAKE_KEY and calls["base"] == get_settings().tikhub_base_url
    stored = client.get("/api/local/providers").json()["tikhub"]["last_test"]
    assert stored["http_status"] == 200 and stored["message"] == "连接成功"


def test_connection_requires_a_key(provider_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tikhub_api_key", "")
    response = api_client(MemoryRepository()).post("/api/local/providers/tikhub/test")
    assert response.status_code == 409, response.text


def test_verify_uses_official_light_endpoint_and_never_echoes_body():
    from app.services import provider_verify

    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "user_data": {"balance_exact": "1.0"}})

    result = asyncio.run(provider_verify.verify_tikhub_key(FAKE_KEY, "https://api.tikhub.io", transport=httpx.MockTransport(handler)))
    assert len(requests) == 1  # 不重试
    assert str(requests[0].url) == "https://api.tikhub.io/api/v1/tikhub/user/get_user_info"
    assert requests[0].headers.get("authorization") == f"Bearer {FAKE_KEY}"
    assert result["ok"] is True and result["http_status"] == 200 and result["latency_ms"] >= 0
    assert FAKE_KEY not in json.dumps(result)

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": 401, "message": "invalid key", "echo": FAKE_KEY})

    failed = asyncio.run(provider_verify.verify_tikhub_key(FAKE_KEY, "https://api.tikhub.io", transport=httpx.MockTransport(unauthorized)))
    assert failed["ok"] is False and failed["http_status"] == 401
    assert FAKE_KEY not in json.dumps(failed) and "401" in failed["message"]


def test_placeholders_are_explicitly_unavailable(provider_path):
    body = api_client(MemoryRepository()).get("/api/local/providers").json()
    ids = {item["id"]: item for item in body["placeholders"]}
    assert ids["firecrawl"]["available"] is False and ids["llm"]["available"] is False
    assert "未接入" in ids["firecrawl"]["status"] and "未接入" in ids["llm"]["status"]
    assert body["restart_required"] is False
