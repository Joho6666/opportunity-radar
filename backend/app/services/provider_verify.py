"""测试连接：仅调用 TikHub 官方用户信息端点（不发起任何内容采集）。

- 不重试、不经过采集器；请求头携带 Bearer 密钥，响应正文一律不返回、不记录。
- 结果只保留状态码、耗时与固定文案，绝不包含密钥明文。
"""
import time
from datetime import UTC, datetime

import httpx

from ..collectors.transport import public_transport

USER_INFO_ENDPOINT = "/api/v1/tikhub/user/get_user_info"


async def verify_tikhub_key(api_key: str, base_url: str, transport=None, timeout: float = 12.0) -> dict:
    started = time.monotonic()
    tested_at = datetime.now(UTC).isoformat()
    url = f"{base_url.rstrip('/')}{USER_INFO_ENDPOINT}"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport or public_transport(), trust_env=False) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"})
    except httpx.HTTPError:
        return {"ok": False, "http_status": None, "latency_ms": int((time.monotonic() - started) * 1000), "tested_at": tested_at,
                "message": "网络不可达或超时；未完成连接测试。"}
    latency_ms = int((time.monotonic() - started) * 1000)
    if response.status_code == 200:
        return {"ok": True, "http_status": 200, "latency_ms": latency_ms, "tested_at": tested_at,
                "message": "连接成功（官方用户信息端点，未发起内容采集）。"}
    if response.status_code in {401, 403}:
        message = f"密钥无效或已过期（HTTP {response.status_code}，服务端拒绝鉴权）。"
    elif response.status_code == 429:
        message = "请求过于频繁（HTTP 429），请稍后重试。"
    else:
        message = f"服务端返回 HTTP {response.status_code}；未完成连接测试。"
    return {"ok": False, "http_status": response.status_code, "latency_ms": latency_ms, "tested_at": tested_at, "message": message}
