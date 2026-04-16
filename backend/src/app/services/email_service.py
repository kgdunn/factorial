"""Email service: async SMTP sending via aiosmtplib."""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html_body: str) -> None:
    """Send an HTML email via SMTP.

    If ``SMTP_HOST`` is not configured the email is logged and skipped,
    allowing the application to run in development without SMTP.
    """
    if not settings.smtp_host:
        logger.warning("SMTP not configured — email to %s (%s) logged only", to, subject)
        return

    msg = EmailMessage()
    msg["From"] = settings.smtp_from_email
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            start_tls=settings.smtp_use_tls,
        )
        logger.info("Email sent to %s: %s", to, subject)
    except Exception:
        logger.exception("Failed to send email to %s: %s", to, subject)
        raise


async def send_admin_notification(signup_email: str, use_case: str) -> None:
    """Notify admin(s) about a new signup request."""
    admin_url = f"{settings.frontend_url}/admin/signups"
    html = f"""\
<h2>New signup request</h2>
<p><strong>Email:</strong> {signup_email}</p>
<p><strong>Why they want access:</strong></p>
<blockquote>{use_case}</blockquote>
<p><a href="{admin_url}">Review signup requests</a></p>
"""
    for admin in settings.admin_email_list:
        try:
            await send_email(admin, f"New signup request from {signup_email}", html)
        except Exception:
            logger.exception("Failed to notify admin %s about signup from %s", admin, signup_email)


async def send_signup_confirmation(to: str, use_case: str) -> None:
    """Send the user a confirmation that their signup request was received."""
    html = f"""\
<h2>We received your signup request</h2>
<p>Thanks for your interest in Agentic DOE! We've received your request and
will review it shortly. You'll get another email once your account is approved.</p>
<p><strong>Here's a copy of what you submitted:</strong></p>
<blockquote>{use_case}</blockquote>
"""
    try:
        await send_email(to, "Signup request received — Agentic DOE", html)
    except Exception:
        logger.exception("Failed to send signup confirmation to %s", to)


async def send_invite_email(to: str, invite_token: str) -> None:
    """Send an approved user their invite link to complete registration."""
    invite_url = f"{settings.frontend_url}/register/complete?token={invite_token}"
    hours = settings.invite_token_expire_hours
    html = f"""\
<h2>You're invited to Agentic DOE!</h2>
<p>Your signup request has been approved. Click the link below to create
your account:</p>
<p><a href="{invite_url}">Complete your registration</a></p>
<p>This link expires in {hours} hours.</p>
"""
    await send_email(to, "You're invited — Agentic DOE", html)
