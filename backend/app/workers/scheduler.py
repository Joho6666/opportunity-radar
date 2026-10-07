from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import UTC, datetime

from ..core.config import get_settings
from ..repositories.factory import get_repository_singleton
from ..services.change_detection import breakout_from_snapshots
from ..services.cluster_maintenance import run_maintenance
from ..services.retention_service import cleanup_expired
from ..services.trend_service import make_snapshot
from .queue import enqueue_radar_run

logger = logging.getLogger(__name__)

_last_snapshot_hour: int | None = None
_last_maintenance_day: str | None = None
_last_cleanup_day: str | None = None
_ADVISORY_LOCK_KEY = 727272


def _try_advisory_lock() -> bool:
    """Single-instance guard for multi-replica schedulers (Postgres mode only)."""
    from ..database.client import create_database_engine

    engine = create_database_engine()
    if engine is None:
        return True  # memory mode: nothing to protect
    try:
        with engine.connect() as conn:
            row = conn.exec_driver_sql(f"SELECT pg_try_advisory_lock({_ADVISORY_LOCK_KEY})").first()
            return bool(row and row[0])
    except Exception:
        logger.exception("advisory lock check failed; assuming single instance")
        return True


async def tick(now: datetime | None = None) -> int:
    repo = get_repository_singleton()
    due = repo.list_due_radars(now or datetime.now(UTC))
    queued = 0
    for user_id, radar_id in due:
        run = repo.create_run(radar_id)
        await enqueue_radar_run(user_id, radar_id, run.id)
        queued += 1
    return queued


async def intelligence_tick(now: datetime | None = None) -> int:
    """Hourly: append a snapshot per active trend topic, then detect breakouts.

    Snapshots make "what changed vs yesterday" answerable from history without
    re-crawling; breakouts become ChangeEvents the brief and API can surface.
    """
    global _last_snapshot_hour
    repo = get_repository_singleton()
    now = now or datetime.now(UTC)
    hour = now.hour
    if _last_snapshot_hour == hour:
        return 0
    _last_snapshot_hour = hour
    saved = 0
    try:
        topics = repo.list_trend_topics(limit=500)
        for topic in topics:
            snapshot = make_snapshot(topic, now=now)
            repo.save_trend_snapshot(snapshot)
            saved += 1
            result = breakout_from_snapshots(repo.list_trend_snapshots(topic.id))
            if result is not None and result.is_breakout:
                repo.save_change_event(result.to_event(topic.topic, "mention_count", "topic", topic.radar_id), radar_id=topic.radar_id)
    except Exception:
        logger.exception("intelligence tick failed")
    return saved


async def maintenance_tick(now: datetime | None = None) -> dict[str, int]:
    """Daily: merge near-identical clusters + apply data-retention TTLs."""
    global _last_maintenance_day, _last_cleanup_day
    repo = get_repository_singleton()
    now = now or datetime.now(UTC)
    today = now.strftime("%Y-%m-%d")
    result = {"clusters_merged": 0, "raw_items_removed": 0, "llm_calls_removed": 0}
    if _last_maintenance_day != today:
        _last_maintenance_day = today
        result["clusters_merged"] = await run_maintenance(repo, repo.list_radar_pairs())
    if _last_cleanup_day != today:
        _last_cleanup_day = today
        removed = await cleanup_expired(repo)
        result["raw_items_removed"] = removed.get("raw_items", 0)
        result["llm_calls_removed"] = removed.get("llm_calls", 0)
    return result


async def main() -> None:
    from ..core.logging import configure_logging

    configure_logging()
    while True:
        try:
            await asyncio.sleep(random.uniform(0, 10))  # jitter against replica thundering herds
            if not _try_advisory_lock():
                logger.info("another scheduler instance holds the advisory lock; skipping tick")
                continue
            started = time.perf_counter()
            queued = await tick()
            logger.info("scheduler tick queued=%s", queued)
            await intelligence_tick()
            await maintenance_tick()
            logger.info("scheduler cycle done", extra={"latency_ms": int((time.perf_counter() - started) * 1000)})
        except Exception:
            logger.exception("scheduler tick failed")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
