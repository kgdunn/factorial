"""Tool bridge: thin adapter from process_improve.tool_spec to the app's tool API.

Wraps the real ``process_improve`` functions so that:

- ``ValueError`` / ``TypeError`` from unknown or mis-called tools are
  converted to :class:`~app.services.exceptions.ToolExecutionError`.
- The public API (``get_tool_specs``, ``execute_tool_call``) stays
  identical to the old stub module so **no other file needs import changes**.
"""

from __future__ import annotations

from typing import Any

from process_improve.tool_spec import execute_tool_call as _pi_execute
from process_improve.tool_spec import get_tool_specs as _pi_get_specs

from app.services.exceptions import ToolExecutionError


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
        If the tool name is unknown or the call raises ``ValueError`` / ``TypeError``.
    """
    try:
        return _pi_execute(tool_name, tool_input)
    except (ValueError, TypeError) as exc:
        raise ToolExecutionError(str(exc), tool_name=tool_name) from exc
