from functools import lru_cache
from ..core.config import get_settings
from ..database.client import create_database_engine
from .memory import repository as memory_singleton
from .postgres import PostgresRepository


@lru_cache
def get_repository_singleton():
    settings = get_settings()
    if settings.use_in_memory_store:
        return memory_singleton
    engine = create_database_engine()
    if engine is None:
        return memory_singleton
    return PostgresRepository(engine)


def create_repository():
    return get_repository_singleton()
