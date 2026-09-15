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
from manc.formulas.registry import get_formula

AS_OF = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)
ASSET = AssetSpec(symbol="EURUSD", kind="forex", economies=("euro_area", "united_states"))


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
