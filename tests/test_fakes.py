"""Fakes must satisfy the Protocols and behave like a store."""

from datetime import UTC, date, datetime, timedelta

import pytest

from manc.analysis.interface import Analyzer
from manc.calendar.interface import CalendarProvider
from manc.formulas.contract import AssetSpec, IndexScore
from manc.models import CalendarEvent, NewsItem, NewsTag
from manc.news.interface import NewsProvider
from manc.store.interface import Store
from tests.fakes import FakeAnalyzer, FakeCalendar, FakeNews, FakeStore

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
ASSET = AssetSpec(symbol="EURUSD", kind="forex", economies=("euro_area", "united_states"))


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(FakeCalendar(), CalendarProvider)
    assert isinstance(FakeNews(), NewsProvider)
    assert isinstance(FakeAnalyzer(), Analyzer)
    assert isinstance(FakeStore(), Store)


def test_fake_analyzer_tags_every_item_for_every_asset_neutral() -> None:
    items = [
        NewsItem.from_feed(source="s", title="t", url=f"u{i}", published_at=NOW) for i in range(2)
    ]
    tags = FakeAnalyzer().tag(items, [ASSET])
    assert len(tags) == 2
    assert all(t.direction == 0 and t.asset == "EURUSD" for t in tags)


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
    store.save(item, tag, event, score)

    assert store.load_news(NOW - timedelta(days=1)) == [item]
    assert store.load_tagged_news("EURUSD", NOW - timedelta(days=1)) == [(item, tag)]
    assert store.load_events(date(2026, 9, 15), date(2026, 9, 20)) == [event]
    assert store.load_scores("EURUSD", "v1", date(2026, 9, 1), date(2026, 9, 30)) == [score]
    assert store.load_scores("EURUSD", "v2", date(2026, 9, 1), date(2026, 9, 30)) == []


def test_fake_store_upserts() -> None:
    store = FakeStore()
    item = NewsItem.from_feed(source="s", title="t", url="u", published_at=NOW)
    store.save(item, item)
    assert len(store.news) == 1


def test_fake_store_rejects_unknown_types() -> None:
    with pytest.raises(TypeError, match="cannot store str"):
        FakeStore().save("not a record")  # type: ignore[arg-type]
