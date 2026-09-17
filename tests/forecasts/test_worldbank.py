"""World Bank Commodity Markets Outlook (blueprint section 4): gold averages from the xlsx."""

import logging
from datetime import UTC, date, datetime
from io import BytesIO
from pathlib import Path

import httpx
import openpyxl
import pytest
import respx

from manc.forecasts.interface import ForecastProvider
from manc.forecasts.worldbank import OUTLOOK_URL, WorldBankOutlook, parse_workbook
from manc.models import ForecastAsset

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "forecasts"
WORKBOOK_URL = (
    "https://thedocs.worldbank.org/en/doc/f3138644a1e8e2bb631399ae11d6c408-0050012026"
    "/related/CMO-April-2026-Forecasts.xlsx"
)
RELEASED_AT = datetime(2026, 4, 28, tzinfo=UTC)


def serve_page(body: bytes | None = None) -> respx.Route:
    if body is None:
        body = (FIXTURES / "commodity-markets.html").read_bytes()
    return respx.get(OUTLOOK_URL).mock(return_value=httpx.Response(200, content=body))


def serve_workbook(**response_kwargs: object) -> respx.Route:
    if not response_kwargs:
        body = (FIXTURES / "CMO-April-2026-Forecasts.xlsx").read_bytes()
        response_kwargs = {"status_code": 200, "content": body}
    return respx.get(WORKBOOK_URL).mock(return_value=httpx.Response(**response_kwargs))


def test_satisfies_protocol() -> None:
    assert isinstance(WorldBankOutlook(), ForecastProvider)


@respx.mock
def test_april_2026_gold_averages_become_asset_forecasts() -> None:
    serve_page()
    serve_workbook()

    forecasts = WorldBankOutlook().fetch(datetime(2026, 1, 1, tzinfo=UTC))

    assert forecasts.macro == ()
    assert forecasts.asset == (
        ForecastAsset.new(
            institution="world_bank",
            asset="XAUUSD",
            horizon_date=date(2026, 12, 31),
            horizon_label="2026 average",
            value=4700.0,
            published_at=RELEASED_AT,
            source_url=WORKBOOK_URL,
            source_kind="structured",
            confidence=1.0,
        ),
        ForecastAsset.new(
            institution="world_bank",
            asset="XAUUSD",
            horizon_date=date(2027, 12, 31),
            horizon_label="2027 average",
            value=4300.0,
            published_at=RELEASED_AT,
            source_url=WORKBOOK_URL,
            source_kind="structured",
            confidence=1.0,
        ),
    )


@respx.mock
def test_edition_released_before_since_is_skipped() -> None:
    serve_page()
    serve_workbook()  # the release date is inside the workbook, so it is always read

    assert WorldBankOutlook().fetch(datetime(2026, 4, 29, tzinfo=UTC)).asset == ()


@respx.mock
def test_release_day_itself_counts() -> None:
    serve_page()
    serve_workbook()

    assert len(WorldBankOutlook().fetch(datetime(2026, 4, 28, 12, tzinfo=UTC)).asset) == 2


@respx.mock
def test_page_failure_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    respx.get(OUTLOOK_URL).mock(return_value=httpx.Response(503))

    with caplog.at_level(logging.WARNING, logger="manc.forecasts"):
        forecasts = WorldBankOutlook().fetch(datetime(2026, 1, 1, tzinfo=UTC))

    assert forecasts.asset == ()
    assert "world bank" in caplog.text and "503" in caplog.text


@respx.mock
def test_page_without_a_forecasts_link_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    serve_page(b"<html><body>Commodity Markets</body></html>")

    with caplog.at_level(logging.WARNING, logger="manc.forecasts"):
        forecasts = WorldBankOutlook().fetch(datetime(2026, 1, 1, tzinfo=UTC))

    assert forecasts.asset == ()
    assert "no forecasts link" in caplog.text


@respx.mock
def test_workbook_failure_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    serve_page()
    serve_workbook(status_code=404)

    with caplog.at_level(logging.WARNING, logger="manc.forecasts"):
        forecasts = WorldBankOutlook().fetch(datetime(2026, 1, 1, tzinfo=UTC))

    assert forecasts.asset == ()
    assert "404" in caplog.text


@respx.mock
def test_unreadable_workbook_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    serve_page()
    serve_workbook(status_code=200, content=b"not a workbook")

    with caplog.at_level(logging.WARNING, logger="manc.forecasts"):
        forecasts = WorldBankOutlook().fetch(datetime(2026, 1, 1, tzinfo=UTC))

    assert forecasts.asset == ()
    assert "unreadable" in caplog.text


def workbook(*rows: list[object]) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Forecast"
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_parse_takes_the_first_column_of_each_forecast_year() -> None:
    content = workbook(
        ["TABLE 1", None, "Released: October 28, 2026"],
        ["Commodity", "Unit", 2025, "2026f", "2027f", "2026f", "2027f"],
        ["Crude oil, Brent", "$/bbl", 69, 86, 70, 24.6, -18.6],
        ["Gold", "$/toz", 3442, 4700, 4300, 36.6, -8.5],
        ["Silver", "$/toz", 39.8, 70, 65, 75.9, -7.1],
    )

    assert parse_workbook(content) == (
        date(2026, 10, 28),
        [("XAUUSD", 2026, 4700.0), ("XAUUSD", 2027, 4300.0)],
    )


def test_parse_rejects_a_sheet_without_a_release_date() -> None:
    with pytest.raises(ValueError, match="release date"):
        parse_workbook(workbook(["Commodity", "Unit", "2026f"], ["Gold", "$/toz", 4700]))


def test_parse_rejects_a_sheet_without_forecast_years() -> None:
    with pytest.raises(ValueError, match="forecast-year"):
        parse_workbook(workbook(["Released: April 28, 2026"], ["Gold", "$/toz", 4700]))
