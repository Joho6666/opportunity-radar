from fastapi import Depends
from ..core.security import CurrentUser, current_user
from ..repositories.base import Repository
from ..repositories.factory import get_repository_singleton


def get_repository() -> Repository:
    return get_repository_singleton()


async def get_current_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    from uuid import uuid4
    from ..services.billing_gateway import paid_context
    with paid_context(get_repository(), user.id, "assistant", str(uuid4())):
        yield user
