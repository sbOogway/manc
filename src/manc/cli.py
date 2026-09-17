"""`manc` command line: run | rescore | api | ui | serve."""

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, time

from manc.analysis.empty import EmptyAnalyzer
from manc.calendar.nasdaq import NasdaqCalendar
from manc.config import load_config
from manc.forecasts.extractor import LlmExtractor
from manc.formulas.contract import IndexScore
from manc.formulas.registry import get_formula
from manc.news.rss import RssNews
from manc.pipeline import rescore, run
from manc.store import db
from manc.store.sql import SqlStore

M4_COMMANDS = ("api", "ui", "serve")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(stream=sys.stderr)  # no-op if a handler is already installed
    logging.getLogger("manc").setLevel(logging.INFO if args.verbose else logging.WARNING)
    if args.command in M4_COMMANDS:
        print(f"manc {args.command}: not implemented yet (milestone M4)", file=sys.stderr)
        return 2
    try:
        store = SqlStore(db.make_engine())
    except RuntimeError as error:
        print(f"manc: {error}", file=sys.stderr)
        return 1
    config = load_config()
    if args.command == "run":
        scores = run(
            as_of=_as_of(args.date),
            config=config,
            calendar=NasdaqCalendar(config.calendar),
            news=RssNews(config.feeds + config.forecasts.query_feeds),
            analyzer=EmptyAnalyzer(),
            forecasts=LlmExtractor(config, store.news),
            store=store,
            formula=get_formula(config.scoring.formula),
        )
    else:
        scores = rescore(
            config=config,
            store=store,
            formula=get_formula(args.formula or config.scoring.formula),
            start=args.start,
            end=args.end or date.today(),
        )
    for score in scores:
        print(_line(score))
    return 0


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
    parser.add_argument("-v", "--verbose", action="store_true", help="log each step to stderr")
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser("run", help="fetch, tag, score and store every asset")
    run_cmd.add_argument("--date", type=date.fromisoformat, help="score as of this day (UTC)")

    rescore_cmd = commands.add_parser("rescore", help="recompute stored days under a formula")
    rescore_cmd.add_argument("--formula", help="formula name; defaults to config/scoring.yaml")
    rescore_cmd.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    rescore_cmd.add_argument("--to", dest="end", type=date.fromisoformat, help="default: today")

    for name in M4_COMMANDS:
        commands.add_parser(name, help="milestone M4")
    return parser
