"""Synchronous agent tool-use loop, runs in a background thread.

Split out from :mod:`app.services.agent_service` so the orchestrator
(``run_chat``) and the sync worker can be reviewed and tested as
separate concerns. The loop itself is untouched.
"""

from __future__ import annotations

import json
import logging
import queue
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import anthropic
import psutil

from app.services import pricing
from app.services.anthropic_status import status_tracker
from app.services.exceptions import ToolExecutionError
from app.services.simulator_interception import RevealCounts, SimulatorStates, post_dispatch, pre_dispatch
from app.services.tools import execute_tool_call, is_local_tool

# Pretty labels for the ``phase`` event's ``label`` field. Keep in sync
# with the Anthropic-format tool specs returned by ``get_tool_specs``.
_TOOL_LABELS: dict[str, str] = {
    "generate_design": "Design Matrix",
    "evaluate_design": "Design Evaluation",
    "analyze_results": "Result Analysis",
    "create_simulator": "Simulator Setup",
    "simulate_process": "Process Simulation",
    "reveal_simulator": "Simulator Reveal",
    "visualize_doe": "Visualization",
}

logger = logging.getLogger(__name__)

# Safety limit: maximum agent loop iterations before forced stop.
MAX_AGENT_TURNS = 10

# Sentinel pushed to the queue to signal that the loop has finished.
_SENTINEL: None = None

# Type alias for items in the event queue.
_QueueItem = tuple[str, dict[str, Any]] | None


# ---------------------------------------------------------------------------
# Agent loop (runs in a thread)
# ---------------------------------------------------------------------------


def _run_agent_loop(  # noqa: PLR0913
    event_queue: queue.Queue[_QueueItem],
    messages: list[dict[str, Any]],
    tool_specs: list[dict[str, Any]],
    client: anthropic.Anthropic,
    model: str,
    turn_id: uuid.UUID,
    system_prompt: str,
    simulator_states: SimulatorStates | None = None,
    reveal_counts: RevealCounts | None = None,
    newly_created_sims: list[dict[str, Any]] | None = None,
    force_reveal: bool = False,
) -> dict[str, Any]:
    """Synchronous agent loop executed in a background thread.

    Pushes ``(event_name, data_dict)`` tuples to *event_queue*.
    Returns a result dict with ``new_messages`` (Anthropic-format messages
    appended during the loop) and ``tool_call_records`` (timing/audit data).
    """
    # Defaults allow callers that don't use the simulator hooks (e.g.
    # legacy tests) to call this loop with the original signature.
    if simulator_states is None:
        simulator_states = {}
    if reveal_counts is None:
        reveal_counts = {}
    if newly_created_sims is None:
        newly_created_sims = []

    new_messages: list[dict[str, Any]] = []
    tool_call_records: list[dict[str, Any]] = []
    agent_turn = 0
    # Tracks the most recent ``record_plan`` invocation so subsequent
    # ``update_plan`` events can be tagged with the same ``plan_id``.
    current_plan_id: str | None = None

    try:
        while agent_turn < MAX_AGENT_TURNS:
            agent_turn += 1
            turn_start = time.perf_counter()

            # Phase: model is "thinking" — covers the API round-trip
            # before the first text token arrives.
            event_queue.put(
                (
                    "phase",
                    {"phase": "thinking", "turn": agent_turn, "max_turns": MAX_AGENT_TURNS},
                )
            )

            # --- Stream the API call ---
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=tool_specs,
            ) as stream:
                text_parts: list[str] = []
                streaming_phase_emitted = False
                for event in stream:
                    if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                        if not streaming_phase_emitted:
                            event_queue.put(
                                (
                                    "phase",
                                    {"phase": "streaming", "turn": agent_turn, "max_turns": MAX_AGENT_TURNS},
                                )
                            )
                            streaming_phase_emitted = True
                        event_queue.put(("token", {"text": event.delta.text}))
                        text_parts.append(event.delta.text)

                response = stream.get_final_message()

            turn_latency_ms = int((time.perf_counter() - turn_start) * 1000)
            status_tracker.record_success(turn_latency_ms)

            # --- Collect response metadata ---
            usage = response.usage
            cost = pricing.calculate_cost(response.model, usage.input_tokens, usage.output_tokens)
            response_meta = {
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "stop_reason": response.stop_reason,
                "model": response.model,
                "latency_ms": turn_latency_ms,
                **cost,
            }

            # --- Append assistant message (with all content blocks) ---
            # Convert SDK content blocks to dicts for serialisation.
            content_dicts = []
            for block in response.content:
                if block.type == "text":
                    content_dicts.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    content_dicts.append(
                        {
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        }
                    )

            assistant_msg = {"role": "assistant", "content": content_dicts, "_meta": response_meta}
            messages.append({"role": "assistant", "content": response.content})
            new_messages.append(assistant_msg)

            # --- Check for tool calls ---
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if response.stop_reason != "tool_use" or not tool_use_blocks:
                event_queue.put(("phase", {"phase": "finalizing"}))
                event_queue.put(("done", {}))
                break

            # --- Execute each tool call ---
            tool_results: list[dict[str, Any]] = []
            for call_order, tool_block in enumerate(tool_use_blocks, start=1):
                # Meta tools (record_plan / update_plan) are translated
                # into ``plan`` / ``plan_update`` SSE events instead of
                # the usual ``tool_start`` / ``tool_result`` pair so the
                # frontend can render them as inline plan UI rather than
                # tool-call cards.
                if is_local_tool(tool_block.name):
                    if tool_block.name == "record_plan":
                        plan_id = uuid.uuid4().hex
                        current_plan_id = plan_id
                        steps = tool_block.input.get("steps", []) if isinstance(tool_block.input, dict) else []
                        event_queue.put(("plan", {"plan_id": plan_id, "steps": steps}))
                    elif tool_block.name == "update_plan":
                        updates = tool_block.input.get("updates", []) if isinstance(tool_block.input, dict) else []
                        event_queue.put(
                            (
                                "plan_update",
                                {"plan_id": current_plan_id, "updates": updates},
                            )
                        )
                else:
                    event_queue.put(
                        (
                            "phase",
                            {
                                "phase": "calling_tool",
                                "tool": tool_block.name,
                                "label": _TOOL_LABELS.get(tool_block.name, tool_block.name),
                                "turn": agent_turn,
                                "max_turns": MAX_AGENT_TURNS,
                            },
                        )
                    )
                    event_queue.put(("tool_start", {"tool": tool_block.name, "input": tool_block.input}))

                input_bytes = len(json.dumps(tool_block.input, default=str).encode("utf-8"))
                record: dict[str, Any] = {
                    "tool_use_id": tool_block.id,
                    "tool_name": tool_block.name,
                    "tool_input": tool_block.input,
                    "agent_turn": agent_turn,
                    "call_order": call_order,
                    "started_at": datetime.now(UTC),
                    "turn_id": turn_id,
                    "model_key": model,
                    "input_bytes": input_bytes,
                    "output_truncated": False,
                }

                t0 = time.perf_counter()
                try:
                    effective_input = pre_dispatch(
                        tool_block.name,
                        tool_block.input,
                        simulator_states=simulator_states,
                        reveal_counts=reveal_counts,
                        force_reveal=force_reveal,
                    )
                    result = execute_tool_call(tool_block.name, effective_input)
                    result = post_dispatch(
                        tool_block.name,
                        result,
                        simulator_states=simulator_states,
                        newly_created=newly_created_sims,
                    )
                    duration_ms = int((time.perf_counter() - t0) * 1000)
                    output_bytes = len(json.dumps(result, default=str).encode("utf-8"))

                    record.update(
                        {
                            "tool_output": result,
                            "status": "success",
                            "completed_at": datetime.now(UTC),
                            "duration_ms": duration_ms,
                            "output_bytes": output_bytes,
                        }
                    )

                    if not is_local_tool(tool_block.name):
                        event_queue.put(("tool_result", {"tool": tool_block.name, "output": result}))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": json.dumps(result),
                        }
                    )

                except ToolExecutionError as exc:
                    duration_ms = int((time.perf_counter() - t0) * 1000)
                    record.update(
                        {
                            "status": "error",
                            "error_message": exc.message,
                            "completed_at": datetime.now(UTC),
                            "duration_ms": duration_ms,
                        }
                    )

                    if not is_local_tool(tool_block.name):
                        event_queue.put(
                            (
                                "tool_result",
                                {
                                    "tool": tool_block.name,
                                    "output": {"error": exc.message},
                                },
                            )
                        )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": json.dumps({"error": exc.message}),
                            "is_error": True,
                        }
                    )

                # Process-wide system snapshot at tool finish. NOT per-tool:
                # in a multi-worker process the numbers describe the whole
                # backend, not this tool's own cost. Best read as "what was
                # the system doing when this tool ended".
                try:
                    proc = psutil.Process()
                    record["rss_bytes"] = proc.memory_info().rss
                    record["cpu_percent"] = proc.cpu_percent(interval=None)
                except psutil.Error:
                    # Telemetry must never break the agent loop.
                    record["rss_bytes"] = None
                    record["cpu_percent"] = None

                tool_call_records.append(record)

            # Append tool results as a user message and loop.
            tool_result_msg = {"role": "user", "content": tool_results, "_is_tool_results": True}
            messages.append({"role": "user", "content": tool_results})
            new_messages.append(tool_result_msg)

        else:
            # Exhausted MAX_AGENT_TURNS
            event_queue.put(("error", {"message": f"Agent loop exceeded {MAX_AGENT_TURNS} iterations."}))

    except anthropic.AuthenticationError:
        event_queue.put(("error", {"message": "Invalid Anthropic API key."}))
    except anthropic.RateLimitError:
        event_queue.put(("error", {"message": "Anthropic rate limit exceeded. Please retry later."}))
    except (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.InternalServerError) as exc:
        status_tracker.record_error(type(exc).__name__)
        event_queue.put(
            (
                "error",
                {
                    "kind": "anthropic_unavailable",
                    "message": "The AI service is currently unavailable. Please try again in a moment.",
                    "detail": str(exc),
                },
            )
        )
    except Exception:
        logger.exception("Agent loop failed")
        event_queue.put(("error", {"message": "Internal error in agent loop."}))
    finally:
        event_queue.put(_SENTINEL)

    return {"new_messages": new_messages, "tool_call_records": tool_call_records}
