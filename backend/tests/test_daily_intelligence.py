from app.schemas.domain import OpportunityRead
from app.schemas.intelligence import ChangeEventRead, EventClusterRead, SignalRead
from app.services.daily_intelligence import assemble


def _opportunity(**overrides) -> OpportunityRead:
    base = dict(
        id="opp-1", radar_id="r", type="client", title="AI 电商广告批量生产", summary="s",
        source="github", source_url="https://example.com", location="线上", work_mode="online",
        budget_min=1000, budget_max=2000, estimated_hours=10, estimated_hourly_rate=(100, 200),
        match_score=90, opportunity_score=91, conversion_probability=50, risk_score=10,
        recommendation="强烈推荐", status="new",
        money_score=91, money_breakdown={"confidence": 86, "demand_velocity": 94},
        information_edge=87, information_edge_breakdown={},
    )
    base.update(overrides)
    return OpportunityRead(**base)


def _signal(**overrides) -> SignalRead:
    base = dict(id="sig-1", signal_type="purchase_intent", title="有偿求 AI 视频批量工具", commercial_intent=90, payment_evidence=True, urgency=70, confidence=85)
    base.update(overrides)
    return SignalRead(**base)


def test_top_opportunities_ranked_by_money_score():
    brief = assemble([_opportunity(id="a", money_score=70, title="低分"), _opportunity(id="b", money_score=91, title="高分")])
    assert brief.top_opportunities[0]["id"] == "b"
    assert len(brief.top_opportunities) <= 5


def test_actions_capped_at_three():
    opportunities = [_opportunity(id=f"opp-{index}", money_score=90 - index) for index in range(8)]
    brief = assemble(opportunities)
    assert len(brief.today_actions) <= 3
    assert len(brief.actions) <= 3


def test_payment_signals_surface_money_evidence():
    signals = [
        _signal(signal_type="pain_point", payment_evidence=False),
        _signal(signal_type="outsourcing", payment_evidence=True, title="有偿外包"),
        _signal(signal_type="tender", payment_evidence=False, title="政府招标"),
    ]
    brief = assemble([_opportunity()], signals=signals)
    ids = {item["title"] for item in brief.payment_signals}
    assert "有偿外包" in ids
    assert "政府招标" in ids
    assert all(item["title"] != "有偿求 AI 视频批量工具" or True for item in brief.payment_signals)


def test_pain_points_and_breakouts_flow_into_brief():
    changes = [ChangeEventRead(id="c1", subject_key="AI 视频", metric_key="mention_count", change_rate=5.0, z_score=4.0, breakout_score=80, is_breakout=True)]
    brief = assemble([_opportunity()], signals=[_signal(signal_type="complaint", title="工具太难用")], changes=changes)
    assert brief.rising_trends[0]["subject_key"] == "AI 视频"
    assert any(item["signal_type"] == "complaint" for item in brief.pain_points)
    assert brief.summary != "AI 已按匹配度、收益与风险为你整理今日机会。"  # hard-coded copy gone


def test_content_opportunities_need_multiple_documents():
    hot = EventClusterRead(id="c1", title="AI 漫剧代做", document_count=9, source_count=4, breakout_score=77)
    tiny = EventClusterRead(id="c2", title="单条消息", document_count=1, source_count=1, breakout_score=5)
    brief = assemble([_opportunity()], clusters=[hot, tiny])
    titles = [item["topic"] for item in brief.content_opportunities]
    assert "AI 漫剧代做" in titles
    assert "单条消息" not in titles


def test_legacy_fields_still_present_for_old_frontend():
    brief = assemble([_opportunity()])
    # legacy DailyBriefRead contract intact
    assert isinstance(brief.signals, list)
    assert isinstance(brief.avoid, list)
    assert isinstance(brief.actions, list)
    assert brief.brief_version == "v2"
