"""Render an experiment's analysis history into runnable reproducible code.

factorial's agent produces numeric results by calling deterministic
``process_improve`` tools — not by generating numbers inside the LLM.
That makes results *in principle* reproducible, but users have no way
to verify that without re-running the exact same calls themselves.
This service closes the gap: every exported artifact imports the same
``process_improve.tool_spec.execute_tool_call`` the backend uses and
dispatches each recorded step with the captured ``tool_input`` JSON.

Three code formats and a bundle sit on top of one shared step-extraction
pipeline so the ``.py`` / ``.ipynb`` / ``.md_code`` renderings stay
internally consistent — the same function calls, the same JSON inputs,
the same ordering.  The ``.zip`` bundle packages all three plus an
``xlsx`` data snapshot and a pinned ``requirements.txt`` so a user can
pip-install and re-run offline.
"""

from __future__ import annotations

import importlib.metadata
import io
import json
import zipfile
from datetime import UTC, datetime
from typing import Any

import nbformat
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ToolCall
from app.models.experiment import Experiment
from app.services import export_service
from app.services.export_service import _jinja_env

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
    calls = await _fetch_or_400(db, experiment, format_name=".py")
    return render_python_script(experiment, calls).encode("utf-8")


# ---------------------------------------------------------------------------
# Shared pre-rendering used by the notebook + literate-markdown renderers.
# ---------------------------------------------------------------------------


def _step_blocks(calls: list[ToolCall]) -> list[dict[str, Any]]:
    """Pre-render the per-step pieces that ``.ipynb`` and ``.md_code`` share.

    Each entry carries the step number, tool metadata, and two
    pre-formatted source strings — the ``step_N_<tool>_input = {...}``
    literal and the matching ``execute_tool_call(...)`` line — so the
    notebook cells and the literate-markdown fenced blocks can stay
    identical without re-implementing the JSON formatting.
    """
    blocks: list[dict[str, Any]] = []
    for i, call in enumerate(calls, start=1):
        var = f"step_{i}_{call.tool_name}"
        input_literal = json.dumps(call.tool_input or {}, indent=4, sort_keys=True)
        code = f'{var}_input = {input_literal}\n{var} = execute_tool_call("{call.tool_name}", {var}_input)'
        blocks.append(
            {
                "index": i,
                "tool_name": call.tool_name,
                "agent_turn": call.agent_turn,
                "call_order": call.call_order,
                "var_name": var,
                "input_literal": input_literal,
                "code": code,
            }
        )
    return blocks


# ---------------------------------------------------------------------------
# Warnings surfaced in the bundle README.
# ---------------------------------------------------------------------------

_DESIGN_SEED_KEYS = frozenset({"seed", "random_state", "random_seed"})


def collect_warnings(calls: list[ToolCall]) -> list[str]:
    """Inspect ToolCall rows for things that threaten bit-for-bit reproducibility.

    Emits one line per issue for inclusion in the bundle's ``README.md``.
    Kept small and deterministic so tests can assert on exact strings.
    """
    warnings: list[str] = []
    for call in calls:
        tool_input = call.tool_input or {}
        if call.tool_name == "generate_design" and not _DESIGN_SEED_KEYS & set(tool_input):
            warnings.append(
                f"Step {call.agent_turn}.{call.call_order} (generate_design): "
                "no seed / random_state captured — any randomised run-order "
                "is expected to differ on re-run. Tracked in TODO.md."
            )
        if getattr(call, "output_truncated", False):
            warnings.append(
                f"Step {call.agent_turn}.{call.call_order} ({call.tool_name}): "
                "tool_output was truncated server-side; reproducibility of "
                "this step is not guaranteed."
            )
    return warnings


# ---------------------------------------------------------------------------
# Notebook renderer.
# ---------------------------------------------------------------------------


def render_notebook(
    experiment: Experiment,
    calls: list[ToolCall],
    *,
    pi_version: str | None = None,
    generated_at: datetime | None = None,
) -> bytes:
    """Emit a Jupyter ``.ipynb`` that replays the analysis step by step.

    Structure: header markdown, a setup code cell, then alternating
    ``## Step i`` markdown + code cell per recorded call, then a short
    footer. ``nbformat.validate`` must pass on the result; tests assert
    this.
    """
    if not calls:
        raise ValueError("no analysis tool calls available for this experiment")

    version = pi_version or _resolve_process_improve_version()
    ts = (generated_at or datetime.now(UTC)).isoformat(timespec="seconds")
    blocks = _step_blocks(calls)

    nb = nbformat.v4.new_notebook()
    nb.cells.append(
        nbformat.v4.new_markdown_cell(
            "\n".join(
                [
                    f"# Reproducible analysis: {experiment.name or 'Untitled Experiment'}",
                    "",
                    f"- **Experiment ID**: `{experiment.id}`",
                    f"- **Generated (UTC)**: `{ts}`",
                    f"- **process-improve**: `{version}`",
                    "",
                    "Install the pinned dependency and run the cells below to",
                    "reproduce the exact numeric outputs the factorial agent",
                    "computed. Plot images may differ from the web UI because",
                    "they are re-rendered locally (font / renderer drift).",
                    "",
                    f'```bash\npip install "process-improve=={version}"\n```',
                ]
            )
        )
    )
    nb.cells.append(
        nbformat.v4.new_code_cell(
            "from process_improve.tool_spec import execute_tool_call",
        )
    )
    for block in blocks:
        nb.cells.append(
            nbformat.v4.new_markdown_cell(
                f"## Step {block['index']} — `{block['tool_name']}`\n\n"
                f"Captured from agent turn {block['agent_turn']}, "
                f"call order {block['call_order']}."
            )
        )
        nb.cells.append(nbformat.v4.new_code_cell(block["code"]))
    nb.cells.append(
        nbformat.v4.new_markdown_cell(
            f"---\n\nReproduced {len(calls)} analysis step(s). "
            "See `data.xlsx` in the bundle for the design matrix and "
            "recorded responses."
        )
    )
    return nbformat.writes(nb).encode("utf-8")


async def build_notebook(db: AsyncSession, experiment: Experiment) -> bytes:
    """High-level entry point for the ``.ipynb`` export endpoint."""
    calls = await _fetch_or_400(db, experiment, format_name=".ipynb")
    return render_notebook(experiment, calls)


# ---------------------------------------------------------------------------
# Literate-markdown renderer.
# ---------------------------------------------------------------------------


def render_literate_markdown(
    experiment: Experiment,
    calls: list[ToolCall],
    *,
    pi_version: str | None = None,
    generated_at: datetime | None = None,
) -> str:
    """Emit a markdown walkthrough with fenced ``python`` code blocks.

    Prose explains each step; the code inside the blocks is identical
    byte-for-byte to what the notebook cells and the ``.py`` script
    emit (same ``_step_blocks`` source).
    """
    if not calls:
        raise ValueError("no analysis tool calls available for this experiment")

    version = pi_version or _resolve_process_improve_version()
    ts = (generated_at or datetime.now(UTC)).isoformat(timespec="seconds")
    blocks = _step_blocks(calls)
    template = _jinja_env.get_template("reproducible_report.md.j2")
    return template.render(
        experiment=experiment,
        pi_version=version,
        generated_at=ts,
        step_blocks=blocks,
        warnings=collect_warnings(calls),
    )


async def build_literate_markdown(db: AsyncSession, experiment: Experiment) -> bytes:
    """High-level entry point for the ``.md_code`` export endpoint."""
    calls = await _fetch_or_400(db, experiment, format_name=".md_code")
    return render_literate_markdown(experiment, calls).encode("utf-8")


# ---------------------------------------------------------------------------
# Data file + README + requirements.txt for the bundle.
# ---------------------------------------------------------------------------


def build_data_file(experiment: Experiment) -> bytes:
    """Return ``data.xlsx`` bytes matching the existing static XLSX export."""
    return export_service.build_xlsx(experiment, include_results=True)


def build_requirements_txt(pi_version: str) -> str:
    """Single-line pin so ``pip install -r`` gives the bundle the right tools."""
    return f"process-improve=={pi_version}\n"


def build_readme(
    experiment: Experiment,
    pi_version: str,
    *,
    warnings: list[str],
    generated_at: datetime | None = None,
) -> str:
    """Render the bundle's ``README.md`` via the Jinja template."""
    ts = (generated_at or datetime.now(UTC)).isoformat(timespec="seconds")
    template = _jinja_env.get_template("reproducible_bundle_readme.md.j2")
    return template.render(
        experiment=experiment,
        pi_version=pi_version,
        generated_at=ts,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Bundle builder — zips everything together.
# ---------------------------------------------------------------------------


async def build_reproducible_bundle(db: AsyncSession, experiment: Experiment) -> bytes:
    """Return a ``.zip`` containing code + data + README + pinned requirements.

    Entries:
        analysis.py           - render_python_script(...)
        analysis.ipynb        - render_notebook(...)
        analysis.md           - render_literate_markdown(...)
        data.xlsx             - build_data_file(...)
        README.md             - build_readme(...)
        requirements.txt      - build_requirements_txt(...)

    All renderers share one ``pi_version`` / ``generated_at`` / warnings
    pair so the bundle is internally consistent.
    """
    calls = await _fetch_or_400(db, experiment, format_name=".zip")
    version = _resolve_process_improve_version()
    now = datetime.now(UTC)
    warnings = collect_warnings(calls)

    entries: list[tuple[str, bytes]] = [
        (
            "analysis.py",
            render_python_script(experiment, calls, pi_version=version, generated_at=now).encode("utf-8"),
        ),
        (
            "analysis.ipynb",
            render_notebook(experiment, calls, pi_version=version, generated_at=now),
        ),
        (
            "analysis.md",
            render_literate_markdown(experiment, calls, pi_version=version, generated_at=now).encode("utf-8"),
        ),
        ("data.xlsx", build_data_file(experiment)),
        (
            "README.md",
            build_readme(experiment, version, warnings=warnings, generated_at=now).encode("utf-8"),
        ),
        ("requirements.txt", build_requirements_txt(version).encode("utf-8")),
    ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, payload in entries:
            zf.writestr(name, payload)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Shared fetch / 400 guard for all four high-level entry points.
# ---------------------------------------------------------------------------


async def _fetch_or_400(
    db: AsyncSession,
    experiment: Experiment,
    *,
    format_name: str,
) -> list[ToolCall]:
    calls = await fetch_analysis_tool_calls(db, experiment)
    if not calls:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No analysis tool calls were found for this experiment. "
                f"The {format_name} export needs at least one successful "
                f"{'/'.join(sorted(ANALYSIS_TOOLS))} call."
            ),
        )
    return calls
