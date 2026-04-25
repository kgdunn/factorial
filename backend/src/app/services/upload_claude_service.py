"""Claude integration for the DOE upload flow.

Hands a parsed 2D matrix to Claude and asks it to either return a
fully-populated :class:`ParsedDesignPayload` or a list of
:class:`ClarifyingQuestion`. We never accept free-text answers — both
paths go through forced ``tool_use`` so the response is always a
typed JSON object we can validate.

This module is async; the existing :func:`get_anthropic_client`
returns the sync SDK, so we run a single ``messages.create`` call on
the executor thread via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import anthropic
from pydantic import ValidationError

from app.config import settings
from app.schemas.uploads import (
    MAX_CLARIFYING_QUESTIONS,
    ClarifyingQuestion,
    ParsedDesignPayload,
)
from app.services.agent_service import get_anthropic_client

logger = logging.getLogger(__name__)


class UploadClaudeError(RuntimeError):
    """Claude returned a malformed response or no tool call at all."""


SYSTEM_PROMPT = (
    "You are a data-shape recogniser for Design of Experiments uploads. "
    "The user gives you a 2D matrix from an Excel or CSV file. Determine: "
    "(1) orientation — does each ROW represent one experiment, or each COLUMN; "
    "(2) factor names and ranges (low / high for continuous, levels for categorical); "
    "(3) response/outcome columns (which goal: maximize / minimize / target if obvious from the name); "
    "(4) which rows already have run results filled in. "
    "Be conservative: if ANY column heading is ambiguous (could be a factor or a response), "
    "or the units are unclear, or you cannot tell continuous vs categorical, ASK "
    f"using `ask_clarifying_questions` (max {MAX_CLARIFYING_QUESTIONS} questions). "
    "When confident, return the canonical structure via `report_design_structure`. "
    "Always pick exactly one of the two tools — never reply with prose."
)


# ---------------------------------------------------------------------------
# Tool specs
# ---------------------------------------------------------------------------

_FACTOR_SCHEMA = {
    "type": "object",
    "required": ["name"],
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string", "enum": ["continuous", "categorical", "mixture"]},
        "low": {"type": ["number", "null"]},
        "high": {"type": ["number", "null"]},
        "levels": {"type": ["array", "null"], "items": {}},
        "units": {"type": ["string", "null"]},
    },
}

_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["name"],
    "properties": {
        "name": {"type": "string"},
        "goal": {"type": ["string", "null"], "enum": ["maximize", "minimize", "target", None]},
        "units": {"type": ["string", "null"]},
    },
}

REPORT_TOOL: dict[str, Any] = {
    "name": "report_design_structure",
    "description": "Return the parsed design structure when no clarification is needed.",
    "input_schema": {
        "type": "object",
        "required": ["orientation", "factors", "design_actual"],
        "properties": {
            "orientation": {"type": "string", "enum": ["rows", "columns"]},
            "factors": {"type": "array", "items": _FACTOR_SCHEMA},
            "responses": {"type": "array", "items": _RESPONSE_SCHEMA},
            "design_actual": {
                "type": "array",
                "items": {"type": "object"},
                "description": "One object per run, keyed by factor (and response) name.",
            },
            "results_data": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Subset of design_actual rows where response columns were filled in.",
            },
        },
    },
}

ASK_TOOL: dict[str, Any] = {
    "name": "ask_clarifying_questions",
    "description": (
        "Ask the user up to "
        f"{MAX_CLARIFYING_QUESTIONS} clarifying questions when the file's "
        "structure is ambiguous. Each question must have a stable id (q1, q2, ...)."
    ),
    "input_schema": {
        "type": "object",
        "required": ["questions"],
        "properties": {
            "questions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["id", "question"],
                    "properties": {
                        "id": {"type": "string"},
                        "question": {"type": "string"},
                        "options": {"type": ["array", "null"], "items": {"type": "string"}},
                        "column_ref": {"type": ["string", "null"]},
                    },
                },
            }
        },
    },
}


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


async def discover_structure(
    raw_rows: list[list[Any]],
    *,
    prior_questions: list[ClarifyingQuestion] | None = None,
    prior_answers: dict[str, str] | None = None,
) -> ParsedDesignPayload | list[ClarifyingQuestion]:
    """Ask Claude to parse ``raw_rows`` into a design structure.

    On the second round-trip (when ``prior_answers`` is set), the user
    message includes the previous Q&A so Claude commits to
    ``report_design_structure`` rather than asking again.
    """

    user_message = _build_user_message(raw_rows, prior_questions, prior_answers)

    response = await asyncio.to_thread(_call_claude, user_message)

    return _interpret_response(response)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _call_claude(user_message: str) -> anthropic.types.Message:
    client = get_anthropic_client()
    return client.messages.create(
        model=settings.anthropic_model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[REPORT_TOOL, ASK_TOOL],
        tool_choice={"type": "any"},
        messages=[{"role": "user", "content": user_message}],
    )


def _build_user_message(
    raw_rows: list[list[Any]],
    prior_questions: list[ClarifyingQuestion] | None,
    prior_answers: dict[str, str] | None,
) -> str:
    parts = [
        "Here is the 2D matrix extracted from the user's file (JSON-encoded, with `null` for empty cells):",
        "",
        "```json",
        json.dumps(raw_rows, default=str),
        "```",
    ]

    if prior_questions and prior_answers:
        parts.extend(
            [
                "",
                "## Previous Q&A",
                "",
                "I already asked the user these clarifying questions and they answered.",
                "Use these answers to commit to a final structure now — do NOT ask again.",
                "",
            ]
        )
        for q in prior_questions:
            answer = prior_answers.get(q.id, "(no answer)")
            parts.append(f"- **{q.id}**: {q.question} → `{answer}`")
        parts.append("")
        parts.append("Now call `report_design_structure` with the resolved structure.")

    return "\n".join(parts)


def _interpret_response(
    response: anthropic.types.Message,
) -> ParsedDesignPayload | list[ClarifyingQuestion]:
    if response.stop_reason != "tool_use":
        raise UploadClaudeError(  # noqa: TRY003
            f"Expected tool_use response from Claude, got stop_reason={response.stop_reason!r}"
        )

    for block in response.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        if block.name == REPORT_TOOL["name"]:
            return _validate_report(block.input)
        if block.name == ASK_TOOL["name"]:
            return _validate_questions(block.input)

    raise UploadClaudeError("Claude did not invoke a known tool.")  # noqa: TRY003


def _validate_report(payload: Any) -> ParsedDesignPayload:
    try:
        return ParsedDesignPayload.model_validate(payload)
    except ValidationError as exc:
        logger.warning("Claude returned an invalid report_design_structure payload: %s", exc)
        raise UploadClaudeError(  # noqa: TRY003
            "Claude returned a malformed structure. Try uploading the file again."
        ) from exc


def _validate_questions(payload: Any) -> list[ClarifyingQuestion]:
    try:
        questions_raw = payload.get("questions") if isinstance(payload, dict) else None
        if not isinstance(questions_raw, list) or not questions_raw:
            raise ValueError("missing `questions` array")  # noqa: TRY003,TRY301
        return [ClarifyingQuestion.model_validate(q) for q in questions_raw[:MAX_CLARIFYING_QUESTIONS]]
    except (ValidationError, ValueError) as exc:
        logger.warning("Claude returned an invalid ask_clarifying_questions payload: %s", exc)
        raise UploadClaudeError(  # noqa: TRY003
            "Claude returned malformed questions. Try uploading the file again."
        ) from exc
