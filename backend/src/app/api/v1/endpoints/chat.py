"""Chat endpoint — streams agent responses via SSE."""

from __future__ import annotations

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.schemas.chat import ChatRequest
from app.services.agent_service import run_chat

router = APIRouter()


@router.post("")
async def chat(request: ChatRequest) -> EventSourceResponse:
    """Start or continue a conversation with the DOE agent.

    Accepts a user message and optional ``conversation_id``.
    Returns an SSE stream with events: ``conversation_id``, ``token``,
    ``tool_start``, ``tool_result``, ``done``, and ``error``.
    """
    return EventSourceResponse(run_chat(request.message, request.conversation_id))
