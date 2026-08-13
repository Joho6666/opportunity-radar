from fastapi import APIRouter, Depends
from ..api.deps import get_current_user, get_repository
from ..core.security import CurrentUser
from ..repositories.memory import MemoryRepository
from ..schemas.domain import OpportunityRead
router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])
@router.get("", response_model=list[OpportunityRead])
async def pipeline(user: CurrentUser = Depends(get_current_user), repo: MemoryRepository = Depends(get_repository)): return repo.list_opportunities(user.id)
