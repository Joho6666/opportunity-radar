"""Limited-mode adapters for platforms without global keyword content search.

Each adapter is honest about its scope and derived from a real paid response
archived on 2026-10-18 (see tikhub-mode-verification.json):

- Telegram: keyword search *inside named public channels* only.
- LinkedIn: jobs search only; results are hiring signals, never buyer demand.
- Toutiao: import by article link only; the API has no keyword content search.

All paid calls flow through HttpFetcher -> billing_gateway reserve/finish, so
prices, run limits and the ledger are never bypassed. No pagination, no
automatic retries (LinkedIn gets exactly one explicit retry on transient 400).
"""
from __future__ import annotations

import asyncio
import html
import re
from datetime import UTC, datetime
from urllib.parse import urlencode, urlsplit

import httpx

from .base import CollectorCapabilities, SourceAdapter
from .http import fetcher
from .text import clean_text
from ..core.config import get_settings
from ..core.errors import AppError
from ..schemas.domain import RawItem

TELEGRAM_PATH = "/api/v1/telegram/web/fetch_channel_search"
LINKEDIN_PATH = "/api/v1/linkedin/web_v2/search_jobs"
TOUTIAO_ARTICLE_PATH = "/api/v1/toutiao/web/get_article_info"
WECHAT_DETAIL_PATH = "/api/v1/wechat_channels/v2/fetch_video_detail"
WECHAT_SHARE_PATH = "/api/v1/wechat_channels/v2/fetch_video_share_url"

TELEGRAM_NOTE = "指定频道内搜索；不是全站关键词搜索。"
TOUTIAO_NOTE = "按链接导入；不支持关键词搜索。"
LINKEDIN_NOTE = "招聘信号（潜在客户线索）；不是买方直接需求。"

_CHANNEL_RE = re.compile(r"^[A-Za-z0-9_]{3,64}$")
_TG_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/([^/?#]+)", re.I)
_TT_ARTICLE_RE = re.compile(r"^/article/(\d+)/?$")


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _headers() -> dict[str, str]:
    settings = get_settings()
    if not settings.tikhub_api_key:
        raise AppError("SOURCE_NOT_CONFIGURED", "TikHub 未配置；不会发送请求。", 400)
    return {"Authorization": f"Bearer {settings.tikhub_api_key}", "Accept": "application/json"}


def _envelope(payload, label: str) -> dict:
    if not isinstance(payload, dict):
        raise AppError("PROVIDER_RESPONSE_INVALID", f"{label} 返回非 JSON 对象。", 502)
    if payload.get("code") not in (None, 200):
        raise AppError("PROVIDER_RESPONSE_INVALID", f"{label} 返回非成功响应。", 502)
    return payload


def _iso(value) -> datetime | None:
    text = _text(value).replace("+0000", "+00:00").replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _time(value) -> datetime | None:
    text = _text(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _epoch(value) -> datetime | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number > 10**12:
        number //= 1000
    try:
        return datetime.fromtimestamp(number, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


# ---------------------------------------------------------------- parsers
def parse_telegram_channels(value) -> list[str]:
    """Accept @name, t.me/name, comma/space/newline separated; reject junk."""
    if isinstance(value, (list, tuple)):
        tokens = [str(item) for item in value]
    else:
        tokens = [token for token in re.split(r"[\s,，;；]+", str(value or "")) if token]
    if len(tokens) > 3:
        raise AppError("TELEGRAM_CHANNELS_LIMIT", "Telegram 最多填写 3 个频道用户名。", 422)
    channels: list[str] = []
    for token in tokens:
        match = _TG_URL_RE.match(token)
        name = match.group(1) if match else token.lstrip("@")
        name = name.strip().strip("/")
        if not _CHANNEL_RE.fullmatch(name):
            continue
        if name not in channels:
            channels.append(name)
    return channels


def parse_toutiao_links(value) -> list[dict[str, str]]:
    """Accept only public Toutiao /article/<numeric-id>/ links; max 3."""
    if isinstance(value, (list, tuple)):
        tokens = [str(item.get("url") if isinstance(item, dict) else item) for item in value]
    else:
        tokens = [token for token in re.split(r"[\s,，;；]+", str(value or "")) if token]
    if len(tokens) > 3:
        raise AppError("TOUTIAO_LINKS_LIMIT", "今日头条最多填写 3 条文章链接。", 422)
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for token in tokens:
        try:
            parsed = urlsplit(token)
        except ValueError:
            continue
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not (host == "toutiao.com" or host.endswith(".toutiao.com")):
            continue
        match = _TT_ARTICLE_RE.match(parsed.path or "")
        if not match or match.group(1) in seen:
            continue
        seen.add(match.group(1))
        links.append({"id": match.group(1), "url": f"https://www.toutiao.com/article/{match.group(1)}/"})
    return links


def parse_wechat_share_count(value) -> int:
    if value is None or str(value).strip() == "":
        return 1
    try:
        count = int(str(value).strip())
    except (TypeError, ValueError):
        raise AppError("WECHAT_SHARE_COUNT_INVALID", "视频号分享链条数只能是 1–3。", 422)
    if count not in {1, 2, 3}:
        raise AppError("WECHAT_SHARE_COUNT_INVALID", "视频号分享链条数只能是 1–3。", 422)
    return count


# ---------------------------------------------------------------- telegram
def parse_telegram_messages(payload: dict, channel: str, query: str) -> list[RawItem]:
    payload = _envelope(payload, "Telegram")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        raise AppError("PROVIDER_SCHEMA_CHANGED", "Telegram 响应缺少 data.messages。", 502)
    items: list[RawItem] = []
    for message in data["messages"]:
        if not isinstance(message, dict):
            continue
        text = _text(message.get("text")) or clean_text(message.get("text"))
        message_id = str(message.get("id") or "").strip()
        url = _text(message.get("url")) or (f"https://t.me/{channel}/{message_id}" if message_id else "")
        if not text or not message_id or not url.startswith("https://t.me/"):
            continue
        title = re.sub(r"\s+", " ", text).strip()[:120]
        items.append(RawItem(
            external_id=f"{channel}:{message_id}", title=title, content=text, url=url,
            author=channel, source="telegram", platform="telegram",
            published_at=_iso(message.get("date")),
            metadata={
                "content_kind": "channel_post", "query": query, "channel": channel,
                "message_id": message_id, "message_type": _text(message.get("type")),
                "backend": data.get("backend"), "scanned": data.get("scanned"),
                "matched": data.get("matched"), "mode": "channel_search",
                "mode_note": TELEGRAM_NOTE, "acquisition_tool": "tikhub",
                "original_platform": "telegram", "validation_status": "live_verified",
                "provider_request_id": payload.get("request_id"),
            },
        ))
    return items


class TelegramChannelCollector(SourceAdapter):
    slug = "telegram"
    path = TELEGRAM_PATH
    method = "GET"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, detail=False)

    def request_args(self, query: str, config: dict[str, str] | None = None) -> dict:
        channels = parse_telegram_channels((config or {}).get("telegram_channels"))
        return {"channel": channels[0] if channels else "channel", "query": query, "limit": 20}

    async def search(self, query: str) -> list[RawItem]:
        raise AppError("TELEGRAM_CHANNELS_REQUIRED", "Telegram 必须填写 1–3 个频道用户名。", 422)

    async def search_configured(self, query: str, source_config: dict[str, str]) -> list[RawItem]:
        channels = parse_telegram_channels(source_config.get("telegram_channels"))
        if not channels:
            raise AppError("TELEGRAM_CHANNELS_REQUIRED", "Telegram 必须填写 1–3 个频道用户名。", 422)
        query = (query or "").strip()
        if not query:
            raise AppError("TIKHUB_QUERY_REQUIRED", "关键词不能为空。", 400)
        base = get_settings().tikhub_base_url.rstrip("/") + self.path
        items: list[RawItem] = []
        for channel in channels:
            params = {"channel": channel, "query": query, "limit": 20}
            payload = await fetcher.get_json(base + "?" + urlencode(params), headers=_headers(), timeout=45,
                                             billable_provider="tikhub", billable_source=self.slug)
            parsed = parse_telegram_messages(payload, channel, query)
            for item in parsed:
                item.metadata["provider_endpoint"] = base
            items.extend(parsed)
        return items


# ---------------------------------------------------------------- linkedin
def parse_linkedin_jobs(payload: dict, query: str) -> list[RawItem]:
    payload = _envelope(payload, "LinkedIn")
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise AppError("PROVIDER_SCHEMA_CHANGED", "LinkedIn 响应缺少 data.data。", 502)
    items: list[RawItem] = []
    for row in data["data"]:
        if not isinstance(row, dict):
            continue
        company = clean_text(row.get("company"))
        job_title = clean_text(row.get("job_title"))
        url = _text(row.get("job_url"))
        if not company or not job_title or not url.startswith("https://www.linkedin.com/jobs/view/"):
            continue
        location = clean_text(row.get("location"))
        remote = clean_text(row.get("remote"))
        posted_time = _text(row.get("posted_time"))
        salary = clean_text(row.get("salary"))
        content = "\n".join([
            f"职位：{job_title}", f"公司：{company}", f"地点：{location or '未注明'}",
            f"工作方式：{remote or '未注明'}", f"发布时间：{posted_time or '未注明'}",
            f"薪资：{salary or '未注明'}",
            "信号说明：在招视频相关岗位的公司通常有持续的视频制作/剪辑需求。",
            "分类：招聘信号（潜在客户线索），不是买方直接需求。",
        ])
        items.append(RawItem(
            external_id=_text(row.get("job_urn")) or url.rsplit("/", 1)[-1],
            title=f"{company} · {job_title}", content=content, url=url,
            author=company, source="linkedin", platform="linkedin",
            published_at=_time(posted_time),
            metadata={
                "content_kind": "job_posting", "query": query, "company": company,
                "job_title": job_title, "location": location, "remote": remote,
                "salary": salary, "posted_time": posted_time,
                "lead_kind": "hiring_signal", "signal_label": "招聘信号（潜在客户线索）",
                "signal_reason": "在招视频相关岗位的公司通常有持续的视频制作/剪辑需求",
                "mode": "hiring_signal", "mode_note": LINKEDIN_NOTE,
                "acquisition_tool": "tikhub", "original_platform": "linkedin",
                "validation_status": "live_verified", "provider_request_id": payload.get("request_id"),
            },
        ))
    return items


class LinkedInJobsCollector(SourceAdapter):
    slug = "linkedin"
    path = LINKEDIN_PATH
    method = "GET"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, detail=False)

    def request_args(self, query: str) -> dict:
        return {"keywords": query, "geo_code": "92000000", "sort_by": "Most recent"}

    async def search(self, query: str) -> list[RawItem]:
        return await self.search_configured(query, {})

    async def search_configured(self, query: str, source_config: dict[str, str]) -> list[RawItem]:
        query = (query or "").strip()
        if not query:
            raise AppError("TIKHUB_QUERY_REQUIRED", "关键词不能为空。", 400)
        base = get_settings().tikhub_base_url.rstrip("/") + self.path
        url = base + "?" + urlencode(self.request_args(query))
        last: httpx.HTTPStatusError | None = None
        for attempt in (1, 2):
            try:
                payload = await fetcher.get_json(url, headers=_headers(), timeout=60,
                                                 billable_provider="tikhub", billable_source=self.slug)
                break
            except httpx.HTTPStatusError as exc:
                last = exc
                if attempt == 2 or exc.response.status_code not in {400, 500, 502, 503, 504}:
                    raise
                # Explicitly one retry only; the retry is another paid request.
                await asyncio.sleep(0.6)
        else:  # pragma: no cover - loop always returns or raises
            raise last or RuntimeError("LinkedIn request failed")
        items = parse_linkedin_jobs(payload, query)
        for item in items:
            item.metadata["provider_endpoint"] = base
        return items


# ---------------------------------------------------------------- toutiao
def _plain_html(value: str) -> str:
    value = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", value, flags=re.S | re.I)
    value = re.sub(r"<br\s*/?>|</p>|</div>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"[ \t\u00a0]+", " ", value).strip()


def parse_toutiao_article(payload: dict, link: dict[str, str]) -> RawItem:
    payload = _envelope(payload, "今日头条")
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        article = data["data"]
    else:
        raise AppError("PROVIDER_SCHEMA_CHANGED", "今日头条响应缺少 data.data。", 502)
    raw_html = article.get("content")
    if not isinstance(raw_html, str) or not raw_html.strip():
        raise AppError("PROVIDER_SCHEMA_CHANGED", "今日头条文章缺少正文。", 502)
    title_match = re.search(r'class="[^"]*tt-title[^"]*"[^>]*>(.*?)</', raw_html, re.S)
    author_match = re.search(r'class="[^"]*author-name-link[^"]*"[^>]*>(.*?)</', raw_html, re.S)
    epoch_match = re.search(r'class="[^"]*sub-title[^"]*"[^>]*>\s*(\d{10})', raw_html)
    title = html.unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip() if title_match else ""
    author = html.unescape(re.sub(r"<[^>]+>", "", author_match.group(1))).strip() if author_match else ""
    content = _plain_html(raw_html)
    if not title:
        title = next((line.strip() for line in content.splitlines() if line.strip()), "")[:160]
    if not title or not content:
        raise AppError("PROVIDER_SCHEMA_CHANGED", "今日头条文章缺少标题或正文。", 502)
    item_id = str(article.get("item_id") or article.get("group_id") or link["id"])
    return RawItem(
        external_id=item_id, title=title[:200], content=content, url=link["url"],
        author=author or None, source="toutiao", platform="toutiao",
        published_at=_epoch(epoch_match.group(1)) if epoch_match else None,
        metadata={
            "content_kind": "article", "query": "", "aweme_id": item_id,
            "mode": "link_import", "mode_note": TOUTIAO_NOTE,
            "import_url": link["url"], "acquisition_tool": "tikhub",
            "original_platform": "toutiao", "validation_status": "live_verified",
            "provider_request_id": payload.get("request_id"),
        },
    )


class ToutiaoLinkCollector(SourceAdapter):
    slug = "toutiao"
    path = TOUTIAO_ARTICLE_PATH
    method = "GET"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, detail=True)

    def request_args(self, query: str) -> dict:
        return {"aweme_id": "7450114952884503059"}

    async def search(self, query: str) -> list[RawItem]:
        raise AppError("TOUTIAO_LINKS_REQUIRED", "今日头条只支持按链接导入，请粘贴 1–3 条文章链接。", 422)

    async def search_configured(self, query: str, source_config: dict[str, str]) -> list[RawItem]:
        links = parse_toutiao_links(source_config.get("toutiao_links"))
        if not links:
            raise AppError("TOUTIAO_LINKS_REQUIRED", "今日头条只支持按链接导入，请粘贴 1–3 条文章链接。", 422)
        base = get_settings().tikhub_base_url.rstrip("/") + self.path
        items: list[RawItem] = []
        for link in links:
            payload = await fetcher.get_json(base + "?" + urlencode({"aweme_id": link["id"]}),
                                             headers=_headers(), timeout=45,
                                             billable_provider="tikhub", billable_source=self.slug)
            item = parse_toutiao_article(payload, link)
            item.metadata["provider_endpoint"] = base
            items.append(item)
        return items


MODE_COLLECTORS = (TelegramChannelCollector, LinkedInJobsCollector, ToutiaoLinkCollector)
