from app.repositories.memory import MemoryRepository
from app.schemas.domain import OpportunityAnalysis, OpportunityRead, ProfileUpsert, RadarCreate
from app.services.feedback_service import FeedbackService
from app.services.score_engine import calculate_score


def _opportunity(**overrides) -> OpportunityRead:
    payload = dict(id="o1", radar_id="r1", type="project", title="n8n AI Agent 自动化", summary="s", source="github", source_url="https://example.com", location="远程", work_mode="online", budget_min=800, budget_max=1600, estimated_hours=12, estimated_hourly_rate=(60, 130), match_score=80, opportunity_score=80, conversion_probability=70, risk_score=20, recommendation="值得考虑", status="new", skills=["n8n", "AI Agent"])
    payload.update(overrides)
    return OpportunityRead(**payload)


def test_saving_agent_and_ignoring_ppt_shifts_keyword_weights():
    repo = MemoryRepository()
    user_id = "learner"
    repo.save_profile(user_id, ProfileUpsert(display_name="测", skills=[{"name": "n8n", "level": "strong"}], goals=["project"]))
    service = FeedbackService(repo)
    agent = _opportunity()
    ppt = _opportunity(id="o2", title="桂林毕业答辩 PPT", skills=["PPT"], type="client", source="mock")
    service.record_event(user_id, agent, "saved")
    service.record_event(user_id, agent, "saved")
    service.record_event(user_id, ppt, "ignored")
    state = repo.get_preference(user_id)
    assert state.keyword_weights.get("n8n", 0) > 0
    assert state.keyword_weights.get("AI Agent", 0) > 0
    assert state.keyword_weights.get("PPT", 0) < 0
    assert state.source_weights.get("github", 0) > state.source_weights.get("mock", 0)


def test_preference_does_not_change_unbiased_score():
    analysis = OpportunityAnalysis(is_opportunity=True, type="client", title="PPT", summary="", budget_min=200, budget_max=300, estimated_hours=3, commercial_intent=95, skill_match=96, conversion_probability=82, urgency=88, competition=45, risk=18)
    plain = calculate_score(analysis, 200)
    with_empty = calculate_score(analysis, 200, preference=None)
    assert plain.opportunity_score == with_empty.opportunity_score
