"""Email composers for the user-feedback flow.

Three senders:

- :func:`notify_user_of_submission` — confirmation echo to the submitter.
- :func:`notify_admins_of_submission` — one message per active admin, with
  the screenshot attached when present.
- :func:`notify_user_of_reply` — admin's reply, forwarded to the user.

All calls delegate to :func:`app.services.email_service.send_email` and
silently no-op when SMTP is not configured.
"""

from __future__ import annotations

import html
import logging

from app.models.user import User
from app.models.user_feedback import UserFeedback
from app.services.email_service import send_email

logger = logging.getLogger(__name__)

_TOPIC_LABELS = {
    "incorrect_response": "Incorrect response",
    "improvement": "Improvement suggestion",
    "bug": "Bug / error",
    "other": "Other",
}


def _topic_label(topic: str) -> str:
    return _TOPIC_LABELS.get(topic, topic)


def _quote(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


async def notify_user_of_submission(feedback: UserFeedback, user: User) -> None:
    html_body = f"""\
<h2>Thanks for your feedback</h2>
<p>We've received your note and an administrator will take a look. Here's a
copy of what you sent:</p>
<p><strong>Topic:</strong> {html.escape(_topic_label(feedback.topic))}</p>
<blockquote>{_quote(feedback.message)}</blockquote>
<p>You don't need to reply to this email.</p>
"""
    try:
        await send_email(user.email, "We got your feedback", html_body)
    except Exception:
        logger.exception("Failed to send feedback confirmation to %s", user.email)


async def notify_admins_of_submission(
    feedback: UserFeedback,
    user: User,
    admin_emails: list[str],
) -> None:
    if not admin_emails:
        return
    subject = f"[Feedback: {_topic_label(feedback.topic)}] from {user.email}"
    html_body = f"""\
<h2>New user feedback</h2>
<p><strong>From:</strong> {html.escape(user.email)}</p>
<p><strong>Topic:</strong> {html.escape(_topic_label(feedback.topic))}</p>
<p><strong>Page:</strong> {html.escape(feedback.page_url or "(not captured)")}</p>
<p><strong>App version:</strong> {html.escape(feedback.app_version or "(unknown)")}</p>
<p><strong>Viewport:</strong> {html.escape(feedback.viewport or "(unknown)")}</p>
<p><strong>User agent:</strong> {html.escape(feedback.user_agent or "(unknown)")}</p>
<hr>
<blockquote>{_quote(feedback.message)}</blockquote>
"""
    attachments: list[tuple[str, str, bytes]] | None = None
    if feedback.screenshot_png:
        attachments = [
            (
                f"feedback-{feedback.id}.png",
                feedback.screenshot_mime or "image/png",
                bytes(feedback.screenshot_png),
            )
        ]
    for admin in admin_emails:
        try:
            await send_email(admin, subject, html_body, attachments=attachments)
        except Exception:
            logger.exception("Failed to notify admin %s about feedback %s", admin, feedback.id)


async def notify_user_of_reply(
    feedback: UserFeedback,
    user: User,
    admin: User,
    reply_body: str,
) -> None:
    signer = admin.display_name or admin.email
    subject = f"Re: your feedback about {_topic_label(feedback.topic).lower()}"
    html_body = f"""\
<p>Hi,</p>
<p>{_quote(reply_body)}</p>
<p>— {html.escape(signer)}</p>
<hr>
<p style="color:#5A5649"><em>On {feedback.created_at:%Y-%m-%d %H:%M UTC} you wrote:</em></p>
<blockquote>{_quote(feedback.message)}</blockquote>
"""
    try:
        await send_email(user.email, subject, html_body)
    except Exception:
        logger.exception("Failed to deliver feedback reply to %s", user.email)
