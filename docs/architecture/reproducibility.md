# Reproducibility

factorial's agent never invents numbers. Every result shown in chat comes
from a call to the deterministic `process_improve.tool_spec.execute_tool_call`
dispatch, which the backend records in the `tool_calls` table. The
**reproducible-code export** feature lets users re-run those exact calls
locally — without re-spending agent tokens, and without having to trust
that the agent's summary of the numbers is faithful.

## What you can download

`GET /api/v1/experiments/{id}/export?format=<fmt>` returns one of:

| Format | Contents |
|--------|----------|
| `py` | Self-contained Python script that replays every analysis step. |
| `ipynb` | Jupyter notebook with narrative markdown + runnable code cells. |
| `md_code` | Literate markdown with prose around fenced `python` blocks. |
| `zip` | Bundle: all three of the above + `data.xlsx` + `README.md` + a pinned `requirements.txt`. Primary deliverable for most users. |

Each artifact imports `from process_improve.tool_spec import execute_tool_call`
and dispatches the recorded `tool_input` for every step in the original
order. The code inside the `.py`, the `.ipynb` cells, and the `.md_code`
fenced blocks is identical byte-for-byte — they're different surfaces
over one shared step-extraction pipeline.

These formats are **not** exposed on public share links
(`/api/v1/public/experiments/{token}/export`) — the artifacts carry raw
tool inputs and belong behind owner auth.

## What "reproducible" means here

- **Numeric tool outputs are bit-for-bit reproducible** across machines
  running the same pinned `process-improve` version: design matrices,
  ANOVA tables, coefficients, p-values, VIF, aliasing, efficiency,
  prediction-variance maps. These are the numbers users actually reason
  about, and they're what the bundle guarantees.
- **Plot images are *not* guaranteed to be byte-identical**. They're
  re-rendered locally, so font availability and renderer version drift
  can produce pixel-level differences between the web UI and your
  local environment. The numeric content driving the plots stays
  reproducible; only the rasterisation differs.

## Known gaps (tracked in `TODO.md`)

- Some `process_improve.generate_design` calls don't capture a `seed`
  / `random_state` kwarg today. When that happens, any randomised
  run-order will differ on re-run. The exported `README.md` surfaces
  a warning per affected step. Upstream fix: thread a `seed` kwarg
  through the design generators.
- `ToolCall.tool_version` is not yet populated in the agent loop, so
  the bundle's `requirements.txt` pins the **currently installed**
  `process-improve`, not the version that was installed when each
  call ran. Rare mismatch in practice; tracked in `TODO.md`.

## Running a downloaded bundle

```bash
unzip experiment.zip -d ./experiment-repro
cd ./experiment-repro
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python analysis.py            # numeric outputs match the agent's
jupyter nbconvert --execute analysis.ipynb --to html
```

The bundle's own `README.md` repeats these instructions and lists any
per-export warnings; use it as the canonical guide when handing a
bundle to a colleague.
