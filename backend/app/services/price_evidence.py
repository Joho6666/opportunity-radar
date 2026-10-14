"""Endpoint prices require a server-admin receipt, not a generic advertised range.

The receipt records a human's verification of the exact endpoint quote. It is
not proof supplied by the provider and never triggers a pricing API request.
"""
import json
import math
from datetime import UTC, datetime
from urllib.parse import urlsplit
from ..core.config import get_settings


def tikhub_endpoint(source):
    from ..collectors.tikhub_cn import DOMESTIC_COLLECTORS
    from ..collectors.tikhub import TikHubCollector
    return next((cls.path for cls in (*DOMESTIC_COLLECTORS, TikHubCollector) if cls.slug == source), None)


def verified_tikhub_price(endpoint):
    settings=get_settings()
    try:
        prices=json.loads(settings.tikhub_endpoint_prices_json or "{}")
        receipts=json.loads(settings.tikhub_price_receipts_json or "{}")
        price=prices.get(endpoint)
        receipt=receipts.get(endpoint)
        if not isinstance(receipt,dict) or not isinstance(price,(float,int)) or isinstance(price,bool) or not math.isfinite(price) or price <= 0:
            return None
        if receipt.get("price_usd") != price or receipt.get("unit") != "USD/request" or not receipt.get("verified_by"):
            return None
        url=urlsplit(receipt.get("source_url", ""))
        if url.scheme != "https" or url.hostname not in {"tikhub.io","user.tikhub.io","docs.tikhub.io"} or url.username or url.password:
            return None
        verified=datetime.fromisoformat(receipt.get("verified_at", "").replace("Z","+00:00"))
        if verified.tzinfo is None or verified > datetime.now(UTC):
            return None
        return price, {key:receipt[key] for key in ("price_usd","unit","source_url","verified_at","verified_by")}
    except (ValueError,TypeError,AttributeError):
        return None
