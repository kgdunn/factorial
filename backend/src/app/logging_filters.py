"""Logging hooks used across the FastAPI app and the admin CLI."""

from __future__ import annotations

import logging
import re
from typing import Any

_CRLF = {0x0A: None, 0x0D: None}

# Strings of this shape go through the redaction below before they
# reach a handler. The patterns match Anthropic-style keys
# (``sk-ant-*``), ``Bearer`` tokens, and generic
# ``api_key=`` / ``authorization:`` / ``password=`` shapes some
# misconfigured client might log verbatim. Loose matching is fine —
# the redaction replaces only what matches; false positives turn into
# ``[redacted]`` but no real signal is lost.
_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.]{16,}", re.IGNORECASE),
    re.compile(
        r"(?i)\b(?:api[_-]?key|x[-_]api[-_]key|authorization|password)"
        r"\s*[=:]\s*[\"']?[A-Za-z0-9_\-\.]{8,}[\"']?",
    ),
)
_REDACTED = "[redacted]"


def _scrub(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    cleaned = value.translate(_CRLF)
    for pat in _SENSITIVE_PATTERNS:
        cleaned = pat.sub(_REDACTED, cleaned)
    return cleaned


def install_log_injection_guard() -> None:
    """Install a ``LogRecord`` factory that scrubs message + args.

    Two layers of defence:

    1. **CR/LF stripping** (CWE-117 log forgery). API input is already
       validated by Pydantic upstream, but this guarantees no log line
       — from any logger, anywhere in the app — can carry embedded
       newlines even if a future caller forgets to validate.
    2. **Secret redaction**. Anthropic keys, generic ``Bearer`` /
       ``API-Key`` / ``Authorization`` / ``password`` patterns are
       replaced with ``[redacted]`` *before* the record reaches any
       handler. The primary BYOK guarantee is that the token never
       hits a logger argument in the first place — this is the
       defence-in-depth backstop catching the case where a future
       contributor logs a header dict verbatim.

    Idempotent: repeated calls are a no-op.
    """
    current = logging.getLogRecordFactory()
    if getattr(current, "_log_injection_guard", False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = current(*args, **kwargs)
        record.msg = _scrub(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_scrub(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _scrub(v) for k, v in record.args.items()}
        return record

    factory._log_injection_guard = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)
