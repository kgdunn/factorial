"""Tool bridge: thin adapter from process_improve.tool_spec to the app's tool API.

Wraps the real ``process_improve`` functions so that:

- ``ValueError`` / ``TypeError`` from unknown or mis-called tools are
  converted to :class:`~app.services.exceptions.ToolExecutionError`.
- Tool names are validated against an allowlist before execution.
- All exceptions (not just ValueError/TypeError) are caught so that
  unexpected errors are returned as structured error responses.
- Structured ``process_improve.tool_safety`` errors (input too large,
  timeout, memory cap) are translated to the matching app-level
  exception subclass so FastAPI handlers can return the right status.

When ``settings.tool_safe_mode`` is true (the default), tool calls are
routed through :func:`process_improve.tool_safety.safe_execute_tool_call`,
which runs the call in a forked worker subprocess with a wall-clock
timeout and a per-subprocess memory cap. Tests and local notebooks can
set ``TOOL_SAFE_MODE=0`` to keep the fast in-process path.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from process_improve.tool_safety import (
    ToolInputInvalidError as _PISafetyInvalid,
)
from process_improve.tool_safety import (
    ToolInputTooLargeError as _PISafetyTooLarge,
)
from process_improve.tool_safety import (
    ToolMemoryExceededError as _PISafetyMemory,
)
from process_improve.tool_safety import (
    ToolSafetyError as _PISafetyError,
)
from process_improve.tool_safety import (
    ToolTimeoutError as _PISafetyTimeout,
)
from process_improve.tool_safety import (
    safe_execute_tool_call as _pi_safe_execute,
)
from process_improve.tool_spec import execute_tool_call as _pi_execute
from process_improve.tool_spec import get_tool_specs as _pi_get_specs

from app.config import settings
from app.services.exceptions import (
    ToolExecutionError,
    ToolInputTooLargeError,
    ToolMemoryExceededError,
    ToolTimeoutError,
)

logger = logging.getLogger(__name__)

# Build an allowlist of valid tool names at import time.
_ALLOWED_TOOL_NAMES: frozenset[str] = frozenset(spec["name"] for spec in _pi_get_specs() if "name" in spec)


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


def _translate_safety_error(exc: _PISafetyError, tool_name: str) -> ToolExecutionError:
    """Map a process_improve safety exception to the app-level subclass."""
    if isinstance(exc, (_PISafetyTooLarge, _PISafetyInvalid)):
        return ToolInputTooLargeError(str(exc), tool_name=tool_name)
    if isinstance(exc, _PISafetyTimeout):
        return ToolTimeoutError(str(exc), tool_name=tool_name)
    if isinstance(exc, _PISafetyMemory):
        return ToolMemoryExceededError(str(exc), tool_name=tool_name)
    return ToolExecutionError(str(exc), tool_name=tool_name)


def execute_tool_call(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    timeout: float | None = None,
    memory_mb: int | None = None,
    safe_mode: bool | None = None,
) -> Any:  # noqa: ANN401
    """Dispatch a tool call, mapping errors to ``ToolExecutionError``.

    Synchronous. Safe to call from a thread (e.g. ``asyncio.to_thread``)
    or from other sync code. Do **not** call directly from an async
    endpoint — use :func:`execute_tool_call_async` instead, otherwise
    the wait on the subprocess result will block the event loop.

    Parameters
    ----------
    tool_name:
        Registered tool name (e.g. ``"generate_design"``).
    tool_input:
        Keyword arguments for the tool.
    timeout:
        Optional wall-clock timeout in seconds. Defaults to
        ``settings.tool_timeout_seconds``. Ignored when ``safe_mode``
        is false.
    memory_mb:
        Optional per-subprocess memory cap (MB). Defaults to
        ``settings.tool_memory_mb``. Ignored when ``safe_mode`` is false.
    safe_mode:
        Override ``settings.tool_safe_mode``. When true, runs the call
        through ``safe_execute_tool_call`` (subprocess isolation).

    Raises
    ------
    ToolExecutionError
        Base class. Subclasses:
        :class:`ToolInputTooLargeError` (413),
        :class:`ToolTimeoutError` (408),
        :class:`ToolMemoryExceededError` (507).
    """
    if tool_name not in _ALLOWED_TOOL_NAMES:
        raise ToolExecutionError(
            f"Unknown tool: {tool_name!r}. Valid tools: {sorted(_ALLOWED_TOOL_NAMES)}",
            tool_name=tool_name,
        )

    if not isinstance(tool_input, dict):
        raise ToolExecutionError(
            f"Tool input must be a dict, got {type(tool_input).__name__}",
            tool_name=tool_name,
        )

    effective_safe_mode = settings.tool_safe_mode if safe_mode is None else safe_mode

    try:
        if effective_safe_mode:
            return _pi_safe_execute(
                tool_name,
                tool_input,
                timeout=timeout if timeout is not None else settings.tool_timeout_seconds,
                memory_mb=memory_mb if memory_mb is not None else settings.tool_memory_mb,
                max_cells=settings.tool_max_cells,
                max_string=settings.tool_max_string,
            )
        return _pi_execute(tool_name, tool_input)
    except _PISafetyError as exc:
        raise _translate_safety_error(exc, tool_name) from exc
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


async def execute_tool_call_async(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    timeout: float | None = None,
    memory_mb: int | None = None,
    safe_mode: bool | None = None,
) -> tuple[Any, float]:
    """Async variant of :func:`execute_tool_call`.

    Runs the synchronous call in a thread (``asyncio.to_thread``) so
    event-loop-hosted callers do not block on the subprocess result.

    Returns
    -------
    tuple[Any, float]
        ``(result, elapsed_seconds)`` — the tool's return value and the
        wall-clock time spent inside the call. The duration is useful
        for per-identity CPU-budget accounting.
    """
    t0 = time.perf_counter()
    result = await asyncio.to_thread(
        execute_tool_call,
        tool_name,
        tool_input,
        timeout=timeout,
        memory_mb=memory_mb,
        safe_mode=safe_mode,
    )
    return result, time.perf_counter() - t0
