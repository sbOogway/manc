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
    def _(self, item: NewsItem) -> None:
        self.news[item.id] = item

    @_put.register
    def _(self, tag: NewsTag) -> None:
        self.tags[(tag.news_id, tag.asset)] = tag

    @_put.register
    def _(self, event: CalendarEvent) -> None:
        self.events[event.id] = event

    @_put.register
    def _(self, score: IndexScore) -> None:
        self.scores[(score.asset, score.date.isoformat(), score.formula)] = score

    def load_news(self, since: datetime) -> list[NewsItem]:
        recent = [item for item in self.news.values() if item.published_at >= since]
        return sorted(recent, key=lambda item: item.published_at)

    def load_tagged_news(self, asset: str, since: datetime) -> list[tuple[NewsItem, NewsTag]]:
        pairs: list[tuple[NewsItem, NewsTag]] = []
        for (news_id, tag_asset), tag in self.tags.items():
            item = self.news.get(news_id)
            if tag_asset == asset and item and item.published_at >= since:
                pairs.append((item, tag))
        return sorted(pairs, key=lambda pair: pair[0].published_at)

    def load_events(self, start: date, end: date) -> list[CalendarEvent]:
        in_window = [event for event in self.events.values() if start <= event.date.date() <= end]
        return sorted(in_window, key=lambda event: event.date)

    def load_scores(self, asset: str, formula: str, start: date, end: date) -> list[IndexScore]:
        matching = [
            score
            for (score_asset, score_date, score_formula), score in self.scores.items()
            if score_asset == asset
            and score_formula == formula
            and start <= date.fromisoformat(score_date) <= end
        ]
        return sorted(matching, key=lambda score: score.date)
