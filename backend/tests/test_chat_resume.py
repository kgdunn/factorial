"""Tests for the SSE chat-stream resume endpoint.

The endpoint's DB access is small and stable (one ``db.get`` plus a
few ``db.execute`` selects), so these tests install a hand-rolled
async-session fake keyed by the SQL statement shape rather than
spinning up SQLite. That keeps the tests fast and avoids the
postgres-UUID → SQLite impedance mismatch.
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import TESTING_USER_ID
from app.main import app
from app.models.conversation import ChatEvent, Conversation

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeResult:
    """Mimics the slice of the SQLAlchemy ``Result`` API we consume."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _FakeResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Minimal async session that serves Conversation + ChatEvent rows."""

    def __init__(
        self,
        *,
        conversation: Conversation | None,
        events: list[ChatEvent],
    ) -> None:
        self._conversation = conversation
        self._events = events

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def get(self, entity: Any, ident: Any) -> Any:
        if entity is Conversation and self._conversation and self._conversation.id == ident:
            return self._conversation
        return None

    async def execute(self, stmt: Any) -> _FakeResult:
        """Route the three statements the endpoint issues.

        Disambiguated by inspecting ``column_descriptions``:

        - ``select(ChatEvent.turn_id)`` — single column named "turn_id",
          used to resolve the most recent turn for a conversation.
        - ``select(ChatEvent.event_type)`` — single column named
          "event_type", used to probe whether the turn has ended.
        - ``select(ChatEvent)`` — entity select, used by the replay loop.
        """
        desc = getattr(stmt, "column_descriptions", None) or []
        names = [d.get("name") for d in desc]

        if names == ["turn_id"]:
            if not self._events:
                return _FakeResult([])
            latest = max(self._events, key=lambda e: e.sequence)
            return _FakeResult([latest.turn_id])

        if names == ["event_type"]:
            if not self._events:
                return _FakeResult([])
            latest = max(self._events, key=lambda e: e.sequence)
            return _FakeResult([latest.event_type])

        # Entity select — rows of ChatEvent. Filter by WHERE params.
        params = stmt.compile().params
        after_seq = params.get("sequence_1", 0)
        turn_id = params.get("turn_id_1")
        conv_id = params.get("conversation_id_1")
        rows = [
            e
            for e in self._events
            if e.sequence > after_seq
            and (turn_id is None or e.turn_id == turn_id)
            and (conv_id is None or e.conversation_id == conv_id)
        ]
        rows.sort(key=lambda e: e.sequence)
        return _FakeResult(rows)


def _conversation(user_id: uuid.UUID) -> Conversation:
    c = Conversation()
    c.id = uuid.uuid4()
    c.user_id = user_id
    c.title = "t"
    return c


def _event(
    conversation_id: uuid.UUID,
    turn_id: uuid.UUID,
    sequence: int,
    event_type: str,
    data: dict[str, Any],
) -> ChatEvent:
    e = ChatEvent()
    e.id = uuid.uuid4()
    e.conversation_id = conversation_id
    e.turn_id = turn_id
    e.sequence = sequence
    e.event_type = event_type
    e.data = data
    return e


def _parse_sse(body: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in body.splitlines():
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:") :].strip()
        elif line.startswith("id:"):
            current["id"] = line[len("id:") :].strip()
        elif line == "" and current:
            out.append(current)
            current = {}
    if current:
        out.append(current)
    return out


def _install_fake_factory(conversation: Conversation, events: list[ChatEvent]):
    """Return a patch context manager that substitutes the endpoint's session factory."""

    def factory() -> _FakeSession:
        return _FakeSession(conversation=conversation, events=events)

    return patch("app.api.v1.endpoints.chat.async_session_factory", factory)


# ---------------------------------------------------------------------------
# Unit tests for _parse_last_event_id
# ---------------------------------------------------------------------------


class TestParseLastEventId:
    def test_valid_header_parses(self) -> None:
        from app.api.v1.endpoints.chat import _parse_last_event_id

        turn_id = uuid.uuid4()
        result = _parse_last_event_id(f"{turn_id}:42")
        assert result == (turn_id, 42)

    def test_missing_returns_none(self) -> None:
        from app.api.v1.endpoints.chat import _parse_last_event_id

        assert _parse_last_event_id(None) is None
        assert _parse_last_event_id("") is None

    def test_malformed_returns_none(self) -> None:
        from app.api.v1.endpoints.chat import _parse_last_event_id

        assert _parse_last_event_id("not-a-uuid") is None
        assert _parse_last_event_id("not-a-uuid:3") is None
        assert _parse_last_event_id(f"{uuid.uuid4()}:not-a-number") is None


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


class TestResumeEndpoint:
    @pytest.mark.asyncio
    async def test_replay_from_last_event_id_skips_already_seen_events(self) -> None:
        conv = _conversation(TESTING_USER_ID)
        turn_id = uuid.uuid4()
        events = [
            _event(conv.id, turn_id, 1, "conversation_id", {"conversation_id": "x"}),
            _event(conv.id, turn_id, 2, "token", {"text": "Hel"}),
            _event(conv.id, turn_id, 3, "token", {"text": "lo"}),
            _event(conv.id, turn_id, 4, "done", {}),
        ]

        with _install_fake_factory(conv, events):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get(
                    f"/api/v1/chat/{conv.id}/resume",
                    headers={"Last-Event-ID": f"{turn_id}:2"},
                )

        assert response.status_code == 200
        parsed = _parse_sse(response.text)
        types = [e.get("event") for e in parsed]
        assert "token" in types
        assert "done" in types
        # The "Hel" token (seq=2) must NOT be replayed.
        assert all(json.loads(e["data"]).get("text") != "Hel" for e in parsed if e.get("event") == "token")
        # Event IDs must carry the turn id so the client can pick up again.
        token_event = next(e for e in parsed if e.get("event") == "token")
        assert token_event["id"] == f"{turn_id}:3"

    @pytest.mark.asyncio
    async def test_interrupted_turn_emits_synthetic_marker(self) -> None:
        conv = _conversation(TESTING_USER_ID)
        turn_id = uuid.uuid4()
        events = [
            _event(conv.id, turn_id, 1, "conversation_id", {"conversation_id": "x"}),
            _event(conv.id, turn_id, 2, "token", {"text": "partial"}),
        ]

        with _install_fake_factory(conv, events):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get(f"/api/v1/chat/{conv.id}/resume")

        assert response.status_code == 200
        parsed = _parse_sse(response.text)
        types = [e.get("event") for e in parsed]
        assert "interrupted" in types
        assert "done" not in types

    @pytest.mark.asyncio
    async def test_unknown_conversation_returns_404(self) -> None:
        # No conversation seeded → ``db.get`` returns ``None``.
        with _install_fake_factory(None, []):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get(f"/api/v1/chat/{uuid.uuid4()}/resume")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_foreign_conversation_returns_404(self) -> None:
        # Conversation exists but belongs to a different user.
        conv = _conversation(uuid.uuid4())  # not TESTING_USER_ID
        with _install_fake_factory(conv, []):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get(f"/api/v1/chat/{conv.id}/resume")

        assert response.status_code == 404
