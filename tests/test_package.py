"""The wheel is self-contained: `uv tool install` yields a manc that finds its configuration and
migrations without a checkout."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from manc.config import DEFAULT_CONFIG_DIR, load_config
from manc.store import db

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out), "--quiet"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return next(out.glob("manc-*.whl"))


def test_wheel_carries_the_config_files_and_the_migrations(wheel: Path) -> None:
    names = set(zipfile.ZipFile(wheel).namelist())
    for yaml in DEFAULT_CONFIG_DIR.glob("*.yaml"):
        assert f"manc/config/{yaml.name}" in names, yaml.name
    assert "manc/migrations/env.py" in names
    versions = [name for name in names if name.startswith("manc/migrations/versions/")]
    assert versions and any(name.endswith("_initial.py") for name in versions)
    assert not any(name.startswith("manc/config.py") for name in names)  # the module is the package
    assert "manc/systemd/manc-api.service" in names and "manc/systemd/env.example" in names


def test_config_and_migrations_live_inside_the_package() -> None:
    assert DEFAULT_CONFIG_DIR == ROOT / "src" / "manc" / "config"
    assert load_config().assets  # no argument: the packaged files
    assert (ROOT / "src" / "manc" / "migrations" / "env.py").is_file()
    assert not (ROOT / "config").exists() and not (ROOT / "migrations").exists()


def test_upgrade_works_from_any_working_directory(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'elsewhere.db'}"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from manc.store import db; db.upgrade(); print(db.is_at_head(db.make_engine()))",
        ],
        cwd=tmp_path,
        env={**os.environ, "MANC_DB_URL": url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"
    assert db.is_at_head(db.make_engine(url))
