"""Trend topics + hourly snapshots (MetricHistory).

A TrendTopic tracks a keyword/phrase across a radar's runs; every scheduler
hour-tick appends an immutable TrendSnapshot row so velocity questions are
answered from history, never by re-crawling.
"""

from datetime import UTC, datetime

from ..schemas.intelligence import TrendSnapshotRead, TrendTopicRead


def upsert_topic(
    existing: TrendTopicRead | None,
    radar_id: str,
    topic: str,
    mention_count: int,
    engagement: int,
    metrics: dict | None = None,
    now: datetime | None = None,
) -> TrendTopicRead:
    """Merge a run's counts into the topic row (repository persists)."""
    now = now or datetime.now(UTC)
    if existing is None:
        return TrendTopicRead(
            id=f"topic:{radar_id}:{topic}",
            radar_id=radar_id,
            topic=topic,
            mention_count=mention_count,
            engagement=engagement,
            metrics=metrics or {},
            first_seen_at=now,
            last_seen_at=now,
        )
    merged_metrics = {**existing.metrics, **(metrics or {})}
    return existing.model_copy(update={
        "mention_count": existing.mention_count + mention_count,
        "engagement": existing.engagement + engagement,
        "metrics": merged_metrics,
        "last_seen_at": now,
    })


def make_snapshot(topic: TrendTopicRead, mention_delta: int | None = None, engagement_delta: int | None = None, now: datetime | None = None) -> TrendSnapshotRead:
    """Snapshot totals are CUMULATIVE (matching trend_topics.mention_count);
    per-period deltas are derived by subtraction at analysis time."""
    now = now or datetime.now(UTC)
    mention_total = topic.mention_count + (mention_delta or 0)
    engagement_total = topic.engagement + (engagement_delta or 0)
    return TrendSnapshotRead(
        id=f"snapshot:{topic.id}:{now.isoformat()}",
        topic_id=topic.id,
        captured_at=now,
        mention_count=mention_total,
        engagement=engagement_total,
        metrics=dict(topic.metrics),
    )


def ordered_oldest_first(snapshots: list[TrendSnapshotRead]) -> list[TrendSnapshotRead]:
    """Normalize any snapshot ordering (memory inserts oldest-first, Postgres
    returns newest-first) into oldest→newest."""

    def key(snapshot: TrendSnapshotRead):
        return snapshot.captured_at or datetime.min.replace(tzinfo=UTC)

    return sorted(snapshots, key=key)


def cumulative_deltas(oldest_first: list[TrendSnapshotRead]) -> list[float]:
    totals = [float(snapshot.mention_count) for snapshot in oldest_first]
    if not totals:
        return []
    return [max(0.0, totals[index] - totals[index - 1]) for index in range(1, len(totals))]


def rolling_mentions(snapshots: list[TrendSnapshotRead], hours: float, now: datetime | None = None) -> int:
    """Mentions accumulated in the trailing window, from cumulative snapshots."""
    now = now or datetime.now(UTC)

    def as_utc(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    ordered = ordered_oldest_first(snapshots)
    if not ordered:
        return 0
    latest = ordered[-1]
    if as_utc(latest.captured_at) > now:
        return 0
    edge_total = 0
    for snapshot in ordered:
        captured = as_utc(snapshot.captured_at) if snapshot.captured_at else None
        if captured is not None and (now - captured).total_seconds() / 3600 <= hours:
            continue
        edge_total = snapshot.mention_count
    return max(0, latest.mention_count - edge_total)
