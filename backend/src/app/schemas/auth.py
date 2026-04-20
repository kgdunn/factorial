"""Pydantic schemas for authentication endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Direct registration payload.

    Kept for the (now 403-ed) ``POST /auth/register`` endpoint so clients
    calling it get a proper 403 instead of a 422. The fields mirror the
    invite registration payload.
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(None, max_length=100)


class LoginRequest(BaseModel):
    """User login payload."""

    email: EmailStr
    password: str
    timezone: str | None = Field(None, max_length=64)


class TokenResponse(BaseModel):
    """JWT token pair returned on login/register."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token exchange payload."""

    refresh_token: str


class UserResponse(BaseModel):
    """Public user profile."""

    id: uuid.UUID
    email: str
    display_name: str | None
    background: str | None
    is_admin: bool = False
    created_at: datetime | None = None
    balance_usd: Decimal | None = None
    balance_tokens: int | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Password reset / setup
# ---------------------------------------------------------------------------


class PasswordResetRequestPayload(BaseModel):
    """Public password-reset initiation payload."""

    email: EmailStr


class PasswordResetValidateResponse(BaseModel):
    """Response when validating a setup/reset token."""

    email: str
    valid: bool
    purpose: str | None = None


class PasswordResetCompletePayload(BaseModel):
    """Complete a setup or reset by setting a new password."""

    token: str
    password: str = Field(min_length=8, max_length=128)


class PasswordChangePayload(BaseModel):
    """Authenticated password change."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)
