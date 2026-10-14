from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..api.deps import get_current_user, get_repository
from ..core.security import CurrentUser
from ..repositories.base import Repository
from ..schemas.pipeline import PipelinePatch, QuoteRequest
from ..schemas.domain import OpportunityRead, OpportunityStatus
router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])
class PipelineSummary(BaseModel):
    income: int
    counts: dict[str, int]
    won_count: int
@router.get("", response_model=list[OpportunityRead])
async def pipeline(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return repo.list_opportunities(user.id)
@router.get("/summary", response_model=PipelineSummary)
async def summary(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    items = repo.list_opportunities(user.id)
    counts = {status: len([x for x in items if x.status == status]) for status in OpportunityStatus.__args__}
    return PipelineSummary(income=repo.won_revenue(user.id), counts=counts, won_count=counts["won"])

@router.patch("/{opportunity_id}", response_model=OpportunityRead)
async def update(opportunity_id: str, payload: "PipelinePatch", user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return repo.update_pipeline(user.id,opportunity_id,payload)

@router.post("/{opportunity_id}/quote")
async def quote(opportunity_id: str, payload: "QuoteRequest", user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    from ..services.acquisition_service import quote_draft
    item=repo.get_opportunity(user.id,opportunity_id)
    draft=quote_draft(item,payload)
    repo.update_pipeline(user.id,opportunity_id,PipelinePatch(quote_draft=draft,service_type=payload.service_type))
    return draft

@router.post("/{opportunity_id}/quote/preview")
async def preview_quote(opportunity_id: str, payload: QuoteRequest, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    from ..services.acquisition_service import quote_draft
    return quote_draft(repo.get_opportunity(user.id,opportunity_id),payload)

@router.post("/{opportunity_id}/communication")
async def communication(opportunity_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    from ..services.acquisition_service import outreach_draft
    draft=outreach_draft(repo.get_opportunity(user.id,opportunity_id))
    repo.update_pipeline(user.id,opportunity_id,PipelinePatch(communication_draft=draft))
    return {"status":"draft","text":draft,"requires_human_review":True}
