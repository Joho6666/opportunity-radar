from __future__ import annotations

from ..repositories.base import Repository
from ..schemas.domain import OpportunityRead, PreferenceState

EVENT_WEIGHTS = {
    "viewed": 0.2,
    "saved": 2.0,
    "contacted": 3.0,
    "applied": 3.0,
    "won": 5.0,
    "ignored": -2.0,
    "lost": -1.0,
    "negotiating": 2.5,
}
DECAY = 0.98
CLAMP = 10.0


def _nudge(mapping: dict[str, float], key: str | None, delta: float) -> None:
    if not key:
        return
    mapping[key] = max(-CLAMP, min(CLAMP, mapping.get(key, 0.0) * DECAY + delta))


class FeedbackService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def record_event(self, user_id: str, opportunity: OpportunityRead, event: str) -> PreferenceState:
        state = self.repository.get_preference(user_id)
        delta = EVENT_WEIGHTS.get(event, 0.0)
        _nudge(state.type_weights, opportunity.type, delta)
        _nudge(state.source_weights, opportunity.source, delta)
        _nudge(state.location_weights, opportunity.location, delta)
        for skill in opportunity.skills:
            _nudge(state.skill_weights, skill, delta)
            _nudge(state.keyword_weights, skill, delta)
        title_tokens = [token for token in opportunity.title.replace("｜", " ").split() if len(token) >= 2][:4]
        for token in title_tokens:
            _nudge(state.keyword_weights, token, delta * 0.5)
        if event in {"saved", "contacted", "applied", "won"} and opportunity.budget_min:
            hint = state.min_budget_hint or opportunity.budget_min
            state.min_budget_hint = round((hint + opportunity.budget_min) / 2)
        if event == "ignored":
            state.recommendation_threshold = min(95, (state.recommendation_threshold or 90) + 1)
        elif event in {"saved", "won"}:
            state.recommendation_threshold = max(75, (state.recommendation_threshold or 90) - 1)
        self.repository.record_event(user_id, opportunity.id, event, {"type": opportunity.type, "source": opportunity.source})
        return self.repository.save_preference(user_id, state)
