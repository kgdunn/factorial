"""Command-line admin tools.

Run from the ``backend/`` directory:

.. code-block:: bash

   uv run python -m app.cli create-admin --email admin@example.com [--name "Jane Doe"]
   uv run python -m app.cli list-admins
   uv run python -m app.cli promote --email alice@example.com
   uv run python -m app.cli demote  --email alice@example.com
   uv run python -m app.cli reset-password --email alice@example.com

These commands work against the configured ``DATABASE_URL`` directly
and are the only blessed way to bootstrap the first admin on a fresh
install.
"""
# ruff: noqa: T201
# CLI entrypoint — print is the output format.

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.services import admin_service, setup_token_service
from app.services.email_service import send_setup_email

logger = logging.getLogger(__name__)


async def _with_session(coro_factory):
    async with async_session_factory() as session:
        try:
            result = await coro_factory(session)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Subcommand implementations
# ---------------------------------------------------------------------------


async def _cmd_create_admin(session: AsyncSession, email: str, name: str | None) -> dict[str, str]:
    user = await admin_service.create_admin_shell(session, email=email, display_name=name)
    token = await setup_token_service.issue_token(session, user, setup_token_service.SETUP)
    url = await setup_token_service.build_setup_url(token)
    return {"email": user.email, "url": url}


async def _cmd_promote(session: AsyncSession, email: str) -> str:
    user = await admin_service.get_user_by_email(session, email.strip().lower())
    if user is None:
        raise SystemExit(f"No user with email {email}")
    await admin_service.set_admin(session, user, True)
    return user.email


async def _cmd_demote(session: AsyncSession, email: str) -> str:
    user = await admin_service.get_user_by_email(session, email.strip().lower())
    if user is None:
        raise SystemExit(f"No user with email {email}")
    await admin_service.set_admin(session, user, False)
    return user.email


async def _cmd_list_admins(session: AsyncSession) -> list[dict[str, str]]:
    users, _ = await admin_service.list_users(session, page=1, page_size=500, admins_only=True)
    return [
        {
            "email": u.email,
            "display_name": u.display_name or "",
            "created_at": str(u.created_at),
            "is_active": "yes" if u.is_active else "no",
        }
        for u in users
    ]


async def _cmd_reset_password(session: AsyncSession, email: str) -> dict[str, str]:
    user = await admin_service.get_user_by_email(session, email.strip().lower())
    if user is None:
        raise SystemExit(f"No user with email {email}")
    token = await setup_token_service.issue_token(session, user, setup_token_service.RESET)
    url = await setup_token_service.build_setup_url(token)
    return {"email": user.email, "url": url}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app.cli", description="Agentic DOE admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create-admin", help="Bootstrap an admin user and print a setup URL")
    p_create.add_argument("--email", required=True)
    p_create.add_argument("--name", required=False, default=None, help="Optional display name")
    p_create.add_argument(
        "--no-email", action="store_true", help="Skip emailing the setup link even if SMTP is configured"
    )

    p_list = sub.add_parser("list-admins", help="List all admins")
    p_list.set_defaults(command="list-admins")

    p_promote = sub.add_parser("promote", help="Grant admin to an existing user")
    p_promote.add_argument("--email", required=True)

    p_demote = sub.add_parser("demote", help="Revoke admin from an existing user")
    p_demote.add_argument("--email", required=True)

    p_reset = sub.add_parser("reset-password", help="Issue a password-reset link")
    p_reset.add_argument("--email", required=True)
    p_reset.add_argument("--no-email", action="store_true")

    return parser


async def _main_async(args: argparse.Namespace) -> int:
    if args.command == "create-admin":
        info = await _with_session(lambda s: _cmd_create_admin(s, args.email, args.name))
        print(f"Admin created: {info['email']}")
        print(f"Setup link (valid 72h): {info['url']}")
        if not args.no_email:
            with contextlib.suppress(Exception):
                await send_setup_email(info["email"], info["url"], is_first_time=True)
        return 0

    if args.command == "list-admins":
        rows = await _with_session(_cmd_list_admins)
        if not rows:
            print("No admins found.")
            return 0
        print(f"{'email':<40} {'name':<24} {'active':<8} created_at")
        for r in rows:
            print(f"{r['email']:<40} {r['display_name']:<24} {r['is_active']:<8} {r['created_at']}")
        return 0

    if args.command == "promote":
        email = await _with_session(lambda s: _cmd_promote(s, args.email))
        print(f"Promoted {email} to admin.")
        return 0

    if args.command == "demote":
        email = await _with_session(lambda s: _cmd_demote(s, args.email))
        print(f"Demoted {email} from admin.")
        return 0

    if args.command == "reset-password":
        info = await _with_session(lambda s: _cmd_reset_password(s, args.email))
        print(f"Reset link for {info['email']} (valid 72h): {info['url']}")
        if not args.no_email:
            with contextlib.suppress(Exception):
                await send_setup_email(info["email"], info["url"], is_first_time=False)
        return 0

    print(f"Unknown command: {args.command}", file=sys.stderr)
    return 2


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = _build_parser().parse_args()
    try:
        code = asyncio.run(_main_async(args))
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
