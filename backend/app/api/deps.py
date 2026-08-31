from fastapi import Depends
from ..core.security import CurrentUser, current_user
from ..repositories.base import Repository
from ..repositories.factory import get_repository_singleton


def get_repository() -> Repository:
    return get_repository_singleton()


async def get_current_user(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    return user
