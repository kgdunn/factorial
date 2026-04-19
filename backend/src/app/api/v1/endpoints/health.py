from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.graph.neo4j_driver import get_neo4j_session
from app.schemas.health import HealthResponse
from app.services.anthropic_status import status_tracker

router = APIRouter()


@router.get("", response_model=HealthResponse)
async def health_check():
    """Basic liveness probe — confirms the API process is running."""
    return HealthResponse(status="ok", service="agentic-doe-api")


@router.get("/ready", response_model=HealthResponse)
async def readiness_check(
    db: AsyncSession = Depends(get_db_session),
    neo4j_session=Depends(get_neo4j_session),
):
    """Readiness probe — confirms PostgreSQL and Neo4j are connected."""
    await db.execute(text("SELECT 1"))

    result = await neo4j_session.run("RETURN 1 AS n")
    await result.consume()

    return HealthResponse(status="ok", service="agentic-doe-api")


@router.get("/llm")
async def llm_health(response: Response):
    """Public LLM connection status — drives the global site banner.

    Returns the banner-facing snapshot of the in-memory Anthropic status
    tracker: ``status`` (``ok`` / ``slow`` / ``down``), a rolling
    error rate and p95 latency over the last 5 minutes, and the last
    observed error type. No auth required — the banner is rendered
    on public pages (including ``/login``) and the payload contains
    no secrets.
    """
    response.headers["Cache-Control"] = "no-store"
    return status_tracker.snapshot()
