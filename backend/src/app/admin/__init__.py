"""Read-only admin DB browser, powered by ``sqladmin``.

Mounts at ``/admin`` and gates on the existing ``users.is_admin`` flag.
Authentication uses a separate session cookie (managed by sqladmin's
own ``SessionMiddleware``) — operators log in once at ``/admin/login``
with the same email + password they use for the SvelteKit app.

Every model view is read-only; sensitive columns
(``users.password_hash``, ``setup_tokens.token``,
``signup_requests.invite_token``) are excluded from both list and
detail pages.
"""

from app.admin.mount import mount_admin

__all__ = ["mount_admin"]
