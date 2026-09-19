"""build_inputs turns stored rows into the formula's ScoringInputs."""

from datetime import UTC, datetime, timedelta

import pytest

from manc.config import (
    CalendarConfig,
    Config,
    FeedSpec,
    ForecastsConfig,
    LexiconConfig,
    LlmConfig,
    ScoringConfig,
)
from manc.formulas.contract import AssetSpec
from manc.models import CalendarEvent, NewsItem, NewsTag
from manc.scoring.adapter import build_inputs
from tests.fakes import FakeStore

AS_OF = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
EURUSD = AssetSpec(symbol="EURUSD", kind="forex", economies=("euro_area", "united_states"))
CONFIG = Config(
    assets=(EURUSD,),
    feeds=(FeedSpec("reuters", "https://r", 1.0), FeedSpec("fxstreet", "https://f", 0.6)),
    scoring=ScoringConfig(
        formula="v1",
        params={"news_weight": 0.6},
        windows={
            "news_hours": 72,
            "released_days": 7,
            "upcoming_days": 7,
            "surprise_history_days": 730,
        },
    ),
    llm=LlmConfig(model="m", fallback=None, temperature=0, batch_size=40),
    calendar=CalendarConfig(categories=(), importances=(), countries={}),
    forecasts=ForecastsConfig(
        institutions=(), signals=(), metrics=(), queries=(), min_confidence=0.5
    ),
    lexicon=LexiconConfig(economies=(), categories=(), assets=(), polarity=()),
)


def _event(event_id: str, when: datetime, country: str, actual: float | None) -> CalendarEvent:
    return CalendarEvent(
        id=event_id,
        date=when,
        country=country,
        event="x",
        category="inflation",
        importance=2,
        consensus=1.0,
        previous=1.0,
        actual=actual,
    )


def test_splits_released_and_upcoming_within_windows_and_economies() -> None:
    store = FakeStore()
    store.events.add(
        _event("released", AS_OF - 2 * DAY, "united_states", actual=1.2),
        _event("too_old", AS_OF - 8 * DAY, "united_states", actual=1.2),
        _event("not_released_yet_today", AS_OF - 1 * HOUR, "euro_area", actual=None),
        _event("upcoming", AS_OF + 3 * DAY, "euro_area", actual=None),
        _event("too_far", AS_OF + 8 * DAY, "euro_area", actual=None),
        _event("other_economy", AS_OF + 1 * DAY, "japan", actual=None),
    )
    inputs = build_inputs(store, EURUSD, AS_OF, CONFIG)
    assert [event.country for event in inputs.released] == ["united_states"]
    assert [event.date for event in inputs.upcoming] == [AS_OF + 3 * DAY]
    assert inputs.asset == EURUSD
    assert inputs.as_of == AS_OF
    assert inputs.params == {"news_weight": 0.6}


def _release(
    event_id: str, when: datetime, name: str, consensus: float | None, actual: float | None
):
    return CalendarEvent(
        id=event_id,
        date=when,
        country="united_states",
        event=name,
        category="inflation",
        importance=3,
        consensus=consensus,
        previous=None,
        actual=actual,
    )


def test_released_events_carry_the_earlier_surprises_of_the_same_release() -> None:
    store = FakeStore()
    store.events.add(
        _release("now", AS_OF - DAY, "CPI", consensus=3.0, actual=3.4),
        _release("month_ago", AS_OF - 31 * DAY, "CPI", consensus=2.9, actual=3.0),
        _release("two_months", AS_OF - 61 * DAY, "CPI", consensus=2.8, actual=2.6),
        _release("no_consensus", AS_OF - 92 * DAY, "CPI", consensus=None, actual=2.5),
        _release("other_release", AS_OF - 31 * DAY, "Core CPI", consensus=2.0, actual=2.5),
        _release("too_old", AS_OF - 800 * DAY, "CPI", consensus=2.0, actual=3.0),
    )
    [released] = build_inputs(store, EURUSD, AS_OF, CONFIG).released
    assert released.past_surprises == pytest.approx((-0.2, 0.1))  # oldest first, CPI only


def test_formula_windows_override_the_config() -> None:
    store = FakeStore()
    store.events.add(
        _event("recent", AS_OF - 2 * DAY, "united_states", actual=1.2),
        _event("older", AS_OF - 30 * DAY, "united_states", actual=1.2),
    )
    assert len(build_inputs(store, EURUSD, AS_OF, CONFIG).released) == 1
    widened = build_inputs(store, EURUSD, AS_OF, CONFIG, windows={"released_days": 90})
    assert [event.date for event in widened.released] == [AS_OF - 30 * DAY, AS_OF - 2 * DAY]


def test_tags_carry_feed_weights_and_respect_news_window() -> None:
    store = FakeStore()
    recent = NewsItem.from_feed(source="fxstreet", title="a", url="u/a", published_at=AS_OF - HOUR)
    old = NewsItem.from_feed(source="reuters", title="b", url="u/b", published_at=AS_OF - 80 * HOUR)
    unknown = NewsItem.from_feed(source="blog", title="c", url="u/c", published_at=AS_OF)
    store.news.add(recent, old, unknown)
    store.tags.add(
        NewsTag(news_id=recent.id, asset="EURUSD", direction=1, confidence=0.8),
        NewsTag(news_id=old.id, asset="EURUSD", direction=-1, confidence=0.9),
        NewsTag(news_id=unknown.id, asset="EURUSD", direction=1, confidence=0.5),
        NewsTag(news_id=recent.id, asset="XAUUSD", direction=-1, confidence=0.8),
    )
    inputs = build_inputs(store, EURUSD, AS_OF, CONFIG)
    by_weight = sorted(inputs.tags, key=lambda tag: tag.source_weight)
    assert [(tag.direction, tag.source_weight) for tag in by_weight] == [(1, 0.6), (1, 1.0)]
    assert all(tag.published_at.tzinfo is not None for tag in inputs.tags)
