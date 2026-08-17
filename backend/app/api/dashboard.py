from fastapi import APIRouter, Depends
from pydantic import BaseModel
from ..api.deps import get_current_user, get_repository
from ..core.security import CurrentUser
from ..repositories.memory import MemoryRepository
router = APIRouter(prefix="/api", tags=["Dashboard"])
class DashboardRead(BaseModel):
    scanned: int; found: int; matched: int; recommended: int; potential_income_min: int; potential_income_max: int; won_count: int; won_revenue: int
@router.get("/dashboard", response_model=DashboardRead)
async def dashboard(user: CurrentUser = Depends(get_current_user), repo: MemoryRepository = Depends(get_repository)):
    items = repo.list_opportunities(user.id); won = [x for x in items if x.status == "won"]; recommended = [x for x in items if x.recommendation == "强烈推荐"]
    return DashboardRead(scanned=repo.scanned_count(user.id), found=len(items), matched=len([x for x in items if x.match_score >= 75]), recommended=len(recommended), potential_income_min=sum(x.budget_min for x in recommended), potential_income_max=sum(x.budget_max for x in recommended), won_count=len(won), won_revenue=repo.won_revenue(user.id))
