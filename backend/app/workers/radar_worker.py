from ..repositories.memory import repository
from ..services.radar_run_service import RadarRunService


async def execute_radar_run(user_id: str, radar_id: str, run_id: str):
    """Worker seam for future Redis/Celery/Arq execution."""
    return await RadarRunService(repository).run(user_id, radar_id, run_id)
