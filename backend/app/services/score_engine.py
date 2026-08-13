from dataclasses import dataclass
from ..schemas.domain import OpportunityAnalysis


@dataclass(frozen=True)
class ScoreResult:
    opportunity_score: int
    income_score: int
    hourly_rate_score: int
    recommendation: str


def calculate_score(analysis: OpportunityAnalysis, minimum_budget: int, risk_adjustment: int = 0) -> ScoreResult:
    budget = max(analysis.budget_max, analysis.budget_min)
    income_score = min(100, round((budget / max(minimum_budget, 1)) * 50)) if budget else 25
    hourly_rate = budget / max(analysis.estimated_hours, 1)
    hourly_rate_score = min(100, round(hourly_rate * 1.2))
    effective_risk = min(100, analysis.risk + risk_adjustment)
    score = (analysis.skill_match * .25 + income_score * .20 + hourly_rate_score * .15 + analysis.conversion_probability * .15 + analysis.urgency * .10 + (100 - analysis.competition) * .10 + (100 - effective_risk) * .05)
    final = max(0, min(100, round(score)))
    recommendation = "强烈推荐" if final >= 90 else "值得考虑" if final >= 75 else "一般" if final >= 60 else "不建议"
    return ScoreResult(final, income_score, hourly_rate_score, recommendation)
