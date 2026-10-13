from datetime import UTC, datetime

from app.schemas.domain import RawItem
from app.services.evidence_from_raw import raw_items_to_evidence_batch


def test_raw_items_keep_platform_and_acquisition_provenance():
    item = RawItem(
        external_id="123",
        title="AI ad case",
        content="AI广告案例：一张产品图生成短视频",
        url="https://www.tiktok.com/@creator/video/123",
        source="tikhub",
        platform="tiktok",
        published_at=datetime(2026, 10, 11, tzinfo=UTC),
        engagement={"plays": 500000},
        metadata={"acquisition_tool": "tikhub"},
    )
    batch = raw_items_to_evidence_batch(source="tikhub", query="AI视频广告", items=[item], batch_id="tikhub-1")
    record = batch.items[0]
    assert record.category == "market"
    assert record.classification_source == "rule_v2"
    assert record.classification_reason
    assert record.source_platform == "tiktok"
    assert record.acquisition_tool == "tikhub"
    assert record.payment_signal is None


def test_high_engagement_does_not_create_buyer_signal():
    item = RawItem(
        external_id="456",
        title="AI ad case",
        content="AI产品广告案例展示",
        url="https://www.tiktok.com/@creator/video/456",
        source="tikhub",
        platform="tiktok",
        engagement={"plays": 9999999, "likes": 999999},
    )
    record = raw_items_to_evidence_batch(source="tikhub", query="AI视频广告", items=[item], batch_id="tikhub-2").items[0]
    assert record.category == "market"
    assert record.classification_source == "rule_v2"


def test_rule_grade_survives_persistence():
    from app.repositories.memory import MemoryRepository

    texts = {
        "buyer": "求推荐靠谱的外包团队做小程序，预算2万，月底前交付",
        "content": "AI短视频怎么做？新手教程第一集",
        "market": "AI广告案例：一张产品图生成短视频",
    }
    items = [
        RawItem(external_id=key, title=text, content=text, url=f"https://www.tiktok.com/@u/video/{key}", source="tikhub", platform="tiktok")
        for key, text in texts.items()
    ]
    batch = raw_items_to_evidence_batch(source="tiktok", query="q", items=items, batch_id="b1")
    stored = {record.external_id: record for record in MemoryRepository().upsert_evidence_batch("u1", batch).records}
    assert stored["buyer"].evidence_grade == "A"
    assert stored["content"].evidence_grade == "B"
    assert stored["market"].evidence_grade == "C"


def test_long_github_issue_preserves_full_source_text():
    from app.schemas.domain import RawItem
    from app.services.evidence_from_raw import raw_items_to_evidence_batch
    body="Need a freelancer to build a website. " + "documented scope. "*3500
    item=RawItem(external_id="large",source="github",url="https://github.com/example/repo/issues/1",title="Long scope",content=body)
    batch=raw_items_to_evidence_batch(source="github",query="freelance",items=[item],batch_id="long")
    assert body.strip() in batch.items[0].raw_text and len(batch.items[0].raw_text)>20000
