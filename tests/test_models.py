"""Domain models are immutable value objects."""

from datetime import UTC, datetime

import pytest

from manc.models import CalendarEvent, NewsItem, NewsTag

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)


def test_news_item_id_is_derived_from_url() -> None:
    a = NewsItem.from_feed(source="cnbc", title="A", url="https://x/1", published_at=NOW)
    b = NewsItem.from_feed(source="cnbc", title="B", url="https://x/1", published_at=NOW)
    assert a.id == b.id
    assert len(a.id) == 40  # sha1 hex


def test_models_are_frozen_and_hashable() -> None:
    item = NewsItem.from_feed(source="cnbc", title="A", url="https://x/1", published_at=NOW)
    tag = NewsTag(news_id=item.id, asset="EURUSD", direction=1, confidence=0.8)
    event = CalendarEvent(
        id="e1",
        date=NOW,
        country="united_states",
        event="CPI",
        category="inflation",
        importance=3,
        consensus=3.0,
        previous=2.9,
        actual=None,
    )
    for obj in (item, tag, event):
        hash(obj)
        with pytest.raises(AttributeError):
            obj.asset = "x"  # type: ignore[attr-defined,misc]


def test_news_tag_rejects_bad_direction_and_confidence() -> None:
    with pytest.raises(ValueError):
        NewsTag(news_id="n", asset="EURUSD", direction=2, confidence=0.5)
    with pytest.raises(ValueError):
        NewsTag(news_id="n", asset="EURUSD", direction=1, confidence=1.5)


def test_calendar_event_released_only_when_actual_present() -> None:
    kw = dict(id="e", date=NOW, country="u", event="x", category="c", importance=1)
    assert not CalendarEvent(**kw, consensus=1.0, previous=1.0, actual=None).released
    assert CalendarEvent(**kw, consensus=1.0, previous=1.0, actual=1.2).released
