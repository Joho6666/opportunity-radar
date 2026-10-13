"""Fail-closed paid-call boundary. Reservations survive errors and process restarts."""
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal, ROUND_CEILING
from uuid import uuid4
import math

from sqlalchemy import text

from ..core.config import get_settings
from ..core.errors import AppError

_context: ContextVar[dict | None] = ContextVar("paid_call_context", default=None)


@contextmanager
def paid_context(repository, user_id: str, scope: str, run_id: str, scheduled: bool = False):
    token = _context.set(dict(repository=repository, user_id=user_id, scope=scope, run_id=run_id, scheduled=scheduled))
    try:
        yield
    finally:
        _context.reset(token)


def _micros(value) -> int:
    return int((Decimal(str(value)) * 1_000_000).to_integral_value(rounding=ROUND_CEILING))


def reserve(provider: str, source: str, estimated_tokens: int = 0) -> tuple[object, str]:
    settings = get_settings()
    if not settings.paid_api_enabled:
        raise AppError("PAID_API_DISABLED", "真实付费调用默认关闭，请先由服务端管理员启用。", 403)
    context = _context.get()
    if not context or not hasattr(context["repository"], "engine"):
        raise AppError("BILLING_CONTEXT_REQUIRED", "付费调用需要持久化授权上下文。", 403)
    prices = {"tikhub": settings.tikhub_price_per_request, "firecrawl": settings.firecrawl_price_per_request,
              "llm": settings.llm_price_input_per_mtok, "embedding": settings.embedding_price_per_mtok}
    price = prices.get(provider, 0)
    if price <= 0 or (provider == "llm" and settings.llm_price_output_per_mtok <= 0):
        raise AppError("BILLING_PRICE_REQUIRED", "需配置保守的费用上限，不能把未知价格当成免费。", 403)
    # Reserve the larger token tariff, including a byte-based upper bound on input and max output.
    if provider in {"llm", "embedding"}:
        estimated_tokens += 256
        price = max(price, settings.llm_price_output_per_mtok if provider == "llm" else price) * estimated_tokens / 1_000_000
    cost = max(1, _micros(price))
    repo = context["repository"]
    from ..repositories.postgres import as_uuid
    uid = as_uuid(context["user_id"])
    params = dict(uid=uid, scope=context["scope"], run=context["run_id"])
    with repo.engine.begin() as conn:
        # Account-wide lock serializes all scopes; DB outage never falls back to memory.
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:uid, 0))"), {"uid": uid})
        policy = conn.execute(text("SELECT * FROM billing_authorizations WHERE user_id=CAST(:uid AS uuid) AND scope=:scope FOR UPDATE"), params).mappings().first()
        if not policy or not policy["enabled"] or provider not in policy["providers"] or (context["scheduled"] and not policy["allow_scheduled"]):
            raise AppError("PAID_CALL_UNAUTHORIZED", "该来源或定时运行未获得付费授权。", 403)
        totals = conn.execute(text("SELECT count(*) AS requests, COALESCE(sum(GREATEST(reserved_micros,COALESCE(actual_micros,0))),0) AS cost, COALESCE(sum(GREATEST(estimated_tokens,COALESCE(actual_tokens,0))),0) AS tokens FROM billing_calls WHERE user_id=CAST(:uid AS uuid) AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"), params).mappings().one()
        daily = conn.execute(text("SELECT count(*) AS requests, COALESCE(sum(GREATEST(reserved_micros,COALESCE(actual_micros,0))),0) AS cost FROM billing_calls WHERE user_id=CAST(:uid AS uuid) AND scope=:scope AND created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"), params).mappings().one()
        run = conn.execute(text("SELECT count(*) AS requests, COALESCE(sum(GREATEST(reserved_micros,COALESCE(actual_micros,0))),0) AS cost FROM billing_calls WHERE user_id=CAST(:uid AS uuid) AND run_id=:run"), params).mappings().one()
        if (daily["requests"] + 1 > policy["daily_requests"] or run["requests"] + 1 > policy["run_requests"]
            or daily["cost"] + cost > policy["daily_micros"] or run["cost"] + cost > policy["run_micros"]
            or totals["cost"] + cost > _micros(settings.paid_daily_cost_limit)
            or totals["requests"] + 1 > settings.paid_daily_request_limit
            or (settings.llm_daily_token_budget > 0 and totals["tokens"] + estimated_tokens > settings.llm_daily_token_budget)):
            raise AppError("PAID_QUOTA_EXHAUSTED", "付费请求、token 或费用额度不足。", 429)
        call_id = str(uuid4())
        conn.execute(text("INSERT INTO billing_calls (id,user_id,scope,run_id,provider,source,reserved_micros,estimated_tokens,scheduled) VALUES (CAST(:id AS uuid),CAST(:uid AS uuid),:scope,:run,:provider,:source,:cost,:tokens,:scheduled)"),
                     {**params, "id": call_id, "provider": provider, "source": source, "cost": cost, "tokens": estimated_tokens, "scheduled": context["scheduled"]})
    return repo, call_id


def finish(reservation, payload: dict | None = None, *, ok: bool = True) -> None:
    repo, call_id = reservation
    usage = (payload or {}).get("usage") or {}
    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
    tokens = usage.get("total_tokens")
    reported = usage.get("cost_usd")  # Only provider-reported cost; unknown remains NULL.
    actual = _micros(reported) if isinstance(reported,(int,float)) and math.isfinite(reported) and reported >= 0 else None
    def count(value):
        return value if isinstance(value,int) and value >= 0 else None
    with repo.engine.begin() as conn:
        owner=conn.execute(text("SELECT user_id FROM billing_calls WHERE id=CAST(:id AS uuid)"),{"id":call_id}).scalar_one()
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:uid,0))"),{"uid":str(owner)})
        # If a provider exceeds its configured conservative estimate, consume the
        # larger observed value so subsequent calls stop at the real usage limit.
        conn.execute(text("UPDATE billing_calls SET status=:status,prompt_tokens=:prompt,completion_tokens=:completion,actual_tokens=:tokens,actual_micros=:cost WHERE id=CAST(:id AS uuid)"),
                     dict(id=call_id,status="succeeded" if ok else "failed",prompt=count(prompt),completion=count(completion),tokens=count(tokens),cost=actual))
