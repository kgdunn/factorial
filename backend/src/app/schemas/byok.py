"""Pydantic schemas for BYOK (Bring-Your-Own-Key) endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Min/max lengths: an Anthropic key is well under 1024 bytes; the lower
# bound rejects empty / pathologically short values without trying to
# encode the exact prefix here, so a future format change doesn't break
# the schema. The actual format check is delegated to Anthropic via the
# verification ping.
_KEY_MIN = 16
_KEY_MAX = 1024


class BYOKEnrollRequest(BaseModel):
    """Body for ``POST /api/v1/byok/enroll`` and ``POST /api/v1/byok/rotate``.

    Re-verifying the password is required because the active session
    does not have it in scope — the user re-enters it in the form. The
    Anthropic key is stored encrypted under a KEK derived from the
    same password, so we cannot proceed without it.
    """

    password: str = Field(min_length=1, max_length=1024)
    anthropic_api_key: str = Field(min_length=_KEY_MIN, max_length=_KEY_MAX)


BYOKStatusValue = Literal["absent", "active", "rejected", "orphaned"]


class BYOKStatusResponse(BaseModel):
    """Body for ``GET /api/v1/byok``.

    Public state surfaced to the profile UI. **Does not** carry any
    ciphertext or key material — only metadata the user can already
    read in the rendered page.
    """

    status: BYOKStatusValue
    last_verified_at: datetime | None = None


class BYOKTestResponse(BaseModel):
    """Body for ``POST /api/v1/byok/test``.

    ``outcome``:
    - ``ok``       — Anthropic accepted the key; status flipped to
      ``active`` and ``last_verified_at`` updated.
    - ``rejected`` — 401 / 403 from Anthropic; status flipped to
      ``rejected`` so the UI can prompt re-entry.
    - ``transient`` — Anthropic returned 5xx / network error / rate
      limit; status NOT changed. Caller should retry later.
    - ``no_key``   — user has no enrollment to test.
    """

    outcome: Literal["ok", "rejected", "transient", "no_key"]
    status: BYOKStatusValue
    last_verified_at: datetime | None = None
