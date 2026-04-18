"""Pydantic schemas for signup request and invite endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupSubmitRequest(BaseModel):
    """Public signup request payload."""

    email: EmailStr
    use_case: str = Field(min_length=10, max_length=400)
    # The applicant's self-declared role. A slug from ``GET /roles``, or
    # ``other:<freetext>`` when they picked "Other". The admin decides the
    # final role at approval time; this is never trusted directly.
    requested_role: str | None = Field(None, max_length=255)


class SignupSubmitResponse(BaseModel):
    """Response after submitting a signup request."""

    message: str


class RoleSummary(BaseModel):
    """Minimal role representation for embedding in other responses."""

    id: uuid.UUID
    name: str
    description: str | None = None

    model_config = {"from_attributes": True}


class SignupDetail(BaseModel):
    """Admin view of a signup request."""

    id: uuid.UUID
    email: str
    use_case: str
    status: str
    admin_note: str | None
    requested_role: str | None
    role: RoleSummary | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SignupListResponse(BaseModel):
    """Paginated list of signup requests for the admin dashboard."""

    signups: list[SignupDetail]
    total: int
    page: int
    page_size: int


class NewRoleInput(BaseModel):
    """Payload for 'create a new role as part of approval'."""

    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(None, max_length=500)


class SignupApproveRequest(BaseModel):
    """Admin approval payload.

    Admin either:
    - Assigns an existing role via ``role_id``, OR
    - Creates a new role on the spot via ``new_role``, OR
    - Leaves both null to approve without a role.
    """

    role_id: uuid.UUID | None = None
    new_role: NewRoleInput | None = None


class SignupRejectRequest(BaseModel):
    """Optional note when rejecting a signup."""

    note: str | None = Field(None, max_length=500)


class InviteValidateResponse(BaseModel):
    """Response when validating an invite token."""

    email: str
    valid: bool


class InviteRegisterRequest(BaseModel):
    """Registration payload using an invite token."""

    token: str
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(None, max_length=100)
