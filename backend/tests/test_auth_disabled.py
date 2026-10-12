import pytest

from app.core.config import Settings
from app.core.security import current_user


@pytest.mark.asyncio
async def test_auth_disabled_returns_stable_local_user(monkeypatch):
    monkeypatch.setattr(
        "app.core.security.get_settings",
        lambda: Settings(auth_disabled=True, local_user_id="00000000-0000-0000-0000-000000000001"),
    )
    user = await current_user(None)
    assert user.id == "00000000-0000-0000-0000-000000000001"
    assert user.email == "local@opportunity-radar"
