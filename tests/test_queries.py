"""Read-side logic over a Store: bands, deltas, sparklines, headlines, events, forecasts."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from manc.config import (
    CalendarConfig,
    Config,
    FeedSpec,
    ForecastsConfig,
    InstitutionSpec,
    LexiconConfig,
    LlmConfig,
    ScoringConfig,
)
from manc.formulas.contract import AssetSpec, IndexScore
from manc.models import (
    CalendarEvent,
    ChainMetric,
    ForecastAsset,
    ForecastMacro,
    NewsItem,
    NewsTag,
    SpotPrice,
)
from manc.queries import (
    BANDS,
    asset_history,
    band,
    chain_series,
    forecasts_for,
    headlines_behind,
    overview,
    scale_of,
    upcoming_events,
)
from tests.fakes import FakeStore

TODAY = date(2026, 9, 15)
NOON = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
EURUSD = AssetSpec(symbol="EURUSD", kind="forex", economies=("euro_area", "united_states"))
SPX = AssetSpec(symbol="SPX", kind="equity_index", economies=("united_states",))
BTCUSD = AssetSpec(
    symbol="BTCUSD",
    kind="crypto",
    economies=("united_states",),
    chain={"coinmetrics": "btc", "defillama": "bitcoin"},
)
CONFIG = Config(
    assets=(EURUSD, SPX, BTCUSD),
    feeds=(FeedSpec("reuters", "https://r", 1.0), FeedSpec("fxstreet", "https://f", 0.6)),
    scoring=ScoringConfig(
        formula="v1",
        params={},
        windows={"news_hours": 72, "released_days": 7, "upcoming_days": 7},
    ),
    llm=LlmConfig(model="m", fallback=None, temperature=0, batch_size=40),
    calendar=CalendarConfig(categories=(), importances=(), countries={}),
    forecasts=ForecastsConfig(
        institutions=(
            InstitutionSpec("goldman_sachs", ("Goldman",), "bank", 0.9),
            InstitutionSpec("ing", (), "bank", 0.5),
        ),
        signals=(),
        metrics=("policy_rate",),
        min_confidence=0.5,
        queries=(),
    ),
    lexicon=LexiconConfig(economies=(), categories=(), assets=(), polarity=()),
)


def _score(
    asset: str, day: date, score: float, formula: str = "v1", risk: float = 0.0
) -> IndexScore:
    return IndexScore(
        asset=asset,
        date=day,
        score=score,
        formula=formula,
        components={"N": 0.1, "S": -0.2, "R": risk},
        n_news=3,
        n_events=1,
    )


def _event(
    event_id: str, when: datetime, country: str = "united_states", importance: int = 3
) -> CalendarEvent:
    return CalendarEvent(
        id=event_id,
        date=when,
        country=country,
        event="CPI",
        category="inflation",
        importance=importance,
        consensus=3.0,
        previous=2.9,
        actual=None,
    )


def _headline(
    store: FakeStore,
    title: str,
    *,
    source: str,
    published_at: datetime,
    direction: int,
    confidence: float,
) -> NewsItem:
    item = NewsItem.from_feed(
        source=source, title=title, url=f"https://x/{title}", published_at=published_at
    )
    store.news.add(item)
    store.tags.add(NewsTag(item.id, "EURUSD", direction, confidence, model="m"))
    return item


def _forecast(
    institution: str,
    value: float,
    published_at: datetime,
    horizon: date = date(2026, 12, 31),
    confidence: float = 0.9,
    asset: str = "EURUSD",
) -> ForecastAsset:
    return ForecastAsset.new(
        institution=institution,
        asset=asset,
        horizon_date=horizon,
        horizon_label="year-end",
        value=value,
        published_at=published_at,
        source_url="https://x",
        source_kind="extracted",
        confidence=confidence,
        model="m",
    )


def _macro(institution: str, economy: str, value: float, published_at: datetime) -> ForecastMacro:
    return ForecastMacro.new(
        institution=institution,
        economy=economy,
        metric="policy_rate",
        horizon_date=date(2026, 12, 31),
        horizon_label="year-end",
        value=value,
        published_at=published_at,
        source_url="https://x",
        source_kind="structured",
        confidence=1.0,
    )


# --- band -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, "headwind"),
        (29.9, "headwind"),
        (30.0, "lean_against"),
        (44.9, "lean_against"),
        (45.0, "neutral"),
        (54.9, "neutral"),
        (55.0, "lean_for"),
        (69.9, "lean_for"),
        (70.0, "tailwind"),
        (100.0, "tailwind"),
    ],
)
def test_band_boundaries(score: float, expected: str) -> None:
    assert band(score, scale_of("v1")) == expected


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (-100.0, "headwind"),
        (-40.0, "lean_against"),
        (-10.0, "neutral"),
        (10.0, "lean_for"),
        (40.0, "tailwind"),
    ],
)
def test_band_on_the_v2_scale(score: float, expected: str) -> None:
    assert band(score, scale_of("v2")) == expected


@given(st.floats(-100, 100), st.floats(-100, 100), st.sampled_from(["v1", "v2"]))
def test_band_is_monotone_in_the_score(low: float, high: float, formula: str) -> None:
    low, high = sorted((low, high))
    scale = scale_of(formula)
    assert BANDS.index(band(low, scale)) <= BANDS.index(band(high, scale))


# --- overview ---------------------------------------------------------------


def test_overview_one_summary_per_scored_asset() -> None:
    store = FakeStore()
    store.scores.add(_score("EURUSD", TODAY, 62.0))
    summaries = overview(store, CONFIG, TODAY)
    assert [summary.symbol for summary in summaries] == ["EURUSD"]
    summary = summaries[0]
    assert (summary.kind, summary.date, summary.score, summary.band, summary.formula) == (
        "forex",
        TODAY,
        62.0,
        "lean_for",
        "v1",
    )
    assert summary.delta is None
    assert summary.sparkline == (62.0,)


def test_overview_skips_assets_whose_kind_is_not_active() -> None:
    store = FakeStore()
    store.scores.add(_score("EURUSD", TODAY, 62.0), _score("SPX", TODAY, 40.0))
    config = replace(CONFIG, active_kinds=("equity_index",))
    assert [summary.symbol for summary in overview(store, config, TODAY)] == ["SPX"]


def test_overview_delta_from_the_previous_stored_day() -> None:
    store = FakeStore()
    store.scores.add(_score("EURUSD", TODAY - 3 * DAY, 40.0), _score("EURUSD", TODAY, 45.0))
    summary = overview(store, CONFIG, TODAY)[0]
    assert summary.delta == 5.0
    assert summary.sparkline == (40.0, 45.0)


def test_overview_sparkline_is_the_last_thirty_days_oldest_first() -> None:
    store = FakeStore()
    store.scores.add(
        *(_score("EURUSD", TODAY - offset * DAY, float(offset)) for offset in range(40))
    )
    summary = overview(store, CONFIG, TODAY)[0]
    assert len(summary.sparkline) == 30
    assert summary.sparkline[0] == 29.0
    assert summary.sparkline[-1] == 0.0


def test_overview_uses_the_latest_score_on_or_before_as_of() -> None:
    store = FakeStore()
    store.scores.add(_score("EURUSD", TODAY - DAY, 55.0), _score("EURUSD", TODAY + DAY, 80.0))
    summary = overview(store, CONFIG, TODAY)[0]
    assert (summary.date, summary.score) == (TODAY - DAY, 55.0)


def test_overview_event_risk_is_the_r_component() -> None:
    store = FakeStore()
    store.scores.add(_score("EURUSD", TODAY, 50.0, risk=0.75))
    assert overview(store, CONFIG, TODAY)[0].event_risk == 0.75


def test_overview_ignores_other_formulas() -> None:
    store = FakeStore()
    store.scores.add(_score("EURUSD", TODAY, 90.0, formula="v2"))
    assert overview(store, CONFIG, TODAY) == []


def test_overview_orders_by_distance_from_fifty() -> None:
    store = FakeStore()
    store.scores.add(_score("EURUSD", TODAY, 55.0), _score("SPX", TODAY, 20.0))
    assert [summary.symbol for summary in overview(store, CONFIG, TODAY)] == ["SPX", "EURUSD"]


def test_overview_under_v2_orders_by_distance_from_zero_and_bands_on_its_scale() -> None:
    store = FakeStore()
    store.scores.add(
        _score("EURUSD", TODAY, 5.0, formula="v2"), _score("SPX", TODAY, -45.0, formula="v2")
    )
    config = replace(CONFIG, scoring=replace(CONFIG.scoring, formula="v2"))
    summaries = overview(store, config, TODAY)
    assert [(summary.symbol, summary.band) for summary in summaries] == [
        ("SPX", "headwind"),
        ("EURUSD", "neutral"),
    ]


# --- asset_history ----------------------------------------------------------


def test_asset_history_series_within_range_and_formula() -> None:
    store = FakeStore()
    store.scores.add(
        _score("EURUSD", TODAY - 5 * DAY, 30.0),
        _score("EURUSD", TODAY - DAY, 48.0),
        _score("EURUSD", TODAY, 72.0),
        _score("EURUSD", TODAY, 99.0, formula="v2"),
    )
    history = asset_history(store, CONFIG, "EURUSD", "v1", TODAY - 2 * DAY, TODAY)
    assert (history.symbol, history.formula) == ("EURUSD", "v1")
    assert [(point.date, point.score, point.band) for point in history.points] == [
        (TODAY - DAY, 48.0, "neutral"),
        (TODAY, 72.0, "tailwind"),
    ]
    assert history.points[0].components == {"N": 0.1, "S": -0.2, "R": 0.0}
    assert (history.points[0].n_news, history.points[0].n_events) == (3, 1)
    assert history.scale == scale_of("v1")


def test_asset_history_under_v2_carries_its_scale_and_bands() -> None:
    store = FakeStore()
    store.scores.add(_score("EURUSD", TODAY, -30.0, formula="v2"))
    history = asset_history(store, CONFIG, "EURUSD", "v2", TODAY, TODAY)
    assert (history.scale.low, history.scale.high, history.scale.neutral) == (-100.0, 100.0, 0.0)
    assert history.points[0].band == "lean_against"


def test_asset_history_unknown_symbol() -> None:
    with pytest.raises(KeyError):
        asset_history(FakeStore(), CONFIG, "XXXUSD", "v1", TODAY, TODAY)


# --- headlines_behind -------------------------------------------------------


def test_headlines_behind_keeps_directional_tags_strongest_first() -> None:
    store = FakeStore()
    _headline(store, "weak", source="fxstreet", published_at=NOON, direction=1, confidence=0.9)
    _headline(store, "strong", source="reuters", published_at=NOON, direction=-1, confidence=0.8)
    _headline(store, "flat", source="reuters", published_at=NOON, direction=0, confidence=0.9)
    _headline(store, "unknown", source="blog", published_at=NOON, direction=1, confidence=0.5)
    views = headlines_behind(store, CONFIG, "EURUSD", TODAY)
    assert [view.title for view in views] == ["strong", "weak", "unknown"]
    strongest = views[0]
    assert (strongest.source, strongest.direction, strongest.confidence) == ("reuters", -1, 0.8)
    assert strongest.source_weight == 1.0
    assert strongest.weight == pytest.approx(0.8)
    assert strongest.url == "https://x/strong"
    assert strongest.published_at == NOON
    assert views[1].weight == pytest.approx(0.54)
    assert views[2].source_weight == 1.0  # a source missing from the feeds table


def test_headlines_behind_respects_the_news_window() -> None:
    store = FakeStore()
    end_of_day = datetime.combine(TODAY, datetime.max.time(), tzinfo=UTC)
    _headline(
        store,
        "old",
        source="reuters",
        published_at=end_of_day - 73 * HOUR,
        direction=1,
        confidence=1.0,
    )
    _headline(
        store,
        "fresh",
        source="reuters",
        published_at=end_of_day - 71 * HOUR,
        direction=1,
        confidence=1.0,
    )
    _headline(
        store,
        "future",
        source="reuters",
        published_at=end_of_day + HOUR,
        direction=1,
        confidence=1.0,
    )
    assert [view.title for view in headlines_behind(store, CONFIG, "EURUSD", TODAY)] == ["fresh"]


def test_headlines_behind_unknown_symbol() -> None:
    with pytest.raises(KeyError):
        headlines_behind(FakeStore(), CONFIG, "XXXUSD", TODAY)


# --- upcoming_events --------------------------------------------------------


def test_upcoming_events_filters_economies_and_importance_sorted_by_date() -> None:
    store = FakeStore()
    store.events.add(
        _event("later", NOON + 3 * DAY, importance=3),
        _event("soon", NOON + DAY, country="euro_area", importance=2),
        _event("minor", NOON + DAY, importance=1),
        _event("foreign", NOON + DAY, country="japan", importance=3),
        _event("past", NOON - DAY, importance=3),
    )
    events = upcoming_events(store, CONFIG, TODAY, TODAY + 7 * DAY, min_importance=2)
    assert [event.id for event in events] == ["soon", "later"]
    config = replace(CONFIG, active_kinds=("equity_index",))  # SPX: united_states only
    events = upcoming_events(store, config, TODAY, TODAY + 7 * DAY, min_importance=2)
    assert [event.id for event in events] == ["later"]


# --- forecasts_for ----------------------------------------------------------


def test_forecasts_for_latest_vintage_revision_and_distance_from_spot() -> None:
    store = FakeStore()
    store.forecasts_asset.add(
        _forecast("goldman_sachs", 1.10, NOON - 30 * DAY),
        _forecast("goldman_sachs", 1.20, NOON - 2 * DAY),
        _forecast("ing", 1.15, NOON - DAY),
        _forecast("goldman_sachs", 1.30, NOON + DAY),  # not yet known
    )
    store.spot.add(SpotPrice("EURUSD", TODAY, 1.0, "yahoo"))
    panel = forecasts_for(store, CONFIG, "EURUSD", TODAY, min_confidence=0.5)
    assert panel.symbol == "EURUSD"
    assert panel.spot == 1.0
    assert [(row.institution, row.value, row.previous_value) for row in panel.rows] == [
        ("goldman_sachs", 1.20, 1.10),
        ("ing", 1.15, None),
    ]
    goldman = panel.rows[0]
    assert (goldman.horizon_date, goldman.horizon_label) == (date(2026, 12, 31), "year-end")
    assert goldman.vs_spot == pytest.approx(0.20)
    assert goldman.published_at == NOON - 2 * DAY
    assert goldman.confidence == 0.9
    assert [median.horizon_date for median in panel.medians] == [date(2026, 12, 31)]
    assert panel.medians[0].value == pytest.approx(1.175)


def test_forecasts_for_without_spot_or_forecasts() -> None:
    panel = forecasts_for(FakeStore(), CONFIG, "EURUSD", TODAY, min_confidence=0.5)
    assert (panel.spot, panel.rows, panel.medians, panel.macro) == (None, (), (), ())


def test_forecasts_for_vs_spot_is_none_without_a_spot() -> None:
    store = FakeStore()
    store.forecasts_asset.add(_forecast("ing", 1.15, NOON - DAY))
    panel = forecasts_for(store, CONFIG, "EURUSD", TODAY, min_confidence=0.5)
    assert panel.rows[0].vs_spot is None


def test_forecasts_for_uses_the_spot_known_on_as_of() -> None:
    store = FakeStore()
    store.spot.add(SpotPrice("EURUSD", TODAY - DAY, 1.0, "yahoo"))
    store.spot.add(SpotPrice("EURUSD", TODAY + DAY, 2.0, "yahoo"))
    assert forecasts_for(store, CONFIG, "EURUSD", TODAY, min_confidence=0.5).spot == 1.0


def test_forecasts_for_filters_by_confidence() -> None:
    store = FakeStore()
    store.forecasts_asset.add(_forecast("ing", 1.15, NOON - DAY, confidence=0.3))
    assert forecasts_for(store, CONFIG, "EURUSD", TODAY, min_confidence=0.5).rows == ()


def test_forecasts_for_orders_institutions_by_weight_then_horizon() -> None:
    store = FakeStore()
    near, far = date(2026, 10, 31), date(2027, 6, 30)
    store.forecasts_asset.add(
        _forecast("ing", 1.15, NOON - DAY, horizon=near),
        _forecast("goldman_sachs", 1.25, NOON - DAY, horizon=far),
        _forecast("goldman_sachs", 1.20, NOON - DAY, horizon=near),
        _forecast("unknown_shop", 1.05, NOON - DAY, horizon=near),
    )
    panel = forecasts_for(store, CONFIG, "EURUSD", TODAY, min_confidence=0.5)
    assert [(row.institution, row.horizon_date) for row in panel.rows] == [
        ("goldman_sachs", near),
        ("goldman_sachs", far),
        ("ing", near),
        ("unknown_shop", near),
    ]
    assert [median.horizon_date for median in panel.medians] == [near, far]


def test_forecasts_for_macro_limited_to_the_asset_economies() -> None:
    store = FakeStore()
    store.forecasts_macro.add(
        _macro("goldman_sachs", "united_states", 3.5, NOON - 20 * DAY),
        _macro("goldman_sachs", "united_states", 3.25, NOON - DAY),
        _macro("ing", "euro_area", 2.0, NOON - DAY),
        _macro("ing", "japan", 0.5, NOON - DAY),
        _macro("ing", "united_states", 3.0, NOON + DAY),  # not yet known
    )
    panel = forecasts_for(store, CONFIG, "EURUSD", TODAY, min_confidence=0.5)
    assert [
        (row.institution, row.economy, row.value, row.previous_value) for row in panel.macro
    ] == [
        ("goldman_sachs", "united_states", 3.25, 3.5),
        ("ing", "euro_area", 2.0, None),
    ]
    assert panel.macro[0].metric == "policy_rate"


def test_forecasts_for_unknown_symbol() -> None:
    with pytest.raises(KeyError):
        forecasts_for(FakeStore(), CONFIG, "XXXUSD", TODAY, min_confidence=0.5)


# --- on-chain ------------------------------------------------------------------


def _chain(day: date, metric: str, value: float, source: str = "coinmetrics") -> ChainMetric:
    return ChainMetric(asset="BTCUSD", date=day, metric=metric, value=value, source=source)


def test_chain_series_in_a_fixed_order_with_the_net_flow_derived() -> None:
    store = FakeStore()
    store.chain.add(
        _chain(TODAY - DAY, "mvrv", 1.4),
        _chain(TODAY, "mvrv", 1.5),
        _chain(TODAY, "active_addresses", 600000.0),
        _chain(TODAY - 9 * DAY, "active_addresses", 1.0),  # outside the range
        _chain(TODAY, "exchange_inflow_usd", 1000.0),
        _chain(TODAY, "exchange_outflow_usd", 1500.0),
        _chain(TODAY - DAY, "exchange_inflow_usd", 900.0),  # no outflow that day: no net flow
        _chain(TODAY, "fees_usd", 10000.0, source="defillama"),
    )
    store.chain.add(
        _chain(TODAY, "fear_greed", 73.0, source="coinmarketcap"),
        _chain(TODAY, "sentiment_votes_up_pct", 78.6, source="coingecko"),
    )
    series = chain_series(store, CONFIG, "BTCUSD", TODAY - 7 * DAY, TODAY)
    assert [(one.metric, one.source, one.group) for one in series] == [
        ("active_addresses", "coinmetrics", "chain"),
        ("exchange_netflow_usd", "coinmetrics", "chain"),
        ("fees_usd", "defillama", "chain"),
        ("mvrv", "coinmetrics", "chain"),
        ("fear_greed", "coinmarketcap", "sentiment"),
        ("sentiment_votes_up_pct", "coingecko", "sentiment"),
    ]
    by_metric = {one.metric: one for one in series}
    assert [(point.date, point.value) for point in by_metric["mvrv"].points] == [
        (TODAY - DAY, 1.4),
        (TODAY, 1.5),
    ]
    assert [(point.date, point.value) for point in by_metric["exchange_netflow_usd"].points] == [
        (TODAY, -500.0)
    ]
    assert by_metric["active_addresses"].label == "Active addresses"
    assert by_metric["exchange_netflow_usd"].label == "Exchange net flow (USD)"


def test_chain_series_is_empty_for_an_asset_without_chain_data() -> None:
    assert chain_series(FakeStore(), CONFIG, "EURUSD", TODAY - DAY, TODAY) == []
    with pytest.raises(KeyError):
        chain_series(FakeStore(), CONFIG, "NOPE", TODAY - DAY, TODAY)
