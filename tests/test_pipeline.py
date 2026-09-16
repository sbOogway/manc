"""The daily run on fakes: fetch, tag, score, store."""

from datetime import UTC, date, datetime, timedelta

import pytest

from manc.config import load_config
from manc.formulas.registry import get_formula
from manc.models import CalendarEvent, NewsItem
from manc.pipeline import rescore, run
from tests.fakes import FakeAnalyzer, FakeCalendar, FakeNews, FakeStore

AS_OF = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
CONFIG = load_config()


def _event(event_id: str, when: datetime) -> CalendarEvent:
    return CalendarEvent(
        id=event_id,
        date=when,
        country="united_states",
        event="CPI",
        category="inflation",
        importance=3,
        consensus=3.0,
        previous=2.9,
        actual=None,
    )


def test_run_stores_inputs_and_one_score_per_asset() -> None:
    store = FakeStore()
    event = _event("e1", AS_OF + timedelta(days=2))
    item = NewsItem.from_feed(source="cnbc_top", title="t", url="u", published_at=AS_OF)
    scores = run(
        as_of=AS_OF,
        config=CONFIG,
        calendar=FakeCalendar([event]),
        news=FakeNews([item]),
        analyzer=FakeAnalyzer(),
        store=store,
        formula=get_formula("v1"),
    )
    assert store.events.rows == {"e1": event}
    assert store.news.rows == {item.id: item}
    assert len(store.tags.rows) == len(CONFIG.assets)  # FakeAnalyzer tags every asset
    assert [score.asset for score in scores] == [asset.symbol for asset in CONFIG.assets]
    assert all(score.date == date(2026, 9, 15) and score.formula == "v1" for score in scores)
    assert all(score.score == 50.0 for score in scores)
    assert store.scores.series("EURUSD", "v1", AS_OF.date(), AS_OF.date()) == [scores[0]]


class ExplodingCalendar:
    def fetch(self, start: date, end: date) -> list[CalendarEvent]:
        raise AssertionError("rescore must not fetch")


def test_rescore_replays_stored_inputs_without_providers() -> None:
    store = FakeStore()
    scores = rescore(
        config=CONFIG,
        store=store,
        formula=get_formula("v1"),
        start=date(2026, 9, 14),
        end=date(2026, 9, 15),
    )
    assert len(scores) == 2 * len(CONFIG.assets)
    assert {score.date for score in scores} == {date(2026, 9, 14), date(2026, 9, 15)}
    assert store.scores.series("SPX", "v1", date(2026, 9, 14), date(2026, 9, 15)) == [
        score for score in scores if score.asset == "SPX"
    ]


def test_rescore_rejects_inverted_range() -> None:
    with pytest.raises(ValueError, match="start"):
        rescore(
            config=CONFIG,
            store=FakeStore(),
            formula=get_formula("v1"),
            start=date(2026, 9, 15),
            end=date(2026, 9, 14),
        )
