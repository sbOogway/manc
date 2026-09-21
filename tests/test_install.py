"""`manc install` lays the production machine out: the manc user, /var/lib/manc, /etc/manc/env
and the system units, then enables them. Everything privileged goes through one recorded
runner, the files land under a prefix."""

import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

import manc
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


def test_first_install_creates_everything_in_order(tmp_path: Path, root: None) -> None:
    runner = Recorder()
    install.install("mattia", prefix=tmp_path, run=runner)
    env_file = tmp_path / "etc" / "manc" / "env"
    assert env_file.read_text() == (UNITS_DIR / "env.example").read_text()
    assert oct(env_file.stat().st_mode & 0o777) == "0o640"
    data = tmp_path / "var" / "lib" / "manc"
    assert data.is_dir() and oct(data.stat().st_mode & 0o7777) == "0o2770"
    assert not any(line.startswith("setfacl") for line in runner.lines())  # setgid + umask do it
    system = tmp_path / "etc" / "systemd" / "system"
    assert {path.name for path in system.iterdir()} == {
        path.name for path in UNITS_DIR.iterdir() if path.name != "env.example"
    }
    assert (system / "manc-api.service").read_text() == (UNITS_DIR / "manc-api.service").read_text()
    _in_order(
        runner.lines(),
        f"uv tool install --force --python 3.12 --constraints {CONSTRAINTS} {install.SOURCE}",
        "getent passwd manc",
        "useradd -r -m -d /var/lib/manc -s /usr/sbin/nologin manc",
        "usermod -aG manc mattia",
        "chown manc:manc",
        "chown root:manc",
        "runuser -u manc -- env MANC_DB_URL=sqlite:////var/lib/manc/manc.db manc migrate",
        "chmod 0660 /var/lib/manc/manc.db",
        "systemctl daemon-reload",
        "systemctl enable --now manc-api.service manc-fetch.timer manc-run@mattia.timer",
        "systemctl restart manc-api.service",
    )
    tool_env = runner.environments[0]  # the tool, its Python and the entry point outside /root
    assert tool_env["UV_TOOL_DIR"] == "/opt/manc/tools"
    assert tool_env["UV_PYTHON_INSTALL_DIR"] == "/opt/manc/python"
    assert tool_env["UV_TOOL_BIN_DIR"] == "/usr/local/bin"


def test_the_default_source_is_the_tag_of_this_version() -> None:
    """A checkout of `main` is never what production runs; a release is a tag."""
    assert f"git+https://github.com/sbOogway/manc@v{manc.__version__}" == install.SOURCE


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
    install.install("mattia", source="git+file:///tmp/manc.git", prefix=tmp_path, run=runner)
    assert runner.lines()[0].endswith("git+file:///tmp/manc.git")


def test_second_install_keeps_the_env_file_and_the_user(tmp_path: Path, root: None) -> None:
    first = Recorder()
    install.install("mattia", prefix=tmp_path, run=first)
    env_file = tmp_path / "etc" / "manc" / "env"
    env_file.write_text("MISTRAL_API_KEY=secret\n")
    again = Recorder(users=first.users)
    install.install("mattia", prefix=tmp_path, run=again)
    assert env_file.read_text() == "MISTRAL_API_KEY=secret\n"
    assert not any(line.startswith("useradd") for line in again.lines())
    assert any(line.startswith("systemctl restart manc-api.service") for line in again.lines())


def test_refuses_without_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    with pytest.raises(PermissionError, match="root"):
        install.install("mattia", prefix=tmp_path, run=Recorder())


def test_cli_install_takes_the_owner_and_the_source(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(install, "install", lambda owner, **kw: calls.append((owner, kw["source"])))
    assert cli.main(["install", "--owner", "mattia"]) == 0
    assert calls == [("mattia", install.SOURCE)]
    assert "manc-run@mattia.timer" in capsys.readouterr().out
    assert cli.main(["install", "--owner", "mattia", "--source", "git+file:///x"]) == 0
    assert calls[-1] == ("mattia", "git+file:///x")


def test_cli_install_reports_refusals_and_failed_commands(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    def refuse(owner: str, **_: object) -> None:
        raise PermissionError("run as root")

    monkeypatch.setattr(install, "install", refuse)
    assert cli.main(["install", "--owner", "mattia"]) == 1
    assert "root" in capsys.readouterr().err

    def fail(owner: str, **_: object) -> None:
        raise subprocess.CalledProcessError(1, ["useradd"])

    monkeypatch.setattr(install, "install", fail)
    assert cli.main(["install", "--owner", "mattia"]) == 1
    assert "useradd" in capsys.readouterr().err
