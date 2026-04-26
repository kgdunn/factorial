"""SQLAlchemy model for browser sessions.

A session is the canonical browser-side credential, replacing the JWT
access/refresh pair. The cookie carries the opaque ``id`` (32 random bytes,
base64url-encoded on the wire) which is looked up directly against this
table on every authenticated request.

- ``family_id`` groups sessions for "sign out everywhere": revoking a
  family revokes every session opened by that user. We use it instead of
  ``user_id`` on the revoke path so a future sharded users table doesn't
  force us to refactor.
- ``last_used_at`` is updated at most once per minute per session
  (write-throttled in ``session_service``) to avoid amplifying writes on
  hot paths.
- ``revoked_at IS NOT NULL`` is the kill bit; expired sessions stay in
  the table until a periodic sweeper deletes them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[bytes] = mapped_column(LargeBinary(32), primary_key=True)
    # Non-secret identifier exposed on /auth/sessions and accepted by
    # DELETE /auth/sessions/{public_id}. Never use ``id`` for that — it
    # is the credential.
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ip: Mapped[str | None] = mapped_column(INET(), nullable=True)
