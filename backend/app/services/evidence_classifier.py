from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Classification:
    category: str
    reason_code: str
    confidence: float
    evidence_grade: str
    payment_signal: str | None = None
    urgency_signal: str | None = None


_BUYER = re.compile(r"找人|求推荐|询价|报价|预算|外包|接单|定制|合作|采购|交付|截止|月底|联系我|私信")
_CONTENT = re.compile(r"怎么做|教程|求教程|有没有人能教|为什么|求方法|避坑|经验")
_MONEY = re.compile(r"预算|报价|多少钱|元|￥|\$|付费|采购")
_URGENT = re.compile(r"急|尽快|今天|明天|截止|月底|本周")


def classify_tiktok(raw_text: str, *, engagement: dict | None = None) -> Classification:
    """Conservatively classify public TikTok text; engagement never creates buyer intent."""
    text = raw_text.strip()
    if _BUYER.search(text) and (_MONEY.search(text) or _URGENT.search(text) or re.search(r"找人|求推荐|外包|定制|合作", text)):
        money = _MONEY.search(text)
        urgency = _URGENT.search(text)
        return Classification(
            category="buyer",
            reason_code="explicit_request_budget_deadline",
            confidence=0.82,
            evidence_grade="A",
            payment_signal=money.group(0) if money else None,
            urgency_signal=urgency.group(0) if urgency else None,
        )
    if _CONTENT.search(text):
        return Classification(category="content", reason_code="audience_question_or_howto", confidence=0.72, evidence_grade="B")
    return Classification(category="market", reason_code="content_or_trend_without_buying_intent", confidence=0.58, evidence_grade="C")
