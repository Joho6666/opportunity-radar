"""Create the explicitly authorized small batch once. Does not make HTTP calls.

Run from backend: ../.venv/bin/python ../scripts/authorize_tikhub_batch.py
Configure PAID_BATCH_ID first. Re-running cannot replenish an existing batch.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import text
from app.core.config import get_settings
from app.database.client import create_database_engine
from app.repositories.postgres import PostgresRepository, as_uuid
from app.api.billing import Authorization, authorize, status
from app.core.security import CurrentUser


async def main():
    settings = get_settings()
    if not settings.paid_batch_id or settings.use_in_memory_store or not settings.database_url:
        raise SystemExit("PAID_BATCH_ID and PostgreSQL persistence are required")
    repo = PostgresRepository(create_database_engine())
    uid = settings.local_user_id
    repo.get_profile(uid)
    with repo.engine.begin() as conn:
        conn.execute(text("INSERT INTO billing_batches(id,user_id,enabled,providers,sources,request_limit,cost_limit_micros,request_limit_micros) VALUES(:id,CAST(:uid AS uuid),true,'[\"tikhub\"]','[\"xiaohongshu\",\"weibo\",\"douyin\"]',5,500000,100000) ON CONFLICT(id) DO NOTHING"), {"id": settings.paid_batch_id, "uid": as_uuid(uid)})
        batch = conn.execute(text("SELECT user_id,request_limit,cost_limit_micros,request_limit_micros FROM billing_batches WHERE id=:id"), {"id": settings.paid_batch_id}).one()
        if str(batch.user_id) != as_uuid(uid) or tuple(batch[1:]) != (5,500000,100000):
            raise SystemExit("Existing batch differs from the authorized limits; refusing to modify it")
    await authorize("evidence", Authorization(enabled=True, providers=["tikhub"], allow_scheduled=False, run_requests=1, daily_requests=5, run_cost_usd=.1, daily_cost_usd=.5), CurrentUser(id=uid), repo)
    result = await status(CurrentUser(id=uid), repo)
    print({"paid_api_enabled": result["paid_api_enabled"], "batch": result["batch"], "scheduled": False})


if __name__ == "__main__":
    asyncio.run(main())
