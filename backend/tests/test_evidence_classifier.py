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


@pytest.mark.parametrize(
    "text",
    [
        "商务合作请私信，接各类品牌推广",
        "我的穿搭分享 合作联系我",
        "DM for collab, link in bio",
    ],
)
def test_seller_self_promotion_is_not_buyer(text):
    result = classify_tiktok(text)
    assert result.category == "seller"
    assert result.reason_code == "seller_self_promotion"
    assert result.evidence_grade == "C"


def test_yuan_inside_word_is_not_payment_signal():
    result = classify_tiktok("元宇宙入门教程第三集")
    assert result.category == "content"
    assert result.payment_signal is None


def test_english_request_with_budget_is_buyer_candidate():
    result = classify_tiktok("Looking for a freelancer to build my Shopify store, budget $500")
    assert result.category == "buyer"
    assert result.evidence_grade == "A"
    assert result.payment_signal is not None


def test_explicit_outsourcing_request_stays_buyer():
    result = classify_tiktok("求推荐靠谱的外包团队做小程序，预算2万，月底前交付")
    assert result.category == "buyer"
    assert result.evidence_grade == "A"
    assert result.payment_signal == "预算"
    assert result.urgency_signal == "月底"
