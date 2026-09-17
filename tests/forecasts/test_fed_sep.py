"""Fed SEP publisher (blueprint section 4): medians per projection year from the accessible page."""

import logging
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
import respx

from manc.forecasts.fed_sep import CALENDAR_URL, FedSep, parse_medians, table_url
from manc.forecasts.interface import ForecastProvider
from manc.models import ForecastMacro

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "forecasts"
SEPTEMBER = date(2026, 9, 16)
RELEASED_AT = datetime(2026, 9, 16, 18, 0, tzinfo=UTC)  # 14:00 Eastern, with the statement
EARLY_2026 = datetime(2026, 1, 1, tzinfo=UTC)


def serve_calendar() -> respx.Route:
    body = (FIXTURES / "fomccalendars.html").read_bytes()
    return respx.get(CALENDAR_URL).mock(return_value=httpx.Response(200, content=body))


def serve_table(day: date, **response_kwargs: object) -> respx.Route:
    if not response_kwargs:
        body = (FIXTURES / f"fomcprojtabl{day:%Y%m%d}.html").read_bytes()
        response_kwargs = {"status_code": 200, "content": body}
    return respx.get(table_url(day)).mock(return_value=httpx.Response(**response_kwargs))


def test_satisfies_protocol() -> None:
    assert isinstance(FedSep(), ForecastProvider)


@respx.mock
def test_september_2026_medians_become_macro_forecasts() -> None:
    serve_calendar()
    serve_table(SEPTEMBER)

    forecasts = FedSep().fetch(datetime(2026, 9, 15, tzinfo=UTC))

    assert forecasts.asset == ()
    by_key = {(row.metric, row.horizon_label): row.value for row in forecasts.macro}
    assert by_key == {
        ("gdp", "2026"): 2.3,
        ("gdp", "2027"): 2.4,
        ("gdp", "2028"): 2.2,
        ("gdp", "2029"): 2.1,
        ("unemployment", "2026"): 4.1,
        ("unemployment", "2027"): 4.1,
        ("unemployment", "2028"): 4.1,
        ("unemployment", "2029"): 4.1,
        ("pce", "2026"): 3.7,
        ("pce", "2027"): 2.3,
        ("pce", "2028"): 2.1,
        ("pce", "2029"): 2.0,
        ("policy_rate", "2026"): 4.1,
        ("policy_rate", "2027"): 4.1,
        ("policy_rate", "2028"): 3.9,
        ("policy_rate", "2029"): 3.6,
    }
    rate_2027 = next(
        row for row in forecasts.macro if (row.metric, row.horizon_label) == ("policy_rate", "2027")
    )
    assert rate_2027 == ForecastMacro.new(
        institution="fed",
        economy="united_states",
        metric="policy_rate",
        horizon_date=date(2027, 12, 31),
        horizon_label="2027",
        value=4.1,
        published_at=RELEASED_AT,
        source_url=table_url(SEPTEMBER),
        source_kind="structured",
        confidence=1.0,
    )


@respx.mock
def test_since_selects_the_releases_to_fetch() -> None:
    serve_calendar()
    march = serve_table(date(2026, 3, 18), status_code=404)
    june = serve_table(date(2026, 6, 17), status_code=404)
    september = serve_table(SEPTEMBER)

    FedSep().fetch(datetime(2026, 6, 17, tzinfo=UTC))

    assert not march.called
    assert june.called and september.called


@respx.mock
def test_nothing_released_since_means_no_table_request() -> None:
    serve_calendar()
    september = serve_table(SEPTEMBER)

    assert FedSep().fetch(datetime(2026, 9, 17, tzinfo=UTC)).macro == ()
    assert not september.called


@respx.mock
def test_calendar_failure_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    respx.get(CALENDAR_URL).mock(return_value=httpx.Response(503))

    with caplog.at_level(logging.WARNING, logger="manc.forecasts"):
        forecasts = FedSep().fetch(EARLY_2026)

    assert forecasts.macro == ()
    assert "fed sep" in caplog.text and "503" in caplog.text


@respx.mock
def test_one_failing_table_keeps_the_others(caplog: pytest.LogCaptureFixture) -> None:
    serve_calendar()
    serve_table(date(2026, 6, 17), status_code=500)
    serve_table(SEPTEMBER)

    with caplog.at_level(logging.WARNING, logger="manc.forecasts"):
        forecasts = FedSep().fetch(datetime(2026, 6, 1, tzinfo=UTC))

    assert {row.published_at for row in forecasts.macro} == {RELEASED_AT}
    assert "2026-06-17" in caplog.text and "500" in caplog.text


@respx.mock
def test_page_without_the_projection_table_is_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    serve_calendar()
    serve_table(SEPTEMBER, status_code=200, content=b"<html><body>moved</body></html>")

    with caplog.at_level(logging.WARNING, logger="manc.forecasts"):
        forecasts = FedSep().fetch(datetime(2026, 9, 15, tzinfo=UTC))

    assert forecasts.macro == ()
    assert "no projection table" in caplog.text


def test_parse_skips_tables_without_a_median_header() -> None:
    page = """
    <table><tr><th>Year</th><th>Actual</th></tr><tr><td>2025</td><td>2.0</td></tr></table>
    <table>
      <tr><th>Variable</th><th>Median<sup>1</sup></th><th>Range</th></tr>
      <tr><th>2026</th><th>Longer run</th><th>2026</th><th>Longer run</th></tr>
      <tr><td>Change in real GDP</td><td>1.9</td><td>2.0</td><td>1.5-2.2</td><td></td></tr>
      <tr><td>Core PCE inflation<sup>4</sup></td><td>2.6</td><td></td><td>2.4-2.8</td></tr>
    </table>
    """

    assert parse_medians(page) == [("gdp", 2026, 1.9)]
