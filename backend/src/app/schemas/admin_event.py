"""Admin events dashboard schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AdminEventDetail(BaseModel):
    id: uuid.UUID
    event_type: str
    status: str
    source: str
    actor: str | None
    message: str | None
    error_message: str | None
    payload: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AdminEventListResponse(BaseModel):
    events: list[AdminEventDetail]
    total: int
    page: int
    page_size: int
