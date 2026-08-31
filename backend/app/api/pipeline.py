from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..api.deps import get_current_user, get_repository
from ..core.security import CurrentUser
from ..repositories.base import Repository
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
