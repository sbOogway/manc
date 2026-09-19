"""The formula contract: registry lookup, bounds, neutrality on empty inputs."""

from datetime import UTC, date, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from manc.formulas.contract import (
    AssetSpec,
    EventObservation,
    IndexFormula,
    ScoringInputs,
    TaggedHeadline,
)
from manc.formulas.registry import formula_names, get_formula

AS_OF = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
ASSET = AssetSpec(symbol="EURUSD", kind="forex", economies=("euro_area", "united_states"))


def test_index_score_report_defaults_empty_and_can_be_attached() -> None:
    from dataclasses import replace

    score = get_formula("v1").compute(
        ScoringInputs(asset=ASSET, as_of=AS_OF, tags=(), released=(), upcoming=(), params={})
    )
    assert score.report_md == ""
    assert replace(score, report_md="# EURUSD").report_md == "# EURUSD"


def test_registry_returns_v1() -> None:
    formula = get_formula("v1")
    assert isinstance(formula, IndexFormula)
    assert formula.name == "v1"


def test_registry_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown formula"):
        get_formula("nope")


def test_v1_is_exactly_50_on_empty_inputs() -> None:
    inputs = ScoringInputs(asset=ASSET, as_of=AS_OF, tags=(), released=(), upcoming=(), params={})
    score = get_formula("v1").compute(inputs)
    assert score.score == 50.0
    assert score.asset == "EURUSD"
    assert score.date == date(2026, 9, 15)
    assert score.formula == "v1"
    assert score.n_news == 0 and score.n_events == 0


headlines = st.builds(
    TaggedHeadline,
    direction=st.sampled_from([-1, 0, 1]),
    confidence=st.floats(0, 1),
    source_weight=st.floats(0, 1),
    published_at=st.datetimes(
        min_value=datetime(2026, 9, 12), max_value=datetime(2026, 9, 15), timezones=st.just(UTC)
    ),
)
events = st.builds(
    EventObservation,
    date=st.datetimes(
        min_value=datetime(2026, 9, 8), max_value=datetime(2026, 9, 22), timezones=st.just(UTC)
    ),
    country=st.sampled_from(["united_states", "euro_area"]),
    category=st.sampled_from(["inflation", "employment", "growth", "rates"]),
    importance=st.integers(1, 3),
    consensus=st.none() | st.floats(-10, 10),
    previous=st.none() | st.floats(-10, 10),
    actual=st.none() | st.floats(-10, 10),
)


@given(st.tuples(headlines).map(tuple), st.lists(events, max_size=5), st.lists(events, max_size=5))
def test_v1_stays_within_bounds(tags, released, upcoming) -> None:
    inputs = ScoringInputs(
        asset=ASSET,
        as_of=AS_OF,
        tags=tuple(tags),
        released=tuple(released),
        upcoming=tuple(upcoming),
        params={},
    )
    score = get_formula("v1").compute(inputs)
    assert 0.0 <= score.score <= 100.0


def test_formula_names_lists_every_version() -> None:
    assert formula_names() == ["v1", "v2"]


@pytest.mark.parametrize("name", ["v1", "v2"])
def test_every_formula_declares_an_ordered_scale(name: str) -> None:
    scale = get_formula(name).scale
    assert scale.low < scale.neutral < scale.high
    assert list(scale.edges) == sorted(scale.edges)
    assert scale.low < scale.edges[0] and scale.edges[-1] < scale.high
    assert scale.band(scale.low) == "headwind"
    assert scale.band(scale.neutral) == "neutral"
    assert scale.band(scale.high) == "tailwind"


@pytest.mark.parametrize("name", ["v1", "v2"])
def test_every_formula_declares_its_window_overrides(name: str) -> None:
    windows = get_formula(name).windows
    assert all(isinstance(value, int) and value > 0 for value in windows.values())


def test_v1_scale_is_the_section_5_scale() -> None:
    scale = get_formula("v1").scale
    assert (scale.low, scale.neutral, scale.high) == (0.0, 50.0, 100.0)
    assert [scale.band(value) for value in (29.9, 30, 44.9, 45, 54.9, 55, 69.9, 70)] == [
        "headwind",
        "lean_against",
        "lean_against",
        "neutral",
        "neutral",
        "lean_for",
        "lean_for",
        "tailwind",
    ]
