"""Agent service: Anthropic tool-use loop with SSE streaming.

Core architecture:
    1. ``run_chat()`` is the async orchestrator called by the chat endpoint.
    2. It launches ``_run_agent_loop()`` in a thread via ``asyncio.to_thread``.
    3. The sync loop pushes SSE events to a ``queue.Queue``.
    4. ``_stream_from_queue()`` is an async generator that drains the queue
       and yields ``ServerSentEvent`` objects for ``EventSourceResponse``.
    5. After the loop finishes, assistant messages and tool-call audit rows
       are persisted to PostgreSQL.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import re
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import ServerSentEvent

from app.config import settings
from app.db.session import async_session_factory
from app.models.conversation import Conversation, Message, ToolCall
from app.services import pricing
from app.services.exceptions import ToolExecutionError
from app.services.experiment_service import (
    create_experiment,
    get_latest_experiment_for_conversation,
)
from app.services.tools import execute_tool_call, get_tool_specs

logger = logging.getLogger(__name__)

# Safety limit: maximum agent loop iterations before forced stop.
MAX_AGENT_TURNS = 10

SYSTEM_PROMPT = """\
You are an expert Design of Experiments (DOE) assistant helping scientists and \
engineers plan, execute, and analyse experiments systematically.

Your expertise covers:
- Factorial designs (full and fractional), Plackett-Burman screening designs
- Response surface methodology (CCD, Box-Behnken, D-optimal)
- Mixture designs, Taguchi methods, definitive screening designs
- Statistical analysis: ANOVA, regression, significance testing
- Practical guidance: choosing factors, setting levels, interpreting results

When a user describes their experimental problem:
1. Ask clarifying questions if the problem is under-specified.
2. Recommend an appropriate design strategy with reasoning.
3. Use the available tools to create designs or analyse results \u2014 do not \
   fabricate numerical outputs yourself.
4. Whenever ``generate_design`` succeeds, immediately call \
   ``evaluate_design`` on the same design before showing the matrix to \
   the user. Summarise the resolution, the confounding/aliasing of main \
   effects and 2-factor interactions, the D- and I-efficiency, and the \
   power per main effect for the assumed noise level. If the user has \
   not supplied an expected residual standard deviation (\u03c3) or a \
   minimum practical effect size, ask for them before calling \
   ``evaluate_design``.
5. Explain results in plain language, highlighting which factors matter \
   and what to do next.

Always explain your reasoning before calling a tool, and summarise the \
results after receiving tool output.
"""

# Role slugs come from the admin-managed ``roles`` table (or the legacy
# ``users.background`` column). They're still validated against this
# regex before being interpolated into the system prompt so that a
# tampered DB row can't inject prompt content.
_ALLOWED_BACKGROUND_RE = re.compile(r"^[a-z0-9_]{1,50}$")


# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------


def get_anthropic_client() -> anthropic.Anthropic:
    """Create a synchronous Anthropic client.

    Raises ``RuntimeError`` when the API key is not configured.
    """
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")  # noqa: TRY003
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


# ---------------------------------------------------------------------------
# SSE event helpers
# ---------------------------------------------------------------------------

# Sentinel pushed to the queue to signal that the loop has finished.
_SENTINEL: None = None

# Type alias for items in the event queue.
_QueueItem = tuple[str, dict[str, Any]] | None


def _sse(event: str, data: dict[str, Any]) -> ServerSentEvent:
    """Create a ``ServerSentEvent`` with a JSON-serialised data payload."""
    return ServerSentEvent(data=json.dumps(data), event=event)


# ---------------------------------------------------------------------------
# Agent loop (runs in a thread)
# ---------------------------------------------------------------------------


def _run_agent_loop(
    event_queue: queue.Queue[_QueueItem],
    messages: list[dict[str, Any]],
    tool_specs: list[dict[str, Any]],
    client: anthropic.Anthropic,
    model: str,
) -> dict[str, Any]:
    """Synchronous agent loop executed in a background thread.

    Pushes ``(event_name, data_dict)`` tuples to *event_queue*.
    Returns a result dict with ``new_messages`` (Anthropic-format messages
    appended during the loop) and ``tool_call_records`` (timing/audit data).
    """
    new_messages: list[dict[str, Any]] = []
    tool_call_records: list[dict[str, Any]] = []
    agent_turn = 0

    try:
        while agent_turn < MAX_AGENT_TURNS:
            agent_turn += 1
            turn_start = time.perf_counter()

            # --- Stream the API call ---
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=tool_specs,
            ) as stream:
                text_parts: list[str] = []
                for event in stream:
                    if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                        event_queue.put(("token", {"text": event.delta.text}))
                        text_parts.append(event.delta.text)

                response = stream.get_final_message()

            turn_latency_ms = int((time.perf_counter() - turn_start) * 1000)

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
                event_queue.put(("done", {}))
                break

            # --- Execute each tool call ---
            tool_results: list[dict[str, Any]] = []
            for call_order, tool_block in enumerate(tool_use_blocks, start=1):
                event_queue.put(("tool_start", {"tool": tool_block.name, "input": tool_block.input}))

                record: dict[str, Any] = {
                    "tool_use_id": tool_block.id,
                    "tool_name": tool_block.name,
                    "tool_input": tool_block.input,
                    "agent_turn": agent_turn,
                    "call_order": call_order,
                    "started_at": datetime.now(UTC),
                }

                t0 = time.perf_counter()
                try:
                    result = execute_tool_call(tool_block.name, tool_block.input)
                    duration_ms = int((time.perf_counter() - t0) * 1000)

                    record.update(
                        {
                            "tool_output": result,
                            "status": "success",
                            "completed_at": datetime.now(UTC),
                            "duration_ms": duration_ms,
                        }
                    )

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
    except Exception:
        logger.exception("Agent loop failed")
        event_queue.put(("error", {"message": "Internal error in agent loop."}))
    finally:
        event_queue.put(_SENTINEL)

    return {"new_messages": new_messages, "tool_call_records": tool_call_records}


# ---------------------------------------------------------------------------
# Async SSE generator
# ---------------------------------------------------------------------------


async def _stream_from_queue(event_queue: queue.Queue[_QueueItem]) -> AsyncGenerator[ServerSentEvent, None]:
    """Async generator that drains the thread-safe queue as SSE events."""
    while True:
        try:
            item = event_queue.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.01)
            continue

        if item is _SENTINEL:
            break

        event_name, data = item
        yield _sse(event_name, data)


# ---------------------------------------------------------------------------
# History reconstruction
# ---------------------------------------------------------------------------


def _build_messages_from_history(rows: list[Message]) -> list[dict[str, Any]]:
    """Convert stored ``Message`` rows into Anthropic API message format.

    Groups consecutive rows by role, assembling multi-block content arrays
    for assistant tool_use messages and user tool_result messages.
    """
    if not rows:
        return []

    messages: list[dict[str, Any]] = []
    current_role: str | None = None
    current_blocks: list[Any] = []

    def _flush() -> None:
        if current_role and current_blocks:
            if len(current_blocks) == 1 and isinstance(current_blocks[0], str):
                messages.append({"role": current_role, "content": current_blocks[0]})
            else:
                messages.append({"role": current_role, "content": list(current_blocks)})

    for row in rows:
        # Determine the block for this row.
        if row.is_tool_result:
            block: Any = {
                "type": "tool_result",
                "tool_use_id": row.tool_use_id or "",
                "content": row.content or "",
            }
            role = "user"
        elif row.tool_name and row.role == "assistant":
            # Assistant tool_use block.
            block = {
                "type": "tool_use",
                "id": row.tool_use_id or "",
                "name": row.tool_name,
                "input": row.tool_input or {},
            }
            role = "assistant"
        else:
            # Plain text block.
            block = row.content or ""
            role = row.role

        # Group consecutive same-role blocks.
        if role != current_role:
            _flush()
            current_role = role
            current_blocks = [block]
        else:
            current_blocks.append(block)

    _flush()
    return messages


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


async def _persist_new_messages(
    db: AsyncSession,
    conversation: Conversation,
    new_messages: list[dict[str, Any]],
    start_sequence: int,
) -> dict[str, uuid.UUID]:
    """Persist new assistant / tool_result messages.  Returns a map of tool_use_id -> Message.id."""
    seq = start_sequence
    tool_use_id_to_msg_id: dict[str, uuid.UUID] = {}

    for msg in new_messages:
        role = msg["role"]
        meta = msg.get("_meta", {})
        is_tool_results = msg.get("_is_tool_results", False)
        content_blocks = msg.get("content", [])

        if is_tool_results:
            # Tool result entries.
            for block in content_blocks:
                msg_row = Message(
                    conversation_id=conversation.id,
                    role="user",
                    content=block.get("content", ""),
                    tool_use_id=block.get("tool_use_id"),
                    is_tool_result=True,
                    sequence=seq,
                )
                db.add(msg_row)
                seq += 1
        elif isinstance(content_blocks, list):
            # Assistant message with one or more content blocks.
            for block in content_blocks:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    msg_row = Message(
                        conversation_id=conversation.id,
                        role="assistant",
                        content="",
                        tool_use_id=block.get("id"),
                        tool_name=block.get("name"),
                        tool_input=block.get("input"),
                        sequence=seq,
                        input_tokens=meta.get("input_tokens", 0),
                        output_tokens=meta.get("output_tokens", 0),
                        model_used=meta.get("model"),
                        stop_reason=meta.get("stop_reason"),
                        latency_ms=meta.get("latency_ms"),
                        input_rate_usd_per_mtok=meta.get("input_rate_usd_per_mtok"),
                        output_rate_usd_per_mtok=meta.get("output_rate_usd_per_mtok"),
                        input_cost_usd=meta.get("input_cost_usd"),
                        output_cost_usd=meta.get("output_cost_usd"),
                        markup_rate=meta.get("markup_rate"),
                        markup_cost_usd=meta.get("markup_cost_usd"),
                    )
                    db.add(msg_row)
                    tool_use_id_to_msg_id[block.get("id", "")] = msg_row.id
                    seq += 1
                elif isinstance(block, dict) and block.get("type") == "text":
                    msg_row = Message(
                        conversation_id=conversation.id,
                        role="assistant",
                        content=block.get("text", ""),
                        sequence=seq,
                        input_tokens=meta.get("input_tokens", 0),
                        output_tokens=meta.get("output_tokens", 0),
                        model_used=meta.get("model"),
                        stop_reason=meta.get("stop_reason"),
                        latency_ms=meta.get("latency_ms"),
                        input_rate_usd_per_mtok=meta.get("input_rate_usd_per_mtok"),
                        output_rate_usd_per_mtok=meta.get("output_rate_usd_per_mtok"),
                        input_cost_usd=meta.get("input_cost_usd"),
                        output_cost_usd=meta.get("output_cost_usd"),
                        markup_rate=meta.get("markup_rate"),
                        markup_cost_usd=meta.get("markup_cost_usd"),
                    )
                    db.add(msg_row)
                    seq += 1
        else:
            # Simple text message (shouldn't happen for new assistant msgs, but handle it).
            msg_row = Message(
                conversation_id=conversation.id,
                role=role,
                content=str(content_blocks),
                sequence=seq,
            )
            db.add(msg_row)
            seq += 1

        # Accumulate token counts on the conversation.
        conversation.total_input_tokens = (conversation.total_input_tokens or 0) + meta.get("input_tokens", 0)
        conversation.total_output_tokens = (conversation.total_output_tokens or 0) + meta.get("output_tokens", 0)

        # Accumulate cost. Raw cost = what Anthropic charges us; markup cost
        # = what we would bill the customer at the markup rate in force
        # when the call was made.
        conversation.total_cost_usd = (conversation.total_cost_usd or Decimal("0")) + meta.get(
            "raw_cost_usd", Decimal("0")
        )
        conversation.total_markup_cost_usd = (conversation.total_markup_cost_usd or Decimal("0")) + meta.get(
            "markup_cost_usd", Decimal("0")
        )

    return tool_use_id_to_msg_id


async def _persist_tool_calls(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    records: list[dict[str, Any]],
    tool_use_id_to_msg_id: dict[str, uuid.UUID],
) -> None:
    """Persist ``ToolCall`` audit rows."""
    for rec in records:
        tc = ToolCall(
            conversation_id=conversation_id,
            message_id=tool_use_id_to_msg_id.get(rec.get("tool_use_id", "")),
            tool_use_id=rec.get("tool_use_id"),
            tool_name=rec["tool_name"],
            tool_input=rec.get("tool_input"),
            tool_output=rec.get("tool_output"),
            status=rec.get("status", "success"),
            error_message=rec.get("error_message"),
            started_at=rec.get("started_at"),
            completed_at=rec.get("completed_at"),
            duration_ms=rec.get("duration_ms"),
            agent_turn=rec.get("agent_turn", 1),
            call_order=rec.get("call_order", 1),
        )
        db.add(tc)


# ---------------------------------------------------------------------------
# Auto-save helper
# ---------------------------------------------------------------------------


async def _create_experiment_from_design(
    db: AsyncSession,
    design_output: dict[str, Any],
    conversation_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> Any:  # noqa: ANN401
    """Create an Experiment record from a successful generate_design output."""
    return await create_experiment(db, design_output=design_output, conversation_id=conversation_id, user_id=user_id)


def _build_system_prompt(user_background: str | None) -> str:
    """Build the system prompt, optionally personalised with user background.

    The background value is validated against an allowlist to prevent
    prompt injection via the user profile field.
    """
    if user_background and _ALLOWED_BACKGROUND_RE.match(user_background):
        bg_label = user_background.replace("_", " ")
        return (
            f"{SYSTEM_PROMPT}\n\n"
            f"The user's background: {bg_label}. "
            f"Tailor your explanations, terminology, and examples to this domain."
        )
    return SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------


async def run_chat(
    message: str,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID | None = None,
    user_background: str | None = None,
) -> AsyncGenerator[ServerSentEvent, None]:
    """Orchestrate a chat turn: load history, run agent loop, persist, stream SSE.

    The DB session is managed inside the generator (not via ``Depends``)
    so its lifetime matches the SSE stream.
    """
    system_prompt = _build_system_prompt(user_background)

    async with async_session_factory() as db:
        try:
            # 1. Load or create conversation.
            if conversation_id:
                conversation = await db.get(Conversation, conversation_id)
                if not conversation:
                    yield _sse("error", {"message": f"Conversation {conversation_id} not found."})
                    return
                # Ownership check: only service accounts can access other users' conversations.
                if user_id and conversation.user_id and conversation.user_id != user_id:
                    yield _sse("error", {"message": f"Conversation {conversation_id} not found."})
                    return
                result = await db.execute(
                    select(Message).where(Message.conversation_id == conversation_id).order_by(Message.sequence)
                )
                history_rows = list(result.scalars().all())
                api_messages = _build_messages_from_history(history_rows)
                next_seq = (history_rows[-1].sequence + 1) if history_rows else 1
            else:
                conversation = Conversation(
                    title=message[:100],
                    model_key=settings.anthropic_model,
                    system_prompt=system_prompt,
                    user_id=user_id,
                    total_input_tokens=0,
                    total_output_tokens=0,
                    message_count=0,
                )
                db.add(conversation)
                await db.flush()
                api_messages = []
                next_seq = 1

            # 2. Persist the user message.
            user_msg = Message(
                conversation_id=conversation.id,
                role="user",
                content=message,
                sequence=next_seq,
            )
            db.add(user_msg)
            conversation.message_count = (conversation.message_count or 0) + 1
            await db.flush()
            next_seq += 1

            # 3. Append user message to API history.
            api_messages.append({"role": "user", "content": message})

            # 4. Emit conversation_id so the frontend can track it.
            yield _sse("conversation_id", {"conversation_id": str(conversation.id)})

            # 5. Launch agent loop in a thread.
            event_queue: queue.Queue[_QueueItem] = queue.Queue()
            tool_specs = [{k: v for k, v in s.items() if k != "category"} for s in get_tool_specs()]

            try:
                client = get_anthropic_client()
            except RuntimeError as exc:
                yield _sse("error", {"message": str(exc)})
                return

            loop = asyncio.get_event_loop()
            future = loop.run_in_executor(
                None,
                _run_agent_loop,
                event_queue,
                api_messages,
                tool_specs,
                client,
                settings.anthropic_model,
            )

            # 6. Stream SSE events from the queue.
            async for sse_event in _stream_from_queue(event_queue):
                yield sse_event

            # 7. Await the thread result.
            loop_result = await future

            # 8. Persist assistant messages + tool call audit rows.
            new_messages = loop_result.get("new_messages", [])
            tool_call_records = loop_result.get("tool_call_records", [])

            tool_use_id_map = await _persist_new_messages(db, conversation, new_messages, next_seq)
            await _persist_tool_calls(db, conversation.id, tool_call_records, tool_use_id_map)

            # 9. Auto-create experiments for successful generate_design calls,
            #    and attach evaluate_design output to the most recent
            #    experiment in this conversation.
            created_experiments: list[Any] = []
            for rec in tool_call_records:
                if rec.get("status") != "success":
                    continue
                if rec["tool_name"] == "generate_design":
                    experiment = await _create_experiment_from_design(
                        db, rec["tool_output"], conversation.id, user_id=user_id
                    )
                    created_experiments.append(experiment)
                elif rec["tool_name"] == "evaluate_design":
                    target = created_experiments[-1] if created_experiments else None
                    if target is None:
                        target = await get_latest_experiment_for_conversation(db, conversation.id)
                    if target is not None:
                        target.evaluation_data = rec["tool_output"]

            # Update cached message count.
            msg_count = len(new_messages)
            for m in new_messages:
                content = m.get("content", [])
                if isinstance(content, list):
                    msg_count += len(content) - 1  # each block is a row
            conversation.message_count = (conversation.message_count or 0) + msg_count

            await db.commit()

            # 10. Emit experiment_created events (after commit, so IDs are stable).
            for experiment in created_experiments:
                yield _sse(
                    "experiment_created",
                    {
                        "experiment_id": str(experiment.id),
                        "name": experiment.name,
                        "design_type": experiment.design_type,
                    },
                )

        except Exception:
            logger.exception("run_chat failed")
            await db.rollback()
            yield _sse("error", {"message": "Internal server error."})
