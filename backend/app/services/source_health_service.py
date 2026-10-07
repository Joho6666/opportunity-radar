"""Source Health: per-collector reliability ledger.

Every registry.search() call reports here. One collector failing must never
take down a radar run — the health record exists so the degradation is visible
(and alertable) instead of silent. Health score blends success rate, latency
and rate-limit pressure.
"""

from datetime import UTC, datetime

from ..schemas.intelligence import SourceHealthRead


def record(
    existing: SourceHealthRead | None,
    slug: str,
    ok: bool,
    items: int,
    latency_ms: int,
    error_code: str | None = None,
    error_message: str | None = None,
    now: datetime | None = None,
) -> SourceHealthRead:
    now = now or datetime.now(UTC)
    if existing is None:
        existing = SourceHealthRead(slug=slug)
    runs_total = existing.runs_total + 1
    runs_ok = existing.runs_ok + (1 if ok else 0)
    error_count = existing.error_count + (0 if ok else 1)
    rate_limited = existing.rate_limited_count + (1 if error_code == "RATE_LIMITED" else 0)
    runs_for_latency = max(runs_ok, 1)
    avg_latency = int((existing.avg_latency_ms * (runs_for_latency - 1) + latency_ms) / runs_for_latency) if ok else existing.avg_latency_ms
    success_rate = runs_ok / runs_total if runs_total else 0.0
    health = _health_score(success_rate, avg_latency, rate_limited)
    status = "healthy" if health >= 80 else "degraded" if health >= 50 else "unhealthy"
    if runs_total <= 1 and not ok:
        status = "degraded"
    return existing.model_copy(update={
        "status": status,
        "last_success_at": now if ok else existing.last_success_at,
        "last_failure_at": None if ok else now,
        "last_error": None if ok else (error_message or error_code),
        "last_error_code": None if ok else error_code,
        "runs_total": runs_total,
        "runs_ok": runs_ok,
        "items_fetched": existing.items_fetched + max(items, 0),
        "success_rate": round(success_rate, 4),
        "avg_latency_ms": avg_latency,
        "rate_limited_count": rate_limited,
        "error_count": error_count,
        "health_score": health,
    })


def _health_score(success_rate: float, avg_latency_ms: int, rate_limited_count: int) -> int:
    score = success_rate * 100
    if avg_latency_ms > 5000:
        score -= 10
    elif avg_latency_ms > 2000:
        score -= 5
    score -= min(15, rate_limited_count * 3)
    return max(0, min(100, round(score)))
