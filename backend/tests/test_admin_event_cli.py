"""Unit tests for the ``admin-event`` CLI surface.

These cover the small pure helpers and the async command wrappers
(``_cmd_admin_event_*``); the DB-touching ones use the session-scoped
Postgres ``db_session`` fixture from ``conftest.py``. The argparse
wiring itself is exercised through a parser round-trip.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cli
from app.models.admin_event import AdminEvent  # noqa: F401 — register table

# ---------------------------------------------------------------------------
# _parse_payload_json
# ---------------------------------------------------------------------------


def test_parse_payload_json_none() -> None:
    assert cli._parse_payload_json(None) is None


def test_parse_payload_json_dict() -> None:
    assert cli._parse_payload_json('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parse_payload_json_invalid_json() -> None:
    with pytest.raises(SystemExit, match="not valid JSON"):
        cli._parse_payload_json("{not json")


def test_parse_payload_json_rejects_list() -> None:
    with pytest.raises(SystemExit, match="JSON object"):
        cli._parse_payload_json("[1, 2, 3]")


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------


def test_parser_admin_event_start_args() -> None:
    parser = cli._build_parser()
    args = parser.parse_args(
        [
            "admin-event",
            "start",
            "--type",
            "postgres_backup",
            "--source",
            "cron@vps01",
            "--payload-json",
            '{"k":"v"}',
        ]
    )
    assert args.command == "admin-event"
    assert args.admin_event_cmd == "start"
    assert args.event_type == "postgres_backup"
    assert args.source == "cron@vps01"
    assert args.payload_json == '{"k":"v"}'


def test_parser_admin_event_finish_requires_status_choice() -> None:
    parser = cli._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "admin-event",
                "finish",
                "--id",
                str(uuid.uuid4()),
                "--status",
                "done",  # not a valid choice
            ]
        )


# ---------------------------------------------------------------------------
# _cmd_admin_event_* — round-trip against in-memory SQLite
# ---------------------------------------------------------------------------


async def test_cmd_start_then_finish_roundtrip(db_session: AsyncSession) -> None:
    event_id = await cli._cmd_admin_event_start(
        db_session,
        event_type="postgres_backup",
        source="cron@vps01",
        actor=None,
        message=None,
        payload={"s3_key": "k1"},
    )
    assert isinstance(event_id, uuid.UUID)

    await cli._cmd_admin_event_finish(
        db_session,
        event_id=event_id,
        status="success",
        message="ok",
        error_message=None,
        payload_merge={"size_bytes": 99},
    )

    row = (await db_session.execute(select(AdminEvent).where(AdminEvent.id == event_id))).scalar_one()
    assert row.status == "success"
    assert row.message == "ok"
    assert row.payload == {"s3_key": "k1", "size_bytes": 99}
    assert row.completed_at is not None


async def test_cmd_log_snapshot_roundtrip(db_session: AsyncSession) -> None:
    event_id = await cli._cmd_admin_event_log(
        db_session,
        event_type="user_count_snapshot",
        source="app",
        payload={"n": 7},
        message=None,
    )
    row = (await db_session.execute(select(AdminEvent).where(AdminEvent.id == event_id))).scalar_one()
    assert row.status == "info"
    assert row.payload == {"n": 7}
