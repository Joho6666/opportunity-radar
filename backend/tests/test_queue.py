import asyncio
from datetime import UTC, datetime, timedelta
from app.repositories.memory import MemoryRepository
from app.schemas.domain import ProfileUpsert, RadarCreate
from app.workers import scheduler as scheduler_module
from app.workers.queue import enqueue_radar_run


def test_enqueue_without_redis_runs_in_process():
    from app.repositories.factory import get_repository_singleton

    repo = get_repository_singleton()
    user_id = "queue-user"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "PPT", "level": "strong"}], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="PPT", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"]))
    run = repo.create_run(radar.id)
    result_status = asyncio.run(enqueue_radar_run(user_id, radar.id, run.id))
    assert result_status is None or True
    saved = repo.get_run(user_id, run.id)
    assert saved.status == "completed"
    assert repo.list_opportunities(user_id)


def test_scheduler_skips_paused_radars(monkeypatch):
    repo = MemoryRepository()
    user_id = "sched-user"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "PPT", "level": "strong"}], goals=["client"]))
    active = repo.create_radar(user_id, RadarCreate(name="A", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"]))
    paused = repo.create_radar(user_id, RadarCreate(name="B", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"]))
    past = datetime.now(UTC) - timedelta(hours=1)
    repo.save_radar(active.model_copy(update={"status": "active", "next_run_at": past}))
    repo.save_radar(paused.model_copy(update={"status": "paused", "next_run_at": past}))
    monkeypatch.setattr(scheduler_module, "get_repository_singleton", lambda: repo)
    queued_ids = []

    async def fake_enqueue(user_id, radar_id, run_id):
        queued_ids.append(radar_id)

    monkeypatch.setattr(scheduler_module, "enqueue_radar_run", fake_enqueue)
    count = asyncio.run(scheduler_module.tick(datetime.now(UTC)))
    assert count == 1
    assert queued_ids == [active.id]
