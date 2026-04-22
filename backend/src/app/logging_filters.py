"""Logging hooks used across the FastAPI app and the admin CLI."""

from __future__ import annotations

import logging
from typing import Any

_CRLF = {0x0A: None, 0x0D: None}


def _scrub(value: Any) -> Any:
    return value.translate(_CRLF) if isinstance(value, str) else value


def install_log_injection_guard() -> None:
    """Install a ``LogRecord`` factory that strips CR/LF from message + args.

    Defence-in-depth against log forgery (CWE-117): API input is already
    validated by Pydantic's ``EmailStr`` upstream, but this guarantees that
    no log line — from any logger, anywhere in the app — can contain
    embedded newlines even if a future caller forgets to validate.

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
