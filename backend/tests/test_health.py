import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "agentic-doe-api"


@pytest.mark.asyncio
async def test_health_check_returns_json_content_type(client):
    response = await client.get("/api/v1/health")
    assert response.headers["content-type"] == "application/json"
