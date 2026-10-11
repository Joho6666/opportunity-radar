import pytest

from app.services.evidence_classifier import classify_tiktok


def test_explicit_request_with_budget_is_buyer_candidate():
    result = classify_tiktok("有人知道哪里可以找人做短视频广告吗？预算5000，月底前要")
    assert result.category == "buyer"
    assert result.reason_code == "explicit_request_budget_deadline"
    assert result.payment_signal == "预算"
    assert result.urgency_signal == "月底"
    assert result.evidence_grade == "A"


def test_how_to_question_is_content_candidate():
    result = classify_tiktok("有没有人能教我批量做这种视频？求教程")
    assert result.category == "content"
    assert result.reason_code == "audience_question_or_howto"


def test_ad_case_with_engagement_is_market_not_buyer():
    result = classify_tiktok(
        "AI广告案例：一张产品图生成短视频",
        engagement={"plays": 500000, "likes": 50000, "comments": 3000},
    )
    assert result.category == "market"
    assert result.payment_signal is None
    assert result.evidence_grade == "C"
