from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.schemas.domain import OpportunityRead, RadarCreate
from app.schemas.evidence import EvidenceBatch, EvidenceReview


@pytest.fixture
def pg():
    from app.core.config import get_settings
    from app.database.client import create_database_engine
    from app.repositories.postgres import PostgresRepository

    if not get_settings().database_url:
        pytest.skip("DATABASE_URL not configured")
    engine = create_database_engine()
    if engine is None:
        pytest.skip("postgres engine unavailable")
    repo = PostgresRepository(engine)
    user_id = str(uuid4())
    repo.get_profile(user_id)
    return repo, user_id


def _verified_buyer(repo, user_id):
    radar = repo.create_radar(user_id, RadarCreate(name="r", goal="寻找适合当前能力的客户项目机会"))
    batch = EvidenceBatch(batch_id=str(uuid4()), items=[{"source": "rss", "url": f"https://example.test/{uuid4()}", "external_id": str(uuid4()), "raw_text": "企业明确寻找视频制作服务，预算待沟通。", "category": "buyer"}])
    evidence = repo.upsert_evidence_batch(user_id, batch).records[0]
    repo.review_evidence(user_id, evidence.evidence_id, EvidenceReview(verification_status="verified", category="buyer"))
    return radar, evidence


def _opportunity(radar_id, evidence_id):
    return OpportunityRead(id=str(uuid4()), radar_id=radar_id, type="client", title="视频制作服务", summary="企业寻找视频制作服务", source="rss", source_url="https://example.test/x", location="线上", work_mode="online", budget_min=0, budget_max=0, estimated_hours=1, estimated_hourly_rate=(0, 0), match_score=0, opportunity_score=0, conversion_probability=0, risk_score=0, recommendation="待人工评估", status="new", evidence_id=evidence_id)


def _count(repo, evidence_id):
    with repo.engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM opportunities WHERE evidence_id=:eid"), {"eid": evidence_id}).scalar()


def test_concurrent_conversion_creates_one_opportunity(pg):
    repo, user_id = pg
    radar, evidence = _verified_buyer(repo, user_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(repo.convert_evidence, user_id, evidence.evidence_id, _opportunity(radar.id, evidence.evidence_id)) for _ in range(2)]
        results = [future.result() for future in futures]
    assert results[0].id == results[1].id
    assert _count(repo, evidence.evidence_id) == 1
    assert repo.get_evidence(user_id, evidence.evidence_id).converted_opportunity_id == results[0].id


def test_conversion_links_orphan_from_half_finished_attempt(pg):
    repo, user_id = pg
    radar, evidence = _verified_buyer(repo, user_id)
    orphan = repo.add_opportunity(_opportunity(radar.id, evidence.evidence_id), user_id)
    assert repo.get_evidence(user_id, evidence.evidence_id).converted_opportunity_id is None

    saved = repo.convert_evidence(user_id, evidence.evidence_id, _opportunity(radar.id, evidence.evidence_id))

    assert saved.id == orphan.id
    assert _count(repo, evidence.evidence_id) == 1
    assert repo.get_evidence(user_id, evidence.evidence_id).converted_opportunity_id == orphan.id
