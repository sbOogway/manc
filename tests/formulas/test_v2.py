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
    assert -100.0 <= score <= 100.0
    assert _score(upcoming=upcoming) == 0.0


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
def test_flipping_every_sign_mirrors_the_score_around_0(tags, released, upcoming) -> None:
    flipped_tags = [replace(tag, direction=-tag.direction) for tag in tags]
    flipped_events = [
        replace(event, actual=2 * event.consensus - event.actual)
        if event.actual is not None and event.consensus is not None
        else event
        for event in released
    ]
    score = _score(tags=tags, released=released, upcoming=upcoming)
    mirror = _score(tags=flipped_tags, released=flipped_events, upcoming=upcoming)
    assert score + mirror == pytest.approx(0.0, abs=1e-6)


@settings(max_examples=200)
@given(tag_lists, released_lists, upcoming_lists)
def test_upcoming_events_only_shrink_toward_0(tags, released, upcoming) -> None:
    calm = _score(tags=tags, released=released)
    busy = _score(tags=tags, released=released, upcoming=upcoming)
    assert abs(busy) <= abs(calm) + 1e-9
    assert busy * calm >= 0
