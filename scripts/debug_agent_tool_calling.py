#!/usr/bin/env python3
"""Standalone debug harness for the factorial agent tool-calling loop.

Reproduces production's ``app.services.agent_loop._run_agent_loop`` flow
(streaming Anthropic call + tool dispatch via process_improve) without
the FastAPI / SSE / Postgres scaffolding around it. Useful for isolating
whether a bug is in:

- the process_improve tool registry (specs, schemas, dispatcher), or
- the agent loop's request/response handshake with the Anthropic API.

Run:

    cd backend && uv sync                          # install backend deps
    export ANTHROPIC_API_KEY=sk-...
    python ../scripts/debug_agent_tool_calling.py \\
        --prompt "Are there outliers in [1,2,3,100]?" \\
        --transcript run.json

Compare modes to localise a failure:

    python scripts/debug_agent_tool_calling.py --no-stream
    python scripts/debug_agent_tool_calling.py --tools-category meta
    python scripts/debug_agent_tool_calling.py --tools-category univariate
    python scripts/debug_agent_tool_calling.py --detail-level expert

Every event the production loop pushes onto its SSE queue is printed to
stderr with a wall-clock offset; tool inputs and outputs are dumped in
full to ``--transcript`` so the result can be diffed against a captured
production transcript.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import queue
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path & env setup — must happen BEFORE importing app.* so pydantic Settings
# reads the right values and our ``app`` package is importable.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_SRC = _REPO_ROOT / "backend" / "src"
if _BACKEND_SRC.is_dir() and str(_BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(_BACKEND_SRC))

# Settings has sane defaults for everything except ANTHROPIC_API_KEY.
# We do not touch DATABASE_URL — Settings synthesizes it from POSTGRES_*
# defaults and never opens a connection just from importing app.config.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("TIMING_LOG_PATH", "")  # disable rotating file handler

import anthropic  # noqa: E402

from app.config import settings  # noqa: E402
from app.services.agent_loop import MAX_AGENT_TURNS, _run_agent_loop  # noqa: E402
from app.services.agent_service import _build_system_prompt  # noqa: E402
from app.services.tools import get_tool_specs  # noqa: E402
from app.services.turn_timing import TurnTimer  # noqa: E402

logger = logging.getLogger("debug_agent")


# ---------------------------------------------------------------------------
# Pretty event printer
# ---------------------------------------------------------------------------


class EventPrinter:
    """Drain queue events and pretty-print each one with a timestamp."""

    def __init__(self, t0: float, transcript: list[dict[str, Any]] | None) -> None:
        self._t0 = t0
        self._transcript = transcript
        self._token_buf: list[str] = []

    def _flush_tokens(self) -> None:
        if not self._token_buf:
            return
        text = "".join(self._token_buf)
        self._token_buf.clear()
        # Indent multi-line streamed text so the prefix stays readable.
        prefix = self._stamp("token") + " "
        for i, line in enumerate(text.splitlines() or [""]):
            sys.stderr.write(prefix + line + "\n" if i == 0 else " " * len(prefix) + line + "\n")
        sys.stderr.flush()

    def _stamp(self, event: str) -> str:
        return f"[+{time.perf_counter() - self._t0:7.3f}s] {event:<14}"

    def handle(self, event: str, data: dict[str, Any]) -> None:
        if self._transcript is not None:
            self._transcript.append({"event": event, "data": data, "t": time.perf_counter() - self._t0})

        if event == "token":
            self._token_buf.append(data.get("text", ""))
            return

        # Any non-token event flushes the streamed-text buffer first.
        self._flush_tokens()

        if event == "phase":
            phase = data.get("phase", "?")
            extra = ""
            if "turn" in data:
                extra = f" turn={data['turn']}/{data.get('max_turns', '?')}"
            if "tool" in data:
                extra += f" tool={data['tool']}"
            sys.stderr.write(self._stamp("phase") + f" {phase}{extra}\n")
        elif event == "tool_start":
            tool = data.get("tool", "?")
            inp = json.dumps(data.get("input", {}), default=str)
            inp_short = inp if len(inp) <= 400 else inp[:400] + f"... ({len(inp)} chars)"
            sys.stderr.write(self._stamp("tool_start") + f" {tool} input={inp_short}\n")
        elif event == "tool_result":
            tool = data.get("tool", "?")
            out = json.dumps(data.get("output", {}), default=str)
            out_short = out if len(out) <= 500 else out[:500] + f"... ({len(out)} chars)"
            sys.stderr.write(self._stamp("tool_result") + f" {tool} output={out_short}\n")
        elif event == "plan":
            steps = data.get("steps") or []
            sys.stderr.write(self._stamp("plan") + f" plan_id={data.get('plan_id')} steps={steps}\n")
        elif event == "plan_update":
            updates = data.get("updates") or []
            sys.stderr.write(self._stamp("plan_update") + f" plan_id={data.get('plan_id')} updates={updates}\n")
        elif event == "error":
            sys.stderr.write(self._stamp("ERROR") + f" {json.dumps(data, default=str)}\n")
        elif event == "done":
            sys.stderr.write(self._stamp("done") + " agent loop finished cleanly\n")
        else:
            sys.stderr.write(self._stamp(event) + f" {json.dumps(data, default=str)}\n")
        sys.stderr.flush()


# ---------------------------------------------------------------------------
# Optional non-streaming shim — for --no-stream A/B comparison
# ---------------------------------------------------------------------------


class _NonStreamShim:
    """Emulate the SDK's stream context object from a non-streaming response.

    The production loop iterates over the stream for ``content_block_delta``
    events and then calls ``stream.get_final_message()``. With
    --no-stream we skip the iteration and synthesise the same final
    message from a plain ``messages.create`` call.
    """

    def __init__(self, response: Any) -> None:
        self._response = response

    def __iter__(self):  # noqa: D401 — generator protocol
        return iter(())  # No streaming events; loop body runs zero times.

    def get_final_message(self) -> Any:
        return self._response


def _patch_client_for_no_stream(client: anthropic.Anthropic) -> None:
    """Replace ``client.messages.stream`` with a non-streaming context manager.

    Narrow monkey-patch — only the ``stream`` attribute is touched and
    the patched function does exactly one ``messages.create`` round-trip.
    """
    real_create = client.messages.create

    class _Ctx:
        def __init__(self, kwargs: dict[str, Any]) -> None:
            self._kwargs = kwargs
            self._shim: _NonStreamShim | None = None

        def __enter__(self) -> _NonStreamShim:
            response = real_create(**self._kwargs)
            self._shim = _NonStreamShim(response)
            return self._shim

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            return False

    def patched_stream(**kwargs: Any) -> _Ctx:
        return _Ctx(kwargs)

    client.messages.stream = patched_stream  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--prompt",
        default="Are there outliers in [1, 2, 3, 100]?",
        help="User message that starts the conversation.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override settings.anthropic_model (e.g. claude-sonnet-4-5, claude-opus-4-5).",
    )
    parser.add_argument(
        "--user-background",
        default=None,
        help="Slug like 'chemical_engineer' (must match ^[a-z0-9_]{1,50}$).",
    )
    parser.add_argument(
        "--detail-level",
        default="intermediate",
        choices=("beginner", "intermediate", "expert"),
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help=f"Override MAX_AGENT_TURNS (default {MAX_AGENT_TURNS}).",
    )
    parser.add_argument(
        "--tools-category",
        default=None,
        help="Restrict tools to a single category (univariate, multivariate, experiments, meta, ...).",
    )
    parser.add_argument(
        "--tools",
        default=None,
        help="Comma-separated allow-list of tool names.",
    )
    parser.add_argument(
        "--force-reveal",
        action="store_true",
        help="Skip the simulator-reveal double-confirm gate.",
    )
    parser.add_argument(
        "--byok-key",
        default=None,
        help="Use this Anthropic key instead of ANTHROPIC_API_KEY (BYOK path).",
    )
    parser.add_argument(
        "--transcript",
        default=None,
        type=Path,
        help="Path to write a JSON dump of all events, messages, and tool I/O.",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Use messages.create() instead of messages.stream() — A/B test for streaming bugs.",
    )
    parser.add_argument(
        "--log-level",
        default="DEBUG",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    # ---------- environment summary ----------
    try:
        import process_improve  # noqa: PLC0415

        pi_version = getattr(process_improve, "__version__", "unknown")
    except ImportError:
        pi_version = "MISSING — pip install process_improve"

    print("=" * 78, file=sys.stderr)
    print("Agent tool-calling debug harness", file=sys.stderr)
    print(f"  python           : {sys.version.split()[0]}", file=sys.stderr)
    print(f"  anthropic sdk    : {anthropic.__version__}", file=sys.stderr)
    print(f"  process_improve  : {pi_version}", file=sys.stderr)
    print(f"  app_env          : {settings.app_env}", file=sys.stderr)
    print(f"  tool_safe_mode   : {settings.tool_safe_mode}", file=sys.stderr)
    print(f"  model            : {args.model or settings.anthropic_model}", file=sys.stderr)
    print(f"  no_stream        : {args.no_stream}", file=sys.stderr)
    print("=" * 78, file=sys.stderr)

    # ---------- API key ----------
    api_key = args.byok_key or settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(
            "ERROR: no Anthropic API key found. Set ANTHROPIC_API_KEY env var "
            "or pass --byok-key.",
            file=sys.stderr,
        )
        return 2
    # Don't echo any portion of the key, even a prefix or suffix —
    # CodeQL's clear-text-logging rule (and good hygiene) forbids it.
    # The length is enough to confirm "the variable is set".
    print(f"  api_key          : present ({len(api_key)} chars)", file=sys.stderr)

    # ---------- tool specs ----------
    tool_names: list[str] | None = None
    if args.tools:
        tool_names = [n.strip() for n in args.tools.split(",") if n.strip()]
    raw_specs = get_tool_specs(names=tool_names, category=args.tools_category)
    # Strip the ``category`` field exactly the way agent_service.run_chat does.
    tool_specs = [{k: v for k, v in s.items() if k != "category"} for s in raw_specs]
    print(f"  tools registered : {len(tool_specs)}", file=sys.stderr)
    for spec in sorted(tool_specs, key=lambda s: s["name"]):
        print(f"      - {spec['name']}", file=sys.stderr)
    print("=" * 78, file=sys.stderr)
    if not tool_specs:
        print("WARNING: no tools matched the filters — agent has nothing to call.", file=sys.stderr)

    # ---------- system prompt ----------
    system_prompt = _build_system_prompt(args.user_background, args.detail_level)
    print(f"  system_prompt    : {len(system_prompt)} chars", file=sys.stderr)
    print("=" * 78, file=sys.stderr)

    # ---------- client ----------
    client = anthropic.Anthropic(api_key=api_key)
    if args.no_stream:
        _patch_client_for_no_stream(client)
        logger.info("client.messages.stream patched to non-streaming wrapper")

    # ---------- loop ----------
    messages: list[dict[str, Any]] = [{"role": "user", "content": args.prompt}]
    print(f"USER: {args.prompt}", file=sys.stderr)
    print("=" * 78, file=sys.stderr)

    transcript: list[dict[str, Any]] | None = [] if args.transcript else None
    event_queue: queue.Queue[Any] = queue.Queue()
    turn_id = uuid.uuid4()

    # Override MAX_AGENT_TURNS by patching the module global if requested.
    if args.max_turns is not None:
        from app.services import agent_loop as _al  # noqa: PLC0415

        _al.MAX_AGENT_TURNS = args.max_turns
        logger.info("MAX_AGENT_TURNS overridden to %d", args.max_turns)

    timer = TurnTimer(conversation_id=None, turn_id=turn_id)
    t0 = time.perf_counter()
    printer = EventPrinter(t0, transcript)
    exit_code = 0

    try:
        # Run synchronously in the main thread so any crash gives us a
        # clean traceback instead of disappearing into a worker thread.
        loop_result = _run_agent_loop(
            event_queue=event_queue,
            messages=messages,
            tool_specs=tool_specs,
            client=client,
            model=args.model or settings.anthropic_model,
            turn_id=turn_id,
            system_prompt=system_prompt,
            simulator_states={},
            reveal_counts={},
            newly_created_sims=[],
            force_reveal=args.force_reveal,
            timer=timer,
            byok_used=bool(args.byok_key),
        )
    except anthropic.APIError as exc:
        request_id = getattr(exc, "request_id", None) or getattr(getattr(exc, "response", None), "headers", {}).get(
            "x-request-id"
        )
        sys.stderr.write(
            f"\nAnthropic APIError: {type(exc).__name__}: {exc}\n"
            f"  request_id = {request_id}\n",
        )
        traceback.print_exc(file=sys.stderr)
        exit_code = 3
        loop_result = {"new_messages": [], "tool_call_records": []}
    except Exception:
        sys.stderr.write("\nUnexpected exception in agent loop:\n")
        traceback.print_exc(file=sys.stderr)
        exit_code = 4
        loop_result = {"new_messages": [], "tool_call_records": []}

    # Drain any events the loop pushed before raising.
    while True:
        try:
            item = event_queue.get_nowait()
        except queue.Empty:
            break
        if item is None:
            continue
        printer.handle(item[0], item[1])
    printer._flush_tokens()  # noqa: SLF001 — final flush

    # ---------- summary ----------
    print("=" * 78, file=sys.stderr)
    print(f"agent_turns_seen : {len(loop_result.get('tool_call_records', []))} tool call(s)", file=sys.stderr)
    for rec in loop_result.get("tool_call_records", []):
        status = rec.get("status", "?")
        name = rec.get("tool_name", "?")
        dur = rec.get("duration_ms")
        in_b = rec.get("input_bytes")
        out_b = rec.get("output_bytes")
        print(
            f"  - turn={rec.get('agent_turn')} order={rec.get('call_order')} "
            f"name={name} status={status} duration_ms={dur} "
            f"input_bytes={in_b} output_bytes={out_b}",
            file=sys.stderr,
        )
        if rec.get("error_message"):
            print(f"      error: {rec['error_message']}", file=sys.stderr)

    # Final assistant text (last assistant message in messages).
    final_text = ""
    for m in reversed(loop_result.get("new_messages", [])):
        if m.get("role") == "assistant":
            for block in m.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    final_text = block.get("text", "") + final_text
            if final_text:
                break
    print("=" * 78, file=sys.stderr)
    print("FINAL ASSISTANT TEXT:", file=sys.stderr)
    print(final_text or "(no text content in final assistant message)", file=sys.stderr)
    print("=" * 78, file=sys.stderr)

    # ---------- transcript dump ----------
    if args.transcript and transcript is not None:
        # ``messages`` carries SDK content blocks; convert to dicts for JSON.
        def _serialise_block(block: Any) -> Any:
            if isinstance(block, dict):
                return block
            t = getattr(block, "type", None)
            if t == "text":
                return {"type": "text", "text": getattr(block, "text", "")}
            if t == "tool_use":
                return {
                    "type": "tool_use",
                    "id": getattr(block, "id", None),
                    "name": getattr(block, "name", None),
                    "input": getattr(block, "input", None),
                }
            return repr(block)

        serialised_messages: list[dict[str, Any]] = []
        for m in messages:
            content = m.get("content")
            if isinstance(content, list):
                serialised_messages.append({"role": m["role"], "content": [_serialise_block(b) for b in content]})
            else:
                serialised_messages.append({"role": m["role"], "content": content})

        payload = {
            "args": vars(args) | {"transcript": str(args.transcript)},
            "events": transcript,
            "messages": serialised_messages,
            "tool_call_records": [
                {k: (str(v) if k in {"started_at", "completed_at", "turn_id"} else v) for k, v in rec.items()}
                for rec in loop_result.get("tool_call_records", [])
            ],
            "exit_code": exit_code,
        }
        args.transcript.write_text(json.dumps(payload, indent=2, default=str))
        print(f"transcript written to {args.transcript}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
