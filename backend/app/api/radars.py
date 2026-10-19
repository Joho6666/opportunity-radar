from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..api.deps import get_current_user, get_repository
from ..core.security import CurrentUser
from ..core.config import get_settings
from ..repositories.base import Repository
from ..schemas.domain import RadarCreate, RadarRead, RadarRunRead, SourceSlug
from ..services.identity_defaults import apply_identity_defaults, identity_defaults_for
from ..services.listener_service import compile_listener
from ..workers.queue import enqueue_radar_run

router = APIRouter(prefix="/api/radars", tags=["Radars"])


def _with_identity_defaults(user_id: str, value: RadarCreate, repo: Repository) -> RadarCreate:
    """抓单雷达未填写的条件从个人身份设定补齐；用户显式选择永不覆盖，旧雷达不受影响。"""
    return apply_identity_defaults(value, identity_defaults_for(repo, user_id))


async def _with_listener_config(user_id: str, value: RadarCreate, repo: Repository, radar_id: str | None = None) -> RadarCreate:
    """Compile the natural-language listener when the description changed."""
    if not value.listener_description:
        return value
    previous = None
    if radar_id:
        try:
            previous = repo.get_radar(user_id, radar_id)
        except Exception:
            previous = None
    if previous is not None and previous.listener_description == value.listener_description and previous.listener_config:
        return value  # unchanged description keeps its cached config
    compiled = await compile_listener(value)
    return value.model_copy(update={"listener_config": compiled.model_dump()})


@router.get("", response_model=list[RadarRead])
async def list_radars(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return repo.list_radars(user.id)


@router.post("", response_model=RadarRead, status_code=201)
async def create_radar(value: RadarCreate, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    value = _with_identity_defaults(user.id, value, repo)
    value = await _with_listener_config(user.id, value, repo)
    return repo.create_radar(user.id, value)


@router.get("/{radar_id}", response_model=RadarRead)
async def get_radar(radar_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return repo.get_radar(user.id, radar_id)


@router.put("/{radar_id}", response_model=RadarRead)
async def put_radar(radar_id: str, value: RadarCreate, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    old = repo.get_radar(user.id, radar_id)
    value = _with_identity_defaults(user.id, value, repo)
    value = await _with_listener_config(user.id, value, repo, radar_id=radar_id)
    changes = value.model_dump()
    # model_copy does not validate nested dictionaries. Revalidate the policy,
    # and invalidate cached query plans after the user's search input changes.
    if any(getattr(old, key) != getattr(value, key) for key in ("goal", "keywords", "sources", "source_config", "mode", "listener_description")):
        changes["queries"] = []
    return repo.save_radar(RadarRead.model_validate({**old.model_dump(), **changes}))


@router.delete("/{radar_id}", status_code=204)
async def delete_radar(radar_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    repo.delete_radar(user.id, radar_id)


@router.post("/{radar_id}/run", response_model=RadarRunRead, status_code=202)
async def run_radar(radar_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    radar = repo.get_radar(user.id, radar_id)
    run = repo.create_run(radar_id)
    if run.status == "queued":
        try:
            await enqueue_radar_run(user.id, radar_id, run.id)
        except Exception as exc:
            if get_settings().app_env.lower() != "local":
                raise
            run = repo.save_run(run.model_copy(update={"stage_stats": {**run.stage_stats, "dispatch_status": "waiting_for_redis", "dispatch_error": getattr(exc, "code", "QUEUE_UNAVAILABLE")}}))
    return run


class SourceRerun(BaseModel):
    source: SourceSlug
    query: str = Field(min_length=1, max_length=100)
    confirmed: bool = False


@router.post("/{radar_id}/rerun-source", response_model=RadarRunRead, status_code=202)
async def rerun_source(radar_id: str, payload: SourceRerun, user: CurrentUser = Depends(get_current_user),
                       repo: Repository = Depends(get_repository)):
    """One platform only, one short query, explicit paid confirmation; never auto-retries."""
    radar = repo.get_radar(user.id, radar_id)
    if payload.source not in radar.sources:
        raise HTTPException(status_code=400, detail="该平台不在雷达来源中。")
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="需要人工确认本次付费调用。")
    query = payload.query.strip()
    if not query or len(query) > 100:
        raise HTTPException(status_code=400, detail="短词须为 1–100 字。")
    run = repo.create_run(radar_id)
    if run.status == "queued":
        run = repo.save_run(run.model_copy(update={"stage_stats": {
            **run.stage_stats, "source_override": payload.source, "query_override": query,
            "rerun_reason": "manual_short_keyword"}}))
        try:
            await enqueue_radar_run(user.id, radar_id, run.id)
        except Exception as exc:
            if get_settings().app_env.lower() != "local":
                raise
            run = repo.save_run(run.model_copy(update={"stage_stats": {
                **run.stage_stats, "dispatch_status": "waiting_for_redis",
                "dispatch_error": getattr(exc, "code", "QUEUE_UNAVAILABLE")}}))
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


from pydantic import BaseModel,Field

class RunRecovery(BaseModel):
    reason: str = Field(min_length=10,max_length=500)

@router.post("/runs/{run_id}/recover",response_model=RadarRunRead)
async def recover_run(run_id:str,payload:RunRecovery,user:CurrentUser=Depends(get_current_user),repo:Repository=Depends(get_repository)):
    """Mark a stale run failed and pause its Radar; never retry paid calls automatically."""
    return repo.recover_run(user.id,run_id,payload.reason)
