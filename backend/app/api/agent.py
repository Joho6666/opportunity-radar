"""Agent 专用本地 API（/api/agent）：给 agent 与命令行的机器接口。

安全边界（与网页的本地会话链路完全隔离）：
- 仅 APP_ENV=local 且请求直连 loopback（127.0.0.1 / localhost）时可用；
- 鉴权只认 ``Authorization: Bearer <agent token>``：缺 token、错 token、非本机一律 401/403，
  绝不回退到网页的本地会话或本机代理凭据（避免 CSRF 协同攻击）；
- 写操作必须携带 ``Idempotency-Key``，同一键重放复用首次响应，不会重复建单或重复扣费；
- 付费运行必须显式 ``{"confirm": true}``，并受既有计费网关（预留 + 账本 + 授权行）限制；
  授权行固定 ``allow_scheduled=false``，不开放自动定时付费调度；
- 不提供发私信/评论/关注、修改密钥或会话、改数据库密码等能力；任何密钥只回掩码。
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from ..core import agent_idempotency
from ..core.agent_token import verify_agent_token
from ..core.config import get_settings
from ..core.errors import AppError
from ..core.security import CurrentUser, _is_direct_local_request
from ..repositories.base import Repository
from ..schemas.domain import RadarCreate, RadarRead, RadarRunRead
from ..schemas.identity import IdentityProfile
from ..services.billing_gateway import _micros, paid_context
from ..services.identity_defaults import apply_identity_defaults, identity_defaults_for
from ..services.provider_verify import verify_tikhub_key
from ..workers.queue import enqueue_radar_run
from . import billing as billing_api
from . import local as local_api
from .deps import get_repository
from .local import _provider_state
from .radars import _with_listener_config

router = APIRouter(prefix="/api/agent", tags=["Agent"])

SHANGHAI = timezone(timedelta(hours=8))
MATCH_LABELS = {"strict": "严格匹配", "pending": "待确认", "mismatch": "不匹配", "hiring_signal": "招聘信号"}


async def agent_request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    """Agent 接口的 422 也返回 {error:{code,message}} 结构，便于机器处理。"""
    return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": "请求参数无效：请检查分页上限（默认 20 / 最大 100）与字段类型。"}})


# ---- 鉴权与工具 ----

def utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def shanghai_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(SHANGHAI).isoformat(timespec="seconds")


def _parse(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if 1970 <= parsed.year <= 9999 else None


def with_shanghai_times(payload):
    """时间字段统一为 ISO8601 UTC（Z），并追加同名 *_shanghai 上海时间字段。"""
    if isinstance(payload, list):
        return [with_shanghai_times(item) for item in payload]
    if not isinstance(payload, dict):
        return payload
    result: dict = {}
    for key, value in payload.items():
        processed = with_shanghai_times(value)
        result[key] = processed
        if isinstance(key, str) and key.endswith("_at") and isinstance(processed, str) and processed:
            parsed = _parse(processed)
            if parsed is not None:
                result[key] = utc_iso(parsed)
                result[f"{key}_shanghai"] = shanghai_iso(parsed)
    return result


async def require_agent(request: Request, authorization: str | None = Header(default=None), repo: Repository = Depends(get_repository)) -> CurrentUser:
    """Agent 鉴权：本机 loopback + Bearer token；任何失败都不回退网页会话。"""
    settings = get_settings()
    if settings.app_env.lower() != "local":
        raise AppError("AGENT_API_LOCAL_ONLY", "Agent 接口仅在本机版（Local Edition）可用。", 403)
    allowed_hosts = {f"127.0.0.1:{settings.local_api_port}", f"localhost:{settings.local_api_port}"}
    if not _is_direct_local_request(request) or request.headers.get("host", "").lower() not in allowed_hosts:
        raise AppError("AGENT_LOCAL_ONLY", "Agent 接口只接受 127.0.0.1 直连请求；请勿经代理、端口转发或公网访问。", 403)
    token = authorization.removeprefix("Bearer ").strip() if authorization and authorization.startswith("Bearer ") else ""
    if not token:
        raise AppError("AGENT_TOKEN_REQUIRED", "缺少 Bearer Token：请先在设置页生成 Agent 令牌，再附带 Authorization: Bearer <token>。", 401)
    if not verify_agent_token(token):
        raise AppError("AGENT_TOKEN_INVALID", "Agent 令牌无效或已吊销；请在设置页重新生成。", 401)
    user = CurrentUser(id=str(UUID(settings.local_user_id)), email="agent@opportunity-radar")
    # 与网页路径一致：请求内的付费调用仍走计费网关（scope=assistant），不绕过授权与账簿。
    with paid_context(repo, user.id, "assistant", f"agent-{uuid4()}"):
        yield user


def _begin_write(request: Request, user_id: str, repo, payload, *, path: str) -> tuple[str, str, JSONResponse | None]:
    key = agent_idempotency.require_idempotency_key(request.headers)
    fingerprint = agent_idempotency.request_fingerprint(request.method, path, payload)
    stored = agent_idempotency.replay(user_id, key, fingerprint, repo)
    if stored is None:
        return key, fingerprint, None
    return key, fingerprint, JSONResponse(status_code=stored.status_code, content=stored.body, headers={"Idempotency-Replayed": "true"})


def _finish_write(user_id: str, key: str, fingerprint: str, repo, status_code: int, body: dict) -> JSONResponse:
    agent_idempotency.remember(user_id, key, fingerprint, status_code, body, repo)
    return JSONResponse(status_code=status_code, content=body, headers={"Idempotency-Replayed": "false"})


def radar_payload(radar: RadarRead) -> dict:
    data = radar.model_dump(mode="json")
    raw = data.get("source_config", {}).get("hunt_conditions")
    try:
        conditions = json.loads(raw) if raw else None
    except ValueError:
        conditions = None
    data["lead_hunt"] = data.get("source_config", {}).get("lead_hunt") == "true"
    data["hunt_conditions"] = conditions
    return with_shanghai_times(data)


def run_payload(run: RadarRunRead) -> dict:
    return with_shanghai_times(run.model_dump(mode="json"))


def _manual_budgets() -> dict:
    try:
        return _provider_state()["tikhub"]["budgets"]
    except Exception:  # 配置不可读时退回本机硬上限
        return {"single_run_limit_usd": 0.1, "daily_limit_usd": 1.0, "daily_request_limit": 20, "confirm_required": True}


def _radar_uses_tikhub(radar: RadarRead) -> bool:
    from ..collectors.tikhub_catalog import source_catalog

    providers = {item["id"]: item.get("provider") for item in source_catalog(get_settings())}
    return any(providers.get(slug) == "tikhub" for slug in radar.sources)


def _ensure_manual_authorization(repo, user: CurrentUser, radar: RadarRead) -> dict:
    """与网页“手动运行”一致：为本雷达写入 allow_scheduled=false 的付费授权行（预算沿用界面配置）。"""
    from sqlalchemy import text

    budgets = _manual_budgets()
    limit = max(1, min(6, int(budgets.get("daily_request_limit", 20))))
    info = {
        "provider": "tikhub",
        "authorized": False,
        "allow_scheduled": False,
        "confirm_required": bool(budgets.get("confirm_required", True)),
        "single_run_limit_usd": float(budgets.get("single_run_limit_usd", 0.1)),
        "daily_limit_usd": float(budgets.get("daily_limit_usd", 1.0)),
        "daily_request_limit": int(budgets.get("daily_request_limit", 20)),
        "run_requests": limit,
    }
    settings = get_settings()
    if not (settings.paid_api_enabled and settings.local_manual_tikhub_enabled):
        return info  # 付费关闭：仍允许建单，运行会如实失败，不绕过任何开关
    if not _radar_uses_tikhub(radar):
        return info
    if not hasattr(repo, "engine"):
        raise AppError("BILLING_PERSISTENCE_REQUIRED", "付费授权需要 PostgreSQL 持久化。", 409)
    from ..repositories.postgres import as_uuid

    with repo.engine.begin() as conn:
        conn.execute(
            text("INSERT INTO billing_authorizations(user_id,scope,enabled,providers,allow_scheduled,run_requests,daily_requests,run_micros,daily_micros) VALUES(CAST(:uid AS uuid),:scope,true,CAST(:providers AS jsonb),false,:run_requests,:daily_requests,:run_micros,:daily_micros) ON CONFLICT(user_id,scope) DO UPDATE SET enabled=EXCLUDED.enabled,providers=EXCLUDED.providers,allow_scheduled=false,run_requests=EXCLUDED.run_requests,daily_requests=EXCLUDED.daily_requests,run_micros=EXCLUDED.run_micros,daily_micros=EXCLUDED.daily_micros,updated_at=now()"),
            {"uid": as_uuid(user.id), "scope": radar.id, "providers": json.dumps(["tikhub"]), "run_requests": limit,
             "daily_requests": int(budgets.get("daily_request_limit", 20)), "run_micros": _micros(budgets.get("single_run_limit_usd", 0.1)), "daily_micros": _micros(budgets.get("daily_limit_usd", 1.0))},
        )
    return {**info, "authorized": True}


# ---- 只读端点 ----

@router.get("/sources")
async def sources(user: CurrentUser = Depends(require_agent), repo: Repository = Depends(get_repository)):
    """平台目录与状态（严格按既有来源台账回读，绝不探测 provider）。"""
    payload = await local_api.hunt_sources(user=user, repo=repo)
    return with_shanghai_times(payload)


@router.get("/identity")
async def get_identity(user: CurrentUser = Depends(require_agent), repo: Repository = Depends(get_repository)):
    return await local_api.get_identity(user=user, repo=repo)


@router.get("/radars")
async def list_radars(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_agent),
    repo: Repository = Depends(get_repository),
):
    rows = repo.list_radars(user.id)
    page = rows[offset: offset + limit]
    return with_shanghai_times({"items": [radar_payload(radar) for radar in page], "page": {"limit": limit, "offset": offset, "count": len(page), "total": len(rows), "has_more": len(rows) > offset + limit}})


@router.get("/radars/{radar_id}")
async def get_radar(radar_id: str, user: CurrentUser = Depends(require_agent), repo: Repository = Depends(get_repository)):
    return {"radar": radar_payload(repo.get_radar(user.id, radar_id))}


def _result_items(rows) -> list[dict]:
    items = []
    for record, match in rows:
        ranking = match.get("ranking") or {}
        hunt = ranking.get("hunt_match") or {}
        status = hunt.get("status")
        items.append(with_shanghai_times({
            "evidence_id": record.evidence_id,
            "source": record.source,
            "title": record.metadata.get("raw_title", ""),
            "url": str(record.url),
            "raw_text": record.raw_text,
            "query": record.query,
            "published_at": utc_iso(record.published_at),
            "captured_at": utc_iso(record.captured_at),
            "is_saved": record.is_saved,
            "is_read": record.is_read,
            "match": {
                "status": status,
                "label": MATCH_LABELS.get(status or "", "未分类"),
                "score": match.get("score"),
                "reasons": match.get("reasons") or [],
                "hunt_match": hunt or None,
                "evidence": hunt.get("evidence") or {},
                "missing": hunt.get("missing") or [],
                "conflicts": hunt.get("conflicts") or [],
                "evidence_level": hunt.get("evidence_level"),
                "match_mode": hunt.get("match_mode"),
                "matched_at": utc_iso(match.get("matched_at")) if match.get("matched_at") else None,
                "run_id": str(match["run_id"]) if match.get("run_id") else None,
            },
        }))
    return items


@router.get("/radars/{radar_id}/results")
async def radar_results(
    radar_id: str,
    status: str | None = Query(default=None, pattern="^(strict|pending|mismatch|hiring_signal)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(require_agent),
    repo: Repository = Depends(get_repository),
):
    """严格/待确认/不匹配 + 证据原文 + 原文链接 + 发布时间；分页稳定（相关度 DESC，证据 id ASC）。"""
    repo.get_radar(user.id, radar_id)
    rows = repo.list_radar_results(user.id, radar_id, status=status, limit=limit, offset=offset)
    has_more = len(rows) > limit
    items = _result_items(rows[:limit])
    return {"radar": {"id": radar_id}, "items": items, "page": {"limit": limit, "offset": offset, "count": len(items), "next_offset": offset + limit if has_more else None, "has_more": has_more, "status": status}}


@router.get("/runs")
async def list_runs(
    radar_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: CurrentUser = Depends(require_agent),
    repo: Repository = Depends(get_repository),
):
    floor = datetime(1970, 1, 1, tzinfo=UTC)
    rows = [run for run in repo.runs_of_user(user.id) if radar_id is None or run.radar_id == radar_id]
    rows.sort(key=lambda run: (run.started_at or run.finished_at or floor, run.id), reverse=True)
    page = rows[:limit]
    return {"items": [run_payload(run) for run in page], "page": {"limit": limit, "count": len(page), "total": len(rows), "has_more": len(rows) > limit}}


@router.get("/runs/{run_id}")
async def get_run(run_id: str, user: CurrentUser = Depends(require_agent), repo: Repository = Depends(get_repository)):
    return {"run": run_payload(repo.get_run(user.id, run_id))}


@router.get("/billing/status")
async def billing_status(user: CurrentUser = Depends(require_agent), repo: Repository = Depends(get_repository)):
    """只读预算/账本状态；Agent 接口没有任何修改计费配置的写入口。"""
    return with_shanghai_times(await billing_api.status(user=user, repo=repo))


# ---- 写端点（全部要求 Idempotency-Key） ----

@router.put("/identity")
async def put_identity(value: IdentityProfile, request: Request, user: CurrentUser = Depends(require_agent), repo: Repository = Depends(get_repository)):
    key, fingerprint, replay_response = _begin_write(request, user.id, repo, value.model_dump(mode="json"), path="/api/agent/identity")
    if replay_response is not None:
        return replay_response
    body = {"identity": repo.save_identity(user.id, value).model_dump()}
    return _finish_write(user.id, key, fingerprint, repo, 200, body)


@router.post("/radars", status_code=201)
async def create_radar(payload: RadarCreate, request: Request, user: CurrentUser = Depends(require_agent), repo: Repository = Depends(get_repository)):
    key, fingerprint, replay_response = _begin_write(request, user.id, repo, payload.model_dump(mode="json"), path="/api/agent/radars")
    if replay_response is not None:
        return replay_response
    value = apply_identity_defaults(payload, identity_defaults_for(repo, user.id))
    value = await _with_listener_config(user.id, value, repo)
    try:
        radar = repo.create_radar(user.id, value)
    except ValidationError as exc:  # 身份默认值合并后的二次校验
        raise AppError("IDENTITY_DEFAULTS_INVALID", "身份默认值与本次抓单条件冲突，请检查设置。", 422) from exc
    return _finish_write(user.id, key, fingerprint, repo, 201, {"radar": radar_payload(radar)})


class AgentRunRequest(BaseModel):
    confirm: bool = False


@router.post("/radars/{radar_id}/run", status_code=202)
async def run_radar(radar_id: str, request: Request, payload: AgentRunRequest | None = None, user: CurrentUser = Depends(require_agent), repo: Repository = Depends(get_repository)):
    """手动触发一轮抓取：必须显式 confirm=true；付费仍走既有计费网关与预算上限。"""
    confirmed = bool(payload and payload.confirm is True)
    key, fingerprint, replay_response = _begin_write(request, user.id, repo, {"radar_id": radar_id, "confirm": confirmed}, path=f"/api/agent/radars/{radar_id}/run")
    if replay_response is not None:
        return replay_response
    if not confirmed:
        raise AppError("CONFIRM_REQUIRED", "运行会触发真实付费采集：请求体必须显式包含 {\"confirm\": true}。", 400)
    radar = repo.get_radar(user.id, radar_id)
    billing = _ensure_manual_authorization(repo, user, radar)
    run = repo.create_run(radar_id)
    if run.status == "queued":
        try:
            await enqueue_radar_run(user.id, radar_id, run.id)
        except Exception as exc:
            if get_settings().app_env.lower() != "local":
                raise
            run = repo.save_run(run.model_copy(update={"stage_stats": {**run.stage_stats, "dispatch_status": "waiting_for_redis", "dispatch_error": getattr(exc, "code", "QUEUE_UNAVAILABLE")}}))
    return _finish_write(user.id, key, fingerprint, repo, 202, {"run": run_payload(run), "radar": radar_payload(radar), "billing": billing})


@router.post("/provider/test")
async def provider_test(request: Request, user: CurrentUser = Depends(require_agent), repo: Repository = Depends(get_repository)):
    """连通性测试：只调用官方轻量端点，不采集内容；响应只含掩码，绝不含密钥明文。"""
    from ..core.provider_config import ProviderConfig, effective_key, masked_key, read_provider_config, write_provider_config

    key, fingerprint, replay_response = _begin_write(request, user.id, repo, {"action": "provider-test"}, path="/api/agent/provider/test")
    if replay_response is not None:
        return replay_response
    settings = get_settings()
    api_key, source = effective_key(settings)
    if not api_key:
        raise AppError("PROVIDER_KEY_MISSING", "尚未保存 TikHub 密钥，无法测试连接。", 409)
    result = await verify_tikhub_key(api_key, settings.tikhub_base_url)
    config = read_provider_config()
    persisted = False
    if config is not None:
        merged = ProviderConfig.model_validate({**config.model_dump(), "test_result": result})
        write_provider_config(merged)
        persisted = True
    body = with_shanghai_times({**result, "key_source": source, "masked_key": masked_key(api_key), "persisted": persisted})
    return _finish_write(user.id, key, fingerprint, repo, 200, body)
