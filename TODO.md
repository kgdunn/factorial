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

## Pre-existing CI failures (unrelated to reproducible-code-export)

- [ ] `tests/test_simulator_flow.py::test_loop_create_then_simulate_end_to_end`,
      `::test_loop_reveal_requires_two_asks`, and
      `::test_loop_reveal_with_force_reveals_immediately` fail with
      `KeyError: 'sim_id'` on `main` at `42f08b2` (verified 2026-04-23).
      The scripted `_Dynamic.stream` stub in those tests parses the
      `tool_result` content expecting a `sim_id` key, but the
      `create_simulator` tool output under `process-improve==1.5.1`
      (pinned in `uv.lock`) no longer returns that key. Either update
      the test to read whatever key the newer tool emits, or adjust
      the simulator tool's output schema upstream in `process-improve`
      so the contract is restored. CI has been red on `main` because
      of this — fix it on a dedicated branch, not piggybacked onto
      unrelated feature PRs.

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

- [ ] Large `tool_output` objects (full design matrices, plot payloads) go
      into `./fixtures/tool_output_<n>.json` in the zip — referenced only by
      the expected-value comparison step, not by the runnable path. Keep
      `analysis.py` slim.
- [ ] Include a `check_outputs.py` in the bundle that re-runs the script
      and diffs against `fixtures/` so users can verify numerical
      reproducibility without reading the code.

## Docs

- [ ] Add a short section under `docs/architecture/` describing the
      reproducibility guarantee, scope limits, and the TODO items above so
      the scope is visible without digging through code.
- [ ] Link to the generated bundle's README.md from the main docs so users
      can preview what they'll get before clicking download.

## Phased delivery

- [x] **PR-1 — MINOR bump.** `.py` export + `reproducible_export_service.py`
      + round-trip tests. Ships via the existing `GET /export?format=py`
      endpoint. No UI.
- [ ] **PR-2 — MINOR bump.** `.ipynb`, `.md_code`, `.zip` bundle,
      `data.xlsx`, `README.md`, `requirements.txt`. Add `nbformat`
      dependency. Bundle tests.
- [ ] **PR-3 — PATCH bump.** `ExportMenu.svelte` entries + `types.ts` enum
      sync + section split. No backend change.
