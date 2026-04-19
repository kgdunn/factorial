"""Hosted MCP-style tool endpoint.

Exposes the ``process_improve`` tool registry as an HTTP surface for
machine-to-machine agents (including the agent hosted at factori.al).

This is a REST shim, not full MCP streamable-HTTP protocol. Fully
compliant MCP transport can be layered on top later; for now we focus
on the security envelope:

- Auth: requires JWT or the shared ``X-API-Key`` (via ``require_auth``).
- Rate: slowapi IP-based limit (``settings.mcp_rate_limit``).
- Budget: per-identity daily CPU-second quota (``tool_usage`` table).
- Isolation: tool execution runs off the event loop in a forked
  subprocess with a wall-clock timeout and memory cap (via
  ``process_improve.tool_safety.safe_execute_tool_call``).

The endpoint is only mounted when ``settings.mcp_enabled`` is true.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthUser, require_auth
from app.api.rate_limit import limiter
from app.config import settings
from app.db.session import get_db_session
from app.services.exceptions import ToolExecutionError
from app.services.tool_budget import check_budget, record_call
from app.services.tools import execute_tool_call_async, get_tool_specs

router = APIRouter()


class ToolListResponse(BaseModel):
    tools: list[dict[str, Any]]


class ToolInvokeRequest(BaseModel):
    input: dict[str, Any] = Field(default_factory=dict)


class ToolInvokeResponse(BaseModel):
    tool: str
    result: Any
    cpu_seconds: float


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(
    _user: AuthUser = Depends(require_auth),
    category: str | None = None,
) -> ToolListResponse:
    """Return the registered tool specs in Anthropic-compatible format."""
    return ToolListResponse(tools=get_tool_specs(category=category))


@router.post("/tools/{tool_name}", response_model=ToolInvokeResponse)
@limiter.limit(settings.mcp_rate_limit)
async def invoke_tool(
    request: Request,  # noqa: ARG001  required by slowapi
    tool_name: str,
    body: ToolInvokeRequest,
    current_user: AuthUser = Depends(require_auth),
    db: AsyncSession = Depends(get_db_session),
) -> ToolInvokeResponse:
    """Execute a tool call in a resource-isolated worker subprocess."""
    await check_budget(db, current_user.id)

    try:
        result, duration = await execute_tool_call_async(tool_name, body.input)
    except ToolExecutionError as exc:
        # Even failed calls consume the caller's budget so pathological
        # inputs cannot be retried indefinitely at zero cost.
        await record_call(db, current_user.id, duration_seconds=0.1)
        raise HTTPException(status_code=exc.http_status, detail=exc.message) from exc

    await record_call(db, current_user.id, duration_seconds=duration)

    if isinstance(result, dict) and "error" in result:
        # The tool reported a structured error. Count as a successful
        # call for budget purposes but return 400 so clients can react.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"])

    return ToolInvokeResponse(tool=tool_name, result=result, cpu_seconds=round(duration, 3))
