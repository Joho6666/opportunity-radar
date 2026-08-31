from fastapi import APIRouter, Depends
from ..api.deps import get_current_user, get_repository
from ..core.security import CurrentUser
from ..repositories.base import Repository
from ..schemas.domain import ProfileAnalysis, ProfileAnalyzeRequest, ProfileRead, ProfileUpsert
from ..services.ai_service import analyze_profile
router = APIRouter(prefix="/api/profile", tags=["Profile"])
@router.get("", response_model=ProfileRead)
async def get_profile(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return repo.get_profile(user.id)
@router.put("", response_model=ProfileRead)
async def put_profile(value: ProfileUpsert, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return repo.save_profile(user.id, value)
@router.post("/analyze", response_model=ProfileAnalysis)
async def profile_analyze(value: ProfileAnalyzeRequest, _: CurrentUser = Depends(get_current_user)): return await analyze_profile(value)
