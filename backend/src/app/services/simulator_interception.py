"""Helpers that splice simulator state in/out of the agent tool-call loop.

The agent loop in :mod:`app.services.agent_service` runs in a background
thread that dispatches tool calls via
:func:`app.services.tools.execute_tool_call`. Three simulator tools —
``create_simulator``, ``simulate_process``, ``reveal_simulator`` — rely
on state that is deliberately absent from the LLM-visible JSON schema:

- The hidden ``private_state`` produced by ``create_simulator`` must be
  captured server-side and stripped from the tool result before it is
  echoed back to the LLM.
- ``simulate_process`` and ``reveal_simulator`` must have that
  ``simulator_state`` injected back in when the LLM calls them by
  ``sim_id``; the LLM never carries the state itself.
- ``reveal_simulator`` is gated behind a double-confirm policy: the
  first request returns a "pending" status, the second flips
  ``confirmed=True``.

All three helpers are synchronous and free of I/O so they can be called
from inside the agent loop's thread without touching the asyncio event
loop. They mutate the passed-in dicts, which are owned by ``run_chat``.
"""

from __future__ import annotations

from typing import Any

# ``sim_id`` value -> hidden ``private_state`` dict, used to inject
# state into ``simulate_process`` / ``reveal_simulator`` tool inputs.
SimulatorStates = dict[str, dict[str, Any]]

# ``sim_id`` -> number of times ``reveal_simulator`` has been called
# during the current conversation without the user having confirmed.
RevealCounts = dict[str, int]

SIMULATOR_TOOL_NAMES: frozenset[str] = frozenset(
    {"create_simulator", "simulate_process", "reveal_simulator"}
)


def pre_dispatch(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    simulator_states: SimulatorStates,
    reveal_counts: RevealCounts,
    force_reveal: bool,
) -> dict[str, Any]:
    """Return a tool-input dict enriched with server-side state.

    Never mutates *tool_input* (the caller keeps the raw LLM request for
    the audit log). The returned dict is what we actually pass to
    ``execute_tool_call``.
    """
    if tool_name not in SIMULATOR_TOOL_NAMES:
        return tool_input
    effective = dict(tool_input)
    sim_id = effective.get("sim_id") if isinstance(effective.get("sim_id"), str) else None

    if tool_name == "simulate_process" and sim_id:
        state = simulator_states.get(sim_id)
        if state is not None:
            effective["simulator_state"] = state

    elif tool_name == "reveal_simulator" and sim_id:
        state = simulator_states.get(sim_id)
        if state is not None:
            effective["simulator_state"] = state
        # Double-confirm policy: first request increments counter and
        # dispatches unconfirmed (tool returns 'confirmation_needed');
        # second request flips to confirmed=True and resets the counter.
        current = reveal_counts.get(sim_id, 0)
        is_confirmed = force_reveal or current >= 1
        effective["confirmed"] = is_confirmed
        reveal_counts[sim_id] = 0 if is_confirmed else current + 1

    return effective


def post_dispatch(
    tool_name: str,
    result: Any,
    *,
    simulator_states: SimulatorStates,
    newly_created: list[dict[str, Any]],
) -> Any:
    """Intercept ``create_simulator`` output: stash + strip the hidden state.

    Mutates *result* in place (pops the leading-underscore ``_private``
    key) so the same object — now stripped — ends up in the tool audit
    log and in the tool_result message sent back to the LLM. Returns
    *result* unchanged for caller convenience.
    """
    if tool_name != "create_simulator" or not isinstance(result, dict):
        return result
    private = result.pop("_private", None)
    sim_id = result.get("sim_id")
    if isinstance(sim_id, str) and isinstance(private, dict):
        simulator_states[sim_id] = private
        newly_created.append(
            {
                "sim_id": sim_id,
                "public_summary": result.get("public") or {},
                "private_state": private,
            }
        )
    return result
