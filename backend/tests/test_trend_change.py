from datetime import UTC, datetime, timedelta

from app.schemas.intelligence import TrendSnapshotRead, TrendTopicRead
from app.services.change_detection import detect_change, detect_daily_breakout
from app.services.trend_service import make_snapshot, rolling_mentions, upsert_topic


def test_topic_upsert_accumulates_mentions():
    now = datetime.now(UTC)
    topic = upsert_topic(None, "radar-1", "AI 视频", 5, 100, now=now)
    assert topic.mention_count == 5
    topic = upsert_topic(topic, "radar-1", "AI 视频", 3, 20, now=now)
    assert topic.mention_count == 8
    assert topic.engagement == 120


def test_snapshot_and_rolling_window():
    now = datetime.now(UTC)
    topic = upsert_topic(None, "radar-1", "n8n", 10, 0, now=now)
    snapshots = []
    cumulative = 0
    for hours_ago, delta in [(72, 5), (48, 6), (24, 7), (1, 18), (0, 97)]:
        captured = now - timedelta(hours=hours_ago)
        cumulative += delta
        snapshots.append(TrendSnapshotRead(id=f"s{hours_ago}", topic_id=topic.id, captured_at=captured, mention_count=cumulative))
    assert rolling_mentions(snapshots, 24, now=now) == 97 + 18 + 7  # inclusive 24h boundary
    assert rolling_mentions(snapshots, 7 * 24, now=now) == 5 + 6 + 7 + 18 + 97


def test_snapshot_defaults_to_cumulative_total():
    topic = upsert_topic(None, "radar-1", "MCP", 42, 0)
    snapshot = make_snapshot(topic)
    assert snapshot.mention_count == 42  # cumulative, not the delta


def test_breakout_from_cumulative_snapshots():
    from app.services.change_detection import breakout_from_snapshots

    now = datetime.now(UTC)
    cumulative = 0
    snapshots = []
    for index, delta in enumerate([17, 19, 18, 18, 97]):
        cumulative += delta
        snapshots.append(TrendSnapshotRead(id=f"s{index}", topic_id="t", captured_at=now - timedelta(hours=120 - index * 24), mention_count=cumulative))
    result = breakout_from_snapshots(snapshots)
    assert result is not None and result.is_breakout is True


def test_breakout_detected_18_daily_to_97_today():
    """验收样例：7 日基线每天 18 条，今天 97 条 → breakout。"""
    baseline = [18.0, 17.0, 19.0, 18.0, 18.0, 18.0, 18.0]
    result = detect_daily_breakout(baseline, 97.0)
    assert result.is_breakout is True
    assert result.breakout_score >= 40
    assert result.z_score > 3


def test_quiet_topic_does_not_breakout():
    baseline = [1.0, 0.0, 0.0, 2.0, 0.0, 1.0, 0.0]
    result = detect_daily_breakout(baseline, 8.0)
    # z-score is high but baseline sample is below the floor
    assert result.is_breakout is False


def test_steady_topic_does_not_breakout():
    baseline = [18.0, 18.0, 18.0, 18.0, 18.0, 18.0, 18.0]
    result = detect_daily_breakout(baseline, 18.0)
    assert result.is_breakout is False
    assert result.breakout_score == 0


def test_change_event_payload_carries_metrics():
    result = detect_change([10.0, 12.0, 11.0, 13.0, 12.0, 14.0, 13.0], 30.0)
    event = result.to_event("AI 视频", "mention_count", "topic", "radar-1")
    assert event.subject_key == "AI 视频"
    assert event.metric_key == "mention_count"
    assert event.current_value == 30.0
    assert event.is_breakout is True


def test_trend_snapshot_read_defaults():
    topic = TrendTopicRead(id="topic-1", radar_id="r", topic="MCP")
    snapshot = make_snapshot(topic, mention_delta=4)
    assert snapshot.topic_id == "topic-1"
    assert snapshot.mention_count == 4
    assert isinstance(snapshot, TrendSnapshotRead)
