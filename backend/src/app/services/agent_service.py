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
import uuid
from collections.abc import AsyncGenerator
from decimal import Decimal
from typing import Any

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import ServerSentEvent

from app.config import settings
from app.db.session import async_session_factory
from app.models.conversation import ChatEvent, Conversation, Message, ToolCall
from app.services.agent_loop import _run_agent_loop
from app.services.experiment_service import (
    create_experiment,
    get_latest_experiment_for_conversation,
)
from app.services.simulator_interception import RevealCounts, SimulatorStates
from app.services.simulator_service import (
    create_simulator_record,
    list_simulators_for_conversation,
    set_reveal_request_count,
)
from app.services.tools import get_tool_specs

logger = logging.getLogger(__name__)


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
3. Use the available tools to create designs or analyse results — do not \
   fabricate numerical outputs yourself.
4. Whenever ``generate_design`` succeeds, immediately call \
   ``evaluate_design`` on the same design before showing the matrix to \
   the user. Summarise the resolution, the confounding/aliasing of main \
   effects and 2-factor interactions, the D- and I-efficiency, and the \
   power per main effect for the assumed noise level. If the user has \
   not supplied an expected residual standard deviation (σ) or a \
   minimum practical effect size, ask for them before calling \
   ``evaluate_design``.
5. Explain results in plain language, highlighting which factors matter \
   and what to do next.

Always explain your reasoning before calling a tool, and summarise the \
results after receiving tool output.

Fake-data simulators. If the user wants synthetic but realistic data \
to plan or demonstrate an experiment, first propose a reasonable set \
of factors (with ranges from your domain knowledge) and responses, \
confirm with the user, and only then call ``create_simulator``. Use \
``simulate_process`` to evaluate the simulator at specific settings; \
outputs will differ slightly between identical calls (that is noise, \
not a bug). Never paraphrase or guess the hidden model: if the user \
asks to see it, call ``reveal_simulator``. The system will refuse the \
first request with a confirmation prompt — surface it verbatim — and \
reveal the model on the second request.

Planning protocol. The user's chat UI renders a live checklist of what \
you are doing so the response does not feel stuck during long calls. \
You communicate that checklist through two meta-tools:

- For any request that needs at least one tool call OR multi-step \
  reasoning, your FIRST action is to call ``record_plan`` with 2-5 \
  short imperative steps describing what you will do. Steps must be \
  concrete (e.g. "Generate the 2² factorial design", "Evaluate \
  confounding and power") rather than generic ("Help the user").
- Before each subsequent tool call, call ``update_plan`` to mark the \
  active step ``in_progress``. After the tool returns, call \
  ``update_plan`` again to mark it ``completed``. You may batch \
  transitions in a single ``update_plan`` call (e.g. mark step 0 \
  ``completed`` and step 1 ``in_progress`` together).
- Skip ``record_plan`` entirely for trivial replies: greetings, \
  one-sentence clarifications, confirmations, or pure follow-up \
  questions back to the user. Planning overhead is not worth it for \
  these.
- The plan is metadata for the UI; it does not replace your normal \
  textual reply. Continue to write your usual prose response and call \
  the real tools (``generate_design``, ``evaluate_design``, etc.) as \
  before.
"""

# Role slugs come from the admin-managed ``roles`` table. They're
# validated against this regex before being interpolated into the system
# prompt so a tampered DB row can't inject prompt content.
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


def _sse(event: str, data: dict[str, Any], event_id: str | None = None) -> ServerSentEvent:
    """Create a ``ServerSentEvent`` with a JSON-serialised data payload.

    When ``event_id`` is provided it becomes the SSE ``id:`` field, which
    the browser echoes back as ``Last-Event-ID`` on automatic reconnect.
    """
    return ServerSentEvent(data=json.dumps(data), event=event, id=event_id)


async def _persist_chat_event(
    conversation_id: uuid.UUID,
    turn_id: uuid.UUID,
    sequence: int,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Append one SSE event row to ``chat_events`` in its own session.

    Uses an independent session so event persistence is committed
    immediately and is visible to any other container that serves a
    resume request (important for blue-green cutovers).

    Persistence failures are swallowed — the live SSE stream must not
    die just because the resume log is unavailable.
    """
    try:
        async with async_session_factory() as db:
            db.add(
                ChatEvent(
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    sequence=sequence,
                    event_type=event_type,
                    data=data,
                )
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to persist chat_event seq=%s turn=%s", sequence, turn_id)


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
            turn_id=rec.get("turn_id"),
            model_key=rec.get("model_key"),
            rss_bytes=rec.get("rss_bytes"),
            cpu_percent=rec.get("cpu_percent"),
            input_bytes=rec.get("input_bytes"),
            output_bytes=rec.get("output_bytes"),
            output_truncated=rec.get("output_truncated", False),
            tool_version=rec.get("tool_version"),
        )
        db.add(tc)


# ---------------------------------------------------------------------------
# Auto-save helper
# ---------------------------------------------------------------------------


async def _create_experiment_from_design(
    db: AsyncSession,
    design_output: dict[str, Any],
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Any:  # noqa: ANN401
    """Create an Experiment record from a successful generate_design output."""
    return await create_experiment(db, design_output=design_output, conversation_id=conversation_id, user_id=user_id)


_DETAIL_LEVEL_CLAUSES: dict[str, str] = {
    "beginner": (
        "Response style: the user is new to Design of Experiments. Explain "
        "concepts in plain language, define technical terms the first time "
        "you use them, walk through your reasoning step by step, and prefer "
        "worked examples over abstract rules."
    ),
    "intermediate": "",
    "expert": (
        "Response style: the user is a DOE expert. Be concise. Skip basic "
        "definitions and reasoning the user can reconstruct. Focus on the "
        "result, non-obvious caveats, and any assumptions you had to make. "
        "No preamble, no recap."
    ),
}


def _build_system_prompt(user_background: str | None, detail_level: str = "intermediate") -> str:
    """Build the system prompt, optionally personalised with user background and detail level.

    The ``user_background`` value is validated against an allowlist to
    prevent prompt injection via the user profile field. ``detail_level``
    is looked up against a fixed set of clauses; any unknown value falls
    back to ``intermediate`` (which appends nothing).
    """
    prompt = SYSTEM_PROMPT
    if user_background and _ALLOWED_BACKGROUND_RE.match(user_background):
        bg_label = user_background.replace("_", " ")
        prompt = (
            f"{prompt}\n\n"
            f"The user's background: {bg_label}. "
            f"Tailor your explanations, terminology, and examples to this domain."
        )
    detail_clause = _DETAIL_LEVEL_CLAUSES.get(detail_level, "")
    if detail_clause:
        prompt = f"{prompt}\n\n{detail_clause}"
    return prompt


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------


async def run_chat(
    message: str,
    conversation_id: uuid.UUID | None,
    user_id: uuid.UUID,
    user_background: str | None = None,
    detail_level: str = "intermediate",
) -> AsyncGenerator[ServerSentEvent, None]:
    """Orchestrate a chat turn: load history, run agent loop, persist, stream SSE.

    The DB session is managed inside the generator (not via ``Depends``)
    so its lifetime matches the SSE stream.

    Every SSE event yielded by this generator carries an ``id:`` of the
    form ``{turn_id}:{sequence}`` and is persisted to ``chat_events``
    before being yielded, so a disconnected client can replay missed
    events via the resume endpoint using the standard SSE
    ``Last-Event-ID`` header.
    """
    system_prompt = _build_system_prompt(user_background, detail_level)

    # One ``turn_id`` per ``run_chat`` invocation. Shared across all
    # SSE events emitted during this turn so the resume endpoint can
    # scope its replay cleanly.
    turn_id = uuid.uuid4()
    event_seq = 0

    async with async_session_factory() as db:
        try:
            # 1. Load or create conversation.
            if conversation_id:
                conversation = await db.get(Conversation, conversation_id)
                if not conversation:
                    # Pre-conversation error — nothing to persist into
                    # ``chat_events``; client can't resume a turn that
                    # never existed.
                    yield _sse("error", {"message": f"Conversation {conversation_id} not found."})
                    return
                if conversation.user_id != user_id:
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

            # 2. Persist the user message. Committed eagerly so that
            #    (a) the user's turn is durable even if the agent loop
            #    later crashes, and (b) ``chat_events`` rows written
            #    from their own sessions below can satisfy the FK to
            #    ``conversations.id``.
            user_msg = Message(
                conversation_id=conversation.id,
                role="user",
                content=message,
                sequence=next_seq,
            )
            db.add(user_msg)
            conversation.message_count = (conversation.message_count or 0) + 1
            await db.commit()
            next_seq += 1

            # 3. Append user message to API history.
            api_messages.append({"role": "user", "content": message})

            # Helper that assigns the next sequence, persists the event
            # to ``chat_events`` in a side session, and returns the
            # ``ServerSentEvent`` ready to yield.
            async def emit(event_type: str, data: dict[str, Any]) -> ServerSentEvent:
                nonlocal event_seq
                event_seq += 1
                await _persist_chat_event(conversation.id, turn_id, event_seq, event_type, data)
                return _sse(event_type, data, event_id=f"{turn_id}:{event_seq}")

            # 4. Emit conversation_id + the turn_id so the frontend can
            #    construct a resume URL without guessing.
            yield await emit(
                "conversation_id",
                {"conversation_id": str(conversation.id), "turn_id": str(turn_id)},
            )

            # 5. Pre-load existing simulators for this conversation so their
            #    hidden private_state can be injected into simulate_process /
            #    reveal_simulator calls without an async round-trip from the
            #    worker thread.
            existing_sims = await list_simulators_for_conversation(db, conversation.id)
            simulator_states: SimulatorStates = {sim.sim_id: dict(sim.private_state) for sim in existing_sims}
            reveal_counts: RevealCounts = {sim.sim_id: int(sim.reveal_request_count) for sim in existing_sims}
            newly_created_sims: list[dict[str, Any]] = []

            # 6. Launch agent loop in a thread.
            event_queue: queue.Queue[_QueueItem] = queue.Queue()
            tool_specs = [{k: v for k, v in s.items() if k != "category"} for s in get_tool_specs()]

            try:
                client = get_anthropic_client()
            except RuntimeError as exc:
                yield await emit("error", {"message": str(exc)})
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
                turn_id,
                system_prompt,
                simulator_states,
                reveal_counts,
                newly_created_sims,
                settings.simulator_reveal_force,
            )

            # 6. Stream SSE events from the queue — persist each one
            #    before yielding so the resume log is always at least as
            #    advanced as what the client has received.
            async for sse_event in _stream_from_queue(event_queue):
                payload = json.loads(sse_event.data) if sse_event.data else {}
                yield await emit(sse_event.event or "message", payload)

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

            # Persist newly-created simulators and refresh reveal counts on
            # pre-existing ones so the double-confirm gate carries across
            # turns in the same conversation.
            created_sim_rows = []
            for sim_info in newly_created_sims:
                row = await create_simulator_record(
                    db,
                    sim_id=sim_info["sim_id"],
                    public_summary=sim_info["public_summary"],
                    private_state=sim_info["private_state"],
                    user_id=user_id,
                    conversation_id=conversation.id,
                )
                created_sim_rows.append(row)

            existing_by_id = {sim.sim_id: sim for sim in existing_sims}
            for sim_id, count in reveal_counts.items():
                prev = existing_by_id.get(sim_id)
                if prev is not None and int(prev.reveal_request_count) != count:
                    await set_reveal_request_count(db, sim_id, user_id, count)

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
                yield await emit(
                    "experiment_created",
                    {
                        "experiment_id": str(experiment.id),
                        "name": experiment.name,
                        "design_type": experiment.design_type,
                    },
                )

            # 11. Emit simulator_created events for newly persisted simulators.
            for sim_row in created_sim_rows:
                yield await emit(
                    "simulator_created",
                    {
                        "simulator_id": str(sim_row.id),
                        "sim_id": sim_row.sim_id,
                    },
                )

        except Exception:
            logger.exception("run_chat failed")
            await db.rollback()
            # Attempt a persisted error event so a reconnecting client
            # sees the turn ended in failure rather than looping forever.
            try:
                yield await emit("error", {"message": "Internal server error."})
            except Exception:
                yield _sse("error", {"message": "Internal server error."})
