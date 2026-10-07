from datetime import UTC, datetime, timedelta

from app.services.information_edge import edge_from_pipeline, half_life_hours, information_edge, load_weights


def test_weights_sum_to_one():
    weights = load_weights()
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_fresh_cross_confirmed_rare_signal_has_high_edge():
    edge = information_edge(novelty=85, freshness=90, source_rarity=70, cross_source_confirmation=80, demand_growth=85, supply_gap=75, competition_awareness=20, actionability=80)
    assert edge.total >= 75


def test_crowded_old_signal_has_low_edge():
    edge = information_edge(novelty=10, freshness=10, source_rarity=5, cross_source_confirmation=10, demand_growth=5, supply_gap=10, competition_awareness=95, actionability=20)
    assert edge.total <= 30


def test_half_life_respects_freshness_and_rarity():
    long_window = half_life_hours(freshness=95, source_rarity=90, demand_growth=90)
    short_window = half_life_hours(freshness=10, source_rarity=10, demand_growth=10)
    assert long_window > short_window
    assert long_window <= 336
    assert short_window >= 0


def test_edge_from_pipeline_fresh_document():
    now = datetime.now(UTC)
    edge = edge_from_pipeline(published_at=now - timedelta(hours=2), document_sources=4, cluster_documents=8, demand_growth=0.8, competition=25)
    assert edge.freshness >= 90
    assert edge.cross_source_confirmation == 100
    assert edge.total >= 60


def test_edge_from_pipeline_old_document_decays():
    now = datetime.now(UTC)
    fresh = edge_from_pipeline(published_at=now - timedelta(hours=1), document_sources=3, cluster_documents=6, demand_growth=0.7, competition=25)
    stale = edge_from_pipeline(published_at=now - timedelta(days=30), document_sources=3, cluster_documents=6, demand_growth=0.7, competition=25)
    assert fresh.total > stale.total
    assert stale.freshness == 0


def test_edge_from_pipeline_undated_gets_neutral_freshness():
    edge = edge_from_pipeline(published_at=None, document_sources=1, cluster_documents=1, demand_growth=0.1, competition=50)
    assert edge.freshness == 60
