"""The units under src/manc/systemd/, system units that `manc install` copies into place: the
API, the fetch timer and the daily run, all as the manc user with one confinement block."""

import configparser
import shutil
import subprocess
from pathlib import Path

import pytest

from manc.install import UNITS_DIR

SERVICES = ("manc-api.service", "manc-fetch.service", "manc-run.service")
UNITS = (*SERVICES, "manc-fetch.timer", "manc-run.timer")
PATH = "/var/lib/manc/.local/bin:/usr/local/bin:/usr/bin:/bin"  # the uv tool and claude first


def _unit(name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # systemd keys are case-sensitive
    parser.read_string((UNITS_DIR / name).read_text())
    return parser


def test_the_folder_holds_the_units_and_the_env_example() -> None:
    assert {path.name for path in UNITS_DIR.iterdir()} == {*UNITS, "env.example"}
    example = (UNITS_DIR / "env.example").read_text()
    assert "MANC_DB_URL=sqlite:////var/lib/manc/manc.db" in example
    assert "MANC_SITE_DIR=/var/lib/manc/site" in example
    assert "MANC_API_HOST=127.0.0.1" in example
    assert "MANC_API_PORT=8888" in example
    assert "MANC_MAIL_TO=" in example


HARDENING = {
    "ProtectSystem": "strict",
    "ProtectHome": "yes",
    "ReadWritePaths": "/var/lib/manc",
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


def test_every_service_runs_as_manc_under_the_same_confinement() -> None:
    for name in SERVICES:
        service = _unit(name)["Service"]
        assert service["User"] == "manc" and service["Group"] == "manc", name
        assert service["EnvironmentFile"] == "/etc/manc/env", name
        assert service["ExecStart"].startswith("/usr/bin/env manc "), name
        assert f"PATH={PATH}" in service["Environment"].split(), name
        assert service["WorkingDirectory"] == "/var/lib/manc", name
        assert {key: service[key] for key in HARDENING} == HARDENING, name
        assert "UMask" not in service, name  # one writer of the database, the default mode
        assert "InaccessiblePaths" not in service, name  # no home of a person is in reach


def test_only_the_tunnel_machine_and_loopback_reach_the_api() -> None:
    """The tunnel machine's address is a drop-in (`systemctl edit manc-api`), not the unit."""
    api = _unit("manc-api.service")["Service"]
    assert api["IPAddressDeny"] == "any" and api["IPAddressAllow"] == "localhost"
    for name in ("manc-fetch.service", "manc-run.service"):  # these fetch the internet
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


def test_the_daily_run_keeps_its_claude_and_mails_the_reports() -> None:
    service = _unit("manc-run.service")["Service"]
    assert service["ExecStart"] == "/usr/bin/env manc run" and service["Type"] == "oneshot"
    assert "DISABLE_AUTOUPDATER=1" in service["Environment"].split()  # claude stays as logged in
    # the day's reports by mail through the machine's MTA, only when a recipient is set
    mail = 'manc report | mail -s "manc $(date -u +%%F)" "$MANC_MAIL_TO"'
    assert service["ExecStartPost"] == f"/bin/sh -c '[ -z \"$MANC_MAIL_TO\" ] || {mail}'"
    timer = _unit("manc-run.timer")
    assert timer["Timer"]["OnCalendar"] == "*-*-* 06:00:00 UTC"  # crypto trades on weekends
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Install"]["WantedBy"] == "timers.target"


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="no systemd here")
def test_units_verify(tmp_path: Path) -> None:
    for name in UNITS:
        shutil.copy(UNITS_DIR / name, tmp_path / name)
    result = subprocess.run(
        ["systemd-analyze", "verify", *(str(path) for path in tmp_path.iterdir())],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
