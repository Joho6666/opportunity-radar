from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from ..repositories.factory import get_repository_singleton
from .queue import enqueue_radar_run

logger = logging.getLogger(__name__)


async def tick(now: datetime | None = None) -> int:
    repo = get_repository_singleton()
    due = repo.list_due_radars(now or datetime.now(UTC))
    queued = 0
    for user_id, radar_id in due:
        run = repo.create_run(radar_id)
        await enqueue_radar_run(user_id, radar_id, run.id)
        queued += 1
    return queued


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            queued = await tick()
            logger.info("scheduler tick queued=%s", queued)
        except Exception:
            logger.exception("scheduler tick failed")
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
