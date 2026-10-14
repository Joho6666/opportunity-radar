"""Persistent manual-request identity and tenant-bound provider continuations."""
import json
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from ..core.errors import AppError
from ..repositories.postgres import as_uuid


def claim_request(repo, user_id: str, request_id: str, fingerprint: str):
    if not hasattr(repo, "engine"):
        raise AppError("REQUEST_PERSISTENCE_REQUIRED", "幂等采集需要 PostgreSQL。", 409)
    repo.get_profile(user_id)
    params = {"uid": as_uuid(user_id), "id": request_id, "fingerprint": fingerprint}
    with repo.engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:uid,0))"), params)
        row = conn.execute(text("SELECT fingerprint,status,result FROM collection_requests WHERE user_id=CAST(:uid AS uuid) AND id=:id"), params).mappings().first()
        if row:
            if row["fingerprint"] != fingerprint:
                raise AppError("REQUEST_ID_CONFLICT", "同一请求标识不能更换关键词、来源或分页。", 409)
            if row["status"] == "succeeded":
                return row["result"]
            if row["status"] == "failed":
                failure = row["result"]
                raise AppError(failure["code"], failure["message"], failure["status_code"])
            raise AppError("COLLECTION_IN_PROGRESS", "该请求正在执行或需人工恢复；不会重复发起付费请求。", 409)
        conn.execute(text("INSERT INTO collection_requests(id,user_id,fingerprint) VALUES(:id,CAST(:uid AS uuid),:fingerprint)"), params)
    return None


def finish_request(repo, user_id: str, request_id: str, result: dict, *, failed: bool = False):
    with repo.engine.begin() as conn:
        conn.execute(text("UPDATE collection_requests SET status=:status,result=CAST(:result AS jsonb) WHERE user_id=CAST(:uid AS uuid) AND id=:id AND status='running'"),
                     {"uid": as_uuid(user_id), "id": request_id, "status": "failed" if failed else "succeeded", "result": json.dumps(jsonable_encoder(result), ensure_ascii=False)})


def issue_cursor(repo, user_id: str, source: str, query: str, state: str | None) -> str | None:
    if not state:
        return None
    if not hasattr(repo, "engine"):
        raise AppError("CURSOR_PERSISTENCE_REQUIRED", "来源分页需要 PostgreSQL。", 409)
    cursor = str(uuid4())
    with repo.engine.begin() as conn:
        conn.execute(text("INSERT INTO collector_cursors(id,user_id,source,query,state) VALUES(:id,CAST(:uid AS uuid),:source,:query,CAST(:state AS jsonb))"),
                     {"id": cursor, "uid": as_uuid(user_id), "source": source, "query": query, "state": json.dumps({"cursor": state})})
    return cursor


def resolve_cursor(repo, user_id: str, source: str, query: str, cursor: str) -> str:
    if not hasattr(repo, "engine"):
        raise AppError("INVALID_CURSOR", "分页标识不可用。", 400)
    with repo.engine.connect() as conn:
        state = conn.execute(text("SELECT state FROM collector_cursors WHERE id=:id AND user_id=CAST(:uid AS uuid) AND source=:source AND query=:query AND expires_at>now()"),
                             {"id": cursor, "uid": as_uuid(user_id), "source": source, "query": query}).scalar_one_or_none()
    if not state:
        raise AppError("INVALID_CURSOR", "分页已过期或不属于当前来源、关键词和账户。", 400)
    return state["cursor"]
