"""Persistence boundary: one repository per record type, composed into a Store.

Repository pattern. Each repository owns one record type: ``add`` is an upsert and every
query method is named for the question it answers. Queries return rows sorted by time.
"""

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from manc.models import CalendarEvent, IndexScore, NewsItem, NewsTag


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
class Store(Protocol):
    news: NewsRepository
    tags: TagRepository
    events: EventRepository
    scores: ScoreRepository
