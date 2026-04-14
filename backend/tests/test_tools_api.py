"""Tests for the /api/v1/tools endpoints."""

import pytest


@pytest.mark.asyncio
async def test_list_all_tools(client):
    """GET /api/v1/tools returns all registered tools."""
    response = await client.get("/api/v1/tools")
    assert response.status_code == 200

    data = response.json()
    assert "tools" in data
    assert "count" in data
    assert data["count"] >= 30
    assert len(data["tools"]) == data["count"]

    # Verify spec format
    for spec in data["tools"]:
        assert "name" in spec
        assert "description" in spec
        assert "input_schema" in spec


@pytest.mark.asyncio
async def test_list_tools_by_category(client):
    """GET /api/v1/tools?category=experiments returns only experiment tools."""
    response = await client.get("/api/v1/tools", params={"category": "experiments"})
    assert response.status_code == 200

    data = response.json()
    assert data["count"] >= 8
    for spec in data["tools"]:
        assert spec.get("category") == "experiments"


@pytest.mark.asyncio
async def test_list_tools_empty_category(client):
    """Unknown category returns empty list, not an error."""
    response = await client.get("/api/v1/tools", params={"category": "nonexistent"})
    assert response.status_code == 200
    assert response.json()["count"] == 0


@pytest.mark.asyncio
async def test_execute_tool(client):
    """POST /api/v1/tools/execute runs a tool and returns its result."""
    payload = {
        "tool_name": "robust_summary_stats",
        "tool_input": {"values": [1.0, 2.0, 3.0, 4.0, 5.0]},
    }
    response = await client.post("/api/v1/tools/execute", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "mean" in data
    assert "median" in data
    assert data["N_non_missing"] == 5


@pytest.mark.asyncio
async def test_execute_unknown_tool(client):
    """Executing an unknown tool returns 422."""
    payload = {
        "tool_name": "nonexistent_tool",
        "tool_input": {},
    }
    response = await client.post("/api/v1/tools/execute", json=payload)
    assert response.status_code == 422
    assert "error" in response.json()


@pytest.mark.asyncio
async def test_execute_tool_empty_name(client):
    """Empty tool name is rejected by Pydantic validation."""
    payload = {"tool_name": "", "tool_input": {}}
    response = await client.post("/api/v1/tools/execute", json=payload)
    assert response.status_code == 422
