"""Read-side logic over a Store (blueprint section 7).

Everything between rows in the store and JSON on the wire: the band a score falls in, the
delta versus the previous day, the sparkline window, the event-risk badge, the ordering of
the overview, the forecast panel. The API routes, the report builder and the CLI all call
these functions, so each of those numbers is computed in exactly one place. Plain
functions over a `Store`, frozen dataclasses out, no HTTP.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Any

from manc.config import Config
from manc.formulas.contract import BANDS, AssetSpec, IndexScore, Scale
from manc.formulas.registry import get_formula
from manc.models import CalendarEvent, ChainMetric, ForecastAsset, ForecastMacro

__all__ = ["BANDS"]
SPARKLINE_DAYS = 30
UNKNOWN_SOURCE_WEIGHT = 1.0
UNKNOWN_INSTITUTION_WEIGHT = 0.0
EVENT_RISK_COMPONENT = "R"
# on-chain and sentiment series in display order: metric -> (label, group); the net flow is
# derived from the two flow readings
CHAIN_METRICS: dict[str, tuple[str, str]] = {
    "active_addresses": ("Active addresses", "chain"),
    "exchange_netflow_usd": ("Exchange net flow (USD)", "chain"),
    "fees_usd": ("Fees paid (USD)", "chain"),
    "mvrv": ("MVRV", "chain"),
    "stablecoins_usd": ("Stablecoins on chain (USD)", "chain"),
    "tvl_usd": ("TVL (USD)", "chain"),
    "tx_per_second": ("Transactions per second", "chain"),
    "fear_greed": ("Fear & Greed (market)", "sentiment"),
    "sentiment_votes_up_pct": ("CoinGecko votes up (%)", "sentiment"),
    "watchlist_users": ("CoinGecko watchlists", "sentiment"),
}


@dataclass(frozen=True)
class AssetSummary:
    """One overview card."""

    symbol: str
    kind: str
    formula: str
    date: date  # the day the score refers to
    score: float
    band: str
    delta: float | None  # versus the previous stored day, None on the first
    sparkline: tuple[float, ...]  # last 30 days, oldest first
    event_risk: float  # the formula's R component, 0..1


@dataclass(frozen=True)
class ScorePoint:
    date: date
    score: float
    band: str
    components: dict[str, float]
    n_news: int
    n_events: int


@dataclass(frozen=True)
class AssetHistory:
    symbol: str
    formula: str
    scale: Scale  # where the scores live, so a chart can draw the bands and the neutral line
    points: tuple[ScorePoint, ...]


@dataclass(frozen=True)
class HeadlineView:
    """A tagged headline and how much it weighed on the score."""

    title: str
    url: str
    source: str
    published_at: datetime
    direction: int
    confidence: float
    source_weight: float
    weight: float  # confidence times source weight


@dataclass(frozen=True)
class ForecastRow:
    institution: str
    horizon_date: date
    horizon_label: str
    value: float
    previous_value: float | None  # the vintage before this one, for the revision arrow
    vs_spot: float | None  # value / spot - 1
    published_at: datetime
    confidence: float


@dataclass(frozen=True)
class MedianRow:
    horizon_date: date
    value: float


@dataclass(frozen=True)
class MacroForecastRow:
    institution: str
    economy: str
    metric: str
    horizon_date: date
    horizon_label: str
    value: float
    previous_value: float | None
    published_at: datetime
    confidence: float


@dataclass(frozen=True)
class ChainPoint:
    date: date
    value: float


@dataclass(frozen=True)
class ChainSeries:
    metric: str
    label: str
    group: str  # "chain" | "sentiment": which card of the asset page shows it
    source: str
    points: tuple[ChainPoint, ...]  # oldest first


@dataclass(frozen=True)
class ForecastPanel:
    symbol: str
    as_of: date
    spot: float | None
    rows: tuple[ForecastRow, ...]
    medians: tuple[MedianRow, ...]
    macro: tuple[MacroForecastRow, ...]


def scale_of(formula: str) -> Scale:
    return get_formula(formula).scale


def band(score: float, scale: Scale) -> str:
    """headwind, lean against, neutral, lean for, tailwind on the formula's scale."""
    return scale.band(score)


def overview(store: Any, config: Config, as_of: date) -> list[AssetSummary]:
    """One summary per active asset scored in the sparkline window, farthest from neutral first."""
    formula = config.scoring.formula
    scale = scale_of(formula)
    start = as_of - timedelta(days=SPARKLINE_DAYS - 1)
    summaries = []
    for asset in config.active_assets:
        series = store.scores.series(asset.symbol, formula, start, as_of)
        if not series:
            continue
        latest = series[-1]
        previous = series[-2] if len(series) > 1 else None
        summaries.append(
            AssetSummary(
                symbol=asset.symbol,
                kind=asset.kind,
                formula=formula,
                date=latest.date,
                score=latest.score,
                band=band(latest.score, scale),
                delta=None if previous is None else latest.score - previous.score,
                sparkline=tuple(score.score for score in series),
                event_risk=latest.components.get(EVENT_RISK_COMPONENT, 0.0),
            )
        )
    return sorted(summaries, key=lambda summary: -abs(summary.score - scale.neutral))


def asset_history(
    store: Any, config: Config, symbol: str, formula: str, start: date, end: date
) -> AssetHistory:
    asset = _asset(config, symbol)
    scale = scale_of(formula)
    points = tuple(
        _point(score, scale) for score in store.scores.series(asset.symbol, formula, start, end)
    )
    return AssetHistory(symbol=asset.symbol, formula=formula, scale=scale, points=points)


def headlines_behind(store: Any, config: Config, symbol: str, as_of: date) -> list[HeadlineView]:
    """The directional headlines inside the news window ending on `as_of`, strongest first."""
    asset = _asset(config, symbol)
    end = _end_of_day(as_of)
    since = end - timedelta(hours=config.scoring.windows["news_hours"])
    feed_weights = {feed.name: feed.weight for feed in config.feeds}
    views = []
    for item, tag in store.news.tagged(asset.symbol, since):
        if tag.direction == 0 or item.published_at > end:
            continue
        source_weight = feed_weights.get(item.source, UNKNOWN_SOURCE_WEIGHT)
        views.append(
            HeadlineView(
                title=item.title,
                url=item.url,
                source=item.source,
                published_at=item.published_at,
                direction=tag.direction,
                confidence=tag.confidence,
                source_weight=source_weight,
                weight=tag.confidence * source_weight,
            )
        )
    return sorted(views, key=lambda view: (-view.weight, view.published_at))


def upcoming_events(
    store: Any, config: Config, start: date, end: date, min_importance: int
) -> list[CalendarEvent]:
    """Calendar events for the economies of any active asset, at or above the floor."""
    economies = {economy for asset in config.active_assets for economy in asset.economies}
    return [
        event
        for event in store.events.between(start, end)
        if event.country in economies and event.importance >= min_importance
    ]


def forecasts_for(
    store: Any, config: Config, symbol: str, as_of: date, min_confidence: float
) -> ForecastPanel:
    """What the institutions expected for the asset as known on `as_of`."""
    asset = _asset(config, symbol)
    closes = store.spot.between(asset.symbol, date.min, as_of)
    spot = closes[-1].close if closes else None
    weights = {
        institution.name: institution.weight for institution in config.forecasts.institutions
    }

    def rank(institution: str) -> float:
        return -weights.get(institution, UNKNOWN_INSTITUTION_WEIGHT)

    known = [
        forecast
        for forecast in store.forecasts_asset.as_of(asset.symbol, as_of)
        if forecast.confidence >= min_confidence
    ]
    rows = [
        ForecastRow(
            institution=latest.institution,
            horizon_date=latest.horizon_date,
            horizon_label=latest.horizon_label,
            value=latest.value,
            previous_value=None if previous is None else previous.value,
            vs_spot=None if spot is None else latest.value / spot - 1.0,
            published_at=latest.published_at,
            confidence=latest.confidence,
        )
        for latest, previous in _latest_vintages(known, _asset_call)
    ]
    rows.sort(key=lambda row: (rank(row.institution), row.institution, row.horizon_date))

    by_horizon: dict[date, list[float]] = defaultdict(list)
    for row in rows:
        by_horizon[row.horizon_date].append(row.value)
    medians = [
        MedianRow(horizon_date=horizon, value=median(values))
        for horizon, values in sorted(by_horizon.items())
    ]

    macro_known = [
        forecast
        for economy in asset.economies
        for forecast in store.forecasts_macro.as_of(economy, as_of)
        if forecast.confidence >= min_confidence
    ]
    macro = [
        MacroForecastRow(
            institution=latest.institution,
            economy=latest.economy,
            metric=latest.metric,
            horizon_date=latest.horizon_date,
            horizon_label=latest.horizon_label,
            value=latest.value,
            previous_value=None if previous is None else previous.value,
            published_at=latest.published_at,
            confidence=latest.confidence,
        )
        for latest, previous in _latest_vintages(macro_known, _macro_call)
    ]
    macro.sort(
        key=lambda row: (
            rank(row.institution),
            row.institution,
            asset.economies.index(row.economy),
            row.metric,
            row.horizon_date,
        )
    )
    return ForecastPanel(
        symbol=asset.symbol,
        as_of=as_of,
        spot=spot,
        rows=tuple(rows),
        medians=tuple(medians),
        macro=tuple(macro),
    )


def chain_series(
    store: Any, config: Config, symbol: str, start: date, end: date
) -> list[ChainSeries]:
    """The stored on-chain readings of a coin in [start, end], one series per metric."""
    asset = _asset(config, symbol)
    if not asset.chain:
        return []
    stored = {
        metric: store.chain.series(asset.symbol, metric, start, end)
        for metric in (*CHAIN_METRICS, "exchange_inflow_usd", "exchange_outflow_usd")
    }
    stored["exchange_netflow_usd"] = _net_flow(
        stored["exchange_inflow_usd"], stored["exchange_outflow_usd"]
    )
    series = []
    for metric, (label, group) in CHAIN_METRICS.items():
        rows = stored[metric]
        if not rows:
            continue
        series.append(
            ChainSeries(
                metric=metric,
                label=label,
                group=group,
                source=rows[-1].source,
                points=tuple(ChainPoint(date=row.date, value=row.value) for row in rows),
            )
        )
    return series


def _net_flow(inflows: list[ChainMetric], outflows: list[ChainMetric]) -> list[ChainMetric]:
    """Inflow minus outflow on the days that have both: positive means supply for sale."""
    outflow_by_day = {row.date: row for row in outflows}
    net = []
    for inflow in inflows:
        outflow = outflow_by_day.get(inflow.date)
        if outflow is None:
            continue
        net.append(
            ChainMetric(
                asset=inflow.asset,
                date=inflow.date,
                metric="exchange_netflow_usd",
                value=inflow.value - outflow.value,
                source=inflow.source,
            )
        )
    return net


def _asset(config: Config, symbol: str) -> AssetSpec:
    for asset in config.assets:
        if asset.symbol == symbol:
            return asset
    raise KeyError(symbol)


def _point(score: IndexScore, scale: Scale) -> ScorePoint:
    return ScorePoint(
        date=score.date,
        score=score.score,
        band=band(score.score, scale),
        components=dict(score.components),
        n_news=score.n_news,
        n_events=score.n_events,
    )


def _end_of_day(day: date) -> datetime:
    return datetime.combine(day, datetime.max.time(), tzinfo=UTC)


def _asset_call(forecast: ForecastAsset) -> tuple[Any, ...]:
    return (forecast.institution, forecast.horizon_date)


def _macro_call(forecast: ForecastMacro) -> tuple[Any, ...]:
    return (forecast.institution, forecast.economy, forecast.metric, forecast.horizon_date)


def _latest_vintages(forecasts: list[Any], call: Any) -> list[tuple[Any, Any | None]]:
    """(newest, the one before it) per distinct call; `forecasts` arrive oldest first."""
    vintages: dict[tuple[Any, ...], list[Any]] = defaultdict(list)
    for forecast in sorted(forecasts, key=lambda row: (row.published_at, row.id)):
        vintages[call(forecast)].append(forecast)
    return [
        (history[-1], history[-2] if len(history) > 1 else None) for history in vintages.values()
    ]
