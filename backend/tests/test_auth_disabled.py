import pytest
from starlette.requests import Request

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import current_user


def _request(host="127.0.0.1", headers=()):
    return Request({"type": "http", "client": (host, 50000), "headers": [(k.encode(), v.encode()) for k, v in headers]})


@pytest.fixture
def local_mode(monkeypatch):
    monkeypatch.setattr(
        "app.core.security.get_settings",
        lambda: Settings(auth_disabled=True, local_user_id="00000000-0000-0000-0000-000000000001"),
    )


@pytest.mark.asyncio
async def test_auth_disabled_returns_stable_local_user(local_mode):
    user = await current_user(_request(), None)
    assert user.id == "00000000-0000-0000-0000-000000000001"
    assert user.email == "local@opportunity-radar"


@pytest.mark.asyncio
async def test_auth_disabled_rejects_remote_client(local_mode):
    with pytest.raises(AppError) as exc:
        await current_user(_request(host="203.0.113.5"), None)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_auth_disabled_rejects_proxied_request(local_mode):
    with pytest.raises(AppError) as exc:
        await current_user(_request(headers=[("x-forwarded-for", "203.0.113.5")]), None)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_auth_disabled_refuses_to_start_in_production(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "get_settings", lambda: Settings(auth_disabled=True, app_env="production"))
    with pytest.raises(RuntimeError, match="AUTH_DISABLED"):
        async with main.lifespan(main.app):
            pass
