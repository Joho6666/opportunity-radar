"""Deterministic count of paid provider calls for one query unit.

Used by source stats and UI estimates. It counts *planned* calls, including
the extra WeChat detail/share calls, one call per Telegram channel and one call
per imported Toutiao link. It never changes billing limits.
"""
from __future__ import annotations


def planned_provider_calls(source: str, source_config: dict | None = None) -> int:
    config = source_config or {}
    if source == "wechat_search":
        if config.get("wechat_business_type") != "video":
            return 1
        try:
            count = int(str(config.get("wechat_share_links") or "1"))
        except (TypeError, ValueError):
            count = 1
        count = count if count in {1, 2, 3} else 1
        return 1 + 2 * count
    if source == "telegram":
        from ..collectors.tikhub_modes import parse_telegram_channels
        return len(parse_telegram_channels(config.get("telegram_channels")))
    if source == "toutiao":
        from ..collectors.tikhub_modes import parse_toutiao_links
        return len(parse_toutiao_links(config.get("toutiao_links")))
    return 1
