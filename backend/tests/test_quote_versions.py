from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import get_repository,get_current_user
from app.core.security import CurrentUser
from app.repositories.memory import MemoryRepository
from app.schemas.pipeline import PipelinePatch
from test_acquisition_workflow import build


def test_quote_preview_has_distinct_deliverables_and_no_writes():
    repo=MemoryRepository();_,item=build(repo)
    app.dependency_overrides[get_current_user]=lambda:CurrentUser("sales-user")
    app.dependency_overrides[get_repository]=lambda:repo
    try:
        response=TestClient(app).post(f"/api/pipeline/{item.id}/quote/preview",json={"hourly_rate":100,"estimated_hours":5,"scope":"20页PPT排版和动画交付","service_type":"PPT"})
        assert response.status_code == 200
        draft=response.json()
        assert len({p["scope"] for p in draft["plans"]}) == 3
        assert all(p["profit_before_tax"] is None for p in draft["plans"])
        assert repo.get_opportunity("sales-user",item.id).pipeline == item.pipeline
    finally:app.dependency_overrides.clear()


def test_quote_versions_idempotent_and_followups_append_only():
    repo=MemoryRepository();_,item=build(repo)
    first=repo.update_pipeline("sales-user",item.id,PipelinePatch(quote_draft={"status":"draft","plans":[]},quote_request_id="request-123",expected_quote_version=0))
    assert len(first.pipeline["quote_versions"]) == 1
    again=repo.update_pipeline("sales-user",item.id,PipelinePatch(quote_draft={"status":"draft","plans":[]},quote_request_id="request-123",expected_quote_version=0))
    assert len(again.pipeline["quote_versions"]) == 1
    next_item=repo.update_pipeline("sales-user",item.id,PipelinePatch(follow_up_event={"request_id":"event-123","kind":"note","text":"查看原文，尚未联系","quote_version":1}))
    assert next_item.pipeline["follow_up_history"][0]["quote_version"] == 1
    assert next_item.status == "new"


def test_stale_quote_cannot_overwrite_new_version():
    import pytest
    from app.core.errors import AppError
    repo=MemoryRepository();_,item=build(repo)
    repo.update_pipeline("sales-user",item.id,PipelinePatch(quote_draft={"one":1},expected_quote_version=0))
    with pytest.raises(AppError) as err:
        repo.update_pipeline("sales-user",item.id,PipelinePatch(quote_draft={"two":2},expected_quote_version=0))
    assert err.value.code == "QUOTE_VERSION_CONFLICT"
