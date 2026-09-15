"""In-memory fakes for every module Protocol. Used by pipeline and CLI tests."""

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from functools import singledispatchmethod

from manc.formulas.contract import AssetSpec, IndexScore
from manc.models import CalendarEvent, NewsItem, NewsTag


class FakeCalendar:
    def __init__(self, events: Iterable[CalendarEvent] = ()) -> None:
        self.events = list(events)

    def fetch(self, start: date, end: date) -> list[CalendarEvent]:
        return [e for e in self.events if start <= e.date.date() <= end]


class FakeNews:
    def __init__(self, items: Iterable[NewsItem] = ()) -> None:
        self.items = list(items)

    def fetch(self, since: datetime) -> list[NewsItem]:
        return [i for i in self.items if i.published_at >= since]


class FakeAnalyzer:
    """Tags every headline as neutral for every asset, or replays canned tags."""

    def __init__(self, tags: Iterable[NewsTag] = ()) -> None:
        self.canned = list(tags)

    def tag(self, items: Sequence[NewsItem], assets: Sequence[AssetSpec]) -> list[NewsTag]:
        if self.canned:
            wanted = {i.id for i in items}
            return [t for t in self.canned if t.news_id in wanted]
        return [
            NewsTag(news_id=i.id, asset=a.symbol, direction=0, confidence=0.0)
            for i in items
            for a in assets
        ]


class FakeStore:
    def __init__(self) -> None:
        self.news: dict[str, NewsItem] = {}
        self.tags: dict[tuple[str, str], NewsTag] = {}
        self.events: dict[str, CalendarEvent] = {}
        self.scores: dict[tuple[str, str, str], IndexScore] = {}

    def save(self, *objects: CalendarEvent | NewsItem | NewsTag | IndexScore) -> None:
        for obj in objects:
            self._put(obj)

    @singledispatchmethod
    def _put(self, obj: object) -> None:
        raise TypeError(f"cannot store {type(obj).__name__}")

    @_put.register
    def _(self, obj: NewsItem) -> None:
        self.news[obj.id] = obj

    @_put.register
    def _(self, obj: NewsTag) -> None:
        self.tags[(obj.news_id, obj.asset)] = obj

    @_put.register
    def _(self, obj: CalendarEvent) -> None:
        self.events[obj.id] = obj

    @_put.register
    def _(self, obj: IndexScore) -> None:
        self.scores[(obj.asset, obj.date.isoformat(), obj.formula)] = obj

    def load_news(self, since: datetime) -> list[NewsItem]:
        return sorted(
            (i for i in self.news.values() if i.published_at >= since), key=lambda i: i.published_at
        )

    def load_tagged_news(self, asset: str, since: datetime) -> list[tuple[NewsItem, NewsTag]]:
        out = []
        for (news_id, tag_asset), tag in self.tags.items():
            item = self.news.get(news_id)
            if tag_asset == asset and item and item.published_at >= since:
                out.append((item, tag))
        return sorted(out, key=lambda p: p[0].published_at)

    def load_events(self, start: date, end: date) -> list[CalendarEvent]:
        return sorted(
            (e for e in self.events.values() if start <= e.date.date() <= end), key=lambda e: e.date
        )

    def load_scores(self, asset: str, formula: str, start: date, end: date) -> list[IndexScore]:
        return sorted(
            (
                s
                for (a, d, f), s in self.scores.items()
                if a == asset and f == formula and start <= date.fromisoformat(d) <= end
            ),
            key=lambda s: s.date,
        )
