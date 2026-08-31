from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections import defaultdict
from urllib.parse import urlparse
import httpx
from ..core.errors import AppError

USER_AGENT = "OpportunityRadar/0.2 (+https://github.com/Joho6666/opportunity-radar)"
BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal", "metadata.google.com"}
PRIVATE_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("2001:db8::/32"),
)


def _is_blocked_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return True
    return any(ip in network for network in PRIVATE_NETWORKS)


def validate_public_url(url: str, resolver=socket.getaddrinfo) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise AppError("BLOCKED_URL", "只允许 http/https 请求。", 400)
    host = (parsed.hostname or "").strip().lower()
    if not host or host in BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        raise AppError("BLOCKED_HOST", "拒绝访问本地或保留主机。", 400)
    try:
        ipaddress.ip_address(host)
        if _is_blocked_ip(host):
            raise AppError("BLOCKED_HOST", "拒绝访问环回、私有或保留地址。", 400)
    except ValueError:
        pass
    try:
        answers = resolver(host, None)
    except OSError as exc:
        raise AppError("BLOCKED_HOST", "无法解析该主机。", 400) from exc
    for family, _type, _proto, _canon, sockaddr in answers:
        address = sockaddr[0]
        if _is_blocked_ip(address):
            raise AppError("BLOCKED_HOST", "拒绝访问环回、私有或保留地址。", 400)
    return host


class HttpFetcher:
    def __init__(self, timeout: float = 20, retries: int = 2, min_interval: float = 0.2, client: httpx.AsyncClient | None = None) -> None:
        self.timeout = timeout
        self.retries = retries
        self.min_interval = min_interval
        self._client = client
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_call: dict[str, float] = {}

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        host = validate_public_url(url)
        headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
        timeout = kwargs.pop("timeout", self.timeout)
        async with self._locks[host]:
            loop = asyncio.get_event_loop()
            wait = self.min_interval - (loop.time() - self._last_call.get(host, 0))
            if wait > 0:
                await asyncio.sleep(wait)
            last_error: Exception | None = None
            for attempt in range(self.retries + 1):
                try:
                    client = self._client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
                    close = self._client is None
                    try:
                        response = await client.request(method, url, headers=headers, timeout=timeout, **kwargs)
                    finally:
                        if close:
                            await client.aclose()
                    self._last_call[host] = loop.time()
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < self.retries:
                        await asyncio.sleep(0.4 * (attempt + 1))
                        continue
                    response.raise_for_status()
                    return response
                except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                    last_error = exc
                    if attempt >= self.retries:
                        raise
                    await asyncio.sleep(0.4 * (attempt + 1))
            raise last_error or RuntimeError("request failed")

    async def get_json(self, url: str, **kwargs):
        response = await self.request("GET", url, **kwargs)
        return response.json()

    async def post_json(self, url: str, payload: dict, **kwargs):
        response = await self.request("POST", url, json=payload, **kwargs)
        return response.json()


fetcher = HttpFetcher()
