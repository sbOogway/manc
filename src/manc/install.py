"""`manc install`: lay the production machine out and start the services (§8, Production).

A dedicated `manc` user runs the API and the fetch timer, confined to /var/lib/manc; the daily
run is a template unit instantiated with the owner, whose Claude Code login tags the headlines.
The one file left to edit is /etc/manc/env. Idempotent: run again after `uv tool upgrade manc`.
"""

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

UNITS_DIR = Path(__file__).resolve().parent / "systemd"
USER = "manc"
DATA_DIR = Path("/var/lib/manc")
DATABASE_URL = f"sqlite:///{DATA_DIR}/manc.db"
Runner = Callable[..., object]


def install(owner: str, prefix: Path = Path("/"), run: Runner = subprocess.run) -> None:
    """Everything below `prefix` (`/` for real), every privileged command through `run`."""
    if os.geteuid() != 0:
        raise PermissionError("manc install must run as root: sudo manc install --owner $USER")
    data = prefix / DATA_DIR.relative_to("/")
    etc = prefix / "etc" / "manc"
    system = prefix / "etc" / "systemd" / "system"

    if _run(run, ["getent", "passwd", USER]) != 0:
        _run(run, ["useradd", "-r", "-m", "-d", str(DATA_DIR), "-s", "/usr/sbin/nologin", USER])
    _run(run, ["usermod", "-aG", USER, owner])

    for folder in (data, etc, system):
        folder.mkdir(parents=True, exist_ok=True)
    _run(run, ["chown", f"{USER}:{USER}", str(data)])
    data.chmod(0o2770)  # group manc writes; new files inherit the group...
    _run(run, ["setfacl", "-d", "-m", f"g:{USER}:rwx", str(data)])  # ...and are group-writable

    env_file = etc / "env"
    if not env_file.exists():
        shutil.copy(UNITS_DIR / "env.example", env_file)
    _run(run, ["chown", f"root:{USER}", str(env_file)])
    env_file.chmod(0o640)

    _run(
        run, ["runuser", "-u", USER, "--", "env", f"MANC_DB_URL={DATABASE_URL}", "manc", "migrate"]
    )

    for unit in sorted(UNITS_DIR.glob("manc-*")):
        shutil.copy(unit, system / unit.name)
        (system / unit.name).chmod(0o644)
    _run(run, ["systemctl", "daemon-reload"])
    _run(
        run,
        [
            "systemctl",
            "enable",
            "--now",
            "manc-api.service",
            "manc-fetch.timer",
            f"manc-run@{owner}.timer",
        ],
    )
    _run(run, ["systemctl", "restart", "manc-api.service"])


def _run(run: Runner, command: list[str]) -> int:
    result = run(command, check=False)
    return int(getattr(result, "returncode", 0))
