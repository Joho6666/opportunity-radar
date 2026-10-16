from __future__ import annotations

import logging
from urllib.parse import urlparse
from ..core.config import get_settings
from ..core.errors import AppError
from .radar_worker import execute_radar_run

logger = logging.getLogger(__name__)


def redis_settings():
    from arq.connections import RedisSettings

    url = get_settings().redis_url or "redis://localhost:6379"
    parsed = urlparse(url)
    database = (parsed.path or "/0").strip("/") or "0"
    return RedisSettings(host=parsed.hostname or "localhost", port=parsed.port or 6379, database=int(database), password=parsed.password)


async def enqueue_radar_run(user_id: str, radar_id: str, run_id: str) -> None:
    """Dispatch through Arq; only explicit dev/test mode may run inline."""
    if not get_settings().redis_url:
        if get_settings().app_env.lower() == "local":
            raise AppError("LOCAL_REDIS_REQUIRED", "本地后台队列不可用；任务已保留为待派发状态。", 503)
        await execute_radar_run(user_id, radar_id, run_id)
        return
    from arq import create_pool

    import asyncio
    pool = await asyncio.wait_for(create_pool(redis_settings()), timeout=2.5)
    try:
        await asyncio.wait_for(pool.enqueue_job("run_radar_job", user_id, radar_id, run_id, _job_id=f"radar-run:{run_id}"), timeout=2.5)
    finally:
        await pool.close()
