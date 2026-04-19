"""Service layer bridging FastAPI (async) to process-improve (sync).

All DOE tool calls run off the event loop via
:func:`app.services.tools.execute_tool_call_async`, which delegates to
``process_improve.tool_safety.safe_execute_tool_call`` when safe mode
is enabled. The wall-clock timeout and memory cap are enforced inside
``safe_execute_tool_call``, so this module no longer layers its own
``asyncio.wait_for``.
"""

import logging
from typing import Any

from app.services.exceptions import ToolExecutionError
from app.services.tools import execute_tool_call_async

logger = logging.getLogger(__name__)


async def call_tool(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Execute a process-improve tool call without blocking the event loop.

    Parameters
    ----------
    tool_name:
        Registered tool name (e.g. ``"generate_design"``).
    tool_input:
        Keyword arguments for the tool, matching its ``input_schema``.

    Returns
    -------
    dict
        The tool's JSON-serialisable result dict.

    Raises
    ------
    ToolExecutionError
        If the tool returns an ``{"error": ...}`` dict, times out,
        breaks an input-size limit, or the worker subprocess dies.
    """
    result, _duration = await execute_tool_call_async(tool_name, tool_input)

    if isinstance(result, dict) and "error" in result:
        raise ToolExecutionError(result["error"], tool_name=tool_name)

    return result
