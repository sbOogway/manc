"""`manc` command line: fetch, chain, run, rescore, forecasts, install, migrate, api, ui, serve."""

import argparse
import logging
import os
import sys
import threading
from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import uvicorn

from manc import install as installer
from manc.analysis.lexicon import LexiconAnalyzer
from manc.analysis.llm import LlmAnalyzer
from manc.api.app import create_app
from manc.calendar.nasdaq import NasdaqCalendar
from manc.chain.coingecko import CoinGecko
from manc.chain.coinmetrics import CoinMetrics
from manc.chain.defillama import DefiLlama
from manc.chain.fear_greed import FearGreed
from manc.chain.interface import ChainProvider
from manc.chain.solana_rpc import SolanaRpc
from manc.config import Config, load_config
from manc.forecasts.extractor import LlmExtractor
from manc.forecasts.fed_sep import FedSep
from manc.forecasts.interface import ForecastProvider
from manc.forecasts.worldbank import WorldBankOutlook
from manc.formulas.contract import IndexScore
from manc.formulas.registry import get_formula
from manc.llm import complete
from manc.news.rss import RssNews
from manc.pipeline import fetch, fetch_chain, fetch_forecasts, rescore, run
from manc.spot.yahoo import YahooSpot
from manc.store import db
from manc.store.sql import SqlStore

API_HOST = "127.0.0.1"  # MANC_API_HOST overrides it (the env file, for the tunnel machine)
API_PORT = 8000
SITE_PORT = 8050
SITE_DIR = Path(__file__).resolve().parents[2] / "site" / "dist"  # what `npm run build` writes
LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s"
LOG_DATEFMT = "%H:%M:%S"

log = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # no-op if a handler is already installed
    logging.basicConfig(stream=sys.stderr, format=LOG_FORMAT, datefmt=LOG_DATEFMT)
    logging.getLogger("manc").setLevel(logging.DEBUG if args.verbose else logging.INFO)
    if args.command == "ui":
        if not _site_built():
            return 1
        _serve_site()
        return 0
    if args.command == "install":
        try:
            installer.install(args.owner)
        except PermissionError as error:
            print(f"manc: {error}", file=sys.stderr)
            return 1
        print(
            f"install: manc-api.service, manc-fetch.timer and manc-run@{args.owner}.timer are up; "
            "edit /etc/manc/env, then `systemctl restart manc-api`"
        )
        return 0
    if args.command == "migrate":
        db.upgrade()
        print(f"migrate: {db.database_url()} at {db.head_revision()}")
        return 0
    try:
        store = SqlStore(db.make_engine())
    except RuntimeError as error:
        print(f"manc: {error}", file=sys.stderr)
        return 1
    config = load_config()
    if args.command == "serve" and not _site_built():
        return 1
    if args.command in ("api", "serve"):
        host = os.environ.get("MANC_API_HOST") or API_HOST
        log.info("manc api: serving http://%s:%d, %s", host, API_PORT, db.database_url())
        serve_api = partial(uvicorn.run, create_app(config, store), host=host, port=API_PORT)
        if args.command == "api":
            serve_api()
            return 0
        threading.Thread(target=serve_api, daemon=True).start()
        _serve_site()
        return 0
    if args.command == "forecasts":
        return _backfill_forecasts(config, store, args.since)
    if args.command == "chain":
        coins = [asset for asset in config.active_assets if asset.chain]
        rows = fetch_chain(_chain_providers(), coins, args.since, date.today(), store)
        print(f"chain: {len(rows)} rows for {len(coins)} coins since {args.since}")
        return 0
    if args.command == "fetch":
        fetched = fetch(
            as_of=datetime.now(UTC),
            config=config,
            calendar=NasdaqCalendar(config.calendar),
            news=RssNews(config.feeds + config.forecasts.query_feeds),
            spot=YahooSpot(),
            store=store,
        )
        print(
            f"events={len(fetched.events)} news={len(fetched.items)} closes={len(fetched.closes)}"
        )
        return 0
    if args.command == "run":
        as_of = _as_of(args.date)
        log.info(
            "manc run: starting, scoring %s as of %s, %d assets, %s, model %s",
            as_of.date(),
            as_of.strftime("%H:%M UTC"),
            len(config.active_assets),
            db.database_url(),
            config.llm.model,
        )
        scores = run(
            as_of=as_of,
            config=config,
            calendar=NasdaqCalendar(config.calendar),
            news=RssNews(config.feeds + config.forecasts.query_feeds),
            analyzer=LlmAnalyzer(config, fallback=LexiconAnalyzer(config.lexicon)),
            forecasts=_forecast_providers(config, store),
            spot=YahooSpot(),
            chain=_chain_providers(),
            store=store,
            formula=get_formula(config.scoring.formula),
            summarize=complete,
        )
    else:
        scores = rescore(
            config=config,
            store=store,
            formula=get_formula(args.formula or config.scoring.formula),
            start=args.start,
            end=args.end or date.today(),
            summarize=complete if args.summaries else None,
        )
    for score in scores:
        print(_line(score))
    return 0


def _backfill_forecasts(config: Config, store: SqlStore, since_day: date) -> int:
    """Pull the per-asset query feeds far back, store them, extract forecasts from the store."""
    since = datetime.combine(since_day, time.min, tzinfo=UTC)
    items = RssNews(config.forecasts.query_feeds).fetch(since)
    store.news.add(*items)
    found = fetch_forecasts(_forecast_providers(config, store), since, store)
    print(f"news={len(items)} forecasts: asset={len(found.asset)} macro={len(found.macro)}")
    return 0


def _chain_providers() -> list[ChainProvider]:
    return [CoinMetrics(), DefiLlama(), SolanaRpc(), FearGreed(), CoinGecko()]


def _forecast_providers(config: Config, store: SqlStore) -> list[ForecastProvider]:
    """The extractor over stored news, then the structured publishers."""
    return [LlmExtractor(config, store.news), FedSep(), WorldBankOutlook()]


def _site_built() -> bool:
    if (SITE_DIR / "index.html").is_file():
        return True
    print(
        f"manc: no built site at {SITE_DIR}: run `cd site && npm ci && npm run build`",
        file=sys.stderr,
    )
    return False


def _serve_site() -> None:
    """The built site from `site/dist`, for the local test against the API."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(SITE_DIR))
    log.info("manc ui: serving %s on http://%s:%d", SITE_DIR, API_HOST, SITE_PORT)
    ThreadingHTTPServer((API_HOST, SITE_PORT), handler).serve_forever()


def _as_of(day: date | None) -> datetime:
    """Now for today; end of day for a past date so its whole news window counts."""
    if day is None or day == datetime.now(UTC).date():
        return datetime.now(UTC)
    return datetime.combine(day, time.max, tzinfo=UTC)


def _line(score: IndexScore) -> str:
    return (
        f"{score.date} {score.asset} {score.score:.1f} {score.formula} "
        f"news={score.n_news} events={score.n_events}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="manc", description="macro analysis, news and calendar")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="also log every feed and calendar day"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("fetch", help="calendar, news and spot closes into the store; no model")
    chain_cmd = commands.add_parser("chain", help="backfill on-chain metrics for the coins")
    chain_cmd.add_argument("--since", type=date.fromisoformat, required=True, help="first day")
    run_cmd = commands.add_parser("run", help="fetch, tag, score and store every asset")
    run_cmd.add_argument("--date", type=date.fromisoformat, help="score as of this day (UTC)")

    rescore_cmd = commands.add_parser("rescore", help="recompute stored days under a formula")
    rescore_cmd.add_argument(
        "--formula", help="formula name; defaults to src/manc/config/scoring.yaml"
    )
    rescore_cmd.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    rescore_cmd.add_argument("--to", dest="end", type=date.fromisoformat, help="default: today")
    rescore_cmd.add_argument(
        "--summaries",
        action="store_true",
        help="also ask the model for the report's opening paragraph (one call per asset and day)",
    )

    forecasts_cmd = commands.add_parser(
        "forecasts", help="backfill institutional forecasts from the per-asset query feeds"
    )
    forecasts_cmd.add_argument(
        "--since", type=date.fromisoformat, required=True, help="earliest publication day"
    )

    install_cmd = commands.add_parser(
        "install", help="as root: the manc user, /var/lib/manc, /etc/manc/env and the systemd units"
    )
    install_cmd.add_argument(
        "--owner", required=True, help="the user whose Claude Code login runs the daily run"
    )
    commands.add_parser(
        "migrate", help="create or migrate the database (MANC_DB_URL) to the current schema"
    )
    commands.add_parser("api", help=f"serve the REST API on http://{API_HOST}:{API_PORT}")
    commands.add_parser("ui", help=f"serve the dashboard on http://{API_HOST}:{SITE_PORT}")
    commands.add_parser("serve", help="the API and the dashboard together")
    return parser
