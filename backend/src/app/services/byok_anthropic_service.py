"""Anthropic-side BYOK helpers (one-shot verification + status mapping).

Owns the network calls that ``/api/v1/byok`` endpoints use to confirm a
user-supplied API key is still valid. Kept separate from
``byok_service`` (pure crypto, no I/O) and ``byok_session_service``
(DB-aware composition, no I/O) so the network surface — and therefore
the integration-test surface — is small and obvious.
"""

from __future__ import annotations

import logging
from enum import StrEnum

import anthropic

from app.config import settings

logger = logging.getLogger(__name__)


class VerificationOutcome(StrEnum):
    """Result of a one-shot Anthropic ping with a user-supplied key."""

    OK = "ok"
    REJECTED = "rejected"
    TRANSIENT = "transient"


def verify_with_anthropic(api_key: str) -> VerificationOutcome:
    """Issue a minimal ``messages.create`` call to validate ``api_key``.

    Behavior:

    - 200 / any successful response -> ``OK``
    - ``AuthenticationError`` (401) or ``PermissionDeniedError`` (403)
      -> ``REJECTED``. Caller should mark ``byok_token_status='rejected'``
      and surface a "your API key was rejected by Anthropic" message.
    - Any other ``APIError``, network failure, or rate-limit response
      -> ``TRANSIENT``. The key may still be valid; do not flip the
      stored status. Caller should surface "couldn't verify right now"
      and let the user retry.

    The request uses ``max_tokens=1`` and a one-token user message, so
    a single verification call costs the user at most a fraction of a
    cent on Anthropic's side. Token plaintext exists only inside this
    function — never logged or persisted.
    """
    try:
        client = anthropic.Anthropic(api_key=api_key)
        client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1,
            messages=[{"role": "user", "content": "."}],
        )
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        # Don't log the exception object — the SDK includes a redacted
        # form of the key in the request URL it embeds in the message.
        logger.info("BYOK verification rejected by Anthropic")
        return VerificationOutcome.REJECTED
    except anthropic.APIError:
        logger.warning("BYOK verification transient failure")
        return VerificationOutcome.TRANSIENT
    except Exception:
        # Catch-all for network errors, DNS failures, etc. We never want
        # a verification call to take down the enroll endpoint.
        logger.warning("BYOK verification unexpected failure")
        return VerificationOutcome.TRANSIENT
    return VerificationOutcome.OK
