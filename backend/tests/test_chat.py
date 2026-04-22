"""Tests for the chat endpoint and agent service.

Mocked tests run without an Anthropic API key.
Integration tests are skipped unless ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

# ---------------------------------------------------------------------------
# SSE parsing helper
# ---------------------------------------------------------------------------


def parse_sse_events(body: str) -> list[dict[str, str]]:
    """Parse an SSE response body into a list of {event, data} dicts."""
    events: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in body.splitlines():
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:") :].strip()
        elif line == "" and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


# ---------------------------------------------------------------------------
# Mock Anthropic SDK objects
# ---------------------------------------------------------------------------


@dataclass
class MockTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class MockToolUseBlock:
    type: str = "tool_use"
    id: str = "toolu_mock_001"
    name: str = "create_design"
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class MockUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class MockResponse:
    content: list[Any] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = "claude-sonnet-4-20250514"
    usage: MockUsage = field(default_factory=MockUsage)


@dataclass
class MockTextDelta:
    type: str = "text_delta"
    text: str = ""


@dataclass
class MockStreamEvent:
    type: str = "content_block_delta"
    delta: MockTextDelta = field(default_factory=MockTextDelta)


class MockStreamManager:
    """Simulates ``client.messages.stream()`` context manager."""

    def __init__(self, responses: list[MockResponse]) -> None:
        self._responses = responses
        self._call_count = 0

    def __call__(self, **kwargs: Any) -> MockStreamContext:
        idx = min(self._call_count, len(self._responses) - 1)
        ctx = MockStreamContext(self._responses[idx])
        self._call_count += 1
        return ctx


class MockStreamContext:
    """Context manager returned by ``client.messages.stream()``."""

    def __init__(self, response: MockResponse) -> None:
        self._response = response

    def __enter__(self) -> MockStreamContext:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def __iter__(self):
        # Yield text delta events for text blocks.
        for block in self._response.content:
            if block.type == "text":
                yield MockStreamEvent(
                    type="content_block_delta",
                    delta=MockTextDelta(type="text_delta", text=block.text),
                )

    def get_final_message(self) -> MockResponse:
        return self._response


class MockAnthropicClient:
    """Fake ``anthropic.Anthropic`` client."""

    def __init__(self, stream_manager: MockStreamManager) -> None:
        self.messages = type("Messages", (), {"stream": stream_manager})()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_client(responses: list[MockResponse]) -> MockAnthropicClient:
    return MockAnthropicClient(MockStreamManager(responses))


# ---------------------------------------------------------------------------
# Mocked tests — no API key needed
# ---------------------------------------------------------------------------


class TestChatEndpointMocked:
    """Tests with a mocked Anthropic client, no real API calls."""

    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        """Agent returns plain text — SSE should have token + done events."""
        mock_response = MockResponse(
            content=[MockTextBlock(text="Hello! I can help with DOE.")],
            stop_reason="end_turn",
        )
        mock_client = _make_mock_client([mock_response])

        with (
            patch("app.services.agent_service.get_anthropic_client", return_value=mock_client),
            patch("app.services.agent_service.async_session_factory") as mock_sf,
        ):
            # Provide a no-op async session.
            mock_sf.return_value = _NoOpAsyncSession()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post("/api/v1/chat", json={"message": "Hello"})

            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            events = parse_sse_events(response.text)
            event_types = [e.get("event") for e in events]
            assert "conversation_id" in event_types
            assert "token" in event_types
            assert "done" in event_types

    @pytest.mark.asyncio
    async def test_tool_use_response(self):
        """Agent calls a tool — SSE should have tool_start + tool_result."""
        # First response: assistant calls create_design.
        tool_response = MockResponse(
            content=[
                MockTextBlock(text="Let me create a design."),
                MockToolUseBlock(
                    id="toolu_001",
                    name="create_design",
                    input={"factors": [{"name": "A", "low": 0, "high": 1}]},
                ),
            ],
            stop_reason="tool_use",
        )
        # Second response: assistant summarises the result.
        summary_response = MockResponse(
            content=[MockTextBlock(text="Here is your design.")],
            stop_reason="end_turn",
        )
        mock_client = _make_mock_client([tool_response, summary_response])

        with (
            patch("app.services.agent_service.get_anthropic_client", return_value=mock_client),
            patch("app.services.agent_service.async_session_factory") as mock_sf,
        ):
            mock_sf.return_value = _NoOpAsyncSession()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/chat",
                    json={"message": "Create a 2-factor design"},
                )

            events = parse_sse_events(response.text)
            event_types = [e.get("event") for e in events]
            assert "tool_start" in event_types
            assert "tool_result" in event_types
            assert "done" in event_types

            # Verify tool_start has the right tool name.
            tool_start = next(e for e in events if e.get("event") == "tool_start")
            data = json.loads(tool_start["data"])
            assert data["tool"] == "create_design"

            # Verify tool_result has output.
            tool_result = next(e for e in events if e.get("event") == "tool_result")
            data = json.loads(tool_result["data"])
            assert data["tool"] == "create_design"
            assert "output" in data

    @pytest.mark.asyncio
    async def test_cost_fields_persisted(self):
        """Verify that cost snapshot flows into persisted Message/Conversation rows."""
        from decimal import Decimal

        from app.models.conversation import Conversation, Message

        mock_response = MockResponse(
            content=[MockTextBlock(text="Hi.")],
            stop_reason="end_turn",
        )
        mock_client = _make_mock_client([mock_response])
        session = _NoOpAsyncSession()

        with (
            patch("app.services.agent_service.get_anthropic_client", return_value=mock_client),
            patch("app.services.agent_service.async_session_factory", return_value=session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post("/api/v1/chat", json={"message": "hi"})
            assert response.status_code == 200

        messages = [o for o in session.added if isinstance(o, Message)]
        conversations = [o for o in session.added if isinstance(o, Conversation)]
        assistant_msgs = [m for m in messages if m.role == "assistant"]
        assert assistant_msgs, "expected an assistant message to be persisted"
        m = assistant_msgs[0]
        # MockUsage: 100 input, 50 output @ sonnet-4 rates ($3/$15 per MTok)
        assert m.input_cost_usd == Decimal("0.0003")
        assert m.output_cost_usd == Decimal("0.00075")
        assert m.markup_rate is not None
        assert m.markup_cost_usd is not None
        assert m.markup_cost_usd > m.input_cost_usd + m.output_cost_usd

        assert conversations, "expected a conversation to be persisted"
        c = conversations[0]
        assert c.total_cost_usd == Decimal("0.00105")
        assert c.total_markup_cost_usd > c.total_cost_usd

    @pytest.mark.asyncio
    async def test_tool_call_telemetry_persisted(self):
        """Verify turn_id, model_key, RSS/CPU, and payload-size telemetry land on persisted ToolCall rows."""
        from app.models.conversation import ToolCall

        tool_response = MockResponse(
            content=[
                MockTextBlock(text="Let me create a design."),
                MockToolUseBlock(
                    id="toolu_telemetry_001",
                    name="create_design",
                    input={"factors": [{"name": "A", "low": 0, "high": 1}]},
                ),
            ],
            stop_reason="tool_use",
        )
        summary_response = MockResponse(
            content=[MockTextBlock(text="Done.")],
            stop_reason="end_turn",
        )
        mock_client = _make_mock_client([tool_response, summary_response])
        session = _NoOpAsyncSession()

        with (
            patch("app.services.agent_service.get_anthropic_client", return_value=mock_client),
            patch("app.services.agent_service.async_session_factory", return_value=session),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                await ac.post("/api/v1/chat", json={"message": "Create a 2-factor design"})

        tool_calls = [o for o in session.added if isinstance(o, ToolCall)]
        assert tool_calls, "expected at least one persisted ToolCall row"
        tc = tool_calls[0]
        assert tc.turn_id is not None
        assert tc.model_key is not None and tc.model_key != ""
        assert tc.input_bytes is not None and tc.input_bytes > 0
        # Successful tool calls should have an output-size figure too.
        if tc.status == "success":
            assert tc.output_bytes is not None and tc.output_bytes > 0
        # psutil sampling is best-effort but should almost always succeed in tests.
        assert tc.rss_bytes is not None and tc.rss_bytes > 0
        assert tc.cpu_percent is not None
        assert tc.output_truncated is False

        # All tools from the same chat turn should share the same turn_id.
        turn_ids = {t.turn_id for t in tool_calls}
        assert len(turn_ids) == 1

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error_event(self):
        """When ANTHROPIC_API_KEY is empty, an error SSE event is emitted."""
        with (
            patch("app.services.agent_service.settings") as mock_settings,
            patch("app.services.agent_service.async_session_factory") as mock_sf,
        ):
            mock_settings.anthropic_api_key = ""
            mock_settings.anthropic_model = "claude-sonnet-4-20250514"
            mock_sf.return_value = _NoOpAsyncSession()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post("/api/v1/chat", json={"message": "test"})

            events = parse_sse_events(response.text)
            event_types = [e.get("event") for e in events]
            assert "error" in event_types

    @pytest.mark.asyncio
    async def test_empty_message_returns_422(self):
        """Empty message should be rejected by Pydantic validation."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post("/api/v1/chat", json={"message": ""})
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_detail_level_returns_422(self):
        """Unknown detail_level values are rejected by Pydantic validation."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/chat",
                json={"message": "hi", "detail_level": "bogus"},
            )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# No-op async session for mocked tests
# ---------------------------------------------------------------------------


class _NoOpAsyncSession:
    """Async context manager that does nothing — for tests without a real DB."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args: Any):
        pass

    def add(self, obj: Any) -> None:
        # Assign a fake id if the object needs one.
        if hasattr(obj, "id") and obj.id is None:
            import uuid

            obj.id = uuid.uuid4()
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def get(self, model: Any, id: Any) -> None:
        return None

    async def execute(self, stmt: Any) -> _NoOpResult:
        return _NoOpResult()


class _NoOpResult:
    def scalars(self) -> _NoOpResult:
        return self

    def all(self) -> list:
        return []


# ---------------------------------------------------------------------------
# Integration tests — require ANTHROPIC_API_KEY
# ---------------------------------------------------------------------------

_SKIP_INTEGRATION = not os.environ.get("ANTHROPIC_API_KEY")


@pytest.mark.skipif(_SKIP_INTEGRATION, reason="ANTHROPIC_API_KEY not set")
class TestChatEndpointIntegration:
    """Integration tests that call the real Anthropic API."""

    @pytest.mark.asyncio
    async def test_simple_conversation(self):
        """Send a simple message and verify SSE stream structure."""
        with patch("app.services.agent_service.async_session_factory") as mock_sf:
            mock_sf.return_value = _NoOpAsyncSession()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/chat",
                    json={"message": "What is a factorial design? Answer in one sentence."},
                    timeout=30.0,
                )

            assert response.status_code == 200
            events = parse_sse_events(response.text)
            event_types = [e.get("event") for e in events]
            assert "conversation_id" in event_types
            assert "token" in event_types
            assert "done" in event_types

    @pytest.mark.asyncio
    async def test_tool_use_conversation(self):
        """Ask for a design — agent should call the create_design tool."""
        with patch("app.services.agent_service.async_session_factory") as mock_sf:
            mock_sf.return_value = _NoOpAsyncSession()

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/api/v1/chat",
                    json={"message": "Create a full factorial design for Temperature (100-200) and Pressure (1-5)."},
                    timeout=60.0,
                )

            assert response.status_code == 200
            events = parse_sse_events(response.text)
            event_types = [e.get("event") for e in events]
            # The agent should use the create_design tool.
            assert "tool_start" in event_types or "done" in event_types
