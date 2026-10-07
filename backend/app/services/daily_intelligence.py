"""Daily Money Brief assembler (V2).

Builds the 《今日财富情报》 sections from real pipeline data — signals, clusters,
change events, money-scored opportunities — with zero hard-coded marketing copy.
The legacy DailyBriefRead fields (summary/signals/avoid/actions) are derived
from the same data so old frontend contracts keep working; LLM-written narrative
is a Phase 7 add-on.
"""

from ..schemas.domain import DailyBriefRead, OpportunityRead
from ..schemas.intelligence import ChangeEventRead, EventClusterRead, SignalRead


def assemble(
    opportunities: list[OpportunityRead],
    signals: list[SignalRead] | None = None,
    clusters: list[EventClusterRead] | None = None,
    changes: list[ChangeEventRead] | None = None,
    max_top: int = 5,
    max_actions: int = 3,
) -> DailyBriefRead:
    from datetime import date

    signals = signals or []
    clusters = clusters or []
    changes = changes or []

    scored = [item for item in opportunities if item.money_score is not None]
    ranked = sorted(scored or opportunities, key=lambda item: (item.money_score or item.opportunity_score), reverse=True)
    recommended = [item for item in opportunities if item.recommendation == "强烈推荐"]

    top = [
        {
            "id": item.id,
            "title": item.title,
            "money_score": item.money_score,
            "information_edge": item.information_edge,
            "opportunity_score": item.opportunity_score,
            "confidence": (item.money_breakdown or {}).get("confidence"),
            "verification_status": item.verification_status,
            "source": item.source,
            "source_url": item.source_url,
            "budget_min": item.budget_min,
            "budget_max": item.budget_max,
            "why_now": _why_now(item, clusters, changes),
        }
        for item in ranked[:max_top]
    ]

    payment = [
        {"id": signal.id, "title": signal.title, "signal_type": signal.signal_type, "payment_evidence": signal.payment_evidence, "commercial_intent": signal.commercial_intent, "occurred_at": signal.occurred_at.isoformat() if signal.occurred_at else None}
        for signal in sorted(signals, key=lambda item: (item.payment_evidence, item.commercial_intent), reverse=True)
        if signal.signal_type in {"purchase_intent", "outsourcing", "tender", "hiring"} or signal.payment_evidence
    ][:10]

    pain = [
        {"id": signal.id, "title": signal.title, "signal_type": signal.signal_type, "urgency": signal.urgency, "commercial_intent": signal.commercial_intent}
        for signal in signals if signal.signal_type in {"pain_point", "complaint", "feature_request"}
    ][:10]

    job_market = [
        {"id": signal.id, "title": signal.title, "keywords": signal.keywords[:5]}
        for signal in signals if signal.signal_type == "hiring"
    ][:10]
    tender = [
        {"id": signal.id, "title": signal.title, "keywords": signal.keywords[:5]}
        for signal in signals if signal.signal_type == "tender"
    ][:10]

    breakouts = sorted(changes, key=lambda item: item.breakout_score, reverse=True)[:5]
    rising = [
        {"subject_key": event.subject_key, "metric_key": event.metric_key, "change_rate": event.change_rate, "breakout_score": event.breakout_score, "is_breakout": event.is_breakout}
        for event in breakouts
    ]
    content = [
        {"topic": cluster.title, "document_count": cluster.document_count, "source_count": cluster.source_count, "breakout_score": cluster.breakout_score}
        for cluster in sorted(clusters, key=lambda item: (item.breakout_score, item.document_count), reverse=True)
        if cluster.document_count >= 2
    ][:5]

    actions = [
        {"order": index + 1, "opportunity_id": item["id"], "action": f"优先联系：{item['title']}", "source": "recommended_contact"}
        for index, item in enumerate(top[:max_actions])
    ]

    return DailyBriefRead(
        date=date.today(),
        scanned_count=0,
        opportunities_count=len(opportunities),
        recommended_count=len(recommended),
        potential_income_min=0,
        potential_income_max=0,
        summary=f"今日 {len(top)} 个高价值机会、{len(rising)} 个上升主题、{len(pain)} 条集中痛点。",
        signals=[event["subject_key"] for event in rising] or ["今日无显著上升趋势"],
        avoid=["高竞争且无付费证据的方向"] if not payment else [],
        actions=[action["action"] for action in actions],
        top_opportunities=top,
        rising_trends=rising,
        pain_points=pain,
        payment_signals=payment,
        job_market_signals=job_market,
        tender_signals=tender,
        content_opportunities=content,
        today_actions=actions,
        brief_version="v2",
    )


def _why_now(item: OpportunityRead, clusters: list[EventClusterRead], changes: list[ChangeEventRead]) -> str:
    if item.money_breakdown and (item.money_breakdown.get("demand_velocity") or 0) >= 70:
        return "需求增速进入高位，且已有付费证据"
    breakout = next((event for event in changes if event.is_breakout), None)
    if breakout:
        return f"相关主题 {breakout.subject_key} 出现爆发式增长"
    if item.information_edge and item.information_edge >= 70:
        return "跨来源确认但仍少有人注意，存在信息差窗口"
    return "综合评分进入可执行区间"
