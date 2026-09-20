"""Nasdaq economic calendar (blueprint section 4), called directly over httpx.

Quirks of the endpoint, verified 2026-09-16: `date=D` returns the events of the previous day,
the `gmt` column is in fact US Eastern time, blanks come as "&nbsp;" or " ", and values are
strings such as "1,774K", "5.4%" or "310.70B". There is no importance field, so category and
importance come from the regex maps in src/manc/config/calendar.yaml.
"""

import logging
import re
from datetime import UTC, date, datetime, timedelta
from hashlib import sha1
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from manc.config import CalendarConfig
from manc.http import Client, gather
from manc.models import CalendarEvent

log = logging.getLogger(__name__)

ENDPOINT = "https://api.nasdaq.com/api/calendar/economicevents"
EASTERN = ZoneInfo("America/New_York")
_SCALE = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
_NUMBER = re.compile(r"^(-?\d+(?:\.\d+)?)([KMBT])?%?$")
_CLOCK = re.compile(r"^\d{1,2}:\d{2}$")


class NasdaqCalendar:
    def __init__(self, config: CalendarConfig, client: httpx.Client | None = None) -> None:
        self.config = config
        self.client = client or Client()

    def fetch(self, start: date, end: date) -> list[CalendarEvent]:
        """Events for every day in [start, end], sorted by time; a failing day is skipped."""
        days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
        events = [event for found in gather(self._fetch_day, days) for event in found]
        return sorted(events, key=lambda event: event.date)

    def _fetch_day(self, day: date) -> list[CalendarEvent]:
        requested = day + timedelta(days=1)  # the endpoint returns the previous day's events
        try:
            response = self.client.get(ENDPOINT, params={"date": requested.isoformat()})
            response.raise_for_status()
            rows = (response.json().get("data") or {}).get("rows") or []
        except (httpx.HTTPError, ValueError) as error:
            log.warning("calendar %s skipped: %s", day, error)
            return []
        seen: dict[tuple[str, str], int] = {}
        events = []
        for row in rows:
            country = self.config.country(row.get("country", ""))
            name = row.get("eventName", "").strip()
            ordinal = seen[country, name] = seen.get((country, name), -1) + 1
            events.append(self._to_event(day, country, name, ordinal, row))
        log.debug("calendar %s: %d events", day, len(events))
        return events

    def _to_event(
        self, day: date, country: str, name: str, ordinal: int, row: dict[str, Any]
    ) -> CalendarEvent:
        return CalendarEvent(
            id=sha1(f"{day.isoformat()}|{country}|{name}|{ordinal}".encode()).hexdigest(),
            date=_event_time(day, row.get("gmt", "")),
            country=country,
            event=name,
            category=self.config.category(name),
            importance=self.config.importance(name),
            consensus=parse_value(row.get("consensus", "")),
            previous=parse_value(row.get("previous", "")),
            actual=parse_value(row.get("actual", "")),
        )


def _event_time(day: date, clock: str) -> datetime:
    """Eastern wall-clock time to UTC; "All Day", "Tentative" and "24H" become midnight."""
    hour, minute = map(int, clock.split(":")) if _CLOCK.match(clock.strip()) else (0, 0)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=EASTERN).astimezone(UTC)


def parse_value(raw: str | None) -> float | None:
    """ "1,774K" -> 1774000.0, "4.1%" -> 4.1, blanks and non-numbers -> None."""
    cleaned = (raw or "").replace("&nbsp;", "").replace(",", "").strip()
    match = _NUMBER.match(cleaned)
    if match is None:
        return None
    number, suffix = match.groups()
    return float(number) * _SCALE.get(suffix or "", 1.0)
