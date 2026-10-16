from .queue import redis_settings
from .radar_worker import execute_radar_run
from ..core.config import get_settings, validate_runtime

validate_runtime()


async def run_radar_job(ctx, user_id: str, radar_id: str, run_id: str):
    return await execute_radar_run(user_id, radar_id, run_id)


class WorkerSettings:
    functions = [run_radar_job]
    max_tries = 1
    job_timeout = 600
    retry_jobs = False
    max_jobs = 1 if get_settings().app_env.lower() == "local" else 10
    redis_settings = redis_settings()
