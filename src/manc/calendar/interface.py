from datetime import date
from typing import Protocol, runtime_checkable

from manc.models import CalendarEvent


@runtime_checkable
class CalendarProvider(Protocol):
    def fetch(self, start: date, end: date) -> list[CalendarEvent]: ...
