from .queue import redis_settings
from .radar_worker import execute_radar_run


async def run_radar_job(ctx, user_id: str, radar_id: str, run_id: str):
    return await execute_radar_run(user_id, radar_id, run_id)


class WorkerSettings:
    functions = [run_radar_job]
    max_tries = 3
    job_timeout = 600
    retry_jobs = True
    redis_settings = redis_settings()
