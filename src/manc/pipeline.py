"""The pipeline (blueprint section 2) in two steps.

`fetch` pulls the calendar, the news and the spot closes into the store: no model call, it
runs every few minutes. `run` fetches too, then tags every headline in the news window that
no earlier run analysed, extracts forecasts, scores and writes the reports: once a day.
Every input the formula sees is persisted first, so `rescore` can replay any date range
under any formula without touching a provider. `summarize` is the LLM call site the report
builder uses for its opening paragraph, or None for template-only reports.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta

from manc.analysis.interface import Analyzer
from manc.calendar.interface import CalendarProvider
from manc.chain.interface import ChainProvider
from manc.config import Config
from manc.forecasts.interface import ForecastProvider
from manc.formulas.contract import AssetSpec, IndexFormula, IndexScore
from manc.models import (
    CalendarEvent,
    ChainMetric,
    ForecastAsset,
    ForecastMacro,
    Forecasts,
    NewsItem,
    SpotPrice,
)
from manc.news.interface import NewsProvider
from manc.report.builder import Complete, build_report
from manc.scoring.adapter import build_inputs
from manc.spot.interface import SpotProvider
from manc.store.interface import Store

log = logging.getLogger(__name__)
CHAIN_LOOKBACK_DAYS = 7  # a daily run re-reads the last week: late rows and revisions


@dataclass(frozen=True)
class Fetched:
    """What one fetch pulled from the providers (all of it is in the store by then)."""

    events: list[CalendarEvent]
    items: list[NewsItem]
    closes: list[SpotPrice]


def fetch(
    *,
    as_of: datetime,
    config: Config,
    calendar: CalendarProvider,
    news: NewsProvider,
    spot: SpotProvider,
    store: Store,
) -> Fetched:
    """The fast step: calendar, news and spot closes into the store, nothing analysed."""
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

    closes = spot.fetch(config.active_assets, as_of.date())
    store.spot.add(*closes)
    log.info("spot: %d closes for %s", len(closes), as_of.date())

    return Fetched(events=events, items=items, closes=closes)


def run(
    *,
    as_of: datetime,
    config: Config,
    calendar: CalendarProvider,
    news: NewsProvider,
    analyzer: Analyzer,
    forecasts: Sequence[ForecastProvider],
    spot: SpotProvider,
    chain: Sequence[ChainProvider],
    store: Store,
    formula: IndexFormula,
    summarize: Complete | None,
) -> list[IndexScore]:
    """The daily step: fetch, then tag what the fetches left unanalysed, forecasts, scores."""
    fetch(as_of=as_of, config=config, calendar=calendar, news=news, spot=spot, store=store)
    day = as_of.date()
    fetch_chain(chain, config.active_assets, day - timedelta(days=CHAIN_LOOKBACK_DAYS), day, store)
    news_since = as_of - timedelta(hours=config.scoring.windows["news_hours"])

    pending = store.news.unanalyzed(news_since)
    tags = analyzer.tag(pending, config.assets)
    store.tags.add(*tags)
    store.news.mark_analyzed(*pending)
    log.info("analysis: %d headlines, %d tags", len(pending), len(tags))

    found = fetch_forecasts(forecasts, news_since, store)
    log.info("forecasts: %d asset, %d macro", len(found.asset), len(found.macro))

    return _score_all(as_of, config, store, formula, summarize)


def fetch_chain(
    providers: Sequence[ChainProvider],
    assets: Sequence[AssetSpec],
    start: date,
    end: date,
    store: Store,
) -> list[ChainMetric]:
    """Every on-chain source over [start, end] for the coins among `assets`; stored, returned."""
    coins = [asset for asset in assets if asset.chain]
    stored: list[ChainMetric] = []
    for provider in providers:
        metrics = provider.fetch(coins, start, end)
        store.chain.add(*metrics)
        stored.extend(metrics)
    log.info(
        "chain: %d readings for %d coins between %s and %s", len(stored), len(coins), start, end
    )
    return stored


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
    for asset in config.active_assets:
        inputs = build_inputs(store, asset, as_of, config, formula.windows)
        scored = formula.compute(inputs)
        score = replace(scored, report_md=build_report(store, config, scored, complete=summarize))
        store.scores.add(score)
        scores.append(score)
        log.info("%s %s %.1f (%s)", score.date, score.asset, score.score, score.formula)
    return scores
