from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_v1_router
from app.config import settings
from app.db.session import engine
from app.graph.neo4j_driver import neo4j_driver
from app.services.exceptions import ToolExecutionError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify database connections (skip in testing)
    if settings.app_env != "testing":
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        await neo4j_driver.verify_connectivity()

    yield

    # Shutdown: dispose connection pools
    if settings.app_env != "testing":
        await engine.dispose()
        await neo4j_driver.close()


app = FastAPI(
    title="Agentic Experimental Design & Analysis",
    description="Backend API for AI agent-based Design of Experiments",
    version="0.2.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.exception_handler(ToolExecutionError)
async def tool_execution_error_handler(request, exc: ToolExecutionError):
    """Return a structured 422 response when a DOE tool call fails."""
    content = {"error": exc.message}
    if exc.tool_name:
        content["tool_name"] = exc.tool_name
    return JSONResponse(status_code=422, content=content)
