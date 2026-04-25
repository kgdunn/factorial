"""Per-chat-turn timing instrumentation.

Writes one JSON object per line to ``settings.timing_log_path`` so the chat
hot path can be diagnosed with ``tail -f`` and ``jq``. The helper is
deliberately small: a context-manager phase recorder plus a one-shot
``event`` method. No external dependency — stdlib ``logging`` with a
``RotatingFileHandler`` is enough.

If the configured path is not writable (read-only filesystem, missing
directory the runtime cannot create, etc.) the module installs a
``NullHandler`` so importing ``app.services.turn_timing`` is always safe.
Telemetry must never break the chat path.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.config import settings

_TIMING_LOGGER_NAME = "app.timing"
_logger = logging.getLogger(__name__)


def _build_timing_logger() -> logging.Logger:
    """Configure the module-level ``app.timing`` logger exactly once."""
    timing_logger = logging.getLogger(_TIMING_LOGGER_NAME)
    timing_logger.propagate = False
    if timing_logger.handlers:
        return timing_logger

    path_value = (settings.timing_log_path or "").strip()
    if not path_value:
        timing_logger.addHandler(logging.NullHandler())
        return timing_logger

    try:
        path = Path(path_value)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(
            path,
            maxBytes=settings.timing_log_max_bytes,
            backupCount=settings.timing_log_backup_count,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        timing_logger.addHandler(handler)
        timing_logger.setLevel(logging.INFO)
    except OSError as exc:
        _logger.warning("Timing log unavailable at %s (%s) — disabling.", path_value, exc)
        timing_logger.addHandler(logging.NullHandler())

    return timing_logger


_timing_logger = _build_timing_logger()


class TurnTimer:
    """Records phase spans and one-shot events for one chat turn.

    Instances are cheap; create one per ``run_chat`` invocation. Records
    share ``conversation_id`` and ``turn_id`` so a single ``jq`` filter
    can reconstruct the whole turn.
    """

    __slots__ = ("conversation_id", "turn_id", "_started")

    def __init__(self, conversation_id: uuid.UUID | str | None, turn_id: uuid.UUID | str) -> None:
        self.conversation_id = str(conversation_id) if conversation_id is not None else None
        self.turn_id = str(turn_id)
        self._started = time.perf_counter()

    @contextmanager
    def phase(self, name: str, **extra: Any) -> Iterator[dict[str, Any]]:
        """Time a block and emit a ``phase`` record on exit."""
        scratch: dict[str, Any] = {}
        start = time.perf_counter()
        status = "ok"
        try:
            yield scratch
        except BaseException:
            status = "error"
            raise
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._emit("phase", phase=name, duration_ms=duration_ms, status=status, **extra, **scratch)

    def event(self, kind: str, **fields: Any) -> None:
        """Emit a single record with arbitrary fields."""
        self._emit(kind, **fields)

    def elapsed_ms(self) -> int:
        """Wall-clock milliseconds since this timer was created."""
        return int((time.perf_counter() - self._started) * 1000)

    def _emit(self, kind: str, **fields: Any) -> None:
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "kind": kind,
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
        }
        record.update(fields)
        try:
            # ``json.dumps`` escapes embedded newlines in string values
            # (``\n`` → ``\\n``) so the encoded record is already a single
            # line. The explicit translate call drops any stray CR/LF that
            # might creep in via ``default=str`` on exotic objects, and
            # makes the no-newline guarantee visible to log-injection
            # static analysers.
            serialized = json.dumps(record, default=str).translate({0x0A: None, 0x0D: None})
            _timing_logger.info(serialized)
        except Exception:  # noqa: BLE001 — telemetry must not break the chat path
            _logger.exception("Failed to write timing record kind=%s", kind)
