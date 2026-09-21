"""scripts/publish-site.sh builds site/ and copies the build to the server's site folder."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish-site.sh"


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A folder shaped like the repo, with a stand-in for vite and fakes for rsync and ssh
    that record their arguments instead of touching a machine."""
    work = tmp_path / "work"
    (work / "site" / "src").mkdir(parents=True)
    (work / "site" / "src" / "index.html").write_text("<title>manc</title>")
    (work / "site" / "package.json").write_text(
        '{"name": "fake", "private": true, "scripts": {"build": "rm -rf dist && cp -r src dist"}}'
    )
    (work / "scripts").mkdir()
    (work / "scripts" / "publish-site.sh").write_bytes(SCRIPT.read_bytes())
    (work / "scripts" / "publish-site.sh").chmod(0o755)
    fakes = tmp_path / "bin"
    fakes.mkdir()
    for tool in ("rsync", "ssh"):
        (fakes / tool).write_text(f'#!/bin/sh\necho "{tool} $*" >> "{tmp_path}/calls"\n')
        (fakes / tool).chmod(0o755)
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(work),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@x",
            "commit",
            "-q",
            "-m",
            "site",
        ],
        check=True,
    )
    return work


def _publish(checkout: Path, server: str | None) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PATH": f"{checkout.parent / 'bin'}:{os.environ['PATH']}"}
    environment.pop("MANC_SERVER", None)
    if server is not None:
        environment["MANC_SERVER"] = server
    return subprocess.run(
        ["scripts/publish-site.sh"], cwd=checkout, env=environment, capture_output=True, text=True
    )


def test_builds_then_copies_to_the_server_and_moves_it_under_the_manc_user(checkout: Path) -> None:
    result = _publish(checkout, "me@server")
    assert result.returncode == 0, result.stderr
    assert (checkout / "site" / "dist" / "index.html").is_file()  # the build ran first
    calls = (checkout.parent / "calls").read_text().splitlines()
    into_home = "rsync -a --delete site/dist/ me@server:manc-site/"  # no key for manc needed
    under_manc = "sudo rsync -a --delete --chown=manc:manc manc-site/ /var/lib/manc/site/"
    assert calls == [into_home, f"ssh -t me@server {under_manc}"]
    assert "me@server:/var/lib/manc/site/" in result.stdout


def test_refuses_without_a_server(checkout: Path) -> None:
    result = _publish(checkout, None)
    assert result.returncode != 0
    assert "MANC_SERVER" in result.stderr
    assert not (checkout.parent / "calls").exists()


def test_no_hook_publishes_the_site() -> None:
    """Publishing is a deliberate command, never a side effect of a commit or a pull."""
    import yaml

    config = yaml.safe_load((SCRIPT.parents[1] / ".pre-commit-config.yaml").read_text())
    hooks = [hook for repo in config["repos"] for hook in repo["hooks"]]
    assert "publish-site" not in {hook["id"] for hook in hooks}
    assert all("stages" not in hook for hook in hooks)
    assert "default_stages" not in config
