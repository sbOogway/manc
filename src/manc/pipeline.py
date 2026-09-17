"""The daily run (blueprint section 2): fetch, tag, extract forecasts, score, store.

Every input the formula sees is persisted first, so `rescore` can replay any date range
under any formula without touching a provider.
"""

import logging
from datetime import UTC, date, datetime, time, timedelta

from manc.analysis.interface import Analyzer
from manc.calendar.interface import CalendarProvider
from manc.config import Config
from manc.forecasts.interface import ForecastProvider
from manc.formulas.contract import IndexFormula, IndexScore
from manc.news.interface import NewsProvider
from manc.scoring.adapter import build_inputs
from manc.store.interface import Store

log = logging.getLogger(__name__)


def run(
    *,
    as_of: datetime,
    config: Config,
    calendar: CalendarProvider,
    news: NewsProvider,
    analyzer: Analyzer,
    forecasts: ForecastProvider,
    store: Store,
    formula: IndexFormula,
) -> list[IndexScore]:
    windows = config.scoring.windows

    calendar_start = (as_of - timedelta(days=windows["released_days"])).date()
    calendar_end = (as_of + timedelta(days=windows["calendar_lookahead_days"])).date()
    events = calendar.fetch(calendar_start, calendar_end)
    store.events.add(*events)
    log.info("calendar: %d events between %s and %s", len(events), calendar_start, calendar_end)

    news_since = as_of - timedelta(hours=windows["news_hours"])
    items = news.fetch(news_since)
    store.news.add(*items)
    log.info("news: %d items since %s", len(items), news_since)

    tags = analyzer.tag(items, config.assets)
    store.tags.add(*tags)
    log.info("analysis: %d tags", len(tags))

    found = forecasts.fetch(news_since)
    store.forecasts_asset.add(*found.asset)
    store.forecasts_macro.add(*found.macro)
    log.info("forecasts: %d asset, %d macro", len(found.asset), len(found.macro))

    return _score_all(as_of, config, store, formula)


def rescore(
    *, config: Config, store: Store, formula: IndexFormula, start: date, end: date
) -> list[IndexScore]:
    """Recompute every day in [start, end] from stored inputs; no provider is called."""
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    scores: list[IndexScore] = []
    day = start
    while day <= end:
        as_of = datetime.combine(day, time.max, tzinfo=UTC)
        scores.extend(_score_all(as_of, config, store, formula))
        day += timedelta(days=1)
    return scores


def _score_all(
    as_of: datetime, config: Config, store: Store, formula: IndexFormula
) -> list[IndexScore]:
    scores = []
    for asset in config.assets:
        inputs = build_inputs(store, asset, as_of, config)
        score = formula.compute(inputs)
        store.scores.add(score)
        scores.append(score)
        log.info("%s %s %.1f (%s)", score.date, score.asset, score.score, score.formula)
    return scores
