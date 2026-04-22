import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.api.rate_limit import limiter
from app.api.v1.router import api_v1_router
from app.config import settings
from app.db.session import engine
from app.graph.neo4j_driver import neo4j_driver
from app.logging_filters import install_log_injection_guard
from app.services.anthropic_status import _llm_performance_snapshot_loop
from app.services.exceptions import ToolExecutionError

install_log_injection_guard()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast if production secrets are missing or weak.
    settings.validate_production_secrets()

    # Startup: verify database connections (skip in testing)
    if settings.app_env != "testing":
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        await neo4j_driver.verify_connectivity()

    # Background task: log an LLM-performance rollup to admin_events
    # approximately hourly. Skip in testing to keep tests hermetic.
    snapshot_task: asyncio.Task | None = None
    if settings.app_env != "testing":
        snapshot_task = asyncio.create_task(_llm_performance_snapshot_loop())
        app.state.llm_snapshot_task = snapshot_task

    yield

    # Shutdown: stop the background snapshot loop, then dispose pools.
    if snapshot_task is not None:
        snapshot_task.cancel()
        with suppress(asyncio.CancelledError):
            await snapshot_task

    if settings.app_env != "testing":
        await engine.dispose()
        await neo4j_driver.close()


# Disable OpenAPI docs in production to reduce attack surface.
_docs_url = None if settings.app_env == "production" else "/docs"
_redoc_url = None if settings.app_env == "production" else "/redoc"
_openapi_url = None if settings.app_env == "production" else "/openapi.json"

app = FastAPI(
    title="Factorial",
    description="Backend API for conversational Design of Experiments",
    version="0.6.0",
    lifespan=lifespan,
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    openapi_url=_openapi_url,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)

# Rate limiting (slowapi).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(api_v1_router, prefix="/api/v1")


@app.exception_handler(ToolExecutionError)
async def tool_execution_error_handler(request, exc: ToolExecutionError):
    """Return a structured response when a DOE tool call fails.

    Status is taken from the exception's ``http_status`` class attribute
    so subclasses map to 408 (timeout), 413 (input too large), 429
    (budget exceeded), or 507 (memory cap) rather than a generic 422.
    """
    content = {"error": exc.message}
    if exc.tool_name:
        content["tool_name"] = exc.tool_name
    return JSONResponse(status_code=exc.http_status, content=content)
