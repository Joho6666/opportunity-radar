import json
from datetime import UTC, datetime
from app.core.config import get_settings
from app.api.intelligence import _source_status
from app.collectors.tikhub_cn import XiaohongshuCollector


def test_numeric_price_without_official_receipt_is_not_verified(monkeypatch):
    monkeypatch.setattr(get_settings(), "tikhub_endpoint_prices_json", json.dumps({XiaohongshuCollector.path: .01}))
    assert _source_status()["xiaohongshu"]["estimated_request_cost_usd"] is None


def receipt(price=.01):
    return {"price_usd": price, "unit": "USD/request", "source_url": "https://user.tikhub.io/dashboard/api-marketplace",
            "verified_at": datetime.now(UTC).isoformat(), "verified_by": "offline-test-fixture"}


def test_price_receipt_must_match_endpoint_amount_and_official_origin(monkeypatch):
    from app.services.price_evidence import verified_tikhub_price
    settings=get_settings()
    monkeypatch.setattr(settings,"tikhub_endpoint_prices_json",json.dumps({XiaohongshuCollector.path:.01}))
    for changes in ({"price_usd":.02},{"source_url":"https://tikhub.io.evil.example/pricing"},{"verified_at":"2035-01-01T00:00:00Z"},{"unit":"tokens"}):
        monkeypatch.setattr(settings,"tikhub_price_receipts_json",json.dumps({XiaohongshuCollector.path:{**receipt(),**changes}}))
        assert verified_tikhub_price(XiaohongshuCollector.path) is None
    monkeypatch.setattr(settings,"tikhub_price_receipts_json",json.dumps({XiaohongshuCollector.path:receipt()}))
    assert verified_tikhub_price(XiaohongshuCollector.path)[0] == .01
