from datetime import date, datetime
from typing import Protocol, runtime_checkable

from manc.models import CalendarEvent, IndexScore, NewsItem, NewsTag

Persistable = CalendarEvent | NewsItem | NewsTag | IndexScore


@runtime_checkable
class Store(Protocol):
    """Persistence boundary.

    One ``save`` for every record type, dispatched on the object's type (implementations use
    ``functools.singledispatchmethod``); every save is an upsert. Loads keep distinct names
    because they differ by arguments and return type, which type dispatch cannot select on.
    Every load returns rows sorted by time.
    """

    def save(self, *objects: Persistable) -> None: ...

    def load_news(self, since: datetime) -> list[NewsItem]: ...
    def load_tagged_news(self, asset: str, since: datetime) -> list[tuple[NewsItem, NewsTag]]: ...
    def load_events(self, start: date, end: date) -> list[CalendarEvent]: ...
    def load_scores(self, asset: str, formula: str, start: date, end: date) -> list[IndexScore]: ...
