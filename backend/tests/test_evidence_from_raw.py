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
    assert record.classification_source == "rule_v1"
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
    assert record.classification_source == "rule_v1"
