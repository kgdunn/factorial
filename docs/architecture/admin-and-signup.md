# Admin, signup & approval

How user accounts, admin privileges, and roles are created and managed.

This document describes the **current** design.

## 1. The one-time admin bootstrap

There is **no "admin by environment variable"**. Admin status is a column on the `users` table (`users.is_admin`). A fresh install therefore needs one manual step to create the first admin.

From the `backend/` directory:

```bash
# Create the first admin.  Prints a one-time setup URL.
uv run python -m app.cli create-admin --email admin@example.com --name "Jane Doe"
```

The command:

1. Creates a `users` row with `is_admin=TRUE`, `password_hash=''`, `is_active=TRUE`.
2. Generates a `setup_tokens` row (`purpose="setup"`, 72 h expiry).
3. Prints `https://<frontend>/auth/setup?token=...` to stdout.
4. If SMTP is configured, also emails the link to the admin.

The admin opens the link, sets a password, and is logged in. The token is single‑use (`used_at` set on completion).

Additional admin‑management subcommands:

| Command                            | What it does                                                       |
| ---------------------------------- | ------------------------------------------------------------------ |
| `app.cli create-admin --email e`   | Bootstrap an admin, print setup URL                                |
| `app.cli list-admins`              | List email + created_at of all `is_admin` users                    |
| `app.cli promote --email e`        | Flip `is_admin=TRUE` on an existing user                           |
| `app.cli demote --email e`         | Flip `is_admin=FALSE` (refuses to demote the last remaining admin) |
| `app.cli reset-password --email e` | Issue a setup/reset token and print the URL                        |

These commands also work after deployment — anyone with shell access to the container can rescue a locked‑out account. (In production, `docker compose exec app uv run python -m app.cli ...`.)

## 2. The signup / approval / invite flow

End‑to‑end, for a non‑admin user:

```
[ prospect ]                         [ admin ]                     [ user ]
    │                                    │                            │
    │ POST /signup/request               │                            │
    │ { email, use_case, requested_role }│                            │
    │ ──► signup_requests row (pending)  │                            │
    │                                    │                            │
    │                   ◄── email: admin notified                     │
    │                                    │                            │
    │                                    │ GET  /admin/signups        │
    │                                    │ POST /admin/{id}/approve   │
    │                                    │   { role_id  OR            │
    │                                    │     new_role: {name, desc}}│
    │                                    │                            │
    │                                    │ ──► signup: status=approved│
    │                                    │     invite_token issued    │
    │                                    │     role_id recorded       │
    │                                    │                            │
    │                                    │ ── email: invite link ──► │
    │                                    │                            │
    │                                    │ GET  /signup/invite/validate
    │                                    │ POST /signup/invite/register
    │                                    │   { token, password,       │
    │                                    │     display_name }         │
    │                                    │                            │
    │                                    │ ──► users row created      │
    │                                    │     role_id from signup    │
    │                                    │     signup: status=registered
    │                                    │                            │
    │                                    │    ◄── Set-Cookie: factorial_session
```

Key properties:

- **Role is mandatory.** The applicant must pick a role at signup (or pick "Other" and describe their role in free text); the admin must assign a role (existing or newly created) at approval. Role is used in the LLM system prompt, so we require it up front.
- **`signup_requests.requested_role`** is what the applicant _asked_ for — a slug from the roles list, or an `other:<freetext>` string when they picked "Other". The admin never trusts this directly.
- **`signup_requests.role_id`** is the _decided_ role. It is set by the admin at approval time: either assign an existing role or create a brand new role as part of the approval. The user's final `users.role_id` is copied from here on registration.
- The admin UI shows the applicant's `requested_role` next to a role dropdown and a "Create new role from this request" control. Nothing is auto‑created — the admin makes the call. The Approve button is disabled until a role choice is valid.
- `signup_requests.email` is unique at the "in‑flight" stage (pending/approved). Once a user registers, the signup row stays as an audit record but the email is now also on `users.email`.
- Rejected signups can be re‑submitted after an admin clears the old row (or we relax the uniqueness — not done yet).

## 3. Password reset & setup tokens

Both first‑time admin setup and regular password reset use the same `setup_tokens` table.

| Column       |                                                     |
| ------------ | --------------------------------------------------- |
| `id`         | UUID primary key                                    |
| `user_id`    | FK → `users.id`, CASCADE delete                     |
| `token`      | URL‑safe string, unique                             |
| `purpose`    | `"setup"` (new account) or `"reset"` (existing)     |
| `expires_at` | 72 h after creation                                 |
| `used_at`    | Null until consumed; set on successful password set |

Endpoints:

- `POST /auth/password-reset/request` — public, rate‑limited. If the email matches an active user, issues a token and emails a link. Always returns 200 (no email enumeration).
- `GET /auth/setup/validate?token=...` — checks token exists, is `setup`‑or‑`reset`, and not expired/used. Returns the email for display.
- `POST /auth/setup/complete` — takes `{ token, password }`, sets the password, marks token used, mints a session and Sets the `factorial_session` + `factorial_csrf` cookies. Works for both purposes.
- `POST /auth/password/change` — authenticated, `{ current_password, new_password }`.

## 4. Roles

Stored in a `roles` table with `(id, name, description, is_builtin, created_at, updated_at)`. The migration seeds the eight existing `background` values as built‑in roles. `users.role_id` is a nullable FK.

Public endpoint:

- `GET /roles` — list of `{id, name, description}`. Unauthenticated so the signup form can populate its dropdown.

Admin endpoints:

- `POST /admin/roles` — create `{name, description}`
- `PATCH /admin/roles/{id}` — edit description (name is immutable once created to avoid breaking references)
- `DELETE /admin/roles/{id}` — only allowed when `is_builtin=FALSE` and no users reference it

The role's `name` is a slug (`[a-z0-9_]+`, ≤50 chars). The slug is what's interpolated into the LLM system prompt, so it's constrained to prevent prompt injection even though roles are admin‑created.

## 5. Admin UI

`/admin` has three tabs:

| Tab     | Path             | Purpose                                                                 |
| ------- | ---------------- | ----------------------------------------------------------------------- |
| Signups | `/admin/signups` | Pending list, approve/reject, pick or create role at approval           |
| Users   | `/admin/users`   | List users, toggle admin, change role, deactivate, issue password reset |
| Roles   | `/admin/roles`   | Create/edit/delete roles                                                |

Everything behind the admin UI calls endpoints protected by the `require_admin` dependency, which checks `current_user.is_admin` on the DB‑loaded user. The "admin by email" check in `api/deps.py` and `auth.py` is gone.

## 6. What changed vs. the old design

|                                 | Old                                                                           | New                                                                      |
| ------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| First admin                     | Add email to `ADMIN_EMAILS`, then register through the normal invite flow     | `uv run python -m app.cli create-admin --email ...` → click setup link   |
| Admin check                     | `email in settings.admin_email_list`                                          | `user.is_admin` boolean on `users` row                                   |
| Promote/demote                  | Redeploy with new env var                                                     | Admin UI toggle or CLI                                                   |
| User "background"               | Free‑text string column, Literal allowlist in Pydantic, hardcoded in frontend | `roles` table, FK from `users.role_id`, seeded with the old eight values |
| Custom role requested at signup | No way to add one                                                             | Admin picks existing or creates on approval                              |
| Password reset                  | Not implemented                                                               | `/auth/password-reset/request` + setup token                             |

## 7. Data migration notes

Migration `0008_admin_roles_and_setup_tokens`:

1. Creates `roles` and `setup_tokens` tables.
2. Seeds the eight built‑in roles (`chemical_engineer`, `pharmaceutical_scientist`, `food_scientist`, `academic_researcher`, `quality_engineer`, `data_scientist`, `student`, `other`).
3. Adds `users.is_admin` (default FALSE) and `users.role_id` (nullable FK).
4. Backfills `users.role_id` from the old `users.background` string by name match.
5. Adds `signup_requests.requested_role` (nullable text) and `signup_requests.role_id` (nullable FK).
6. Leaves `users.background` in place for one release. It is no longer read — a subsequent migration will drop it.

`settings.admin_emails` and the `admin_email_list` property are removed in the same PR; the env var becomes inert.
