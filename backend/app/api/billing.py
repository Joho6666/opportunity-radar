from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from ..api.deps import get_current_user, get_repository
from ..core.config import get_settings
from ..core.errors import AppError
from ..core.security import CurrentUser
from ..repositories.postgres import as_uuid
from ..services.billing_gateway import _micros

router = APIRouter(prefix="/api/billing", tags=["Billing"])


class Authorization(BaseModel):
    enabled: bool = False
    providers: list[Literal["tikhub", "firecrawl", "llm", "embedding"]] = Field(default_factory=list)
    allow_scheduled: bool = False
    run_requests: int = Field(default=1, ge=1, le=100)
    daily_requests: int = Field(default=5, ge=1, le=1000)
    run_cost_usd: float = Field(default=0.1, gt=0, le=100)
    daily_cost_usd: float = Field(default=0.5, gt=0, le=1000)

    @model_validator(mode="after")
    def limits(self):
        if self.run_requests > self.daily_requests or self.run_cost_usd > self.daily_cost_usd:
            raise ValueError("Single-run limits cannot exceed daily limits")
        return self


def require_pg(repo):
    if not hasattr(repo, "engine"):
        raise AppError("BILLING_PERSISTENCE_REQUIRED", "付费授权需要 PostgreSQL。", 409)


@router.put("/authorizations/{scope}")
async def authorize(scope: str, value: Authorization, user: CurrentUser = Depends(get_current_user), repo=Depends(get_repository)):
    require_pg(repo)
    if scope not in {"evidence", "assistant"}:
        repo.get_radar(user.id, scope)
    repo.get_profile(user.id)
    import json
    with repo.engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:uid,0))"), {"uid": as_uuid(user.id)})
        conn.execute(text("INSERT INTO billing_authorizations(user_id,scope,enabled,providers,allow_scheduled,run_requests,daily_requests,run_micros,daily_micros) VALUES(CAST(:uid AS uuid),:scope,:enabled,CAST(:providers AS jsonb),:allow_scheduled,:run_requests,:daily_requests,:run_micros,:daily_micros) ON CONFLICT(user_id,scope) DO UPDATE SET enabled=EXCLUDED.enabled,providers=EXCLUDED.providers,allow_scheduled=EXCLUDED.allow_scheduled,run_requests=EXCLUDED.run_requests,daily_requests=EXCLUDED.daily_requests,run_micros=EXCLUDED.run_micros,daily_micros=EXCLUDED.daily_micros,updated_at=now()"),
                     {**value.model_dump(exclude={"run_cost_usd", "daily_cost_usd"}), "uid": as_uuid(user.id), "scope": scope, "providers": json.dumps(value.providers), "run_micros": _micros(value.run_cost_usd), "daily_micros": _micros(value.daily_cost_usd)})
    return {"scope": scope, **value.model_dump(), "paid_api_enabled": get_settings().paid_api_enabled}


@router.get("/status")
async def status(user: CurrentUser = Depends(get_current_user), repo=Depends(get_repository)):
    result = {"paid_api_enabled": get_settings().paid_api_enabled, "authorizations": [], "requests_today": 0, "reserved_cost_usd": 0, "actual_cost_usd": None, "tokens_reported": None}
    if not hasattr(repo, "engine"):
        return {**result, "warning": "内存模式禁止真实付费调用"}
    uid = as_uuid(user.id)
    with repo.engine.begin() as conn:
        policies = conn.execute(text("SELECT scope,enabled,providers,allow_scheduled,run_requests,daily_requests,run_micros,daily_micros FROM billing_authorizations WHERE user_id=CAST(:uid AS uuid)"), {"uid": uid}).mappings().all()
        calls = conn.execute(text("SELECT scope,count(*) requests,sum(GREATEST(reserved_micros,COALESCE(actual_micros,0))) cost,sum(reserved_micros) estimated,CASE WHEN count(actual_micros)=count(*) THEN sum(actual_micros) ELSE NULL END actual,sum(actual_tokens) tokens FROM billing_calls WHERE user_id=CAST(:uid AS uuid) AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' GROUP BY scope"), {"uid": uid}).mappings().all()
    by_scope = {row["scope"]: row for row in calls}
    account_requests = max(0, get_settings().paid_daily_request_limit - sum(row["requests"] for row in calls))
    account_micros = max(0, _micros(get_settings().paid_daily_cost_limit) - sum(row["cost"] for row in calls))
    result["account_remaining_requests"] = account_requests
    result["account_remaining_cost_usd"] = account_micros / 1_000_000
    for row in policies:
        used = by_scope.get(row["scope"], {})
        result["authorizations"].append({
            **dict(row),
            "remaining_requests": min(account_requests, max(0, row["daily_requests"] - int(used.get("requests", 0)))),
            "remaining_cost_usd": min(account_micros, max(0, row["daily_micros"] - int(used.get("cost", 0)))) / 1_000_000,
        })
    result["requests_today"] = sum(row["requests"] for row in calls)
    result["reserved_cost_usd"] = sum(row["estimated"] for row in calls)/1_000_000
    result["consumed_cost_usd"] = sum(row["cost"] for row in calls)/1_000_000
    result["actual_cost_usd"] = sum(row["actual"] for row in calls if row["actual"] is not None)/1_000_000 if calls and all(row["actual"] is not None for row in calls) else None
    result["tokens_reported"] = sum(row["tokens"] for row in calls if row["tokens"] is not None) or None
    return result
