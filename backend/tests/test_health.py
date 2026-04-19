import pytest

from app.services.anthropic_status import status_tracker


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


@pytest.mark.asyncio
async def test_llm_health_returns_ok_when_tracker_empty(client):
    status_tracker.reset()
    response = await client.get("/api/v1/health/llm")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["sample_count"] == 0
    assert response.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio
async def test_llm_health_reflects_down_status(client):
    status_tracker.reset()
    for _ in range(3):
        status_tracker.record_error("APIConnectionError")
    response = await client.get("/api/v1/health/llm")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "down"
    assert data["last_error"] == "APIConnectionError"
    status_tracker.reset()
