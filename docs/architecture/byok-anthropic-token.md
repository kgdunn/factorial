# Bring-Your-Own Anthropic API Token

Design discussion for letting sophisticated users supply their own Anthropic API
key, stored encrypted, so they pay Anthropic directly and bypass the platform
markup defined in `backend/src/app/services/pricing.py`
(`CURRENT_MARKUP_RATE = 0.50`).

## Problem

Today every user is billed through the platform's Anthropic key, which carries
a 50% markup on raw token cost. Sophisticated users already have an Anthropic
account and would prefer to:

1. Paste a personal Anthropic API key into a profile UI.
2. Have it stored such that the maintainer (with database **and** code access)
   cannot read it from the database.
3. Have it transparently used at request time in place of the platform key,
   with no markup applied.

## Critical Assessment — what we can and cannot deliver

!!! warning "Honest scope"
    The user-facing requirement *"not even the maintainer can see the token"*
    is **only partially achievable** on a server-rendered, password-based web
    app. Be explicit about this in the UI.

A maintainer with deploy access can patch
`backend/src/app/api/v1/endpoints/auth.py` to log the user's plaintext password
(or any key derived from it) on the next sign-in and harvest the token within
hours. This is true for **any** server-side, password-based encryption scheme —
the password hash is not a hardware boundary, it's just a value living in the
same Python process.

Genuine zero-knowledge against a deploy-capable attacker requires either:

- **Browser-side WebCrypto with an audited static frontend** — subresource
  integrity, reproducible builds, ideally third-party-hosted JS bundle. None of
  this exists today and adding it is a much bigger project than BYOK itself.
- **Hardware enclave or HSM** at the server.

**What we *can* deliver well:** strong protection against accidental database
leakage — Postgres dumps, backups, ad-hoc `SELECT` queries by an SRE, leaked
snapshots. This is a real and common threat class and is worth defending.

The `/profile` UI must say so verbatim:

> Your token is encrypted with a key derived from your password. We cannot
> read it from a database backup or query. A maintainer who modifies the
> application code could intercept it when you sign in — this is a
> fundamental limitation of server-side password-based encryption. If you
> need stronger guarantees, do not use BYOK; use Anthropic's tools directly.

## Rejected alternative: browser-side encryption (Design B)

The agent loop in `backend/src/app/services/agent_loop.py` is **multi-turn and
server-driven** — one inbound HTTP request opens an SSE stream, then the server
runs `client.messages.stream(...)` for up to 10 turns, calling Anthropic
directly for each turn.

This means the browser can hand the decrypted token to the server only **once**,
at SSE open. After that the plaintext token sits in process memory anyway. So
browser-side encryption is functionally identical to server-side encryption from
a leakage standpoint, while doubling frontend complexity (WebCrypto key
management, sessionStorage hygiene, re-derivation on every page load) and
*still* not delivering true zero-knowledge unless we also redesign the agent
loop to proxy each turn through the browser.

Given the multi-turn server agent, Design B's marginal security gain is
essentially zero. Rejected.

## Chosen design (Design A)

Three-layer keying, all server-side, using AES-256-GCM and Argon2id.

| Key | Source | Lifetime | Purpose |
|-----|--------|----------|---------|
| **Token** | User-supplied | Until user removes / rotates | The actual Anthropic API key |
| **DEK** (Data Encryption Key) | 32 random bytes | Long-lived; survives password change | AES-GCM-encrypts the token at rest |
| **KEK** (Key Encryption Key) | `Argon2id(password, salt, params)` | Derived on-demand | Wraps the DEK at rest |
| **Session DEK wrap** | 32 random bytes per session | One session | AES-GCM-wraps the DEK in the `sessions` row |

The cookie value stays unchanged (still an opaque session id). Putting the DEK
directly in a cookie was rejected because cookies leak too easily into Sentry
payloads, access-log dumps, and browser-extension scopes.

The per-session wrap key is itself encrypted at rest under a server-side master
key from a fresh env var `BYOK_MASTER_KEY` (32 bytes, base64), so a database
dump alone cannot decrypt the wrapped DEK on a session row.

### Lifecycle

**Enrollment** (user pastes a key in `/profile`)
:   The active session does not have the password in scope, so the form
    requires the user to re-enter their password. Server: derive KEK → generate
    DEK → AES-GCM-encrypt token under DEK → wrap DEK under KEK → persist
    ciphertexts → also wrap the new DEK under the current session key.

**Login**
:   bcrypt verify → if BYOK is active for this user, derive KEK from the
    submitted password → unwrap DEK → wrap DEK under a fresh per-session key →
    write the wrapped DEK to the new session row. Discard plaintext password
    and KEK before returning the response.

**Chat request**
:   Look up session → unwrap DEK using the per-session key → decrypt token →
    pass to the Anthropic SDK → discard. Token plaintext lives only inside the
    current request's stack frames.

**Password change**
:   Verify old password → derive old KEK → unwrap DEK → derive new KEK →
    re-wrap DEK. Token ciphertext is unchanged.

**Password reset**
:   The DEK is permanently unrecoverable (this is the point). Mark
    `byok_token_status = 'orphaned'`; the UI prompts the user to re-enter the
    token on next login. Do **not** silently delete — the user needs to know
    why their key stopped working.

**User-initiated removal**
:   Wipe ciphertext columns and any wrapped DEKs in active sessions.

### Schema additions

`users` table
:   - `byok_token_ciphertext BYTEA NULL` — AES-GCM blob (`nonce ‖ ct ‖ tag`)
    - `byok_dek_wrapped BYTEA NULL`
    - `byok_kek_salt BYTEA NULL` (16 bytes)
    - `byok_kdf_params JSONB NULL` (`{"variant":"argon2id","m":...,"t":...,"p":...}`)
    - `byok_token_last_verified_at TIMESTAMPTZ NULL`
    - `byok_token_status` enum: `absent | active | rejected | orphaned`

`sessions` table
:   - `byok_dek_session_wrapped BYTEA NULL`
    - `byok_session_key_encrypted BYTEA NULL` (encrypted under `BYOK_MASTER_KEY`)

`messages` table
:   - `byok_used BOOLEAN NOT NULL DEFAULT false` — for analytics, support, and
      audit ("why didn't I get charged?")

New `byok_credentials_history` table
:   Append-only audit trail. **No key material.** Records `{user_id, action,
    started_at, ended_at, last_verified_at, status}`. Key rotation is modelled
    as delete-then-create so the trail shows clear `[T1, T2)` intervals.

### Pricing & billing

`backend/src/app/services/pricing.py` stays a pure function (rates × tokens).
The agent-loop call site decides whether the user is billed:

- BYOK request: `markup_cost_usd = Decimal(0)`, `billable_to_user_usd = 0`,
  `byok_used = True`. `raw_cost_usd` is still computed for analytics — it's a
  real cost, just not ours.
- Platform-key request: unchanged from today.

This keeps historical `raw_cost_usd` / `markup_cost_usd` semantics intact, and
makes BYOK rows trivially identifiable (`billable_to_user_usd = 0 AND
raw_cost_usd > 0`) for support and margin reporting.

## Operational hardening (non-negotiable)

- **Log scrubbing.** Logger config and Sentry `before_send` must scrub headers
  and any field matching `*api_key*`, `*token*`, `anthropic*`. Add a regression
  test that runs a full BYOK chat and asserts the token's bytes never appear in
  captured stdout/stderr or Sentry payloads.
- **Typed SSE error events.** Distinguish Anthropic 401 (key rejected → flip
  `byok_token_status` to `rejected`, surface to UI) from 429 (rate limited —
  surface but don't flip status) from 5xx (transient — retry once).
- **Pre-save verification.** `POST /api/v1/byok/enroll` should ping Anthropic
  with `max_tokens: 1` before persisting; reject the enrollment if Anthropic
  returns 401.
- **No silent decrypt failures.** AES-GCM tag mismatch on unwrap must raise.
  Wrong-password attempts cannot return garbage bytes.
- **`BYOK_MASTER_KEY` rotation runbook.** Re-encrypt all
  `byok_session_key_encrypted` values, or accept that all sessions are
  invalidated on rotation (forced re-login).

## Out of scope

- WebCrypto / browser-side encryption (rejected — see above).
- HSM / enclave.
- Key escrow or recovery (deliberately impossible — that's the point).
- Shared/team tokens.

## Threat model summary

| Attacker | Defended? |
|----------|-----------|
| Database dump / backup theft | **Yes** |
| SRE running ad-hoc `SELECT` | **Yes** |
| Malicious maintainer with deploy access | **No** — they can patch the login endpoint to capture passwords |
| Process memory inspection on a live server | **No** — token is plaintext during a request |
| Compromised SDK that exfiltrates headers | **No** — out of scope |
| Compromised browser / browser extension reading the user's password as they type | **No** — out of scope |

If the unmet rows are unacceptable to a given user, BYOK is the wrong feature
for them; recommend Anthropic-direct tooling instead.
