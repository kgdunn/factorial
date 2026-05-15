# Factorial — System Specification

> **Status:** As-built architecture reference, reverse-engineered from the
> codebase at version `0.29.4`. This document describes what the system
> *is* and *does* today. Capabilities that are designed but not yet
> implemented are confined to [§20 Future scope](#20-future-scope) and
> are not described as present-tense behaviour anywhere else.
>
> Where this document and an older page under `docs/` disagree, the
> code-accurate statement here is authoritative and the divergence is
> noted inline.

---

## Table of contents

1. [Overview & purpose](#1-overview--purpose)
2. [System architecture](#2-system-architecture)
3. [Personas & roles](#3-personas--roles)
4. [Account & access lifecycle](#4-account--access-lifecycle)
5. [Authentication & sessions](#5-authentication--sessions)
6. [The conversational agent](#6-the-conversational-agent)
7. [Experiments](#7-experiments)
8. [Data import](#8-data-import)
9. [Exports & reproducibility](#9-exports--reproducibility)
10. [Sharing](#10-sharing)
11. [Billing & BYOK](#11-billing--byok)
12. [Admin console](#12-admin-console)
13. [Hosted MCP endpoint](#13-hosted-mcp-endpoint)
14. [Data model](#14-data-model)
15. [API surface](#15-api-surface)
16. [Frontend specification](#16-frontend-specification)
17. [Non-functional requirements](#17-non-functional-requirements)
18. [Deployment & operations](#18-deployment--operations)
19. [Engineering conventions](#19-engineering-conventions)
20. [Future scope](#20-future-scope)
21. [Glossary](#21-glossary)

---

## 1. Overview & purpose

**Factorial** is a conversational, LLM-assisted web application that helps
scientists and engineers design, run, and analyse experiments using
**Design of Experiments (DOE)** methodology. It is the open-source
codebase behind the hosted instance at **factori.al**, and it is built to
be self-hosted: any operator can clone the repository and stand up their
own instance.

### 1.1 The problem

Systematic experimentation is statistically demanding. Choosing a design
(how many runs, which factor combinations), reasoning about confounding
and aliasing, fitting models, and interpreting response surfaces all
require expertise that most domain scientists do not have at hand.
Factorial puts that expertise behind a chat interface: an agent powered
by Claude guides the user through design selection, executes the
statistics, and renders interactive visualisations.

### 1.2 Core principle — the agent never invents numbers

Every numeric result the agent presents comes from a real call to the
deterministic **`process-improve`** package (a separate library:
`github.com/kgdunn/process-improve`). The agent's job is to choose tools,
supply inputs, and explain outputs in plain language — never to fabricate
coefficients, p-values, or design matrices. This principle is enforced in
the system prompt and is the foundation of the reproducible-export
feature ([§9](#9-exports--reproducibility)): because every figure is the
output of a recorded tool call, the user can re-run those exact calls
locally and obtain bit-identical numbers.

### 1.3 Product capabilities

- Agent-first chat UI as the primary interaction mode.
- Design generation for factorial, fractional-factorial, screening
  (Plackett–Burman, definitive screening), response-surface (central
  composite, Box–Behnken), optimal, mixture, and Taguchi designs.
- Design evaluation: resolution, aliasing, D-/I-efficiency, VIF,
  condition number, prediction-variance maps, and power per effect.
- Incremental results entry — users record response values as
  experimental runs complete.
- Interactive visualisation: 3-D response surfaces, contour plots,
  main-effect and interaction plots.
- A fake-data **simulator** so users can plan or demonstrate an
  experiment against synthetic-but-realistic data.
- Import of existing designs from Excel/CSV with LLM-assisted parsing.
- Export to PDF/XLSX/CSV/Markdown reports and to **reproducible code
  bundles** (Python script, Jupyter notebook, literate Markdown).
- Public, revocable share links for finished experiments.
- Bring-Your-Own-Key (BYOK): users may supply a personal Anthropic API
  key, stored encrypted, and bypass the platform billing markup.

### 1.4 Mobile-native mandate

Mobile browsers are first-class. Every UI surface is designed and tested
for touch interaction, small viewports, and cellular performance on equal
footing with desktop. A change that degrades the mobile experience is not
acceptable even if it looks correct on desktop.

---

## 2. System architecture

### 2.1 Monorepo

The backend and frontend live in a single repository. They share no code
and communicate only over HTTP at `/api/v1/`; each has its own Dockerfile,
package manager, and CI workflow. The monorepo exists for workflow
simplicity — one `git pull && docker compose up --build` deploys the whole
system, one clone gives a coding agent full system context, and an API
contract change updates client and server in the same commit.

### 2.2 Component diagram

```
                 Browser (SvelteKit SPA, static)
                          │  fetch /api/v1/*  +  SSE
                          ▼
        ┌──────────────────────────────────────────┐
        │            FastAPI + Uvicorn             │
        │  /api/v1 routers · Pydantic · middleware  │
        │  CORS · rate-limit (slowapi) · CSRF       │
        │                                          │
        │  agent loop  ──►  process-improve tools   │
        │  (thread)         (subprocess sandbox)    │
        │       │                                  │
        │  SQLAlchemy 2.0 async      Neo4j async    │
        └───────┬──────────────────────┬───────────┘
                ▼                      ▼
          PostgreSQL 16           Neo4j 5 Community
       (all application data)   (connectivity only;
                                 graph schema planned)
```

### 2.3 Backend

- **FastAPI + Uvicorn** (ASGI), Python ≥ 3.12 syntax.
- **SQLAlchemy 2.0 async** over **asyncpg** for all PostgreSQL access;
  **Alembic** for migrations.
- **PostgreSQL 16** holds every piece of application state.
- **Neo4j 5 Community** is connected and health-checked at startup, but
  the knowledge-graph schema is not yet used by application code (see
  [§20](#20-future-scope)).
- **`pydantic-settings`** reads configuration from `.env` / environment.
- The agent uses the raw **Anthropic SDK**.
- Code lives under `backend/src/app/` (src layout, imported as
  `app.<module>`). API routes are versioned under `/api/v1/`.

### 2.4 Frontend

- **SvelteKit + Svelte 5** (runes API), **Vite**, **TypeScript strict**.
- **Tailwind CSS 4** for styling.
- **ECharts + echarts-gl** for all visualisation.
- Built with **`adapter-static`** — the frontend is a single-page app
  with no server-side rendering, served by nginx in production.
- State is held in Svelte 5 rune-based stores (no legacy stores API).

### 2.5 The agent execution model

The chat agent is intentionally *not* a pure async coroutine. The
multi-turn tool-use loop is synchronous and blocking (it makes blocking
Anthropic SDK calls), so it runs in a worker thread:

1. `run_chat()` — the async orchestrator — is invoked by the chat
   endpoint and opens a Server-Sent Events (SSE) response.
2. It launches `_run_agent_loop()` in a background thread via
   `asyncio.to_thread`.
3. The synchronous loop pushes `(event_name, data)` tuples onto a
   `queue.Queue`.
4. An async generator (`_stream_from_queue()`) drains that queue and
   yields `ServerSentEvent` objects to the client.
5. When the loop finishes, assistant messages and a tool-call audit
   trail are persisted to PostgreSQL.

This is the central design pattern of the backend; everything in
[§6](#6-the-conversational-agent) builds on it.

---

## 3. Personas & roles

| Persona | Description |
|---------|-------------|
| **Domain scientist / engineer** | The primary user. Authenticated, owns conversations and experiments. Self-identifies with a *role*. |
| **Administrator** | A user with `is_admin = true`. Approves signups, manages users/roles, reviews feedback, reads the operational event log. |
| **Public viewer** | Unauthenticated. Can open a revocable share link to a read-only experiment snapshot. |
| **Machine client** | A service authenticating with an `X-API-Key` header instead of a browser session. Also the consumer of the optional hosted MCP endpoint. |

### 3.1 Roles

Every user has a **role** (FK `users.role_id` → `roles`). Seven built-in
roles are seeded by the initial migration: `chemical_engineer`,
`pharmaceutical_scientist`, `food_scientist`, `academic_researcher`,
`quality_engineer`, `data_scientist`, `student`. (An eighth seeded
`other` role was removed in migration `0010`; the signup form provides
its own free-text "Other" instead.)

A role has a slug `name` (`[a-z0-9_]+`, ≤ 50 chars), a human-readable
`description`, and an `is_builtin` flag. The slug is interpolated into the
agent's system prompt to personalise its language, so it is constrained
and re-validated (`^[a-z0-9_]{1,50}$`) before interpolation even though
roles are admin-created — a defence against prompt injection via a
tampered database row. Admins can create custom roles; built-in roles
cannot be renamed or deleted, and a role in use by any user cannot be
deleted.

---

## 4. Account & access lifecycle

The platform is **invite-only**. Direct self-registration is disabled
(`POST /auth/register` returns `403`).

### 4.1 First admin (bootstrap)

There is no "admin by environment variable". Admin status is the
`users.is_admin` boolean. A fresh install is bootstrapped from the CLI:

```
uv run python -m app.cli create-admin --email you@example.com --name "Jane Doe"
```

This creates a `users` row with `is_admin = true` and an empty password
hash, mints a single-use `setup` token (72-hour expiry), and prints — and,
if SMTP is configured, emails — a `…/auth/setup?token=…` link. The admin
follows the link, sets a password, and is signed in.

Additional CLI subcommands: `list-admins`, `promote`, `demote` (refuses
to demote the last remaining admin), and `reset-password`. These also run
inside the deployed container, so an operator with shell access can
rescue a locked-out account.

### 4.2 Signup → approval → invite → registration

```
Prospect          POST /signup/request        → signup_requests row (pending)
                  { email, use_case, requested_role, accepted_disclaimers }
                                                  admin notified by email
Admin             GET  /signup/admin/list
                  POST /signup/admin/{id}/approve  { role_id | new_role }
                                                  → status = approved
                                                    invite token issued
                                                    invite emailed
User              GET  /signup/invite/validate
                  POST /signup/invite/register  { token, password, display_name }
                                                  → users row created
                                                    role copied from signup
                                                    status = registered
                                                    session cookies set
```

Key properties:

- **Role is mandatory.** The applicant picks a role (or "Other" + free
  text); the admin assigns a real role at approval, either an existing
  one or one created inline. Nothing is auto-created.
- `signup_requests.requested_role` is what the applicant *asked for* and
  is never trusted directly; `signup_requests.role_id` is the admin's
  *decision* and is what the new user's `users.role_id` is copied from.
- A signup request also records which legal disclaimer versions the
  applicant accepted (`accepted_disclaimers`, added in migration `0005`).
- Admins may reject a request with an optional note.

### 4.3 Setup & password-reset tokens

First-time setup and password reset share the `setup_tokens` table.
A token has a `purpose` (`setup` or `reset`), a 72-hour expiry, and a
single-use `used_at` marker.

- `POST /auth/password-reset/request` — public, rate-limited; always
  returns `202` regardless of whether the email matches a user (no
  account enumeration). Issues a `reset` token and emails the link.
- `GET /auth/setup/validate` — checks a token is valid and unconsumed,
  returns the associated email for display.
- `POST /auth/setup/complete` — sets the password, consumes the token,
  and mints a session. Works for both `setup` and `reset`.
- `POST /auth/password/change` — authenticated; takes the current and
  new password. For BYOK-enrolled users this also re-wraps the data
  encryption key (see [§11](#11-billing--byok)).

---

## 5. Authentication & sessions

### 5.1 Dual authentication

Two credential types are accepted:

- **Browser session cookie** — `factorial_session`, an opaque pointer to
  a row in the `sessions` table. The session id is 32 random bytes; there
  is **no signing key** anywhere in the loop, so server redeploys do not
  invalidate cookies.
- **API key** — the `X-API-Key` header, compared by HMAC. Retained for
  machine-to-machine calls. API-key callers are mapped to a synthetic
  service identity and skip CSRF (a header-based credential is not
  subject to the CSRF threat).

The `require_auth` dependency tries the cookie first, then the API key,
and returns an `AuthUser` dataclass (`id`, `email`, `is_admin`,
`session_id`, `family_id`, …). `require_admin` builds on it and gates on
`is_admin`. Admin-only routes are checked unconditionally against the
database-loaded user.

### 5.2 Session lifecycle

- **Idle expiry**: 30 days (`COOKIE_SESSION_IDLE_DAYS`) — maximum gap
  between requests.
- **Absolute expiry**: 180 days (`COOKIE_SESSION_ABSOLUTE_DAYS`) —
  maximum total age regardless of activity.
- `last_used_at` is write-throttled (updated at most once per minute) to
  avoid a database write on every request.
- Sessions belong to a **family** (`family_id`) so "sign out everywhere"
  can revoke every device at once.
- Each session also has a non-secret `public_id` so the session list UI
  can identify a device for revocation without exposing the cookie value.

Endpoints: `POST /auth/login`, `POST /auth/logout`,
`POST /auth/logout-all`, `GET /auth/me`, `GET /auth/sessions`,
`DELETE /auth/sessions/{public_id}`. There is no `/auth/refresh` —
sessions are sliding, not token-refresh based.

### 5.3 CSRF

State-changing requests use a **double-submit** scheme. A non-httpOnly
`factorial_csrf` cookie is set at login; the SPA mirrors it into an
`X-CSRF-Token` header on every POST/PUT/PATCH/DELETE. The `require_csrf`
dependency rejects a mismatch (constant-time comparison). Safe methods,
API-key callers, and opaque-token public-share routes are exempt.

### 5.4 SSE and revocation

`require_auth` resolves once, before the streaming response opens.
Server-side session revocation does **not** interrupt an in-flight SSE
stream — it takes effect on the next connection. The `/profile` UI states
this explicitly.

### 5.5 Frontend auth behaviour

Nothing related to identity is stored in `localStorage`. The SPA learns
who the user is by calling `GET /auth/me` at boot. The shared `authFetch`
wrapper sends `credentials: 'include'`, attaches the CSRF header, and on a
`401` opens an inline re-authentication modal, replaying the original
request after the user signs back in; concurrent `401`s share a single
modal and promise. A `5xx` is surfaced to the caller — a transient
backend blip never logs the user out.

---

## 6. The conversational agent

### 6.1 Endpoints

- `POST /api/v1/chat` — start or continue a conversation. Body:
  `{ text, conversation_id?, detail_level }`. Returns an SSE stream.
  Rate-limited (`CHAT_RATE_LIMIT`, default `10/minute`).
- `GET /api/v1/chat/{conversation_id}/resume` — replay the persisted
  event log for a turn, honouring `Last-Event-ID`, so a dropped stream
  can reconnect (see §6.6).
- `GET /api/v1/chat/{conversation_id}/messages` — load a conversation's
  messages, formatted as content blocks for rendering.

### 6.2 The tool-use loop

The synchronous loop (`_run_agent_loop`) iterates up to
`MAX_AGENT_TURNS = 10` times — a hard safety stop against a runaway
agent. Each iteration:

1. Calls the Anthropic API with the conversation so far and the tool
   specifications.
2. Streams text deltas as `token` events.
3. For each `tool_use` block in the response: emits `tool_start`,
   executes the tool, emits `tool_result`, and records an audit row.
4. If the model's `stop_reason` is `tool_use`, the tool results are
   appended and the loop continues; if it is `end_turn`, the loop emits
   `done` and stops.

### 6.3 Tools

DOE tools are provided by the `process-improve` package and reached
through a thin bridge (`app.services.tools`). The agent-facing tools
include `generate_design`, `evaluate_design`, `analyze_results`,
`visualize_doe`, and the simulator tools `create_simulator`,
`simulate_process`, `reveal_simulator`. Tool names are checked against an
allowlist before execution.

The system prompt instructs the agent to always call `evaluate_design`
immediately after a successful `generate_design`, and to ask the user for
the expected residual standard deviation (σ) and a minimum practical
effect size first if they are needed for the power calculation.

### 6.4 The planning protocol

Two **local meta-tools** — `record_plan` and `update_plan` — exist purely
to drive the UI's live activity checklist. They perform no real work and
bypass the tool sandbox; the loop translates their invocations into
`plan` and `plan_update` SSE events. The agent is instructed to call
`record_plan` (2–5 short imperative steps) as its first action for any
non-trivial request, and `update_plan` to move steps through
`pending → in_progress → completed`. Trivial replies (greetings,
clarifying questions) skip planning entirely.

The loop additionally emits `phase` events — a coarse activity label
(thinking, streaming, calling a named tool, finalising) — so the UI can
show a live status pill and elapsed timer.

### 6.5 The fake-data simulator

A user can ask the agent to build a synthetic process so they can plan or
demonstrate an experiment without real data. The agent proposes factors
and responses, confirms with the user, then calls `create_simulator`,
which stores a hidden model (`private_state`) and an LLM-visible summary
(`public_summary`). `simulate_process` evaluates the simulator at given
settings, with deliberate run-to-run noise.

The hidden model is protected by a **two-step reveal gate**: the first
`reveal_simulator` call is refused with a confirmation prompt (surfaced
verbatim to the user); only the second call reveals the model. This is
enforced in `simulator_interception` via `pre_dispatch` / `post_dispatch`
hooks around tool execution and a per-simulator `reveal_request_count`.
The `SIMULATOR_REVEAL_FORCE` setting bypasses the gate and is for
debugging only.

### 6.6 Streaming protocol & resume

Every event emitted during a turn is appended to the `chat_events` table,
keyed by a per-turn `turn_id` and a monotonic `sequence`. If the client's
SSE connection drops, it reconnects to the resume endpoint with the last
`sequence` it saw and replays anything it missed. If the turn never
reached a terminal state (e.g. the backend restarted mid-turn), the
resume endpoint emits a synthetic `interrupted` event and the UI offers a
retry. The frontend attempts up to three reconnections with exponential
backoff before giving up.

SSE event types:

| Event | Payload / meaning |
|-------|-------------------|
| `conversation_id` | Server-assigned conversation and turn id. |
| `token` | A text delta to append to the current bubble. |
| `tool_start` | A tool call began: `{ tool, input }`. |
| `tool_result` | A tool call returned: `{ tool, output }`. |
| `plan` | Initial plan: `{ plan_id, steps[] }`. |
| `plan_update` | Step status transitions. |
| `phase` | Coarse activity label + turn counter. |
| `experiment_created` | An experiment was auto-created this turn. |
| `done` | Terminal — the turn completed normally. |
| `interrupted` | Terminal — the turn was cut short; retry offered. |
| `error` | Terminal — `{ message, kind? }`. |

A typed `error` with `kind = "anthropic_unavailable"` flips the global
LLM-status banner to "down" immediately rather than being shown as a
generic chat error.

### 6.7 Token-batched persistence

SSE `token` events are delivered to the client one delta at a time
(unchanged), but for *persistence* they are coalesced into a single
`chat_events` row roughly every 0.25 s. This drops per-turn database
writes from O(tokens) to O(phases). Per-turn latency is also instrumented
to a rotating JSON-Lines file (`turn_timing`) for offline `jq` analysis.

### 6.8 Math rendering

The agent is instructed to wrap mathematics in LaTeX `\( … \)` (inline)
and `\[ … \]` (display) delimiters — never `$…$`. The frontend typesets
these with KaTeX.

### 6.9 Detail level & voice input

The chat UI offers a detail-level control (beginner / intermediate /
expert), persisted to `localStorage` and sent with every request as a
hint to the model. A voice-input button uses the browser Web Speech API
where available (hidden where it is not, e.g. Firefox).

---

## 7. Experiments

An **experiment** is the persistent record of a DOE study. It is
**auto-created** when the agent's `generate_design` tool succeeds within
a conversation, so designs survive browser sessions and support
incremental results entry.

An experiment stores: `name`, `status` (`draft` / `active` / `completed`
/ `archived`), `design_type`, the factor specifications, the full
`generate_design` output (`design_data` — coded and actual matrices, run
order, …), user-entered `results_data`, the most recent `evaluate_design`
output (`evaluation_data` — aliasing, resolution, efficiency, VIF,
condition number, prediction-variance map, power), and a link back to the
originating conversation.

Operations (all owner-scoped):

- `GET /experiments` — paginated, status-filterable list.
- `GET /experiments/{id}` — full detail.
- `PATCH /experiments/{id}` — rename, change status.
- `DELETE /experiments/{id}`.
- `POST /experiments/{id}/results` / `GET …/results` — record and read
  response values. Each results row carries the response value, optional
  free-text `notes`, and an `included` flag (default `true`) so a user
  can exclude an outlier run. (The analysis path does not yet honour
  `included` when fitting models — tracked in `TODO.md`.)
- `POST /experiments/{id}/evaluate` — re-run `evaluate_design`, e.g. with
  a revised σ, effect size, or α.

Ownership is checked unconditionally; `experiments.user_id` is
`NOT NULL`.

---

## 8. Data import

Users can import an existing design from a spreadsheet instead of having
the agent generate one. A three-step wizard:

1. `POST /experiments/uploads` — upload an Excel/CSV file. The file is
   parsed into a 2-D matrix (`upload_parsing_service`), then Claude is
   asked, with forced tool use, to discover the structure
   (`upload_claude_service.discover_structure`). It returns either a
   parsed design or a set of clarifying questions (e.g. "is row 1 a
   header?", "which columns are factors vs. responses?").
2. `POST /experiments/uploads/{id}/answers` — the user answers the
   clarifying questions; Claude makes a second pass.
3. `POST /experiments/uploads/{id}/finalize` — the confirmed structure
   becomes a normal experiment.

Two limits bound the cost of every upload-driven Anthropic call:
`UPLOAD_MAX_BYTES` (raw file size, default 5 MiB) and `UPLOAD_MAX_CELLS`
(parsed-matrix cells handed to Claude, default 10 000).

---

## 9. Exports & reproducibility

`GET /experiments/{id}/export?format=<fmt>` produces a downloadable
artifact in one of eight formats.

**Report formats** describe the experiment for a reader:

| Format | Contents |
|--------|----------|
| `csv` | Design matrix + results as CSV. |
| `xlsx` | The same as an Excel workbook. |
| `md` | A Markdown report. |
| `pdf` | A rendered report with embedded plots. |

PDF rendering uses WeasyPrint, and ECharts options are rasterised to PNG
via a headless Chromium (Playwright) in `chart_render_service`.

**Reproducible-code formats** let the user re-run the analysis:

| Format | Contents |
|--------|----------|
| `py` | A self-contained Python script replaying every recorded tool call. |
| `ipynb` | A Jupyter notebook: narrative Markdown + runnable cells. |
| `md_code` | Literate Markdown: prose around fenced `python` blocks. |
| `zip` | A bundle: all three of the above + `data.xlsx` + `README.md` + a pinned `requirements.txt`. The primary deliverable. |

Each artifact imports `from process_improve.tool_spec import
execute_tool_call` and dispatches the recorded `tool_input` for every
step, in the original order. The code in the `.py`, the `.ipynb` cells,
and the `.md_code` fenced blocks is byte-identical — three surfaces over
one shared step-extraction pipeline.

### 9.1 What "reproducible" means

- **Numeric tool outputs are bit-for-bit reproducible** across machines
  running the same pinned `process-improve` version — design matrices,
  ANOVA tables, coefficients, p-values, VIF, efficiency, prediction
  variance. These are the numbers users reason about and are what the
  bundle guarantees.
- **Plot images are not** guaranteed byte-identical: they are re-rendered
  locally, so font and renderer drift can cause pixel-level differences.
  The numeric content driving the plots stays reproducible.

Known gaps (run-order randomisation without a captured seed;
`ToolCall.tool_version` not yet populated) are tracked in `TODO.md` and
surfaced as per-export warnings in the bundle README.

### 9.2 Public exposure

Reproducible-code formats carry raw tool inputs and are **only** served
behind owner authentication. The public-share export endpoint refuses
`py` / `ipynb` / `md_code` / `zip`.

---

## 10. Sharing

An owner can publish a read-only snapshot of an experiment via a
revocable share link.

- `POST /experiments/{id}/shares` — create a share. Generates an opaque
  token (`SHARE_TOKEN_LENGTH`, default 32 bytes), with a default 30-day
  expiry (`SHARE_TOKEN_EXPIRE_DAYS`) or no expiry, and an `allow_results`
  flag controlling whether response data is visible (design-only vs. full
  share).
- `GET /experiments/{id}/shares` — list the owner's shares.
- `DELETE /shares/{token}` — revoke.
- `GET /public/experiments/{token}` — unauthenticated read of the
  snapshot: name, factors, design matrix, evaluation, owner display name,
  view count, expiry, and — only if `allow_results` — the results.
- `GET /public/experiments/{token}/export` — unauthenticated export,
  restricted to report formats (no reproducible-code formats).

Public-share endpoints are rate-limited (`PUBLIC_SHARE_RATE_LIMIT`,
default `30/minute`) to resist token enumeration. The public view also
carries a signup call-to-action to convert visitors.

---

## 11. Billing & BYOK

### 11.1 Cost accounting

`app.services.pricing` owns a rate table (USD per million input/output
tokens, keyed by model-id prefix with longest-prefix match) and the
markup. The current markup is **0.50** — the customer is billed at 1.5×
the raw Anthropic cost.

Cost is snapshotted **per message** at call time: the input/output rates,
raw cost, markup rate, markup cost, and billable amount are all frozen
onto the `messages` row. Historical rows therefore stay accurate after
the rate table or markup later changes. Conversations carry running
totals. A `user_balances` table holds a prepaid USD/token balance that
admins can top up; balance *consumption* is not yet wired into the agent
loop.

### 11.2 Bring-Your-Own-Key (BYOK)

A user may supply a personal Anthropic API key. When present, the agent
calls Anthropic with that key, the user is billed directly by Anthropic,
and **no platform markup is applied** (`markup_cost_usd = 0`,
`billable_to_user_usd = 0`); the message row is flagged `byok_used` and
the raw cost is still computed for analytics.

**Cryptographic design** — three-layer keying, AES-256-GCM + Argon2id,
all server-side:

| Key | Source | Purpose |
|-----|--------|---------|
| **Token** | User-supplied | The Anthropic API key itself. |
| **DEK** | 32 random bytes | AES-GCM-encrypts the token at rest; long-lived, survives password changes. |
| **KEK** | `Argon2id(password, salt, params)` | Wraps the DEK at rest. |
| **Session wrap key** | 32 random bytes per session | AES-GCM-wraps the DEK on the `sessions` row; itself encrypted under the server-side `BYOK_MASTER_KEY`. |

Lifecycle:

- **Enrolment** (`POST /byok/enroll`) — the user re-enters their password
  (the session does not hold it). The server pre-verifies the key against
  Anthropic, derives the KEK, generates the DEK, encrypts the token, wraps
  the DEK under both the KEK and the current session key, and persists.
- **Login** — after password verification, the KEK is derived, the DEK
  unwrapped, and re-wrapped under a fresh per-session key on the new
  session row.
- **Chat request** — the session's wrapped DEK is unwrapped, the token
  decrypted, handed to the SDK, and dropped; plaintext lives only inside
  the request's stack frames.
- **Password change** — the DEK is re-wrapped under the new KEK; the token
  ciphertext is untouched.
- **Password reset** — the DEK is unrecoverable by design; the token
  status becomes `orphaned` and the UI asks the user to re-enrol.
- **Rotation / removal** (`POST /byok/rotate`, `DELETE /byok`) — replace
  or wipe the key. `GET /byok` reports status; `POST /byok/test` re-checks
  the stored key.

`byok_token_status` is one of `absent` / `active` / `rejected` (Anthropic
returned `401`) / `orphaned`. An append-only `byok_credentials_history`
table records enrol/rotate/delete actions with **no key material**.

**Honest threat boundary.** BYOK defends against database-dump and
backup theft and against an SRE running an ad-hoc `SELECT`. It does **not**
defend against a malicious maintainer with deploy access, who could patch
the login endpoint to capture passwords — a fundamental limitation of
server-side, password-based encryption. The `/profile` UI states this
verbatim. Logs and any error reporting scrub headers and any field
matching `*api_key*` / `*token*` / `anthropic*`.

---

## 12. Admin console

The admin area (gated by `require_admin`) provides:

- **Signups** — list pending requests, approve (assigning or creating a
  role) or reject.
- **Users** — a searchable list with per-user aggregates (cost, tokens,
  conversation/experiment/feedback counts). Admins can toggle
  `is_admin` / `is_active`, change a role, issue a password-reset link,
  and top up a user's balance. Login IPs are resolved to an ISO-3166
  country via an optional MaxMind GeoLite2 database (`geoip_service`); if
  the database is absent, country lookup is silently skipped.
- **Roles** — create / edit / delete roles.
- **Feedback** — review user feedback submissions (topic, message, page
  URL, screenshot) and reply.
- **Events** — the `admin_events` operational log: an append-only audit
  trail of backups, restores, restore drills, balance top-ups, signup
  approvals, and periodic snapshots, filterable by type and status, with
  an expandable JSON payload.

Separately, a read-only **`sqladmin`** database browser is mounted at
`/admin`. It uses its own session cookie (signed with `API_SECRET_KEY`)
and only `is_admin` users can sign in.

### 12.1 Feedback

Any authenticated user can submit feedback (`POST /feedback`) with a
topic, message, page context, and an optional screenshot PNG. Submission
is rate-limited and triggers background email notifications to the user
and to admins. The screenshot is fetched via
`GET /feedback/{id}/screenshot` (owner or admin).

---

## 13. Hosted MCP endpoint

An optional **Model Context Protocol** surface exposes the
`process-improve` tool registry over HTTP so external agents can call the
DOE tools. It is **off by default** (`MCP_ENABLED = false`) and mounts
only when an operator enables it. When on, it provides
`GET {prefix}/tools` and `POST {prefix}/tools/{tool_name}`, gated by
authentication, a rate limit (`MCP_RATE_LIMIT`), and a per-identity daily
CPU-second budget (`MCP_DAILY_CPU_SECONDS`, default 3600) tracked in the
`tool_usage` table.

---

## 14. Data model

All application state is in PostgreSQL. Models inherit from
`app.db.base.Base`. Primary keys are UUIDs (`gen_random_uuid()`) unless
noted.

| Table | Purpose / notable columns |
|-------|---------------------------|
| `roles` | `name` slug (unique), `description`, `is_builtin`. Seven seeded. |
| `users` | `email` (unique), `password_hash` (bcrypt), `display_name`, `role_id`, `is_admin`, `is_active`, `last_login_at/ip`, `country`, `timezone`, and the BYOK columns (`byok_token_ciphertext`, `byok_dek_wrapped`, `byok_kek_salt`, `byok_kdf_params`, `byok_token_status`, …). |
| `sessions` | PK is the 32-byte opaque session id; `public_id`, `user_id`, `family_id`, idle/absolute expiry, `last_used_at`, `revoked_at`, `user_agent`, `ip`, and the BYOK session wraps. |
| `signup_requests` | `email`, `use_case`, `status`, `requested_role`, `role_id`, `invite_token`, `accepted_disclaimers`, `admin_note`. |
| `setup_tokens` | `user_id`, `token`, `purpose` (`setup`/`reset`), `expires_at`, `used_at`. |
| `conversations` | `user_id`, `title`, `status`, `system_prompt`, token/cost running totals, `starred`. |
| `messages` | `conversation_id`, `sequence`, `role`, `content`, tool-block fields, per-message token counts, the frozen per-message cost snapshot, and `byok_used`. |
| `tool_calls` | Per-invocation audit trail: `tool_name`, `tool_input/output`, `status`, timing, `agent_turn`, `call_order`, `turn_id`, process RSS/CPU snapshot, payload sizes. |
| `chat_events` | Append-only SSE event log for stream resume: `turn_id`, `sequence` (unique together), `event_type`, `data`. |
| `experiments` | `user_id`, `name`, `status`, `design_type`, `factors`, `design_data`, `results_data`, `evaluation_data`, `conversation_id`. |
| `experiment_shares` | `experiment_id`, opaque `token`, `allow_results`, `expires_at`, `view_count`. |
| `simulators` | `sim_id`, `public_summary`, `private_state` (hidden model), `reveal_request_count`. |
| `user_balances` | Prepaid `balance_usd` / `balance_tokens` per user. |
| `tool_usage` | Per-user, per-day CPU-second accumulation for the MCP budget. |
| `user_feedback` | `topic`/message, page context, screenshot blob, reply state. |
| `admin_events` | Operational audit log: `event_type`, `source`, `status`, `payload`, timing, `error_message`. |
| `byok_credentials_history` | Append-only enrol/rotate/delete trail; no key material. |

### 14.1 Migration discipline

The schema began as a **single initial revision**
(`alembic/versions/0001_initial_schema.py`); every later change is a new
revision chained on top (0002 admin events, 0003 chat events, 0004
tool-call telemetry, 0005 signup disclaimers, 0006 user feedback, 0007
balance, 0008 simulators, 0009 sessions, 0010 remove `other` role, 0011
BYOK). `0001` is never edited in place.

Because production uses a **blue-green** deploy in which two code versions
run against the same database during a cutover, every migration merged to
`main` must be backwards-compatible with the previous code version
(**expand/contract**): expand-safe changes (add a table, add a nullable
column, add an index concurrently, widen a column, backfill) may ship
with the code that uses them; contract-destructive changes (drop a
column/table, tighten `NULL`→`NOT NULL`, rename a column) must wait for a
subsequent deploy, after the old code is gone.

---

## 15. API surface

All routes are under `/api/v1`. **Auth** column: *public* = no
credential; *cookie/key* = `require_auth`; *admin* = `require_admin`;
*token* = opaque share/setup token is itself the credential.
State-changing routes additionally require CSRF unless the caller used an
API key.

### Health
| Method & path | Auth | Purpose |
|---|---|---|
| `GET /health` | public | Liveness probe. |
| `GET /health/ready` | public | Readiness — Postgres + Neo4j connectivity. |
| `GET /health/llm` | public | LLM status snapshot for the site banner. |

### Auth & sessions
| Method & path | Auth | Purpose |
|---|---|---|
| `POST /auth/register` | public | Disabled — returns `403`. |
| `POST /auth/login` | public | Sign in; sets session + CSRF cookies. |
| `POST /auth/logout` | cookie | Revoke current session. |
| `POST /auth/logout-all` | cookie | Revoke the whole session family. |
| `GET /auth/me` | cookie/key | Current user profile + balance. |
| `GET /auth/sessions` | cookie/key | List active sessions. |
| `DELETE /auth/sessions/{public_id}` | cookie/key | Revoke one device. |
| `POST /auth/password-reset/request` | public | Request a reset link (`202`). |
| `GET /auth/setup/validate` | token | Validate a setup/reset token. |
| `POST /auth/setup/complete` | token | Set password, mint session. |
| `POST /auth/password/change` | cookie/key | Change password. |

### Signup & roles
| Method & path | Auth | Purpose |
|---|---|---|
| `POST /signup/request` | public | Submit a signup request. |
| `GET /signup/invite/validate` | token | Validate an invite token. |
| `POST /signup/invite/register` | token | Complete registration. |
| `GET /signup/admin/list` | admin | List signup requests. |
| `POST /signup/admin/{id}/approve` | admin | Approve, assign/create role. |
| `POST /signup/admin/{id}/reject` | admin | Reject with optional note. |
| `GET /roles` | public | List roles (for the signup form). |
| `POST /roles` · `PATCH /roles/{id}` · `DELETE /roles/{id}` | admin | Manage roles. |

### Chat, designs & tools
| Method & path | Auth | Purpose |
|---|---|---|
| `POST /chat` | cookie/key | Stream an agent turn (SSE). |
| `GET /chat/{id}/resume` | cookie/key | Resume a dropped stream. |
| `GET /chat/{id}/messages` | cookie/key | Load conversation messages. |
| `POST /designs/generate` | cookie/key | Run `generate_design` directly. |
| `GET /tools` · `POST /tools/execute` | cookie/key | List / run a tool. |

### Experiments, uploads & shares
| Method & path | Auth | Purpose |
|---|---|---|
| `GET /experiments` | cookie/key | List experiments. |
| `GET /experiments/{id}` | cookie/key | Experiment detail. |
| `PATCH /experiments/{id}` · `DELETE /experiments/{id}` | cookie/key | Update / delete. |
| `POST /experiments/{id}/results` · `GET …/results` | cookie/key | Record / read results. |
| `POST /experiments/{id}/evaluate` | cookie/key | Re-run design evaluation. |
| `GET /experiments/{id}/export` | cookie/key | Export (8 formats). |
| `POST /experiments/{id}/shares` · `GET …/shares` | cookie/key | Create / list shares. |
| `DELETE /shares/{token}` | cookie/key | Revoke a share. |
| `POST /experiments/uploads` | cookie/key | Upload a design file. |
| `POST /experiments/uploads/{id}/answers` | cookie/key | Answer parsing questions. |
| `POST /experiments/uploads/{id}/finalize` | cookie/key | Finalise the import. |

### Public shares
| Method & path | Auth | Purpose |
|---|---|---|
| `GET /public/experiments/{token}` | token | Read a shared snapshot. |
| `GET /public/experiments/{token}/export` | token | Export (report formats only). |

### Feedback, BYOK & admin
| Method & path | Auth | Purpose |
|---|---|---|
| `POST /feedback` | cookie/key | Submit feedback. |
| `GET /feedback/{id}/screenshot` | cookie/key | Fetch a feedback screenshot. |
| `GET /byok` · `POST /byok/enroll` · `POST /byok/rotate` · `POST /byok/test` · `DELETE /byok` | cookie/key | BYOK lifecycle. |
| `GET /admin/users` · `PATCH /admin/users/{id}` | admin | List / update users. |
| `POST /admin/users/{id}/reset-password` | admin | Issue a reset link. |
| `POST /admin/users/{id}/balance/topup` | admin | Top up a balance. |
| `GET /admin/events` | admin | Operational event log. |
| `GET /admin/feedback` · `POST …/{id}/reply` · `PATCH …/{id}` | admin | Review / reply to feedback. |
| `GET {mcp}/tools` · `POST {mcp}/tools/{name}` | cookie/key | MCP (only when enabled). |

---

## 16. Frontend specification

### 16.1 Pages

The SPA prerenders routes and runs with SSR disabled.

| Route | Purpose |
|-------|---------|
| `/` | Landing page; CTA differs for authenticated vs. anonymous visitors. |
| `/login` | Email/password sign-in. |
| `/register` | Signup-request form (role selector, use case, disclaimer). |
| `/register/complete` · `/auth/setup` | Token-gated account completion / password setup. |
| `/chat` | The agent chat — primary interaction surface. |
| `/experiments` | Project list with stat cards, status filters, "import from file". |
| `/experiments/{id}` | Experiment detail: design matrix, evaluation, results entry, export/share. |
| `/profile` | Account info, BYOK enrolment, active-session management. |
| `/admin/*` | Signups, users, roles, feedback, events. |
| `/share/{token}` | Public read-only experiment view. |
| `/prototype` | Embedded design-reference prototype. |

A persistent top-nav layout guards authenticated routes (redirecting to
`/login` once the boot check completes) and shows a system banner driven
by the LLM-status poll.

### 16.2 Components

Chat: `ChatWindow`, `MessageBubble`, `PlanChecklist`, `ToolResultCard`.
Data & forms: `ExperimentDataTable` (with an `F2` full-screen
`DataTableModal`), `ResultsEntryForm`, `DesignEvaluationBlock`.
Visualisation: `BaseChart` (lazy-loads `echarts`, and `echarts-gl` only
for 3-D). Export & share: `ExportMenu`, `ShareModal`, `SignupCTA`.
Import: `UploadWizardModal`. Settings/auth: `BYOKSection`, `ReauthModal`.

### 16.3 State

Svelte 5 rune-based stores: `auth` (bootstraps from `/auth/me`), `chat`
(messages, streaming state, SSE resume, detail level), `experiments`
(list/detail, pagination, filters), `anthropicStatus` (polls
`/health/llm` while the tab is visible), `reauth` (shared promise for the
inline re-auth modal).

### 16.4 API & streaming clients

`authFetch` is the single fetch wrapper (cookies, CSRF, 401-reauth, 5xx
surfacing). The SSE client uses `fetch` + a manual SSE parser (because
the chat request is a `POST`, not an `EventSource`) tolerant of both
`\n` and `\r\n` line endings, and supports the resume flow of §6.6.
Assistant text is rendered through `marked` + KaTeX and sanitised with
DOMPurify.

---

## 17. Non-functional requirements

### 17.1 Security

- The server refuses to start in production with weak or missing secrets
  (`API_SECRET_KEY`, `POSTGRES_PASSWORD`, `NEO4J_PASSWORD`) — validated in
  the lifespan startup.
- OpenAPI docs (`/docs`, `/redoc`, `/openapi.json`) are disabled in
  production to reduce attack surface.
- A log-injection guard strips CR/LF (CWE-117) and redacts secrets
  (`sk-ant-*`, bearer tokens, `api_key=`/`password=` patterns) from every
  log record.
- CORS origins, methods, and headers are environment-driven and tighten
  in production.
- DOE tool calls run in a subprocess sandbox (`TOOL_SAFE_MODE`, default
  on) with a wall-clock timeout, a memory cap, and matrix-size limits;
  `ToolExecutionError` subclasses map to HTTP 408/413/429/507.
- Per-endpoint rate limits (slowapi): chat `10/min`, auth `5/min`,
  register `3/hour`, feedback `20/hour`, public share `30/min`.

### 17.2 Reliability

- SSE streams are resumable (§6.6); revocation never kills an in-flight
  stream (§5.4).
- Docker healthchecks cover the app, Postgres, Neo4j; `restart:
  unless-stopped` on every service.
- The blue-green deploy drains long-lived SSE streams before retiring the
  old container.

### 17.3 Observability

- `GET /health/llm` exposes a rolling Anthropic error rate and p95
  latency, polled by the SPA to drive a global status banner; an hourly
  background task also writes an LLM-performance rollup to `admin_events`.
- Per-turn chat latency is written to a rotating JSON-Lines timing log
  for offline analysis; the `Makefile` ships `jq`-based query targets.
- `admin_events` is the durable operational audit trail.

### 17.4 Performance

- All database access is async (asyncpg / Neo4j async driver).
- The blocking agent loop runs off the event loop in a worker thread.
- Token persistence is batched (§6.7); `sessions.last_used_at` writes are
  throttled.
- ECharts and `echarts-gl` are lazy-loaded on demand.

---

## 18. Deployment & operations

### 18.1 Containers

`docker-compose.yml` defines the app (FastAPI on 8000, with `app-blue` /
`app-green` profile variants for blue-green deploys), the frontend
(SvelteKit built to static assets, served by nginx), `postgres:16-alpine`,
a separate `postgres-test` instance on 5433, and `neo4j:5-community`.
Redis is present but commented out. All ports bind to `127.0.0.1`; a
Caddy reverse proxy fronts the stack and terminates TLS.

### 18.2 CI/CD

GitHub Actions workflows: backend CI (ruff lint + format check, pytest
against a real Postgres), frontend CI (`svelte-check`, vitest, build),
Docker image builds, MkDocs docs build/deploy, a release workflow that
tags `v<version>` on merge to `main`, and weekly CodeQL analysis.
Dependabot keeps actions, pip, npm, and Docker base images current.

### 18.3 VPS deployment & blue-green

The deployment guide (`docs/deployment/vps-guide.md`) walks 14 phases
from server hardening to backups. Redeployment can be a simple
`git pull && docker compose up --build` (a few seconds of downtime) or a
**blue-green** cutover (`scripts/deploy-blue-green.sh`): build the idle
colour, health-check it, run `alembic upgrade head` in it, flip the Caddy
upstream, drain in-flight SSE streams for `DRAIN_SECONDS` (default 120),
then stop the old colour. Rollback flips Caddy back.

### 18.4 Backups

`scripts/backup-postgres.sh` dumps Postgres to S3-compatible object
storage (Hetzner) with grandfather-father-son retention, Object Lock
(WORM) immutability, and sha256 verification. A weekly `restore-drill.sh`
restores the newest backup to a scratch database and smoke-queries it.
Every run records its history in `admin_events`.

---

## 19. Engineering conventions

- **Versioning** — `backend/pyproject.toml` `[project] version`, 3-part
  semver, auto-bumped on every code/config PR: PATCH for fixes/docs/CI,
  MINOR for features.
- **Backend style** — Python ≥ 3.12; 120-char hard line limit; ruff
  (rules E, W, F, I, N, UP, B, S, T20, SIM) for lint *and* format; a
  pre-commit hook mirrors CI.
- **Frontend style** — Svelte 5 runes only; TypeScript strict; Tailwind
  utilities; ECharts only.
- **Testing** — backend pytest runs against a real Postgres test database
  (port 5433); the conftest builds the schema once via Alembic and wraps
  each test in a rolled-back transaction, and overrides the auth
  dependencies with synthetic stubs. Frontend uses vitest.
- **Configuration** — `.env.example` at the repo root is the single
  source of truth for every environment variable; it must stay in sync
  with `config.py` and the deployment guide.
- **Git/PR** — commit per logical change, push regularly, open a PR as
  soon as the branch has its first commit, plan-first PRs for non-trivial
  features. Dependency lock files are refreshed manually and never
  committed from an automated session.
- **`TODO.md`** — the living backlog of cross-cutting follow-ups; checked
  at the start of every session and kept in sync with every PR.

---

## 20. Future scope

The following are designed or scaffolded but **not** implemented in
application behaviour today:

- **Neo4j knowledge graph.** The Neo4j driver is wired up and the
  readiness probe verifies connectivity, but no application code reads or
  writes the graph. The intended node/relationship ontology (users,
  experiments, factors, responses, designs, models, domains) is sketched
  in `docs/architecture/knowledge-graph.md`.
- **LangGraph agent orchestration.** The current agent is a hand-written
  tool-use loop using the raw Anthropic SDK. A migration to LangGraph for
  multi-step workflow orchestration is planned.
- **Agent observability tracing** — LangSmith or Langfuse.
- **Redis** — present but commented out in `docker-compose.yml`; intended
  for agent conversation caching when warranted.
- **Balance enforcement.** `user_balances` exists and admins can top it
  up, but the agent loop does not yet debit a balance or block on a zero
  balance.
- **`results_data.included` in analysis.** The per-row include/exclude
  flag is recorded but the model-fitting path does not yet drop excluded
  rows.
- **`ToolCall.tool_version`** is not yet populated, so reproducible
  bundles pin the currently installed `process-improve` rather than the
  version used at each call.

Smaller deferred items are tracked in `TODO.md`.

---

## 21. Glossary

| Term | Meaning |
|------|---------|
| **DOE** | Design of Experiments — planning experiments so that factor effects can be estimated efficiently. |
| **Factor / response** | An input variable that is deliberately varied / a measured outcome. |
| **RSM** | Response Surface Methodology — fitting a curved model (e.g. central composite, Box–Behnken designs) to optimise a response. |
| **Resolution / aliasing** | How severely factor effects are confounded with one another in a fractional design. |
| **process-improve** | The separate Python package providing the deterministic DOE/statistics tools the agent calls. |
| **Agent loop** | The synchronous, multi-turn Anthropic tool-use loop, capped at 10 turns. |
| **Meta-tool** | `record_plan` / `update_plan` — local no-op tools that drive the UI plan checklist. |
| **Simulator** | A synthetic process with a hidden model, for planning/demonstration. |
| **SSE** | Server-Sent Events — the one-way stream carrying agent output to the browser. |
| **BYOK** | Bring-Your-Own-Key — a user-supplied Anthropic API key, stored encrypted. |
| **DEK / KEK** | Data Encryption Key / Key Encryption Key — the two inner layers of BYOK keying. |
| **Expand / contract** | The migration discipline that keeps every schema change backwards-compatible during a blue-green deploy. |
| **Blue-green** | A zero-downtime deploy where a new container colour takes over from the old one after a drain window. |
