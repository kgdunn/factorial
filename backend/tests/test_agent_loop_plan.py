"""Verify the agent loop translates record_plan / update_plan tool calls
into structured ``plan`` / ``plan_update`` SSE events and emits coarse
``phase`` events around LLM calls and real tool calls.

Exercises the synchronous loop directly with a stub Anthropic client so
no network / Postgres / Neo4j is needed.
"""

from __future__ import annotations

import queue
import uuid
from types import SimpleNamespace

import pytest

from app.services import agent_service
from app.services.tools import execute_tool_call, get_tool_specs

# ---------------------------------------------------------------------------
# Stub client
# ---------------------------------------------------------------------------


class _StubBlock(SimpleNamespace):
    """Minimal stand-in for an Anthropic content block."""


def _text_block(text: str) -> _StubBlock:
    return _StubBlock(type="text", text=text)


def _tool_use_block(name: str, tool_input: dict, tool_id: str | None = None) -> _StubBlock:
    return _StubBlock(
        type="tool_use",
        id=tool_id or f"toolu_{uuid.uuid4().hex[:8]}",
        name=name,
        input=tool_input,
    )


def _stub_message(content_blocks: list[_StubBlock], stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(
        content=content_blocks,
        stop_reason=stop_reason,
        model="claude-sonnet-4-6",
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
    )


class _StubStream:
    def __init__(self, final_message: SimpleNamespace) -> None:
        self._final = final_message

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def __iter__(self):
        return iter(())  # No content_block_delta events — get_final_message is what matters.

    def get_final_message(self) -> SimpleNamespace:
        return self._final


class _StubMessages:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = list(responses)
        self._call = 0

    def stream(self, **_kwargs):
        idx = min(self._call, len(self._responses) - 1)
        self._call += 1
        return _StubStream(self._responses[idx])


class _StubClient:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.messages = _StubMessages(responses)


def _drain(q: queue.Queue) -> list[tuple]:
    """Drain the event queue into a flat list of (event_name, payload)."""
    out: list[tuple] = []
    while True:
        item = q.get_nowait()
        if item is None:
            break
        out.append(item)
    return out


def _run(responses: list[SimpleNamespace]) -> list[tuple]:
    q: queue.Queue = queue.Queue()
    agent_service._run_agent_loop(
        event_queue=q,
        messages=[{"role": "user", "content": "hi"}],
        tool_specs=[],
        client=_StubClient(responses),  # type: ignore[arg-type]
        model="claude-sonnet-4-6",
        turn_id=uuid.uuid4(),
        system_prompt="test prompt",
    )
    return _drain(q)


# ---------------------------------------------------------------------------
# Local meta tools (record_plan / update_plan)
# ---------------------------------------------------------------------------


class TestLocalMetaTools:
    def test_record_plan_appears_in_specs(self):
        names = {s["name"] for s in get_tool_specs()}
        assert "record_plan" in names
        assert "update_plan" in names

    def test_record_plan_executes_without_subprocess(self):
        # If the local short-circuit broke, this would route to the
        # process_improve sandbox and fail the unknown-tool check.
        result = execute_tool_call("record_plan", {"steps": ["A", "B"]})
        assert result == {"acknowledged": True}

    def test_update_plan_executes_without_subprocess(self):
        result = execute_tool_call(
            "update_plan",
            {"updates": [{"step_index": 0, "status": "completed"}]},
        )
        assert result == {"acknowledged": True}

    def test_record_plan_rejects_empty_steps(self):
        from app.services.exceptions import ToolExecutionError

        with pytest.raises(ToolExecutionError):
            execute_tool_call("record_plan", {"steps": []})

    def test_update_plan_rejects_bad_status(self):
        from app.services.exceptions import ToolExecutionError

        with pytest.raises(ToolExecutionError):
            execute_tool_call(
                "update_plan",
                {"updates": [{"step_index": 0, "status": "bogus"}]},
            )

    def test_meta_tools_filter_by_category(self):
        names = {s["name"] for s in get_tool_specs(category="meta")}
        assert names == {"record_plan", "update_plan"}


# ---------------------------------------------------------------------------
# Agent loop event emission
# ---------------------------------------------------------------------------


class TestAgentLoopEvents:
    def test_record_plan_emits_plan_event_not_tool_events(self):
        # Turn 1: model calls record_plan; turn 2: ends.
        responses = [
            _stub_message(
                [_tool_use_block("record_plan", {"steps": ["First step", "Second step"]})],
                stop_reason="tool_use",
            ),
            _stub_message([_text_block("done")]),
        ]
        events = _run(responses)
        names = [n for n, _ in events]

        assert "plan" in names, names
        plan_payloads = [d for n, d in events if n == "plan"]
        assert plan_payloads[0]["steps"] == ["First step", "Second step"]
        assert "plan_id" in plan_payloads[0] and plan_payloads[0]["plan_id"]

        # No tool_start / tool_result events for the meta-tool.
        for name, data in events:
            if name in {"tool_start", "tool_result"}:
                assert data.get("tool") != "record_plan", (name, data)

    def test_update_plan_emits_plan_update_event_with_plan_id(self):
        # Turn 1: record_plan; Turn 2: update_plan; Turn 3: ends.
        responses = [
            _stub_message(
                [_tool_use_block("record_plan", {"steps": ["S1", "S2"]})],
                stop_reason="tool_use",
            ),
            _stub_message(
                [
                    _tool_use_block(
                        "update_plan",
                        {"updates": [{"step_index": 0, "status": "completed"}]},
                    )
                ],
                stop_reason="tool_use",
            ),
            _stub_message([_text_block("done")]),
        ]
        events = _run(responses)

        plan_id = next(d["plan_id"] for n, d in events if n == "plan")
        updates = [d for n, d in events if n == "plan_update"]
        assert len(updates) == 1
        assert updates[0]["plan_id"] == plan_id
        assert updates[0]["updates"] == [{"step_index": 0, "status": "completed"}]

        # Same suppression invariant for update_plan tool_* events.
        for name, data in events:
            if name in {"tool_start", "tool_result"}:
                assert data.get("tool") != "update_plan", (name, data)

    def test_phase_thinking_precedes_each_llm_call(self):
        responses = [_stub_message([_text_block("hi")])]
        events = _run(responses)
        # The very first event must be a thinking phase.
        assert events[0][0] == "phase"
        assert events[0][1]["phase"] == "thinking"
        assert events[0][1]["turn"] == 1

    def test_phase_calling_tool_precedes_real_tool_call(self):
        responses = [
            _stub_message(
                [_tool_use_block("robust_summary_stats", {"values": [1.0, 2.0, 3.0]})],
                stop_reason="tool_use",
            ),
            _stub_message([_text_block("done")]),
        ]
        events = _run(responses)
        # Find the phase event for the tool, then the tool_start that follows.
        phase_idx = next(i for i, (n, d) in enumerate(events) if n == "phase" and d.get("phase") == "calling_tool")
        # tool_start should be the next non-phase event.
        ts_idx = next(i for i, (n, _) in enumerate(events) if n == "tool_start")
        assert ts_idx > phase_idx
        assert events[phase_idx][1]["tool"] == "robust_summary_stats"

    def test_phase_finalizing_precedes_done(self):
        responses = [_stub_message([_text_block("hi")])]
        events = _run(responses)
        names = [n for n, _ in events]
        # finalizing must be the entry directly before done.
        done_idx = names.index("done")
        assert names[done_idx - 1] == "phase"
        assert events[done_idx - 1][1]["phase"] == "finalizing"
