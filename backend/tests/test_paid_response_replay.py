from datetime import UTC, datetime
from app.services.paid_response_replay import replay_response


def test_replay_is_repeatable_and_preserves_unverified_status():
    payload = {"data": {"parsed_data": {"results": [{"weibo_id": "w1", "content": "找人做PPT，预算1200元，本周交付", "publish_time": "5分钟前", "post_url": "https://weibo.com/1/w1"}]}}}
    captured = datetime(2026,10,13,4,tzinfo=UTC)
    first = replay_response("weibo",payload,"PPT",captured,"call1")
    assert first == replay_response("weibo",payload,"PPT",captured,"call1")
    assert first[0]["category"] == "buyer"
    assert first[0]["verification_status"] == "unverified"
    assert first[0]["published_at"] == "2026-10-13T03:55:00Z"


def test_empty_success_replays_without_fake_schema_error():
    assert replay_response("xiaohongshu",{"data":{"data":{"items":[]}}},"PPT",datetime(2026,10,13,tzinfo=UTC),"call1") == []
