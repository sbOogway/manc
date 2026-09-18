"""Nasdaq calendar provider (blueprint section 4): one request per day, D+1 offset, ET -> UTC."""

import json
import logging
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from manc.calendar.interface import CalendarProvider
from manc.calendar.nasdaq import NasdaqCalendar, parse_value
from manc.config import load_config

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "calendar"
CALENDAR = load_config().calendar
NO_RECORD = json.loads((FIXTURES / "2026-09-06.json").read_text())


def endpoint(day: str) -> str:
    return f"https://api.nasdaq.com/api/calendar/economicevents?date={day}"


def serve(day: str, body: dict | None = None, **response_kwargs: object) -> respx.Route:
    if body is None and not response_kwargs:
        body = json.loads((FIXTURES / f"{day}.json").read_text())
    if body is not None:
        return respx.get(endpoint(day)).mock(return_value=httpx.Response(200, json=body))
    return respx.get(endpoint(day)).mock(return_value=httpx.Response(**response_kwargs))


def test_satisfies_protocol() -> None:
    assert isinstance(NasdaqCalendar(CALENDAR), CalendarProvider)


@respx.mock
def test_friday_window_requests_saturday_and_maps_payrolls() -> None:
    route = serve("2026-09-05")

    events = NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 4), date(2026, 9, 4))

    assert route.called
    payrolls = next(event for event in events if event.event == "Nonfarm Payrolls")
    assert payrolls.date == datetime(2026, 9, 4, 12, 30, tzinfo=UTC)  # 08:30 EDT
    assert payrolls.country == "united_states"
    assert payrolls.category == "employment"
    assert payrolls.importance == 3
    assert (payrolls.actual, payrolls.consensus, payrolls.previous) == (
        162_000.0,
        55_000.0,
        21_000.0,
    )
    assert payrolls.released


@respx.mock
def test_events_are_sorted_by_time_and_carry_every_country() -> None:
    serve("2026-09-05")

    events = NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 4), date(2026, 9, 4))

    assert len(events) == 55
    assert [event.date for event in events] == sorted(event.date for event in events)
    assert "euro_area" in {event.country for event in events}
    assert "united_kingdom" in {event.country for event in events}


@respx.mock
def test_same_name_rows_on_one_day_keep_distinct_ids() -> None:
    serve("2026-09-17")

    events = NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 16), date(2026, 9, 16))

    core_cpi = [
        event for event in events if event.event == "Core CPI" and event.country == "united_kingdom"
    ]
    assert len(core_cpi) == 2
    assert len({event.id for event in core_cpi}) == 2
    assert len({event.id for event in events}) == len(events)


@respx.mock
def test_ids_are_stable_across_fetches() -> None:
    serve("2026-09-17")

    first = NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 16), date(2026, 9, 16))
    second = NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 16), date(2026, 9, 16))

    assert [event.id for event in first] == [event.id for event in second]


@respx.mock
def test_unreleased_event_has_no_actual() -> None:
    serve("2026-09-17")

    events = NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 16), date(2026, 9, 16))

    decision = next(event for event in events if event.event == "Fed Interest Rate Decision")
    assert decision.actual is None
    assert not decision.released
    assert decision.category == "rates"
    assert decision.importance == 3
    assert decision.date == datetime(2026, 9, 16, 18, 0, tzinfo=UTC)  # 14:00 EDT


@respx.mock
def test_no_record_day_yields_nothing() -> None:
    serve("2026-09-06", NO_RECORD)

    assert NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 5), date(2026, 9, 5)) == []


@respx.mock
def test_window_covers_every_day_and_merges() -> None:
    serve("2026-09-05")
    serve("2026-09-06", NO_RECORD)
    serve("2026-09-07", NO_RECORD)

    events = NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 4), date(2026, 9, 6))

    assert len(events) == 55
    assert respx.calls.call_count == 3


@respx.mock
def test_http_error_on_one_day_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    serve("2026-09-05")
    serve("2026-09-06", status_code=403)

    with caplog.at_level(logging.WARNING, logger="manc.calendar.nasdaq"):
        events = NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 4), date(2026, 9, 5))

    assert len(events) == 55
    assert any("2026-09-05" in record.message for record in caplog.records)


@respx.mock
def test_connection_error_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    respx.get(endpoint("2026-09-05")).mock(side_effect=httpx.ConnectTimeout("slow"))

    with caplog.at_level(logging.WARNING, logger="manc.calendar.nasdaq"):
        assert NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 4), date(2026, 9, 4)) == []

    assert any("2026-09-04" in record.message for record in caplog.records)


@respx.mock
def test_all_day_and_tentative_times_are_midnight_eastern() -> None:
    rows = [
        {
            "gmt": "All Day",
            "country": "United States",
            "eventName": "Holiday",
            "actual": "&nbsp;",
            "previous": " ",
            "consensus": " ",
            "description": "",
        },
        {
            "gmt": "Tentative",
            "country": "China",
            "eventName": "New Loans",
            "actual": " ",
            "previous": "1,200.0B",
            "consensus": " ",
            "description": "",
        },
        {
            "gmt": "24H",
            "country": "Japan",
            "eventName": "BoJ Meeting",
            "actual": " ",
            "previous": " ",
            "consensus": " ",
            "description": "",
        },
    ]
    serve("2026-09-05", {"data": {"rows": rows}})

    events = NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 4), date(2026, 9, 4))

    assert {event.date for event in events} == {datetime(2026, 9, 4, 4, 0, tzinfo=UTC)}  # 00:00 EDT
    loans = next(event for event in events if event.event == "New Loans")
    assert loans.actual is None
    assert loans.previous == 1_200_000_000_000.0
    assert loans.country == "china"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("162K", 162_000.0),
        ("1,774K", 1_774_000.0),
        ("4.1%", 4.1),
        ("-0.7%", -0.7),
        ("310.70B", 310_700_000_000.0),
        ("2.5M", 2_500_000.0),
        ("52.881K", 52_881.0),
        ("7.39", 7.39),
        ("&nbsp;", None),
        (" ", None),
        ("", None),
        ("n/a", None),
    ],
)
def test_parse_value(raw: str, expected: float | None) -> None:
    assert parse_value(raw) == expected


@pytest.mark.live
def test_live_recent_friday_has_a_jobs_release() -> None:
    today = date.today()
    friday = today - timedelta(days=(today.weekday() - 4) % 7 or 7)
    events = NasdaqCalendar(CALENDAR).fetch(friday, friday)

    assert events
    assert any(
        event.country == "united_states" and event.category == "employment" for event in events
    )


@respx.mock
def test_days_are_fetched_at_the_same_time() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        time.sleep(0.2)
        return httpx.Response(200, json={"data": {"rows": []}})

    respx.get(url__startswith="https://api.nasdaq.com/api/calendar/economicevents").mock(
        side_effect=slow
    )
    started = time.perf_counter()
    NasdaqCalendar(CALENDAR).fetch(date(2026, 9, 1), date(2026, 9, 6))
    assert time.perf_counter() - started < 0.2 * 6 / 2
