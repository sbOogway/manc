"""The units under src/manc/systemd/, system units that `manc install` copies into place: the
API and the fetch timer as the manc user, the daily run as the owner (a template instance)."""

import configparser
import shutil
import subprocess
from pathlib import Path

import pytest

from manc.install import UNITS_DIR

USER_MANC = ("manc-api.service", "manc-fetch.service")
TEMPLATE = "manc-run@.service"
UNITS = ("manc-api.service", "manc-fetch.service", "manc-fetch.timer", TEMPLATE, "manc-run@.timer")


def _unit(name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # systemd keys are case-sensitive
    parser.read_string((UNITS_DIR / name).read_text())
    return parser


def test_the_folder_holds_the_units_and_the_env_example() -> None:
    assert {path.name for path in UNITS_DIR.iterdir()} == {*UNITS, "env.example"}
    example = (UNITS_DIR / "env.example").read_text()
    assert "MANC_DB_URL=sqlite:////var/lib/manc/manc.db" in example
    assert "MANC_API_HOST=127.0.0.1" in example
    assert "MANC_API_PORT=8888" in example
    assert "MANC_MAIL_TO=" in example


def test_every_service_loads_the_env_file_and_runs_manc_from_the_path() -> None:
    for name in (*USER_MANC, TEMPLATE):
        service = _unit(name)["Service"]
        assert service["EnvironmentFile"] == "/etc/manc/env", name
        assert service["ExecStart"].startswith("/usr/bin/env manc "), name
        assert service["WorkingDirectory"] == "/var/lib/manc", name


HARDENING = {
    "ProtectSystem": "strict",
    "NoNewPrivileges": "yes",
    "PrivateTmp": "yes",
    "ProtectKernelTunables": "yes",
    "ProtectKernelModules": "yes",
    "ProtectControlGroups": "yes",
    "RestrictSUIDSGID": "yes",
    "RestrictRealtime": "yes",
    "LockPersonality": "yes",
    "PrivateDevices": "yes",
    "ProtectClock": "yes",
    "ProtectHostname": "yes",
    "ProtectProc": "invisible",
    "RestrictNamespaces": "yes",
    "RestrictAddressFamilies": "AF_UNIX AF_INET AF_INET6",
    "CapabilityBoundingSet": "",
    "SystemCallArchitectures": "native",
    "SystemCallFilter": "@system-service",
}


def test_the_manc_user_services_are_hardened() -> None:
    for name in USER_MANC:
        service = _unit(name)["Service"]
        assert service["User"] == "manc" and service["Group"] == "manc", name
        assert service["UMask"] == "0002", name  # the owner's run writes the same database
        assert {key: service[key] for key in HARDENING} == HARDENING, name
        assert service["ProtectHome"] == "yes", name
        assert service["ReadWritePaths"] == "/var/lib/manc", name


def test_the_daily_run_is_confined_around_the_owners_claude_login() -> None:
    """Home is read-only, not hidden: the login is in ~/.claude and claude writes there."""
    service = _unit(TEMPLATE)["Service"]
    assert {key: service[key] for key in HARDENING} == HARDENING
    assert service["ProtectHome"] == "read-only"
    assert service["ReadWritePaths"] == "/var/lib/manc /home/%i/.claude -/home/%i/.cache"
    secrets = (
        "/home/%i/.ssh",
        "/home/%i/.gnupg",
        "/home/%i/.git-credentials",
        "/home/%i/.config/gh",
    )
    assert service["InaccessiblePaths"].split() == [f"-{path}" for path in secrets]
    assert "DISABLE_AUTOUPDATER=1" in service["Environment"]  # ~/.local is read-only


def test_only_the_tunnel_machine_and_loopback_reach_the_api() -> None:
    """The tunnel machine's address is a drop-in (`systemctl edit manc-api`), not the unit."""
    api = _unit("manc-api.service")["Service"]
    assert api["IPAddressDeny"] == "any" and api["IPAddressAllow"] == "localhost"
    for name in ("manc-fetch.service", TEMPLATE):  # these fetch the internet
        assert "IPAddressDeny" not in _unit(name)["Service"], name


def test_the_api_restarts_and_the_fetch_runs_every_fifteen_minutes() -> None:
    api = _unit("manc-api.service")
    assert api["Service"]["ExecStart"] == "/usr/bin/env manc api"
    assert api["Service"]["Restart"] == "on-failure"
    assert api["Install"]["WantedBy"] == "multi-user.target"
    fetch = _unit("manc-fetch.service")["Service"]
    assert fetch["ExecStart"] == "/usr/bin/env manc fetch" and fetch["Type"] == "oneshot"
    timer = _unit("manc-fetch.timer")
    assert timer["Timer"]["OnCalendar"] == "*-*-* *:00/15:00"
    assert timer["Install"]["WantedBy"] == "timers.target"


def test_the_daily_run_is_a_template_instantiated_with_the_owner() -> None:
    service = _unit(TEMPLATE)["Service"]
    assert service["User"] == "%i" and service["Group"] == "manc"
    assert service["UMask"] == "0002"  # the database stays writable by manc
    assert service["ExecStart"] == "/usr/bin/env manc run"
    assert "/home/%i/.local/bin" in service["Environment"]  # the owner's claude
    # the day's reports by mail through the machine's MTA, only when a recipient is set
    mail = 'manc report | mail -s "manc $(date -u +%%F)" "$MANC_MAIL_TO"'
    assert service["ExecStartPost"] == f"/bin/sh -c '[ -z \"$MANC_MAIL_TO\" ] || {mail}'"
    timer = _unit("manc-run@.timer")["Timer"]
    assert timer["OnCalendar"] == "*-*-* 06:00:00 UTC"  # crypto trades on weekends
    assert timer["Persistent"] == "true"


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="no systemd here")
def test_units_verify(tmp_path: Path) -> None:
    for name in UNITS:
        shutil.copy(UNITS_DIR / name, tmp_path / name.replace("@.", "@owner."))
    result = subprocess.run(
        ["systemd-analyze", "verify", *(str(path) for path in tmp_path.iterdir())],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
