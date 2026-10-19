from typing import Literal
from uuid import uuid4
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from ..api.deps import get_current_user, get_repository
from ..core.config import get_settings
from ..core.errors import AppError
from ..core.security import CurrentUser
from ..repositories.base import Repository
from ..schemas.identity import IDENTITY_BUSINESS_PRESETS, IDENTITY_ROLE_PRESETS, IdentityProfile
from ..services.provider_verify import verify_tikhub_key

router = APIRouter(prefix="/api/local", tags=["Local Edition"])


class LocalSettingsUpdate(BaseModel):
    ai_mode: Literal["off", "on_demand"]


class TikHubKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str | None = Field(default=None, max_length=200)
    enabled: bool | None = None


class ProviderBudgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    single_run_limit_usd: float | None = None
    daily_limit_usd: float | None = None
    daily_request_limit: int | None = None
    confirm_required: StrictBool | None = None


def _save_provider_config(values: dict):
    from ..core.provider_config import ProviderConfig, read_provider_config, write_provider_config
    current = read_provider_config() or ProviderConfig()
    try:
        merged = ProviderConfig.model_validate({**current.model_dump(), **values})
    except ValidationError as exc:
        raise AppError("PROVIDER_CONFIG_INVALID", "Provider 配置无效：预算需在 USD 1 / 20 请求本机上限内，且单轮不超过每日；密钥需为 8–200 位无空格字符。", 422) from exc
    write_provider_config(merged)
    return merged


def _provider_state() -> dict:
    from ..core.provider_config import provider_state
    return provider_state(get_settings())


@router.get("/identity")
async def get_identity(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    identity = repo.get_identity(user.id)
    return {"identity": identity.model_dump() if identity else None,
            "presets": {"businesses": IDENTITY_BUSINESS_PRESETS, "roles": IDENTITY_ROLE_PRESETS}}


@router.put("/identity")
async def put_identity(value: IdentityProfile, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    return {"identity": repo.save_identity(user.id, value).model_dump()}


@router.get("/providers")
async def list_providers(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    from ..core.provider_config import PLACEHOLDER_PROVIDERS
    return {"tikhub": _provider_state(), "placeholders": PLACEHOLDER_PROVIDERS, "restart_required": False}


@router.put("/providers/tikhub")
async def put_tikhub_key(payload: TikHubKeyUpdate, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    """保存/替换密钥（写入 0700/0600 本机私密配置）；响应只回传掩码。"""
    from ..core.provider_config import KEY_PATTERN, ProviderConfig, read_provider_config
    current = read_provider_config() or ProviderConfig()
    values: dict = {}
    if payload.api_key is not None:
        if not KEY_PATTERN.fullmatch(payload.api_key):
            raise AppError("PROVIDER_KEY_INVALID", "密钥需为 8–200 位无空格的可打印字符。", 422)
        values.update(manage_key=True, tikhub_api_key=payload.api_key,
                      tikhub_manual_enabled=payload.enabled if payload.enabled is not None else True,
                      test_result=None)
    elif payload.enabled is not None:
        if not current.manage_key:
            raise AppError("PROVIDER_KEY_SOURCE_ENV", "当前密钥来自 local.env；先保存新密钥（或先删除）才能调整启用状态。", 409)
        if payload.enabled and not current.tikhub_api_key:
            raise AppError("PROVIDER_KEY_MISSING", "请先保存密钥再启用。", 422)
        values["tikhub_manual_enabled"] = payload.enabled
    if not values:
        raise AppError("PROVIDER_UPDATE_EMPTY", "没有需要保存的改动。", 422)
    _save_provider_config(values)
    return {"tikhub": _provider_state()}


@router.delete("/providers/tikhub")
async def delete_tikhub_key(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    """删除密钥：本机配置接管密钥来源，local.env 里的旧密钥同样被屏蔽。"""
    from ..core.provider_config import ProviderConfig, read_provider_config, write_provider_config
    current = read_provider_config() or ProviderConfig()
    merged = ProviderConfig.model_validate({**current.model_dump(), "manage_key": True, "tikhub_api_key": "", "tikhub_manual_enabled": False, "test_result": None})
    write_provider_config(merged)
    return {"tikhub": _provider_state()}


@router.put("/providers/tikhub/budget")
async def put_tikhub_budget(payload: ProviderBudgetUpdate, user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    """预算与限额：单轮（默认 USD 0.10）、每日（默认 USD 1 / 20 请求）、是否手动确认。"""
    from ..core.provider_config import LOCAL_BUDGET_MAX_USD, LOCAL_DAILY_REQUESTS_MAX
    values = payload.model_dump(exclude_none=True)
    if not values:
        raise AppError("PROVIDER_UPDATE_EMPTY", "没有需要保存的改动。", 422)
    single, daily = values.get("single_run_limit_usd"), values.get("daily_limit_usd")
    requests = values.get("daily_request_limit")
    if single is not None and not 0 < single <= LOCAL_BUDGET_MAX_USD:
        raise AppError("PROVIDER_BUDGET_INVALID", "单轮上限需大于 0 且不超过 USD 1。", 422)
    if daily is not None and not 0 < daily <= LOCAL_BUDGET_MAX_USD:
        raise AppError("PROVIDER_BUDGET_INVALID", "每日上限需大于 0 且不超过 USD 1（本机上限）。", 422)
    if requests is not None and not 1 <= requests <= LOCAL_DAILY_REQUESTS_MAX:
        raise AppError("PROVIDER_BUDGET_INVALID", f"每日请求上限需在 1–{LOCAL_DAILY_REQUESTS_MAX} 之间（本机上限）。", 422)
    if single is not None and daily is not None and single > daily:
        raise AppError("PROVIDER_BUDGET_INVALID", "单轮上限不能高于每日上限。", 422)
    _save_provider_config(values)
    return {"tikhub": _provider_state()}


@router.post("/providers/tikhub/test")
async def test_tikhub_connection(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    """官方轻量端点的连通性测试；不返回密钥，不发起任何内容采集。"""
    from ..core.provider_config import ProviderConfig, effective_key, masked_key, read_provider_config, write_provider_config
    settings = get_settings()
    key, source = effective_key(settings)
    if not key:
        raise AppError("PROVIDER_KEY_MISSING", "尚未保存 TikHub 密钥，无法测试连接。", 409)
    result = await verify_tikhub_key(key, settings.tikhub_base_url)
    config = read_provider_config()
    persisted = False
    if config is not None:
        merged = ProviderConfig.model_validate({**config.model_dump(), "test_result": result})
        write_provider_config(merged)
        persisted = True
    return {**result, "key_source": source, "masked_key": masked_key(key), "persisted": persisted}


@router.get("/sources")
async def hunt_sources(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    """Configuration and succeeded ledger readback only; never probes a provider."""
    from ..collectors.tikhub_catalog import EVIDENCE, source_catalog
    items = source_catalog(get_settings())
    if hasattr(repo, "engine"):
        from sqlalchemy import text
        from ..repositories.postgres import as_uuid
        with repo.engine.connect() as conn:
            sources = set(conn.execute(text("SELECT DISTINCT source FROM billing_calls WHERE user_id=CAST(:uid AS uuid) AND provider='tikhub' AND status='succeeded'"), {"uid": as_uuid(user.id)}).scalars())
        for item in items:
            if item['provider'] == 'tikhub' and item['id'] in sources:
                item['live_verified'] = True
                if item['available']: item['status'] = '可运行 · 已实测'
                item['detail'] = item['detail'].replace('已有契约适配器，非本轮付费实测。', '已完成真实搜索验证。')
    return {"items": items, "platform_count": EVIDENCE["platform_count"],
            "catalog_version": EVIDENCE["version"], "catalog_sha256": EVIDENCE["sha256"],
            "catalog_source": EVIDENCE["source"], "catalog_downloaded_at": EVIDENCE["downloaded_at"]}


def _agent_token_state() -> dict:
    from ..core.agent_token import agent_token_path, masked_token, read_agent_token
    settings = get_settings()
    config = read_agent_token()
    return {
        "configured": bool(config),
        "masked_token": masked_token(config.token) if config else "",
        "created_at": config.created_at if config else "",
        "updated_at": config.updated_at if config else "",
        "rotations": config.rotations if config else 0,
        "path_configured": agent_token_path() is not None,
        "api_base": f"http://127.0.0.1:{settings.local_api_port}/api/agent",
        "restart_required": False,
    }


@router.get("/agent-token")
async def get_agent_token(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    """Agent 令牌状态：只返回掩码、创建时间与轮换次数，永不返回明文。"""
    if get_settings().app_env.lower() != "local":
        raise AppError("AGENT_API_LOCAL_ONLY", "Agent 令牌仅在本机版可用。", 403)
    return _agent_token_state()


@router.post("/agent-token", status_code=201)
async def create_agent_token(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    """生成/重置 Agent 令牌。明文只在本响应出现一次，由用户手动复制；不写入任何日志。"""
    from ..core.agent_token import AgentTokenConfig, generate_token, masked_token, read_agent_token, write_agent_token
    if get_settings().app_env.lower() != "local":
        raise AppError("AGENT_API_LOCAL_ONLY", "Agent 令牌仅在本机版可用。", 403)
    current = read_agent_token()
    token = generate_token()
    now = datetime.now(UTC).isoformat()
    config = write_agent_token(AgentTokenConfig(token=token, created_at=(current.created_at if current else now), rotations=(current.rotations + 1 if current else 1)))
    return {**_agent_token_state(), "plaintext": token, "notice": "明文只显示这一次，请立即复制到本机私密位置；刷新或重新生成后无法再查看，也不会写入日志。"}


@router.delete("/agent-token")
async def revoke_agent_token(user: CurrentUser = Depends(get_current_user), repo: Repository = Depends(get_repository)):
    """吊销 Agent 令牌：删除私密配置文件后立即生效（无需重启）。"""
    from ..core.agent_token import delete_agent_token
    if get_settings().app_env.lower() != "local":
        raise AppError("AGENT_API_LOCAL_ONLY", "Agent 令牌仅在本机版可用。", 403)
    delete_agent_token()
    return _agent_token_state()


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
    return {"ai_mode": repo.get_local_settings(user.id), "paid_api_enabled": settings.paid_api_enabled, "paid_calls_available": bool(settings.paid_api_enabled and settings.local_manual_tikhub_enabled and settings.tikhub_api_key),
            "model_configured": configured, "analysis_available": configured and settings.paid_api_enabled and settings.app_env.lower() != "local",
            "ai_reason": "自动 AI 保持关闭；TikHub 手动采集按已核验价格及单雷达授权执行。"}


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
