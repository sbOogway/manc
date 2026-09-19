"""In-memory fakes for every module Protocol. Used by pipeline and CLI tests."""

from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas

from manc.formulas.contract import AssetSpec, IndexScore
from manc.models import CalendarEvent, Forecasts, NewsItem, NewsTag, SpotPrice

SPOT_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "spot"


class FakeCalendar:
    def __init__(self, events: Iterable[CalendarEvent] = ()) -> None:
        self.events = list(events)

    def fetch(self, start: date, end: date) -> list[CalendarEvent]:
        return [event for event in self.events if start <= event.date.date() <= end]


class FakeNews:
    def __init__(self, items: Iterable[NewsItem] = ()) -> None:
        self.items = list(items)

    def fetch(self, since: datetime) -> list[NewsItem]:
        return [item for item in self.items if item.published_at >= since]


class FakeAnalyzer:
    """Tags every headline as neutral for every asset, or replays canned tags."""

    def __init__(self, tags: Iterable[NewsTag] = ()) -> None:
        self.canned = list(tags)

    def tag(self, items: Sequence[NewsItem], assets: Sequence[AssetSpec]) -> list[NewsTag]:
        if self.canned:
            wanted_ids = {item.id for item in items}
            return [tag for tag in self.canned if tag.news_id in wanted_ids]
        return [
            NewsTag(news_id=item.id, asset=asset.symbol, direction=0, confidence=0.0)
            for item in items
            for asset in assets
        ]


class FakeForecasts:
    def __init__(self, forecasts: Forecasts | None = None) -> None:
        self.forecasts = forecasts or Forecasts()

    def fetch(self, since: datetime) -> Forecasts:
        return Forecasts(
            asset=tuple(
                forecast for forecast in self.forecasts.asset if forecast.published_at >= since
            ),
            macro=tuple(
                forecast for forecast in self.forecasts.macro if forecast.published_at >= since
            ),
        )


class FakeSpot:
    def __init__(self, prices: Iterable[SpotPrice] = ()) -> None:
        self.prices = list(prices)

    def fetch(self, assets: Sequence[AssetSpec], day: date) -> list[SpotPrice]:
        symbols = {asset.symbol for asset in assets}
        return [price for price in self.prices if price.asset in symbols and price.date == day]


def recorded_history(ticker: str, start: date, end: date) -> pandas.DataFrame:
    """Replay a recorded `yfinance.Ticker.history` frame; tz-aware index like the real one."""
    assert start < end
    return pandas.read_csv(SPOT_FIXTURES / f"{ticker}.csv", index_col="Date", parse_dates=["Date"])


class FakeNewsRepository:
    def __init__(self, tags: "FakeTagRepository") -> None:
        self.rows: dict[str, NewsItem] = {}
        self._tags = tags

    def add(self, *items: NewsItem) -> None:
        for item in items:
            self.rows[item.id] = item

    def since(self, published_after: datetime) -> list[NewsItem]:
        recent = [item for item in self.rows.values() if item.published_at >= published_after]
        return sorted(recent, key=lambda item: item.published_at)

    def tagged(self, asset: str, published_after: datetime) -> list[tuple[NewsItem, NewsTag]]:
        pairs: list[tuple[NewsItem, NewsTag]] = []
        for (news_id, tag_asset), tag in self._tags.rows.items():
            item = self.rows.get(news_id)
            if tag_asset == asset and item and item.published_at >= published_after:
                pairs.append((item, tag))
        return sorted(pairs, key=lambda pair: pair[0].published_at)


class FakeTagRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], NewsTag] = {}

    def add(self, *tags: NewsTag) -> None:
        for tag in tags:
            self.rows[(tag.news_id, tag.asset)] = tag


class FakeEventRepository:
    def __init__(self) -> None:
        self.rows: dict[str, CalendarEvent] = {}

    def add(self, *events: CalendarEvent) -> None:
        for event in events:
            self.rows[event.id] = event

    def between(self, start: date, end: date) -> list[CalendarEvent]:
        in_window = [event for event in self.rows.values() if start <= event.date.date() <= end]
        return sorted(in_window, key=lambda event: event.date)


class FakeScoreRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, date, str], IndexScore] = {}

    def add(self, *scores: IndexScore) -> None:
        for score in scores:
            self.rows[(score.asset, score.date, score.formula)] = score

    def series(self, asset: str, formula: str, start: date, end: date) -> list[IndexScore]:
        matching = [
            score
            for (score_asset, score_date, score_formula), score in self.rows.items()
            if score_asset == asset and score_formula == formula and start <= score_date <= end
        ]
        return sorted(matching, key=lambda score: score.date)

    def latest_day(self) -> date | None:
        return max((score.date for score in self.rows.values()), default=None)


class FakeForecastRepository:
    """Vintages by id; a re-report of an id keeps whichever sighting is earlier."""

    def __init__(self, subject_field: str, vintage_fields: tuple[str, ...]) -> None:
        self.rows: dict[str, Any] = {}
        self._subject_field = subject_field
        self._vintage_fields = vintage_fields

    def add(self, *forecasts: Any) -> None:
        for forecast in forecasts:
            existing = self.rows.get(forecast.id)
            if existing is None or forecast.published_at < existing.published_at:
                self.rows[forecast.id] = forecast

    def latest(self, subject: str) -> list[Any]:
        newest: dict[tuple[Any, ...], Any] = {}
        for forecast in self._sorted(lambda row: getattr(row, self._subject_field) == subject):
            newest[tuple(getattr(forecast, name) for name in self._vintage_fields)] = forecast
        return list(newest.values())

    def vintages(self, institution: str, *subject_and_horizon: Any) -> list[Any]:
        wanted = (institution, *subject_and_horizon)
        return self._sorted(
            lambda row: tuple(getattr(row, name) for name in self._vintage_fields) == wanted
        )

    def as_of(self, subject: str, day: date) -> list[Any]:
        return self._sorted(
            lambda row: (
                getattr(row, self._subject_field) == subject and row.published_at.date() <= day
            )
        )

    def _sorted(self, keep: Callable[[Any], bool]) -> list[Any]:
        matching = [row for row in self.rows.values() if keep(row)]
        return sorted(matching, key=lambda row: (row.published_at, row.id))


class FakeSpotRepository:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, date], SpotPrice] = {}

    def add(self, *prices: SpotPrice) -> None:
        for price in prices:
            self.rows[(price.asset, price.date)] = price

    def latest(self, asset: str) -> SpotPrice | None:
        series = self.between(asset, date.min, date.max)
        return series[-1] if series else None

    def between(self, asset: str, start: date, end: date) -> list[SpotPrice]:
        matching = [
            price
            for (price_asset, price_date), price in self.rows.items()
            if price_asset == asset and start <= price_date <= end
        ]
        return sorted(matching, key=lambda price: price.date)


class FakeStore:
    """Composes one fake repository per record type."""

    def __init__(self) -> None:
        self.tags = FakeTagRepository()
        self.news = FakeNewsRepository(self.tags)
        self.events = FakeEventRepository()
        self.scores = FakeScoreRepository()
        self.forecasts_asset: FakeForecastRepository = FakeForecastRepository(
            "asset", ("institution", "asset", "horizon_date")
        )
        self.forecasts_macro: FakeForecastRepository = FakeForecastRepository(
            "economy", ("institution", "economy", "metric", "horizon_date")
        )
        self.spot = FakeSpotRepository()
