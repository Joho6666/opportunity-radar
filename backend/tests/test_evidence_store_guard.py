import pytest

from app.core.config import Settings
from app.repositories import factory


def test_postgres_mode_never_silently_falls_back(monkeypatch):
    factory.get_repository_singleton.cache_clear()
    monkeypatch.setattr(
        factory,
        "get_settings",
        lambda: Settings(use_in_memory_store=False, database_url=""),
    )
    monkeypatch.setattr(factory, "create_database_engine", lambda: None)
    try:
        with pytest.raises(RuntimeError, match="DATABASE_URL"):
            factory.get_repository_singleton()
    finally:
        factory.get_repository_singleton.cache_clear()
