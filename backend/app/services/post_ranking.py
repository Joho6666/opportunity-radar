"""Observable signals, not bot detection or a calibrated conversion probability."""
import ast
import json
import math
from datetime import UTC, datetime, timedelta


def timestamp(value, now):
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
        stamp = stamp.replace(tzinfo=UTC) if stamp and stamp.tzinfo is None else stamp
        return stamp.astimezone(UTC) if stamp and stamp <= now + timedelta(minutes=5) else None
    except (ValueError, TypeError, AttributeError, OverflowError):
        return None


def signals(*, published_at=None, updated_at=None, author=None, engagement=None, now=None):
    now = now or datetime.now(UTC)
    published = timestamp(published_at, now)
    updated = timestamp(updated_at, now)
    latest = max((v for v in (published, updated) if v), default=None)
    if isinstance(engagement, str):
        try:
            engagement = json.loads(engagement)
        except (ValueError, TypeError):
            try:
                # Older records used Python repr; never evaluate executable text.
                engagement = ast.literal_eval(engagement[:4000])
            except (ValueError, SyntaxError, RecursionError):
                engagement = {}
    raw = engagement if isinstance(engagement, dict) else {}
    counts = {k: int(v) for k, v in raw.items() if k in {"likes", "points", "stars", "comments", "num_comments", "shares", "reposts", "collects", "forks"} and isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 10**12 and math.isfinite(v)}
    comments = counts.get("comments", counts.get("num_comments"))
    interactions = sum(counts.values()) if counts else None
    age = max(0, (now - latest).total_seconds() / 3600) if latest else None
    # Log scale limits viral posts; time decay rewards recent observed activity.
    weighted = sum(v * (3 if k in {"comments", "num_comments"} else 2 if k in {"shares", "reposts"} else 1) for k, v in counts.items())
    heat = round(min(100, math.log10(1 + weighted) * 25) / (1 + age / 72)) if counts and age is not None else None
    return {"published_at": published.isoformat() if published else None,
            "last_activity_at": latest.isoformat() if latest else None,
            "age_hours": round(age, 1) if age is not None else None,
            "author_visible": bool(isinstance(author, str) and author.strip()),
            "identity_status": "unverified", "comments": comments, "interactions": interactions,
            "heat_score": heat,
            "heat_reason": "公开累计互动量按时间衰减；仅供已采集结果排序，不代表平台热榜、真人身份或购买意愿" if heat is not None else "互动量或来源时间未知，无法计算热度"}


def evidence_ranking(evidence):
    from .acquisition_priority import priority
    result = priority(evidence, published_at=evidence.published_at)
    observed = signals(published_at=evidence.published_at, updated_at=evidence.metadata.get("updated_at_source"),
                       author=evidence.metadata.get("raw_author"), engagement=evidence.metadata.get("engagement"))
    published = timestamp(evidence.published_at, datetime.now(UTC))
    age = max(0,(datetime.now(UTC)-published).total_seconds()/3600) if published else None
    recency = 50 if age is None else 100 / (1 + age / 72)
    heat = observed["heat_score"] if observed["heat_score"] is not None else 50
    # Popularity has low weight and can never create buyer intent.
    lead = round(result["score"]*.7 + recency*.2 + heat*.1)
    if evidence.category != "buyer" or evidence.verification_status == "invalidated" or not evidence.assessment["actionable_candidate"]:
        lead = 0
    reasons = [f"原获客维度综合 {result['score']}/100，权重70%", *result["reasons"],
               f"发布时效 {recency:.0f}/100，权重20%；"+("发布时间未知，使用中性分" if age is None else f"距今 {age:.0f} 小时"),
               f"热度 {heat}/100，权重10%；"+("互动或时间未知，使用中性分" if observed["heat_score"] is None else "按公开累计互动及时间估算")]
    if evidence.category != "buyer" or evidence.verification_status == "invalidated":
        reasons.append("非买方或已排除，获客分为0；热度仍独立展示")
    return {"kind": "prediction", "lead_score": lead, "reasons": reasons, "signals": observed,
            "label": "获客优先级估算；预算、能力和竞争未知时采用中性分；不是成交概率"}
