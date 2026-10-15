from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .api import billing, briefs, dashboard, intelligence, opportunities, pipeline, profile, radars, skills
from .core.config import get_settings
from .core.errors import AppError, app_error_handler

@asynccontextmanager
async def lifespan(_: FastAPI):
    from .core.logging import configure_logging

    configure_logging()
    _check_local_auth_mode()
    from .core.config import validate_runtime
    validate_runtime()
    _wire_source_health()
    yield


def _check_local_auth_mode() -> None:
    """AUTH_DISABLED is for a single user on this machine; refuse it in production."""
    settings = get_settings()
    if not settings.auth_disabled:
        return
    if settings.app_env.lower() in {"production", "prod"}:
        raise RuntimeError("AUTH_DISABLED=true is not allowed when APP_ENV is production")
    import logging

    logging.getLogger(__name__).warning("AUTH_DISABLED=true: login is off and only loopback requests are accepted. Local use only.")


def _wire_source_health() -> None:
    """Registry failures feed the source_health ledger; never blocks serving."""
    try:
        from .repositories.factory import get_repository_singleton

        repo = get_repository_singleton()

        def record(slug: str, ok: bool, items: int, latency_ms: int, error_code: str | None = None, error_message: str | None = None) -> None:
            repo.record_source_health(slug, ok, items, latency_ms, error_code, error_message)

        from .collectors.registry import registry

        registry.set_health_recorder(record)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("source health wiring skipped")
settings = get_settings()
app = FastAPI(title="Opportunity Radar API", version="0.1.0", description="Opportunity Engine backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(AppError, app_error_handler)
@app.middleware("http")
async def request_id(request: Request, call_next):
    response = await call_next(request); response.headers["X-Request-ID"] = request.headers.get("X-Request-ID", str(uuid4())); return response
@app.get("/health", tags=["Health"])
async def health(): return {"status":"ok"}
for router in (billing.router, profile.router, radars.router, opportunities.router, skills.router, pipeline.router, briefs.router, dashboard.router, intelligence.router): app.include_router(router)


@app.get("/ready",tags=["Health"])
async def ready():
    from .repositories.factory import get_repository_singleton
    from sqlalchemy import text
    try:
        repo=get_repository_singleton()
        if hasattr(repo,"engine"):
            with repo.engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM schema_migrations LIMIT 1"))
        if get_settings().redis_url:
            from arq import create_pool
            from .workers.queue import redis_settings
            pool=await create_pool(redis_settings())
            try:await pool.ping()
            finally:await pool.aclose()
        return {"status":"ready","storage":"postgresql" if hasattr(repo,"engine") else "volatile-development"}
    except Exception:
        return JSONResponse(status_code=503,content={"status":"not_ready"})
