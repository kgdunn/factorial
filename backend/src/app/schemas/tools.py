"""Pydantic schemas for the generic tool execution endpoints."""

from typing import Any

from pydantic import BaseModel, Field


class ToolExecuteRequest(BaseModel):
    """Request body for POST /api/v1/tools/execute."""

    tool_name: str = Field(..., min_length=1, description="Registered tool name.")
    tool_input: dict[str, Any] = Field(default_factory=dict, description="Keyword arguments for the tool.")
