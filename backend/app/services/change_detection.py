"""Change Detection Engine.

Answers "what changed vs. the trailing baseline" for any metric series:
velocity (per-hour rate), acceleration (rate of change of velocity), momentum
(weighted trend direction), and a breakout z-score. Default gate: 7-day daily
baseline with a minimum sample floor so a quiet topic never breakouts on 3 docs.

Example the system must catch: 7-day baseline ≈ 18 docs/day, today 97 → breakout.
"""

from dataclasses import dataclass

from ..core.config import get_settings
from ..schemas.intelligence import ChangeEventRead


@dataclass(frozen=True)
class ChangeResult:
    baseline_value: float
    current_value: float
    change_rate: float
    z_score: float
    velocity: float
    acceleration: float
    momentum: float
    breakout_score: int
    is_breakout: bool

    def to_event(self, subject_key: str, metric_key: str, subject_kind: str = "topic", radar_id: str | None = None, window_end=None) -> ChangeEventRead:
        from datetime import UTC, datetime

        window_end = window_end or datetime.now(UTC)
        dedup_key = f"{radar_id or 'none'}:{subject_kind}:{subject_key}:{metric_key}:{window_end.strftime('%Y-%m-%d')}"
        return ChangeEventRead(
            id=f"change:{subject_key}:{metric_key}",
            radar_id=radar_id,
            subject_kind=subject_kind,  # type: ignore[arg-type]
            subject_key=subject_key,
            metric_key=metric_key,
            baseline_value=round(self.baseline_value, 4),
            current_value=round(self.current_value, 4),
            change_rate=round(self.change_rate, 4),
            z_score=round(self.z_score, 4),
            velocity=round(self.velocity, 4),
            acceleration=round(self.acceleration, 4),
            momentum=round(self.momentum, 4),
            breakout_score=self.breakout_score,
            is_breakout=self.is_breakout,
            window_end=window_end,
            dedup_key=dedup_key,
        )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = _mean(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return variance ** 0.5


def detect_change(
    baseline: list[float],
    current: float,
    settings: dict | None = None,
    previous_velocity: float | None = None,
) -> ChangeResult:
    """baseline: trailing window values (oldest→newest), e.g. 7 daily counts."""
    config = settings or {}
    z_threshold = float(config.get("z_threshold", get_settings().breakout_z_threshold))
    min_baseline = float(config.get("min_baseline", get_settings().breakout_min_baseline))
    baseline_value = _mean(baseline)
    baseline_std = _std(baseline)
    change_rate = (current - baseline_value) / baseline_value if baseline_value > 0 else (float(current > 0) if current else 0.0)
    z_score = (current - baseline_value) / baseline_std if baseline_std > 0 else 0.0
    velocity = change_rate  # per-baseline-period growth rate
    acceleration = (velocity - previous_velocity) if previous_velocity is not None else 0.0
    momentum = max(-100.0, min(100.0, z_score * 20))
    is_breakout = bool(z_score >= z_threshold and baseline_value >= min_baseline and current > baseline_value)
    breakout_score = 0
    if is_breakout:
        z_component = min(60, int((z_score - z_threshold) * 15 + 40))
        rate_component = min(40, int(max(change_rate, 0) * 40))
        breakout_score = min(100, z_component + rate_component)
    return ChangeResult(
        baseline_value=baseline_value,
        current_value=float(current),
        change_rate=change_rate,
        z_score=z_score,
        velocity=velocity,
        acceleration=acceleration,
        momentum=momentum,
        breakout_score=breakout_score,
        is_breakout=is_breakout,
    )


def detect_daily_breakout(daily_counts: list[float], today_count: float, previous_velocity: float | None = None) -> ChangeResult:
    """Convenience wrapper: trailing daily counts + today's count."""
    return detect_change(daily_counts[-7:], today_count, previous_velocity=previous_velocity)


def breakout_from_snapshots(snapshots) -> ChangeResult | None:
    """Derive a ChangeResult from cumulative trend snapshots (any order).

    Per-period deltas come from subtracting consecutive cumulative totals; the
    latest delta is "today", the trailing deltas are the baseline.
    Returns None when there is not enough history (fewer than 2 deltas).
    """
    from .trend_service import cumulative_deltas, ordered_oldest_first

    ordered = ordered_oldest_first(snapshots)
    deltas = cumulative_deltas(ordered)
    if len(deltas) < 2:
        return None
    return detect_change(deltas[-8:-1], deltas[-1])
