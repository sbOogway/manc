"""scripts/publish-site.sh builds site/ and pushes the build alone to the gh-pages branch."""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish-site.sh"


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A throwaway repo with a site/ folder and a bare origin, so nothing touches GitHub."""
    remote = tmp_path / "origin.git"
    _git("init", "--bare", "-q", "-b", "main", str(remote), cwd=tmp_path)
    work = tmp_path / "work"
    _git("clone", "-q", str(remote), str(work), cwd=tmp_path)
    _git("config", "user.email", "test@example.org", cwd=work)
    _git("config", "user.name", "test", cwd=work)
    (work / "site" / "src").mkdir(parents=True)
    (work / "site" / "src" / "index.html").write_text("<title>manc</title>")
    (work / "site" / "src" / "app.js").write_text("// app")
    # a stand-in for vite: the build copies src/ into dist/
    (work / "site" / "package.json").write_text(
        '{"name": "fake", "private": true, "scripts": {"build": "rm -rf dist && cp -r src dist"}}'
    )
    (work / ".gitignore").write_text("site/dist/\n")
    (work / "README.md").write_text("# not published")
    (work / "scripts").mkdir()
    (work / "scripts" / "publish-site.sh").write_bytes(SCRIPT.read_bytes())
    (work / "scripts" / "publish-site.sh").chmod(0o755)
    _git("add", "-A", cwd=work)
    _git("commit", "-q", "-m", "site", cwd=work)
    _git("push", "-q", "origin", "main", cwd=work)
    return work


def test_publishes_the_site_folder_alone_to_gh_pages(clone: Path) -> None:
    result = subprocess.run(
        ["sh", "scripts/publish-site.sh"], cwd=clone, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    _git("fetch", "-q", "origin", "gh-pages", cwd=clone)
    published = _git("ls-tree", "--name-only", "-r", "origin/gh-pages", cwd=clone).splitlines()
    assert sorted(published) == ["app.js", "index.html"]
    assert "github.io" in result.stdout


def test_a_second_publish_chains_on_the_first_and_an_unchanged_site_is_a_no_op(
    clone: Path,
) -> None:
    subprocess.run(["sh", "scripts/publish-site.sh"], cwd=clone, check=True, capture_output=True)
    again = subprocess.run(
        ["sh", "scripts/publish-site.sh"], cwd=clone, capture_output=True, text=True
    )
    assert again.returncode == 0 and "already holds" in again.stdout
    (clone / "site" / "src" / "style.css").write_text("body{}")
    _git("add", "-A", cwd=clone)
    _git("commit", "-q", "-m", "style", cwd=clone)
    subprocess.run(["sh", "scripts/publish-site.sh"], cwd=clone, check=True, capture_output=True)
    _git("fetch", "-q", "origin", "gh-pages", cwd=clone)
    assert _git("rev-list", "--count", "origin/gh-pages", cwd=clone) == "2"
    published = _git("ls-tree", "--name-only", "-r", "origin/gh-pages", cwd=clone).splitlines()
    assert sorted(published) == ["app.js", "index.html", "style.css"]


def test_refuses_uncommitted_site_changes(clone: Path) -> None:
    (clone / "site" / "src" / "index.html").write_text("<title>draft</title>")
    result = subprocess.run(
        ["sh", "scripts/publish-site.sh"], cwd=clone, capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "uncommitted" in result.stderr


def test_skips_quietly_off_main_so_the_daily_run_never_publishes_a_branch(clone: Path) -> None:
    _git("checkout", "-q", "-b", "feat/draft", cwd=clone)
    result = subprocess.run(
        ["sh", "scripts/publish-site.sh"], cwd=clone, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "not on main" in result.stdout
    assert _git("ls-remote", "--heads", "origin", "gh-pages", cwd=clone) == ""
