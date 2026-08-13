from dataclasses import dataclass
from fastapi import Header
from jose import JWTError, jwt
from .config import get_settings
from .errors import AppError


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None = None


async def current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise AppError("UNAUTHORIZED", "请先登录。", 401)
    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
        return CurrentUser(id=str(payload["sub"]), email=payload.get("email"))
    except (JWTError, KeyError) as exc:
        raise AppError("INVALID_TOKEN", "登录状态无效或已过期。", 401) from exc
