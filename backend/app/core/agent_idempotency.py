"""Agent 写操作的幂等账本：同一 Idempotency-Key 只执行一次，重放复用首次响应。

- PostgreSQL 持久化（表 agent_idempotency）：进程或请求重启后仍能识别重试。
- 内存仓库（测试/临时模式）使用进程内实现，行为一致。
- 指纹不同但键相同 = 客户端复用了键，返回 409，绝不把两个不同请求混为一次。
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass

from ..core.errors import AppError
from ..repositories.postgres import as_uuid

IDEMPOTENCY_KEY_PATTERN = re.compile(r"[!-~]{8,200}")


@dataclass(frozen=True)
class StoredAgentResponse:
    fingerprint: str
    status_code: int
    body: dict


def require_idempotency_key(headers) -> str:
    key = (headers.get("Idempotency-Key") or "").strip()
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise AppError("IDEMPOTENCY_KEY_REQUIRED", "写操作需要 Idempotency-Key 请求头（8–200 位无空格字符），用于安全重试。", 400)
    return key


def request_fingerprint(*parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class MemoryAgentIdempotencyStore:
    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], StoredAgentResponse] = {}
        self._lock = threading.Lock()

    def get(self, user_id: str, key: str) -> StoredAgentResponse | None:
        with self._lock:
            return self._rows.get((user_id, key))

    def put(self, user_id: str, key: str, fingerprint: str, status_code: int, body: dict) -> None:
        with self._lock:
            self._rows.setdefault((user_id, key), StoredAgentResponse(fingerprint, status_code, body))

    def clear(self) -> None:
        with self._lock:
            self._rows.clear()


class PostgresAgentIdempotencyStore:
    def __init__(self, engine) -> None:
        self._engine = engine

    def get(self, user_id: str, key: str) -> StoredAgentResponse | None:
        from sqlalchemy import text

        with self._engine.begin() as conn:
            row = conn.execute(
                text("SELECT fingerprint, status_code, response_body FROM agent_idempotency WHERE user_id=CAST(:uid AS uuid) AND idempotency_key=:key"),
                {"uid": as_uuid(user_id), "key": key},
            ).mappings().first()
        if not row:
            return None
        return StoredAgentResponse(row["fingerprint"], int(row["status_code"]), dict(row["response_body"]))

    def put(self, user_id: str, key: str, fingerprint: str, status_code: int, body: dict) -> None:
        from sqlalchemy import text

        with self._engine.begin() as conn:
            conn.execute(
                text("INSERT INTO agent_idempotency(user_id, idempotency_key, fingerprint, status_code, response_body) VALUES(CAST(:uid AS uuid), :key, :fingerprint, :status, CAST(:body AS jsonb)) ON CONFLICT(user_id, idempotency_key) DO NOTHING"),
                {"uid": as_uuid(user_id), "key": key, "fingerprint": fingerprint, "status": status_code, "body": json.dumps(body, ensure_ascii=False, default=str)},
            )

    def clear(self) -> None:  # pragma: no cover - 仅供测试/维护
        from sqlalchemy import text

        with self._engine.begin() as conn:
            conn.execute(text("DELETE FROM agent_idempotency"))


_memory_store = MemoryAgentIdempotencyStore()


def reset_agent_idempotency_store() -> None:
    _memory_store.clear()


def store_for(repo) -> MemoryAgentIdempotencyStore | PostgresAgentIdempotencyStore:
    engine = getattr(repo, "engine", None)
    return PostgresAgentIdempotencyStore(engine) if engine is not None else _memory_store


def replay(user_id: str, key: str, fingerprint: str, repo) -> StoredAgentResponse | None:
    """命中已有键：同指纹返回首次响应；不同指纹拒绝（不可把两个请求混为一次）。"""
    stored = store_for(repo).get(user_id, key)
    if stored is None:
        return None
    if stored.fingerprint != fingerprint:
        raise AppError("IDEMPOTENCY_KEY_REUSED", "该 Idempotency-Key 已用于不同的请求内容；请换一个新的键。", 409)
    return stored


def remember(user_id: str, key: str, fingerprint: str, status_code: int, body: dict, repo) -> None:
    store_for(repo).put(user_id, key, fingerprint, status_code, body)
