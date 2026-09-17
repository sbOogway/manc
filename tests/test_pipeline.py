"""The daily run on fakes: fetch, tag, score, store."""

from datetime import UTC, date, datetime, timedelta

import pytest

from manc.config import load_config
from manc.formulas.registry import get_formula
from manc.models import (
    CalendarEvent,
    ForecastAsset,
    ForecastMacro,
    Forecasts,
    NewsItem,
    SpotPrice,
)
from manc.pipeline import rescore, run
from tests.fakes import (
    FakeAnalyzer,
    FakeCalendar,
    FakeForecasts,
    FakeNews,
    FakeSpot,
    FakeStore,
)

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
        forecasts=FakeForecasts(),
        spot=FakeSpot(),
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


def test_run_stores_the_closes_the_spot_provider_returns() -> None:
    store = FakeStore()
    gold = SpotPrice(asset="XAUUSD", date=AS_OF.date(), close=3650.0, source="yahoo")
    old_gold = SpotPrice(asset="XAUUSD", date=date(2026, 9, 1), close=3600.0, source="yahoo")
    run(
        as_of=AS_OF,
        config=CONFIG,
        calendar=FakeCalendar(),
        news=FakeNews(),
        analyzer=FakeAnalyzer(),
        forecasts=FakeForecasts(),
        spot=FakeSpot([gold, old_gold]),
        store=store,
        formula=get_formula("v1"),
    )
    assert store.spot.latest("XAUUSD") == gold  # FakeSpot answers only for the run's day
    assert store.spot.between("XAUUSD", date.min, date.max) == [gold]


def test_run_stores_the_forecasts_the_provider_returns() -> None:
    store = FakeStore()
    common = dict(
        institution="goldman_sachs",
        horizon_date=date(2026, 12, 31),
        horizon_label="year-end",
        published_at=AS_OF - timedelta(hours=2),
        source_url="https://x/gold",
        source_kind="extracted",
        confidence=0.8,
        model="free",
    )
    gold = ForecastAsset.new(asset="XAUUSD", value=4000.0, **common)
    rate = ForecastMacro.new(economy="united_states", metric="policy_rate", value=3.4, **common)
    stale = ForecastAsset.new(
        asset="WTI", value=60.0, **{**common, "published_at": AS_OF - timedelta(days=30)}
    )
    run(
        as_of=AS_OF,
        config=CONFIG,
        calendar=FakeCalendar(),
        news=FakeNews(),
        analyzer=FakeAnalyzer(),
        forecasts=FakeForecasts(Forecasts(asset=(gold, stale), macro=(rate,))),
        spot=FakeSpot(),
        store=store,
        formula=get_formula("v1"),
    )
    assert store.forecasts_asset.latest("XAUUSD") == [gold]
    assert store.forecasts_asset.latest("WTI") == []  # outside the news window
    assert store.forecasts_macro.latest("united_states") == [rate]


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
