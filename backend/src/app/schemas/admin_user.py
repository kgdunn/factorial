"""Admin user-management schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.signup import RoleSummary


class AdminUserDetail(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_admin: bool
    is_active: bool
    role: RoleSummary | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserListResponse(BaseModel):
    users: list[AdminUserDetail]
    total: int
    page: int
    page_size: int


class AdminUserUpdateRequest(BaseModel):
    """Partial update for a user. Null means 'leave unchanged'."""

    is_admin: bool | None = None
    is_active: bool | None = None
    role_id: uuid.UUID | None = None
    clear_role: bool = False
    display_name: str | None = Field(None, max_length=100)


class AdminUserResetPasswordResponse(BaseModel):
    """Returned to admins after issuing a reset link for a user.

    ``url`` is included so an admin can copy-paste the link out-of-band
    (e.g. when SMTP is intentionally unconfigured in development).
    """

    message: str
    url: str
