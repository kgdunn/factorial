"""Tests for the simulator interception hooks and in-loop state splicing.

Covers the two new modules that mediate between Claude's tool calls and
the simulator tools in process-improve:

- ``simulator_interception.pre_dispatch`` / ``post_dispatch`` — the
  pure helpers that inject ``simulator_state`` + ``confirmed`` into
  tool calls, capture ``_private`` from ``create_simulator`` output,
  and enforce the double-confirm reveal gate.
- ``_run_agent_loop`` — exercised end-to-end with a stubbed Anthropic
  client so we can watch real process-improve tools run under the
  interception harness.

The DB-backed ``simulator_service`` layer is covered implicitly by
the agent_service tests elsewhere; here we stick to the pieces that
can be verified without PostgreSQL.
"""

from __future__ import annotations

import queue
import uuid
from types import SimpleNamespace

import pytest

from app.services import agent_service
from app.services.agent_loop import _run_agent_loop
from app.services.simulator_interception import post_dispatch, pre_dispatch

# ---------------------------------------------------------------------------
# Anthropic stub: replay a scripted sequence of responses.
# ---------------------------------------------------------------------------


class _FakeUsage(SimpleNamespace):
    input_tokens: int = 10
    output_tokens: int = 10


class _FakeResponse(SimpleNamespace):
    model: str = "claude-test"
    stop_reason: str = "end_turn"
    usage: _FakeUsage = _FakeUsage()
    content: list = []


class _ScriptedStream:
    """Context-manager returning the next scripted ``_FakeResponse``."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    def __enter__(self) -> _ScriptedStream:
        return self

    def __exit__(self, *_exc) -> bool:
        return False

    def __iter__(self):  # no streaming deltas in these tests
        return iter(())

    def get_final_message(self) -> _FakeResponse:
        return self._response


class _ScriptedMessages:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = list(responses)

    def stream(self, **_kwargs) -> _ScriptedStream:
        if not self._responses:
            raise RuntimeError("Scripted client ran out of responses")
        return _ScriptedStream(self._responses.pop(0))


class _StubClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.messages = _ScriptedMessages(responses)


def _tool_use(tool_id: str, name: str, tool_input: dict) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)


def _response(*content: SimpleNamespace, stop_reason: str = "tool_use") -> _FakeResponse:
    return _FakeResponse(content=list(content), stop_reason=stop_reason)


def _drain(q: queue.Queue) -> list[tuple]:
    out: list[tuple] = []
    while True:
        item = q.get_nowait()
        if item is agent_service._SENTINEL:
            break
        out.append(item)
    return out


# ---------------------------------------------------------------------------
# Unit tests: pre_dispatch / post_dispatch helpers (no Anthropic).
# ---------------------------------------------------------------------------


class TestInterceptionHelpers:
    def test_pre_dispatch_is_noop_for_unknown_tool(self):
        before = {"values": [1, 2, 3]}
        after = pre_dispatch(
            "robust_summary_stats",
            before,
            simulator_states={},
            reveal_counts={},
            force_reveal=False,
        )
        assert after is before  # untouched, same object

    def test_pre_dispatch_injects_state_for_simulate_process(self):
        state = {"seed": 42}
        out = pre_dispatch(
            "simulate_process",
            {"sim_id": "abc", "settings": {"x": 1.0}},
            simulator_states={"abc": state},
            reveal_counts={},
            force_reveal=False,
        )
        assert out["simulator_state"] is state
        assert out["settings"] == {"x": 1.0}  # preserved

    def test_pre_dispatch_does_not_mutate_caller_input(self):
        original = {"sim_id": "abc", "settings": {"x": 1.0}}
        pre_dispatch(
            "simulate_process",
            original,
            simulator_states={"abc": {"seed": 7}},
            reveal_counts={},
            force_reveal=False,
        )
        assert "simulator_state" not in original

    def test_reveal_first_call_is_unconfirmed(self):
        counts: dict[str, int] = {}
        out = pre_dispatch(
            "reveal_simulator",
            {"sim_id": "abc"},
            simulator_states={"abc": {"seed": 1}},
            reveal_counts=counts,
            force_reveal=False,
        )
        assert out["confirmed"] is False
        assert counts["abc"] == 1

    def test_reveal_second_call_confirms_and_resets(self):
        counts = {"abc": 1}
        out = pre_dispatch(
            "reveal_simulator",
            {"sim_id": "abc"},
            simulator_states={"abc": {"seed": 1}},
            reveal_counts=counts,
            force_reveal=False,
        )
        assert out["confirmed"] is True
        assert counts["abc"] == 0  # reset so subsequent reveals ask again

    def test_reveal_force_bypasses_counter(self):
        counts: dict[str, int] = {}
        out = pre_dispatch(
            "reveal_simulator",
            {"sim_id": "abc"},
            simulator_states={"abc": {"seed": 1}},
            reveal_counts=counts,
            force_reveal=True,
        )
        assert out["confirmed"] is True
        assert counts["abc"] == 0

    def test_post_dispatch_strips_private_from_create_simulator(self):
        states: dict[str, dict] = {}
        newly: list[dict] = []
        result = {
            "sim_id": "abc",
            "public": {"foo": "bar"},
            "_private": {"seed": 99},
        }
        out = post_dispatch(
            "create_simulator",
            result,
            simulator_states=states,
            newly_created=newly,
        )
        assert "_private" not in out
        assert states["abc"] == {"seed": 99}
        assert newly == [{"sim_id": "abc", "public_summary": {"foo": "bar"}, "private_state": {"seed": 99}}]

    def test_post_dispatch_ignores_other_tools(self):
        states: dict[str, dict] = {}
        newly: list[dict] = []
        result = {"foo": "bar"}
        out = post_dispatch(
            "robust_summary_stats",
            result,
            simulator_states=states,
            newly_created=newly,
        )
        assert out is result
        assert states == {}
        assert newly == []


# ---------------------------------------------------------------------------
# End-to-end: run the agent loop with a stubbed Anthropic client.
# ---------------------------------------------------------------------------


@pytest.fixture()
def default_factors() -> list[dict]:
    return [
        {"name": "flow", "low": 100.0, "high": 300.0},
        {"name": "pH", "low": 7.0, "high": 11.0},
    ]


@pytest.fixture()
def default_outputs() -> list[dict]:
    return [{"name": "recovery"}]


def test_loop_create_then_simulate_end_to_end(default_factors, default_outputs):
    """Claude calls create_simulator, then simulate_process on the same sim_id.

    The loop must:
    1. Capture _private from the first result and stash it in simulator_states.
    2. Strip _private from the result forwarded back to Claude.
    3. Inject simulator_state into the simulate_process call so it returns
       real numeric outputs (not the "missing state" error).
    """
    create_call = _tool_use(
        "call_1",
        "create_simulator",
        {
            "process_description": "toy",
            "factors": default_factors,
            "outputs": default_outputs,
            "seed": 1,
        },
    )
    simulate_call = _tool_use(
        "call_2",
        "simulate_process",
        {"sim_id": "PLACEHOLDER", "settings": {"flow": 200.0, "pH": 9.0}},
    )
    # Because we don't know the sim_id ahead of time, the stubbed LLM
    # replays a small state machine: first round emits create_simulator;
    # the second-round response references the sim_id returned by the
    # first tool_result. We implement that by having the test fill in
    # the sim_id between rounds.
    round2 = _response(simulate_call)
    final = _response(stop_reason="end_turn")

    class _Dynamic(_ScriptedMessages):
        def __init__(self):
            super().__init__([])
            self._round = 0
            self.captured_messages: list = []

        def stream(self, **kwargs):
            self.captured_messages.append(list(kwargs["messages"]))
            self._round += 1
            if self._round == 1:
                return _ScriptedStream(_response(create_call))
            if self._round == 2:
                # Pull the sim_id out of the tool_result that Claude
                # would have received.
                last = kwargs["messages"][-1]
                tr = next(b for b in last["content"] if b["type"] == "tool_result")
                import json as _json

                payload = _json.loads(tr["content"])
                simulate_call.input["sim_id"] = payload["sim_id"]
                return _ScriptedStream(round2)
            return _ScriptedStream(final)

    client = _StubClient([])
    client.messages = _Dynamic()

    event_queue: queue.Queue = queue.Queue()
    simulator_states: dict[str, dict] = {}
    reveal_counts: dict[str, int] = {}
    newly: list[dict] = []

    result = _run_agent_loop(
        event_queue,
        messages=[{"role": "user", "content": "simulate something"}],
        tool_specs=[],
        client=client,  # type: ignore[arg-type]
        model="claude-test",
        turn_id=uuid.uuid4(),
        system_prompt="x",
        simulator_states=simulator_states,
        reveal_counts=reveal_counts,
        newly_created_sims=newly,
    )

    # Exactly one simulator was created, and its _private lives in
    # simulator_states but NOT in the tool_output audit trail.
    assert len(newly) == 1
    sim_id = newly[0]["sim_id"]
    assert sim_id in simulator_states
    assert simulator_states[sim_id]["seed"] == 1

    create_record = next(r for r in result["tool_call_records"] if r["tool_name"] == "create_simulator")
    assert "_private" not in create_record["tool_output"]
    assert create_record["tool_output"]["sim_id"] == sim_id

    simulate_record = next(r for r in result["tool_call_records"] if r["tool_name"] == "simulate_process")
    assert simulate_record["status"] == "success"
    assert "outputs" in simulate_record["tool_output"]
    assert "recovery" in simulate_record["tool_output"]["outputs"]
    assert "error" not in simulate_record["tool_output"]  # state was injected

    # Drain the queue just to confirm the loop terminated cleanly.
    events = _drain(event_queue)
    assert any(name == "done" for name, _ in events)


def test_loop_reveal_requires_two_asks(default_factors, default_outputs):
    """First reveal_simulator returns 'confirmation_needed'; second reveals."""
    create_call = _tool_use(
        "call_c",
        "create_simulator",
        {
            "process_description": "toy",
            "factors": default_factors,
            "outputs": default_outputs,
            "seed": 2,
        },
    )
    reveal_call_1 = _tool_use("call_r1", "reveal_simulator", {"sim_id": "PLACEHOLDER"})
    reveal_call_2 = _tool_use("call_r2", "reveal_simulator", {"sim_id": "PLACEHOLDER"})
    final = _response(stop_reason="end_turn")

    class _Dynamic(_ScriptedMessages):
        def __init__(self):
            super().__init__([])
            self._round = 0

        def stream(self, **kwargs):
            self._round += 1
            if self._round == 1:
                return _ScriptedStream(_response(create_call))
            if self._round == 2:
                import json as _json

                tr = next(b for b in kwargs["messages"][-1]["content"] if b["type"] == "tool_result")
                sim_id = _json.loads(tr["content"])["sim_id"]
                reveal_call_1.input["sim_id"] = sim_id
                reveal_call_2.input["sim_id"] = sim_id
                return _ScriptedStream(_response(reveal_call_1))
            if self._round == 3:
                return _ScriptedStream(_response(reveal_call_2))
            return _ScriptedStream(final)

    client = _StubClient([])
    client.messages = _Dynamic()

    event_queue: queue.Queue = queue.Queue()
    result = _run_agent_loop(
        event_queue,
        messages=[{"role": "user", "content": "show me the model"}],
        tool_specs=[],
        client=client,  # type: ignore[arg-type]
        model="claude-test",
        turn_id=uuid.uuid4(),
        system_prompt="x",
    )

    reveal_records = [r for r in result["tool_call_records"] if r["tool_name"] == "reveal_simulator"]
    assert len(reveal_records) == 2
    # First reveal: gated -> confirmation_needed
    assert reveal_records[0]["tool_output"]["status"] == "confirmation_needed"
    # Second reveal: confirmed -> full model returned
    assert reveal_records[1]["tool_output"]["status"] == "revealed"
    assert "model" in reveal_records[1]["tool_output"]


def test_loop_reveal_with_force_reveals_immediately(default_factors, default_outputs):
    """``force_reveal=True`` bypasses the double-confirm gate."""
    create_call = _tool_use(
        "c",
        "create_simulator",
        {
            "process_description": "toy",
            "factors": default_factors,
            "outputs": default_outputs,
            "seed": 3,
        },
    )
    reveal_call = _tool_use("r", "reveal_simulator", {"sim_id": "PLACEHOLDER"})
    final = _response(stop_reason="end_turn")

    class _Dynamic(_ScriptedMessages):
        def __init__(self):
            super().__init__([])
            self._round = 0

        def stream(self, **kwargs):
            self._round += 1
            if self._round == 1:
                return _ScriptedStream(_response(create_call))
            if self._round == 2:
                import json as _json

                tr = next(b for b in kwargs["messages"][-1]["content"] if b["type"] == "tool_result")
                reveal_call.input["sim_id"] = _json.loads(tr["content"])["sim_id"]
                return _ScriptedStream(_response(reveal_call))
            return _ScriptedStream(final)

    client = _StubClient([])
    client.messages = _Dynamic()

    result = _run_agent_loop(
        queue.Queue(),
        messages=[{"role": "user", "content": "force it"}],
        tool_specs=[],
        client=client,  # type: ignore[arg-type]
        model="claude-test",
        turn_id=uuid.uuid4(),
        system_prompt="x",
        force_reveal=True,
    )

    reveal_record = next(r for r in result["tool_call_records"] if r["tool_name"] == "reveal_simulator")
    assert reveal_record["tool_output"]["status"] == "revealed"
