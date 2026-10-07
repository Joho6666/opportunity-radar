from contextvars import ContextVar, Token
import logging
import re
import time
from typing import Any
from pydantic import TypeAdapter
from ..ai.provider import get_provider
from ..core.config import get_settings
from ..schemas.domain import OpportunityAnalysis, PreferenceState, ProfileAnalysis, ProfileAnalyzeRequest, QueryPlanItem, RadarCreate, RawItem
from .risk_rules import risk_adjustment

logger = logging.getLogger(__name__)
_llm_context: ContextVar[dict[str, Any] | None] = ContextVar("llm_context", default=None)


def bind_llm_context(**values) -> Token:
    current = dict(_llm_context.get() or {})
    current.update(values)
    return _llm_context.set(current)


def reset_llm_context(token: Token) -> None:
    _llm_context.reset(token)


def _record_llm_call(schema_name: str, provider: str | None, model: str, latency_ms: int, fallbacked: bool, stage: str | None = None, usage: dict | None = None) -> None:
    context = _llm_context.get() or {}
    repository = context.get("repository")
    if repository is None:
        return
    settings = get_settings()
    prompt_tokens = usage.get("prompt_tokens") if usage else None
    completion_tokens = usage.get("completion_tokens") if usage else None
    cost_usd = None
    if prompt_tokens is not None and completion_tokens is not None and (settings.llm_price_input_per_mtok or settings.llm_price_output_per_mtok):
        cost_usd = (prompt_tokens * settings.llm_price_input_per_mtok + completion_tokens * settings.llm_price_output_per_mtok) / 1_000_000
    repository.record_llm_call(
        user_id=context.get("user_id"),
        radar_id=context.get("radar_id"),
        run_id=context.get("run_id"),
        provider=provider,
        model=model,
        latency_ms=latency_ms,
        fallbacked=fallbacked,
        schema_name=schema_name,
        stage=stage,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
    )


async def _llm_structured(prompt: str, schema_name: str) -> dict[str, Any] | None:
    """Calls the configured LLM for a JSON object; returns None when unavailable or invalid."""
    settings = get_settings()
    provider = get_provider()
    started = time.perf_counter()
    fallbacked = True
    payload: dict[str, Any] | None = None
    usage: dict | None = None
    try:
        if provider is None:
            return None
        result, usage = await provider.structured_output_with_usage(f"{prompt}\n\n只输出一个 JSON 对象，不要包含 markdown 代码块或其他文本。字段说明：{schema_name}", schema_name)
        if isinstance(result, dict):
            payload = result
            fallbacked = False
            return payload
        return None
    except Exception:
        logger.exception("llm structured output failed", extra={"schema_name": schema_name})
        usage = None
        return None
    finally:
        _record_llm_call(schema_name, "openai-compatible" if provider else None, settings.llm_model, int((time.perf_counter() - started) * 1000), fallbacked, stage=schema_name, usage=usage)


async def analyze_profile(request: ProfileAnalyzeRequest) -> ProfileAnalysis:
    prompt = f"分析以下自我描述，提取身份 identity（英文标签列表）、技能 skills（name + level: beginner/intermediate/strong/expert）、目标 goals（仅限 job/client/project/business）和推荐方向 recommended_directions：\n{request.text}"
    payload = await _llm_structured(prompt, "identity: string[], skills: {{name: string, level: string}}[], goals: ('job'|'client'|'project'|'business')[], recommended_directions: string[]")
    if payload is not None:
        try:
            return TypeAdapter(ProfileAnalysis).validate_python(payload)
        except Exception:
            pass
    text = request.text.lower()
    skills = []
    for name, level in [("PPT", "strong"), ("Python", "intermediate"), ("AI Agent", "strong"), ("n8n", "strong"), ("网站开发", "intermediate"), ("STM32", "beginner")]:
        if name.lower() in text:
            skills.append({"name": name, "level": level})
    goals = [goal for goal, terms in {"job": ["实习", "工作", "求职"], "client": ["兼职", "客户", "接单"], "project": ["项目"], "business": ["商机"]}.items() if any(term in text for term in terms)] or ["client"]
    return ProfileAnalysis(identity=["student"] if "学生" in text or "大学" in text else ["freelancer"], skills=skills, goals=goals, recommended_directions=["AI 自动化外包", "远程 AI 实习", "PPT 项目", "小型 Web 项目"])


async def plan_queries(radar: RadarCreate, preference: PreferenceState | None = None) -> list[QueryPlanItem]:
    sources = radar.sources or ["mock"]
    if preference:
        sources = sorted(sources, key=lambda slug: preference.source_weights.get(slug, 0.0), reverse=True)
    prompt = f"为机会雷达生成搜索查询计划。目标：{radar.goal}；关键词：{radar.keywords}；地区：{radar.locations}；来源：{sources}。生成不超过 10 条查询，source 必须来自已选来源。"
    payload = await _llm_structured(prompt, "queries: {{query: string, source: string, priority: number(0-100)}}[]，键名为 queries")
    if payload is not None and isinstance(payload.get("queries"), list):
        try:
            queries = TypeAdapter(list[QueryPlanItem]).validate_python(payload["queries"])
            queries = [item for item in queries if item.source in sources] or queries
            if queries:
                return queries[:10]
        except Exception:
            pass
    tokens = radar.keywords or re.findall(r"PPT|AI 自动化|n8n|小程序|网站开发|AI Agent", radar.goal) or ["兼职"]
    if preference:
        extra = [key for key, weight in sorted(preference.keyword_weights.items(), key=lambda item: item[1], reverse=True) if weight > 0][:5]
        tokens = list(dict.fromkeys([*extra, *tokens]))
        tokens = [token for token in tokens if preference.keyword_weights.get(token, 0) >= -1] or tokens
    locations = radar.locations or (["桂林", "远程"] if "桂林" in radar.goal else ["线上"])
    if preference:
        locations = sorted(locations, key=lambda item: preference.location_weights.get(item, 0.0), reverse=True)
    output: list[QueryPlanItem] = []
    index = 0
    for source in sources:
        for location in locations:
            for skill in tokens:
                output.append(QueryPlanItem(query=f"{location} {skill} 有偿", source=source, priority=max(70, 92 - index * 3)))
                index += 1
                if len(output) >= 10:
                    return output
    return output[:10]


async def analyze_raw_item(item: RawItem, profile_skills: list[str], has_commercial_signal: bool = True) -> OpportunityAnalysis:
    prompt = f"判断以下内容是否是值得接单的真实机会，并给出结构化分析。用户技能：{profile_skills}。标题：{item.title}；内容：{item.content}；链接：{item.url}"
    payload = await _llm_structured(prompt, "is_opportunity: boolean, type: ('job'|'client'|'project'|'business'|'github'), title: string, summary: string, location: string, work_mode: ('online'|'offline'|'hybrid'), skills: string[], budget_min: number, budget_max: number, estimated_hours: number, commercial_intent/skill_match/conversion_probability/urgency/competition/risk: number(0-100), reasons: string[], warnings: string[]")
    adjustment, rule_warnings = risk_adjustment(item)
    if payload is not None:
        try:
            analysis = TypeAdapter(OpportunityAnalysis).validate_python(payload)
            analysis.risk = min(100, analysis.risk + adjustment)
            analysis.warnings = list(dict.fromkeys([*analysis.warnings, *rule_warnings]))
            return analysis
        except Exception:
            pass
    if not has_commercial_signal:
        # Deterministic fallback must not fabricate opportunities: without any
        # commercial/payment signal, the item is recorded but not scored as one.
        return OpportunityAnalysis(is_opportunity=False, type="project", title=item.title, summary=item.content[:220], location="线上", work_mode="online", skills=[], budget_min=0, budget_max=0, estimated_hours=1, commercial_intent=0, skill_match=0, conversion_probability=0, urgency=0, competition=0, risk=min(100, adjustment), reasons=[], warnings=rule_warnings)
    text = f"{item.title} {item.content}"
    lower = text.lower()
    if "PPT" in text:
        values = ("client", 200, 300, 3, 96, 82, 88, 45, 18, ["PPT"])
    elif "实习" in text:
        values = ("job", 4000, 6000, 80, 92, 70, 70, 55, 25, ["Python", "AI Agent", "n8n"])
    elif "n8n" in lower:
        values = ("project", 800, 1600, 12, 89, 65, 75, 50, 31, ["n8n", "自动化"])
    else:
        values = ("project", 1500, 3000, 30, 76, 55, 60, 55, 43, ["网站开发", "小程序"])
    kind, min_budget, max_budget, hours, match, conversion, urgency, competition, risk, skills = values
    return OpportunityAnalysis(is_opportunity=True, type=kind, title=item.title, summary=item.content[:220], location="桂林" if "桂林" in text else "远程", work_mode="online", skills=skills, budget_min=min_budget, budget_max=max_budget, estimated_hours=hours, commercial_intent=95, skill_match=match, conversion_probability=conversion, urgency=urgency, competition=competition, risk=min(100, risk + adjustment), reasons=["技能高度匹配", "发布时间较短", "预算合理", "交付难度可控"], warnings=rule_warnings or ["请确认需求范围与修改次数"])


# ---- Phase 2: cheap-model calls (fast model preferred, None ⇒ rule fallbacks) ----


def _fast_model(settings) -> str:
    return settings.llm_fast_model or settings.llm_model


async def _llm_structured_fast(prompt: str, schema_name: str) -> dict[str, Any] | None:
    """Cheap-model variant used for signal extraction / listener compilation."""
    settings = get_settings()
    provider = get_provider()
    if provider is None:
        return None
    started = time.perf_counter()
    payload: dict[str, Any] | None = None
    usage: dict | None = None
    try:
        result, usage = await provider.structured_output_with_usage(f"{prompt}\n\n只输出一个 JSON 对象，不要包含 markdown 代码块或其他文本。字段说明：{schema_name}", schema_name, model=_fast_model(settings))
        if isinstance(result, dict):
            payload = result
    except Exception:
        logger.exception("llm fast call failed", extra={"schema_name": schema_name})
        usage = None
    finally:
        _record_llm_call(schema_name, "openai-compatible", _fast_model(settings), int((time.perf_counter() - started) * 1000), payload is None, stage=schema_name, usage=usage)
    return payload


async def extract_signals_llm(text: str) -> list | None:
    """Multi-signal extraction for cluster representatives. None = unavailable."""
    if not text.strip():
        return None
    prompt = (
        "从以下公开信息中抽取所有有价值的商业信号（0-4 条）。signal_type 只能取：pain_point, purchase_intent, hiring, outsourcing, "
        "product_request, feature_request, complaint, price_change, funding, policy, tender, technology_growth, creator_trend, consumer_trend, supply_shortage。"
        "payment_evidence=true 仅当文中出现明确付费/预算/报价证据。\n内容：\n" + text[:2500]
    )
    payload = await _llm_structured_fast(prompt, "signals: {{signal_type: string, title: string, keywords: string[], commercial_intent: number(0-100), payment_evidence: boolean, urgency: number(0-100), confidence: number(0-100)}}[]，键名为 signals")
    if payload is None or not isinstance(payload.get("signals"), list):
        return None
    from ..schemas.intelligence import SignalRead, SignalType

    allowed = set(SignalType.__args__) if hasattr(SignalType, "__args__") else set()
    signals: list[SignalRead] = []
    for item in payload["signals"][:4]:
        if not isinstance(item, dict) or item.get("signal_type") not in allowed:
            continue
        try:
            signals.append(SignalRead(
                signal_type=item["signal_type"],
                title=str(item.get("title") or "")[:200],
                keywords=[str(keyword) for keyword in (item.get("keywords") or [])[:8]],
                intent="commercial" if (item.get("commercial_intent") or 0) >= 40 else "informational",
                commercial_intent=max(0, min(100, int(item.get("commercial_intent") or 0))),
                payment_evidence=bool(item.get("payment_evidence")),
                urgency=max(0, min(100, int(item.get("urgency") or 0))),
                confidence=max(0, min(100, int(item.get("confidence") or 0))),
                extraction_method="llm",
            ))
        except Exception:
            continue
    return signals or None


async def compile_listener_llm(description: str) -> "Any | None":
    """Compile a natural-language listener into gate config; None = unavailable."""
    if not description.strip():
        return None
    from ..schemas.intelligence import RadarListenerConfig
    from pydantic import TypeAdapter

    prompt = (
        "把下面的自然语言监听需求编译为结构化配置。positive_signals：应该出现的关键词/短语；negative_signals：出现即排除的关键词；"
        "search_queries：用于公开网络搜索的查询建议（≤5 条）；exclusion_rules：字面排除规则。\n监听需求：\n" + description[:2000]
    )
    payload = await _llm_structured_fast(prompt, "positive_signals: string[], negative_signals: string[], search_queries: string[], exclusion_rules: string[]")
    if payload is None:
        return None
    try:
        return TypeAdapter(RadarListenerConfig).validate_python(payload)
    except Exception:
        return None


async def describe_pain_solutions(theme: str, summary: str) -> tuple[str, int] | None:
    """Current solutions + satisfaction (0-100) for a pain theme; None = unavailable."""
    prompt = f"针对用户集中抱怨的问题「{theme}」，列出当前市场已有解决方案（≤150 字），并给出 0-100 的整体满意度估计（越高越成熟）。\n背景：{summary[:500]}"
    payload = await _llm_structured_fast(prompt, "current_solutions: string, solution_satisfaction: number(0-100)")
    if payload is None or "current_solutions" not in payload:
        return None
    try:
        satisfaction = max(0, min(100, int(payload.get("solution_satisfaction") or 50)))
        return str(payload["current_solutions"]), satisfaction
    except Exception:
        return None
