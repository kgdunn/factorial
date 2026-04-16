"""Pydantic schemas for shareable experiment links and the public view."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ShareLinkCreate(BaseModel):
    """POST /experiments/{id}/shares request body.

    ``expires_at`` is an explicit absolute datetime.  When omitted, the
    server applies ``share_token_expire_days``; set ``never_expire=True``
    to mint a link with no expiry.
    """

    expires_at: datetime | None = None
    never_expire: bool = False
    allow_results: bool = True


class ShareLinkResponse(BaseModel):
    """A minted (or listed) share link."""

    id: uuid.UUID
    token: str
    url: str
    allow_results: bool
    expires_at: datetime | None
    revoked_at: datetime | None
    view_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ShareLinkListResponse(BaseModel):
    shares: list[ShareLinkResponse]


class PublicExperimentView(BaseModel):
    """Snapshot of an experiment exposed to unauthenticated viewers.

    Deliberately omits ``user_id`` and ``conversation_id`` so no owner
    PII leaks through the public endpoint.  ``results_data`` is None
    when the share was minted with ``allow_results=False``.
    """

    id: uuid.UUID
    name: str
    design_type: str | None = None
    n_runs: int | None = None
    n_factors: int | None = None
    factors: list[dict[str, Any]] | None = None
    design_data: dict[str, Any] | None = None
    results_data: list[dict[str, Any]] | None = None
    owner_display_name: str | None = None
    view_count: int = 0
    expires_at: datetime | None = None
    created_at: datetime
    allow_results: bool = True
    token: str = Field(..., description="Echoed back for client-side deep links")
