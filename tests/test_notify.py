"""The daily report by email: settings from the environment, one message per run."""

from datetime import date
from email.message import EmailMessage
from typing import ClassVar

import pytest

from manc import notify
from manc.formulas.contract import IndexScore


class FakeSmtp:
    """Records what smtplib.SMTP would be asked to do."""

    instances: ClassVar[list["FakeSmtp"]] = []

    def __init__(self, host: str, port: int, timeout: float | None = None) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.calls: list[str] = []
        self.sent: list[EmailMessage] = []
        FakeSmtp.instances.append(self)

    def __enter__(self) -> "FakeSmtp":
        return self

    def __exit__(self, *exc: object) -> None:
        self.calls.append("quit")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login {user} {password}")

    def send_message(self, message: EmailMessage) -> None:
        self.calls.append("send")
        self.sent.append(message)


def _score(asset: str, value: float, report: str) -> IndexScore:
    return IndexScore(
        asset=asset,
        date=date(2026, 9, 21),
        score=value,
        formula="v2",
        components={},
        n_news=3,
        n_events=1,
        report_md=report,
    )


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> notify.MailSettings:
    monkeypatch.setenv("MANC_MAIL_TO", "me@example.org")
    monkeypatch.setenv("MANC_MAIL_FROM", "manc@example.org")
    monkeypatch.setenv("MANC_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("MANC_SMTP_USER", "manc@example.org")
    monkeypatch.setenv("MANC_SMTP_PASSWORD", "app-password")
    FakeSmtp.instances.clear()
    loaded = notify.MailSettings.from_env()
    assert loaded is not None
    return loaded


def test_settings_come_from_the_environment_with_587_by_default(
    settings: notify.MailSettings,
) -> None:
    assert settings.to == "me@example.org" and settings.sender == "manc@example.org"
    assert (settings.host, settings.port) == ("smtp.example.org", 587)
    assert settings.user == "manc@example.org" and settings.password == "app-password"


def test_no_recipient_means_no_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MANC_MAIL_TO", raising=False)
    assert notify.MailSettings.from_env() is None


def test_the_sender_defaults_to_the_user_and_the_port_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MANC_MAIL_TO", "me@example.org")
    monkeypatch.setenv("MANC_SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("MANC_SMTP_USER", "manc@example.org")
    monkeypatch.setenv("MANC_SMTP_PORT", "2525")
    monkeypatch.delenv("MANC_MAIL_FROM", raising=False)
    loaded = notify.MailSettings.from_env()
    assert loaded is not None
    assert loaded.sender == "manc@example.org" and loaded.port == 2525


def test_one_message_carries_every_report(settings: notify.MailSettings) -> None:
    scores = [
        _score("BTCUSD", 23.4, "# BTCUSD\n\nBullish flow."),
        _score("ETHUSD", -5.0, "# ETHUSD\n\nQuiet."),
    ]
    notify.send_reports(scores, settings, smtp=FakeSmtp)
    [connection] = FakeSmtp.instances
    assert (connection.host, connection.port) == ("smtp.example.org", 587)
    assert connection.calls == ["starttls", "login manc@example.org app-password", "send", "quit"]
    [message] = connection.sent
    assert message["Subject"] == "manc 2026-09-21: BTCUSD +23, ETHUSD -5"
    assert message["From"] == "manc@example.org" and message["To"] == "me@example.org"
    body = message.get_content()
    assert "# BTCUSD\n\nBullish flow." in body and "# ETHUSD\n\nQuiet." in body
    assert body.index("BTCUSD") < body.index("ETHUSD")


def test_no_login_without_a_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANC_MAIL_TO", "me@example.org")
    monkeypatch.setenv("MANC_MAIL_FROM", "manc@example.org")
    monkeypatch.setenv("MANC_SMTP_HOST", "localhost")
    monkeypatch.delenv("MANC_SMTP_USER", raising=False)
    FakeSmtp.instances.clear()
    loaded = notify.MailSettings.from_env()
    assert loaded is not None
    notify.send_reports([_score("BTCUSD", 0, "r")], loaded, smtp=FakeSmtp)
    assert FakeSmtp.instances[0].calls == ["starttls", "send", "quit"]


def test_nothing_to_report_sends_nothing(settings: notify.MailSettings) -> None:
    notify.send_reports([], settings, smtp=FakeSmtp)
    assert FakeSmtp.instances == []
