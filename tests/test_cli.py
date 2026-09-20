"""`manc` entry point on a real temp database; every feed, the calendar and the LLM are stubbed."""

import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import httpx
import pytest
import respx

from manc import cli, llm
from manc.chain import coinmetrics, defillama, solana_rpc
from manc.config import load_config
from manc.forecasts import fed_sep, worldbank
from manc.spot import yahoo
from manc.store import db
from manc.store.sql import SqlStore
from tests.fakes import recorded_history

EMPTY_FEED = b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'
NO_RECORD = {"data": None, "status": {"bCodeMessage": [{"errorMessage": "No record found."}]}}

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "forecasts"
CHAIN = Path(__file__).resolve().parent / "fixtures" / "chain"
NON_FEED_HOSTS = {  # the calendar and the on-chain sources; anything else a run asks for is a feed
    "api.nasdaq.com",
    "community-api.coinmetrics.io",
    "api.llama.fi",
    "stablecoins.llama.fi",
    "api.mainnet-beta.solana.com",
}
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


def offline_completion(**kwargs: object) -> object:
    """Every model fails: the tagger falls back to the lexicon, the report has no summary."""
    raise RuntimeError("offline")


@pytest.fixture(autouse=True)
def offline_sources(monkeypatch: pytest.MonkeyPatch) -> Iterator[respx.MockRouter]:
    monkeypatch.setattr(yahoo, "yfinance_history", recorded_history)  # yfinance bypasses httpx
    monkeypatch.setattr(llm.litellm, "completion", offline_completion)
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
        for url, name in (
            (coinmetrics.ENDPOINT, "coinmetrics.json"),
            (defillama.fees_url("solana"), "defillama-fees-solana.json"),
            (defillama.tvl_url("solana"), "defillama-tvl-solana.json"),
            (defillama.stablecoins_url("solana"), "defillama-stablecoins-solana.json"),
        ):
            router.get(url).mock(
                return_value=httpx.Response(200, json=json.loads((CHAIN / name).read_text()))
            )
        router.get(host="api.llama.fi").mock(return_value=httpx.Response(200, json=[]))
        router.get(host="stablecoins.llama.fi").mock(return_value=httpx.Response(200, json=[]))
        router.post(solana_rpc.RPC_URL).mock(
            return_value=httpx.Response(
                200, json=json.loads((CHAIN / "solana-performance.json").read_text())
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
    assert len(lines) == len(load_config().active_assets)
    assert lines[0].split() == ["2026-09-15", "BTCUSD", "0.0", "v2", "news=0", "events=0"]


def test_run_stores_one_close_per_asset(migrated_db: str) -> None:
    assert cli.main(["run", "--date", "2026-09-15"]) == 0
    store = SqlStore(db.make_engine())
    config = load_config()
    closes = {asset.symbol: store.spot.latest(asset.symbol) for asset in config.active_assets}
    assert all(price is not None and price.date == date(2026, 9, 15) for price in closes.values())
    assert closes["BTCUSD"].source == "yahoo"
    assert store.spot.latest("EURUSD") is None  # forex is not an active kind


def test_run_pulls_every_configured_feed_and_forecast_query(
    migrated_db: str, offline_sources: respx.MockRouter
) -> None:
    assert cli.main(["run"]) == 0
    requested = {
        str(call.request.url)
        for call in offline_sources.calls
        if call.request.url.host not in NON_FEED_HOSTS
        and str(call.request.url) not in PUBLISHER_URLS
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
    assert len(capsys.readouterr().out.strip().splitlines()) == len(load_config().active_assets)


def test_rescore_prints_range(migrated_db: str, capsys: pytest.CaptureFixture) -> None:
    code = cli.main(["rescore", "--formula", "v1", "--from", "2026-09-14", "--to", "2026-09-15"])
    assert code == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 2 * len(load_config().active_assets)


def test_unmigrated_database_fails_with_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("MANC_DB_URL", f"sqlite:///{tmp_path / 'empty.db'}")
    assert cli.main(["run"]) == 1
    assert "alembic upgrade head" in capsys.readouterr().err


class FakeSiteServer:
    """Records how the site server was built and returns at once instead of serving."""

    instances: ClassVar[list["FakeSiteServer"]] = []

    def __init__(self, address: tuple[str, int], handler: object) -> None:
        self.address = address
        self.handler = handler
        self.served = False
        FakeSiteServer.instances.append(self)

    def serve_forever(self) -> None:
        self.served = True


@pytest.fixture
def site_server(monkeypatch: pytest.MonkeyPatch) -> type[FakeSiteServer]:
    FakeSiteServer.instances.clear()
    monkeypatch.setattr(cli, "ThreadingHTTPServer", FakeSiteServer)
    return FakeSiteServer


def test_ui_serves_the_site_folder(site_server: type[FakeSiteServer]) -> None:
    assert cli.main(["ui"]) == 0
    [server] = site_server.instances
    assert server.address == ("127.0.0.1", 8050)
    assert server.served
    assert (Path(server.handler.keywords["directory"]) / "index.html").is_file()


def test_serve_starts_the_api_in_a_thread_and_the_site(
    migrated_db: str, site_server: type[FakeSiteServer], monkeypatch: pytest.MonkeyPatch
) -> None:
    served: dict[str, object] = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: served.update(kwargs))
    assert cli.main(["serve"]) == 0
    [server] = site_server.instances
    assert server.served
    assert served["port"] == 8000


def test_api_serves_the_app_with_uvicorn(migrated_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    served: dict[str, object] = {}

    def fake_run(app: object, **kwargs: object) -> None:
        served["app"] = app
        served.update(kwargs)

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)
    assert cli.main(["api"]) == 0
    assert (served["host"], served["port"]) == ("127.0.0.1", 8000)
    assert served["app"].title == "manc"  # type: ignore[attr-defined]


def test_api_binds_the_host_from_the_environment(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    served: dict[str, object] = {}
    monkeypatch.setenv("MANC_API_HOST", "0.0.0.0")
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kwargs: served.update(kwargs))
    assert cli.main(["api"]) == 0
    assert (served["host"], served["port"]) == ("0.0.0.0", 8000)


def test_api_refuses_an_unmigrated_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.setenv("MANC_DB_URL", f"sqlite:///{tmp_path / 'empty.db'}")
    assert cli.main(["api"]) == 1
    assert "alembic upgrade head" in capsys.readouterr().err


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
    assert (
        "2026-09-15" in messages[0]
        and f"{len(load_config().active_assets)} assets" in messages[0]
        and migrated_db in messages[0]
    )
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
    assert re.fullmatch(r"\d\d:\d\d:\d\d\.\d{3} INFO manc\.cli: starting", line)


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
            f' "confidence": 0.9}}, {{"item": {gold}, "asset": "BTCUSD", "direction": 1,'
            ' "confidence": 0.8}]}',
            "Extraction": '{"forecasts": []}',
            "Summary": '{"paragraph": "Gold got a target."}',
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
    assert store.scores.series("XAUUSD", "v2", date(2026, 6, 1), date(2026, 6, 1)) == []
    [score] = store.scores.series("BTCUSD", "v2", date(2026, 6, 1), date(2026, 6, 1))
    assert score.score > 0  # tagged for an active kind, so scored
    assert "\n\nGold got a target.\n\n" in score.report_md
    assert score.report_md.endswith("Summary by free/model.\n")


def test_rescore_with_summaries_asks_the_model(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    schemas: list[str] = []

    def fake_completion(**kwargs: object) -> object:
        schemas.append(kwargs["response_format"].__name__)  # type: ignore[attr-defined]
        message = type("Message", (), {"content": '{"paragraph": "Replayed."}'})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice], "model": "free/model"})()

    monkeypatch.setattr(llm.litellm, "completion", fake_completion)
    code = cli.main(["rescore", "--from", "2026-09-15", "--to", "2026-09-15", "--summaries"])
    assert code == 0
    assert schemas == ["Summary"] * len(load_config().active_assets)
    [score] = SqlStore(db.make_engine()).scores.series(
        "BTCUSD", "v2", date(2026, 9, 15), date(2026, 9, 15)
    )
    assert "\n\nReplayed.\n\n" in score.report_md


def test_fetch_stores_the_inputs_and_prints_the_counts(
    migrated_db: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    def exploding_completion(**kwargs: object) -> object:
        raise AssertionError("fetch must not call the LLM")

    monkeypatch.setattr(llm.litellm, "completion", exploding_completion)
    assert cli.main(["fetch"]) == 0
    assert re.fullmatch(r"events=\d+ news=\d+ closes=\d+\n", capsys.readouterr().out)
    store = SqlStore(db.make_engine())
    assert store.spot.latest("BTCUSD") is not None
    assert store.scores.latest_day() is None


def test_chain_backfill_stores_every_provider_and_prints_the_count(
    migrated_db: str, capsys: pytest.CaptureFixture
) -> None:
    assert cli.main(["chain", "--since", "2026-09-17"]) == 0
    assert re.fullmatch(
        r"chain: \d+ rows for \d+ coins since 2026-09-17\n", capsys.readouterr().out
    )
    store = SqlStore(db.make_engine())
    assert set(store.chain.latest("BTCUSD")) >= {"active_addresses", "mvrv", "exchange_inflow_usd"}
    assert set(store.chain.latest("SOLUSD")) == {
        "fees_usd",
        "tvl_usd",
        "stablecoins_usd",
        "tx_per_second",
    }
    assert store.chain.latest("EURUSD") == {}


def test_run_stores_chain_metrics_too(migrated_db: str) -> None:
    assert cli.main(["run", "--date", "2026-09-19"]) == 0
    assert "active_addresses" in SqlStore(db.make_engine()).chain.latest("ETHUSD")


def test_rescore_never_calls_the_llm(migrated_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    def exploding_completion(**kwargs: object) -> object:
        raise AssertionError("rescore must not call the LLM")

    monkeypatch.setattr(llm.litellm, "completion", exploding_completion)
    assert cli.main(["rescore", "--from", "2026-09-15", "--to", "2026-09-15"]) == 0
    [score] = SqlStore(db.make_engine()).scores.series(
        "BTCUSD", "v2", date(2026, 9, 15), date(2026, 9, 15)
    )
    assert score.report_md.startswith("# BTCUSD 2026-09-15: 0 neutral\n\n## Components")


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
