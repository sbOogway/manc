"""Persistence boundary: one repository per record type, composed into a Store.

Repository pattern. Each repository owns one record type: ``add`` is an upsert and every
query method is named for the question it answers. Queries return rows sorted by time.
"""

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from manc.models import (
    CalendarEvent,
    ForecastAsset,
    ForecastMacro,
    IndexScore,
    NewsItem,
    NewsTag,
    SpotPrice,
)


@runtime_checkable
class NewsRepository(Protocol):
    """``add`` keeps the analysed mark of an item it has already seen."""

    def add(self, *items: NewsItem) -> None: ...
    def since(self, published_after: datetime) -> list[NewsItem]: ...
    def unanalyzed(self, published_after: datetime) -> list[NewsItem]: ...
    def mark_analyzed(self, *items: NewsItem) -> None: ...
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
    def latest_day(self) -> date | None: ...  # newest scored day under any formula


@runtime_checkable
class ForecastAssetRepository(Protocol):
    """Rows are vintages: ``add`` keeps the earliest sighting of an id, never overwrites."""

    def add(self, *forecasts: ForecastAsset) -> None: ...
    def latest(self, asset: str) -> list[ForecastAsset]: ...  # newest per institution + horizon
    def vintages(self, institution: str, asset: str, horizon_date: date) -> list[ForecastAsset]: ...
    def as_of(self, asset: str, day: date) -> list[ForecastAsset]: ...  # published by that day


@runtime_checkable
class ForecastMacroRepository(Protocol):
    def add(self, *forecasts: ForecastMacro) -> None: ...
    def latest(
        self, economy: str
    ) -> list[ForecastMacro]: ...  # newest per institution + metric + horizon
    def vintages(
        self, institution: str, economy: str, metric: str, horizon_date: date
    ) -> list[ForecastMacro]: ...
    def as_of(self, economy: str, day: date) -> list[ForecastMacro]: ...


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
    forecasts_asset: ForecastAssetRepository
    forecasts_macro: ForecastMacroRepository
    spot: SpotRepository
