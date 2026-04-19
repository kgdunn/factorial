"""Per-identity, per-day CPU-budget accounting for tool calls.

Uses the ``tool_usage`` table (one row per ``(user_id, day)``) to enforce
``settings.mcp_daily_cpu_seconds``. The MCP router and (optionally)
the REST tool bridge call :func:`check_budget` before dispatch and
:func:`record_call` afterwards.

A Postgres ``INSERT ... ON CONFLICT DO UPDATE`` keeps the write atomic
so two concurrent tool calls can't both squeeze under the limit.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tool_usage import ToolUsage
from app.services.exceptions import ToolBudgetExceededError


def _today() -> dt.date:
    return dt.datetime.now(tz=dt.UTC).date()


async def get_cpu_seconds_used(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Return today's CPU-seconds spent by *user_id* (0 if no row yet)."""
    stmt = select(ToolUsage.cpu_seconds_used).where(
        ToolUsage.user_id == user_id,
        ToolUsage.day == _today(),
    )
    result = await db.execute(stmt)
    value = result.scalar_one_or_none()
    return int(value) if value is not None else 0


async def check_budget(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    budget_seconds: int | None = None,
) -> None:
    """Raise :class:`ToolBudgetExceededError` if *user_id* has no budget left today.

    Parameters
    ----------
    db:
        Active async session.
    user_id:
        Identity to check. The synthetic ``SERVICE_USER_ID`` shares one
        bucket across all callers of the shared ``X-API-Key``.
    budget_seconds:
        Override ``settings.mcp_daily_cpu_seconds``.
    """
    limit = budget_seconds if budget_seconds is not None else settings.mcp_daily_cpu_seconds
    if limit <= 0:
        return  # A non-positive budget disables enforcement.

    used = await get_cpu_seconds_used(db, user_id)
    if used >= limit:
        raise ToolBudgetExceededError(
            f"Daily CPU budget of {limit}s exhausted ({used}s used). Resets at midnight UTC.",
        )


async def record_call(
    db: AsyncSession,
    user_id: uuid.UUID,
    duration_seconds: float,
) -> None:
    """Atomically upsert today's usage row for *user_id*.

    ``duration_seconds`` is rounded up to the next integer so very short
    calls still count against the budget (prevents amplification by
    high-volume sub-second calls).
    """
    increment = max(1, int(duration_seconds + 0.999))
    stmt = (
        pg_insert(ToolUsage)
        .values(
            user_id=user_id,
            day=_today(),
            cpu_seconds_used=increment,
            call_count=1,
        )
        .on_conflict_do_update(
            constraint="uq_tool_usage_user_day",
            set_={
                "cpu_seconds_used": ToolUsage.cpu_seconds_used + increment,
                "call_count": ToolUsage.call_count + 1,
                "updated_at": dt.datetime.now(tz=dt.UTC),
            },
        )
    )
    await db.execute(stmt)
    await db.commit()
