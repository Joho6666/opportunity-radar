import asyncio
from datetime import UTC, datetime, timedelta

from app.repositories.memory import MemoryRepository
from app.schemas.domain import RadarCreate
from app.schemas.intelligence import TrendSnapshotRead
from app.services.change_detection import detect_daily_breakout
from app.services.trend_service import make_snapshot, upsert_topic
from app.workers import scheduler as scheduler_module


def test_intelligence_tick_snapshots_topics_and_detects_breakout(monkeypatch):
    repo = MemoryRepository()
    radar = repo.create_radar("sched-iq", RadarCreate(name="R", goal="寻找 AI 视频商业机会信号", keywords=["AI 视频"]))
    # topic cumulative total = 187 (daily deltas 17,19,18,18,97 → today breaks out)
    topic = upsert_topic(None, radar.id, "AI 视频", 187, 0)
    topic = repo.upsert_trend_topic(topic)
    # explicit timestamps relative to the tick time keep the test time-of-day independent
    tick_t = datetime(2026, 10, 6, 14, 0, tzinfo=UTC)
    for index, total in enumerate([18, 35, 54, 72, 90]):
        repo.save_trend_snapshot(TrendSnapshotRead(id=f"s{index}", topic_id=topic.id, captured_at=tick_t - timedelta(hours=5 - index), mention_count=total))
    monkeypatch.setattr(scheduler_module, "get_repository_singleton", lambda: repo)
    monkeypatch.setattr(scheduler_module, "_last_snapshot_hour", None)
    saved = asyncio.run(scheduler_module.intelligence_tick(tick_t))
    assert saved >= 1
    events = repo.list_change_events(user_id="sched-iq")
    assert any(event.is_breakout and event.subject_key == "AI 视频" for event in events)


def test_intelligence_tick_skips_topics_without_history(monkeypatch):
    repo = MemoryRepository()
    radar = repo.create_radar("sched-iq2", RadarCreate(name="R", goal="寻找 AI 视频商业机会信号", keywords=["AI 视频"]))
    repo.upsert_trend_topic(upsert_topic(None, radar.id, "全新话题", 3, 0))
    monkeypatch.setattr(scheduler_module, "get_repository_singleton", lambda: repo)
    monkeypatch.setattr(scheduler_module, "_last_snapshot_hour", None)
    saved = asyncio.run(scheduler_module.intelligence_tick(datetime(2026, 10, 6, 15, 0, tzinfo=UTC)))
    assert saved >= 1
    assert repo.list_change_events(user_id="sched-iq2") == []


def test_intelligence_tick_runs_once_per_hour(monkeypatch):
    repo = MemoryRepository()
    monkeypatch.setattr(scheduler_module, "get_repository_singleton", lambda: repo)
    monkeypatch.setattr(scheduler_module, "_last_snapshot_hour", 14)
    saved = asyncio.run(scheduler_module.intelligence_tick(datetime(2026, 10, 6, 14, 30, tzinfo=UTC)))
    assert saved == 0


def test_breakout_fixture_is_breakout():
    result = detect_daily_breakout([18.0, 17.0, 19.0, 18.0, 18.0, 18.0, 18.0], 97.0)
    assert result.is_breakout
