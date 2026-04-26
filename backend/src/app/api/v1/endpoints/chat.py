"""Chat endpoint — streams agent responses via SSE."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.api.deps import AuthUser, require_auth
from app.api.rate_limit import limiter
from app.config import settings
from app.db.session import async_session_factory, get_db_session
from app.models.conversation import ChatEvent, Conversation, Message
from app.models.session import Session as SessionRow
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services import byok_session_service
from app.services.agent_service import run_chat
from app.services.byok_service import BYOKConfigurationError, BYOKDecryptionError

logger = logging.getLogger(__name__)

router = APIRouter()


async def _resolve_byok_token(current_user: AuthUser) -> str | None:
    """Fetch the user's plaintext Anthropic API token for this session.

    Returns ``None`` for users without an active enrollment, when the
    session row lacks the required wraps (e.g. the user has not signed
    in since enrolling), or when BYOK is misconfigured. The chat path
    falls back to the platform key in any of those cases — chat must
    keep working even if the optional BYOK feature is degraded.

    Token plaintext exists only inside this function and the returned
    string; the agent layer hands it to the Anthropic SDK and lets it
    fall out of scope at end-of-turn.
    """
    if current_user.session_id is None:
        return None
    try:
        async with async_session_factory() as db:
            user = await db.get(User, current_user.id)
            session_row = await db.get(SessionRow, current_user.session_id)
            if user is None or session_row is None:
                return None
            return byok_session_service.decrypt_token_for_request(user, session_row)
    except BYOKDecryptionError:
        # Common path: status='absent' or session has no BYOK wraps.
        # Not an error — the user just doesn't have BYOK on this session.
        return None
    except BYOKConfigurationError:
        logger.exception("BYOK token resolution failed: master key misconfigured (user=%s)", current_user.id)
        return None


# Event types that indicate the turn reached a terminal state. A replay
# that ends with one of these needs no further ``interrupted`` marker —
# the turn really is over.
_TERMINAL_EVENT_TYPES = frozenset({"done", "error"})


@router.post("")
@limiter.limit(settings.chat_rate_limit)
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: AuthUser = Depends(require_auth),
) -> EventSourceResponse:
    """Start or continue a conversation with the DOE agent.

    Accepts a user message and optional ``conversation_id``.
    Returns an SSE stream with events: ``conversation_id``, ``token``,
    ``tool_start``, ``tool_result``, ``done``, and ``error``.
    """
    byok_token = await _resolve_byok_token(current_user)
    return EventSourceResponse(
        run_chat(
            body.message,
            body.conversation_id,
            user_id=current_user.id,
            user_background=current_user.background,
            detail_level=body.detail_level,
            byok_token=byok_token,
        )
    )


def _parse_last_event_id(raw: str | None) -> tuple[uuid.UUID, int] | None:
    """Parse a ``Last-Event-ID`` header value of the form ``{turn_id}:{seq}``.

    Returns ``None`` when the header is missing or malformed.
    """
    if not raw:
        return None
    try:
        turn_part, seq_part = raw.split(":", 1)
        return uuid.UUID(turn_part), int(seq_part)
    except (ValueError, AttributeError):
        return None


@router.get("/{conversation_id}/resume")
async def resume_chat(
    conversation_id: uuid.UUID,
    current_user: AuthUser = Depends(require_auth),
    turn_id: uuid.UUID | None = Query(
        None,
        description="Specific turn to resume. Defaults to the most recent turn.",
    ),
    last_event_id: str | None = Header(
        None,
        alias="Last-Event-ID",
        description="Standard SSE reconnect header — echoed back by the browser EventSource.",
    ),
) -> EventSourceResponse:
    """Replay persisted SSE events for a dropped chat stream.

    Resolution order for the target turn:

    1. If ``Last-Event-ID`` is present and parseable, use the ``turn_id``
       embedded in it and replay events with ``sequence`` strictly
       greater than the embedded sequence.
    2. Otherwise if the ``turn_id`` query parameter is given, replay the
       whole of that turn.
    3. Otherwise, replay the most recent turn for the conversation.

    If the replayed turn does not end with a terminal event
    (``done`` / ``error``), a synthetic ``interrupted`` event is emitted
    so the client can render a "stream cut off — retry?" state instead
    of spinning forever.
    """
    parsed = _parse_last_event_id(last_event_id)

    async with async_session_factory() as db:
        conversation = await db.get(Conversation, conversation_id)
        if not conversation or conversation.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Conversation not found")

        resolved_turn_id: uuid.UUID | None
        after_sequence: int
        if parsed is not None:
            resolved_turn_id, after_sequence = parsed
        elif turn_id is not None:
            resolved_turn_id, after_sequence = turn_id, 0
        else:
            # Most recent turn: pick the latest ``created_at`` among this
            # conversation's events.
            latest = await db.execute(
                select(ChatEvent.turn_id)
                .where(ChatEvent.conversation_id == conversation_id)
                .order_by(desc(ChatEvent.created_at))
                .limit(1)
            )
            resolved_turn_id = latest.scalar_one_or_none()
            after_sequence = 0
            if resolved_turn_id is None:
                raise HTTPException(status_code=404, detail="No turns to resume")

    return EventSourceResponse(_replay_events(conversation_id, resolved_turn_id, after_sequence))


async def _replay_events(
    conversation_id: uuid.UUID,
    turn_id: uuid.UUID,
    after_sequence: int,
) -> AsyncGenerator[ServerSentEvent, None]:
    """Yield persisted ``chat_events`` rows as SSE events.

    The stream closes naturally if the turn's last persisted event is
    terminal (``done`` / ``error``); otherwise an ``interrupted`` event
    is emitted so the client can show a clear "stream interrupted"
    state and let the user retry.
    """
    async with async_session_factory() as db:
        result = await db.execute(
            select(ChatEvent)
            .where(
                ChatEvent.conversation_id == conversation_id,
                ChatEvent.turn_id == turn_id,
                ChatEvent.sequence > after_sequence,
            )
            .order_by(ChatEvent.sequence)
        )
        rows: list[ChatEvent] = list(result.scalars().all())

        last_event_type: str | None = None
        for row in rows:
            last_event_type = row.event_type
            yield ServerSentEvent(
                data=json.dumps(row.data),
                event=row.event_type,
                id=f"{row.turn_id}:{row.sequence}",
            )

        # If the caller had missed nothing new but the turn was already
        # terminal, we still want to let them know cleanly.
        if not rows:
            # Probe the very last known sequence to decide what to emit.
            probe = await db.execute(
                select(ChatEvent.event_type)
                .where(ChatEvent.turn_id == turn_id)
                .order_by(desc(ChatEvent.sequence))
                .limit(1)
            )
            last_event_type = probe.scalar_one_or_none()

        if last_event_type is None:
            # Nothing is persisted for this turn — treat it like an
            # interrupted turn so the client doesn't hang.
            yield ServerSentEvent(
                data=json.dumps({"message": "No events found for this turn."}),
                event="interrupted",
            )
            return

        if last_event_type not in _TERMINAL_EVENT_TYPES:
            yield ServerSentEvent(
                data=json.dumps(
                    {
                        "message": (
                            "The chat stream was interrupted before completing. "
                            "You can retry the last message to regenerate the response."
                        )
                    }
                ),
                event="interrupted",
            )


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: AuthUser = Depends(require_auth),
) -> dict[str, Any]:
    """Load conversation messages for resuming a chat session.

    Returns messages formatted as the frontend's ``ChatMessage[]``
    structure with content blocks (text, tool_use, tool_result).
    """
    conversation = await db.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if current_user.id != conversation.user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.sequence)
    )
    rows = list(result.scalars().all())

    # Group message rows into frontend ChatMessage objects.
    messages: list[dict[str, Any]] = []
    current_msg: dict[str, Any] | None = None
    current_role: str | None = None

    for row in rows:
        # Determine the effective role for grouping.
        role = "tool_result_group" if row.is_tool_result else row.role

        # Start a new message group on role change.
        if role != current_role:
            if current_msg:
                messages.append(current_msg)
            current_role = role
            display_role = "assistant" if role == "tool_result_group" else role
            current_msg = {
                "id": str(row.id),
                "role": display_role,
                "content": [],
                "timestamp": row.created_at.isoformat() if row.created_at else None,
            }

        if current_msg is None:
            continue

        # Build the content block.
        if row.is_tool_result:
            current_msg["content"].append(
                {
                    "type": "tool_result",
                    "toolUseId": row.tool_use_id or "",
                    "toolName": row.tool_name or "",
                    "output": _parse_tool_content(row.content),
                    "isError": False,
                }
            )
        elif row.tool_name and row.role == "assistant":
            current_msg["content"].append(
                {
                    "type": "tool_use",
                    "id": row.tool_use_id or "",
                    "name": row.tool_name,
                    "input": row.tool_input or {},
                    "isLoading": False,
                }
            )
        else:
            text = row.content or ""
            if text:
                current_msg["content"].append({"type": "text", "text": text})

    if current_msg:
        messages.append(current_msg)

    # Conversation-level BYOK flag: true if any persisted Message in
    # this conversation was billed against a user-supplied Anthropic
    # key. Surfaced to the chat UI as a small "using your own key"
    # badge so users can tell at a glance which conversations bypassed
    # the platform markup. Cheap to compute since byok_used is already
    # on every Message row.
    byok_used = any(getattr(row, "byok_used", False) for row in rows)

    return {
        "conversation_id": str(conversation.id),
        "title": conversation.title,
        "messages": messages,
        "byok_used": byok_used,
    }


def _parse_tool_content(content: str) -> dict[str, Any]:
    """Try to parse tool result content as JSON, falling back to a text dict."""
    try:
        return json.loads(content)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        return {"text": content}
