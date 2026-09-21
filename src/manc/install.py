"""`manc install`: lay the production machine out and start the services (§8, Production).

One dedicated `manc` user runs everything: the API, the fetch timer and the daily run, whose
Claude Code login lives in its home, /var/lib/manc, next to the database, the site and the
tool itself. The one file left to edit is /etc/manc/env. Idempotent: run again to upgrade.
"""

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

UNITS_DIR = Path(__file__).resolve().parent / "systemd"
# uv.lock exported by the pre-commit hook: `uv tool install` from git does not read the lock
CONSTRAINTS = Path(__file__).resolve().parent / "constraints.txt"
USER = "manc"
HOME = Path("/var/lib/manc")
DATABASE_URL = f"sqlite:///{HOME}/manc.db"
SOURCE = "git+https://github.com/sbOogway/manc@main"  # --source takes a tag instead
SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"
Runner = Callable[..., object]


def install(source: str = SOURCE, prefix: Path = Path("/"), run: Runner = subprocess.run) -> None:
    """Everything below `prefix` (`/` for real), every privileged command through `run`."""
    if os.geteuid() != 0:
        raise PermissionError("manc install must run as root: sudo uvx ... manc install")
    uv = system_uv()
    home = prefix / HOME.relative_to("/")
    etc = prefix / "etc" / "manc"
    system = prefix / "etc" / "systemd" / "system"

    if int(getattr(run(["getent", "passwd", USER], check=False), "returncode", 1)) != 0:
        _run(run, ["useradd", "-r", "-m", "-d", str(HOME), "-s", "/usr/sbin/nologin", USER])
    for folder in (home, etc, system):
        folder.mkdir(parents=True, exist_ok=True)
    _run(run, ["chown", f"{USER}:{USER}", str(home)])
    home.chmod(0o750)

    env_file = etc / "env"
    if not env_file.exists():
        shutil.copy(UNITS_DIR / "env.example", env_file)
    _run(run, ["chown", f"root:{USER}", str(env_file)])
    env_file.chmod(0o640)
    shutil.copy(CONSTRAINTS, etc / "constraints.txt")  # where the manc user can read it
    (etc / "constraints.txt").chmod(0o644)

    # the tool, its Python and the entry point under the manc home (~/.local): runuser keeps
    # root's environment, so HOME is set by hand
    as_manc = ["runuser", "-u", USER, "--", "env", "-i", f"HOME={HOME}"]
    as_manc += [f"PATH={HOME}/.local/bin:/usr/bin"]
    tool = [uv, "tool", "install", "--force", "--python", "3.12"]
    tool += ["--constraints", "/etc/manc/constraints.txt", source]
    _run(run, [*as_manc, *tool])
    _run(run, [*as_manc, f"MANC_DB_URL={DATABASE_URL}", "manc", "migrate"])

    for unit in sorted(UNITS_DIR.glob("manc-*")):
        shutil.copy(unit, system / unit.name)
        (system / unit.name).chmod(0o644)
    _run(run, ["systemctl", "daemon-reload"])
    units = ["manc-api.service", "manc-fetch.timer", "manc-run.timer"]
    _run(run, ["systemctl", "enable", "--now", *units])
    _run(run, ["systemctl", "restart", "manc-api.service"])


def system_uv() -> str:
    """The distro's uv: the manc user cannot run one from the owner's home."""
    if found := shutil.which("uv", path=SYSTEM_PATH):
        return found
    raise FileNotFoundError(f"no uv on {SYSTEM_PATH}: `dnf install uv` (the system package)")


def _run(run: Runner, command: list[str]) -> None:
    run(command, check=True)
