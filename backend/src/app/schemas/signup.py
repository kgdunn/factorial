"""Pydantic schemas for signup request and invite endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class SignupSubmitRequest(BaseModel):
    """Public signup request payload.

    ``requested_role`` is mandatory. Either:
    - a role slug from ``GET /roles`` (e.g. ``"chemical_engineer"``), or
    - ``"other:<freetext>"`` when the applicant picked "Other" and typed
      a description the admin can decipher.

    Admins never trust this directly — they pick or create the final
    role at approval time.
    """

    email: EmailStr
    use_case: str = Field(min_length=10, max_length=400)
    requested_role: str = Field(min_length=1, max_length=255)
    accepted_disclaimers: bool

    @field_validator("accepted_disclaimers")
    @classmethod
    def _disclaimers_must_be_accepted(cls, v: bool) -> bool:
        if not v:
            raise ValueError("You must accept the disclaimers to submit a signup request")
        return v

    @field_validator("requested_role")
    @classmethod
    def _other_must_have_freetext(cls, v: str) -> str:
        stripped = v.strip()
        if stripped.lower().startswith("other:"):
            freetext = stripped.split(":", 1)[1].strip()
            if not freetext:
                raise ValueError("Please describe your role when you pick 'Other'")
        elif stripped.lower() == "other":
            raise ValueError("Please describe your role when you pick 'Other'")
        return stripped


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
    accepted_disclaimers: bool
    disclaimers_accepted_at: datetime | None = None
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

    A role is mandatory — the admin must either:
    - Assign an existing role via ``role_id``, OR
    - Create a new role on the spot via ``new_role``.

    Passing neither (or both) is a 400.
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
