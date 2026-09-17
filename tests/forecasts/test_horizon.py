"""Horizon labels as institutions state them become one target date."""

from datetime import UTC, date, datetime

import pytest

from manc.forecasts.horizon import normalise

PUBLISHED = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("12 months", date(2027, 9, 17)),
        ("12-month", date(2027, 9, 17)),
        ("in 3 months", date(2026, 12, 17)),
        ("6M", date(2027, 3, 17)),
        ("1 year", date(2027, 9, 17)),
        ("two years", date(2028, 9, 17)),
        ("year-end", date(2026, 12, 31)),
        ("end of year", date(2026, 12, 31)),
        ("by year end 2027", date(2027, 12, 31)),
        ("end-2027", date(2027, 12, 31)),
        ("end of 2027", date(2027, 12, 31)),
        ("Q4 2026", date(2026, 12, 31)),
        ("Q1 2027", date(2027, 3, 31)),
        ("4Q26", date(2026, 12, 31)),
        ("2Q27", date(2027, 6, 30)),
        ("Q4", date(2026, 12, 31)),
        ("Q2", date(2027, 6, 30)),
        ("H1 2027", date(2027, 6, 30)),
        ("second half of 2027", date(2027, 12, 31)),
        ("mid-2027", date(2027, 6, 30)),
        ("2027", date(2027, 12, 31)),
        ("2027 average", date(2027, 12, 31)),
        ("March 2027", date(2027, 3, 31)),
        ("end-March 2027", date(2027, 3, 31)),
        ("by June", date(2027, 6, 30)),
        ("by December", date(2026, 12, 31)),
        ("next year", date(2027, 12, 31)),
        ("this year", date(2026, 12, 31)),
        ("2026-12-31", date(2026, 12, 31)),
    ],
)
def test_labels_normalise_to_the_end_of_the_stated_period(label: str, expected: date) -> None:
    assert normalise(label, PUBLISHED) == expected


@pytest.mark.parametrize("label", ["", "soon", "the medium term", "when the Fed cuts", "1999"])
def test_unparseable_labels_are_none(label: str) -> None:
    assert normalise(label, PUBLISHED) is None
