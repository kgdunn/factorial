"""SQLAlchemy model for per-identity daily tool-call accounting."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Date, DateTime, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ToolUsage(Base):
    """One row per (user, day): running total of tool-call CPU spend.

    The MCP router / tool bridge updates this row atomically after each
    tool call completes. A per-identity daily budget
    (``settings.mcp_daily_cpu_seconds``) is enforced against
    ``cpu_seconds_used`` before dispatching a new call.

    ``user_id`` is not a foreign key: the synthetic ``SERVICE_USER_ID``
    used by the shared ``X-API-Key`` is accepted as a valid identity
    here, so the shared API key has its own bucket. If / when a proper
    ``api_keys`` table exists, switch this to a real FK.
    """

    __tablename__ = "tool_usage"
    __table_args__ = (UniqueConstraint("user_id", "day", name="uq_tool_usage_user_day"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    day: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    cpu_seconds_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
