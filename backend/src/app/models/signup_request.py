"""SQLAlchemy model for signup requests (admin-approved registration)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

    # What the applicant asked for (free text: either a role slug they picked
    # from the dropdown, or ``other:<description>`` when they picked "Other").
    requested_role: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # The role the admin decided on at approval time. Copied to the user on
    # registration.
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Invite flow (populated on approval)
    invite_token: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    invite_expires_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Admin review
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Disclaimer acceptance captured on the public signup form.
    accepted_disclaimers: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False,
    )
    disclaimers_accepted_at: Mapped[str | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    role = relationship("Role", lazy="joined", foreign_keys=[role_id])

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
