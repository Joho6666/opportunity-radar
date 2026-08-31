import re
from typing import Any
from pydantic import TypeAdapter
from ..ai.provider import get_provider
from ..schemas.domain import OpportunityAnalysis, ProfileAnalysis, ProfileAnalyzeRequest, QueryPlanItem, RadarCreate, RawItem
from .risk_rules import risk_adjustment


async def _llm_structured(prompt: str, schema_name: str) -> dict[str, Any] | None:
    """Calls the configured LLM for a JSON object; returns None when unavailable or invalid."""
    provider = get_provider()
    if provider is None: return None
    try:
        payload = await provider.structured_output(f"{prompt}\n\n只输出一个 JSON 对象，不要包含 markdown 代码块或其他文本。字段说明：{schema_name}", schema_name)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


async def analyze_profile(request: ProfileAnalyzeRequest) -> ProfileAnalysis:
    prompt = f"分析以下自我描述，提取身份 identity（英文标签列表）、技能 skills（name + level: beginner/intermediate/strong/expert）、目标 goals（仅限 job/client/project/business）和推荐方向 recommended_directions：\n{request.text}"
    payload = await _llm_structured(prompt, "identity: string[], skills: {{name: string, level: string}}[], goals: ('job'|'client'|'project'|'business')[], recommended_directions: string[]")
    if payload is not None:
        try: return TypeAdapter(ProfileAnalysis).validate_python(payload)
        except Exception: pass
    text = request.text.lower(); skills = []
    for name, level in [("PPT", "strong"), ("Python", "intermediate"), ("AI Agent", "strong"), ("n8n", "strong"), ("网站开发", "intermediate"), ("STM32", "beginner")]:
        if name.lower() in text: skills.append({"name": name, "level": level})
    goals = [goal for goal, terms in {"job": ["实习", "工作", "求职"], "client": ["兼职", "客户", "接单"], "project": ["项目"], "business": ["商机"]}.items() if any(term in text for term in terms)] or ["client"]
    return ProfileAnalysis(identity=["student"] if "学生" in text or "大学" in text else ["freelancer"], skills=skills, goals=goals, recommended_directions=["AI 自动化外包", "远程 AI 实习", "PPT 项目", "小型 Web 项目"])


async def plan_queries(radar: RadarCreate) -> list[QueryPlanItem]:
    sources = radar.sources or ["mock"]
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
    locations = radar.locations or (["桂林", "远程"] if "桂林" in radar.goal else ["线上"])
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


async def analyze_raw_item(item: RawItem, profile_skills: list[str]) -> OpportunityAnalysis:
    prompt = f"判断以下内容是否是值得接单的真实机会，并给出结构化分析。用户技能：{profile_skills}。标题：{item.title}；内容：{item.content}；链接：{item.url}"
    payload = await _llm_structured(prompt, "is_opportunity: boolean, type: ('job'|'client'|'project'|'business'|'github'), title: string, summary: string, location: string, work_mode: ('online'|'offline'|'hybrid'), skills: string[], budget_min: number, budget_max: number, estimated_hours: number, commercial_intent/skill_match/conversion_probability/urgency/competition/risk: number(0-100), reasons: string[], warnings: string[]")
    if payload is not None:
        try: return TypeAdapter(OpportunityAnalysis).validate_python(payload)
        except Exception: pass
    text = f"{item.title} {item.content}"; lower = text.lower(); adjustment, rule_warnings = risk_adjustment(item)
    if "PPT" in text: values = ("client", 200, 300, 3, 96, 82, 88, 45, 18, ["PPT"])
    elif "实习" in text: values = ("job", 4000, 6000, 80, 92, 70, 70, 55, 25, ["Python", "AI Agent", "n8n"])
    elif "n8n" in lower: values = ("project", 800, 1600, 12, 89, 65, 75, 50, 31, ["n8n", "自动化"])
    else: values = ("project", 1500, 3000, 30, 76, 55, 60, 55, 43, ["网站开发", "小程序"])
    kind, min_budget, max_budget, hours, match, conversion, urgency, competition, risk, skills = values
    return OpportunityAnalysis(is_opportunity=True, type=kind, title=item.title, summary=item.content[:220], location="桂林" if "桂林" in text else "远程", work_mode="online", skills=skills, budget_min=min_budget, budget_max=max_budget, estimated_hours=hours, commercial_intent=95, skill_match=match, conversion_probability=conversion, urgency=urgency, competition=competition, risk=min(100, risk + adjustment), reasons=["技能高度匹配", "发布时间较短", "预算合理", "交付难度可控"], warnings=rule_warnings or ["请确认需求范围与修改次数"])
