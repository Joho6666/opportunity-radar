import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.collection import CollectionPolicy
from app.schemas.domain import RadarCreate, RawItem
from app.services.collection_filter import filter_page
from app.services.evidence_from_raw import raw_items_to_evidence_batch
from app.services.evidence_ingest import normalize_evidence
from app.services.post_ranking import signals

NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)


def post(id, **kw):
    return RawItem(**{"external_id":id, "title":"PPT外包需求", "content":"找人做PPT，预算3000元", "url":"https://example.test/"+id, "source":"rss", **kw})


def test_time_basis_unknown_dates_and_future_times_are_explicit():
    items = [post("old",published_at=NOW-timedelta(days=100),updated_at_source=NOW-timedelta(hours=1)),post("new",published_at=NOW-timedelta(hours=2)),post("unknown"),post("future",published_at=NOW+timedelta(days=1))]
    strict = CollectionPolicy(time_basis="published", include_unknown_dates=False)
    result, counts = filter_page(items, strict, freshness_hours=24, now=NOW)
    assert [p.external_id for p in result] == ["new"]
    assert counts == {"stale":1,"unknown_date":2,"terms":0,"activity":0}
    result,_ = filter_page(items,CollectionPolicy(),freshness_hours=24,now=NOW)
    assert {p.external_id for p in result} == {"old","new","unknown","future"}
    # Future dates are unknown, never proof of freshness.
    assert signals(published_at=NOW+timedelta(days=1),now=NOW)["published_at"] is None


def test_terms_are_literal_any_or_all_and_exclusions_win():
    items = [post("video",content="找人做PPT和VIDEO，预算3000元"),post("ad",content="PPT VIDEO教程，服务商广告"),post("ppt")]
    policy=CollectionPolicy(required_terms=["ppt","video"],excluded_terms=["广告"],match_mode="all")
    result,counts=filter_page(items,policy,freshness_hours=72,now=NOW)
    assert [p.external_id for p in result] == ["video"] and counts["terms"] == 2
    result,_=filter_page(items,policy.model_copy(update={"match_mode":"any"}),freshness_hours=72,now=NOW)
    assert {p.external_id for p in result} == {"video","ppt"}


def test_author_and_comments_are_observations_not_identity_verification():
    items=[post("ok",author="public-user",published_at=NOW,engagement={"comments":2}),post("no-date",author="public-user",engagement={"comments":5}),post("no-author",published_at=NOW,engagement={"comments":2}),post("zero",author="public-user",published_at=NOW,engagement={"comments":0}),post("unknown",author="public-user",published_at=NOW)]
    policy=CollectionPolicy(activity_filter="discussion")
    result,counts=filter_page(items,policy,freshness_hours=24,now=NOW)
    assert [p.external_id for p in result] == ["ok"] and counts["activity"] == 4
    assert signals(author="public-user",now=NOW)["identity_status"] == "unverified"


def test_heat_is_time_decayed_and_unknown_is_not_zero_or_a_captured_date():
    recent=signals(published_at=NOW,engagement={"likes":500,"comments":20},now=NOW)
    old=signals(published_at=NOW-timedelta(days=3),engagement={"likes":500,"comments":20},now=NOW)
    assert recent["heat_score"] > old["heat_score"]
    assert signals(published_at=NOW,engagement={},now=NOW)["heat_score"] is None
    assert signals(engagement={"likes":50},now=NOW)["heat_score"] is None
    assert signals(published_at=NOW,engagement={"likes":0},now=NOW)["heat_score"] == 0
    assert signals(published_at=NOW,engagement="{'likes': 10, 'comments': None}",now=NOW)["interactions"] == 10
    assert signals(published_at=NOW,engagement={"likes":True,"comments":float('nan'),"plays":1000000},now=NOW)["heat_score"] is None
    assert signals(published_at=NOW,engagement={"likes":10**1000},now=NOW)["heat_score"] is None


def test_latest_sort_compares_instants_across_source_timezones():
    from datetime import timezone
    china=timezone(timedelta(hours=8))
    items=[post("earlier",published_at=(NOW-timedelta(hours=2)).astimezone(china)),post("later",published_at=NOW-timedelta(hours=1))]
    result,_=filter_page(items,CollectionPolicy(sort="latest"),freshness_hours=24,now=NOW)
    assert [p.external_id for p in result] == ["later","earlier"]


def test_hot_sort_unknown_last_and_strict_minimum():
    items=[post("unknown",published_at=NOW),post("low",published_at=NOW,engagement={"likes":1}),post("high",published_at=NOW,engagement={"comments":50})]
    result,_=filter_page(items,CollectionPolicy(sort="hot"),freshness_hours=72,now=NOW)
    assert [p.external_id for p in result] == ["high","low","unknown"]
    result,_=filter_page(items,CollectionPolicy(min_interactions=5),freshness_hours=72,now=NOW)
    assert [p.external_id for p in result] == ["high"]


@pytest.mark.parametrize("policy",[{"min_interactions":-1},{"required_terms":["x"]*21},{"required_terms":[" "]},{"required_terms":["x"*101]},{"activity_filter":"human_verified"},{"unexpected":True}])
def test_invalid_filters_rejected(policy):
    with pytest.raises(ValidationError):CollectionPolicy(**policy)


def test_ad_popularity_and_closed_buyer_cannot_raise_lead_score():
    items=[post("seller",content="专业PPT代做，接单私信我，服务商广告",published_at=NOW,engagement={"likes":1000000}),post("closed",content="找人做PPT，预算3000元。需求已取消。",published_at=NOW)]
    records=normalize_evidence(raw_items_to_evidence_batch(source="rss",query="PPT",items=items,batch_id="ranking"))
    assert records[0].category == "seller"
    assert all(row.ranking["lead_score"] == 0 for row in records)


def test_keyword_planner_preserves_feed_urls_and_source_search_operators():
    from app.services.ai_service import plan_queries
    for source,keyword in [("rss","https://www.v2ex.com/feed/outsourcing.xml"),("hackernews","comments:need developer"),("github","issues:website help")]:
        radar=RadarCreate(name="关键词",goal="寻找真实公开可核实的需求",sources=[source],keywords=[keyword])
        queries=asyncio.run(plan_queries(radar))
        assert [q.query for q in queries] == [keyword]


def test_manual_route_applies_hour_window_terms_and_scores(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api.deps import get_current_user,get_repository
    from app.core.security import CurrentUser
    from app.main import app
    from test_evidence_collect_route import _setup
    now=datetime.now(UTC)
    items=[post("recent",published_at=now-timedelta(hours=2)),post("old",published_at=now-timedelta(hours=26)),post("no-time"),post("tutorial",content="PPT教程，如何学习制作演示文稿",published_at=now)]
    repository,search=_setup(monkeypatch,items)
    with TestClient(app) as client:
        try:
            response=client.post("/api/intelligence/evidence/collect?source=github&query=PPT",json={"freshness_hours":24,"policy":{"time_basis":"published","include_unknown_dates":False,"excluded_terms":["教程"]}})
        finally:app.dependency_overrides.clear()
    assert response.status_code == 200
    body=response.json()
    assert body["inserted"] == 1 and body["fetched"] == 4
    assert body["filtered"] == {"stale":1,"unknown_date":1,"terms":1,"activity":0}
    assert body["records"][0]["ranking"]["kind"] == "prediction"
    assert body["records"][0]["ranking"]["signals"]["identity_status"] == "unverified"
    assert len(search.calls) == 1


def test_saved_radar_applies_policy_before_analysis():
    from app.collectors.base import SourceAdapter
    from app.collectors.registry import CollectorRegistry
    from app.schemas.domain import QueryPlanItem
    from app.services.radar_run_service import RadarRunService
    from test_radar_run import _ready_repo
    class Posts(SourceAdapter):
        slug="rss"
        async def search(self,query):
            return [post("keep",published_at=datetime.now(UTC)),post("drop",published_at=datetime.now(UTC),content="PPT教程如何制作，有偿学习")]
    repo,uid=_ready_repo()
    radar=repo.create_radar(uid,RadarCreate(name="PPT",goal="寻找公开PPT外包制作需求",keywords=["https://www.v2ex.com/feed/outsourcing.xml"],sources=["rss"],collection_policy=CollectionPolicy(required_terms=["PPT"],excluded_terms=["教程"],time_basis="published",include_unknown_dates=False)))
    radar=repo.save_radar(radar.model_copy(update={"listener_config":{"positive_signals":["irrelevant compiled token"],"negative_signals":[],"search_queries":[],"exclusion_rules":[]}}))
    run=repo.create_run(radar.id)
    result=asyncio.run(RadarRunService(repo,CollectorRegistry([Posts()])).run(uid,radar.id,run.id))
    assert result.status == "completed" and result.stage_stats["collection_filtered"]["terms"] == 1
    assert {row.external_id for row in repo.list_evidence(uid)} == {"keep"}
    assert result.stats.opportunities_found == 1


def test_repeat_observations_refresh_heat_without_new_lead_or_lost_review():
    from app.repositories.memory import MemoryRepository
    from app.schemas.evidence import EvidenceReview
    repo=MemoryRepository()
    now=datetime.now(UTC)
    first=raw_items_to_evidence_batch(source="rss",query="PPT",items=[post("same",published_at=now,author="alice",engagement={"comments":1})],batch_id="observation1")
    row=repo.upsert_evidence_batch("u",first).records[0]
    repo.review_evidence("u",row.evidence_id,EvidenceReview(verification_status="verified",notes="人工核实"))
    second=raw_items_to_evidence_batch(source="rss",query="PPT",items=[post("same",published_at=now,author="alice",engagement={"comments":30})],batch_id="observation2")
    result=repo.upsert_evidence_batch("u",second)
    assert result.inserted == 0 and result.duplicates == 1
    assert result.records[0].ranking["signals"]["comments"] == 30
    assert result.records[0].verification_status == "verified" and result.records[0].notes == "人工核实"
    assert result.records[0].captured_at == row.captured_at and len(repo.evidence_revisions) == 0


def test_manual_radar_is_never_scheduled_even_with_stale_next_run():
    from app.repositories.memory import MemoryRepository
    from app.services.radar_run_service import next_run_at
    repo=MemoryRepository()
    radar=repo.create_radar("u",RadarCreate(name="手动",goal="寻找真实公开可核实的需求",frequency="manual"))
    repo.save_radar(radar.model_copy(update={"next_run_at":datetime.now(UTC)-timedelta(days=1)}))
    assert repo.list_due_radars(datetime.now(UTC)) == []
    assert next_run_at("manual",datetime.now(UTC)) is None
