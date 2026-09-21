"""`manc install`: lay the production machine out and start the services (§8, Production).

A dedicated `manc` user runs the API and the fetch timer, confined to /var/lib/manc; the daily
run is a template unit instantiated with the owner, whose Claude Code login tags the headlines.
The one file left to edit is /etc/manc/env. Idempotent: run again after `uv tool upgrade manc`.
"""

import os
import pwd
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from manc import __version__

UNITS_DIR = Path(__file__).resolve().parent / "systemd"
# uv.lock exported by the pre-commit hook: `uv tool install` from git does not read the lock
CONSTRAINTS = Path(__file__).resolve().parent / "constraints.txt"
USER = "manc"
DATA_DIR = Path("/var/lib/manc")
DATABASE_URL = f"sqlite:///{DATA_DIR}/manc.db"
SOURCE = f"git+https://github.com/sbOogway/manc@v{__version__}"  # the release tag, never main
TOOL_HOME = Path("/opt/manc")  # the tool, its interpreter and the entry point, readable by all
TOOL_ENV = {
    "UV_TOOL_DIR": str(TOOL_HOME / "tools"),
    "UV_PYTHON_INSTALL_DIR": str(TOOL_HOME / "python"),  # not under /root, unlike uv's default
    "UV_TOOL_BIN_DIR": "/usr/local/bin",
}
Runner = Callable[..., object]


def install(
    owner: str,
    source: str = SOURCE,
    prefix: Path = Path("/"),
    run: Runner = subprocess.run,
) -> None:
    """Everything below `prefix` (`/` for real), every privileged command through `run`."""
    if os.geteuid() != 0:
        raise PermissionError("manc install must run as root: sudo uvx ... manc install")
    data = prefix / DATA_DIR.relative_to("/")
    etc = prefix / "etc" / "manc"
    system = prefix / "etc" / "systemd" / "system"

    tool = [find_uv(owner), "tool", "install", "--force", "--python", "3.12"]
    tool += ["--constraints", str(CONSTRAINTS), source]
    run(tool, check=True, env={**os.environ, **TOOL_ENV})

    if int(getattr(run(["getent", "passwd", USER], check=False), "returncode", 1)) != 0:
        _run(run, ["useradd", "-r", "-m", "-d", str(DATA_DIR), "-s", "/usr/sbin/nologin", USER])
    _run(run, ["usermod", "-aG", USER, owner])

    for folder in (data, etc, system):
        folder.mkdir(parents=True, exist_ok=True)
    _run(run, ["chown", f"{USER}:{USER}", str(data)])
    data.chmod(0o2770)  # the owner is in group manc; setgid: new files carry the group

    env_file = etc / "env"
    if not env_file.exists():
        shutil.copy(UNITS_DIR / "env.example", env_file)
    _run(run, ["chown", f"root:{USER}", str(env_file)])
    env_file.chmod(0o640)

    _run(
        run, ["runuser", "-u", USER, "--", "env", f"MANC_DB_URL={DATABASE_URL}", "manc", "migrate"]
    )
    # SQLite creates the file 0644 and gives journal and WAL files the same mode as the database,
    # so 0660 here (with UMask=0002 in every unit) is what lets the owner's run write it too
    _run(run, ["chmod", "0660", str(DATA_DIR / "manc.db")])

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


def find_uv(owner: str) -> str:
    """The uv that launched us, one on the PATH, or the owner's or root's user install: the
    upstream installer puts uv in ~/.local/bin, which root's PATH under sudo does not have."""
    if os.environ.get("UV"):
        return os.environ["UV"]
    if found := shutil.which("uv"):
        return found
    homes = [home for home in (_home(owner), _home("root")) if home is not None]
    candidates = [home / ".local" / "bin" / "uv" for home in homes]
    candidates.append(Path("/usr/local/bin/uv"))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    tried = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"uv not found on the PATH nor at {tried}: `dnf install uv` or add it")


def _home(user: str) -> Path | None:
    try:
        return Path(pwd.getpwnam(user).pw_dir)
    except KeyError:
        return None


def _run(run: Runner, command: list[str]) -> None:
    run(command, check=True)
