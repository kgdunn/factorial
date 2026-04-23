"""Render an experiment's analysis history into a runnable Python script.

factorial's agent produces numeric results by calling deterministic
``process_improve`` tools — not by generating numbers inside the LLM.
That makes results *in principle* reproducible, but users have no way
to verify that without re-running the exact same calls themselves.
This service closes the gap: the downloaded ``.py`` imports the same
``process_improve.tool_spec.execute_tool_call`` the backend uses and
dispatches each recorded step with the captured ``tool_input`` JSON.

This module implements the ``.py`` exporter only.  Notebook
(``.ipynb``) and literate-markdown (``.md_code``) renderers, plus the
``.zip`` bundle with a matching data file, land in follow-up PRs
tracked in the repo-root ``TODO.md``.
"""

from __future__ import annotations

import importlib.metadata
import json
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ToolCall
from app.models.experiment import Experiment

# Tools whose calls become steps in the exported script.  Everything
# else the agent invokes (simulator tools, chat-side utility calls) is
# intentionally dropped so the script reads as an analysis recipe, not
# a conversation transcript.
ANALYSIS_TOOLS: frozenset[str] = frozenset({"generate_design", "evaluate_design", "analyze_results"})


def _resolve_process_improve_version() -> str:
    """Return the installed ``process-improve`` version or ``"unknown"``."""
    try:
        return importlib.metadata.version("process-improve")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _sanitise_for_docstring(text: str) -> str:
    """Neutralise triple-quote sequences so the generated docstring stays intact."""
    return text.replace('"""', "'''")


async def fetch_analysis_tool_calls(
    db: AsyncSession,
    experiment: Experiment,
) -> list[ToolCall]:
    """Return the experiment's successful analysis tool calls, in order.

    Empty list if the experiment has no linked conversation.  Callers
    decide how to present that (the export entry point raises 400).
    """
    if experiment.conversation_id is None:
        return []

    stmt = (
        select(ToolCall)
        .where(
            ToolCall.conversation_id == experiment.conversation_id,
            ToolCall.tool_name.in_(ANALYSIS_TOOLS),
            ToolCall.status == "success",
        )
        .order_by(ToolCall.agent_turn, ToolCall.call_order)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def render_python_script(
    experiment: Experiment,
    calls: list[ToolCall],
    *,
    pi_version: str | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Emit a self-contained Python script that replays the analysis.

    The script imports ``process_improve.tool_spec.execute_tool_call``
    — the same dispatch the backend uses — and calls it with the
    captured ``tool_input`` for every step.  ``compile(..., "<gen>",
    "exec")`` must succeed on the returned string; tests assert that.
    """
    if not calls:
        raise ValueError("no analysis tool calls available for this experiment")

    version = pi_version or _resolve_process_improve_version()
    ts = (generated_at or datetime.now(UTC)).isoformat(timespec="seconds")
    safe_name = _sanitise_for_docstring(experiment.name or "Untitled Experiment")

    header = [
        f'"""Reproducible analysis for experiment: {safe_name}',
        "",
        f"Experiment ID  : {experiment.id}",
        f"Generated (UTC): {ts}",
        f"process-improve: {version}",
        "",
        "Re-run locally:",
        f'    pip install "process-improve=={version}"',
        "    python analysis.py",
        "",
        "Reproducibility scope: numeric tool outputs (coefficients, p-values,",
        "design matrix, etc.) will be identical to what the factorial agent",
        "showed. Plot images may differ in rendering (font / renderer drift).",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "from process_improve.tool_spec import execute_tool_call",
        "",
        "",
    ]

    step_lines: list[str] = []
    step_var_names: list[str] = []
    for i, call in enumerate(calls, start=1):
        var = f"step_{i}_{call.tool_name}"
        step_var_names.append(var)
        step_lines.append(f"# Step {i}: {call.tool_name} (agent_turn={call.agent_turn}, call_order={call.call_order})")
        payload = json.dumps(call.tool_input or {}, indent=4, sort_keys=True)
        step_lines.append(f"{var}_input = {payload}")
        step_lines.append(f'{var} = execute_tool_call("{call.tool_name}", {var}_input)')
        step_lines.append("")

    footer = [
        "",
        'if __name__ == "__main__":',
        f'    print("Reproduced {len(calls)} analysis step(s).")',
        *(f'    print("  - {name}:", type({name}).__name__)' for name in step_var_names),
        "",
    ]

    return "\n".join([*header, *step_lines, *footer])


async def build_python_script(
    db: AsyncSession,
    experiment: Experiment,
) -> bytes:
    """High-level entry point for the ``.py`` export endpoint.

    Raises :class:`HTTPException` with status 400 when the experiment
    has no successful analysis steps to reproduce.
    """
    calls = await fetch_analysis_tool_calls(db, experiment)
    if not calls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No analysis tool calls were found for this experiment. "
                "The .py export needs at least one successful "
                f"{'/'.join(sorted(ANALYSIS_TOOLS))} call."
            ),
        )
    source = render_python_script(experiment, calls)
    return source.encode("utf-8")
