"""Audit trail for BYO Anthropic API token credentials.

Append-only log of enrollment / rotation / removal / verification events.
**Stores no key material.** Rows are kept after the user is deleted
(``ON DELETE SET NULL``) so the trail outlives the account.

Rotation is modelled as delete-then-create: rather than UPDATE the
previous row, we close it (set ``ended_at``) and append a fresh row.
Auditors can then read clear ``[started_at, ended_at)`` intervals for
each credential a user had active over time.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BYOKCredentialsHistory(Base):
    """One row per lifecycle event for a user's BYOK token.

    ``action`` is one of:
      enrolled  - user pasted a fresh token
      rotated   - token was replaced (delete-then-create)
      removed   - user disabled BYOK
      verified  - manual or automated /byok/test ping returned 200
      rejected  - Anthropic returned 401 on a chat or test call
      orphaned  - DEK became unrecoverable (e.g. password reset)

    ``status_after`` mirrors ``users.byok_token_status`` after this event
    so an admin can reconstruct the timeline without joining against a
    point-in-time view of the users table.
    """

    __tablename__ = "byok_credentials_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(32))
    status_after: Mapped[str] = mapped_column(String(20))
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
