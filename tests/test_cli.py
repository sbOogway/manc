"""`manc` entry point on a real temp database; every feed and the calendar are stubbed empty."""

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from manc import cli
from manc.config import load_config
from manc.store import db

EMPTY_FEED = b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'
NO_RECORD = {"data": None, "status": {"bCodeMessage": [{"errorMessage": "No record found."}]}}


@pytest.fixture(autouse=True)
def offline_sources() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.get(host="api.nasdaq.com").mock(return_value=httpx.Response(200, json=NO_RECORD))
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


def test_run_pulls_every_configured_feed_and_forecast_query(
    migrated_db: str, offline_sources: respx.MockRouter
) -> None:
    assert cli.main(["run"]) == 0
    requested = {
        str(call.request.url)
        for call in offline_sources.calls
        if call.request.url.host != "api.nasdaq.com"
    }
    config = load_config()
    query_feeds = {query.feed.url for query in config.forecasts.queries}
    assert requested == {feed.url for feed in config.feeds} | query_feeds


def test_run_pulls_every_day_of_the_calendar_window(
    migrated_db: str, offline_sources: respx.MockRouter
) -> None:
    assert cli.main(["run", "--date", "2026-09-15"]) == 0
    windows = load_config().scoring.windows
    first = date(2026, 9, 15) - timedelta(days=windows["released_days"])
    last = date(2026, 9, 15) + timedelta(days=windows["calendar_lookahead_days"])
    requested = {
        call.request.url.params["date"]
        for call in offline_sources.calls
        if call.request.url.host == "api.nasdaq.com"
    }
    expected = {
        (first + timedelta(days=offset + 1)).isoformat()  # the endpoint's one-day offset
        for offset in range((last - first).days + 1)
    }
    assert requested == expected


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
