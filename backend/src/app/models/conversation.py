"""SQLAlchemy models for conversation persistence.

Three models track the full lifecycle of agent conversations:

- **Conversation**: a chat session with metadata, token totals, and status.
- **Message**: individual messages (user text, assistant text, tool_use blocks,
  tool_result entries) ordered by ``sequence`` within a conversation.
- **ToolCall**: per-invocation audit trail capturing tool name, timing,
  input/output, and ordering within the agent loop.
"""

from __future__ import annotations

import uuid

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Conversation(Base):
    """A chat conversation between a user and the DOE agent."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    model_key: Mapped[str] = mapped_column(String(100), default="")
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Token tracking
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    message_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    # Organisation
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    starred: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        order_by="Message.sequence",
        cascade="all, delete-orphan",
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
    )


class Message(Base):
    """A single message (or content block) within a conversation.

    Stores user text, assistant text, tool_use blocks, and tool_result
    entries.  The ``sequence`` column determines ordering.  Tool-related
    fields (``tool_use_id``, ``tool_name``, ``tool_input``) are populated
    for assistant tool_use blocks and their corresponding tool_result
    entries.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, default="")
    sequence: Mapped[int] = mapped_column(Integer)

    # Tool-use fields (nullable — only set for tool_use / tool_result blocks)
    tool_use_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_tool_result: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    # Per-message metrics
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stop_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class ToolCall(Base):
    """Audit trail for individual tool invocations.

    Captures tool name, timing, input/output, success/failure, and
    ordering within the agent loop so tool usage can be analysed
    from day one.
    """

    __tablename__ = "tool_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_use_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Tool identity
    tool_name: Mapped[str] = mapped_column(String(100))
    tool_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Outcome
    status: Mapped[str] = mapped_column(String(20), default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timing
    started_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Ordering within the agent loop
    agent_turn: Mapped[int] = mapped_column(Integer, default=1)
    call_order: Mapped[int] = mapped_column(Integer, default=1)

    # Timestamps
    created_at: Mapped[str] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    conversation: Mapped[Conversation] = relationship(back_populates="tool_calls")
