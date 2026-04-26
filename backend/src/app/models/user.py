"""SQLAlchemy model for user accounts."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """A registered user account.

    ``is_admin`` is the sole admin marker. ``role_id`` points at the
    user's role / profile (see ``roles`` table) and is the canonical
    source for system-prompt personalisation.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_ip: Mapped[str | None] = mapped_column(
        String(45).with_variant(INET(), "postgresql"),
        nullable=True,
    )
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # BYOK (Bring-Your-Own Anthropic API key) columns. All ciphertext
    # blobs are AES-256-GCM ``nonce(12) || ct || tag(16)`` produced by
    # ``app.services.byok_service``. ``byok_token_status`` is one of
    # ``absent | active | rejected | orphaned`` (string + app-level
    # enforcement, matching ``conversations.status`` style).
    #
    #   absent     - user has not enrolled a token
    #   active     - last verification call to Anthropic succeeded
    #   rejected   - Anthropic returned 401 on the most recent attempt;
    #                UI prompts the user to re-enter
    #   orphaned   - DEK is unrecoverable (typically a password reset);
    #                ciphertext kept for diagnostic clarity, not usable
    byok_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    byok_dek_wrapped: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    byok_kek_salt: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    byok_kdf_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    byok_token_last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    byok_token_status: Mapped[str] = mapped_column(
        String(20),
        default="absent",
        server_default="absent",
    )

    role = relationship("Role", lazy="joined", foreign_keys=[role_id])

    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
