"""Smoke tests: the FastAPI app wires the intelligence router; contracts unchanged."""

from fastapi.testclient import TestClient
from app.main import app


def _paths() -> set[str]:
    return {route.path for route in app.routes}


def test_intelligence_routes_registered():
    paths = _paths()
    assert "/api/intelligence/signals" in paths
    assert "/api/intelligence/clusters" in paths
    assert "/api/intelligence/trends" in paths
    assert "/api/intelligence/changes" in paths
    assert "/api/intelligence/source-health" in paths


def test_legacy_routes_untouched():
    paths = _paths()
    for path in ("/api/radars", "/api/opportunities", "/api/profile", "/api/daily-brief", "/api/dashboard", "/api/pipeline/summary", "/health"):
        assert path in paths


def test_app_boots_with_health_recorder_wired():
    from app.collectors.registry import registry

    with TestClient(app) as client:  # entering the client fires startup wiring
        assert registry._health_recorder is not None
        response = client.get("/health")
        assert response.status_code == 200


def test_intelligence_endpoints_require_auth():
    client = TestClient(app)
    for path in ("/api/intelligence/signals", "/api/intelligence/clusters", "/api/intelligence/trends", "/api/intelligence/changes", "/api/intelligence/source-health"):
        response = client.get(path)
        assert response.status_code in {401, 403}
