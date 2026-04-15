"""Chat endpoint — streams agent responses via SSE."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.rate_limit import limiter
from app.config import settings
from app.db.session import get_db_session
from app.models.conversation import Conversation, Message
from app.schemas.chat import ChatRequest
from app.services.agent_service import run_chat

router = APIRouter()


@router.post("")
@limiter.limit(settings.chat_rate_limit)
async def chat(request: Request, body: ChatRequest) -> EventSourceResponse:
    """Start or continue a conversation with the DOE agent.

    Accepts a user message and optional ``conversation_id``.
    Returns an SSE stream with events: ``conversation_id``, ``token``,
    ``tool_start``, ``tool_result``, ``done``, and ``error``.
    """
    return EventSourceResponse(run_chat(body.message, body.conversation_id))


@router.get("/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Load conversation messages for resuming a chat session.

    Returns messages formatted as the frontend's ``ChatMessage[]``
    structure with content blocks (text, tool_use, tool_result).
    """
    conversation = await db.get(Conversation, conversation_id)
    if not conversation:
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

    return {
        "conversation_id": str(conversation.id),
        "title": conversation.title,
        "messages": messages,
    }


def _parse_tool_content(content: str) -> dict[str, Any]:
    """Try to parse tool result content as JSON, falling back to a text dict."""
    import json

    try:
        return json.loads(content)  # type: ignore[no-any-return]
    except (json.JSONDecodeError, TypeError):
        return {"text": content}
