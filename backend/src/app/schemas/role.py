"""Pydantic schemas for role endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_builtin: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RoleListResponse(BaseModel):
    roles: list[RoleResponse]


class RoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(None, max_length=500)


class RoleUpdateRequest(BaseModel):
    description: str | None = Field(None, max_length=500)
