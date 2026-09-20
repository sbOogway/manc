"""scripts/install.sh installs manc system-wide under a dedicated user (`curl | sudo sh`) and
brings an existing install up to date."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install.sh"
STUBBED = (
    "useradd",
    "usermod",
    "getent",
    "id",
    "sudo",
    "chown",
    "chmod",
    "setfacl",
    "loginctl",
    "systemctl",
    "podman",
    "uv",
    "curl",
    "claude",
)
COREUTILS = ("sh", "git", "mkdir", "cp", "ln", "sed", "awk", "grep", "dirname", "env")


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def machine(tmp_path: Path) -> dict[str, Path]:
    """A prefix standing in for /, stubs for every privileged tool, and a bare origin holding
    the files the install reads from the clone."""
    prefix = tmp_path / "root"
    (prefix / "etc").mkdir(parents=True)
    (prefix / "etc" / "subuid").write_text("mattia:100000:65536\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for command in STUBBED:
        stub = bin_dir / command
        stub.write_text(f'#!/bin/sh\necho "{command} $*" >> "{calls}"\n')
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    # id -u → root; id -u manc → the service user's uid; getent passwd manc → unknown until created
    (bin_dir / "id").write_text(
        f'#!/bin/sh\necho "id $*" >> "{calls}"\n[ "$2" = manc ] && echo 987 || echo 0\n'
    )
    (bin_dir / "getent").write_text(
        f'#!/bin/sh\necho "getent $*" >> "{calls}"\ngrep -q "^useradd" "{calls}" 2>/dev/null\n'
    )
    # sudo -u user [env ...] command: run the command itself
    (bin_dir / "sudo").write_text(f'#!/bin/sh\necho "sudo $*" >> "{calls}"\nshift 2\nexec "$@"\n')
    for command in COREUTILS:
        (bin_dir / command).symlink_to(shutil.which(command))
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "-q", "-b", "main", str(origin), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("clone", "-q", str(origin), str(seed), cwd=tmp_path)
    _git("config", "user.email", "test@example.org", cwd=seed)
    _git("config", "user.name", "test", cwd=seed)
    units = [path.relative_to(ROOT).as_posix() for path in (ROOT / "systemd").iterdir()]
    for relative in (".env.example", "pyproject.toml", *units):
        target = seed / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    _git("add", "-A", cwd=seed)
    _git("commit", "-q", "-m", "seed", cwd=seed)
    _git("push", "-q", "origin", "main", cwd=seed)
    return {"prefix": prefix, "bin": bin_dir, "calls": calls, "origin": origin, "seed": seed}


def _run(machine: dict[str, Path], **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": str(machine["bin"]),
        "MANC_REPO": str(machine["origin"]),
        "MANC_ROOT": str(machine["prefix"]),
        "SUDO_USER": "mattia",
        **extra_env,
    }
    return subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True)


def _recorded(machine: dict[str, Path]) -> list[str]:
    return machine["calls"].read_text().splitlines()


def _in_order(recorded: list[str], *steps: str) -> None:
    positions = []
    for step in steps:
        matches = [index for index, line in enumerate(recorded) if line.startswith(step)]
        assert matches, f"{step!r} never ran:\n" + "\n".join(recorded)
        positions.append(matches[0])
    assert positions == sorted(positions), "\n".join(recorded)


def test_first_run_creates_the_user_the_tree_and_the_units(machine: dict[str, Path]) -> None:
    result = _run(machine)
    assert result.returncode == 0, result.stderr + result.stdout
    prefix = machine["prefix"]
    assert (prefix / "opt" / "manc" / ".git").is_dir()
    assert (prefix / "opt" / "manc" / ".env").is_symlink()
    env_file = prefix / "etc" / "manc" / "env"
    assert env_file.is_file() and "MANC_DATA_DIR=/var/lib/manc/data" in env_file.read_text()
    run_unit = (prefix / "etc" / "systemd" / "system" / "manc-run.service").read_text()
    assert "User=mattia" in run_unit and "@OWNER@" not in run_unit
    assert (prefix / "etc" / "systemd" / "system" / "manc-run.timer").is_file()
    user_units = prefix / "var" / "lib" / "manc" / ".config" / "systemd" / "user"
    assert {unit.name for unit in user_units.iterdir()} == {
        "manc-api.service",
        "manc-fetch.service",
        "manc-fetch.timer",
    }
    recorded = _recorded(machine)
    _in_order(
        recorded,
        "useradd -r",
        "usermod --add-subuids 165536-231071 --add-subgids 165536-231071 manc",
        "loginctl enable-linger manc",
        "setfacl",
        "sudo -u manc",  # the clone and the sync happen as the service user
        "uv sync --frozen",
        "uv run alembic upgrade head",
        "podman compose build",
        "systemctl --user daemon-reload",
        "systemctl --user enable --now manc-api.service",
        "systemctl --user enable --now manc-fetch.timer",
        "systemctl --user restart manc-api.service",
        "systemctl daemon-reload",
        "systemctl enable --now manc-run.timer",
        "curl -sf http://127.0.0.1:8000/api/v1/assets",
    )
    assert "/etc/manc/env" in result.stdout  # the one manual step
    assert "npm" not in " ".join(recorded)  # the server never builds the site


def test_second_run_pulls_and_keeps_the_env_and_the_user(machine: dict[str, Path]) -> None:
    assert _run(machine).returncode == 0
    env_file = machine["prefix"] / "etc" / "manc" / "env"
    env_file.write_text("MISTRAL_API_KEY=secret\n")
    seed = machine["seed"]
    (seed / "NEWS").write_text("later\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-q", "-m", "later", cwd=seed)
    _git("push", "-q", "origin", "main", cwd=seed)
    result = _run(machine)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (machine["prefix"] / "opt" / "manc" / "NEWS").is_file()  # pulled
    assert env_file.read_text() == "MISTRAL_API_KEY=secret\n"
    recorded = _recorded(machine)
    assert sum(line.startswith("useradd") for line in recorded) == 1
    assert sum(line.startswith("usermod --add-subuids") for line in recorded) == 1


def test_refuses_without_root_or_without_a_calling_user(machine: dict[str, Path]) -> None:
    (machine["bin"] / "id").write_text("#!/bin/sh\necho 1000\n")
    result = _run(machine)
    assert result.returncode == 1 and "root" in result.stderr
    (machine["bin"] / "id").write_text("#!/bin/sh\necho 0\n")
    result = _run(machine, SUDO_USER="")
    assert result.returncode == 1 and "MANC_OWNER" in result.stderr
    assert not machine["calls"].exists() or "useradd" not in machine["calls"].read_text()


def test_installs_uv_system_wide_when_missing_and_stops_on_other_missing_tools(
    machine: dict[str, Path],
) -> None:
    (machine["bin"] / "podman").unlink()
    result = _run(machine)
    assert result.returncode == 1 and "podman" in result.stderr
    (machine["bin"] / "podman").symlink_to(machine["bin"] / "loginctl")
    (machine["bin"] / "uv").unlink()
    result = _run(machine)
    assert result.returncode == 1 and "uv" in result.stderr
    assert "curl -LsSf https://astral.sh/uv/install.sh" in machine["calls"].read_text()


def test_script_is_executable_and_posix() -> None:
    assert os.access(SCRIPT, os.X_OK)
    assert SCRIPT.read_text().startswith("#!/usr/bin/env sh\n")
