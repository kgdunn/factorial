"""Generic tool listing and execution endpoints."""

from typing import Any

from fastapi import APIRouter, Query

from app.schemas.tools import ToolExecuteRequest
from app.services.doe_service import call_tool
from app.services.tools import get_tool_specs

router = APIRouter()


@router.get("")
async def list_tools(
    category: str | None = Query(None, description="Filter by category (e.g. 'experiments')."),
) -> dict[str, Any]:
    """List all available process-improve tool specs.

    Optionally filter by category.  Returns the specs in Anthropic
    ``tools=`` format so they can be inspected by the frontend or
    forwarded to an LLM integration.
    """
    specs = get_tool_specs(category=category)
    return {"tools": specs, "count": len(specs)}


@router.post("/execute")
async def execute_tool(request: ToolExecuteRequest) -> dict[str, Any]:
    """Execute a process-improve tool by name.

    The tool runs in a background thread with a 300-second timeout
    (same path as the agent chat loop).
    """
    return await call_tool(request.tool_name, request.tool_input)
