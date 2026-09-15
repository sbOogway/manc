"""Fakes must satisfy the Protocols and behave like a store."""

from datetime import UTC, date, datetime, timedelta

from manc.analysis.interface import Analyzer
from manc.calendar.interface import CalendarProvider
from manc.formulas.contract import AssetSpec, IndexScore
from manc.models import CalendarEvent, NewsItem, NewsTag
from manc.news.interface import NewsProvider
from manc.store.interface import (
    EventRepository,
    NewsRepository,
    ScoreRepository,
    Store,
    TagRepository,
)
from tests.fakes import FakeAnalyzer, FakeCalendar, FakeNews, FakeStore

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
ASSET = AssetSpec(symbol="EURUSD", kind="forex", economies=("euro_area", "united_states"))


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(FakeCalendar(), CalendarProvider)
    assert isinstance(FakeNews(), NewsProvider)
    assert isinstance(FakeAnalyzer(), Analyzer)
    store = FakeStore()
    assert isinstance(store, Store)
    assert isinstance(store.news, NewsRepository)
    assert isinstance(store.tags, TagRepository)
    assert isinstance(store.events, EventRepository)
    assert isinstance(store.scores, ScoreRepository)


def test_fake_analyzer_tags_every_item_for_every_asset_neutral() -> None:
    items = [
        NewsItem.from_feed(source="s", title="t", url=f"u{index}", published_at=NOW)
        for index in range(2)
    ]
    tags = FakeAnalyzer().tag(items, [ASSET])
    assert len(tags) == 2
    assert all(tag.direction == 0 and tag.asset == "EURUSD" for tag in tags)


def test_fake_store_round_trips() -> None:
    store = FakeStore()
    item = NewsItem.from_feed(source="s", title="t", url="u", published_at=NOW)
    tag = NewsTag(news_id=item.id, asset="EURUSD", direction=1, confidence=0.9)
    event = CalendarEvent(
        id="e",
        date=NOW + timedelta(days=2),
        country="united_states",
        event="CPI",
        category="inflation",
        importance=3,
        consensus=None,
        previous=None,
        actual=None,
    )
    score = IndexScore(
        asset="EURUSD",
        date=date(2026, 9, 15),
        score=61.0,
        formula="v1",
        components={"N": 0.2},
        n_news=1,
        n_events=1,
    )
    store.news.add(item)
    store.tags.add(tag)
    store.events.add(event)
    store.scores.add(score)

    assert store.news.since(NOW - timedelta(days=1)) == [item]
    assert store.news.tagged("EURUSD", NOW - timedelta(days=1)) == [(item, tag)]
    assert store.events.between(date(2026, 9, 15), date(2026, 9, 20)) == [event]
    assert store.scores.series("EURUSD", "v1", date(2026, 9, 1), date(2026, 9, 30)) == [score]
    assert store.scores.series("EURUSD", "v2", date(2026, 9, 1), date(2026, 9, 30)) == []


def test_fake_store_upserts() -> None:
    store = FakeStore()
    item = NewsItem.from_feed(source="s", title="t", url="u", published_at=NOW)
    store.news.add(item, item)
    assert len(store.news.rows) == 1
