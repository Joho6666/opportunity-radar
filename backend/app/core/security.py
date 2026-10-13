from dataclasses import dataclass
from fastapi import Header, Request
from jose import JWTError, jwt
from .config import get_settings
from .errors import AppError


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_direct_local_request(request: Request) -> bool:
    # A forwarding header means a proxy relayed the request, so the peer address is not the real client.
    if "x-forwarded-for" in request.headers or "forwarded" in request.headers:
        return False
    return request.client is not None and request.client.host in _LOOPBACK_HOSTS


async def current_user(request: Request, authorization: str | None = Header(default=None)) -> CurrentUser:
    settings = get_settings()
    if settings.auth_disabled:
        if not _is_direct_local_request(request):
            raise AppError("LOCAL_MODE_REMOTE_FORBIDDEN", "本机单用户模式只接受本机请求。", 403)
        return CurrentUser(id=settings.local_user_id, email="local@opportunity-radar")
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("UNAUTHORIZED", "请先登录。", 401)
    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        return CurrentUser(id=str(payload["sub"]), email=payload.get("email"))
    except (JWTError, KeyError) as exc:
        raise AppError("INVALID_TOKEN", "登录状态无效或已过期。", 401) from exc
