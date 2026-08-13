import re
from ..core.config import get_settings
from ..schemas.domain import OpportunityAnalysis, ProfileAnalysis, ProfileAnalyzeRequest, QueryPlanItem, RawItem, RadarCreate
from .risk_rules import risk_adjustment


async def analyze_profile(request: ProfileAnalyzeRequest) -> ProfileAnalysis:
    text = request.text.lower(); skills = []
    for name, level in [("PPT", "strong"), ("Python", "intermediate"), ("AI Agent", "strong"), ("n8n", "strong"), ("网站开发", "intermediate"), ("STM32", "beginner")]:
        if name.lower() in text: skills.append({"name": name, "level": level})
    goals = [goal for goal, terms in {"job": ["实习", "工作", "求职"], "client": ["兼职", "客户", "接单"], "project": ["项目"], "business": ["商机"]}.items() if any(term in text for term in terms)] or ["client"]
    return ProfileAnalysis(identity=["student"] if "学生" in text or "大学" in text else ["freelancer"], skills=skills, goals=goals, recommended_directions=["AI 自动化外包", "远程 AI 实习", "PPT 项目", "小型 Web 项目"])


async def plan_queries(radar: RadarCreate) -> list[QueryPlanItem]:
    tokens = radar.keywords or re.findall(r"PPT|AI 自动化|n8n|小程序|网站开发", radar.goal) or ["兼职"]
    locations = radar.locations or (["桂林", "远程"] if "桂林" in radar.goal else ["线上"])
    output = [QueryPlanItem(query=f"{location} {skill} 有偿", source="mock", priority=max(70, 92-index*3)) for index, (location, skill) in enumerate((pair for location in locations for pair in [(location, skill) for skill in tokens]))]
    return output[:10] or [QueryPlanItem(query=radar.goal, source="mock", priority=80)]


async def analyze_raw_item(item: RawItem, profile_skills: list[str]) -> OpportunityAnalysis:
    text = f"{item.title} {item.content}"; lower = text.lower(); adjustment, rule_warnings = risk_adjustment(item)
    if "PPT" in text: values = ("client", 200, 300, 3, 96, 82, 88, 45, 18, ["PPT"])
    elif "实习" in text: values = ("job", 4000, 6000, 80, 92, 70, 70, 55, 25, ["Python", "AI Agent", "n8n"])
    elif "n8n" in lower: values = ("project", 800, 1600, 12, 89, 65, 75, 50, 31, ["n8n", "自动化"])
    else: values = ("project", 1500, 3000, 30, 76, 55, 60, 55, 43, ["网站开发", "小程序"])
    kind, min_budget, max_budget, hours, match, conversion, urgency, competition, risk, skills = values
    return OpportunityAnalysis(is_opportunity=True, type=kind, title=item.title, summary=item.content[:220], location="桂林" if "桂林" in text else "远程", work_mode="online", skills=skills, budget_min=min_budget, budget_max=max_budget, estimated_hours=hours, commercial_intent=95, skill_match=match, conversion_probability=conversion, urgency=urgency, competition=competition, risk=min(100, risk + adjustment), reasons=["技能高度匹配", "发布时间较短", "预算合理", "交付难度可控"], warnings=rule_warnings or ["请确认需求范围与修改次数"])
