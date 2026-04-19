"""Verify agent_service routes Anthropic network errors through the status tracker.

Exercises the synchronous inner loop directly with a stub client so we
don't need Postgres, Neo4j, or the HTTP layer.
"""

from __future__ import annotations

import queue
import uuid

import anthropic
import httpx
import pytest

from app.services import agent_service
from app.services.anthropic_status import status_tracker


class _RaisingStream:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __enter__(self):
        raise self._exc

    def __exit__(self, *_):
        return False


class _RaisingMessages:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def stream(self, **_kwargs):
        return _RaisingStream(self._exc)


class _StubClient:
    def __init__(self, exc: Exception) -> None:
        self.messages = _RaisingMessages(exc)


@pytest.fixture(autouse=True)
def _reset_tracker():
    status_tracker.reset()
    yield
    status_tracker.reset()


def _drain(q: queue.Queue) -> list[tuple]:
    out: list[tuple] = []
    while True:
        item = q.get_nowait()
        if item is None or (isinstance(item, tuple) and item == agent_service._SENTINEL):
            break
        out.append(item)
    return out


def test_api_connection_error_is_recorded_and_emits_anthropic_unavailable():
    q: queue.Queue = queue.Queue()
    client = _StubClient(anthropic.APIConnectionError(request=httpx.Request("POST", "http://x")))

    agent_service._run_agent_loop(
        event_queue=q,
        messages=[{"role": "user", "content": "hi"}],
        tool_specs=[],
        client=client,  # type: ignore[arg-type]
        model="claude-sonnet-4-6",
        turn_id=uuid.uuid4(),
    )

    events = _drain(q)
    errors = [data for name, data in events if name == "error"]
    assert any(e.get("kind") == "anthropic_unavailable" for e in errors), errors

    snap = status_tracker.snapshot()
    assert snap["error_count"] == 1
    assert snap["last_error"] == "APIConnectionError"


def test_auth_error_is_not_routed_through_tracker():
    """AuthenticationError is a config problem — it shouldn't show the banner."""
    q: queue.Queue = queue.Queue()
    client = _StubClient(
        anthropic.AuthenticationError(
            message="bad key",
            response=httpx.Response(401, request=httpx.Request("POST", "http://x")),
            body=None,
        )
    )

    agent_service._run_agent_loop(
        event_queue=q,
        messages=[{"role": "user", "content": "hi"}],
        tool_specs=[],
        client=client,  # type: ignore[arg-type]
        model="claude-sonnet-4-6",
        turn_id=uuid.uuid4(),
    )

    snap = status_tracker.snapshot()
    assert snap["status"] == "ok"
    assert snap["last_error"] is None
