from fastapi.testclient import TestClient
from app.api.deps import get_current_user, get_repository
from app.core.security import CurrentUser
from app.main import app
from app.repositories.memory import MemoryRepository
from app.schemas.domain import RadarCreate


def setup(repo, user="u1"):
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(id=user)
    repo.create_radar(user, RadarCreate(name="r", goal="寻找适合当前能力的客户项目机会"))
    return TestClient(app)


def teardown():
    app.dependency_overrides.clear()


def payload(external_id="x", category="market"):
    return {"batch_id": "b", "items": [{"source": "rss", "url": "https://example.test/x", "external_id": external_id, "raw_text": "企业明确寻找视频制作服务，预算待沟通。", "category": category}]}


def test_review_updates_status_category_and_notes_then_conversion_is_idempotent():
    repo = MemoryRepository(); client = setup(repo)
    try:
        evidence = client.post("/api/intelligence/evidence/batches", json=payload()).json()["records"][0]
        reviewed = client.patch(f"/api/intelligence/evidence/{evidence['evidence_id']}/review", json={"verification_status": "verified", "category": "buyer", "notes": "人工确认买方需求", "title": "视频制作服务", "summary": "企业寻找视频制作服务", "budget_min": None, "budget_max": None})
        assert reviewed.status_code == 200
        assert reviewed.json()["verification_status"] == "verified"
        assert reviewed.json()["category"] == "buyer"
        first = client.post(f"/api/intelligence/evidence/{evidence['evidence_id']}/convert", json={"title": "视频制作服务", "summary": "企业寻找视频制作服务", "budget_min": None, "budget_max": None}).json()
        second = client.post(f"/api/intelligence/evidence/{evidence['evidence_id']}/convert", json={"title": "视频制作服务", "summary": "企业寻找视频制作服务", "budget_min": None, "budget_max": None}).json()
        assert first["id"] == second["id"]
        assert first["source_url"] == evidence["url"]
        assert first["evidence_id"] == evidence["evidence_id"]
        assert first["budget_min"] == 0 and first["budget_max"] == 0
        assert first["metadata"]["budget_unknown"] is True
    finally: teardown()


def test_invalidated_and_unverified_cannot_convert_and_cross_user_cannot_review():
    repo = MemoryRepository(); client = setup(repo)
    try:
        evidence = client.post("/api/intelligence/evidence/batches", json=payload("x2")).json()["records"][0]
        assert client.post(f"/api/intelligence/evidence/{evidence['evidence_id']}/convert", json={"title": "视频制作服务", "summary": "企业寻找视频制作服务", "budget_min": None, "budget_max": None}).status_code == 409
        assert client.patch(f"/api/intelligence/evidence/{evidence['evidence_id']}/review", json={"verification_status": "invalidated"}).status_code == 200
        assert client.post(f"/api/intelligence/evidence/{evidence['evidence_id']}/convert", json={"title": "视频制作服务", "summary": "企业寻找视频制作服务", "budget_min": None, "budget_max": None}).status_code == 409
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="u2")
        assert client.patch(f"/api/intelligence/evidence/{evidence['evidence_id']}/review", json={"verification_status": "verified"}).status_code == 404
    finally: teardown()


def test_verified_non_buyer_requires_buyer_category_for_sales_conversion():
    repo = MemoryRepository(); client = setup(repo)
    try:
        evidence = client.post("/api/intelligence/evidence/batches", json=payload("x3", "content")).json()["records"][0]
        client.patch(f"/api/intelligence/evidence/{evidence['evidence_id']}/review", json={"verification_status": "verified"})
        assert client.post(f"/api/intelligence/evidence/{evidence['evidence_id']}/convert", json={"title": "视频制作服务", "summary": "企业寻找视频制作服务", "budget_min": None, "budget_max": None}).status_code == 409
    finally: teardown()
