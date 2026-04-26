"""Tests for the hourly ``admin_events`` snapshot writer.

We exercise ``_write_hourly_snapshot`` directly rather than spinning up
the full ``_llm_performance_snapshot_loop`` — that way we don't need to
fight an ``asyncio.sleep(3600)``. The loop itself is a trivial wrapper
around ``_write_hourly_snapshot`` + a sleep + error suppression.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models.admin_event import AdminEvent  # noqa: F401 — register table
from app.services import anthropic_status
from app.services.anthropic_status import _write_hourly_snapshot, status_tracker


@pytest.fixture(autouse=True)
def _reset_tracker():
    status_tracker.reset()
    yield
    status_tracker.reset()


async def test_snapshot_writes_admin_event_when_samples_present(db_session_factory) -> None:
    for ms in [1000, 2000, 3000]:
        status_tracker.record_success(ms)
    status_tracker.record_error("APIConnectionError")

    with patch.object(anthropic_status, "async_session_factory", db_session_factory):
        await _write_hourly_snapshot(window_seconds=3600)

    async with db_session_factory() as session:
        rows = (await session.execute(select(AdminEvent))).scalars().all()

    assert len(rows) == 1
    row = rows[0]
    assert row.event_type == "llm_performance_hourly"
    assert row.source == "anthropic_status_monitor"
    assert row.status == "info"
    assert row.payload["sample_count"] == 4
    assert row.payload["success_count"] == 3
    assert row.payload["error_count"] == 1
    assert row.payload["error_types"] == {"APIConnectionError": 1}
    assert row.payload["latency_ms_max"] == 3000
    assert "p95=" in (row.message or "")


async def test_snapshot_skips_write_when_no_samples(db_session_factory) -> None:
    with patch.object(anthropic_status, "async_session_factory", db_session_factory):
        await _write_hourly_snapshot(window_seconds=3600)

    async with db_session_factory() as session:
        rows = (await session.execute(select(AdminEvent))).scalars().all()

    assert rows == []


async def test_snapshot_calls_log_snapshot_with_expected_shape(db_session_factory) -> None:
    status_tracker.record_success(5000)

    mock_log = AsyncMock(return_value=uuid.uuid4())
    with (
        patch.object(anthropic_status, "async_session_factory", db_session_factory),
        patch.object(anthropic_status.admin_event_service, "log_snapshot", mock_log),
    ):
        await _write_hourly_snapshot(window_seconds=3600)

    assert mock_log.await_count == 1
    kwargs = mock_log.await_args.kwargs
    assert kwargs["event_type"] == "llm_performance_hourly"
    assert kwargs["source"] == "anthropic_status_monitor"
    assert kwargs["payload"]["sample_count"] == 1
    assert kwargs["message"].startswith("LLM hourly:")
