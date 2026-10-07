from ..collectors.registry import registry
from ..repositories.factory import get_repository_singleton
from ..services.radar_run_service import RadarRunService


def _wire_source_health() -> None:
    if registry._health_recorder is not None:
        return
    repo = get_repository_singleton()

    def record(slug: str, ok: bool, items: int, latency_ms: int, error_code: str | None = None, error_message: str | None = None) -> None:
        repo.record_source_health(slug, ok, items, latency_ms, error_code, error_message)

    registry.set_health_recorder(record)


async def execute_radar_run(user_id: str, radar_id: str, run_id: str):
    """Worker seam for Redis/Arq execution; uses the configured repository."""
    try:
        _wire_source_health()
    except Exception:
        import logging

        logging.getLogger(__name__).exception("source health wiring failed")
    return await RadarRunService(get_repository_singleton()).run(user_id, radar_id, run_id)
