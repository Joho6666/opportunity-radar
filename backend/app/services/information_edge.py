"""Information Edge: does this carry real information asymmetry?

Nine dimensions plus a half-life estimate that converts into "how long does the
window stay open". Low public awareness + cross-source confirmation + fresh
demand growth = high edge. Nothing here requires an LLM.
"""

import json
import logging

from ..core.config import get_settings
from ..schemas.intelligence import InformationEdgeBreakdown

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS: dict[str, float] = {
    "novelty": 0.12,
    "freshness": 0.14,
    "source_rarity": 0.10,
    "cross_source_confirmation": 0.14,
    "demand_growth": 0.18,
    "supply_gap": 0.12,
    "competition_awareness": 0.06,
    "actionability": 0.14,
}


def load_weights() -> dict[str, float]:
    weights = dict(DEFAULT_WEIGHTS)
    raw = get_settings().information_edge_weights_json
    if raw:
        try:
            for key, value in json.loads(raw).items():
                if key in weights:
                    weights[key] = float(value)
        except (ValueError, TypeError):
            logger.warning("invalid INFORMATION_EDGE_WEIGHTS_JSON ignored")
    total = sum(weights.values()) or 1.0
    return {key: value / total for key, value in weights.items()}


def half_life_hours(freshness: int, source_rarity: int, demand_growth: int) -> float:
    """Hours until the edge decays to half value. Rare + fresh + fast growth lasts longer."""
    base = 24.0
    base *= 0.5 + freshness / 100
    base *= 0.75 + source_rarity / 200
    base *= 0.75 + demand_growth / 200
    return round(min(base, 336.0), 1)  # cap at two weeks


def information_edge(
    novelty: int,
    freshness: int,
    source_rarity: int,
    cross_source_confirmation: int,
    demand_growth: int,
    supply_gap: int,
    competition_awareness: int,
    actionability: int,
    weights: dict[str, float] | None = None,
) -> InformationEdgeBreakdown:
    weights = weights or load_weights()
    dimensions = {
        "novelty": novelty,
        "freshness": freshness,
        "source_rarity": source_rarity,
        "cross_source_confirmation": cross_source_confirmation,
        "demand_growth": demand_growth,
        "supply_gap": supply_gap,
        "competition_awareness": competition_awareness,
        "actionability": actionability,
    }
    total = sum(dimensions[key] * weight for key, weight in weights.items())
    half_life = half_life_hours(freshness, source_rarity, demand_growth)
    return InformationEdgeBreakdown(
        **dimensions,
        information_half_life_hours=half_life,
        total=max(0, min(100, round(total))),
    )


def edge_from_pipeline(
    published_at,  # datetime | None
    document_sources: int,
    cluster_documents: int,
    demand_growth: float,
    competition: int,
    rarity_bonus: int = 0,
    weights: dict[str, float] | None = None,
) -> InformationEdgeBreakdown:
    """Derive dimensions from cluster/pipeline facts."""
    from datetime import UTC, datetime

    freshness = 60
    if published_at is not None:
        age_hours = max(0.0, (datetime.now(UTC) - (published_at if published_at.tzinfo else published_at.replace(tzinfo=UTC))).total_seconds() / 3600)
        freshness = max(0, 100 - int(age_hours * 3))
    rarity = min(100, rarity_bonus + (40 if document_sources <= 2 else 15))
    cross_source = min(100, document_sources * 25)
    growth = max(0, min(100, int(demand_growth * 100)))
    supply_gap = max(0, 100 - competition)
    competition_awareness = min(100, competition)  # high competition = the crowd already knows
    novelty = max(0, min(100, 70 - competition // 2 + rarity_bonus))
    actionability = min(100, 50 + (25 if cluster_documents >= 3 else 0) + (25 if cross_source >= 50 else 0))
    return information_edge(
        novelty=novelty,
        freshness=freshness,
        source_rarity=rarity,
        cross_source_confirmation=cross_source,
        demand_growth=growth,
        supply_gap=supply_gap,
        competition_awareness=competition_awareness,
        actionability=actionability,
        weights=weights,
    )
