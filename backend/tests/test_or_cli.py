"""scripts/or CLI：退出码、--json 可解析、令牌掩码（离线；只用标准库本地服务器）。"""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "scripts" / "or"
TOKEN = "or_agent_clitest0123456789abcdefghijklmn"


class _Handler(BaseHTTPRequestHandler):
    server_version = "fake-agent-api"

    def log_message(self, *args):  # 静默
        pass

    def _respond(self):
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        record = {"method": self.command, "path": self.path, "headers": {key.lower(): value for key, value in self.headers.items()}, "body": raw.decode("utf-8") if raw else ""}
        self.server.records.append(record)
        route = self.server.routes.get(f"{self.command} {self.path.split('?')[0]}")
        if route is None:
            status, payload = 404, {"error": {"code": "NOT_FOUND", "message": "未找到。"}}
        elif callable(route):
            status, payload = route(record)
        else:
            status, payload = route
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = _respond


class FakeApi:
    def __init__(self, routes):
        self.routes = routes
        self.records = []
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.httpd.routes = routes
        self.httpd.records = self.records
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    monkeypatch.delenv("OR_AGENT_TOKEN", raising=False)
    config = tmp_path / "config"
    config.mkdir(mode=0o700)
    monkeypatch.setenv("LOCAL_PRIVATE_CONFIG_DIR", str(config))
    monkeypatch.setenv("OR_AGENT_TOKEN_PATH", str(config / "agent-token.json"))
    (config / "agent-token.json").write_text(json.dumps({"token": TOKEN, "created_at": "2026-10-16T00:00:00Z", "updated_at": "2026-10-16T00:00:00Z", "rotations": 1}))
    os.chmod(config / "agent-token.json", 0o600)
    return config


def run_cli(*args, env=None):
    environment = {key: value for key, value in os.environ.items() if key not in ("OR_AGENT_TOKEN", "OR_AGENT_API_BASE")}
    environment.update(env or {})
    return subprocess.run([sys.executable, str(CLI), *args], capture_output=True, text=True, env=environment, timeout=60)


def test_sources_json_and_table(api_env):
    payload = {"items": [{"id": "xiaohongshu", "name": "小红书", "available": True, "status": "可运行 · 已实测", "provider": "tikhub", "live_verified": True, "price_usd": 0.01}], "platform_count": 14, "catalog_version": "V5.3.2"}
    with FakeApi({"GET /api/agent/sources": (200, payload)}) as api:
        result = run_cli("sources", "--json", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert result.returncode == 0, result.stderr
        body = json.loads(result.stdout)
        assert body["ok"] is True and body["data"]["platform_count"] == 14
        assert api.records[0]["headers"]["authorization"] == f"Bearer {TOKEN}"
        assert api.records[0]["headers"]["x-request-id"]

        table = run_cli("sources", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert table.returncode == 0
        assert "小红书" in table.stdout and "平台目录" in table.stdout
        assert TOKEN not in table.stdout


def test_run_requires_confirm_client_side(api_env):
    with FakeApi({}) as api:
        result = run_cli("run", "radar-1", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert result.returncode == 2
        assert "--confirm" in result.stderr
        assert api.records == []


def test_run_with_confirm_sends_idempotency_key(api_env):
    payload = {"run": {"id": "run-1", "radar_id": "radar-1", "status": "queued"}, "billing": {"allow_scheduled": False, "single_run_limit_usd": 0.1, "daily_limit_usd": 1.0, "daily_request_limit": 20}}
    with FakeApi({"POST /api/agent/radars/radar-1/run": (202, payload)}) as api:
        result = run_cli("run", "radar-1", "--confirm", "--json", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert result.returncode == 0, result.stderr
        body = json.loads(result.stdout)
        assert body["http_status"] == 202 and body["data"]["run"]["id"] == "run-1"
        record = api.records[0]
        assert json.loads(record["body"]) == {"confirm": True}
        assert len(record["headers"]["idempotency-key"]) >= 8
        assert record["headers"]["content-type"].startswith("application/json")


def test_new_builds_lead_hunt_payload(api_env):
    route = {"POST /api/agent/radars": (201, {"radar": {"id": "radar-9", "name": "agent链路验证", "keywords": ["电商 视频 外包"], "sources": ["xiaohongshu"], "freshness_hours": 168, "hunt_conditions": {"match_mode": "remote"}}})}
    with FakeApi(route) as api:
        result = run_cli("new", "--name", "agent链路验证", "--business", "video", "--keywords", "电商 视频 外包", "--sources", "xiaohongshu", "--hours", "168", "--match-mode", "remote", "--json", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert result.returncode == 0, result.stderr
        sent = json.loads(api.records[0]["body"])
        assert sent["name"] == "agent链路验证"
        assert sent["mode"] == "general" and sent["frequency"] == "manual" and sent["local_schedule_enabled"] is False
        assert sent["keywords"] == ["电商 视频 外包"] and sent["sources"] == ["xiaohongshu"]
        assert sent["freshness_hours"] == 168
        assert sent["source_config"]["lead_hunt"] == "true"
        conditions = json.loads(sent["source_config"]["hunt_conditions"])
        assert conditions["match_mode"] == "remote" and conditions["regions"] == []
        assert sent["collection_policy"]["time_basis"] == "published" and sent["collection_policy"]["include_unknown_dates"] is False
        assert "电商" in sent["collection_policy"]["required_terms"]


def test_usage_errors_exit_2(api_env):
    with FakeApi({}) as api:
        base = ["--api-base", f"http://127.0.0.1:{api.httpd.server_port}"]
        assert run_cli("new", "--keywords", "电商", "--sources", "xiaohongshu", "--hours", "48", *base).returncode == 2
        assert run_cli("new", "--keywords", "a,b,c,d", "--sources", "xiaohongshu", *base).returncode == 2
        assert run_cli("new", "--keywords", "a,b,c", "--sources", "s1,s2,s3", *base).returncode == 2
        assert api.records == []


def test_error_exit_codes(api_env):
    with FakeApi({"GET /api/agent/sources": (401, {"error": {"code": "AGENT_TOKEN_INVALID", "message": "Token 无效"}})}) as api:
        result = run_cli("sources", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert result.returncode == 3
        assert "AGENT_TOKEN_INVALID" in result.stderr

    with FakeApi({"POST /api/agent/radars/radar-1/run": (429, {"error": {"code": "PAID_QUOTA_EXHAUSTED", "message": "今日预算已用完"}})}) as api:
        result = run_cli("run", "radar-1", "--confirm", "--json", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert result.returncode == 4
        assert json.loads(result.stdout)["error"]["code"] == "PAID_QUOTA_EXHAUSTED"

    with FakeApi({"PUT /api/agent/identity": (422, {"error": {"code": "VALIDATION_ERROR", "message": "参数无效"}})}) as api:
        identity_file = Path(api_env) / "identity.json"
        identity_file.write_text(json.dumps({"service_mode": "??"}))
        result = run_cli("identity", "--set-file", str(identity_file), "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert result.returncode == 2

    with FakeApi({}) as api:
        result = run_cli("sources", "--api-base", f"http://127.0.0.1:{api.httpd.server_port - 1 if api.httpd.server_port > 1 else 1}", "--timeout", "2")
        assert result.returncode in (1, 3)


def test_token_command_shows_mask_only(api_env):
    with FakeApi({"GET /api/agent/identity": (200, {"identity": None, "presets": {}})}) as api:
        result = run_cli("token", "--json", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert result.returncode == 0, result.stderr
        body = json.loads(result.stdout)
        assert body["data"]["configured"] is True and body["data"]["valid"] is True
        assert body["data"]["masked_token"].endswith(TOKEN[-4:]) and "***" in body["data"]["masked_token"]
        assert TOKEN not in result.stdout

        human = run_cli("token", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert human.returncode == 0
        assert TOKEN not in human.stdout and "***" in human.stdout


def test_token_missing_exits_3(api_env, tmp_path):
    empty = tmp_path / "empty-config"
    empty.mkdir()
    env = {"OR_AGENT_TOKEN_PATH": str(empty / "agent-token.json"), "LOCAL_PRIVATE_CONFIG_DIR": str(empty)}
    with FakeApi({}) as api:
        result = run_cli("sources", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}", env=env)
        assert result.returncode == 3
        assert "AGENT_TOKEN_MISSING" in result.stderr


def test_results_json_and_table(api_env):
    payload = {"items": [{"evidence_id": "e1", "source": "xiaohongshu", "title": "找外包做电商视频", "url": "https://www.xiaohongshu.com/explore/1", "published_at": "2026-10-15T03:00:00Z", "published_at_shanghai": "2026-10-15T11:00:00+08:00", "raw_text": "找人做电商视频", "match": {"status": "strict", "label": "严格匹配", "score": 92}}], "page": {"limit": 20, "offset": 0, "count": 1, "has_more": False}}
    with FakeApi({"GET /api/agent/radars/radar-1/results": (200, payload)}) as api:
        result = run_cli("results", "radar-1", "--json", "--limit", "5", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["data"]["items"][0]["evidence_id"] == "e1"
        assert "limit=5" in api.records[0]["path"]

        table = run_cli("results", "radar-1", "--status", "strict", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert table.returncode == 0
        assert "严格匹配" in table.stdout and "https://www.xiaohongshu.com/explore/1" in table.stdout


def test_status_and_key_test(api_env):
    routes = {
        "GET /api/agent/billing/status": (200, {"paid_api_enabled": True, "requests_today": 3, "reserved_cost_usd": 0.03, "consumed_cost_usd": 0.03, "account_remaining_requests": 17, "account_remaining_cost_usd": 0.97, "authorizations": [{"scope": "radar-1", "enabled": True, "allow_scheduled": False, "remaining_requests": 17, "remaining_cost_usd": 0.97}]}),
        "POST /api/agent/provider/test": (200, {"ok": True, "http_status": 200, "latency_ms": 90, "tested_at": "2026-10-16T00:00:00Z", "tested_at_shanghai": "2026-10-16T08:00:00+08:00", "message": "连接成功", "masked_key": "abc***5678", "key_source": "ui"}),
    }
    with FakeApi(routes) as api:
        status = run_cli("status", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert status.returncode == 0 and "今日请求：3" in status.stdout
        tested = run_cli("key", "test", "--api-base", f"http://127.0.0.1:{api.httpd.server_port}")
        assert tested.returncode == 0 and "abc***5678" in tested.stdout
