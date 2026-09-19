"""The daily run (blueprint section 2): fetch, tag, extract forecasts, spot, score, report, store.

Every input the formula sees is persisted first, so `rescore` can replay any date range
under any formula without touching a provider. `summarize` is the LLM call site the report
builder uses for its opening paragraph, or None for template-only reports.
"""

import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

from manc.analysis.interface import Analyzer
from manc.calendar.interface import CalendarProvider
from manc.config import Config
from manc.forecasts.interface import ForecastProvider
from manc.formulas.contract import IndexFormula, IndexScore
from manc.models import ForecastAsset, ForecastMacro, Forecasts
from manc.news.interface import NewsProvider
from manc.report.builder import Complete, build_report
from manc.scoring.adapter import build_inputs
from manc.spot.interface import SpotProvider
from manc.store.interface import Store

log = logging.getLogger(__name__)


def run(
    *,
    as_of: datetime,
    config: Config,
    calendar: CalendarProvider,
    news: NewsProvider,
    analyzer: Analyzer,
    forecasts: Sequence[ForecastProvider],
    spot: SpotProvider,
    store: Store,
    formula: IndexFormula,
    summarize: Complete | None,
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

    found = fetch_forecasts(forecasts, news_since, store)
    log.info("forecasts: %d asset, %d macro", len(found.asset), len(found.macro))

    closes = spot.fetch(config.assets, as_of.date())
    store.spot.add(*closes)
    log.info("spot: %d closes for %s", len(closes), as_of.date())

    return _score_all(as_of, config, store, formula, summarize)


def fetch_forecasts(
    providers: Sequence[ForecastProvider], since: datetime, store: Store
) -> Forecasts:
    """Run every provider (extractor and publishers), store and return all they found."""
    asset: list[ForecastAsset] = []
    macro: list[ForecastMacro] = []
    for provider in providers:
        found = provider.fetch(since)
        store.forecasts_asset.add(*found.asset)
        store.forecasts_macro.add(*found.macro)
        asset.extend(found.asset)
        macro.extend(found.macro)
    return Forecasts(asset=tuple(asset), macro=tuple(macro))


def rescore(
    *,
    config: Config,
    store: Store,
    formula: IndexFormula,
    start: date,
    end: date,
    summarize: Complete | None,
) -> list[IndexScore]:
    """Recompute every day in [start, end] from stored inputs; no provider is called."""
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    scores: list[IndexScore] = []
    day = start
    while day <= end:
        as_of = datetime.combine(day, time.max, tzinfo=UTC)
        scores.extend(_score_all(as_of, config, store, formula, summarize))
        day += timedelta(days=1)
    return scores


def _score_all(
    as_of: datetime,
    config: Config,
    store: Store,
    formula: IndexFormula,
    summarize: Complete | None,
) -> list[IndexScore]:
    scores = []
    for asset in config.assets:
        inputs = build_inputs(store, asset, as_of, config)
        scored = formula.compute(inputs)
        score = replace(scored, report_md=build_report(store, config, scored, complete=summarize))
        store.scores.add(score)
        scores.append(score)
        log.info("%s %s %.1f (%s)", score.date, score.asset, score.score, score.formula)
    return scores
