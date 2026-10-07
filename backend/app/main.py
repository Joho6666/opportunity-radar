from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .api import briefs, dashboard, intelligence, opportunities, pipeline, profile, radars, skills
from .core.config import get_settings
from .core.errors import AppError, app_error_handler

@asynccontextmanager
async def lifespan(_: FastAPI):
    from .core.logging import configure_logging

    configure_logging()
    yield
settings = get_settings()
app = FastAPI(title="Opportunity Radar API", version="0.1.0", description="Opportunity Engine backend", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.add_exception_handler(AppError, app_error_handler)
@app.middleware("http")
async def request_id(request: Request, call_next):
    response = await call_next(request); response.headers["X-Request-ID"] = request.headers.get("X-Request-ID", str(uuid4())); return response
@app.get("/health", tags=["Health"])
async def health(): return {"status":"ok"}
for router in (profile.router, radars.router, opportunities.router, skills.router, pipeline.router, briefs.router, dashboard.router, intelligence.router): app.include_router(router)


@app.on_event("startup")
async def wire_source_health() -> None:
    """Registry failures feed the source_health ledger; never blocks serving."""
    from .repositories.factory import get_repository_singleton

    repo = get_repository_singleton()

    def record(slug: str, ok: bool, items: int, latency_ms: int, error_code: str | None = None, error_message: str | None = None) -> None:
        repo.record_source_health(slug, ok, items, latency_ms, error_code, error_message)

    from .collectors.registry import registry

    registry.set_health_recorder(record)
