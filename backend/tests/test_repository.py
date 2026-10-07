from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
import pytest
from app.core.errors import AppError
from app.repositories.memory import MemoryRepository
from app.schemas.domain import OpportunityAction, ProfileUpsert, RadarCreate
from app.services.income import potential_income_range
from app.services.radar_run_service import RadarRunService
import asyncio


def _contract(repo, user_id: str) -> None:
    profile = repo.save_profile(user_id, ProfileUpsert(display_name="Alice", skills=[{"name": "PPT", "level": "strong"}], goals=["client"]))
    assert profile.display_name == "Alice"
    assert profile.skills[0].name == "PPT"

    radar = repo.create_radar(user_id, RadarCreate(name="PPT 雷达", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"], sources=["mock"]))
    assert radar.status == "active"
    assert repo.get_radar(user_id, radar.id).name == "PPT 雷达"
    past = datetime.now(UTC) - timedelta(hours=1)
    radar = repo.save_radar(radar.model_copy(update={"next_run_at": past, "status": "active"}))
    assert any(radar_id == radar.id for _, radar_id in repo.list_due_radars(datetime.now(UTC)))

    stranger = str(uuid4())
    with pytest.raises(AppError) as missing:
        repo.get_radar(stranger, radar.id)
    assert missing.value.code == "RADAR_NOT_FOUND"

    assert repo.has_raw(radar.id, "https://example.com/a?x=1") is False
    repo.mark_raw(radar.id, "https://example.com/a?x=1")
    assert repo.has_raw(radar.id, "https://example.com/a") is True

    run = repo.create_run(radar.id)
    assert run.status == "queued"
    saved = repo.save_run(run.model_copy(update={"status": "completed", "error_code": None}))
    assert saved.status == "completed"
    assert repo.get_run(user_id, run.id).status == "completed"

    result = asyncio.run(RadarRunService(repo).run(user_id, radar.id, repo.create_run(radar.id).id))
    assert result.status == "completed"
    items = repo.list_opportunities(user_id)
    assert items
    first = items[0]
    repo.save_opportunity(first.model_copy(update={"status": "won"}))
    assert repo.won_revenue(user_id) == first.budget_max
    repo.record_action(first.id, OpportunityAction(actual_revenue=123), action="won")
    assert repo.won_revenue(user_id) == 123

    brief = repo.daily_brief(user_id)
    low, high = potential_income_range(repo.list_opportunities(user_id))
    assert brief.potential_income_min == low
    assert brief.potential_income_max == high

    repo.delete_radar(user_id, radar.id)
    assert repo.list_opportunities(user_id) == []
    assert repo.runs_of_user(user_id) == []
    with pytest.raises(AppError):
        repo.get_radar(user_id, radar.id)


def test_memory_repository_contract():
    _contract(MemoryRepository(), "memory-user")


def test_postgres_repository_contract():
    from app.core.config import get_settings
    from app.database.client import create_database_engine
    from app.repositories.postgres import PostgresRepository

    if not get_settings().database_url:
        pytest.skip("DATABASE_URL not configured")
    engine = create_database_engine()
    if engine is None:
        pytest.skip("postgres engine unavailable")
    repo = PostgresRepository(engine)
    user_id = str(uuid4())
    try:
        repo.get_profile(user_id)
    except Exception as exc:
        pytest.skip(f"postgres schema unavailable: {exc}")
    _contract(repo, user_id)


def test_factory_defaults_to_memory(monkeypatch):
    from app.core.config import Settings
    from app.repositories import factory
    from app.repositories.memory import MemoryRepository

    monkeypatch.setattr(factory, "get_settings", lambda: Settings())
    factory.get_repository_singleton.cache_clear()
    repo = factory.get_repository_singleton()
    assert isinstance(repo, MemoryRepository)
    factory.get_repository_singleton.cache_clear()


def test_postgres_sql_uses_bound_parameters():
    source = Path("app/repositories/postgres.py").read_text(encoding="utf-8")
    assert "text(f" not in source
    assert ".format(" not in source
    assert "%s" not in source


def test_potential_income_weights_conversion():
    from app.schemas.domain import OpportunityRead

    item = OpportunityRead(
        id="1",
        radar_id="r",
        type="client",
        title="t",
        summary="s",
        source="mock",
        source_url="https://example.com",
        location="线上",
        work_mode="online",
        budget_min=1000,
        budget_max=2000,
        estimated_hours=10,
        estimated_hourly_rate=(100, 200),
        match_score=90,
        opportunity_score=91,
        conversion_probability=50,
        risk_score=10,
        recommendation="强烈推荐",
        status="new",
    )
    assert potential_income_range([item]) == (500, 1000)
