from __future__ import annotations

import logging
from urllib.parse import urlparse
from ..core.config import get_settings
from .radar_worker import execute_radar_run

logger = logging.getLogger(__name__)


def redis_settings():
    from arq.connections import RedisSettings

    url = get_settings().redis_url or "redis://localhost:6379"
    parsed = urlparse(url)
    database = (parsed.path or "/0").strip("/") or "0"
    return RedisSettings(host=parsed.hostname or "localhost", port=parsed.port or 6379, database=int(database), password=parsed.password)


async def enqueue_radar_run(user_id: str, radar_id: str, run_id: str) -> None:
    """Enqueue on Redis when configured; otherwise run in-process for tests and demo mode."""
    if not get_settings().redis_url:
        await execute_radar_run(user_id, radar_id, run_id)
        return
    from arq import create_pool

    pool = await create_pool(redis_settings())
    try:
        await pool.enqueue_job("run_radar_job", user_id, radar_id, run_id, _job_id=f"radar-run:{run_id}")
    finally:
        await pool.close()
