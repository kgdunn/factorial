"""Tool bridge: thin adapter from process_improve.tool_spec to the app's tool API.

Wraps the real ``process_improve`` functions so that:

- ``ValueError`` / ``TypeError`` from unknown or mis-called tools are
  converted to :class:`~app.services.exceptions.ToolExecutionError`.
- Tool names are validated against an allowlist before execution.
- All exceptions (not just ValueError/TypeError) are caught so that
  unexpected errors are returned as structured error responses.
- The public API (``get_tool_specs``, ``execute_tool_call``) stays
  identical to the old stub module so **no other file needs import changes**.
"""

from __future__ import annotations

import logging
from typing import Any

from process_improve.tool_spec import execute_tool_call as _pi_execute
from process_improve.tool_spec import get_tool_specs as _pi_get_specs

from app.services.exceptions import ToolExecutionError

logger = logging.getLogger(__name__)

# Build an allowlist of valid tool names at import time.
_ALLOWED_TOOL_NAMES: frozenset[str] = frozenset(
    spec["name"] for spec in _pi_get_specs() if "name" in spec
)


def get_tool_specs(
    names: list[str] | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Return tool specs in Anthropic API format.

    Parameters
    ----------
    names:
        Optional allow-list of tool names.
    category:
        Optional category filter (e.g. ``"experiments"``).
    """
    return _pi_get_specs(names=names, category=category)


def execute_tool_call(tool_name: str, tool_input: dict[str, Any]) -> Any:  # noqa: ANN401
    """Dispatch a tool call, mapping errors to ``ToolExecutionError``.

    Parameters
    ----------
    tool_name:
        Registered tool name (e.g. ``"generate_design"``).
    tool_input:
        Keyword arguments for the tool.

    Raises
    ------
    ToolExecutionError
        If the tool name is unknown, the input is invalid, or execution fails.
    """
    # Validate tool name against the allowlist.
    if tool_name not in _ALLOWED_TOOL_NAMES:
        raise ToolExecutionError(
            f"Unknown tool: {tool_name!r}. Valid tools: {sorted(_ALLOWED_TOOL_NAMES)}",
            tool_name=tool_name,
        )

    # Validate tool_input is a dict.
    if not isinstance(tool_input, dict):
        raise ToolExecutionError(
            f"Tool input must be a dict, got {type(tool_input).__name__}",
            tool_name=tool_name,
        )

    try:
        return _pi_execute(tool_name, tool_input)
    except (ValueError, TypeError) as exc:
        raise ToolExecutionError(str(exc), tool_name=tool_name) from exc
    except ToolExecutionError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error executing tool %s", tool_name)
        raise ToolExecutionError(
            f"Internal error executing tool {tool_name}",
            tool_name=tool_name,
        ) from exc
