"""Signal extraction: turn RawDocuments into typed Signals.

Phase 1 uses a rule dictionary (zero LLM cost); the LLM hook is reserved for
Phase 2 (cheap-model extraction with the same schema). Payment evidence and
commercial intent drive downstream MoneyScore dimensions.
"""

import re

from ..schemas.domain import RawItem
from ..schemas.intelligence import SignalRead, SignalType

# (signal_type, weight 0-100, keywords) — CJK substring match, English word match
RULES: list[tuple[SignalType, int, tuple[str, ...]]] = [
    ("purchase_intent", 85, ("想买", "求购", "哪里买", "多少钱", "报价", "预算", "budget", "quote", "price check", "willing to pay", "buy")),
    ("payment_evidence_mark", 90, ("已付款", "付费", "有偿", "有预算", "支付", "收款的", "paid", "payment", "prepaid", "subscription")),
    ("outsourcing", 80, ("外包", "有偿求", "谁可以帮忙", "有偿", "找人来", "代做", "求外包", "freelance", "contract work", "for hire", "gig")),
    ("hiring", 75, ("招聘", "急招", "HC", "岗位", "简历", "hiring", "job opening", "we are looking for", "join our team", "recruit")),
    ("product_request", 70, ("求推荐", "有没有工具", "有没有好用的", "求推荐一个", "alternative to", "any tool", "recommend a", "looking for a tool")),
    ("feature_request", 60, ("希望支持", "能不能加", "建议增加", "feature request", "please add", "would love", "would be great if")),
    ("complaint", 65, ("太难用", "太贵了", "太慢", "不好用", "烦死了", "体验差", "too slow", "too expensive", "hate", "frustrating", "painful", "annoying")),
    ("pain_point", 70, ("不会做", "搞不定", "求助", "求救", "翻车", "踩坑", "stuck", "struggling", "can't figure out", "how do i", "how to fix")),
    ("price_change", 60, ("涨价", "降价", "调价", "价格调整", "price increase", "price drop", "raising prices", "discount")),
    ("funding", 70, ("融资", "种子轮", "A轮", "领投", "raised", "funding", "seed round", "series a", "vc investment")),
    ("policy", 60, ("政策", "新规", "补贴", "征求意见稿", "公告", "regulation", "policy", "compliance", "subsidy")),
    ("tender", 80, ("招标", "投标", "中标", "采购", "tender", "rfp", "rfq", "procurement", "bid notice")),
    ("technology_growth", 55, ("趋势", "爆发", "火爆", "出圈", "爆火", "trending", "exploding", "hype", "going viral")),
    ("creator_trend", 55, ("涨粉", "爆款", "流量", "变现", "账号", "went viral", "monetize", "subscribers grew", "creator")),
    ("consumer_trend", 55, ("种草", "热销", "断货", "抢购", "sold out", "best seller", "trending product", "demand for")),
]

PAYMENT_KEYWORDS = ("有偿", "付费", "预算", "报价", "已付款", "paid", "payment", "budget", "quote", "prepaid", "willing to pay")
COMMERCIAL_KEYWORDS = ("多少钱", "报价", "预算", "有偿", "付费", "价格", "价目", "paid", "pricing", "budget", "quote", "subscription", "monthly")
URGENT_KEYWORDS = ("急", "urgent", "asap", "尽快", "马上", "今天就要")

# Buying-language verbs that only count when near a commercial keyword.
QUESTION_MARKERS = ("有没有", "求", "怎么", "如何", "哪里")


def _match_rules(text: str) -> list[tuple[SignalType, int]]:
    matched: list[tuple[SignalType, int]] = []
    for signal_type, weight, keywords in RULES:
        if signal_type == "payment_evidence_mark":
            continue
        for keyword in keywords:
            if keyword in text:
                matched.append((signal_type, weight))
                break
    return matched


def extract_payment_evidence(text: str) -> bool:
    return any(keyword in text for keyword in PAYMENT_KEYWORDS)


def extract_commercial_intent(text: str) -> int:
    score = 0
    for keyword in COMMERCIAL_KEYWORDS:
        if keyword in text:
            score = min(100, score + 30)
    for marker in QUESTION_MARKERS:
        if marker in text:
            score = min(100, score + 10)
    return score


def extract_urgency(text: str) -> int:
    return 80 if any(keyword in text for keyword in URGENT_KEYWORDS) else 35


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    words = re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower())
    seen: list[str] = []
    for word in words:
        if word not in seen:
            seen.append(word)
        if len(seen) >= limit:
            break
    return seen


def extract_signal(item: RawItem) -> SignalRead | None:
    """Rule-based extraction; returns the strongest matched signal or None."""
    text = f"{item.title} {item.content}".strip()
    if not text:
        return None
    matched = _match_rules(text)
    payment = extract_payment_evidence(text)
    if not matched:
        if not payment:
            return None
        matched = [("purchase_intent", 60)]
    signal_type, weight = matched[0]
    commercial = extract_commercial_intent(text)
    confidence = min(95, weight + (10 if payment else 0))
    return SignalRead(
        raw_item_id=None,
        radar_id=None,
        signal_type=signal_type,
        title=item.title[:200],
        entities=[entity for entity in (item.author,) if entity],
        keywords=extract_keywords(text),
        intent="commercial" if commercial >= 40 else "informational",
        sentiment="negative" if signal_type in {"complaint", "pain_point"} else "neutral",
        commercial_intent=commercial,
        payment_evidence=payment,
        urgency=extract_urgency(text),
        confidence=confidence,
        extraction_method="rule",
        occurred_at=item.published_at,
    )


def extract_signals(item: RawItem) -> list[SignalRead]:
    """All matched signals (Phase 2 will return multi-signal LLM output)."""
    primary = extract_signal(item)
    return [primary] if primary else []
