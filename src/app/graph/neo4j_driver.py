from collections.abc import AsyncGenerator

from neo4j import AsyncGraphDatabase

from app.config import settings

neo4j_driver = AsyncGraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password),
)


async def get_neo4j_session() -> AsyncGenerator:
    async with neo4j_driver.session() as session:
        yield session
