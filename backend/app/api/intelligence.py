from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..api.deps import get_current_user, get_repository
from ..collectors.registry import registry
from ..core.config import get_settings
from ..core.errors import AppError
from ..core.security import CurrentUser
from ..repositories.base import Repository
from ..schemas.intelligence import ChangeEventRead, EventClusterRead, PainPointRead, SignalRead, SourceHealthRead, TrendTopicRead
from ..schemas.evidence import EvidenceBatch, EvidenceRecord, EvidenceUpsertResult, EvidenceReview, EvidenceConversion
from ..schemas.domain import OpportunityRead
from ..services.evidence_ingest import normalize_evidence
from ..services.evidence_from_raw import raw_items_to_evidence_batch

router = APIRouter(prefix="/api/intelligence", tags=["Intelligence"])

EvidenceSource = Literal["github", "hackernews", "rss", "tikhub", "xiaohongshu", "weibo", "zhihu", "douyin", "web_search"]
TIKHUB_SOURCES = {"tikhub", "xiaohongshu", "weibo", "zhihu", "douyin"}
BILLABLE_SOURCES = TIKHUB_SOURCES | {"web_search"}


class EvidenceCollectRequest(BaseModel):
    cursor: str | None = Field(default=None,max_length=100)
    manual_confirmed: bool = False


def _source_status() -> dict[str, dict[str, bool]]:
    settings = get_settings()
    return {
        "github": {"configured": True},
        "hackernews": {"configured": True},
        "rss": {"configured": bool(settings.rss_feeds.strip())},
        **{name: {"configured": bool(settings.tikhub_api_key)} for name in sorted(TIKHUB_SOURCES)},
        "web_search": {"configured": bool(settings.firecrawl_api_key)},
    }


@router.get("/evidence/runtime")
async def evidence_runtime(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    settings = get_settings()
    return {
        "paid_api_enabled": settings.paid_api_enabled,
        "storage_mode": "postgres" if hasattr(repo, "engine") else "memory",
        "warning": "当前使用内存存储，重启后数据不会保留。" if settings.use_in_memory_store else None,
        "sources": _source_status(),
    }


@router.post("/evidence/collect")
async def collect_evidence(
    payload: EvidenceCollectRequest,
    source: EvidenceSource = Query(...),
    query: str = Query(..., min_length=1, max_length=200),
    max_age_days: int = Query(default=30, ge=1, le=3650),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    collection_id = str(uuid4())
    status = _source_status()[source]
    if source in BILLABLE_SOURCES and not payload.manual_confirmed:
        raise AppError("MANUAL_CONFIRMATION_REQUIRED", "该数据源可能产生费用，请先确认后再采集。", 400)
    if not status["configured"]:
        raise AppError("SOURCE_NOT_CONFIGURED", "该数据源尚未配置，无法采集。", 400)

    if source in BILLABLE_SOURCES and not get_settings().paid_api_enabled:
        raise AppError("PAID_API_DISABLED", "真实付费调用已关闭。", 403)
    from ..services.billing_gateway import paid_context
    with paid_context(repo, user.id, "evidence", collection_id):
        if payload.cursor is not None:
            items, provider_error = await registry.search(source, query, cursor=payload.cursor, paged=True)
        else:
            items, provider_error = await registry.search(source, query)
    if provider_error:
        raise AppError(provider_error.get("error_code", "COLLECTOR_FAILED"), "数据源采集失败，请稍后重试。", 502)

    accepted = []
    rejected = 0
    stale = 0
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    for item in items:
        text = (item.content or item.title or "").strip()
        if len(text) < 10:
            rejected += 1
            continue
        # An old post is rarely still an open request (search often returns years-old threads).
        if item.published_at and (item.published_at if item.published_at.tzinfo else item.published_at.replace(tzinfo=UTC)) < cutoff:
            stale += 1
            continue
        # Keep collector fields available to the evidence inbox without changing
        # the canonical raw text used for classification.
        metadata = dict(item.metadata or {})
        metadata.update({"raw_title": item.title, "raw_author": item.author or "", "raw_source": item.source})
        accepted.append(item.model_copy(update={"metadata": metadata}))

    if not accepted:
        repo.record_collection(user.id,collection_id,source,len(items),0,stale=stale)
        return {"batch_id": None, "fetched": len(items), "inserted": 0, "duplicates": 0, "rejected": rejected, "stale": stale, "records": [], "warning": "内存存储" if get_settings().use_in_memory_store else None}

    batch = raw_items_to_evidence_batch(
        source="tiktok" if source == "tikhub" else source,
        query=query,
        items=accepted,
        batch_id=collection_id,
    )
    from ..services.semantic_classifier import enrich_batch
    from ..services.billing_gateway import paid_context
    with paid_context(repo, user.id, "evidence", collection_id):
        batch = await enrich_batch(batch)
    result = repo.upsert_evidence_batch(user.id, batch)
    repo.record_collection(user.id,collection_id,source,len(items),result.inserted,result.duplicates,stale)
    return {
        "batch_id": result.batch_id,
        "next_cursor": items[0].metadata.get("next_cursor") if items else None,
        "fetched": len(items),
        "inserted": result.inserted,
        "duplicates": result.duplicates,
        "rejected": rejected,
        "stale": stale,
        "records": result.records,
        "warning": "内存存储，重启后数据不会保留。" if get_settings().use_in_memory_store else None,
    }


@router.post("/evidence/preview", response_model=list[EvidenceRecord])
async def preview_evidence(
    batch: EvidenceBatch,
    user: CurrentUser = Depends(get_current_user),
):
    """Normalize a collector batch before persistence; this endpoint is intentionally side-effect free."""
    return normalize_evidence(batch)


@router.post("/evidence/batches", response_model=EvidenceUpsertResult)
async def ingest_evidence(
    batch: EvidenceBatch,
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    return repo.upsert_evidence_batch(user.id, batch)


@router.get("/evidence", response_model=list[EvidenceRecord])
async def list_evidence(
    category: str | None = Query(default=None, pattern="^(buyer|seller|job|content|market)$"),
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    return repo.list_evidence(user.id, category=category, limit=limit)

@router.patch("/evidence/{evidence_id}/review", response_model=EvidenceRecord)
async def review_evidence(evidence_id: str, payload: EvidenceReview, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return repo.review_evidence(user.id, evidence_id, payload)

@router.post("/evidence/{evidence_id}/convert", response_model=OpportunityRead)
async def convert_evidence(evidence_id: str, payload: EvidenceConversion, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    from ..core.errors import AppError
    evidence = repo.get_evidence(user.id, evidence_id)
    if evidence.verification_status != "verified":
        raise AppError("EVIDENCE_NOT_VERIFIED", "只有人工核实的证据才能转为机会。", 409)
    if evidence.category != "buyer":
        raise AppError("EVIDENCE_NOT_BUYER", "销售机会必须是买方证据。", 409)
    if evidence.converted_opportunity_id:
        return repo.get_opportunity(user.id, evidence.converted_opportunity_id)
    radars = repo.list_radars(user.id)
    if not radars:
        raise AppError("RADAR_REQUIRED", "请先创建一个机会雷达。", 409)
    metadata = dict(evidence.metadata)
    title = payload.title.strip()
    summary = payload.summary.strip()
    if not title or not summary:
        raise AppError("CONVERSION_INPUT_REQUIRED", "请填写机会标题与摘要。", 422)
    if (payload.budget_min is None) != (payload.budget_max is None) or (payload.budget_min is not None and payload.budget_min > payload.budget_max):
        raise AppError("INVALID_BUDGET", "预算上下限应同时提供，且上限不能小于下限；未知请留空。", 422)
    low = payload.budget_min if payload.budget_min is not None else 0
    high = payload.budget_max if payload.budget_max is not None else 0
    unknown = payload.budget_min is None
    oid = str(uuid4())
    from ..services.acquisition_priority import priority
    ranking=priority(evidence,skills=[skill.name for skill in repo.get_profile(user.id).skills],published_at=evidence.published_at)
    item = OpportunityRead(id=oid, radar_id=(metadata.get("radar_id") if any(r.id == metadata.get("radar_id") for r in radars) else radars[0].id), type="client", title=title, summary=summary, source=evidence.source, source_url=str(evidence.url), published_at=evidence.published_at, location="线上", work_mode="online", budget_min=low, budget_max=high, estimated_hours=1, estimated_hourly_rate=(low, high), match_score=0, opportunity_score=ranking["score"], conversion_probability=0, risk_score=0, recommendation="待人工评估", status="new", reasons=ranking["reasons"], warnings=["预算未知，未进行金额推断"] if unknown else [], verification_status="verified", evidence_id=evidence.evidence_id, metadata={"evidence_id": evidence.evidence_id, "provenance": {"source": evidence.source, "url": str(evidence.url)}, "budget_unknown": unknown, "hours_unknown": True, "currency": "CNY" if not unknown else None, "budget_source": "manual_review" if not unknown else "unknown", "score_kind": "prediction", "priority_breakdown": ranking, "radar_id": metadata.get("radar_id", "")})
    return repo.convert_evidence(user.id, evidence_id, item)


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
