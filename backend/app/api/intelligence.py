from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..api.deps import get_current_user, get_repository
from ..collectors.registry import registry
from ..core.config import get_settings
from ..core.errors import AppError
from ..core.security import CurrentUser
from ..repositories.base import Repository
from ..schemas.intelligence import ChangeEventRead, EventClusterRead, PainPointRead, SignalRead, SourceHealthRead, TrendTopicRead
from ..schemas.evidence import EvidenceBatch, EvidenceRecord, EvidenceUpsertResult
from ..services.evidence_ingest import normalize_evidence
from ..services.evidence_from_raw import raw_items_to_evidence_batch

router = APIRouter(prefix="/api/intelligence", tags=["Intelligence"])

EvidenceSource = Literal["github", "hackernews", "rss", "tikhub", "web_search"]


class EvidenceCollectRequest(BaseModel):
    manual_confirmed: bool = False


def _source_status() -> dict[str, dict[str, bool]]:
    settings = get_settings()
    return {
        "github": {"configured": True},
        "hackernews": {"configured": True},
        "rss": {"configured": bool(settings.rss_feeds.strip())},
        "tikhub": {"configured": bool(settings.tikhub_api_key)},
        "web_search": {"configured": bool(settings.firecrawl_api_key)},
    }


@router.get("/evidence/runtime")
async def evidence_runtime(user: CurrentUser = Depends(get_current_user)):
    settings = get_settings()
    return {
        "storage_mode": "memory" if settings.use_in_memory_store else "postgres",
        "warning": "当前使用内存存储，重启后数据不会保留。" if settings.use_in_memory_store else None,
        "sources": _source_status(),
    }


@router.post("/evidence/collect")
async def collect_evidence(
    payload: EvidenceCollectRequest,
    source: EvidenceSource = Query(...),
    query: str = Query(..., min_length=1, max_length=200),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    billable = {"tikhub", "web_search"}
    status = _source_status()[source]
    if source in billable and not payload.manual_confirmed:
        raise AppError("MANUAL_CONFIRMATION_REQUIRED", "该数据源可能产生费用，请先确认后再采集。", 400)
    if not status["configured"]:
        raise AppError("SOURCE_NOT_CONFIGURED", "该数据源尚未配置，无法采集。", 400)

    items, provider_error = await registry.search(source, query)
    if provider_error:
        raise AppError(provider_error.get("error_code", "COLLECTOR_FAILED"), "数据源采集失败，请稍后重试。", 502)

    accepted = []
    rejected = 0
    for item in items:
        text = (item.content or item.title or "").strip()
        if len(text) < 10:
            rejected += 1
            continue
        # Keep collector fields available to the evidence inbox without changing
        # the canonical raw text used for classification.
        metadata = dict(item.metadata or {})
        metadata.update({"raw_title": item.title, "raw_author": item.author or "", "raw_source": item.source})
        accepted.append(item.model_copy(update={"metadata": metadata}))

    if not accepted:
        return {"batch_id": None, "fetched": len(items), "inserted": 0, "duplicates": 0, "rejected": rejected, "records": [], "warning": "内存存储" if get_settings().use_in_memory_store else None}

    batch = raw_items_to_evidence_batch(
        source="tiktok" if source == "tikhub" else source,
        query=query,
        items=accepted,
        batch_id=str(uuid4()),
    )
    result = repo.upsert_evidence_batch(user.id, batch)
    return {
        "batch_id": result.batch_id,
        "fetched": len(items),
        "inserted": result.inserted,
        "duplicates": result.duplicates,
        "rejected": rejected,
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
    category: str | None = Query(default=None, pattern="^(buyer|content|market)$"),
    limit: int = Query(default=100, ge=1, le=500),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    return repo.list_evidence(user.id, category=category, limit=limit)


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
