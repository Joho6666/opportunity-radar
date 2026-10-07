from app.services.source_health_service import record


def test_first_success_is_healthy():
    health = record(None, "github", ok=True, items=10, latency_ms=300)
    assert health.status == "healthy"
    assert health.runs_total == 1
    assert health.runs_ok == 1
    assert health.success_rate == 1.0
    assert health.health_score == 100
    assert health.items_fetched == 10


def test_repeated_failures_degrade_then_unhealthy():
    health = record(None, "rss", ok=True, items=5, latency_ms=200)
    for _ in range(5):
        health = record(health, "rss", ok=False, items=0, latency_ms=0, error_code="COLLECTOR_FAILED", error_message="boom")
    assert health.runs_total == 6
    assert health.error_count == 5
    assert health.status in {"degraded", "unhealthy"}
    assert health.health_score < 50
    assert health.last_error == "boom"
    assert health.last_failure_at is not None
    assert health.last_success_at is not None


def test_rate_limited_errors_counted_and_penalized():
    health = record(None, "web_search", ok=True, items=8, latency_ms=500)
    for _ in range(3):
        health = record(health, "web_search", ok=False, items=0, latency_ms=0, error_code="RATE_LIMITED")
    assert health.rate_limited_count == 3
    assert health.health_score < 100


def test_recovery_restores_health():
    health = record(None, "github", ok=True, items=5, latency_ms=100)
    health = record(health, "github", ok=False, items=0, latency_ms=0, error_code="COLLECTOR_FAILED")
    assert health.status != "healthy"
    recovered = record(health, "github", ok=True, items=6, latency_ms=150)
    assert recovered.last_error is None
    assert recovered.error_count == 1  # history kept, status recovering
    assert recovered.health_score > health.health_score
    for _ in range(3):
        recovered = record(recovered, "github", ok=True, items=6, latency_ms=150)
    assert recovered.status == "healthy"


def test_latency_penalizes_score():
    slow = record(None, "crawl", ok=True, items=3, latency_ms=8000)
    fast = record(None, "crawl", ok=True, items=3, latency_ms=200)
    assert slow.health_score < fast.health_score
