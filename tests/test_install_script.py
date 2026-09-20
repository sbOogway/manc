"""scripts/install.sh sets a machine up from nothing (`curl | sh`) and brings one up to date."""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "install.sh"
STUBBED = ("uv", "npm", "podman", "systemctl", "loginctl", "curl", "claude")


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def machine(tmp_path: Path) -> dict[str, Path]:
    """A fake home, stubs for every tool the script calls, and a bare origin holding this repo's
    scripts, units and example env so the clone has what the install needs."""
    home = tmp_path / "home"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for command in STUBBED:
        stub = bin_dir / command
        stub.write_text(f'#!/bin/sh\necho "{command} $*" >> "{calls}"\n')
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    base = tmp_path / "base"  # the coreutils the scripts need, so PATH holds nothing else
    base.mkdir()
    for command in ("sh", "git", "mkdir", "cp", "dirname", "basename", "ln", "id", "pwd"):
        (base / command).symlink_to(shutil.which(command))
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "-q", "-b", "main", str(origin), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("clone", "-q", str(origin), str(seed), cwd=tmp_path)
    _git("config", "user.email", "test@example.org", cwd=seed)
    _git("config", "user.name", "test", cwd=seed)
    units = [path.relative_to(ROOT).as_posix() for path in (ROOT / "systemd").iterdir()]
    for relative in ("scripts/install-systemd.sh", ".env.example", "pyproject.toml", *units):
        target = seed / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
        target.chmod((ROOT / relative).stat().st_mode)
    _git("add", "-A", cwd=seed)
    _git("commit", "-q", "-m", "seed", cwd=seed)
    _git("push", "-q", "origin", "main", cwd=seed)
    return {"home": home, "bin": bin_dir, "base": base, "calls": calls, "origin": origin}


def _run(machine: dict[str, Path], **extra_env: str) -> subprocess.CompletedProcess[str]:
    env = {
        "HOME": str(machine["home"]),
        "PATH": f"{machine['bin']}:{machine['base']}",
        "MANC_REPO": str(machine["origin"]),
        **extra_env,
    }
    return subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True)


def test_first_run_clones_and_sets_everything_up_in_order(machine: dict[str, Path]) -> None:
    result = _run(machine)
    assert result.returncode == 0, result.stderr
    checkout = machine["home"] / "quant" / "manc"
    assert (checkout / ".git").is_dir() and (checkout / ".env").is_file()
    assert (checkout / ".env").read_text() == (ROOT / ".env.example").read_text()
    recorded = machine["calls"].read_text().splitlines()
    expected = [
        "uv sync --frozen",
        "uv run pre-commit install --hook-type pre-commit --hook-type post-merge",
        "uv run alembic upgrade head",
        "npm --prefix site ci",
        "npm --prefix site run build",
        "podman compose build",
        "loginctl enable-linger",
        "systemctl --user daemon-reload",
        "systemctl --user enable --now manc-api.service",
        "systemctl --user restart manc-api.service",
        "curl -sf http://127.0.0.1:8000/api/v1/assets",
    ]
    positions = [
        next(index for index, line in enumerate(recorded) if line.startswith(step))
        for step in expected
    ]
    assert positions == sorted(positions), recorded
    assert "edit" in result.stdout and ".env" in result.stdout  # the one manual step


def test_second_run_pulls_and_keeps_the_env_file(machine: dict[str, Path]) -> None:
    assert _run(machine).returncode == 0
    checkout = machine["home"] / "quant" / "manc"
    (checkout / ".env").write_text("MISTRAL_API_KEY=secret\n")
    seed = machine["origin"].parent / "seed"
    (seed / "NEWS").write_text("later\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-q", "-m", "later", cwd=seed)
    _git("push", "-q", "origin", "main", cwd=seed)
    machine["calls"].unlink()
    result = _run(machine)
    assert result.returncode == 0, result.stderr
    assert (checkout / "NEWS").is_file()  # pulled
    assert (checkout / ".env").read_text() == "MISTRAL_API_KEY=secret\n"
    assert "git clone" not in result.stdout


def test_installs_uv_when_missing_and_stops_on_other_missing_tools(
    machine: dict[str, Path],
) -> None:
    (machine["bin"] / "uv").unlink()
    (machine["bin"] / "podman").unlink()
    result = _run(machine)
    assert result.returncode == 1
    assert "podman" in result.stderr
    assert not machine["calls"].exists() or "uv sync" not in machine["calls"].read_text()


def test_script_is_executable_and_posix() -> None:
    assert os.access(SCRIPT, os.X_OK)
    assert SCRIPT.read_text().startswith("#!/usr/bin/env sh\n")
