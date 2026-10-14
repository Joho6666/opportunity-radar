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
    request_id: str | None = Field(default=None,min_length=8,max_length=100,pattern=r"^[A-Za-z0-9:_-]+$")
    billing_batch_id: str | None = Field(default=None,max_length=100)


def _source_status() -> dict:
    settings = get_settings()
    import math
    from ..collectors.tikhub_cn import DOMESTIC_COLLECTORS
    from ..collectors.tikhub import TikHubCollector
    costs = {}
    def positive_price(price):
        return price if isinstance(price, (int, float)) and not isinstance(price, bool) and math.isfinite(price) and price > 0 else None
    for cls in (*DOMESTIC_COLLECTORS, TikHubCollector):
        from ..services.price_evidence import verified_tikhub_price
        verified = verified_tikhub_price(cls.path)
        costs[cls.slug] = verified[0] if verified else None
    return {
        "github": {"configured": True},
        "hackernews": {"configured": True},
        "rss": {"configured": bool(settings.rss_feeds.strip())},
        **{name: {"configured": bool(settings.tikhub_api_key), "estimated_request_cost_usd": costs.get(name),
                  "validation_status": "contract_only", "live_verified": False} for name in sorted(TIKHUB_SOURCES)},
        "web_search": {"configured": bool(settings.firecrawl_api_key), "estimated_request_cost_usd": positive_price(settings.firecrawl_price_per_request)},
    }


@router.get("/evidence/runtime")
async def evidence_runtime(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    settings = get_settings()
    from .billing import status
    billing = await status(user=user, repo=repo)
    return {
        "paid_api_enabled": settings.paid_api_enabled,
        "billing_batch_id": settings.paid_batch_id or None,
        "billing_batch": billing["batch"],
        "storage_mode": "postgres" if hasattr(repo, "engine") else "memory",
        "warning": "当前使用内存存储，重启后数据不会保留。" if settings.use_in_memory_store else None,
        "sources": _runtime_sources(repo, user.id),
    }


def _runtime_sources(repo, user_id):
    """Live status reflects this tenant's archived response compatibility only."""
    sources = _source_status()
    from ..collectors.tikhub_cn import DOMESTIC_COLLECTORS
    from ..services.price_evidence import verified_tikhub_price
    for cls in DOMESTIC_COLLECTORS:
        entry=sources[cls.slug]
        verified=verified_tikhub_price(cls.path)
        entry["pricing_evidence"]=verified[1] if verified else None
        if not hasattr(repo,"engine"):
            continue
        from sqlalchemy import text
        from ..repositories.postgres import as_uuid
        with repo.engine.connect() as conn:
            row=conn.execute(text("SELECT r.payload,r.query,r.captured_at FROM provider_responses r JOIN billing_calls c ON c.id=r.call_id WHERE r.user_id=CAST(:uid AS uuid) AND r.endpoint=:path AND r.status_code=200 AND c.status='succeeded' ORDER BY r.captured_at DESC LIMIT 1"),{"uid":as_uuid(user_id),"path":cls.path}).mappings().first()
        if row:
            try:
                cls().parse(row["payload"],row["query"] or "")
                entry.update(validation_status="response_compatible",live_verified=True,live_checked_at=row["captured_at"].isoformat())
            except Exception:
                entry.update(validation_status="response_incompatible",live_verified=False)
    return sources


@router.post("/evidence/collect")
async def collect_evidence(
    payload: EvidenceCollectRequest,
    source: EvidenceSource = Query(...),
    query: str = Query(..., min_length=1, max_length=200),
    max_age_days: int = Query(default=30, ge=1, le=3650),
    user: CurrentUser = Depends(get_current_user),
    repo: Repository = Depends(get_repository),
):
    from ..services.collection_control import claim_request, finish_request
    import hashlib, json
    if payload.billing_batch_id and payload.billing_batch_id != get_settings().paid_batch_id:
        raise AppError("PAID_BATCH_UNAUTHORIZED", "本轮批次标识不匹配。", 403)
    if payload.request_id:
        fingerprint = hashlib.sha256(json.dumps([source, query.strip(), payload.cursor, max_age_days, get_settings().paid_batch_id]).encode()).hexdigest()
        cached = claim_request(repo, user.id, payload.request_id, fingerprint)
        if cached is not None:
            return cached
    try:
        result = await _collect_once(payload, source, query.strip(), max_age_days, user, repo)
        if payload.request_id:
            finish_request(repo, user.id, payload.request_id, result)
        return result
    except AppError as exc:
        if payload.request_id:
            finish_request(repo, user.id, payload.request_id, {"code": exc.code, "message": exc.message, "status_code": exc.status_code}, failed=True)
        raise


async def _collect_once(payload, source, query, max_age_days, user, repo):
    collection_id = str(uuid4())
    status = _source_status()[source]
    if source in BILLABLE_SOURCES and not payload.manual_confirmed:
        raise AppError("MANUAL_CONFIRMATION_REQUIRED", "该数据源可能产生费用，请先确认后再采集。", 400)
    if not status["configured"]:
        raise AppError("SOURCE_NOT_CONFIGURED", "该数据源尚未配置，无法采集。", 400)

    if source in BILLABLE_SOURCES and not get_settings().paid_api_enabled:
        raise AppError("PAID_API_DISABLED", "真实付费调用已关闭。", 403)
    if source in BILLABLE_SOURCES and not payload.request_id:
        raise AppError("REQUEST_ID_REQUIRED", "付费采集需要幂等请求标识，避免重复收费。", 400)
    from ..services.billing_gateway import paid_context
    from ..services.collection_control import resolve_cursor, issue_cursor
    domestic = source in {"xiaohongshu", "douyin", "weibo", "zhihu"}
    cursor = resolve_cursor(repo, user.id, source, query, payload.cursor) if domestic and payload.cursor else payload.cursor
    with paid_context(repo, user.id, "evidence", collection_id) as context:
        if domestic or cursor is not None:
            items, provider_error = await registry.search(source, query, cursor=cursor, paged=True)
        else:
            items, provider_error = await registry.search(source, query)
        next_cursor = context.get("next_cursor") or (items[0].metadata.get("next_cursor") if items else None)
    if provider_error:
        code = provider_error.get("error_code", "COLLECTOR_FAILED")
        message = ("付费授权、接口价格或剩余额度不足，请检查费用配置。" if code.startswith(("PAID_", "BILLING_"))
                   else "数据源采集失败，请检查来源状态或保存的响应。")
        raise AppError(code, message, provider_error.get("status_code", 502))
    if domestic:
        next_cursor = issue_cursor(repo, user.id, source, query, next_cursor)

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
        dates = [value if value.tzinfo else value.replace(tzinfo=UTC) for value in (item.published_at, item.updated_at_source) if value]
        if dates and max(dates) < cutoff:
            stale += 1
            continue
        # Keep collector fields available to the evidence inbox without changing
        # the canonical raw text used for classification.
        metadata = dict(item.metadata or {})
        metadata.pop("next_cursor", None)
        metadata["freshness"] = "known" if dates else "unknown"
        metadata.update({"raw_title": item.title, "raw_author": item.author or "", "raw_source": item.source})
        accepted.append(item.model_copy(update={"metadata": metadata}))

    if not accepted:
        repo.record_collection(user.id,collection_id,source,len(items),0,stale=stale)
        return {"batch_id": collection_id, "next_cursor": next_cursor, "billing_batch_id": get_settings().paid_batch_id or None, "request_id": payload.request_id, "fetched": len(items), "inserted": 0, "duplicates": 0, "rejected": rejected, "stale": stale, "records": [], "warning": "内存存储" if get_settings().use_in_memory_store else None}

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
        "next_cursor": next_cursor,
        "billing_batch_id": get_settings().paid_batch_id or None,
        "request_id": payload.request_id,
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


@router.get("/evidence/labels")
async def export_labels(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    from ..services.demand_qualification import text_digest
    from ..services.label_dataset import content_group
    rows=[]
    for record in repo.list_evidence(user.id,limit=100000):
        if record.metadata.get("dataset_kind") == "synthetic":continue
        if record.metadata.get("human_label_digest") != text_digest(record.raw_text):continue
        rows.append({"id":record.evidence_id,"group_id":record.metadata.get("label_group") or record.metadata.get("origin_url") or str(record.url) or content_group(record.raw_text),
                     "text":record.raw_text,"category":record.category,"source":record.source,"source_url":str(record.url),
                     "published_at":record.published_at.isoformat() if record.published_at else None,"captured_at":record.captured_at.isoformat(),
                     "human_label":True,"dataset_kind":"real","assessment":record.assessment})
    return {"rows":rows,"count":len(rows),"target":250,"usage":"human labels only; review source/repost groups before freezing splits"}

@router.post("/evidence/{evidence_id}/convert", response_model=OpportunityRead)
async def convert_evidence(evidence_id: str, payload: EvidenceConversion, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    from ..core.errors import AppError
    evidence = repo.get_evidence(user.id, evidence_id)
    from ..services.demand_qualification import require_actionable
    require_actionable(evidence)
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
