from jose import jwt
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_repository
from app.core.security import CurrentUser
from app.main import app
from app.repositories.memory import MemoryRepository


def test_evidence_batch_persists_and_is_idempotent_in_api():
    repository = MemoryRepository()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="api-user")
    client = TestClient(app)
    payload = {
        "batch_id": "cue-api-1",
        "items": [
            {
                "source": "cue",
                "url": "https://example.test/api-lead-1",
                "external_id": "api-lead-1",
                "raw_text": "预算五千，寻找小程序开发服务。",
                "category": "buyer",
                "payment_signal": "预算五千",
            }
        ],
    }
    try:
        first = client.post("/api/intelligence/evidence/batches", json=payload)
        second = client.post("/api/intelligence/evidence/batches", json=payload)
        listed = client.get("/api/intelligence/evidence?category=buyer")
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert first.json()["inserted"] == 1
    assert second.json()["duplicates"] == 1
    assert len(listed.json()) == 1
    assert listed.json()[0]["category"] == "buyer"
