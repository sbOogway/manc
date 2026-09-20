"""The container image: entrypoint, Containerfile and compose stay consistent with the CLI."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "scripts" / "container-entrypoint.sh"


def test_entrypoint_migrates_then_execs_the_command(tmp_path: Path) -> None:
    database = tmp_path / "manc.db"
    result = subprocess.run(
        ["sh", str(ENTRYPOINT), "manc", "--help"],
        cwd=ROOT,
        env={**os.environ, "MANC_DB_URL": f"sqlite:///{database}"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "usage: manc" in result.stdout
    assert database.exists()  # alembic upgrade head ran first
    assert os.access(ENTRYPOINT, os.X_OK)


def test_containerfile_serves_the_api_on_every_interface() -> None:
    containerfile = (ROOT / "Containerfile").read_text()
    assert "MANC_API_HOST=0.0.0.0" in containerfile
    assert "MANC_DB_URL=sqlite:////data/manc.db" in containerfile
    assert "container-entrypoint.sh" in containerfile
    assert containerfile.rstrip().endswith('CMD ["manc", "api"]')
    ignored = (ROOT / ".containerignore").read_text().split()
    assert {".venv", "data", ".env", ".git", "tests"} <= set(ignored)


def test_compose_mounts_the_data_folder_and_the_env_file() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    assert "./data:/data" in compose
    assert "env_file" in compose and ".env" in compose
    # loopback unless .env sets MANC_API_BIND, e.g. a LAN address for the tunnel machine
    assert "${MANC_API_BIND:-127.0.0.1}:8000:8000" in compose
    assert "cloudflared" not in compose and "TUNNEL_TOKEN" not in compose
    assert "profiles" not in compose  # one service, no optional ones
