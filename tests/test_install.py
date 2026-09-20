"""`manc install` lays the production machine out: the manc user, /var/lib/manc, /etc/manc/env
and the system units, then enables them. Everything privileged goes through one recorded
runner, the files land under a prefix."""

import os
from pathlib import Path

import pytest

from manc import cli, install
from manc.install import UNITS_DIR


class Recorder:
    """Stands in for subprocess.run: records every command, answers `getent` from a set."""

    def __init__(self, users: set[str] | None = None) -> None:
        self.users = users or set()
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> "Recorder":
        self.commands.append(command)
        self.returncode = 0
        if command[:2] == ["getent", "passwd"]:
            self.returncode = 0 if command[2] in self.users else 2
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
    system = tmp_path / "etc" / "systemd" / "system"
    assert {path.name for path in system.iterdir()} == {
        path.name for path in UNITS_DIR.iterdir() if path.name != "env.example"
    }
    assert (system / "manc-api.service").read_text() == (UNITS_DIR / "manc-api.service").read_text()
    _in_order(
        runner.lines(),
        "getent passwd manc",
        "useradd -r -m -d /var/lib/manc -s /usr/sbin/nologin manc",
        "usermod -aG manc mattia",
        "chown manc:manc",
        "setfacl -d -m g:manc:rwx",
        "chown root:manc",
        "runuser -u manc -- env MANC_DB_URL=sqlite:////var/lib/manc/manc.db manc migrate",
        "systemctl daemon-reload",
        "systemctl enable --now manc-api.service manc-fetch.timer manc-run@mattia.timer",
        "systemctl restart manc-api.service",
    )


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


def test_cli_install_takes_the_owner(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(install, "install", lambda owner, **_: calls.append(owner))
    assert cli.main(["install", "--owner", "mattia"]) == 0
    assert calls == ["mattia"]
    assert "manc-run@mattia.timer" in capsys.readouterr().out
    monkeypatch.setattr(
        install, "install", lambda owner, **_: (_ for _ in ()).throw(PermissionError("run as root"))
    )
    assert cli.main(["install", "--owner", "mattia"]) == 1
    assert "root" in capsys.readouterr().err
