"""FormulaV1 (blueprint section 5): news term, signed surprise term, event-risk shrink."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from manc.formulas.contract import AssetSpec, EventObservation, ScoringInputs, TaggedHeadline
from manc.formulas.v1 import FormulaV1

AS_OF = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)
EURUSD = AssetSpec(
    symbol="EURUSD",
    kind="forex",
    economies=("euro_area", "united_states"),
    signs={
        "euro_area": {"inflation": 1, "employment": 1, "growth": 1, "rates": 1},
        "united_states": {"inflation": -1, "employment": -1, "growth": -1, "rates": -1},
    },
)


def _tag(direction: int, confidence: float = 1.0, weight: float = 1.0, age_hours: float = 0.0):
    return TaggedHeadline(
        direction=direction,
        confidence=confidence,
        source_weight=weight,
        published_at=AS_OF - age_hours * HOUR,
    )


def _event(
    country: str = "united_states",
    category: str = "inflation",
    importance: int = 3,
    consensus: float | None = None,
    previous: float | None = None,
    actual: float | None = None,
    days_ahead: float = 0.0,
) -> EventObservation:
    return EventObservation(
        date=AS_OF + days_ahead * 24 * HOUR,
        country=country,
        category=category,
        importance=importance,
        consensus=consensus,
        previous=previous,
        actual=actual,
    )


def _inputs(tags=(), released=(), upcoming=(), params=None, asset=EURUSD) -> ScoringInputs:
    return ScoringInputs(
        asset=asset,
        as_of=AS_OF,
        tags=tuple(tags),
        released=tuple(released),
        upcoming=tuple(upcoming),
        params=params or {},
    )


def _score(**kwargs) -> float:
    return FormulaV1().compute(_inputs(**kwargs)).score


def test_blueprint_worked_example() -> None:
    """N = +0.3, S = -0.5, R = 0.5 -> raw = -0.02 -> 50 + 50 * -0.02 * 0.75 = 49.25."""
    score = FormulaV1().compute(
        _inputs(
            tags=[_tag(1, confidence=0.65), _tag(-1, confidence=0.35)],
            released=[_event(consensus=3.0, previous=3.0, actual=4.5)],  # +50% hot US CPI
            upcoming=[
                _event("euro_area", "rates", importance=3, days_ahead=2),
                _event("united_states", "employment", importance=3, days_ahead=4),
            ],
        )
    )
    assert score.score == pytest.approx(49.25)
    assert score.components["N"] == pytest.approx(0.3)
    assert score.components["S"] == pytest.approx(-0.5)
    assert score.components["R"] == pytest.approx(0.5)
    assert (score.n_news, score.n_events) == (2, 1)
    assert score.formula == "v1"


# --- news term ------------------------------------------------------------------------------


def test_news_alone_moves_the_score_by_its_weight() -> None:
    assert _score(tags=[_tag(1)]) == pytest.approx(50 + 50 * 0.6)
    assert _score(tags=[_tag(-1)]) == pytest.approx(50 - 50 * 0.6)


def test_fresher_headline_outweighs_an_older_opposite_one() -> None:
    fresh_bull_old_bear = _score(tags=[_tag(1), _tag(-1, age_hours=48)])
    old_bull_fresh_bear = _score(tags=[_tag(1, age_hours=48), _tag(-1)])
    assert fresh_bull_old_bear > 50 > old_bull_fresh_bear
    # one half-life later the old headline still carries half the weight: N = (1 - 0.5) / 1.5
    assert fresh_bull_old_bear == pytest.approx(50 + 50 * 0.6 * (1 / 3))


def test_confidence_and_source_weight_scale_a_headline() -> None:
    assert _score(tags=[_tag(1, confidence=0.5), _tag(-1, confidence=0.5)]) == 50.0
    assert _score(tags=[_tag(1, weight=1.0), _tag(-1, weight=0.5)]) > 50.0
    assert _score(tags=[_tag(1, confidence=0.2), _tag(-1, confidence=0.8)]) < 50.0


def test_neutral_or_zero_confidence_headlines_do_not_move_the_score() -> None:
    assert _score(tags=[_tag(0), _tag(0, confidence=0.9)]) == 50.0
    assert _score(tags=[_tag(1, confidence=0.0)]) == 50.0
    assert _score(tags=[_tag(1, weight=0.0)]) == 50.0


# --- surprise term --------------------------------------------------------------------------


def test_surprise_is_normalised_by_the_larger_of_consensus_and_previous() -> None:
    small_consensus = _score(released=[_event(consensus=0.1, previous=2.0, actual=1.0)])
    # (1.0 - 0.1) / max(0.1, 2.0) = 0.45, signed -1 for a hot US print on EURUSD
    assert small_consensus == pytest.approx(50 - 50 * 0.4 * 0.45)


def test_surprise_is_clipped_to_one() -> None:
    huge_miss = _score(released=[_event(consensus=1.0, previous=1.0, actual=100.0)])
    assert huge_miss == pytest.approx(50 - 50 * 0.4)


def test_surprise_sign_follows_the_asset_map() -> None:
    hot_euro_cpi = _event("euro_area", "inflation", consensus=2.0, previous=2.0, actual=3.0)
    hot_us_cpi = _event("united_states", "inflation", consensus=2.0, previous=2.0, actual=3.0)
    assert _score(released=[hot_euro_cpi]) > 50 > _score(released=[hot_us_cpi])


@pytest.mark.parametrize(
    "ignored",
    [
        _event(consensus=None, previous=2.0, actual=3.0),  # nothing to be surprised against
        _event("japan", "inflation", consensus=2.0, previous=2.0, actual=3.0),  # not in signs
        _event("united_states", "weather", consensus=2.0, previous=2.0, actual=3.0),
        _event(consensus=2.0, previous=2.0, actual=None),  # not released yet
    ],
)
def test_events_the_formula_cannot_sign_are_ignored(ignored: EventObservation) -> None:
    assert _score(released=[ignored]) == 50.0
    strong = _event(consensus=2.0, previous=2.0, actual=3.0)
    assert _score(released=[ignored, strong]) == _score(released=[strong])


def test_zero_sign_category_is_ignored_not_counted_as_neutral() -> None:
    brent = AssetSpec(
        symbol="BRENT",
        kind="commodity",
        economies=("united_states",),
        signs={"united_states": {"inflation": 0, "growth": 1}},
    )
    growth_beat = _event("united_states", "growth", consensus=2.0, previous=2.0, actual=3.0)
    hot_cpi = _event("united_states", "inflation", consensus=2.0, previous=2.0, actual=3.0)
    assert _score(released=[growth_beat], asset=brent) == _score(
        released=[growth_beat, hot_cpi], asset=brent
    )


def test_importance_weights_the_surprise_average() -> None:
    big_beat = _event(importance=3, consensus=2.0, previous=2.0, actual=3.0)  # s = -0.5
    small_miss = _event(importance=1, consensus=2.0, previous=2.0, actual=1.0)  # s = +0.5
    # weights 1 and 0.25: S = (-0.5 * 1 + 0.5 * 0.25) / 1.25 = -0.3
    assert _score(released=[big_beat, small_miss]) == pytest.approx(50 - 50 * 0.4 * 0.3)


def test_previous_alone_normalises_when_consensus_is_zero() -> None:
    assert _score(released=[_event(consensus=0.0, previous=2.0, actual=1.0)]) == pytest.approx(
        50 - 50 * 0.4 * 0.5
    )


# --- event risk -----------------------------------------------------------------------------


def test_event_risk_saturates_at_the_scale() -> None:
    conviction = [_tag(1)]
    four_high = [_event(importance=3, days_ahead=day) for day in range(4)]
    eight_high = [_event(importance=3, days_ahead=day) for day in range(8)]
    assert _score(tags=conviction, upcoming=four_high) == pytest.approx(50 + 50 * 0.6 * 0.5)
    assert _score(tags=conviction, upcoming=eight_high) == pytest.approx(50 + 50 * 0.6 * 0.5)


def test_event_risk_alone_leaves_50() -> None:
    assert _score(upcoming=[_event(importance=3, days_ahead=1)]) == 50.0


def test_low_importance_events_add_a_quarter_each() -> None:
    conviction = [_tag(1)]
    one_low = [_event(importance=1, days_ahead=1)]  # R = 0.25 / 4 = 0.0625
    assert _score(tags=conviction, upcoming=one_low) == pytest.approx(
        50 + 50 * 0.6 * (1 - 0.5 * 0.0625)
    )


# --- params ---------------------------------------------------------------------------------


def test_params_override_the_defaults() -> None:
    news_only = {"news_weight": 1.0, "surprise_weight": 0.0}
    hot_cpi = _event(consensus=2.0, previous=2.0, actual=3.0)
    assert _score(tags=[_tag(1)], released=[hot_cpi], params=news_only) == 100.0
    no_shrink = {"event_risk_shrink": 0.0}
    heavy = [_event(importance=3, days_ahead=day) for day in range(4)]
    assert _score(tags=[_tag(1)], upcoming=heavy, params=no_shrink) == pytest.approx(80.0)
    slow_decay = {"news_half_life_hours": 1_000_000}
    assert _score(tags=[_tag(1), _tag(-1, age_hours=48)], params=slow_decay) == pytest.approx(
        50.0, abs=0.01
    )


# --- properties -----------------------------------------------------------------------------

headlines = st.builds(
    TaggedHeadline,
    direction=st.sampled_from([-1, 0, 1]),
    confidence=st.floats(0, 1),
    source_weight=st.floats(0, 1),
    published_at=st.datetimes(
        min_value=datetime(2026, 9, 12), max_value=datetime(2026, 9, 15, 8), timezones=st.just(UTC)
    ),
)
released_events = st.builds(
    EventObservation,
    date=st.just(AS_OF),
    country=st.sampled_from(["united_states", "euro_area", "japan"]),
    category=st.sampled_from(["inflation", "employment", "growth", "rates", "other"]),
    importance=st.integers(1, 3),
    consensus=st.none() | st.floats(-10, 10),
    previous=st.none() | st.floats(-10, 10),
    actual=st.none() | st.floats(-10, 10),
)
upcoming_events = st.builds(
    EventObservation,
    date=st.just(AS_OF + 2 * 24 * HOUR),
    country=st.sampled_from(["united_states", "euro_area"]),
    category=st.sampled_from(["inflation", "employment", "growth", "rates"]),
    importance=st.integers(1, 3),
    consensus=st.none(),
    previous=st.none(),
    actual=st.none(),
)
tag_lists = st.lists(headlines, max_size=8)
released_lists = st.lists(released_events, max_size=6)
upcoming_lists = st.lists(upcoming_events, max_size=6)


@settings(max_examples=200)
@given(tag_lists, released_lists, upcoming_lists)
def test_bounded_and_neutral_without_information(tags, released, upcoming) -> None:
    score = _score(tags=tags, released=released, upcoming=upcoming)
    assert 0.0 <= score <= 100.0
    assert _score(upcoming=upcoming) == 50.0


@settings(max_examples=200)
@given(tag_lists, released_lists, upcoming_lists, headlines)
def test_a_bullish_headline_never_lowers_and_a_bearish_never_raises(
    tags, released, upcoming, extra
) -> None:
    base = _score(tags=tags, released=released, upcoming=upcoming)
    bull = replace(extra, direction=1)
    bear = replace(extra, direction=-1)
    assert _score(tags=[*tags, bull], released=released, upcoming=upcoming) >= base - 1e-9
    assert _score(tags=[*tags, bear], released=released, upcoming=upcoming) <= base + 1e-9


@settings(max_examples=200)
@given(tag_lists, released_lists, upcoming_lists)
def test_flipping_every_sign_mirrors_the_score_around_50(tags, released, upcoming) -> None:
    flipped_tags = [replace(tag, direction=-tag.direction) for tag in tags]
    flipped_events = [
        replace(event, actual=2 * event.consensus - event.actual)
        if event.actual is not None and event.consensus is not None
        else event
        for event in released
    ]
    score = _score(tags=tags, released=released, upcoming=upcoming)
    mirror = _score(tags=flipped_tags, released=flipped_events, upcoming=upcoming)
    assert score + mirror == pytest.approx(100.0, abs=1e-6)


@settings(max_examples=200)
@given(tag_lists, released_lists, upcoming_lists)
def test_upcoming_events_only_shrink_toward_50(tags, released, upcoming) -> None:
    calm = _score(tags=tags, released=released)
    busy = _score(tags=tags, released=released, upcoming=upcoming)
    assert abs(busy - 50) <= abs(calm - 50) + 1e-9
    assert (busy - 50) * (calm - 50) >= 0  # never flips the side
