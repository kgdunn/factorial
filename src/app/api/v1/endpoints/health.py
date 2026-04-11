from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.graph.neo4j_driver import get_neo4j_session
from app.schemas.health import HealthResponse

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
