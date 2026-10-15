from fastapi.testclient import TestClient
from app.api.deps import get_current_user,get_repository
from app.core.security import CurrentUser
from app.main import app
from app.schemas.evidence import EvidenceBatch,EvidenceReview
from test_evidence_conversion_postgres import pg


def test_review_assessment_audit_and_label_export_tenant_contract(pg):
    repo,uid=pg
    data={'source':'rss','url':'https://example.test/label','raw_text':'需要做个网站，找人帮我，预算未定。','category':'buyer'}
    record=repo.upsert_evidence_batch(uid,EvidenceBatch(batch_id='label-pg',items=[data])).records[0]
    repo.review_evidence(uid,record.evidence_id,EvidenceReview(category='buyer',notes='Contract: user checked original',assessment={'availability':'open','eligibility':'eligible'},label_group='original-topic'))
    assert repo.get_evidence(uid,record.evidence_id).assessment['availability'] == 'open'
    app.dependency_overrides[get_repository]=lambda:repo
    app.dependency_overrides[get_current_user]=lambda:CurrentUser(uid)
    try:
        client=TestClient(app)
        exported=client.get('/api/intelligence/evidence/labels').json()
        assert exported['count'] == 1
        assert exported['rows'][0]['group_id'] == 'original-topic'
        synthetic=repo.upsert_evidence_batch(uid,EvidenceBatch(batch_id='synthetic-label',items=[{**data,'url':'https://example.test/synthetic','metadata':{'dataset_kind':'synthetic'}}])).records[0]
        repo.review_evidence(uid,synthetic.evidence_id,EvidenceReview(category='buyer'))
        assert client.get('/api/intelligence/evidence/labels').json()['count'] == 1
        app.dependency_overrides[get_current_user]=lambda:CurrentUser('00000000-0000-0000-0000-000000009abc')
        assert client.get('/api/intelligence/evidence/labels').json()['count'] == 0
        repo.upsert_evidence_batch(uid,EvidenceBatch(batch_id='label-updated',items=[{**data,'raw_text':data['raw_text']+'需求已取消。'}]))
        app.dependency_overrides[get_current_user]=lambda:CurrentUser(uid)
        assert client.get('/api/intelligence/evidence/labels').json()['count'] == 0
    finally:app.dependency_overrides.clear()
