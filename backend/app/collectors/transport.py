"""Validate DNS at connection time and connect to that exact IP (no second lookup)."""
import asyncio
import httpx
from httpcore._backends.anyio import AnyIOBackend
from .http import _is_blocked_ip, FAKE_IP_NETWORK
from ..core.config import get_settings
from ..core.errors import AppError
import ipaddress


class PublicNetworkBackend(AnyIOBackend):
    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        answers = await asyncio.get_running_loop().getaddrinfo(host, port, type=1)
        settings = get_settings()
        addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
        if not addresses:
            raise AppError("BLOCKED_HOST", "主机解析为空。", 400)
        for address in addresses:
            fake = settings.allow_fake_ip_dns and settings.app_env.lower() == "development" and ipaddress.ip_address(address) in FAKE_IP_NETWORK
            if _is_blocked_ip(address) and not fake:
                raise AppError("BLOCKED_HOST", "连接阶段拒绝私有或保留地址。", 400)
        # HTTPcore keeps the original hostname for TLS/SNI and certificate validation.
        return await super().connect_tcp(addresses[0], port, timeout, local_address, socket_options)


def public_transport():
    transport = httpx.AsyncHTTPTransport(retries=0)
    # httpcore is pinned; this is its documented network backend seam, surfaced by httpx's pool.
    transport._pool._network_backend = PublicNetworkBackend()
    return transport
