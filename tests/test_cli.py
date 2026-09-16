"""`manc` entry point on a real temp database, with every RSS feed stubbed to be empty."""

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from manc import cli
from manc.config import load_config
from manc.store import db

EMPTY_FEED = b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'


@pytest.fixture(autouse=True)
def offline_feeds() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.route().mock(return_value=httpx.Response(200, content=EMPTY_FEED))
        yield router


@pytest.fixture
def migrated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("MANC_DB_URL", url)
    db.upgrade(url)
    return url


def test_run_prints_one_line_per_asset(migrated_db: str, capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["run", "--date", "2026-09-15"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 7
    assert lines[0].split() == ["2026-09-15", "EURUSD", "50.0", "v1", "news=0", "events=0"]


def test_run_pulls_every_configured_feed(migrated_db: str, offline_feeds: respx.MockRouter) -> None:
    assert cli.main(["run"]) == 0
    requested = {str(call.request.url) for call in offline_feeds.calls}
    assert requested == {feed.url for feed in load_config().feeds}


def test_run_defaults_to_today(migrated_db: str, capsys: pytest.CaptureFixture) -> None:
    assert cli.main(["run"]) == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 7


def test_rescore_prints_range(migrated_db: str, capsys: pytest.CaptureFixture) -> None:
    code = cli.main(["rescore", "--formula", "v1", "--from", "2026-09-14", "--to", "2026-09-15"])
    assert code == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 14


def test_unmigrated_database_fails_with_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("MANC_DB_URL", f"sqlite:///{tmp_path / 'empty.db'}")
    assert cli.main(["run"]) == 1
    assert "alembic upgrade head" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["api", "ui", "serve"])
def test_m4_commands_are_stubs(command: str, capsys: pytest.CaptureFixture) -> None:
    assert cli.main([command]) == 2
    assert "not implemented yet" in capsys.readouterr().err


def test_unknown_command_exits_2() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["frobnicate"])
    assert exit_info.value.code == 2


def test_verbose_logs_each_step(migrated_db: str, caplog: pytest.LogCaptureFixture) -> None:
    assert cli.main(["-v", "run", "--date", "2026-09-15"]) == 0
    assert any("calendar: 0 events" in record.message for record in caplog.records)


def test_quiet_by_default(migrated_db: str, caplog: pytest.LogCaptureFixture) -> None:
    assert cli.main(["run", "--date", "2026-09-15"]) == 0
    assert not [record for record in caplog.records if record.name.startswith("manc")]
