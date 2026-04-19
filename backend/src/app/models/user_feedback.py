"""SQLAlchemy model for the ``user_feedback`` table.

One row per submission from the in-app "Give feedback" button. Captures
the submitter, a topic label, free-text message, contextual metadata,
an optional inline PNG screenshot, and a reply audit trail populated
when an admin answers via the dashboard.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    topic: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    viewport: Mapped[str | None] = mapped_column(String(32), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    screenshot_png: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    screenshot_mime: Mapped[str | None] = mapped_column(String(32), nullable=True)

    replied_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reply_body: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
