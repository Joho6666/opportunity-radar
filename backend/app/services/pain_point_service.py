"""PainPoint Engine: "最近互联网用户最集中抱怨什么？"

Aggregates pain/complaint/feature-request signals per radar into pain point
themes with volume, growth, spread, severity and payment intent. Rule mode is
zero-LLM; an optional LLM pass fills current_solutions / solution_satisfaction
per theme (budget-gated at the call site).
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime

from ..repositories.base import Repository
from ..schemas.intelligence import PainPointRead, SignalRead
from .budget_service import check_and_consume, estimate_tokens

logger = logging.getLogger(__name__)

PAIN_SIGNAL_TYPES = {"pain_point", "complaint", "feature_request"}


async def rebuild_for_radar(repository: Repository, user_id: str, radar_id: str, signals: list[SignalRead], cluster_themes: dict[str, str] | None = None) -> list[PainPointRead]:
    """cluster_themes: cluster_id -> theme title (from the run's clusters)."""
    cluster_themes = cluster_themes or {}
    pains = [signal for signal in signals if signal.signal_type in PAIN_SIGNAL_TYPES]
    if not pains:
        return []
    groups: dict[str, list[SignalRead]] = defaultdict(list)
    for signal in pains:
        theme = cluster_themes.get(signal.cluster_id or "") or (signal.keywords[0] if signal.keywords else signal.title[:24] or "未分类")
        groups[theme.strip()[:60] or "未分类"].append(signal)

    previous = {pain.theme: pain for pain in repository.list_pain_points(user_id, radar_id=radar_id, limit=200)}
    saved: list[PainPointRead] = []
    for theme, members in groups.items():
        platforms = {signal.radar_id or "" for signal in members}  # per-signal platform unknown → proxy below
        users = {signal.entities[0] for signal in members if signal.entities}
        mention_count = len(members)
        payment = sum(1 for signal in members if signal.payment_evidence)
        payment_intent = min(100, payment * 30 + (20 if any(signal.commercial_intent >= 50 for signal in members) else 0))
        avg_urgency = sum(signal.urgency for signal in members) / len(members)
        severity = min(100, int(avg_urgency * 0.5 + (30 if payment else 0) + min(30, mention_count * 4)))
        growth = 0.0
        if theme in previous and previous[theme].mention_count:
            growth = round((mention_count - previous[theme].mention_count) / previous[theme].mention_count, 4)
        pain = PainPointRead(
            id="",
            radar_id=radar_id,
            theme=theme,
            title=members[0].title[:200],
            summary=members[0].title[:200],
            mention_count=mention_count,
            growth_rate=growth,
            platform_count=max(1, len(platforms)),
            unique_user_count=max(1, len(users)),
            severity=severity,
            payment_intent=payment_intent,
            current_solutions=previous.get(theme, PainPointRead(id="", radar_id=radar_id, theme=theme)).current_solutions,
            solution_satisfaction=previous.get(theme, PainPointRead(id="", radar_id=radar_id, theme=theme)).solution_satisfaction,
            cluster_id=members[0].cluster_id,
        )
        saved.append(repository.upsert_pain_point(pain))
    return saved


async def fill_solutions(repository: Repository, user_id: str, radar_id: str, limit: int = 3) -> int:
    """Optional LLM pass: describe current solutions + satisfaction per top pain.
    Skips silently when the LLM or the daily budget is unavailable."""
    from .ai_service import describe_pain_solutions

    settings_budget_active = True
    top = repository.list_pain_points(user_id, radar_id=radar_id, limit=limit)
    filled = 0
    for pain in top:
        if pain.current_solutions:
            continue
        if not await check_and_consume(user_id, estimate_tokens(pain.theme + pain.summary)):
            break
        result = await describe_pain_solutions(pain.theme, pain.summary)
        if result is None:
            continue
        solutions, satisfaction = result
        updated = pain.model_copy(update={"current_solutions": solutions[:1000], "solution_satisfaction": satisfaction})
        repository.upsert_pain_point(updated)
        filled += 1
    _ = settings_budget_active
    return filled
