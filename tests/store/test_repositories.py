"""One contract suite for every Store implementation: the fake and the SQL store must agree."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from manc.formulas.contract import IndexScore
from manc.models import AssetForecast, CalendarEvent, MacroForecast, NewsItem, NewsTag, SpotPrice
from manc.store import db
from manc.store.interface import Store
from manc.store.sql import SqlStore
from tests.fakes import FakeStore

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def _sql_store(tmp_path: Path) -> SqlStore:
    url = f"sqlite:///{tmp_path / 'store.db'}"
    db.upgrade(url)
    return SqlStore(db.make_engine(url))


@pytest.fixture(params=["fake", "sql"])
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Store:
    factories: dict[str, Callable[[], Store]] = {
        "fake": FakeStore,
        "sql": lambda: _sql_store(tmp_path),
    }
    return factories[request.param]()


def _item(url: str, published_at: datetime = NOW, title: str = "t") -> NewsItem:
    return NewsItem.from_feed(source="cnbc", title=title, url=url, published_at=published_at)


def _event(event_id: str, when: datetime, actual: float | None = None) -> CalendarEvent:
    return CalendarEvent(
        id=event_id,
        date=when,
        country="united_states",
        event="CPI",
        category="inflation",
        importance=3,
        consensus=3.0,
        previous=2.9,
        actual=actual,
    )


def _score(day: date, formula: str = "v1", value: float = 55.0) -> IndexScore:
    return IndexScore(
        asset="EURUSD",
        date=day,
        score=value,
        formula=formula,
        components={"N": 0.1, "S": -0.2},
        n_news=3,
        n_events=1,
        report_md="# report",
    )


def _forecast(
    value: float = 4000.0,
    published_at: datetime = NOW,
    institution: str = "goldman_sachs",
    asset: str = "XAUUSD",
    horizon_date: date = date(2026, 12, 31),
    source_url: str = "https://x/gold",
) -> AssetForecast:
    return AssetForecast.new(
        institution=institution,
        asset=asset,
        horizon_date=horizon_date,
        horizon_label="year-end",
        value=value,
        published_at=published_at,
        source_url=source_url,
        source_kind="extracted",
        confidence=0.8,
        model="openrouter/free",
    )


def _macro(
    value: float = 3.4,
    published_at: datetime = NOW,
    economy: str = "united_states",
    metric: str = "policy_rate",
    institution: str = "fed",
) -> MacroForecast:
    return MacroForecast.new(
        institution=institution,
        economy=economy,
        metric=metric,
        horizon_date=date(2026, 12, 31),
        horizon_label="2026",
        value=value,
        published_at=published_at,
        source_url="https://fed/sep",
        source_kind="structured",
        confidence=1.0,
    )


def _spot(day: date, close: float = 3650.0, asset: str = "XAUUSD") -> SpotPrice:
    return SpotPrice(asset=asset, date=day, close=close, source="stooq")


def test_news_round_trip_sorted_and_windowed(store: Store) -> None:
    old, mid, new = _item("u/old", NOW - 3 * DAY), _item("u/mid", NOW - DAY), _item("u/new", NOW)
    store.news.add(new, old, mid)
    assert store.news.since(NOW - 2 * DAY) == [mid, new]


def test_news_add_is_an_upsert(store: Store) -> None:
    first = _item("u/1", title="first")
    store.news.add(first)
    store.news.add(replace(first, title="second"))
    assert [item.title for item in store.news.since(NOW - DAY)] == ["second"]


def test_tagged_joins_news_and_tags_for_one_asset(store: Store) -> None:
    item_a, item_b = _item("u/a"), _item("u/b")
    store.news.add(item_a, item_b)
    tag_a = NewsTag(news_id=item_a.id, asset="EURUSD", direction=1, confidence=0.9)
    tag_b = NewsTag(news_id=item_b.id, asset="XAUUSD", direction=-1, confidence=0.4)
    store.tags.add(tag_a, tag_b)
    assert store.news.tagged("EURUSD", NOW - DAY) == [(item_a, tag_a)]
    assert store.news.tagged("BTCUSD", NOW - DAY) == []


def test_tags_add_is_an_upsert(store: Store) -> None:
    item = _item("u/a")
    store.news.add(item)
    store.tags.add(NewsTag(news_id=item.id, asset="EURUSD", direction=1, confidence=0.5))
    store.tags.add(NewsTag(news_id=item.id, asset="EURUSD", direction=-1, confidence=0.7))
    [(_, tag)] = store.news.tagged("EURUSD", NOW - DAY)
    assert (tag.direction, tag.confidence) == (-1, 0.7)


def test_events_between_is_inclusive_and_sorted(store: Store) -> None:
    before = _event("e0", NOW - 2 * DAY, actual=3.1)
    inside_late = _event("e2", NOW + 2 * DAY)
    inside_early = _event("e1", NOW)
    after = _event("e3", NOW + 5 * DAY)
    store.events.add(inside_late, after, inside_early, before)
    window = store.events.between(NOW.date(), (NOW + 2 * DAY).date())
    assert window == [inside_early, inside_late]
    assert window[0].date.tzinfo is not None


def test_events_add_is_an_upsert_that_fills_actual(store: Store) -> None:
    store.events.add(_event("e1", NOW))
    store.events.add(_event("e1", NOW, actual=3.4))
    [event] = store.events.between(NOW.date(), NOW.date())
    assert event.actual == 3.4


def test_scores_series_by_asset_formula_and_window(store: Store) -> None:
    day = NOW.date()
    store.scores.add(_score(day + DAY), _score(day), _score(day - 10 * DAY), _score(day, "v2", 40))
    assert store.scores.series("EURUSD", "v1", day, day + DAY) == [_score(day), _score(day + DAY)]
    assert store.scores.series("EURUSD", "v2", day, day) == [_score(day, "v2", 40)]
    assert store.scores.series("XAUUSD", "v1", day, day) == []


def test_scores_add_is_an_upsert(store: Store) -> None:
    day = NOW.date()
    store.scores.add(_score(day, value=55.0))
    store.scores.add(_score(day, value=61.0))
    [score] = store.scores.series("EURUSD", "v1", day, day)
    assert score.score == 61.0
    assert score.report_md == "# report"


def test_sql_store_refuses_unmigrated_database(tmp_path: Path) -> None:
    engine = db.make_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        SqlStore(engine)


def test_add_with_nothing_is_a_no_op(store: Store) -> None:
    store.news.add()
    assert store.news.since(NOW - DAY) == []


def test_asset_forecasts_round_trip_and_latest_per_institution_and_horizon(store: Store) -> None:
    older = _forecast(value=3700.0, published_at=NOW - 30 * DAY)
    newer = _forecast(value=4000.0)
    other_horizon = _forecast(value=4300.0, horizon_date=date(2027, 6, 30))
    ubs = _forecast(value=3900.0, institution="ubs")
    wti = _forecast(value=60.0, asset="WTI")
    store.forecasts_asset.add(older, newer, other_horizon, ubs, wti)
    assert store.forecasts_asset.latest("XAUUSD") == [newer, other_horizon, ubs]
    assert store.forecasts_asset.latest("WTI") == [wti]
    assert store.forecasts_asset.latest("EURUSD") == []
    assert store.forecasts_asset.latest("XAUUSD")[0].published_at.tzinfo is not None


def test_asset_forecast_upsert_keeps_the_earliest_sighting(store: Store) -> None:
    first = _forecast(published_at=NOW, source_url="https://x/first")
    re_report = _forecast(published_at=NOW + 3 * DAY, source_url="https://y/later")
    earlier = _forecast(published_at=NOW - 2 * DAY, source_url="https://z/earlier")
    store.forecasts_asset.add(first)
    store.forecasts_asset.add(re_report)
    assert store.forecasts_asset.latest("XAUUSD") == [first]
    store.forecasts_asset.add(earlier)  # a backfill finds the original article
    assert store.forecasts_asset.latest("XAUUSD") == [earlier]


def test_asset_forecast_vintages_in_publication_order(store: Store) -> None:
    raised = _forecast(value=4000.0, published_at=NOW)
    initial = _forecast(value=3700.0, published_at=NOW - 60 * DAY)
    cut = _forecast(value=3500.0, published_at=NOW - 90 * DAY)
    store.forecasts_asset.add(raised, initial, cut, _forecast(institution="ubs"))
    vintages = store.forecasts_asset.vintages("goldman_sachs", "XAUUSD", date(2026, 12, 31))
    assert [vintage.value for vintage in vintages] == [3500.0, 3700.0, 4000.0]
    assert store.forecasts_asset.vintages("goldman_sachs", "XAUUSD", date(2030, 1, 1)) == []


def test_asset_forecast_as_of_sees_only_what_was_published_by_then(store: Store) -> None:
    initial = _forecast(value=3700.0, published_at=NOW - 60 * DAY)
    raised = _forecast(value=4000.0, published_at=NOW)
    store.forecasts_asset.add(raised, initial, _forecast(value=61.0, asset="WTI"))
    assert store.forecasts_asset.as_of("XAUUSD", (NOW - DAY).date()) == [initial]
    assert store.forecasts_asset.as_of("XAUUSD", NOW.date()) == [initial, raised]
    assert store.forecasts_asset.as_of("XAUUSD", (NOW - 100 * DAY).date()) == []


def test_macro_forecasts_round_trip_latest_vintages_and_as_of(store: Store) -> None:
    older_rate = _macro(value=3.9, published_at=NOW - 90 * DAY)
    rate = _macro(value=3.4)
    cpi = _macro(value=2.6, metric="cpi")
    euro = _macro(value=2.0, economy="euro_area", institution="ecb")
    store.forecasts_macro.add(older_rate, rate, cpi, euro)
    assert store.forecasts_macro.latest("united_states") == [rate, cpi]
    assert store.forecasts_macro.latest("euro_area") == [euro]
    assert store.forecasts_macro.vintages(
        "fed", "united_states", "policy_rate", date(2026, 12, 31)
    ) == [
        older_rate,
        rate,
    ]
    assert store.forecasts_macro.as_of("united_states", (NOW - DAY).date()) == [older_rate]


def test_macro_forecast_upsert_keeps_the_earliest_sighting(store: Store) -> None:
    store.forecasts_macro.add(_macro(published_at=NOW))
    store.forecasts_macro.add(_macro(published_at=NOW + DAY))
    [forecast] = store.forecasts_macro.latest("united_states")
    assert forecast.published_at == NOW


def test_spot_latest_and_between(store: Store) -> None:
    day = NOW.date()
    store.spot.add(_spot(day - 2 * DAY, 3600.0), _spot(day, 3650.0), _spot(day - DAY, 3620.0))
    store.spot.add(_spot(day, 1.17, asset="EURUSD"))
    assert store.spot.latest("XAUUSD") == _spot(day, 3650.0)
    assert store.spot.latest("BTCUSD") is None
    assert store.spot.between("XAUUSD", day - DAY, day) == [
        _spot(day - DAY, 3620.0),
        _spot(day, 3650.0),
    ]


def test_spot_add_overwrites_the_close(store: Store) -> None:
    day = NOW.date()
    store.spot.add(_spot(day, 3650.0))
    store.spot.add(_spot(day, 3660.0))
    assert store.spot.between("XAUUSD", day, day) == [_spot(day, 3660.0)]
