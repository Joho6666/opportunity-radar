"""MoneyScore: "is this worth money?" — not merely "is this a gig?".

Eleven dimensions, each 0-100, combined with configurable weights. Inputs come
from the intelligence layer (signals, clusters, change events) plus the legacy
LLM analysis, so the score upgrades in place as those layers mature.

Defaults favour: payment evidence > demand velocity > supply gap.
Weights can be overridden via MONEY_SCORE_WEIGHTS_JSON (env) or per call.
"""

import json
import logging

from ..core.config import get_settings
from ..schemas.intelligence import InformationEdgeBreakdown, MoneyScoreBreakdown

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS: dict[str, float] = {
    "demand_velocity": 0.12,
    "payment_evidence": 0.16,
    "supply_gap": 0.12,
    "profit_margin": 0.08,
    "repeatability": 0.07,
    "competition": 0.08,
    "freshness": 0.07,
    "information_edge": 0.10,
    "execution_difficulty": 0.06,
    "personal_fit": 0.09,
    "confidence": 0.05,
}


def load_weights() -> dict[str, float]:
    weights = dict(DEFAULT_WEIGHTS)
    raw = get_settings().money_score_weights_json
    if raw:
        try:
            overrides = json.loads(raw)
            for key, value in overrides.items():
                if key in weights:
                    weights[key] = float(value)
        except (ValueError, TypeError):
            logger.warning("invalid MONEY_SCORE_WEIGHTS_JSON ignored")
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def money_score(
    demand_velocity: int,
    payment_evidence: int,
    supply_gap: int,
    profit_margin: int,
    repeatability: int,
    competition: int,
    freshness: int,
    information_edge: int,
    execution_difficulty: int,
    personal_fit: int,
    confidence: int,
    weights: dict[str, float] | None = None,
) -> MoneyScoreBreakdown:
    """competition/execution_difficulty are inverse contributions (lower is better)."""
    weights = weights or load_weights()
    dimensions = {
        "demand_velocity": demand_velocity,
        "payment_evidence": payment_evidence,
        "supply_gap": supply_gap,
        "profit_margin": profit_margin,
        "repeatability": repeatability,
        "competition": competition,
        "freshness": freshness,
        "information_edge": information_edge,
        "execution_difficulty": execution_difficulty,
        "personal_fit": personal_fit,
        "confidence": confidence,
    }
    total = 0.0
    for key, value in dimensions.items():
        contribution = value
        if key in {"competition", "execution_difficulty"}:
            contribution = 100 - value
        total += contribution * weights.get(key, 0.0)
    return MoneyScoreBreakdown(
        **dimensions,
        weights={key: round(value, 4) for key, value in weights.items()},
        total=max(0, min(100, round(total))),
    )


def score_from_analysis(
    analysis,  # OpportunityAnalysis
    information_edge: InformationEdgeBreakdown | None,
    cluster_docs: int = 0,
    cluster_velocity: float = 0.0,
    payment_signals: int = 0,
    cluster_platforms: int = 1,
    budget: int = 0,
    estimated_hours: float = 1.0,
    minimum_budget: int = 0,
    profile_skills: list[str] | None = None,
    hours_since_published: float | None = None,
    personal_fit_boost: int = 0,
    weights: dict[str, float] | None = None,
) -> MoneyScoreBreakdown:
    """Derive the 11 dimensions from pipeline artifacts (no extra LLM calls)."""
    demand_velocity = min(100, int(cluster_velocity * 12 + min(cluster_docs, 20) * 2 + analysis.urgency * 0.2))
    payment = min(100, payment_signals * 30 + (25 if analysis.commercial_intent >= 60 else 0))
    supply_gap = max(0, min(100, 100 - analysis.competition))
    margin = min(100, int((budget / max(estimated_hours, 1)) * 1.2))
    repeatability = min(100, 40 + (20 if analysis.type in {"client", "business"} else 0) + (10 if analysis.work_mode == "online" else 0))
    freshness = 100 if hours_since_published is None else max(0, 100 - int(hours_since_published / 24 * 8))
    edge = information_edge.total if information_edge else 50
    difficulty = min(100, int(analysis.estimated_hours * 2.5))
    skills = profile_skills or []
    fit = analysis.skill_match if not skills else min(100, analysis.skill_match + (10 if set(s.lower() for s in skills) & set(s.lower() for s in analysis.skills) else 0))
    fit = min(100, fit + personal_fit_boost)
    confidence = min(100, int(analysis.conversion_probability * 0.4 + (30 if payment_signals else 0) + (20 if cluster_docs >= 3 else 0) + 10))
    return money_score(
        demand_velocity=demand_velocity,
        payment_evidence=payment,
        supply_gap=supply_gap,
        profit_margin=margin,
        repeatability=repeatability,
        competition=analysis.competition,
        freshness=freshness,
        information_edge=edge,
        execution_difficulty=difficulty,
        personal_fit=fit,
        confidence=confidence,
        weights=weights,
    )
