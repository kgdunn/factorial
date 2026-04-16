"""Pydantic schemas for signup request and invite endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.auth import BackgroundValue


class SignupSubmitRequest(BaseModel):
    """Public signup request payload."""

    email: EmailStr
    use_case: str = Field(min_length=10, max_length=400)


class SignupSubmitResponse(BaseModel):
    """Response after submitting a signup request."""

    message: str


class SignupDetail(BaseModel):
    """Admin view of a signup request."""

    id: uuid.UUID
    email: str
    use_case: str
    status: str
    admin_note: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SignupListResponse(BaseModel):
    """Paginated list of signup requests for the admin dashboard."""

    signups: list[SignupDetail]
    total: int
    page: int
    page_size: int


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
    background: BackgroundValue | None = None
