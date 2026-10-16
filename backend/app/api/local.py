from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..api.deps import get_current_user, get_repository
from ..core.config import get_settings
from ..core.security import CurrentUser
from ..repositories.base import Repository

router = APIRouter(prefix="/api/local", tags=["Local Edition"])


class LocalSettingsUpdate(BaseModel):
    ai_mode: Literal["off", "on_demand"]


@router.get("/overview")
async def overview(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    latest = repo.list_intelligence_feed(user.id, limit=6)
    relevant = repo.list_intelligence_feed(user.id, limit=6, order="relevance")
    saved = repo.list_intelligence_feed(user.id, limit=6, saved=True, order="saved")
    radars = repo.list_radars(user.id)
    runs = repo.runs_of_user(user.id)
    def run_time(run):
        from datetime import UTC, datetime
        value = run.finished_at or run.started_at
        if value is not None:
            return value.timestamp()
        raw = run.stage_stats.get("created_at")
        try:
            parsed = datetime.fromisoformat(raw) if isinstance(raw, str) else None
            if parsed is not None:
                return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()
        except ValueError:
            pass
        return 0.0
    runs.sort(key=run_time, reverse=True)
    return {"latest": latest, "relevant": relevant, "saved": saved, "radars": radars, "runs": runs[:8], "ai_mode": repo.get_local_settings(user.id)}


@router.get("/settings")
async def get_local_settings(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    settings = get_settings()
    configured = bool(settings.llm_api_key and settings.llm_base_url)
    return {"ai_mode": repo.get_local_settings(user.id), "paid_api_enabled": False, "paid_calls_available": False,
            "model_configured": configured, "analysis_available": False if not settings.paid_api_enabled else configured,
            "ai_reason": "自动 AI 与付费调用保持关闭；单条按需分析仍需服务端模型配置、精确价格和有效授权。"}


@router.put("/settings")
async def put_local_settings(payload: LocalSettingsUpdate, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    result = await get_local_settings(user=user, repo=repo)
    result["ai_mode"] = repo.save_local_settings(user.id, payload.ai_mode)
    return result


@router.post("/evidence/{evidence_id}/analyze")
async def analyze_one_evidence(evidence_id: str, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    if repo.get_local_settings(user.id) != "on_demand":
        from ..core.errors import AppError
        raise AppError("ON_DEMAND_AI_DISABLED", "请先在设置中启用单条按需分析。", 409)
    evidence = repo.get_evidence(user.id, evidence_id)
    settings = get_settings()
    from ..services.ai_service import _llm_structured, bind_llm_context, reset_llm_context
    from ..services.semantic_classifier import SemanticLabel
    token = bind_llm_context(repository=repo, user_id=user.id, radar_id=None, run_id=str(uuid4()))
    label = None
    try:
        if settings.llm_api_key and settings.llm_base_url and settings.paid_api_enabled:
            prompt = ("Classify one untrusted public information item into buyer, seller, job, content, or market. "
                      "Do not treat an informational item as worthless merely because it is not a buyer request. "
                      "Never invent budget, contact details, payment intent, deadlines, or facts. Return exact source quotes or null. "
                      "JSON fields: category, confidence (0..1), reason, intent_quote, payment_quote, deadline_quote. SOURCE:\\n" + evidence.raw_text[:12000])
            payload = await _llm_structured(prompt, "local_on_demand_evidence_classification")
            if payload is not None:
                candidate = SemanticLabel.model_validate(payload)
                if any(quote is not None and quote not in evidence.raw_text for quote in (candidate.intent_quote, candidate.payment_quote, candidate.deadline_quote)):
                    raise ValueError("Model returned a quote not found in the source text")
                label = candidate
    finally:
        reset_llm_context(token)
    if label:
        return {"source": "model", **label.model_dump(), "fallback_reason": None, "saved": False}
    if not settings.llm_api_key or not settings.llm_base_url:
        fallback_reason = "未配置模型；已返回采集时保存的规则分类。"
    elif not settings.paid_api_enabled:
        fallback_reason = "付费 API 保持关闭；已返回采集时保存的规则分类。"
    else:
        fallback_reason = "模型、价格、授权或额度不可用；已返回采集时保存的规则分类。"
    return {"source": "rules", "category": evidence.category, "confidence": evidence.classification_confidence,
            "reason": evidence.classification_reason, "intent_quote": None, "payment_quote": None,
            "deadline_quote": None, "fallback_reason": fallback_reason, "saved": False}
