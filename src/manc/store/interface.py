"""Persistence boundary: one repository per record type, composed into a Store.

Repository pattern. Each repository owns one record type: ``add`` is an upsert and every
query method is named for the question it answers. Queries return rows sorted by time.
"""

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from manc.models import (
    AssetForecast,
    CalendarEvent,
    IndexScore,
    MacroForecast,
    NewsItem,
    NewsTag,
    SpotPrice,
)


@runtime_checkable
class NewsRepository(Protocol):
    def add(self, *items: NewsItem) -> None: ...
    def since(self, published_after: datetime) -> list[NewsItem]: ...
    def tagged(self, asset: str, published_after: datetime) -> list[tuple[NewsItem, NewsTag]]: ...


@runtime_checkable
class TagRepository(Protocol):
    def add(self, *tags: NewsTag) -> None: ...


@runtime_checkable
class EventRepository(Protocol):
    def add(self, *events: CalendarEvent) -> None: ...
    def between(self, start: date, end: date) -> list[CalendarEvent]: ...


@runtime_checkable
class ScoreRepository(Protocol):
    def add(self, *scores: IndexScore) -> None: ...
    def series(self, asset: str, formula: str, start: date, end: date) -> list[IndexScore]: ...


@runtime_checkable
class AssetForecastRepository(Protocol):
    """Rows are vintages: ``add`` keeps the earliest sighting of an id, never overwrites."""

    def add(self, *forecasts: AssetForecast) -> None: ...
    def latest(self, asset: str) -> list[AssetForecast]: ...  # newest per institution + horizon
    def vintages(self, institution: str, asset: str, horizon_date: date) -> list[AssetForecast]: ...
    def as_of(self, asset: str, day: date) -> list[AssetForecast]: ...  # published by that day


@runtime_checkable
class MacroForecastRepository(Protocol):
    def add(self, *forecasts: MacroForecast) -> None: ...
    def latest(
        self, economy: str
    ) -> list[MacroForecast]: ...  # newest per institution + metric + horizon
    def vintages(
        self, institution: str, economy: str, metric: str, horizon_date: date
    ) -> list[MacroForecast]: ...
    def as_of(self, economy: str, day: date) -> list[MacroForecast]: ...


@runtime_checkable
class SpotRepository(Protocol):
    def add(self, *prices: SpotPrice) -> None: ...
    def latest(self, asset: str) -> SpotPrice | None: ...
    def between(self, asset: str, start: date, end: date) -> list[SpotPrice]: ...


@runtime_checkable
class Store(Protocol):
    news: NewsRepository
    tags: TagRepository
    events: EventRepository
    scores: ScoreRepository
    forecasts_asset: AssetForecastRepository
    forecasts_macro: MacroForecastRepository
    spot: SpotRepository
