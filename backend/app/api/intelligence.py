from fastapi import APIRouter, Depends, Query

from ..api.deps import get_current_user, get_repository
from ..core.security import CurrentUser
from ..repositories.base import Repository
from ..schemas.intelligence import ChangeEventRead, EventClusterRead, PainPointRead, SignalRead, SourceHealthRead, TrendTopicRead

router = APIRouter(prefix="/api/intelligence", tags=["Intelligence"])


@router.get("/signals", response_model=list[SignalRead])
async def list_signals(
    radar_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    return repo.list_signals(user.id, radar_id=radar_id, limit=limit)


@router.get("/clusters", response_model=list[EventClusterRead])
async def list_clusters(
    radar_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    return repo.list_clusters(user.id, radar_id=radar_id, limit=limit)


@router.get("/trends", response_model=list[TrendTopicRead])
async def list_trends(
    radar_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    return repo.list_trend_topics(user.id, radar_id=radar_id, limit=limit)


@router.get("/changes", response_model=list[ChangeEventRead])
async def list_changes(
    radar_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    return repo.list_change_events(user_id=user.id, radar_id=radar_id, limit=limit)


@router.get("/source-health", response_model=list[SourceHealthRead])
async def source_health(
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    return repo.list_source_health()


@router.get("/pain-points", response_model=list[PainPointRead])
async def pain_points(
    radar_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    return repo.list_pain_points(user.id, radar_id=radar_id, limit=limit)
