"""The units under systemd/: manc's user units for the container (rootless podman) and the
system units for the daily run on the host as the owner."""

import configparser
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / "systemd"
USER_UNITS = ("manc-api.service", "manc-fetch.service", "manc-fetch.timer")
SYSTEM_UNITS = ("manc-run.service", "manc-run.timer")


def _unit(name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # systemd keys are case-sensitive
    parser.read_string((UNITS / name).read_text())
    return parser


def test_the_folder_holds_exactly_the_two_sets() -> None:
    assert {unit.name for unit in UNITS.iterdir()} == set(USER_UNITS) | set(SYSTEM_UNITS)


def test_every_timer_has_a_service_and_a_schedule() -> None:
    for name in ("manc-fetch.timer", "manc-run.timer"):
        assert (UNITS / name.replace(".timer", ".service")).is_file()
        timer = _unit(name)
        assert timer["Timer"]["OnCalendar"]
        assert timer["Install"]["WantedBy"] == "timers.target"


def test_the_daily_run_is_a_system_unit_as_the_owner_with_the_shared_database() -> None:
    service = _unit("manc-run.service")["Service"]
    assert service["User"] == "@OWNER@"  # rendered by install.sh
    assert service["Group"] == "manc" and service["UMask"] == "0002"
    assert service["WorkingDirectory"] == "/opt/manc"
    assert service["ExecStart"].endswith("uv run --no-sync manc run")
    assert "MANC_DB_URL=sqlite:////var/lib/manc/data/manc.db" in service["Environment"]
    assert "ExecStartPost" not in service  # the owner's post-merge hook publishes the site
    timer = _unit("manc-run.timer")["Timer"]
    assert timer["Persistent"] == "true"
    assert timer["OnCalendar"] == "*-*-* 06:00:00 UTC"  # crypto trades on weekends


def test_fetch_runs_every_fifteen_minutes_in_the_container() -> None:
    assert _unit("manc-fetch.timer")["Timer"]["OnCalendar"] == "*-*-* *:00/15:00"
    service = _unit("manc-fetch.service")["Service"]
    assert service["ExecStart"].endswith("podman compose run --rm api manc fetch")
    assert service["WorkingDirectory"] == "/opt/manc"


def test_the_api_is_a_restarting_user_service() -> None:
    api = _unit("manc-api.service")
    assert api["Service"]["ExecStart"].endswith("podman compose up api")
    assert api["Service"]["ExecStop"].endswith("podman compose down")
    assert api["Service"]["Restart"] == "on-failure"
    assert api["Service"]["WorkingDirectory"] == "/opt/manc"
    assert api["Install"]["WantedBy"] == "default.target"


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="no systemd here")
def test_units_verify(tmp_path: Path) -> None:
    user = subprocess.run(
        ["systemd-analyze", "--user", "verify", *(str(UNITS / name) for name in USER_UNITS)],
        capture_output=True,
        text=True,
    )
    assert user.returncode == 0, user.stderr
    rendered = tmp_path / "manc-run.service"
    rendered.write_text((UNITS / "manc-run.service").read_text().replace("@OWNER@", "root"))
    shutil.copy(UNITS / "manc-run.timer", tmp_path)
    system = subprocess.run(
        ["systemd-analyze", "verify", str(rendered), str(tmp_path / "manc-run.timer")],
        capture_output=True,
        text=True,
    )
    assert system.returncode == 0, system.stderr
