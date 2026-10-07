from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from ..core.config import get_settings


def _ensure_psycopg3(url: str) -> str:
    """SQLAlchemy defaults a bare postgresql:// URL to the psycopg2 dialect,
    which is not installed — the project ships with psycopg (v3)."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def create_database_engine() -> Engine | None:
    """Returns the production PostgreSQL engine when DATABASE_URL is configured.

    V0.1 development uses the in-memory repository until local Supabase is started.
    Repository implementations can switch to this engine without changing API services.
    """
    url = get_settings().database_url
    return create_engine(_ensure_psycopg3(url), pool_pre_ping=True) if url else None
