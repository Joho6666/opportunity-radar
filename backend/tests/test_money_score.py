import pytest

from app.schemas.domain import OpportunityAnalysis
from app.schemas.intelligence import InformationEdgeBreakdown
from app.services.money_score import DEFAULT_WEIGHTS, load_weights, money_score, score_from_analysis


def _analysis(**overrides) -> OpportunityAnalysis:
    base = dict(is_opportunity=True, type="client", title="AI 电商广告批量生产", summary="s", budget_min=1500, budget_max=3000, estimated_hours=10, commercial_intent=90, skill_match=95, conversion_probability=80, urgency=85, competition=30, risk=20)
    base.update(overrides)
    return OpportunityAnalysis(**base)


def test_weights_sum_to_one_and_default_ordering():
    weights = load_weights()
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    assert weights["payment_evidence"] == max(weights.values())


def test_strong_opportunity_scores_high():
    strong = money_score(
        demand_velocity=94, payment_evidence=88, supply_gap=83, profit_margin=80,
        repeatability=75, competition=30, freshness=90, information_edge=85,
        execution_difficulty=25, personal_fit=96, confidence=86,
    )
    assert strong.total >= 85
    assert strong.total <= 100


def test_weak_opportunity_scores_low():
    weak = money_score(
        demand_velocity=10, payment_evidence=0, supply_gap=10, profit_margin=20,
        repeatability=10, competition=90, freshness=10, information_edge=5,
        execution_difficulty=90, personal_fit=5, confidence=10,
    )
    assert weak.total <= 25


def test_competition_and_difficulty_are_inverse():
    low_competition = money_score(demand_velocity=50, payment_evidence=50, supply_gap=50, profit_margin=50, repeatability=50, competition=10, freshness=50, information_edge=50, execution_difficulty=10, personal_fit=50, confidence=50)
    high_competition = money_score(demand_velocity=50, payment_evidence=50, supply_gap=50, profit_margin=50, repeatability=50, competition=90, freshness=50, information_edge=50, execution_difficulty=90, personal_fit=50, confidence=50)
    assert low_competition.total > high_competition.total


def test_custom_weights_change_ranking():
    base = dict(demand_velocity=90, payment_evidence=10, supply_gap=50, profit_margin=50, repeatability=50, competition=50, freshness=50, information_edge=50, execution_difficulty=50, personal_fit=50, confidence=50)
    default_result = money_score(**base)
    payment_heavy = money_score(**base, weights={**{key: 0.0 for key in DEFAULT_WEIGHTS}, "payment_evidence": 1.0})
    assert payment_heavy.total < default_result.total


def test_score_from_analysis_wires_payment_and_cluster_evidence():
    edge = InformationEdgeBreakdown(novelty=80, freshness=90, source_rarity=60, cross_source_confirmation=75, demand_growth=88, supply_gap=70, competition_awareness=30, actionability=75, information_half_life_hours=48, total=80)
    money = score_from_analysis(
        _analysis(), edge,
        cluster_docs=12, cluster_velocity=8.0, payment_signals=2,
        cluster_platforms=3, budget=3000, estimated_hours=10,
        minimum_budget=500, profile_skills=["AI Agent", "n8n"],
        hours_since_published=6,
    )
    assert money.payment_evidence >= 60
    assert money.demand_velocity >= 60
    assert money.total >= 60
    assert set(money.weights) == set(DEFAULT_WEIGHTS)


def test_score_from_analysis_without_payment_evidence_stays_lower():
    edge = InformationEdgeBreakdown(novelty=40, freshness=40, source_rarity=20, cross_source_confirmation=25, demand_growth=20, supply_gap=30, competition_awareness=60, actionability=40, information_half_life_hours=24, total=35)
    with_payment = score_from_analysis(_analysis(), edge, cluster_docs=5, payment_signals=1)
    without_payment = score_from_analysis(_analysis(), edge, cluster_docs=5, payment_signals=0)
    assert with_payment.total > without_payment.total
