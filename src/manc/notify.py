"""The daily report by email, sent at the end of `manc run` when `MANC_MAIL_TO` is set.

Plain SMTP through the standard library: the six `MANC_MAIL_*` / `MANC_SMTP_*` variables live in
the env file next to the provider keys. One message per run, the subject listing every score,
the body the markdown report of every asset.
"""

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from email.message import EmailMessage
from smtplib import SMTP

from manc.formulas.contract import IndexScore

DEFAULT_PORT = 587  # submission with STARTTLS, what Gmail, Fastmail and most providers expect

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MailSettings:
    to: str
    sender: str
    host: str
    port: int = DEFAULT_PORT
    user: str = ""
    password: str = ""

    @classmethod
    def from_env(cls) -> "MailSettings | None":
        """None when no recipient is set; the sender defaults to the SMTP user."""
        to = os.environ.get("MANC_MAIL_TO", "")
        if not to:
            return None
        user = os.environ.get("MANC_SMTP_USER", "")
        return cls(
            to=to,
            sender=os.environ.get("MANC_MAIL_FROM") or user,
            host=os.environ.get("MANC_SMTP_HOST", "localhost"),
            port=int(os.environ.get("MANC_SMTP_PORT") or DEFAULT_PORT),
            user=user,
            password=os.environ.get("MANC_SMTP_PASSWORD", ""),
        )


def send_reports(
    scores: Sequence[IndexScore], settings: MailSettings, smtp: type[SMTP] = SMTP
) -> None:
    """One message with every report of the run; nothing when there is nothing to report."""
    if not scores:
        return
    day = scores[0].date
    summary = ", ".join(f"{score.asset} {score.score:+.0f}" for score in scores)
    message = EmailMessage()
    message["Subject"] = f"manc {day}: {summary}"
    message["From"] = settings.sender
    message["To"] = settings.to
    message.set_content("\n\n---\n\n".join(score.report_md for score in scores))
    log.info("mail: %d reports for %s to %s via %s", len(scores), day, settings.to, settings.host)
    with smtp(settings.host, settings.port, timeout=60) as connection:
        connection.starttls()
        if settings.user:
            connection.login(settings.user, settings.password)
        connection.send_message(message)
