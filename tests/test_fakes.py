"""Fakes must satisfy the Protocols and behave like a store."""

from datetime import UTC, date, datetime, timedelta

from manc.analysis.interface import Analyzer
from manc.calendar.interface import CalendarProvider
from manc.forecasts.interface import ForecastProvider
from manc.formulas.contract import AssetSpec, IndexScore
from manc.models import CalendarEvent, ForecastAsset, Forecasts, NewsItem, NewsTag, SpotPrice
from manc.news.interface import NewsProvider
from manc.spot.interface import SpotProvider
from manc.store.interface import (
    EventRepository,
    ForecastAssetRepository,
    ForecastMacroRepository,
    NewsRepository,
    ScoreRepository,
    SpotRepository,
    Store,
    TagRepository,
)
from tests.fakes import FakeAnalyzer, FakeCalendar, FakeForecasts, FakeNews, FakeSpot, FakeStore

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
ASSET = AssetSpec(symbol="EURUSD", kind="forex", economies=("euro_area", "united_states"))


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(FakeCalendar(), CalendarProvider)
    assert isinstance(FakeNews(), NewsProvider)
    assert isinstance(FakeAnalyzer(), Analyzer)
    assert isinstance(FakeForecasts(), ForecastProvider)
    assert isinstance(FakeSpot(), SpotProvider)
    store = FakeStore()
    assert isinstance(store, Store)
    assert isinstance(store.news, NewsRepository)
    assert isinstance(store.tags, TagRepository)
    assert isinstance(store.events, EventRepository)
    assert isinstance(store.scores, ScoreRepository)
    assert isinstance(store.forecasts_asset, ForecastAssetRepository)
    assert isinstance(store.forecasts_macro, ForecastMacroRepository)
    assert isinstance(store.spot, SpotRepository)


def test_fake_forecasts_and_spot_replay_by_window_and_asset() -> None:
    old = ForecastAsset.new(
        institution="ubs",
        asset="XAUUSD",
        horizon_date=date(2026, 12, 31),
        horizon_label="year-end",
        value=3900.0,
        published_at=NOW - timedelta(days=10),
        source_url="u",
        source_kind="extracted",
        confidence=0.7,
    )
    recent = ForecastAsset.new(
        institution="goldman_sachs",
        asset="XAUUSD",
        horizon_date=date(2026, 12, 31),
        horizon_label="year-end",
        value=4000.0,
        published_at=NOW,
        source_url="u",
        source_kind="extracted",
        confidence=0.7,
    )
    fetched = FakeForecasts(Forecasts(asset=(old, recent))).fetch(NOW - timedelta(days=1))
    assert fetched == Forecasts(asset=(recent,))
    assert FakeForecasts().fetch(NOW) == Forecasts()

    gold = SpotPrice(asset="XAUUSD", date=NOW.date(), close=3650.0, source="yahoo")
    euro = SpotPrice(asset="EURUSD", date=NOW.date(), close=1.17, source="yahoo")
    yesterday = SpotPrice(
        asset="EURUSD", date=NOW.date() - timedelta(days=1), close=1.16, source="yahoo"
    )
    assert FakeSpot([gold, euro, yesterday]).fetch([ASSET], NOW.date()) == [euro]


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
    assert store.scores.latest_day() == score.date


def test_fake_store_upserts() -> None:
    store = FakeStore()
    item = NewsItem.from_feed(source="s", title="t", url="u", published_at=NOW)
    store.news.add(item, item)
    assert len(store.news.rows) == 1
