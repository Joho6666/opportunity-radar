from fastapi import Depends
from ..core.security import CurrentUser, current_user
from ..repositories.memory import MemoryRepository, repository

def get_repository() -> MemoryRepository: return repository
async def get_current_user(user: CurrentUser = Depends(current_user)) -> CurrentUser: return user
