"""SMTP email delivery used by password reset endpoints."""

from __future__ import annotations

import asyncio
import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()
SMTP_USE_SSL = _env_bool("SMTP_USE_SSL", True)
SMTP_TIMEOUT = float(os.getenv("SMTP_TIMEOUT", "15"))


def smtp_configured() -> bool:
    return bool(SMTP_USER and SMTP_PASSWORD and SMTP_FROM)


def _send_message(recipient: str, code: str) -> None:
    if not smtp_configured():
        raise RuntimeError("SMTP_USER, SMTP_PASSWORD, and SMTP_FROM must be configured")

    message = EmailMessage()
    message["Subject"] = "\u7535\u5f71\u63a8\u8350\u7cfb\u7edf\u5bc6\u7801\u91cd\u7f6e\u9a8c\u8bc1\u7801"
    message["From"] = SMTP_FROM
    message["To"] = recipient
    message.set_content(
        "\u60a8\u597d\uff01\n\n"
        f"\u60a8\u7684\u5bc6\u7801\u91cd\u7f6e\u9a8c\u8bc1\u7801\u662f\uff1a{code}\n"
        "\u9a8c\u8bc1\u7801 10 \u5206\u949f\u5185\u6709\u6548\u3002\u82e5\u4e0d\u662f\u60a8\u672c\u4eba\u64cd\u4f5c\uff0c\u8bf7\u5ffd\u7565\u6b64\u90ae\u4ef6\u3002\n"
    )

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(message)
        return

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(message)


async def send_password_reset_code(recipient: str, code: str) -> None:
    """Run blocking smtplib work away from FastAPI's event loop."""

    await asyncio.to_thread(_send_message, recipient, code)
