"""Service layer bridging FastAPI (async) to process-improve (sync).

All DOE tool calls run in a thread pool via ``asyncio.to_thread`` so
they never block the event loop.  Results are inspected for error dicts
and converted to ``ToolExecutionError`` when appropriate.
"""

import asyncio
import logging
from typing import Any

from app.services.exceptions import ToolExecutionError
from app.services.tools import execute_tool_call

logger = logging.getLogger(__name__)

# Maximum time (seconds) a single DOE computation may run before timeout.
COMPUTATION_TIMEOUT = 300.0


async def call_tool(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Execute a process-improve tool call in a background thread.

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
        If the tool returns an ``{"error": ...}`` dict or times out.
    """
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(execute_tool_call, tool_name, tool_input),
            timeout=COMPUTATION_TIMEOUT,
        )
    except TimeoutError:
        msg = f"Computation timed out after {COMPUTATION_TIMEOUT:.0f} seconds"
        logger.error("Tool %s timed out", tool_name)
        raise ToolExecutionError(msg, tool_name=tool_name) from None

    if isinstance(result, dict) and "error" in result:
        raise ToolExecutionError(result["error"], tool_name=tool_name)

    return result
