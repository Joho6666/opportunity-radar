"""Agent 专用本地 API：Bearer token 鉴权、幂等、预算与结果分页（离线契约测试）。"""
import json
import stat
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.api.agent import agent_request_validation_handler
from app.api.agent import router as agent_router
from app.api.deps import get_current_user, get_repository
from app.api.local import router as local_router
from app.core import agent_token as agent_token_module
from app.core.config import get_settings
from app.core.errors import AppError, app_error_handler
from app.core.security import CurrentUser
from app.repositories.memory import MemoryRepository
from app.schemas.collection import CollectionPolicy
from app.schemas.domain import RadarCreate
from app.services.evidence_ingest import EvidenceBatch, EvidenceInput

USER = "11111111-1111-4111-8111-111111111111"
HOST = "127.0.0.1:8015"
TOKEN_PLAINTEXT = "or_agent_" + "testtoken0" * 4


def _settings(monkeypatch, **overrides):
    settings = get_settings()
    values = {"app_env": "local", "local_api_port": 8015, "local_user_id": USER, "local_proxy_token": "a" * 64, "auth_disabled": False}
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)
    return settings


@pytest.fixture
def token_path(tmp_path, monkeypatch):
    path = tmp_path / "config" / "agent-token.json"
    monkeypatch.setenv("OR_AGENT_TOKEN_PATH", str(path))
    agent_token_module.reset_agent_token_cache()
    yield path
    agent_token_module.reset_agent_token_cache()


def write_token(path, token=TOKEN_PLAINTEXT):
    agent_token_module.write_agent_token(agent_token_module.AgentTokenConfig(token=token, created_at="2026-10-16T00:00:00Z", updated_at="2026-10-16T00:00:00Z"), path)
    return token


def agent_client(repo, *, client_host="127.0.0.1"):
    api = FastAPI()
    api.include_router(agent_router)
    api.include_router(local_router)
    api.add_exception_handler(AppError, app_error_handler)
    api.add_exception_handler(RequestValidationError, agent_request_validation_handler)
    api.dependency_overrides[get_repository] = lambda: repo
    api.dependency_overrides[get_current_user] = lambda: CurrentUser(id=USER, email="local@opportunity-radar")
    return TestClient(api, client=(client_host, 51234))


def call(client, method, path, *, token=None, headers=None, json_body=None, client_host=None):
    request_headers = {"host": HOST, **(headers or {})}
    if token is not None:
        request_headers["Authorization"] = f"Bearer {token}"
    return client.request(method.upper(), path, headers=request_headers, json=json_body)


def make_radar(repo, name="agent链路验证", keywords=None, sources=None):
    return repo.create_radar(USER, RadarCreate(
        name=name,
        goal="寻找需要AI 电商视频 / 广告服务的买方公开需求",
        mode="general",
        frequency="manual",
        freshness_hours=168,
        keywords=keywords if keywords is not None else ["电商 视频 外包"],
        sources=sources if sources is not None else ["xiaohongshu"],
        source_config={"lead_hunt": "true", "business": "video", "freshness_hours": "168", "hunt_conditions": json.dumps({"regions": [], "roles": [], "intents": [], "match_mode": "remote"})},
        collection_policy=CollectionPolicy(required_terms=["电商", "视频", "广告"], time_basis="published", include_unknown_dates=False),
    ))


def seed_evidence(repo, radar_id, *, status, score, published_at, external_id, url, raw_text="正文内容示例" * 4):
    batch = EvidenceBatch(batch_id=f"batch-{external_id}", items=[EvidenceInput(source="xiaohongshu", url=url, raw_text=raw_text, external_id=external_id, published_at=published_at)])
    records = repo.upsert_evidence_batch(USER, batch).records
    evidence_id = records[0].evidence_id
    repo.link_evidence_to_radar(USER, radar_id, evidence_id, "run-1", score, ["命中业务词"], {"hunt_match": {"status": status, "evidence": {"业务": "电商"}, "missing": [], "conflicts": [], "evidence_level": "完整正文（规则核验）", "match_mode": "remote"}})
    return evidence_id


@pytest.fixture
def env(token_path, monkeypatch):
    _settings(monkeypatch)
    from app.core import agent_idempotency
    agent_idempotency.reset_agent_idempotency_store()
    yield token_path
    agent_idempotency.reset_agent_idempotency_store()


# ---- 鉴权：不回退本机会话 ----

def test_missing_or_wrong_token_is_rejected_without_session_fallback(env):
    repo = MemoryRepository()
    client = agent_client(repo)
    response = call(client, "get", "/api/agent/sources")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AGENT_TOKEN_REQUIRED"
    assert "error" in response.json() and response.json()["error"]["message"]

    # 即使带着本机代理凭据（网页会话链路的凭据）也必须继续要求 token。
    proxied = call(client, "get", "/api/agent/sources", headers={"x-or-local-proxy": "a" * 64})
    assert proxied.status_code == 401
    assert proxied.json()["error"]["code"] == "AGENT_TOKEN_REQUIRED"

    wrong = call(client, "get", "/api/agent/sources", token="or_agent_wrong")
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "AGENT_TOKEN_INVALID"

    write_token(env)
    ok = call(client, "get", "/api/agent/sources", token=TOKEN_PLAINTEXT)
    assert ok.status_code == 200


def test_non_loopback_or_proxied_requests_are_rejected(env):
    write_token(env)
    repo = MemoryRepository()
    remote = call(agent_client(repo, client_host="192.0.2.9"), "get", "/api/agent/sources", token=TOKEN_PLAINTEXT)
    assert remote.status_code == 403
    assert remote.json()["error"]["code"] == "AGENT_LOCAL_ONLY"

    forwarded = call(agent_client(repo), "get", "/api/agent/sources", token=TOKEN_PLAINTEXT, headers={"x-forwarded-for": "127.0.0.1"})
    assert forwarded.status_code == 403
    assert forwarded.json()["error"]["code"] == "AGENT_LOCAL_ONLY"

    bad_host = call(agent_client(repo), "get", "/api/agent/sources", token=TOKEN_PLAINTEXT, headers={"host": "evil.example"})
    assert bad_host.status_code == 403

    localhost = call(agent_client(repo), "get", "/api/agent/sources", token=TOKEN_PLAINTEXT, headers={"host": "localhost:8015"})
    assert localhost.status_code == 200


def test_agent_api_is_local_edition_only(env, monkeypatch):
    write_token(env)
    monkeypatch.setattr(get_settings(), "app_env", "production")
    response = call(agent_client(MemoryRepository()), "get", "/api/agent/sources", token=TOKEN_PLAINTEXT)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AGENT_API_LOCAL_ONLY"


# ---- token 管理：掩码、一次性明文、热加载、吊销 ----

def test_token_management_masks_plaintext_and_keeps_private_file(env):
    repo = MemoryRepository()
    client = agent_client(repo)
    created = call(client, "post", "/api/local/agent-token", json_body={})
    assert created.status_code == 201
    body = created.json()
    plaintext = body["plaintext"]
    assert plaintext.startswith("or_agent_")
    assert body["masked_token"].startswith("or_agent_")
    assert "***" in body["masked_token"] and plaintext not in body["masked_token"]
    assert plaintext in env.read_text()

    assert stat.S_IMODE(env.stat().st_mode) == 0o600
    assert stat.S_IMODE(env.parent.stat().st_mode) == 0o700

    read_back = call(client, "get", "/api/local/agent-token")
    assert read_back.status_code == 200
    assert read_back.json()["configured"] is True
    assert plaintext not in read_back.text
    assert read_back.json()["masked_token"] == body["masked_token"]

    live = call(client, "get", "/api/agent/identity", token=plaintext)
    assert live.status_code == 200

    revoked = call(client, "delete", "/api/local/agent-token")
    assert revoked.status_code == 200
    assert revoked.json()["configured"] is False
    assert not env.exists()
    dead = call(client, "get", "/api/agent/identity", token=plaintext)
    assert dead.status_code == 401


def test_token_rotation_applies_without_restart(env):
    repo = MemoryRepository()
    client = agent_client(repo)
    first = call(client, "post", "/api/local/agent-token", json_body={}).json()["plaintext"]
    assert call(client, "get", "/api/agent/sources", token=first).status_code == 200
    second = call(client, "post", "/api/local/agent-token", json_body={}).json()["plaintext"]
    assert second != first
    assert call(client, "get", "/api/agent/sources", token=first).status_code == 401
    assert call(client, "get", "/api/agent/sources", token=second).status_code == 200


# ---- 幂等与确认 ----

def test_writes_require_idempotency_key_and_replay_safely(env):
    token = write_token(env)
    repo = MemoryRepository()
    client = agent_client(repo)
    payload = {"name": "agent链路验证", "goal": "寻找需要AI 电商视频 / 广告服务的买方公开需求", "mode": "general", "keywords": ["电商 视频 外包"], "sources": ["xiaohongshu"], "freshness_hours": 168}

    missing = call(client, "post", "/api/agent/radars", token=token, json_body=payload)
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"

    key = "radar-create-0001-abcdef"
    first = call(client, "post", "/api/agent/radars", token=token, headers={"Idempotency-Key": key}, json_body=payload)
    assert first.status_code == 201
    radar_id = first.json()["radar"]["id"]
    assert first.headers.get("Idempotency-Replayed") == "false"

    replay = call(client, "post", "/api/agent/radars", token=token, headers={"Idempotency-Key": key}, json_body=payload)
    assert replay.status_code == 201
    assert replay.json()["radar"]["id"] == radar_id
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert len(repo.list_radars(USER)) == 1

    conflict = call(client, "post", "/api/agent/radars", token=token, headers={"Idempotency-Key": key}, json_body={**payload, "name": "另一个名字"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_run_requires_explicit_confirm_and_replays_without_second_run(env):
    token = write_token(env)
    repo = MemoryRepository()
    client = agent_client(repo)
    radar = make_radar(repo)

    refused = call(client, "post", f"/api/agent/radars/{radar.id}/run", token=token, headers={"Idempotency-Key": "run-key-0001-abcdef"}, json_body={})
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "CONFIRM_REQUIRED"
    assert repo.runs_of_user(USER) == []

    explicit_false = call(client, "post", f"/api/agent/radars/{radar.id}/run", token=token, headers={"Idempotency-Key": "run-key-0001-abcdef"}, json_body={"confirm": False})
    assert explicit_false.status_code == 400
    assert explicit_false.json()["error"]["code"] == "CONFIRM_REQUIRED"

    first = call(client, "post", f"/api/agent/radars/{radar.id}/run", token=token, headers={"Idempotency-Key": "run-key-0001-abcdef"}, json_body={"confirm": True})
    assert first.status_code == 202
    run_id = first.json()["run"]["id"]
    assert first.json()["run"]["radar_id"] == radar.id

    replay = call(client, "post", f"/api/agent/radars/{radar.id}/run", token=token, headers={"Idempotency-Key": "run-key-0001-abcdef"}, json_body={"confirm": True})
    assert replay.status_code == 202
    assert replay.json()["run"]["id"] == run_id
    assert replay.headers.get("Idempotency-Replayed") == "true"
    assert len(repo.runs_of_user(USER)) == 1


def test_run_response_declares_manual_only_budget_scope(env):
    token = write_token(env)
    repo = MemoryRepository()
    client = agent_client(repo)
    radar = make_radar(repo)
    response = call(client, "post", f"/api/agent/radars/{radar.id}/run", token=token, headers={"Idempotency-Key": "run-key-0002-abcdef"}, json_body={"confirm": True})
    assert response.status_code == 202
    billing = response.json()["billing"]
    assert billing["allow_scheduled"] is False
    assert billing["confirm_required"] is True
    assert 0 < billing["single_run_limit_usd"] <= 0.1
    assert billing["daily_request_limit"] <= 20


# ---- 结果读取 ----

def _seed_results(repo, radar):
    base = datetime(2026, 10, 15, 3, 0, tzinfo=UTC)
    rows = [
        ("strict", 92, base),
        ("pending", 81, base + timedelta(hours=1)),
        ("mismatch", 55, base + timedelta(hours=2)),
        ("strict", 92, base + timedelta(hours=3)),
        ("pending", 70, base + timedelta(hours=4)),
    ]
    for index, (status, score, published) in enumerate(rows):
        seed_evidence(repo, radar.id, status=status, score=score, published_at=published, external_id=f"xhs-{index}", url=f"https://www.xiaohongshu.com/explore/{index}")
    return rows


def test_results_are_paginated_sorted_and_filterable(env):
    token = write_token(env)
    repo = MemoryRepository()
    client = agent_client(repo)
    radar = make_radar(repo)
    _seed_results(repo, radar)

    page_one = call(client, "get", f"/api/agent/radars/{radar.id}/results?limit=2&offset=0", token=token).json()
    assert len(page_one["items"]) == 2 and page_one["page"]["has_more"] is True
    assert [item["match"]["score"] for item in page_one["items"]] == [92, 92]

    page_two = call(client, "get", f"/api/agent/radars/{radar.id}/results?limit=2&offset=2", token=token).json()
    page_three = call(client, "get", f"/api/agent/radars/{radar.id}/results?limit=2&offset=4", token=token).json()
    ids = [item["evidence_id"] for item in page_one["items"] + page_two["items"] + page_three["items"]]
    assert len(set(ids)) == 5
    assert page_three["page"]["has_more"] is False

    strict = call(client, "get", f"/api/agent/radars/{radar.id}/results?status=strict", token=token).json()
    assert {item["match"]["status"] for item in strict["items"]} == {"strict"}
    assert strict["page"]["count"] == 2 and strict["page"]["has_more"] is False

    bounded = call(client, "get", f"/api/agent/radars/{radar.id}/results?limit=1000", token=token)
    assert bounded.status_code == 422


def test_results_expose_link_and_publish_time_in_utc_and_shanghai(env):
    token = write_token(env)
    repo = MemoryRepository()
    client = agent_client(repo)
    radar = make_radar(repo)
    _seed_results(repo, radar)
    item = call(client, "get", f"/api/agent/radars/{radar.id}/results?status=strict&limit=1", token=token).json()["items"][0]
    assert item["url"].startswith("https://www.xiaohongshu.com/")
    assert item["published_at"] == "2026-10-15T03:00:00Z"
    assert item["published_at_shanghai"] == "2026-10-15T11:00:00+08:00"
    assert item["captured_at_shanghai"].endswith("+08:00")
    assert item["source"] == "xiaohongshu"
    assert item["match"]["hunt_match"]["evidence_level"]
    assert item["raw_text"]


def test_results_unknown_radar_is_404(env):
    token = write_token(env)
    client = agent_client(MemoryRepository())
    assert call(client, "get", "/api/agent/radars/does-not-exist/results", token=token).status_code == 404


# ---- 其余端点 ----

def test_sources_identity_runs_and_billing_endpoints(env):
    token = write_token(env)
    repo = MemoryRepository()
    client = agent_client(repo)
    sources = call(client, "get", "/api/agent/sources", token=token)
    assert sources.status_code == 200
    assert sources.json()["items"] and sources.json()["platform_count"] >= 1

    identity = call(client, "get", "/api/agent/identity", token=token)
    assert identity.status_code == 200
    assert "identity" in identity.json()

    missing_key = call(client, "put", "/api/agent/identity", token=token, json_body={"service_mode": "remote"})
    assert missing_key.status_code == 400
    saved = call(client, "put", "/api/agent/identity", token=token, headers={"Idempotency-Key": "identity-key-0001"}, json_body={"service_mode": "remote"})
    assert saved.status_code == 200
    assert saved.json()["identity"]["service_mode"] == "remote"

    radar = make_radar(repo)
    run = call(client, "post", f"/api/agent/radars/{radar.id}/run", token=token, headers={"Idempotency-Key": "run-key-0003-abcdef"}, json_body={"confirm": True}).json()["run"]
    fetched = call(client, "get", f"/api/agent/runs/{run['id']}", token=token)
    assert fetched.status_code == 200
    assert fetched.json()["run"]["id"] == run["id"]
    assert fetched.json()["run"]["status"] == "queued"

    runs = call(client, "get", "/api/agent/runs?limit=5", token=token)
    assert runs.status_code == 200
    assert any(row["id"] == run["id"] for row in runs.json()["items"])

    billing = call(client, "get", "/api/agent/billing/status", token=token)
    assert billing.status_code == 200
    assert "paid_api_enabled" in billing.json()

    radars = call(client, "get", "/api/agent/radars", token=token)
    assert radars.status_code == 200
    assert any(row["id"] == radar.id for row in radars.json()["items"])
    single = call(client, "get", f"/api/agent/radars/{radar.id}", token=token)
    assert single.status_code == 200
    assert single.json()["radar"]["id"] == radar.id


def test_provider_test_endpoint_never_leaks_plaintext_key(env, tmp_path, monkeypatch):
    token = write_token(env)
    repo = MemoryRepository()
    client = agent_client(repo)
    from app.core import provider_config

    key_path = tmp_path / "config" / "provider-config.json"
    monkeypatch.setenv("OR_PROVIDER_CONFIG_PATH", str(key_path))
    provider_config.reset_provider_overlay_cache()
    provider_config.write_provider_config(provider_config.ProviderConfig(manage_key=True, tikhub_api_key="abcdefgh12345678", tikhub_manual_enabled=True))
    monkeypatch.setattr(get_settings(), "paid_api_enabled", True)
    monkeypatch.setattr(get_settings(), "local_manual_tikhub_enabled", True)

    async def fake_verify(api_key, base_url, **kwargs):
        assert api_key == "abcdefgh12345678" and base_url
        return {"ok": True, "http_status": 200, "latency_ms": 12, "tested_at": datetime.now(UTC).isoformat(), "message": "连接正常（官方用户信息端点，未发起内容采集）。"}

    monkeypatch.setattr("app.api.agent.verify_tikhub_key", fake_verify)

    missing = call(client, "post", "/api/agent/provider/test", token=token, json_body={})
    assert missing.status_code == 400
    result = call(client, "post", "/api/agent/provider/test", token=token, headers={"Idempotency-Key": "provider-test-0001"}, json_body={})
    assert result.status_code == 200
    body = result.json()
    assert body["ok"] is True
    assert "tested_at_shanghai" in body
    assert "abcdefgh12345678" not in result.text
    assert body["masked_key"] == "abc***5678"
    provider_config.reset_provider_overlay_cache()


def test_high_impact_capabilities_are_not_exposed(env):
    token = write_token(env)
    repo = MemoryRepository()
    client = agent_client(repo)
    radar = make_radar(repo)
    for method, path in (
        ("post", f"/api/agent/radars/{radar.id}/dm"),
        ("post", f"/api/agent/radars/{radar.id}/follow"),
        ("post", "/api/agent/scheduler"),
        ("put", f"/api/agent/billing/authorizations/{radar.id}"),
        ("delete", f"/api/agent/billing/authorizations/{radar.id}"),
        ("post", "/api/agent/settings"),
        ("get", "/api/agent/token"),
        ("post", "/api/agent/token"),
        ("get", "/api/agent/keys/tikhub"),
    ):
        response = call(client, method, path, token=token, headers={"Idempotency-Key": "x-0001-abcdef"}, json_body={})
        assert response.status_code in (404, 405), (method, path, response.status_code)
