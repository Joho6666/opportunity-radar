import asyncio
from datetime import UTC, datetime, timedelta
from app.collectors.base import SourceAdapter
from app.collectors.mock import MockCollector
from app.collectors.registry import CollectorRegistry
from app.repositories.memory import MemoryRepository
from app.schemas.domain import ProfileUpsert, QueryPlanItem, RadarCreate, RawItem
from app.services.radar_run_service import RadarRunService, next_run_at


class BoomCollector(SourceAdapter):
    slug = "github"

    async def search(self, query: str) -> list[RawItem]:
        raise RuntimeError("github down")


def _ready_repo():
    repo = MemoryRepository()
    user_id = "run-user"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "PPT", "level": "strong"}], goals=["client"]))
    return repo, user_id


def test_next_run_supports_hourly_daily_weekly():
    now = datetime(2026, 9, 1, tzinfo=UTC)
    assert next_run_at("hourly", now) == now + timedelta(hours=1)
    assert next_run_at("daily", now) == now + timedelta(days=1)
    assert next_run_at("weekly", now) == now + timedelta(days=7)


def test_failed_collector_does_not_fail_the_run():
    repo, user_id = _ready_repo()
    radar = repo.create_radar(user_id, RadarCreate(name="混合雷达", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"], sources=["github", "mock"]))
    radar = repo.save_radar(radar.model_copy(update={"queries": [QueryPlanItem(query="AI", source="github", priority=90), QueryPlanItem(query="PPT", source="mock", priority=80)]}))
    run = repo.create_run(radar.id)
    collectors = CollectorRegistry([BoomCollector(), MockCollector()])
    result = asyncio.run(RadarRunService(repo, collectors).run(user_id, radar.id, run.id))
    assert result.status == "completed"
    assert result.collector_errors
    assert result.stats.opportunities_found > 0
    assert repo.get_radar(user_id, radar.id).status == "active"
    assert repo.llm_calls
    assert any(call["fallbacked"] for call in repo.llm_calls)


def test_uncaught_run_error_keeps_error_code():
    repo, user_id = _ready_repo()
    radar = repo.create_radar(user_id, RadarCreate(name="PPT", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"]))
    run = repo.create_run(radar.id)

    class Broken(CollectorRegistry):
        async def search(self, slug: str, query: str):
            raise ValueError("boom")

    result = asyncio.run(RadarRunService(repo, Broken([])).run(user_id, radar.id, run.id))
    assert result.status == "failed"
    assert result.error_code == "RADAR_RUN_FAILED"
    assert "ValueError" in (result.error_message or "")
    assert repo.get_radar(user_id, radar.id).status == "error"
