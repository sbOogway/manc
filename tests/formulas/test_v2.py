"""FormulaV2 (blueprint section 9, M6): v1's terms on a -100..100 scale, plus dispersion."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from manc.formulas.contract import AssetSpec, EventObservation, ScoringInputs, TaggedHeadline
from manc.formulas.v2 import FormulaV2

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
BASE = {"standardised_surprise": 0, "decayed_surprise": 0, "novelty_weighting": 0}


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
    past: tuple[float, ...] = (),
) -> EventObservation:
    return EventObservation(
        date=AS_OF + days_ahead * 24 * HOUR,
        country=country,
        category=category,
        importance=importance,
        consensus=consensus,
        previous=previous,
        actual=actual,
        past_surprises=past,
    )


def _inputs(tags=(), released=(), upcoming=(), params=None, asset=EURUSD) -> ScoringInputs:
    return ScoringInputs(
        asset=asset,
        as_of=AS_OF,
        tags=tuple(tags),
        released=tuple(released),
        upcoming=tuple(upcoming),
        params={**BASE, **(params or {})},
    )


def _compute(**kwargs):
    return FormulaV2().compute(_inputs(**kwargs))


def _score(**kwargs) -> float:
    return _compute(**kwargs).score


def test_scale_runs_from_minus_100_to_100_around_0() -> None:
    scale = FormulaV2.scale
    assert (scale.low, scale.high, scale.neutral) == (-100.0, 100.0, 0.0)
    assert scale.edges == (-40.0, -10.0, 10.0, 40.0)


def test_blueprint_worked_example_on_the_new_scale() -> None:
    # v1 gives 49.25: raw = -0.02, shrink 0.75 → v2 gives 100 · -0.02 · 0.75 = -1.5
    tags = [_tag(1, confidence=0.65), _tag(-1, confidence=0.35)]  # N = +0.3
    hot_cpi = _event(consensus=3.0, previous=2.9, actual=4.5)  # s = -0.5 for the euro
    ahead = [
        _event(country="euro_area", category="rates", importance=3, days_ahead=3),
        _event(category="employment", importance=3, days_ahead=4),
    ]
    score = _compute(tags=tags, released=[hot_cpi], upcoming=ahead)
    assert score.formula == "v2"
    assert score.score == pytest.approx(-1.5)
    assert score.components["N"] == pytest.approx(0.3)
    assert score.components["S"] == pytest.approx(-0.5)
    assert score.components["R"] == pytest.approx(0.5)


def test_news_alone_moves_the_score_by_its_weight() -> None:
    assert _score(tags=[_tag(1)]) == pytest.approx(60.0)
    assert _score(tags=[_tag(-1)]) == pytest.approx(-60.0)


def test_full_conviction_reaches_the_ends_of_the_scale() -> None:
    hot = _event(country="euro_area", consensus=1.0, previous=1.0, actual=3.0)  # s = +1
    assert _score(tags=[_tag(1)], released=[hot]) == pytest.approx(100.0)
    cold = _event(country="euro_area", consensus=1.0, previous=1.0, actual=-3.0)
    assert _score(tags=[_tag(-1)], released=[cold]) == pytest.approx(-100.0)


def test_dispersion_is_zero_on_unanimous_tags_and_maximal_on_an_even_split() -> None:
    assert _compute(tags=[_tag(1), _tag(1), _tag(1)]).components["D"] == 0.0
    assert _compute(tags=[_tag(1), _tag(-1)]).components["D"] == pytest.approx(1.0)
    assert _compute().components["D"] == 0.0
    half = _compute(tags=[_tag(1, confidence=0.5), _tag(-1, confidence=0.5)]).components["D"]
    assert half == pytest.approx(0.5)


def test_dispersion_does_not_move_the_score() -> None:
    assert _score(tags=[_tag(1), _tag(-1)]) == 0.0


# --- standardised surprise -------------------------------------------------

STANDARDISED = {"standardised_surprise": 1, "surprise_min_history": 4, "surprise_z_cap": 2.0}
HISTORY_PCT = (0.1, -0.1, 0.2, -0.2)  # sigma 0.158, in percentage points
HISTORY_K = (10.0, -10.0, 20.0, -20.0)  # the same shape in thousands


def _surprise(**kwargs) -> float:
    return _compute(**kwargs).components["S"]


def test_standardised_surprise_gives_the_same_s_for_the_same_z_in_different_units() -> None:
    cpi = _event(country="euro_area", consensus=3.0, actual=3.158, past=HISTORY_PCT)
    claims = _event(
        country="euro_area", category="employment", consensus=200.0, actual=215.8, past=HISTORY_K
    )
    assert _surprise(released=[cpi], params=STANDARDISED) == pytest.approx(0.5, abs=1e-3)
    assert _surprise(released=[claims], params=STANDARDISED) == pytest.approx(0.5, abs=1e-3)


def test_standardised_surprise_clips_at_the_z_cap() -> None:
    huge = _event(country="euro_area", consensus=3.0, actual=9.0, past=HISTORY_PCT)
    assert _surprise(released=[huge], params=STANDARDISED) == 1.0


def test_standardised_surprise_falls_back_below_min_history_or_with_flat_history() -> None:
    short = _event(country="euro_area", consensus=3.0, previous=2.9, actual=4.5, past=(0.1, -0.1))
    flat = _event(country="euro_area", consensus=3.0, previous=2.9, actual=4.5, past=(0.0,) * 6)
    v1_like = _surprise(released=[short])  # switch off: the v1 normaliser
    assert v1_like == pytest.approx(0.5)
    assert _surprise(released=[short], params=STANDARDISED) == pytest.approx(v1_like)
    assert _surprise(released=[flat], params=STANDARDISED) == pytest.approx(v1_like)


# --- decayed surprise window ----------------------------------------------

DECAYED = {"decayed_surprise": 1, "surprise_half_life_days": 14}


def test_decayed_surprise_equals_the_hard_window_at_age_zero() -> None:
    fresh = _event(country="euro_area", consensus=1.0, previous=1.0, actual=1.5)
    assert _surprise(released=[fresh], params=DECAYED) == pytest.approx(_surprise(released=[fresh]))


def test_an_older_surprise_loses_to_a_fresh_opposite_one() -> None:
    fresh_beat = _event(country="euro_area", consensus=1.0, previous=1.0, actual=1.5)
    old_miss = _event(country="euro_area", consensus=1.0, previous=1.0, actual=0.5, days_ahead=-14)
    assert _surprise(released=[fresh_beat, old_miss]) == pytest.approx(0.0)  # hard window: tie
    decayed = _surprise(released=[fresh_beat, old_miss], params=DECAYED)
    assert decayed == pytest.approx(0.5 * (1 - 0.5) / (1 + 0.5))  # weights 1 and 0.5


def test_decay_is_monotone_in_age() -> None:
    def with_age(days: float) -> float:
        old = _event(country="euro_area", consensus=1.0, previous=1.0, actual=0.5, days_ahead=-days)
        fresh = _event(country="euro_area", consensus=1.0, previous=1.0, actual=1.5)
        return _surprise(released=[fresh, old], params=DECAYED)

    assert with_age(0) < with_age(7) < with_age(28) < with_age(90)


def test_v2_declares_the_longer_released_window() -> None:
    assert FormulaV2.windows == {"released_days": 90}


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
    date=st.floats(0, 90).map(lambda days: AS_OF - days * 24 * HOUR),
    country=st.sampled_from(["united_states", "euro_area", "japan"]),
    category=st.sampled_from(["inflation", "employment", "growth", "rates", "other"]),
    importance=st.integers(1, 3),
    consensus=st.none() | st.floats(-10, 10),
    previous=st.none() | st.floats(-10, 10),
    actual=st.none() | st.floats(-10, 10),
    past_surprises=st.lists(st.floats(-5, 5), max_size=10).map(tuple),
)
ALL_ON = {"standardised_surprise": 1, "decayed_surprise": 1}
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
@given(tag_lists, released_lists, upcoming_lists, st.booleans())
def test_bounded_and_neutral_without_information(tags, released, upcoming, switches) -> None:
    params = ALL_ON if switches else {}
    score = _score(tags=tags, released=released, upcoming=upcoming, params=params)
    assert -100.0 <= score <= 100.0
    assert _score(upcoming=upcoming, params=params) == 0.0


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
@given(tag_lists, released_lists, upcoming_lists, st.booleans())
def test_flipping_every_sign_mirrors_the_score_around_0(tags, released, upcoming, switches) -> None:
    params = ALL_ON if switches else {}
    flipped_tags = [replace(tag, direction=-tag.direction) for tag in tags]
    flipped_events = [
        replace(event, actual=2 * event.consensus - event.actual)
        if event.actual is not None and event.consensus is not None
        else event
        for event in released
    ]
    score = _score(tags=tags, released=released, upcoming=upcoming, params=params)
    mirror = _score(tags=flipped_tags, released=flipped_events, upcoming=upcoming, params=params)
    assert score + mirror == pytest.approx(0.0, abs=1e-6)


@settings(max_examples=200)
@given(tag_lists, released_lists, upcoming_lists)
def test_upcoming_events_only_shrink_toward_0(tags, released, upcoming) -> None:
    calm = _score(tags=tags, released=released)
    busy = _score(tags=tags, released=released, upcoming=upcoming)
    assert abs(busy) <= abs(calm) + 1e-9
    assert busy * calm >= 0
