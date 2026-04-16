"""SQLAlchemy model for signup requests (admin-approved registration)."""

from __future__ import annotations

import uuid

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SignupRequest(Base):
    """A pending signup request that requires admin approval."""

    __tablename__ = "signup_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    use_case: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")

    # Invite flow (populated on approval)
    invite_token: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    invite_expires_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Admin review
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
