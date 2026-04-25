"""Tests for ``app.services.upload_claude_service``.

The Anthropic SDK is patched at ``messages.create`` so the test suite
never makes a real network call.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.uploads import ClarifyingQuestion, ParsedDesignPayload
from app.services.upload_claude_service import (
    UploadClaudeError,
    discover_structure,
)

# ---------------------------------------------------------------------------
# Fakes for the anthropic SDK response object
# ---------------------------------------------------------------------------


class _ToolUseBlock:
    type = "tool_use"

    def __init__(self, name: str, payload: dict[str, Any]) -> None:
        self.name = name
        self.input = payload


class _FakeMessage:
    def __init__(self, *, blocks: list[Any], stop_reason: str = "tool_use") -> None:
        self.content = blocks
        self.stop_reason = stop_reason


def _patch_messages_create(payload: _FakeMessage):
    """Patch ``get_anthropic_client`` to return a client that echoes ``payload``."""

    fake_client = MagicMock()
    fake_client.messages.create.return_value = payload
    return patch(
        "app.services.upload_claude_service.get_anthropic_client",
        return_value=fake_client,
    )


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_parsed_payload_for_standard_orientation() -> None:
    payload = {
        "orientation": "rows",
        "factors": [
            {"name": "Temperature", "type": "continuous", "low": 50, "high": 80, "units": "C"},
            {"name": "Pressure", "type": "continuous", "low": 1.0, "high": 2.0, "units": "bar"},
        ],
        "responses": [{"name": "Yield", "goal": "maximize"}],
        "design_actual": [
            {"Temperature": 50, "Pressure": 1.0, "Yield": 72.3},
            {"Temperature": 80, "Pressure": 2.0, "Yield": 88.4},
        ],
        "results_data": [
            {"Temperature": 50, "Pressure": 1.0, "Yield": 72.3},
            {"Temperature": 80, "Pressure": 2.0, "Yield": 88.4},
        ],
    }
    fake = _FakeMessage(blocks=[_ToolUseBlock("report_design_structure", payload)])

    with _patch_messages_create(fake):
        result = await discover_structure([["Temperature", "Pressure", "Yield"], [50, 1.0, 72.3]])

    assert isinstance(result, ParsedDesignPayload)
    assert result.orientation == "rows"
    assert {f.name for f in result.factors} == {"Temperature", "Pressure"}
    assert result.responses[0].goal == "maximize"


@pytest.mark.asyncio
async def test_returns_parsed_payload_for_transposed_orientation() -> None:
    payload = {
        "orientation": "columns",
        "factors": [
            {"name": "Temperature", "type": "continuous", "low": 50, "high": 80},
            {"name": "Pressure", "type": "continuous", "low": 1.0, "high": 2.0},
        ],
        "responses": [],
        "design_actual": [{"Temperature": 50, "Pressure": 1.0}],
        "results_data": [],
    }
    fake = _FakeMessage(blocks=[_ToolUseBlock("report_design_structure", payload)])

    with _patch_messages_create(fake):
        result = await discover_structure(
            [["Factor", "Run 1", "Run 2"], ["Temperature", 50, 80], ["Pressure", 1.0, 2.0]]
        )

    assert isinstance(result, ParsedDesignPayload)
    assert result.orientation == "columns"


@pytest.mark.asyncio
async def test_returns_questions_when_ambiguous() -> None:
    payload = {
        "questions": [
            {
                "id": "q1",
                "question": "Is `yield` a factor or an outcome?",
                "options": ["Factor", "Outcome"],
                "column_ref": "yield",
            }
        ]
    }
    fake = _FakeMessage(blocks=[_ToolUseBlock("ask_clarifying_questions", payload)])

    with _patch_messages_create(fake):
        result = await discover_structure([["yield", "x", "y"], [1, 2, 3]])

    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], ClarifyingQuestion)
    assert result[0].id == "q1"


@pytest.mark.asyncio
async def test_questions_are_capped_to_max() -> None:
    """If Claude returns more than the cap, the service trims the list."""

    payload = {
        "questions": [
            {"id": f"q{i}", "question": f"Question {i}?"}
            for i in range(1, 11)  # 10 questions
        ]
    }
    fake = _FakeMessage(blocks=[_ToolUseBlock("ask_clarifying_questions", payload)])

    with _patch_messages_create(fake):
        result = await discover_structure([["a"]])

    assert isinstance(result, list)
    assert len(result) == 5  # MAX_CLARIFYING_QUESTIONS


@pytest.mark.asyncio
async def test_second_round_with_prior_answers_passes_them_to_claude() -> None:
    """When prior_answers is set, the user message includes the previous Q&A."""

    payload = {
        "orientation": "rows",
        "factors": [{"name": "Temperature", "type": "continuous", "low": 50, "high": 80}],
        "responses": [{"name": "Yield"}],
        "design_actual": [],
        "results_data": [],
    }
    fake = _FakeMessage(blocks=[_ToolUseBlock("report_design_structure", payload)])
    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake

    with patch(
        "app.services.upload_claude_service.get_anthropic_client",
        return_value=fake_client,
    ):
        await discover_structure(
            [["Temperature", "Yield"], [50, 72]],
            prior_questions=[
                ClarifyingQuestion(id="q1", question="Is Yield an outcome?", options=["Yes", "No"]),
            ],
            prior_answers={"q1": "Yes"},
        )

    sent_messages = fake_client.messages.create.call_args.kwargs["messages"]
    user_text = sent_messages[0]["content"]
    assert "Previous Q&A" in user_text
    assert "q1" in user_text
    assert "Yes" in user_text


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_raises_when_stop_reason_is_not_tool_use() -> None:
    fake = _FakeMessage(blocks=[], stop_reason="end_turn")
    with _patch_messages_create(fake), pytest.raises(UploadClaudeError, match="tool_use"):
        await discover_structure([["a"]])


@pytest.mark.asyncio
async def test_raises_when_no_known_tool_invoked() -> None:
    block = _ToolUseBlock("some_other_tool", {})
    fake = _FakeMessage(blocks=[block])
    with _patch_messages_create(fake), pytest.raises(UploadClaudeError, match="known tool"):
        await discover_structure([["a"]])


@pytest.mark.asyncio
async def test_raises_on_malformed_report_payload() -> None:
    # Missing "orientation" -> ParsedDesignPayload validation fails.
    payload = {"factors": [], "design_actual": []}
    fake = _FakeMessage(blocks=[_ToolUseBlock("report_design_structure", payload)])
    with _patch_messages_create(fake), pytest.raises(UploadClaudeError, match="malformed structure"):
        await discover_structure([["a"]])


@pytest.mark.asyncio
async def test_raises_on_malformed_questions_payload() -> None:
    payload: dict[str, Any] = {"questions": []}  # empty list rejected
    fake = _FakeMessage(blocks=[_ToolUseBlock("ask_clarifying_questions", payload)])
    with _patch_messages_create(fake), pytest.raises(UploadClaudeError, match="malformed questions"):
        await discover_structure([["a"]])
