from datetime import date
from fastapi import APIRouter, Depends
from ..api.deps import get_current_user, get_repository
from ..core.errors import AppError
from ..core.security import CurrentUser
from ..repositories.base import Repository
from ..schemas.domain import DailyBriefRead
router = APIRouter(prefix="/api/daily-brief", tags=["Daily Brief"])
@router.get("", response_model=DailyBriefRead)
async def current(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return repo.daily_brief(user.id)
@router.get("/{brief_date}", response_model=DailyBriefRead)
async def by_date(brief_date: date, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    stored = repo.get_brief(user.id, brief_date)
    if stored is None:
        raise AppError("BRIEF_NOT_FOUND", "该日期没有已生成的简报。", 404)
    return stored
