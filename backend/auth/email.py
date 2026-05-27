"""Transactional auth emails (verification, password reset).

Self-contained on purpose: it reads SMTP settings from `auth_config` (the
same place the rest of auth reads config) rather than depending on the
meeting-summary `EmailService`, which has its own env names and templates.

Graceful degradation: if SMTP is not configured (no SMTP_HOST), we DON'T
fail the request. We log the link at WARNING and return False. That keeps
local dev + tests working without a mail server, and a misconfigured prod
surfaces loudly in logs instead of 500-ing a signup. Callers treat send
failure as non-fatal — the user can hit "resend" once mail is configured.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from auth.config import auth_config

logger = logging.getLogger(__name__)

APP_NAME = "Meeting-Ops"


def _send(to_email: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send one email via auth_config SMTP. Returns True if handed to the
    server, False (logged) if SMTP isn't configured or the send failed.
    Never raises — email is best-effort enrichment of the auth flow."""
    if not auth_config.SMTP_HOST:
        logger.warning(
            "SMTP not configured (SMTP_HOST unset); not sending %r to %s. "
            "Body preview: %s",
            subject, to_email, text_body[:200],
        )
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = auth_config.SMTP_FROM_EMAIL
        msg["To"] = to_email
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(auth_config.SMTP_HOST, auth_config.SMTP_PORT, timeout=10) as server:
            server.starttls()
            if auth_config.SMTP_USER and auth_config.SMTP_PASSWORD:
                server.login(auth_config.SMTP_USER, auth_config.SMTP_PASSWORD)
            server.sendmail(auth_config.SMTP_FROM_EMAIL, [to_email], msg.as_string())
        logger.info("Sent %r to %s", subject, to_email)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to send %r to %s: %s", subject, to_email, exc)
        return False


def _button_html(title: str, intro: str, url: str, cta: str, outro: str) -> str:
    return f"""\
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;color:#333;background:#f5f5f5;padding:24px">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden">
    <div style="background:linear-gradient(135deg,#7c3aed,#a855f7);color:#fff;padding:24px 28px">
      <div style="font-size:20px;font-weight:700">{APP_NAME}</div>
    </div>
    <div style="padding:28px">
      <h2 style="margin:0 0 12px;font-size:18px">{title}</h2>
      <p style="margin:0 0 20px;font-size:14px;line-height:1.6;color:#555">{intro}</p>
      <a href="{url}" style="display:inline-block;background:#7c3aed;color:#fff;text-decoration:none;
         padding:12px 22px;border-radius:8px;font-size:14px;font-weight:600">{cta}</a>
      <p style="margin:20px 0 0;font-size:12px;color:#888">{outro}</p>
      <p style="margin:12px 0 0;font-size:12px;color:#aaa;word-break:break-all">{url}</p>
    </div>
  </div>
</body></html>"""


def send_verification_email(to_email: str, verify_url: str) -> bool:
    """Email a user a link to verify their address."""
    return _send(
        to_email,
        f"Verify your {APP_NAME} email",
        _button_html(
            "Confirm your email",
            f"Welcome to {APP_NAME}. Confirm this address to finish setting up your account.",
            verify_url,
            "Verify email",
            "This link expires in 24 hours. If you didn't create an account, you can ignore this email.",
        ),
        f"Welcome to {APP_NAME}. Verify your email: {verify_url}\n"
        "This link expires in 24 hours.",
    )


def send_password_reset_email(to_email: str, reset_url: str) -> bool:
    """Email a user a link to reset their password."""
    return _send(
        to_email,
        f"Reset your {APP_NAME} password",
        _button_html(
            "Reset your password",
            "We received a request to reset your password. Use the button below to choose a new one.",
            reset_url,
            "Reset password",
            "This link expires in 24 hours. If you didn't request this, you can safely ignore it.",
        ),
        f"Reset your {APP_NAME} password: {reset_url}\nThis link expires in 24 hours.",
    )
