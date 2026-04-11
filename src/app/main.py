from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.v1.router import api_v1_router
from app.config import settings
from app.db.session import engine
from app.graph.neo4j_driver import neo4j_driver


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
    version="0.1.0",
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
