"""Data retention: bounded growth for append-only tables.

raw_items follow last_seen_at (an item seen again stays alive), llm_calls follow
created_at. trend_snapshots are tiny and ARE the trend history — kept forever.
Retention days of 0 disable cleanup.
"""

import logging

from ..core.config import get_settings

logger = logging.getLogger(__name__)


async def cleanup_expired(repository) -> dict[str, int]:
    settings = get_settings()
    removed: dict[str, int] = {}
    if settings.retention_raw_items_days > 0:
        removed["raw_items"] = repository.cleanup_raw_items(settings.retention_raw_items_days)
    if settings.retention_llm_calls_days > 0:
        removed["llm_calls"] = repository.cleanup_llm_calls(settings.retention_llm_calls_days)
    if removed:
        logger.info("retention cleanup", extra=removed)
    return removed
