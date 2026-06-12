from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger(__name__)

GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 587


def _mail_configured() -> bool:
    s = get_settings()
    return bool(s.maildev_incoming_user and s.maildev_incoming_pass)


def send_password_reset_email(*, to_email: str, reset_url: str) -> None:
    subject = "Helios — Đặt lại mật khẩu"
    body = f"""Xin chào,

Bạn (hoặc ai đó) đã yêu cầu đặt lại mật khẩu cho tài khoản Helios.

Nhấn vào liên kết sau để đặt mật khẩu mới (liên kết có hiệu lực trong thời gian giới hạn):

{reset_url}

Nếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này.

— Helios
"""

    if not _mail_configured():
        logger.warning(
            "MAILDEV_INCOMING_USER/PASS chưa cấu hình — liên kết đặt lại (dev): %s → %s",
            to_email,
            reset_url,
        )
        return

    s = get_settings()
    sender = s.maildev_incoming_user
    assert sender is not None

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Helios <{sender}>"
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(sender, s.maildev_incoming_pass or "")
        server.send_message(msg)

    logger.info("Đã gửi email đặt lại mật khẩu tới %s", to_email)
