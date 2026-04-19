"""Pydantic schemas for the in-app user feedback flow."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FeedbackTopic = Literal["incorrect_response", "improvement", "bug", "other"]

MAX_MESSAGE_LEN = 5_000
MAX_SCREENSHOT_BYTES = 2 * 1024 * 1024  # 2 MB decoded


class FeedbackSubmitRequest(BaseModel):
    """Payload for ``POST /api/v1/feedback``."""

    topic: FeedbackTopic
    message: str = Field(..., min_length=10, max_length=MAX_MESSAGE_LEN)
    page_url: str | None = Field(None, max_length=2_000)
    user_agent: str | None = Field(None, max_length=1_000)
    viewport: str | None = Field(None, max_length=32)
    screenshot_png_b64: str | None = Field(
        None,
        description=("Optional base64-encoded PNG screenshot of the current tab. Decoded size must not exceed 2 MB."),
    )


class FeedbackSubmitResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime


class FeedbackRow(BaseModel):
    """Row shape returned to admins. Omits the raw screenshot bytes."""

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    user_display_name: str | None
    topic: FeedbackTopic
    message: str
    page_url: str | None
    user_agent: str | None
    viewport: str | None
    app_version: str | None
    has_screenshot: bool
    replied_at: datetime | None
    replied_by_user_id: uuid.UUID | None
    replied_by_email: str | None
    reply_body: str | None
    created_at: datetime


class FeedbackListResponse(BaseModel):
    items: list[FeedbackRow]
    total: int
    page: int
    page_size: int


class FeedbackReplyRequest(BaseModel):
    body: str = Field(..., min_length=10, max_length=MAX_MESSAGE_LEN)


class FeedbackMarkRepliedRequest(BaseModel):
    """Admin-only: mark replied without sending an email (e.g. handled out of band)."""

    replied: bool
