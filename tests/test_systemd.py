"""The systemd user units under systemd/ schedule what the README says, and the install script
links exactly them into the user's systemd folder."""

import configparser
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "systemd"
INSTALL = ROOT / "scripts" / "install-systemd.sh"


def _unit(name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # systemd keys are case-sensitive
    parser.read_string((UNITS / name).read_text())
    return parser


def _units(suffix: str) -> list[Path]:
    return sorted(UNITS.glob(f"*{suffix}"))


def test_every_timer_has_a_service_and_a_schedule() -> None:
    timers = _units(".timer")
    assert timers, "no timers under systemd/"
    for timer_path in timers:
        assert (UNITS / f"{timer_path.stem}.service").is_file(), timer_path.name
        timer = _unit(timer_path.name)
        assert timer["Timer"]["OnCalendar"]
        assert timer["Install"]["WantedBy"] == "timers.target"


def test_the_daily_run_catches_up_and_runs_every_day() -> None:
    timer = _unit("manc-run.timer")
    assert timer["Timer"]["Persistent"] == "true"
    assert timer["Timer"]["OnCalendar"] == "*-*-* 06:00:00 UTC"  # crypto trades on weekends


def test_fetch_runs_every_fifteen_minutes_in_the_container() -> None:
    assert _unit("manc-fetch.timer")["Timer"]["OnCalendar"] == "*-*-* *:00/15:00"
    exec_start = _unit("manc-fetch.service")["Service"]["ExecStart"]
    assert exec_start.endswith("podman compose run --rm api manc fetch")


def test_the_run_happens_on_the_host_with_uv() -> None:
    service = _unit("manc-run.service")["Service"]
    assert service["ExecStart"].endswith("uv run manc run")
    assert service["Type"] == "oneshot"


def test_the_api_is_a_restarting_service_wanted_at_login() -> None:
    api = _unit("manc-api.service")
    assert api["Service"]["ExecStart"].endswith("podman compose up api")
    assert api["Service"]["ExecStop"].endswith("podman compose down")
    assert api["Service"]["Restart"] == "on-failure"
    assert api["Install"]["WantedBy"] == "default.target"


def test_every_service_runs_from_the_checkout() -> None:
    for service_path in _units(".service"):
        service = _unit(service_path.name)["Service"]
        assert service["WorkingDirectory"] == "%h/quant/manc", service_path.name


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="no systemd here")
def test_units_verify() -> None:
    result = subprocess.run(
        ["systemd-analyze", "--user", "verify", *map(str, UNITS.iterdir())],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_install_links_every_unit_and_enables_them(tmp_path: Path) -> None:
    config_home = tmp_path / "config"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for command in ("systemctl", "loginctl"):
        stub = bin_dir / command
        stub.write_text(f'#!/bin/sh\necho "{command} $*" >> "{calls}"\n')
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    result = subprocess.run(
        ["sh", str(INSTALL)],
        cwd=ROOT,
        env={
            **os.environ,
            "XDG_CONFIG_HOME": str(config_home),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    installed = config_home / "systemd" / "user"
    linked = {link.name: link.resolve() for link in installed.iterdir()}
    assert linked == {unit.name: unit.resolve() for unit in UNITS.iterdir()}
    recorded = calls.read_text()
    assert "loginctl enable-linger" in recorded
    assert "systemctl --user daemon-reload" in recorded
    for unit in ("manc-api.service", "manc-fetch.timer", "manc-run.timer"):
        assert f"enable --now {unit}" in recorded, unit
    assert os.access(INSTALL, os.X_OK)
