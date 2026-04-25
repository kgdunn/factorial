# TODO — Reproducible code export

Tracking follow-ups to the reproducible-code-export work. See the plan at
`/root/.claude/plans/pull-the-latest-version-resilient-crescent.md` for full
context.

## Determinism gaps in `process-improve`

- [ ] Open upstream issue on `kgdunn/process-improve`: add a `seed: int | None = None`
      kwarg to `generate_design` and any RSM / randomized-run-order routines,
      threaded through `numpy.random.default_rng(seed)`. Without this, the
      downloaded script cannot reproduce run-order randomization.
- [ ] Once the upstream `seed` kwarg ships, bump the pinned `process-improve`
      version in `reproducible_export_service.py` and have the exporter
      inject a synthesized seed when the original `tool_input` omitted one,
      recording it in the generated README so the original run can be
      replayed exactly.
- [ ] Document in `process-improve` which tools are already deterministic
      (no RNG at all) vs. which depend on a seed. The exporter should key
      off that list rather than hard-coding assumptions.

## ~~Pre-existing CI failures (unrelated to reproducible-code-export)~~

- [x] ~~`tests/test_simulator_flow.py::test_loop_*` fail with
      `KeyError: 'sim_id'`~~ — **resolved 2026-04-23**. Root cause was
      that `process-improve==1.5.1` (the pinned version) didn't ship the
      `simulation/` module, so `execute_tool_call("create_simulator", …)`
      raised `ValueError: Unknown tool`, which became an `is_error`
      tool_result with no `sim_id` key. PR #73 added a skip guard;
      `process-improve 1.6.0` (released in `kgdunn/process-improve#103`)
      now ships `simulation/`; this PR bumps the pin to `>=1.6.0` and
      drops the skip guard. All three tests now run and pass.

## Factorial backend

- [ ] Populate `ToolCall.tool_version` per call in
      `backend/src/app/services/agent_loop.py` (field exists on the ORM but
      is currently left null). Lets the exporter pin per-call version when
      an experiment spans a library upgrade.
- [ ] Guard `fetch_analysis_tool_calls` against `output_truncated=True` rows
      — refuse export and surface the call(s) in the error. The flag is
      never set true today but the guard should land before anyone adds
      truncation logic later.
- [ ] Decide on public-share exposure of reproducible bundles in
      `backend/src/app/api/v1/endpoints/shares_public.py`. Default:
      unauthenticated viewers do NOT get `?format=zip` / `py` / `ipynb` /
      `md_code` (raw response data). Revisit if users ask for "public,
      reproducible" sharing.
- [ ] Consider extending the `ExportMenu.svelte` PDF `acknowledge_share`
      gating pattern (`experiments.py:286`) to the bundle, since it also
      embeds raw response data.

## Plot reproducibility

- [ ] Scope in docs (`docs/architecture/`): the guarantee is **numerical**
      equivalence of tool outputs, not byte-identical plots. Mention font /
      renderer drift.
- [ ] Investigate pinning `matplotlib` + a bundled font in the generated
      `requirements.txt` to tighten plot determinism. Probably not worth it
      — call it out and move on unless users ask.

## Data bundle

- [x] ~~Large `tool_output` objects (full design matrices, plot payloads) go
      into `./fixtures/tool_output_<n>.json` in the zip~~ — retired in PR-2
      (2026-04-23). The runnable path embeds `tool_input` via `json.dumps`
      and regenerates `tool_output` on re-run, which is both simpler and a
      stronger reproducibility check than a frozen-fixture diff.
- [ ] Include a `check_outputs.py` in the bundle that re-runs the script
      and diffs against the agent's recorded `tool_output` so users can
      verify numerical reproducibility without reading the code. (Would
      need a separate "recorded outputs" JSON inside the bundle.)

## Docs

- [x] Add a short section under `docs/architecture/` describing the
      reproducibility guarantee, scope limits, and the TODO items above so
      the scope is visible without digging through code. (Landed as
      `docs/architecture/reproducibility.md` in PR-2.)
- [ ] Link to the generated bundle's README.md from the main docs so users
      can preview what they'll get before clicking download.

## Phased delivery

- [x] **PR-1 — MINOR bump.** `.py` export + `reproducible_export_service.py`
      + round-trip tests. Ships via the existing `GET /export?format=py`
      endpoint. No UI.
- [x] **PR-2 — MINOR bump.** `.ipynb`, `.md_code`, `.zip` bundle,
      `data.xlsx`, `README.md`, `requirements.txt`. Add `nbformat`
      dependency. Bundle tests.
- [x] **PR-3 — PATCH bump.** `ExportMenu.svelte` entries + `types.ts` enum
      sync + section split. No backend change.

## DOE upload tool — chat agent integration (deferred)

The current upload feature (PR #81) ships:
- `POST /api/v1/experiments/uploads` + `/answers` + `/finalize` REST surface
- `app.services.upload_parsing_service` (xlsx/csv → 2D matrix)
- `app.services.upload_claude_service.discover_structure` (forced tool_use,
  two tools: `report_design_structure` / `ask_clarifying_questions`)
- Frontend wizard + reusable `<ExperimentDataTable>` + `<DataTableModal>`
  with F2 keyboard shortcut

What is **not** yet wired and should follow up:

- [ ] Register `parse_uploaded_design` as a tool the chat agent can invoke.
      Input shape `{rows: list[list[Any]]}` so a user pasting CSV-like text
      into chat gets the same parsing behaviour. Implementation sketch:
      add a `_LOCAL_TOOL_HANDLERS` registry to
      `backend/src/app/services/tools.py`; have `execute_tool_call`
      dispatch local handlers before falling through to
      `process_improve`; expose `discover_structure` via a sync wrapper
      that can be called from the agent thread.
- [ ] File-attachment plumbing through the chat endpoint
      (`backend/src/app/api/v1/endpoints/chat.py`). The chat endpoint
      currently accepts JSON-only message turns; adding multipart
      attachments + a transient cache keyed by `file_id` is its own
      side quest. Agree with the user on UX before doing this.
- [ ] Frontend: surface the chat tool's clarifying-question output via
      the existing `ToolResultCard.svelte`, and route attachments
      from `ChatWindow.svelte` into the new endpoint.

## Frontend — mobile

- [ ] Replace the top-nav link group in `frontend/src/routes/+layout.svelte`
      with a hamburger drawer on small screens. The current patch hides the
      balance span and the display-name span under `sm:` so the row fits on
      a phone; a drawer would surface them again without wrapping.
