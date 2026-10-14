"""Public excerpts are development regressions, not a blind accuracy estimate."""
import pytest
from app.services.evidence_classifier import classify_tiktok
from app.services.evidence_facts import facts


@pytest.mark.parametrize("title,body",[
    ("需要做个全网商品比价，主要是淘宝，京东，拼多多","要求：有做过类似项目的，有演示最好，只做比价即可。"),
    ("Wordpress B2B 站点主题设计制作 长期合作","必备要求：良好审美能力，擅长页面构建器与多语言架构。"),
])
def test_implicit_public_project_request_is_a_buyer_candidate(title,body):
    assert classify_tiktok(body,title=title).category == "buyer"


def test_budget_negation_is_not_payment_evidence():
    assert classify_tiktok("公司汇报需要PPT排版，谁能帮我？还没确定预算。").payment_signal is None


def test_open_ended_compensation_and_non_time_delivery():
    result=facts("报酬：5000+，按阶段交付、长期合作。")
    assert result["budget_min"] == 5000 and result["budget_max"] is None
    assert result["currency"] is None
    assert result["deadline"] is None


def test_closed_or_ineligible_demand_never_has_a_grade():
    assert classify_tiktok("找人做PPT预算500元，已经找到人，需求已取消。").evidence_grade != "A"
    assert classify_tiktok("找人帮我代写毕业论文，预算3000元，本周交付。").evidence_grade != "A"


def test_facts_excludes_negated_amount_and_unrelated_year():
    assert facts("预算不是5000元，还没确定")["budget_min"] is None
    assert facts("按阶段交付，项目启动于2025年")["deadline"] is None


def test_review_cannot_turn_closed_source_into_verified_customer():
    from app.repositories.memory import MemoryRepository
    from app.schemas.evidence import EvidenceBatch, EvidenceReview
    from app.core.errors import AppError
    repo=MemoryRepository()
    record=repo.upsert_evidence_batch("u",EvidenceBatch(batch_id="test",items=[{"source":"rss","url":"https://example.com/closed","raw_text":"找人做PPT预算500元，需求已取消。","category":"buyer"}])).records[0]
    with pytest.raises(AppError) as err:
        repo.review_evidence("u",record.evidence_id,EvidenceReview(verification_status="verified",notes="尝试核实",assessment={"availability":"open","eligibility":"eligible"}))
    assert err.value.code == "DEMAND_NOT_ACTIONABLE"


def test_review_qualification_is_persisted_and_invalid_after_source_change():
    from app.repositories.memory import MemoryRepository
    from app.schemas.evidence import EvidenceBatch, EvidenceReview
    repo=MemoryRepository()
    data={"source":"rss","url":"https://example.com/open","raw_text":"找人做PPT预算500元，本周交付。","category":"buyer"}
    record=repo.upsert_evidence_batch("u",EvidenceBatch(batch_id="v1",items=[data])).records[0]
    updated=repo.review_evidence("u",record.evidence_id,EvidenceReview(notes="确认原文和交付能力",assessment={"availability":"open","eligibility":"eligible"}))
    assert updated.assessment["availability"] == "open"
    changed=repo.upsert_evidence_batch("u",EvidenceBatch(batch_id="v2",items=[{**data,"raw_text":data["raw_text"]+"需求已取消。"}])).records[0]
    assert changed.assessment["availability"] == "closed"
    assert len(repo.evidence_reviews) == 1


def test_absolute_past_deadline_blocks_action_but_relative_time_is_unknown():
    from app.services.demand_qualification import qualification
    past=qualification('找人做PPT，截止2020年1月1日，预算500元。')
    assert past['availability'] == 'closed'
    assert past['availability_quote'] == '截止2020年1月1日'
    assert not past['actionable_candidate']
    assert qualification('找人做PPT，明天交付。')['availability'] == 'unknown'


def test_full_long_text_keeps_cancellation_after_middle():
    from app.services.demand_qualification import qualification
    assert not qualification('找人做PPT预算500元。'+ '范围待定。'*3000+'需求已取消。')['actionable_candidate']


def test_import_cannot_forge_human_label_or_qualification_review():
    from app.schemas.evidence import EvidenceBatch
    with pytest.raises(ValueError):
        EvidenceBatch(batch_id='forged-label',items=[{'source':'rss','url':'https://example.test/forged','raw_text':'需要做个网站，找人帮我。','metadata':{'human_label_digest':'forged','qualification_review':'{"availability":"open"}'}}])
