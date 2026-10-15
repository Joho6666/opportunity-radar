import pytest
from app.schemas.pipeline import PipelinePatch,QuoteRequest
from app.core.errors import AppError
from app.repositories.memory import MemoryRepository
from test_acquisition_workflow import build


def test_legacy_quote_preserved_and_old_replay_never_rolls_back_latest():
    repo=MemoryRepository();_,item=build(repo)
    legacy=item.model_copy(update={'pipeline':{'quote_draft':{'legacy':True}}})
    repo.opportunities[item.id]=legacy
    first=repo.update_pipeline('sales-user',item.id,PipelinePatch(quote_draft={'one':1},quote_request_id='request-one',expected_quote_version=0))
    assert first.pipeline['quote_versions'][0]['version'] == 0
    assert first.pipeline['quote_versions'][0]['draft'] == {'legacy':True}
    repo.update_pipeline('sales-user',item.id,PipelinePatch(quote_draft={'two':2},quote_request_id='request-two',expected_quote_version=1))
    replay=repo.update_pipeline('sales-user',item.id,PipelinePatch(quote_draft={'one':1},quote_request_id='request-one',expected_quote_version=0,notes='new note retained'))
    assert replay.pipeline['quote_draft'] == {'two':2}
    assert replay.pipeline['notes'] == 'new note retained'
    assert len(replay.pipeline['quote_versions']) == 3


def test_followup_sent_quote_requires_existing_version_and_no_fake_stage():
    repo=MemoryRepository();_,item=build(repo)
    with pytest.raises(AppError) as error:
        repo.update_pipeline('sales-user',item.id,PipelinePatch(follow_up_event={'request_id':'send-quote','kind':'quote_sent','text':'manual','quote_version':42}))
    assert error.value.code == 'QUOTE_VERSION_NOT_FOUND'
    note=repo.update_pipeline('sales-user',item.id,PipelinePatch(follow_up_event={'request_id':'note-event','kind':'note','text':'checked source'}))
    assert note.status == item.status
    with pytest.raises(AppError) as error:
        repo.update_pipeline('sales-user',item.id,PipelinePatch(follow_up_event={'request_id':'note-event','kind':'note','text':'different'}))
    assert error.value.code == 'FOLLOW_UP_REQUEST_CONFLICT'


def test_invalid_payment_total_and_followup_timezone_rejected():
    with pytest.raises(ValueError):
        QuoteRequest(hourly_rate=100,estimated_hours=1,service_type='PPT',scope='test editable scope',payment_milestones=[{'label':'deposit','percent':30}])
    repo=MemoryRepository();_,item=build(repo)
    with pytest.raises(AppError) as error:
        repo.update_pipeline('sales-user',item.id,PipelinePatch(next_follow_up_at='2026-10-14T12:00:00'))
    assert error.value.code == 'FOLLOW_UP_TIMEZONE_REQUIRED'
