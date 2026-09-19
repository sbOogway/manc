"""`manc` command line: run | rescore | forecasts | api | ui | serve."""

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, time

import uvicorn

from manc.analysis.lexicon import LexiconAnalyzer
from manc.analysis.llm import LlmAnalyzer
from manc.api.app import create_app
from manc.calendar.nasdaq import NasdaqCalendar
from manc.config import Config, load_config
from manc.forecasts.extractor import LlmExtractor
from manc.forecasts.fed_sep import FedSep
from manc.forecasts.interface import ForecastProvider
from manc.forecasts.worldbank import WorldBankOutlook
from manc.formulas.contract import IndexScore
from manc.formulas.registry import get_formula
from manc.llm import complete
from manc.news.rss import RssNews
from manc.pipeline import fetch_forecasts, rescore, run
from manc.spot.yahoo import YahooSpot
from manc.store import db
from manc.store.sql import SqlStore

M4_COMMANDS = ("ui", "serve")
API_HOST = "127.0.0.1"
API_PORT = 8000
LOG_FORMAT = "%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s"
LOG_DATEFMT = "%H:%M:%S"

log = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # no-op if a handler is already installed
    logging.basicConfig(stream=sys.stderr, format=LOG_FORMAT, datefmt=LOG_DATEFMT)
    logging.getLogger("manc").setLevel(logging.DEBUG if args.verbose else logging.INFO)
    if args.command in M4_COMMANDS:
        print(f"manc {args.command}: not implemented yet (milestone M4)", file=sys.stderr)
        return 2
    try:
        store = SqlStore(db.make_engine())
    except RuntimeError as error:
        print(f"manc: {error}", file=sys.stderr)
        return 1
    config = load_config()
    if args.command == "api":
        log.info("manc api: serving http://%s:%d, %s", API_HOST, API_PORT, db.database_url())
        uvicorn.run(create_app(config, store), host=API_HOST, port=API_PORT)
        return 0
    if args.command == "forecasts":
        return _backfill_forecasts(config, store, args.since)
    if args.command == "run":
        as_of = _as_of(args.date)
        log.info(
            "manc run: starting, scoring %s as of %s, %d assets, %s, model %s",
            as_of.date(),
            as_of.strftime("%H:%M UTC"),
            len(config.assets),
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
            summarize=None,  # a replay keeps the template-only report
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


def _forecast_providers(config: Config, store: SqlStore) -> list[ForecastProvider]:
    """The extractor over stored news, then the structured publishers."""
    return [LlmExtractor(config, store.news), FedSep(), WorldBankOutlook()]


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

    run_cmd = commands.add_parser("run", help="fetch, tag, score and store every asset")
    run_cmd.add_argument("--date", type=date.fromisoformat, help="score as of this day (UTC)")

    rescore_cmd = commands.add_parser("rescore", help="recompute stored days under a formula")
    rescore_cmd.add_argument("--formula", help="formula name; defaults to config/scoring.yaml")
    rescore_cmd.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    rescore_cmd.add_argument("--to", dest="end", type=date.fromisoformat, help="default: today")

    forecasts_cmd = commands.add_parser(
        "forecasts", help="backfill institutional forecasts from the per-asset query feeds"
    )
    forecasts_cmd.add_argument(
        "--since", type=date.fromisoformat, required=True, help="earliest publication day"
    )

    commands.add_parser("api", help=f"serve the REST API on http://{API_HOST}:{API_PORT}")
    for name in M4_COMMANDS:
        commands.add_parser(name, help="milestone M4")
    return parser
