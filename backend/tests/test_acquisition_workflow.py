import asyncio
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.api.deps import get_current_user,get_repository
from app.core.security import CurrentUser
from app.core.errors import AppError
from app.main import app
from app.repositories.memory import MemoryRepository
from app.schemas.domain import RadarCreate
from app.schemas.evidence import EvidenceBatch,EvidenceReview,EvidenceConversion
from app.schemas.pipeline import PipelinePatch,QuoteRequest
from app.api.intelligence import convert_evidence
from app.services.acquisition_service import quote_draft


def build(repo,uid="sales-user"):
    radar=repo.create_radar(uid,RadarCreate(name="客户",goal="寻找真实的文档制作与企业广告需求",sources=["rss"]))
    evidence=repo.upsert_evidence_batch(uid,EvidenceBatch(batch_id=str(uuid4()),items=[{"source":"rss","url":f"https://example.com/{uuid4()}","raw_text":"找人做PPT，预算待沟通，月底交付。","category":"buyer"}])).records[0]
    repo.review_evidence(uid,evidence.evidence_id,EvidenceReview(verification_status="verified",notes="人工核实原帖"))
    item=asyncio.run(convert_evidence(evidence.evidence_id,EvidenceConversion(title="PPT需求",summary="找人做PPT，月底交付。"),CurrentUser(uid),repo))
    return evidence,item


def test_closed_loop_uses_only_recorded_outcomes():
    repo=MemoryRepository();evidence,item=build(repo)
    for state in ["verified","ready_to_contact","contacted","replied","quoted","negotiating","won"]:
        item=repo.update_pipeline("sales-user",item.id,PipelinePatch(status=state,**({"actual_revenue":1800,"actual_cost":300,"actual_hours":8} if state == "won" else {})))
    assert repo.won_revenue("sales-user") == 1800
    assert item.pipeline["actual_cost"] == 300
    assert item.actual_hours == 8
    assert item.pipeline["contacted_at"] and item.pipeline["replied_at"]
    assert len(repo.action_log) == 7
    repo.update_pipeline("sales-user",item.id,PipelinePatch(notes="补充记录"))
    assert repo.won_revenue("sales-user") == 1800


def test_drafts_do_not_fake_sales_events():
    repo=MemoryRepository();_,item=build(repo)
    app.dependency_overrides[get_current_user]=lambda:CurrentUser("sales-user")
    app.dependency_overrides[get_repository]=lambda:repo
    try:
        client=TestClient(app)
        quoted=client.post(f"/api/pipeline/{item.id}/quote",json={"hourly_rate":100,"estimated_hours":5,"scope":"包含十页PPT排版与动画制作","service_type":"PPT"})
        assert quoted.status_code == 200 and len(quoted.json()["plans"]) == 3
        communication=client.post(f"/api/pipeline/{item.id}/communication")
        assert communication.json()["requires_human_review"] is True
        assert item.source_url in communication.json()["text"]
        assert repo.get_opportunity("sales-user",item.id).status == "new"
        assert repo.won_revenue("sales-user") == 0
        assert repo.get_opportunity("sales-user",item.id).budget_max == 0
    finally:app.dependency_overrides.clear()


def test_invalidated_evidence_blocks_contact_and_cross_user_update():
    repo=MemoryRepository();evidence,item=build(repo)
    repo.review_evidence("sales-user",evidence.evidence_id,EvidenceReview(verification_status="invalidated"))
    with pytest.raises(AppError):repo.update_pipeline("sales-user",item.id,PipelinePatch(status="contacted"))
    with pytest.raises(AppError):repo.update_pipeline("stranger",item.id,PipelinePatch(status="won",actual_revenue=999))
    with pytest.raises(AppError):repo.update_pipeline("sales-user",item.id,PipelinePatch(status="lost"))


def test_pg_pipeline_persists_and_preserves_revenue():
    from app.core.config import get_settings
    from app.database.client import create_database_engine
    from app.repositories.postgres import PostgresRepository
    if not get_settings().database_url:pytest.skip("DATABASE_URL not configured")
    repo=PostgresRepository(create_database_engine());uid=str(uuid4());_,item=build(repo,uid)
    repo.update_pipeline(uid,item.id,PipelinePatch(status="won",actual_revenue=1600,actual_cost=300,actual_hours=6))
    repo.update_pipeline(uid,item.id,PipelinePatch(notes="重启后补充跟进"))
    second=PostgresRepository(create_database_engine())
    read=second.get_opportunity(uid,item.id)
    assert second.won_revenue(uid) == 1600
    assert read.actual_revenue == 1600 and read.pipeline["actual_cost"] == 300
    assert read.actual_hours == 6 and read.closed_at is not None


def test_worker_replay_does_not_execute_twice():
    from app.services.radar_run_service import RadarRunService
    class Registry:
        calls=0
        async def search(self,*args):self.calls+=1;return [],None
    repo=MemoryRepository();uid="replay";radar=repo.create_radar(uid,RadarCreate(name="R",goal="寻找真实客户的公开需求"));run=repo.create_run(radar.id);registry=Registry()
    service=RadarRunService(repo,registry)
    first=asyncio.run(service.run(uid,radar.id,run.id));second=asyncio.run(service.run(uid,radar.id,run.id))
    assert first.status == second.status == "completed"
    assert registry.calls == 1


def test_synthetic_browser_fixtures_are_excluded_from_acquisition_metrics():
    from app.services.acquisition_metrics import acquisition_metrics
    from app.schemas.evidence import EvidenceBatch,EvidenceReview
    repo=MemoryRepository()
    _,item=build(repo)
    record=repo.get_evidence('sales-user',item.evidence_id)
    repo.upsert_evidence_batch('sales-user',EvidenceBatch(batch_id='synthetic-updated',items=[{'source':record.source,'url':record.url,'external_id':record.external_id,'raw_text':record.raw_text+'（Synthetic QA）','category':'buyer','metadata':{'dataset_kind':'synthetic'}}]))
    report=acquisition_metrics(repo,'sales-user')
    assert report['buyer_evidence'] == 0
    assert report['verified_buyer'] == 0
    assert report['actual_revenue'] is None
    assert not report['pipeline_counts']
