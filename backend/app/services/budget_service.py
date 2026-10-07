"""Per-user LLM token budget with circuit-breaker semantics.

check_and_consume() reserves estimated tokens BEFORE the call; when the daily
budget is exhausted the caller must fall back to the rule path (never raise —
a spent budget degrades quality, it must not break runs).

Storage: Redis INCR with a 48h TTL when REDIS_URL is configured (works across
API/worker processes); otherwise a per-process dict, which is fine for tests
and single-process demo mode.
"""

import logging
from datetime import UTC, datetime

from ..core.config import get_settings

logger = logging.getLogger(__name__)

_local_counters: dict[str, int] = {}
_local_counters_date: dict[str, str] = {}


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _redis_client():
    settings = get_settings()
    if not settings.redis_url:
        return None
    try:
        import redis.asyncio as redis

        return redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        logger.exception("redis unavailable for budget tracking; using in-process counter")
        return None


async def check_and_consume(user_id: str, estimated_tokens: int) -> bool:
    """Reserve tokens for today. False = over budget; caller must skip the LLM."""
    budget = get_settings().llm_daily_token_budget
    if budget <= 0:
        return True
    client = await _redis_client_async()
    key = f"llm_budget:{user_id}:{_today()}"
    if client is not None:
        try:
            value = await client.incrby(key, max(estimated_tokens, 1))
            if value == max(estimated_tokens, 1):
                await client.expire(key, 48 * 3600)
            return value <= budget
        except Exception:
            logger.exception("redis budget check failed; falling back to in-process counter")
    today = _today()
    if _local_counters_date.get(user_id) != today:
        _local_counters[user_id] = 0
        _local_counters_date[user_id] = today
    _local_counters[user_id] = _local_counters.get(user_id, 0) + max(estimated_tokens, 1)
    return _local_counters[user_id] <= budget


async def _redis_client_async():
    return _redis_client()


async def consumed_today(user_id: str) -> int:
    client = await _redis_client_async()
    key = f"llm_budget:{user_id}:{_today()}"
    if client is not None:
        try:
            value = await client.get(key)
            return int(value or 0)
        except Exception:
            return _local_counters.get(user_id, 0)
    return _local_counters.get(user_id, 0)


def estimate_tokens(text: str) -> int:
    """Rough pre-call estimate (~3 chars/token mixed CJK/English) for gating."""
    return max(len(text) // 3, 1)
