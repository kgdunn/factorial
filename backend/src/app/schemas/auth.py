"""Pydantic schemas for authentication endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

# Allowlist of valid user background values. Free-text is not permitted
# because the value is interpolated into the LLM system prompt.
BackgroundValue = Literal[
    "chemical_engineer",
    "pharmaceutical_scientist",
    "food_scientist",
    "academic_researcher",
    "quality_engineer",
    "data_scientist",
    "student",
    "other",
]


class RegisterRequest(BaseModel):
    """User registration payload."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(None, max_length=100)
    background: BackgroundValue | None = None


class LoginRequest(BaseModel):
    """User login payload."""

    email: EmailStr
    password: str


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
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
