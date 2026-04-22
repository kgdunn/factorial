"""Pydantic schemas for the chat endpoint."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

DetailLevel = Literal["beginner", "intermediate", "expert"]


class ChatRequest(BaseModel):
    """Request body for ``POST /api/v1/chat``."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=10_000,
        description="User message text.",
    )
    conversation_id: uuid.UUID | None = Field(
        None,
        description="Existing conversation ID to continue. Omit to start a new conversation.",
    )
    detail_level: DetailLevel = Field(
        "intermediate",
        description=(
            "Desired response verbosity. 'beginner' = plain-language, step-by-step; "
            "'intermediate' = balanced (default); 'expert' = terse, no preamble."
        ),
    )
