from typing import Literal
from fastapi import APIRouter, Depends, Query
from ..api.deps import get_current_user, get_repository
from ..core.security import CurrentUser
from ..repositories.base import Repository
from ..schemas.domain import OpportunityAction, OpportunityRead
from ..services.feedback_service import FeedbackService
router = APIRouter(prefix="/api/opportunities", tags=["Opportunities"])
@router.get("", response_model=list[OpportunityRead])
async def list_opportunities(type: str | None = None, source: str | None = None, location: str | None = None, min_score: int | None = Query(default=None, ge=0, le=100), max_risk: int | None = Query(default=None, ge=0, le=100), status: str | None = None, sort: Literal["recommended", "latest", "score", "budget", "risk"] = "recommended", page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=100), user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    items = repo.list_opportunities(user.id)
    if type: items = [x for x in items if x.type == type]
    if source: items = [x for x in items if x.source == source]
    if location: items = [x for x in items if location in x.location]
    if min_score is not None: items = [x for x in items if x.opportunity_score >= min_score]
    if max_risk is not None: items = [x for x in items if x.risk_score <= max_risk]
    if status: items = [x for x in items if x.status == status]
    key = {"recommended": lambda x: x.opportunity_score, "score": lambda x: x.opportunity_score, "budget": lambda x: x.budget_max, "risk": lambda x: -x.risk_score, "latest": lambda x: x.published_at.timestamp() if x.published_at else 0}[sort]
    return sorted(items, key=key, reverse=True)[(page-1)*page_size:page*page_size]
@router.get("/{opportunity_id}", response_model=OpportunityRead)
async def get_opportunity(opportunity_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return repo.get_opportunity(user.id, opportunity_id)
async def action(opportunity_id: str, new_status: str, payload: OpportunityAction, user: CurrentUser, repo: Repository) -> OpportunityRead:
    item = repo.get_opportunity(user.id, opportunity_id); repo.record_action(opportunity_id, payload, action=new_status)
    saved = repo.save_opportunity(item.model_copy(update={"status": new_status}))
    FeedbackService(repo).record_event(user.id, saved, new_status)
    return saved
@router.post("/{opportunity_id}/save", response_model=OpportunityRead)
async def save(opportunity_id: str, payload: OpportunityAction, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return await action(opportunity_id,"saved",payload,user,repo)
@router.post("/{opportunity_id}/contact", response_model=OpportunityRead)
async def contact(opportunity_id: str, payload: OpportunityAction, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return await action(opportunity_id,"contacted",payload,user,repo)
@router.post("/{opportunity_id}/negotiate", response_model=OpportunityRead)
async def negotiate(opportunity_id: str, payload: OpportunityAction, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return await action(opportunity_id,"negotiating",payload,user,repo)
@router.post("/{opportunity_id}/win", response_model=OpportunityRead)
async def win(opportunity_id: str, payload: OpportunityAction, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return await action(opportunity_id,"won",payload,user,repo)
@router.post("/{opportunity_id}/lose", response_model=OpportunityRead)
async def lose(opportunity_id: str, payload: OpportunityAction, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return await action(opportunity_id,"lost",payload,user,repo)
@router.post("/{opportunity_id}/ignore", response_model=OpportunityRead)
async def ignore(opportunity_id: str, payload: OpportunityAction, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)): return await action(opportunity_id,"ignored",payload,user,repo)
@router.post("/{opportunity_id}/view", response_model=OpportunityRead)
async def view(opportunity_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    item = repo.get_opportunity(user.id, opportunity_id)
    FeedbackService(repo).record_event(user.id, item, "viewed")
    return item
@router.post("/{opportunity_id}/apply", response_model=OpportunityRead)
async def apply(opportunity_id: str, payload: OpportunityAction, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    saved = await action(opportunity_id, "contacted", payload, user, repo)
    FeedbackService(repo).record_event(user.id, saved, "applied")
    return saved
