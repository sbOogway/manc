"""Offline stand-in until the OpenBB provider lands (M2)."""

from datetime import date

from manc.models import CalendarEvent


class EmptyCalendar:
    def fetch(self, start: date, end: date) -> list[CalendarEvent]:
        return []
