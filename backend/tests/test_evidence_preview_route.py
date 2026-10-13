from jose import jwt
from fastapi.testclient import TestClient

from app.main import app


def test_evidence_preview_requires_auth_and_deduplicates():
    payload = {
        "batch_id": "cue-demo-1",
        "items": [
            {
                "source": "cue",
                "url": "https://example.test/lead/1?utm_source=a",
                "external_id": "lead-1",
                "raw_text": "预算三千，寻找 AI 视频广告制作。",
                "payment_signal": "预算三千",
            },
            {
                "source": "cue",
                "url": "https://example.test/lead/1?utm_source=b",
                "external_id": "lead-1",
                "raw_text": "预算三千，寻找 AI 视频广告制作。",
            },
        ],
    }
    client = TestClient(app)
    assert client.post("/api/intelligence/evidence/preview", json=payload).status_code in {401, 403}

    token = jwt.encode({"sub": "00000000-0000-0000-0000-00000000edce", "aud": "authenticated"}, "offline-test-jwt-secret-not-for-deployment", algorithm="HS256")
    response = client.post(
        "/api/intelligence/evidence/preview",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["verification_status"] == "unverified"
    assert body[0]["payment_signal"] == "预算三千"
