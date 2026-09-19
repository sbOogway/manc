"""One thin handler per section 7 row: parse, call one query, answer."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from manc import queries
from manc.api.deps import get_config, get_store
from manc.api.schemas import AssetOut, FormulasOut, HealthOut, ReportOut
from manc.config import Config
from manc.formulas.registry import formula_names
from manc.models import CalendarEvent, ForecastMacro, SpotPrice
from manc.store.interface import Store

SERIES_DAYS = 90
EVENTS_AHEAD_DAYS = 30

router = APIRouter()
ConfigDep = Annotated[Config, Depends(get_config)]
StoreDep = Annotated[Store, Depends(get_store)]
Importance = Annotated[int, Query(ge=1, le=3)]
Confidence = Annotated[float | None, Query(ge=0.0, le=1.0)]


def _today() -> date:
    return datetime.now(UTC).date()


def _range(start: date | None, end: date | None) -> tuple[date, date]:
    end = end or _today()
    return start or end - timedelta(days=SERIES_DAYS), end


def _unknown_asset(symbol: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"unknown asset {symbol}")


@router.get("/api/v1/assets", response_model=list[AssetOut])
def assets(config: ConfigDep) -> list[AssetOut]:
    return [
        AssetOut(symbol=asset.symbol, kind=asset.kind, economies=list(asset.economies))
        for asset in config.active_assets
    ]


@router.get("/api/v1/overview", response_model=list[queries.AssetSummary])
def overview(config: ConfigDep, store: StoreDep, as_of: date | None = None) -> list:
    return queries.overview(store, config, as_of or _today())


@router.get("/api/v1/assets/{symbol}/scores", response_model=queries.AssetHistory)
def scores(
    symbol: str,
    config: ConfigDep,
    store: StoreDep,
    formula: str | None = None,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> queries.AssetHistory:
    start, end = _range(start, end)
    try:
        return queries.asset_history(
            store, config, symbol, formula or config.scoring.formula, start, end
        )
    except KeyError:
        raise _unknown_asset(symbol) from None


@router.get("/api/v1/assets/{symbol}/report", response_model=ReportOut)
def report(
    symbol: str,
    config: ConfigDep,
    store: StoreDep,
    day: Annotated[date | None, Query(alias="date")] = None,
    formula: str | None = None,
) -> ReportOut:
    day = day or _today()
    formula = formula or config.scoring.formula
    if symbol not in {asset.symbol for asset in config.assets}:
        raise _unknown_asset(symbol)
    series = store.scores.series(symbol, formula, day, day)
    if not series:
        raise HTTPException(status_code=404, detail=f"no {formula} score for {symbol} on {day}")
    return ReportOut(symbol=symbol, date=day, formula=formula, report_md=series[0].report_md)


@router.get("/api/v1/assets/{symbol}/headlines", response_model=list[queries.HeadlineView])
def headlines(
    symbol: str,
    config: ConfigDep,
    store: StoreDep,
    day: Annotated[date | None, Query(alias="date")] = None,
) -> list:
    try:
        return queries.headlines_behind(store, config, symbol, day or _today())
    except KeyError:
        raise _unknown_asset(symbol) from None


@router.get("/api/v1/events", response_model=list[CalendarEvent])
def events(
    config: ConfigDep,
    store: StoreDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
    min_importance: Importance = 1,
) -> list:
    start = start or _today()
    end = end or start + timedelta(days=EVENTS_AHEAD_DAYS)
    return queries.upcoming_events(store, config, start, end, min_importance)


@router.get("/api/v1/assets/{symbol}/forecasts", response_model=queries.ForecastPanel)
def forecasts(
    symbol: str,
    config: ConfigDep,
    store: StoreDep,
    as_of: date | None = None,
    min_confidence: Confidence = None,
) -> queries.ForecastPanel:
    if min_confidence is None:
        min_confidence = config.forecasts.min_confidence
    try:
        return queries.forecasts_for(store, config, symbol, as_of or _today(), min_confidence)
    except KeyError:
        raise _unknown_asset(symbol) from None


@router.get("/api/v1/assets/{symbol}/spot", response_model=list[SpotPrice])
def spot(
    symbol: str,
    config: ConfigDep,
    store: StoreDep,
    start: Annotated[date | None, Query(alias="from")] = None,
    end: Annotated[date | None, Query(alias="to")] = None,
) -> list:
    if symbol not in {asset.symbol for asset in config.assets}:
        raise _unknown_asset(symbol)
    start, end = _range(start, end)
    return store.spot.between(symbol, start, end)


@router.get("/api/v1/macro/forecasts", response_model=list[ForecastMacro])
def macro_forecasts(store: StoreDep, economy: str, metric: str | None = None) -> list:
    latest = store.forecasts_macro.latest(economy)
    return [forecast for forecast in latest if metric is None or forecast.metric == metric]


@router.get("/api/v1/formulas", response_model=FormulasOut)
def formulas(config: ConfigDep) -> FormulasOut:
    return FormulasOut(default=config.scoring.formula, known=formula_names())


@router.get("/health", response_model=HealthOut)
def health(store: StoreDep) -> HealthOut:
    return HealthOut(status="ok", last_run=store.scores.latest_day())
