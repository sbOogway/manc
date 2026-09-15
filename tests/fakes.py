"""In-memory fakes for every module Protocol. Used by pipeline and CLI tests."""

from collections.abc import Iterable, Sequence
from datetime import date, datetime

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


class FakeStore:
    """Composes one fake repository per record type."""

    def __init__(self) -> None:
        self.tags = FakeTagRepository()
        self.news = FakeNewsRepository(self.tags)
        self.events = FakeEventRepository()
        self.scores = FakeScoreRepository()
