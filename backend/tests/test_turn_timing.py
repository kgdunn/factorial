"""Tests for the per-turn timing helper.

Avoids touching the global ``app.timing`` logger that imports at module
load (which is wired to whatever ``settings.timing_log_path`` was when
the module was first imported). Instead, builds a one-off
``RotatingFileHandler`` on a tmp path and attaches it to the same logger
for the duration of the test, mirroring how the helper itself works in
production.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from app.services.turn_timing import TurnTimer


@pytest.fixture
def timing_log(tmp_path: Path) -> Path:
    """Redirect ``app.timing`` records to a fresh file for this test."""
    log_path = tmp_path / "timing.jsonl"
    logger = logging.getLogger("app.timing")
    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    saved_handlers = logger.handlers[:]
    saved_level = logger.level
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    try:
        yield log_path
    finally:
        handler.close()
        logger.handlers = saved_handlers
        logger.setLevel(saved_level)


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_phase_records_duration(timing_log: Path) -> None:
    timer = TurnTimer(conversation_id=uuid.uuid4(), turn_id=uuid.uuid4())
    with timer.phase("load_history") as scratch:
        scratch["row_count"] = 7
        time.sleep(0.005)

    records = _read_records(timing_log)
    assert len(records) == 1
    record = records[0]
    assert record["kind"] == "phase"
    assert record["phase"] == "load_history"
    assert record["status"] == "ok"
    assert record["duration_ms"] >= 0
    assert record["row_count"] == 7
    assert record["turn_id"] == timer.turn_id


def test_event_emits_one_record(timing_log: Path) -> None:
    timer = TurnTimer(conversation_id=None, turn_id=uuid.uuid4())
    timer.event("turn_total", duration_ms=1234, status="ok", agent_turns=2)

    records = _read_records(timing_log)
    assert len(records) == 1
    record = records[0]
    assert record["kind"] == "turn_total"
    assert record["duration_ms"] == 1234
    assert record["agent_turns"] == 2
    assert record["conversation_id"] is None


def test_phase_records_error_status(timing_log: Path) -> None:
    timer = TurnTimer(conversation_id=uuid.uuid4(), turn_id=uuid.uuid4())
    # Nested form (rather than ``with pytest.raises(...), timer.phase(...):``)
    # so static analysers can see the body of ``timer.phase`` runs and the
    # records assertions afterwards are reachable.
    with pytest.raises(RuntimeError):  # noqa: SIM117
        with timer.phase("agent_loop"):
            raise RuntimeError("boom")

    records = _read_records(timing_log)
    assert len(records) == 1
    assert records[0]["status"] == "error"
    assert records[0]["phase"] == "agent_loop"


def test_unwritable_path_falls_back_silently(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A bad ``timing_log_path`` must never break the chat path."""
    import importlib

    from app import config
    from app.services import turn_timing as turn_timing_module

    bad_path = tmp_path / "nonexistent" / "subdir" / "timing.jsonl"
    monkeypatch.setattr(config.settings, "timing_log_path", str(bad_path))

    # Force the parent to exist as a *file* so mkdir(parents=True) fails cleanly.
    (tmp_path / "nonexistent").write_text("not a directory")

    # Wipe any handlers that previous tests installed, then re-import to
    # exercise ``_build_timing_logger`` against the bad path.
    logger = logging.getLogger("app.timing")
    logger.handlers = []

    importlib.reload(turn_timing_module)

    timer = turn_timing_module.TurnTimer(conversation_id=None, turn_id=uuid.uuid4())
    timer.event("turn_total", duration_ms=10)  # must not raise
