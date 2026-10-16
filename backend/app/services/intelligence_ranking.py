"""Explainable topic ranking; the result is an ordering heuristic, never a buyer score."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime


def _tokens(value: str) -> list[str]:
    # A free-form topic should still rank related posts when the entire sentence
    # is not repeated verbatim in the source text. Keep English words and Chinese
    # bigrams; drop common grammatical/noise bigrams so the score stays readable.
    stop = {"的", "了", "和", "与", "及", "是", "在", "将", "从", "为", "对", "及", "一个", "最新", "动态", "关注"}
    terms: list[str] = []
    for token in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", value.casefold()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            parts = [token] if len(token) == 2 else [token[index:index + 2] for index in range(len(token) - 1)]
            terms.extend(part for part in parts if part not in stop and not any(char in stop and len(char) == 1 for char in part))
        elif token not in stop and len(token) >= 2:
            terms.append(token)
    return list(dict.fromkeys(terms))


def _terms(radar) -> list[str]:
    if radar.keywords:
        return list(dict.fromkeys(value.strip().casefold() for value in radar.keywords if value.strip()))
    return _tokens(radar.goal)


def score_information(item, radar, *, is_new: bool, source_quality: float | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    text = f"{item.title} {item.content}".casefold()
    terms = _terms(radar)
    if radar.keywords:
        exact = [term for term in terms if term in text]
    else:
        body_terms = set(_tokens(text))
        exact = [term for term in terms if term in body_terms]
    # Keep substring matching grounded in the user's own topic; do not infer a purchase intent.
    topic = round(100 * len(exact) / max(1, len(terms))) if terms else 0
    stamp = item.published_at or getattr(item, "updated_at_source", None)
    if stamp is not None:
        stamp = stamp.replace(tzinfo=UTC) if stamp.tzinfo is None else stamp.astimezone(UTC)
        age_hours = max(0.0, (now - stamp).total_seconds() / 3600)
        freshness: float | None = round(100 / (1 + age_hours / 48))
    else:
        freshness = None
    engagement = item.engagement if isinstance(item.engagement, dict) else {}
    counts = [value for key, value in engagement.items() if key in {"likes", "points", "stars", "comments", "num_comments", "shares", "reposts", "collects", "forks"} and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 10**12]
    interaction_score = round(min(100, math.log10(1 + sum(counts)) * 25)) if counts else None
    dimensions = {"topic_relevance": topic, "freshness": freshness, "novelty": 100 if is_new else 0, "source_quality": source_quality, "public_interaction": interaction_score}
    weights = {"topic_relevance": .55, "freshness": .20, "novelty": .10, "source_quality": .10, "public_interaction": .05}
    available_weight = sum(weights[key] for key, value in dimensions.items() if value is not None)
    score = round(sum(weights[key] * value for key, value in dimensions.items() if value is not None) / available_weight) if available_weight else 0
    reasons = [f"主题相关词命中：{', '.join(exact[:8])}" if exact else "未命中主题相关词；仅保留供人工检索"]
    reasons.append(f"新鲜度：{freshness}/100" if freshness is not None else "发布时间未知，新鲜度未参与排序")
    reasons.append("首次在该雷达发现" if is_new else "此前已在该雷达发现")
    reasons.append(f"来源人工复核记录：{source_quality:.0f}/100" if source_quality is not None else "来源质量缺少至少10条人工复核记录，未参与排序")
    reasons.append(f"公开互动信号：{interaction_score}/100" if interaction_score is not None else "公开互动数未知，未参与排序")
    return {"version": "general-v1", "score": score, "dimensions": dimensions, "reasons": reasons, "label": "情报相关度排序启发式；不是客户意向或成交概率"}
