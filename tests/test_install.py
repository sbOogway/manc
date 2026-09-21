"""`manc install` lays the production machine out: the manc user, /var/lib/manc, /etc/manc/env
and the system units, then enables them. Everything privileged goes through one recorded
runner, the files land under a prefix."""

import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from manc import cli, install
from manc.install import CONSTRAINTS, UNITS_DIR

ROOT = Path(__file__).resolve().parents[1]


class Recorder:
    """Stands in for subprocess.run: records every command, answers `getent` from a set."""

    def __init__(self, users: set[str] | None = None) -> None:
        self.users = users or set()
        self.commands: list[list[str]] = []
        self.environments: list[dict[str, str]] = []

    def __call__(self, command: list[str], **kwargs: object) -> "Recorder":
        self.commands.append(command)
        self.environments.append(dict(kwargs.get("env") or {}))
        self.returncode = 0
        if command[:2] == ["getent", "passwd"]:
            self.returncode = 0 if command[2] in self.users else 2
        elif kwargs.get("check") is not True:
            raise AssertionError(f"{command} must run with check=True")  # failures stop the install
        if command[0] == "useradd":
            self.users.add(command[-1])
        return self

    def lines(self) -> list[str]:
        return [" ".join(command) for command in self.commands]


def _in_order(lines: list[str], *steps: str) -> None:
    positions = []
    for step in steps:
        matches = [index for index, line in enumerate(lines) if line.startswith(step)]
        assert matches, f"{step!r} never ran:\n" + "\n".join(lines)
        positions.append(matches[0])
    assert positions == sorted(positions), "\n".join(lines)


@pytest.fixture
def root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(install, "system_uv", lambda: "/usr/bin/uv")


def test_first_install_creates_everything_in_order(tmp_path: Path, root: None) -> None:
    runner = Recorder()
    install.install(prefix=tmp_path, run=runner)
    env_file = tmp_path / "etc" / "manc" / "env"
    assert env_file.read_text() == (UNITS_DIR / "env.example").read_text()
    assert oct(env_file.stat().st_mode & 0o777) == "0o640"
    constraints = tmp_path / "etc" / "manc" / "constraints.txt"
    assert constraints.read_text() == CONSTRAINTS.read_text()  # readable by the manc user
    data = tmp_path / "var" / "lib" / "manc"
    assert data.is_dir() and oct(data.stat().st_mode & 0o7777) == "0o750"
    system = tmp_path / "etc" / "systemd" / "system"
    assert {path.name for path in system.iterdir()} == {
        path.name for path in UNITS_DIR.iterdir() if path.name != "env.example"
    }
    assert (system / "manc-api.service").read_text() == (UNITS_DIR / "manc-api.service").read_text()
    as_manc = "runuser -u manc -- env -i HOME=/var/lib/manc PATH=/var/lib/manc/.local/bin:/usr/bin"
    _in_order(
        runner.lines(),
        "getent passwd manc",
        "useradd -r -m -d /var/lib/manc -s /usr/sbin/nologin manc",
        "chown manc:manc",
        "chown root:manc",
        f"{as_manc} /usr/bin/uv tool install --force --python 3.12 "
        f"--constraints /etc/manc/constraints.txt {install.SOURCE}",
        f"{as_manc} MANC_DB_URL=sqlite:////var/lib/manc/manc.db manc migrate",
        "systemctl daemon-reload",
        "systemctl enable --now manc-api.service manc-fetch.timer manc-run.timer",
        "systemctl restart manc-api.service",
    )
    for line in runner.lines():  # one user owns the database: nothing to share with anyone
        assert not line.startswith(("usermod", "chmod", "setfacl")), line


def test_the_tool_and_the_migration_run_as_manc_in_its_own_home(tmp_path: Path, root: None) -> None:
    """`runuser` keeps root's environment, so HOME is set by hand: uv installs under it."""
    runner = Recorder()
    install.install(prefix=tmp_path, run=runner)
    as_manc = [line for line in runner.lines() if line.startswith("runuser")]
    assert len(as_manc) == 2
    for line in as_manc:
        assert "env -i HOME=/var/lib/manc" in line


def test_uv_must_be_the_system_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """The manc user cannot run a uv from the owner's home; the distro package is on /usr/bin."""
    monkeypatch.setattr(install.shutil, "which", lambda name, path=None: None)
    with pytest.raises(FileNotFoundError, match="dnf install uv"):
        install.system_uv()
    found = lambda name, path=None: "/usr/bin/uv" if path and "/usr/bin" in path else None  # noqa: E731
    monkeypatch.setattr(install.shutil, "which", found)
    assert install.system_uv() == "/usr/bin/uv"


def test_the_default_source_is_main() -> None:
    """A fix reaches the machine without a release; `--source` takes a tag when one is wanted."""
    assert install.SOURCE == "git+https://github.com/sbOogway/manc@main"


def test_the_constraints_pin_every_dependency_from_the_lock() -> None:
    """`uv tool install` from git ignores uv.lock; the exported pins ride in the wheel."""
    pins = {
        line.split("==")[0]: line.split("==")[1].split(" ")[0]
        for line in CONSTRAINTS.read_text().splitlines()
        if "==" in line
    }
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    for requirement in pyproject["project"]["dependencies"]:
        name = re.split(r"[\[><=~!;\s]", requirement, maxsplit=1)[0]
        assert name in pins, f"{name} is not pinned in {CONSTRAINTS}"
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked = {
        package["name"]: package["version"]
        for package in lock["package"]
        if package["name"] != "manc"
    }
    for name, version in pins.items():
        assert locked.get(name) == version, f"{name}=={version} is not what uv.lock says"


def test_the_source_can_be_a_local_repository(tmp_path: Path, root: None) -> None:
    runner = Recorder()
    install.install(source="git+file:///tmp/manc.git", prefix=tmp_path, run=runner)
    assert any(line.endswith("git+file:///tmp/manc.git") for line in runner.lines())


def test_second_install_keeps_the_env_file_and_the_user(tmp_path: Path, root: None) -> None:
    first = Recorder()
    install.install(prefix=tmp_path, run=first)
    env_file = tmp_path / "etc" / "manc" / "env"
    env_file.write_text("MISTRAL_API_KEY=secret\n")
    again = Recorder(users=first.users)
    install.install(prefix=tmp_path, run=again)
    assert env_file.read_text() == "MISTRAL_API_KEY=secret\n"
    assert not any(line.startswith("useradd") for line in again.lines())
    assert any(line.startswith("systemctl restart manc-api.service") for line in again.lines())


def test_refuses_without_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    with pytest.raises(PermissionError, match="root"):
        install.install(prefix=tmp_path, run=Recorder())


def test_cli_install_takes_the_source(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(install, "install", lambda **kw: calls.append(kw["source"]))
    assert cli.main(["install"]) == 0
    assert calls == [install.SOURCE]
    out = capsys.readouterr().out
    assert "manc-run.timer" in out and "sudo -u manc -H claude" in out  # the login is next
    assert cli.main(["install", "--source", "git+file:///x"]) == 0
    assert calls[-1] == "git+file:///x"


def test_cli_install_reports_refusals_and_failed_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    def refuse(**_: object) -> None:
        raise PermissionError("run as root")

    monkeypatch.setattr(install, "install", refuse)
    assert cli.main(["install"]) == 1
    assert "root" in capsys.readouterr().err

    def fail(**_: object) -> None:
        raise subprocess.CalledProcessError(1, ["useradd"])

    monkeypatch.setattr(install, "install", fail)
    assert cli.main(["install"]) == 1
    assert "useradd" in capsys.readouterr().err

    def missing(**_: object) -> None:
        raise FileNotFoundError("uv not found")

    monkeypatch.setattr(install, "install", missing)
    assert cli.main(["install"]) == 1
    assert "uv not found" in capsys.readouterr().err
