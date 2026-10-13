"""Apply unapplied migrations transactionally. Never replay or alter historical SQL."""
import hashlib
import os
from pathlib import Path
import psycopg


def migrate(url: str, directory: Path) -> int:
    applied = 0
    with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(727273)")
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS public.schema_migrations(name text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())")
            conn.execute("ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY")
            for file in sorted(directory.glob("*.sql")):
                sql = file.read_text()
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                old = conn.execute("SELECT checksum FROM schema_migrations WHERE name=%s", (file.name,)).fetchone()
                if old:
                    if old[0] != checksum:
                        raise RuntimeError(f"Applied migration changed: {file.name}")
                    continue
                # An existing database without this ledger needs explicit adoption;
                # blindly replaying history or guessing checksums is unsafe.
                if file.name.startswith("202608130001") and conn.execute("SELECT to_regclass('public.radars')").fetchone()[0]:
                    raise RuntimeError("Existing schema without ledger: audit applied migrations before adopting the ledger")
                with conn.transaction():
                    conn.execute(sql, prepare=False)
                    conn.execute("INSERT INTO schema_migrations(name,checksum) VALUES(%s,%s)", (file.name,checksum))
                applied += 1
                print(f"Applied {file.name}")
        finally:
            conn.execute("SELECT pg_advisory_unlock(727273)")
    return applied


if __name__ == "__main__":
    from ..core.config import get_settings
    migrate(get_settings().database_url, Path(os.getenv("MIGRATIONS_DIR", "../supabase/migrations")))
