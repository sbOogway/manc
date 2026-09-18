"""`manc` entry point on a real temp database; every feed and the calendar are stubbed empty."""

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from manc import cli, llm
from manc.config import load_config
from manc.forecasts import fed_sep, worldbank
from manc.spot import yahoo
from manc.store import db
from manc.store.sql import SqlStore
from tests.fakes import recorded_history

EMPTY_FEED = b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'
NO_RECORD = {"data": None, "status": {"bCodeMessage": [{"errorMessage": "No record found."}]}}

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "forecasts"
WORKBOOK_URL = "https://thedocs.worldbank.org/en/doc/x/related/CMO-April-2026-Forecasts.xlsx"
PUBLISHER_URLS = {
    fed_sep.CALENDAR_URL,
    fed_sep.table_url(date(2026, 9, 16)),
    worldbank.OUTLOOK_URL,
    WORKBOOK_URL,
}
FOMC_CALENDAR = b'<a href="/monetarypolicy/fomcprojtabl20260916.htm">September 16, 2026</a>'
OUTLOOK_PAGE = (
    b'<a href="https://thedocs.worldbank.org/en/doc/x/related/CMO-April-2026-Forecasts.pdf">'
)


@pytest.fixture(autouse=True)
def offline_sources(monkeypatch: pytest.MonkeyPatch) -> Iterator[respx.MockRouter]:
    monkeypatch.setattr(yahoo, "yfinance_history", recorded_history)  # yfinance bypasses httpx
    with respx.mock(assert_all_called=False) as router:
        router.get(host="api.nasdaq.com").mock(return_value=httpx.Response(200, json=NO_RECORD))
        router.get(fed_sep.CALENDAR_URL).mock(
            return_value=httpx.Response(200, content=FOMC_CALENDAR)
        )
        router.get(fed_sep.table_url(date(2026, 9, 16))).mock(
            return_value=httpx.Response(
                200, content=(FIXTURES / "fomcprojtabl20260916.html").read_bytes()
            )
        )
        router.get(worldbank.OUTLOOK_URL).mock(
            return_value=httpx.Response(200, content=OUTLOOK_PAGE)
        )
        router.get(WORKBOOK_URL).mock(
            return_value=httpx.Response(
                200, content=(FIXTURES / "CMO-April-2026-Forecasts.xlsx").read_bytes()
            )
        )
        router.route(name="feeds").mock(return_value=httpx.Response(200, content=EMPTY_FEED))
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


def test_run_stores_one_close_per_asset(migrated_db: str) -> None:
    assert cli.main(["run", "--date", "2026-09-15"]) == 0
    store = SqlStore(db.make_engine())
    closes = {asset.symbol: store.spot.latest(asset.symbol) for asset in load_config().assets}
    assert all(price is not None and price.date == date(2026, 9, 15) for price in closes.values())
    assert closes["EURUSD"].source == "yahoo"


def test_run_pulls_every_configured_feed_and_forecast_query(
    migrated_db: str, offline_sources: respx.MockRouter
) -> None:
    assert cli.main(["run"]) == 0
    requested = {
        str(call.request.url)
        for call in offline_sources.calls
        if call.request.url.host != "api.nasdaq.com" and str(call.request.url) not in PUBLISHER_URLS
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


def test_logs_the_start_and_each_step_by_default(
    migrated_db: str, caplog: pytest.LogCaptureFixture
) -> None:
    assert cli.main(["run", "--date", "2026-09-15"]) == 0
    messages = [record.message for record in caplog.records if record.name.startswith("manc")]
    assert messages[0].startswith("manc run: starting")
    assert "2026-09-15" in messages[0] and "7 assets" in messages[0] and migrated_db in messages[0]
    assert any(message.startswith("calendar: 0 events") for message in messages)
    assert not [record for record in caplog.records if record.levelno < logging.INFO]


def test_verbose_adds_the_debug_lines(migrated_db: str, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="manc")
    assert cli.main(["-v", "run", "--date", "2026-09-15"]) == 0
    assert [record for record in caplog.records if record.levelno == logging.DEBUG]


def test_log_lines_carry_time_level_and_module() -> None:
    record = logging.makeLogRecord(
        {"name": "manc.cli", "levelno": logging.INFO, "levelname": "INFO", "msg": "starting"}
    )
    line = logging.Formatter(cli.LOG_FORMAT, cli.LOG_DATEFMT).format(record)
    assert re.fullmatch(r"\d\d:\d\d:\d\d INFO manc\.cli: starting", line)


def test_run_spins_while_working(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    labels: list[str] = []

    @contextmanager
    def fake_spinner(label: str, **kwargs: object) -> Iterator[None]:
        labels.append(label)
        yield None

    monkeypatch.setattr(cli.progress, "spinner", fake_spinner)
    assert cli.main(["run", "--date", "2026-09-15"]) == 0
    assert labels == ["manc run"]


FORECAST_FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>q</title>
<item><title>Goldman Sachs raises gold target to $4,000 by year-end</title>
<link>https://x/gold</link><pubDate>Mon, 01 Jun 2026 10:00:00 GMT</pubDate></item>
<item><title>Markets wrap: stocks drift</title>
<link>https://x/wrap</link><pubDate>Mon, 01 Jun 2026 11:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_forecasts_backfill_pulls_only_the_query_feeds_and_stores_what_the_llm_finds(
    migrated_db: str,
    offline_sources: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    offline_sources["feeds"].mock(return_value=httpx.Response(200, content=FORECAST_FEED))
    prompts: list[str] = []

    def fake_completion(**kwargs: object) -> object:
        messages = kwargs["messages"]
        prompts.append(messages[-1]["content"])  # type: ignore[index]
        content = (
            '{"forecasts": [{"item": 0, "institution": "Goldman Sachs", "subject": "XAUUSD",'
            ' "value": 4000, "horizon": "year-end", "confidence": 0.9}]}'
        )
        message = type("Message", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice], "model": "free/model"})()

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)

    assert cli.main(["forecasts", "--since", "2026-05-01"]) == 0

    config = load_config()
    requested = {
        str(call.request.url)
        for call in offline_sources.calls
        if str(call.request.url) not in PUBLISHER_URLS
    }
    assert requested == {query.feed.url for query in config.forecasts.queries}
    assert len(prompts) == 1 and "Goldman Sachs raises gold" in prompts[0]
    assert "Markets wrap" not in prompts[0]
    store = SqlStore(db.make_engine())
    [forecast] = store.forecasts_asset.latest("XAUUSD")
    assert (forecast.institution, forecast.value, forecast.model) == (
        "goldman_sachs",
        4000.0,
        "free/model",
    )
    assert forecast.horizon_date == date(2026, 12, 31)
    stored = store.news.since(datetime(2026, 1, 1, tzinfo=UTC))
    assert len(stored) == 2  # both items once, although every query answered with the same feed
    assert len(store.forecasts_macro.latest("united_states")) == 16  # the September SEP
    assert store.forecasts_asset.latest("XAUUSD") == [forecast]  # April's outlook predates since
    assert capsys.readouterr().out.strip() == "news=2 forecasts: asset=1 macro=16"


def test_run_stores_the_publishers_forecasts(migrated_db: str) -> None:
    assert cli.main(["run", "--date", "2026-09-17"]) == 0
    store = SqlStore(db.make_engine())
    assert {row.metric for row in store.forecasts_macro.latest("united_states")} == {
        "gdp",
        "unemployment",
        "pce",
        "policy_rate",
    }


def test_run_tags_the_headlines_through_the_llm(
    migrated_db: str, offline_sources: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    offline_sources["feeds"].mock(return_value=httpx.Response(200, content=FORECAST_FEED))
    schemas: list[str] = []

    def fake_completion(**kwargs: object) -> object:
        schema = kwargs["response_format"].__name__  # type: ignore[attr-defined]
        schemas.append(schema)
        lines = kwargs["messages"][-1]["content"].splitlines()  # type: ignore[index]
        gold = next(index for index, line in enumerate(lines) if "gold target" in line)
        content = {
            "Tagging": f'{{"tags": [{{"item": {gold}, "asset": "XAUUSD", "direction": 1,'
            ' "confidence": 0.9}]}',
            "Extraction": '{"forecasts": []}',
        }[schema]
        message = type("Message", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice], "model": "free/model"})()

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)

    assert cli.main(["run", "--date", "2026-06-01"]) == 0

    assert "Tagging" in schemas
    store = SqlStore(db.make_engine())
    [(item, tag)] = store.news.tagged("XAUUSD", datetime(2026, 5, 1, tzinfo=UTC))
    assert item.url == "https://x/gold"
    assert (tag.direction, tag.confidence, tag.model, tag.prompt_version) == (
        1,
        0.9,
        "free/model",
        "v1",
    )


def test_run_tags_with_the_lexicon_when_the_llm_fails(
    migrated_db: str, offline_sources: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    offline_sources["feeds"].mock(return_value=httpx.Response(200, content=FORECAST_FEED))

    def failing_completion(**kwargs: object) -> object:
        raise RuntimeError("429 rate limited")

    monkeypatch.setattr(llm.litellm, "completion", failing_completion)

    assert cli.main(["run", "--date", "2026-06-01"]) == 0

    store = SqlStore(db.make_engine())
    [(item, tag)] = store.news.tagged("XAUUSD", datetime(2026, 5, 1, tzinfo=UTC))
    assert item.url == "https://x/gold"
    assert (tag.direction, tag.model, tag.prompt_version) == (1, "", "")
