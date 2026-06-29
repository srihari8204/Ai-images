"""Transactional email sender.

In dev (no SMTP configured) emails are logged rather than sent, which keeps the
verification/reset flows testable end-to-end without external dependencies.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        logger.info("email_dev_log", to=to, subject=subject, body=body)
        return

    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("email_sent", to=to, subject=subject)
    except Exception as exc:  # noqa: BLE001
        logger.error("email_failed", to=to, error=str(exc))


def send_verification_email(to: str, token: str) -> None:
    url = f"{settings.frontend_base_url}/auth/verify?token={token}"
    send_email(
        to,
        "Verify your AI Mirror account",
        f"Welcome! Confirm your email to activate your account:\n\n{url}\n\n"
        f"This link expires in {settings.email_verification_ttl_seconds // 3600} hours.",
    )


def send_password_reset_email(to: str, token: str) -> None:
    url = f"{settings.frontend_base_url}/auth/reset?token={token}"
    send_email(
        to,
        "Reset your AI Mirror password",
        f"Use this link to set a new password:\n\n{url}\n\n"
        f"If you did not request this, ignore this email. "
        f"The link expires in {settings.password_reset_ttl_seconds // 60} minutes.",
    )


def send_export_ready_email(to: str, download_url: str) -> None:
    send_email(
        to,
        "Your AI Mirror data export is ready",
        f"Your data export is ready to download:\n\n{download_url}",
    )
