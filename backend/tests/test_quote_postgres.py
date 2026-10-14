from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import text
from app.core.errors import AppError
from app.schemas.pipeline import PipelinePatch,QuoteRequest
from app.services.acquisition_service import quote_draft
from test_evidence_conversion_postgres import pg,_verified_buyer,_opportunity


def test_postgres_quote_concurrency_isolation_and_followup_persistence(pg):
    repo,uid=pg
    radar,evidence=_verified_buyer(repo,uid)
    item=repo.convert_evidence(uid,evidence.evidence_id,_opportunity(radar.id,evidence.evidence_id))
    patch=PipelinePatch(quote_draft={'plans':[]},quote_request_id='concurrent-quote',expected_quote_version=0)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=[f.result() for f in [pool.submit(repo.update_pipeline,uid,item.id,patch) for _ in range(2)]]
    assert all(len(r.pipeline['quote_versions']) == 1 for r in results)
    event=PipelinePatch(follow_up_event={'request_id':'persisted-event','kind':'note','text':'Synthetic persistence contract only','quote_version':1})
    for _ in range(2):repo.update_pipeline(uid,item.id,event)
    saved=repo.get_opportunity(uid,item.id)
    assert len(saved.pipeline['follow_up_history']) == 1
    assert saved.pipeline['follow_up_history'][0]['source_url'] == item.source_url
    with pytest.raises(AppError):repo.update_pipeline('00000000-0000-0000-0000-000000009abc',item.id,patch)
    with repo.engine.connect() as conn:
        before=conn.execute(text('SELECT count(*) FROM opportunity_actions WHERE opportunity_id=:id'),{'id':item.id}).scalar()
    quote_draft(saved,QuoteRequest(hourly_rate=100,estimated_hours=2,scope='Synthetic contract scope only',service_type='website',internal_hourly_cost=40,direct_cost=10))
    with repo.engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM opportunity_actions WHERE opportunity_id=:id'),{'id':item.id}).scalar() == before


def test_quote_cost_math_and_idempotency_conflicts():
    from test_acquisition_workflow import build
    from app.repositories.memory import MemoryRepository
    repo=MemoryRepository();_,item=build(repo)
    draft=quote_draft(item,QuoteRequest(hourly_rate=100,estimated_hours=5,scope='20页PPT排版和动画交付',service_type='PPT',internal_hourly_cost=40,direct_cost=50))
    assert draft['plans'][0]['profit_before_tax'] == 300
    assert draft['payment_milestones'][0]['percent'] == 50
    patch=PipelinePatch(quote_draft=draft,quote_request_id='same-request',expected_quote_version=0)
    repo.update_pipeline('sales-user',item.id,patch)
    with pytest.raises(AppError,match='相同请求标识'):
        repo.update_pipeline('sales-user',item.id,PipelinePatch(quote_draft={'different':True},quote_request_id='same-request',expected_quote_version=0))
