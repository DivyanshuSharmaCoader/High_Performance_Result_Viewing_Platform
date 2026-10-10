"""Outgoing email through a provider-agnostic SMTP adapter (Mailpit in dev; SES/Postmark SMTP in prod).

Emails never contain marks or results — only links to the tenant host (docs/03 W11).
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

import aiosmtplib

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class OutgoingEmail:
    to: str
    subject: str
    text: str
    html: str | None = None
    reply_to: str | None = None


class Mailer(Protocol):
    async def send(self, email: OutgoingEmail) -> str: ...


class MailDeliveryError(Exception):
    pass


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, email: OutgoingEmail) -> str:
        msg = EmailMessage()
        msg["From"] = self.settings.mail_from
        msg["To"] = email.to
        msg["Subject"] = email.subject
        # The sender's own domain in the Message-ID, as receivers expect from an authenticated domain.
        sender = self.settings.mail_from.rsplit("<", 1)[-1].rstrip(">").strip()
        msg_id = make_msgid(domain=sender.rsplit("@", 1)[-1] if "@" in sender else "scorecode")
        msg["Message-ID"] = msg_id
        if email.reply_to:
            msg["Reply-To"] = email.reply_to
        msg.set_content(email.text)
        if email.html:
            msg.add_alternative(email.html, subtype="html")
        try:
            await aiosmtplib.send(
                msg,
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                username=self.settings.smtp_username,
                password=self.settings.smtp_password.get_secret_value()
                if self.settings.smtp_password
                else None,
                start_tls=self.settings.smtp_starttls,
                timeout=10,
            )
        except (aiosmtplib.SMTPException, OSError, TimeoutError) as exc:
            raise MailDeliveryError(type(exc).__name__) from exc
        return msg_id
