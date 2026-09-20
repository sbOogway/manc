"""The daily run on fakes: fetch, tag, score, store."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import pytest

from manc.config import load_config
from manc.formulas.contract import AssetSpec
from manc.formulas.registry import get_formula
from manc.models import (
    CalendarEvent,
    ForecastAsset,
    ForecastMacro,
    Forecasts,
    NewsItem,
    NewsTag,
    SpotPrice,
)
from manc.pipeline import fetch, rescore, run
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
        forecasts=[FakeForecasts()],
        spot=FakeSpot(),
        store=store,
        formula=get_formula("v1"),
        summarize=None,
    )
    assert store.events.rows == {"e1": event}
    assert store.news.rows == {item.id: item}
    assert len(store.tags.rows) == len(CONFIG.assets)  # FakeAnalyzer tags every asset
    assert [score.asset for score in scores] == [asset.symbol for asset in CONFIG.active_assets]
    assert all(score.date == date(2026, 9, 15) and score.formula == "v1" for score in scores)
    assert all(score.score == 50.0 for score in scores)
    assert store.scores.series("BTCUSD", "v1", AS_OF.date(), AS_OF.date()) == [scores[0]]


def test_run_stores_the_closes_the_spot_provider_returns() -> None:
    store = FakeStore()
    gold = SpotPrice(asset="XAUUSD", date=AS_OF.date(), close=3650.0, source="yahoo")
    bitcoin = SpotPrice(asset="BTCUSD", date=AS_OF.date(), close=115000.0, source="yahoo")
    old_bitcoin = SpotPrice(asset="BTCUSD", date=date(2026, 9, 1), close=110000.0, source="yahoo")
    run(
        as_of=AS_OF,
        config=CONFIG,
        calendar=FakeCalendar(),
        news=FakeNews(),
        analyzer=FakeAnalyzer(),
        forecasts=[],
        spot=FakeSpot([gold, bitcoin, old_bitcoin]),
        store=store,
        formula=get_formula("v1"),
        summarize=None,
    )
    assert store.spot.latest("BTCUSD") == bitcoin  # FakeSpot answers only for the run's day
    assert store.spot.between("BTCUSD", date.min, date.max) == [bitcoin]
    assert store.spot.latest("XAUUSD") is None  # metal is not an active kind


def test_run_stores_the_forecasts_every_provider_returns() -> None:
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
        asset="BRENT", value=60.0, **{**common, "published_at": AS_OF - timedelta(days=30)}
    )
    run(
        as_of=AS_OF,
        config=CONFIG,
        calendar=FakeCalendar(),
        news=FakeNews(),
        analyzer=FakeAnalyzer(),
        forecasts=[
            FakeForecasts(Forecasts(asset=(gold, stale))),
            FakeForecasts(Forecasts(macro=(rate,))),
        ],
        spot=FakeSpot(),
        store=store,
        formula=get_formula("v1"),
        summarize=None,
    )
    assert store.forecasts_asset.latest("XAUUSD") == [gold]
    assert store.forecasts_asset.latest("BRENT") == []  # outside the news window
    assert store.forecasts_macro.latest("united_states") == [rate]


class ExplodingAnalyzer:
    def tag(self, items: object, assets: object) -> list[NewsTag]:
        raise AssertionError("fetch must not tag")


def test_fetch_stores_the_inputs_and_never_analyzes() -> None:
    store = FakeStore()
    event = _event("e1", AS_OF + timedelta(days=2))
    item = NewsItem.from_feed(source="cnbc_top", title="t", url="u", published_at=AS_OF)
    bitcoin = SpotPrice(asset="BTCUSD", date=AS_OF.date(), close=115000.0, source="yahoo")
    fetched = fetch(
        as_of=AS_OF,
        config=CONFIG,
        calendar=FakeCalendar([event]),
        news=FakeNews([item]),
        spot=FakeSpot([bitcoin]),
        store=store,
    )
    assert (fetched.events, fetched.items, fetched.closes) == ([event], [item], [bitcoin])
    assert store.events.rows == {"e1": event}
    assert store.news.unanalyzed(AS_OF - timedelta(days=1)) == [item]
    assert store.spot.latest("BTCUSD") == bitcoin
    assert store.tags.rows == {} and store.scores.rows == {}


def test_run_tags_only_what_earlier_fetches_left_unanalyzed() -> None:
    store = FakeStore()
    earlier = NewsItem.from_feed(source="cnbc_top", title="a", url="u/a", published_at=AS_OF)
    fetch(
        as_of=AS_OF,
        config=CONFIG,
        calendar=FakeCalendar(),
        news=FakeNews([earlier]),
        spot=FakeSpot(),
        store=store,
    )
    seen_twice = NewsItem.from_feed(source="cnbc_top", title="b", url="u/b", published_at=AS_OF)
    tagged_ids: list[set[str]] = []

    class RecordingAnalyzer(FakeAnalyzer):
        def tag(self, items: Sequence[NewsItem], assets: Sequence[AssetSpec]) -> list[NewsTag]:
            tagged_ids.append({item.id for item in items})
            return super().tag(items, assets)

    common = dict(
        as_of=AS_OF,
        config=CONFIG,
        calendar=FakeCalendar(),
        analyzer=RecordingAnalyzer(),
        forecasts=[],
        spot=FakeSpot(),
        store=store,
        formula=get_formula("v1"),
        summarize=None,
    )
    run(news=FakeNews([earlier, seen_twice]), **common)
    run(news=FakeNews([seen_twice]), **common)  # the next day: nothing new to tag
    assert tagged_ids == [{earlier.id, seen_twice.id}, set()]
    assert store.news.unanalyzed(AS_OF - timedelta(days=1)) == []


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
        summarize=None,
    )
    assert len(scores) == 2 * len(CONFIG.active_assets)
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
            summarize=None,
        )


class Paragraph:
    """A `complete` that answers every summary request with the same line."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, config: object, messages: object, response_model: type) -> tuple:
        self.calls += 1
        return response_model(paragraph="Nothing moved."), "free/model"


def test_run_stores_a_report_with_the_summary_for_every_asset() -> None:
    store = FakeStore()
    summarize = Paragraph()
    scores = run(
        as_of=AS_OF,
        config=CONFIG,
        calendar=FakeCalendar(),
        news=FakeNews(),
        analyzer=FakeAnalyzer(),
        forecasts=[],
        spot=FakeSpot(),
        store=store,
        formula=get_formula("v1"),
        summarize=summarize,
    )
    assert summarize.calls == len(CONFIG.active_assets)
    for score in scores:
        assert score.report_md.startswith(
            f"# {score.asset} 2026-09-15: 50 neutral\n\nNothing moved."
        )
        assert store.scores.series(score.asset, "v1", AS_OF.date(), AS_OF.date()) == [score]


def test_rescore_stores_template_only_reports() -> None:
    store = FakeStore()
    [score, *_rest] = rescore(
        config=CONFIG,
        store=store,
        formula=get_formula("v1"),
        start=date(2026, 9, 15),
        end=date(2026, 9, 15),
        summarize=None,
    )
    assert score.report_md.startswith("# BTCUSD 2026-09-15: 50 neutral\n\n## Components")
    assert "Summary by" not in score.report_md
