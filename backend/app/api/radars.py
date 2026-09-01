from fastapi import APIRouter, Depends
from ..api.deps import get_current_user, get_repository
from ..core.security import CurrentUser
from ..repositories.base import Repository
from ..schemas.domain import RadarCreate, RadarRead, RadarRunRead
from ..workers.queue import enqueue_radar_run

router = APIRouter(prefix="/api/radars", tags=["Radars"])


@router.get("", response_model=list[RadarRead])
async def list_radars(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return repo.list_radars(user.id)


@router.post("", response_model=RadarRead, status_code=201)
async def create_radar(value: RadarCreate, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return repo.create_radar(user.id, value)


@router.get("/{radar_id}", response_model=RadarRead)
async def get_radar(radar_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return repo.get_radar(user.id, radar_id)


@router.put("/{radar_id}", response_model=RadarRead)
async def put_radar(radar_id: str, value: RadarCreate, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    old = repo.get_radar(user.id, radar_id)
    return repo.save_radar(old.model_copy(update=value.model_dump()))


@router.delete("/{radar_id}", status_code=204)
async def delete_radar(radar_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    repo.delete_radar(user.id, radar_id)


@router.post("/{radar_id}/run", response_model=RadarRunRead, status_code=202)
async def run_radar(radar_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    repo.get_radar(user.id, radar_id)
    run = repo.create_run(radar_id)
    await enqueue_radar_run(user.id, radar_id, run.id)
    return run


@router.post("/{radar_id}/pause", response_model=RadarRead)
async def pause(radar_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return repo.save_radar(repo.get_radar(user.id, radar_id).model_copy(update={"status": "paused"}))


@router.post("/{radar_id}/resume", response_model=RadarRead)
async def resume(radar_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return repo.save_radar(repo.get_radar(user.id, radar_id).model_copy(update={"status": "active"}))


@router.get("/runs/{run_id}", response_model=RadarRunRead)
async def get_run(run_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return repo.get_run(user.id, run_id)
