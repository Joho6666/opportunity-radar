from ..repositories.factory import get_repository_singleton
from ..services.radar_run_service import RadarRunService


async def execute_radar_run(user_id: str, radar_id: str, run_id: str):
    """Worker seam for Redis/Arq execution; uses the configured repository."""
    return await RadarRunService(get_repository_singleton()).run(user_id, radar_id, run_id)
