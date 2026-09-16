"""Empty providers satisfy their Protocols and return nothing."""

from datetime import UTC, date, datetime

from manc.analysis.empty import EmptyAnalyzer
from manc.analysis.interface import Analyzer
from manc.calendar.empty import EmptyCalendar
from manc.calendar.interface import CalendarProvider
from manc.news.empty import EmptyNews
from manc.news.interface import NewsProvider


def test_empty_providers() -> None:
    assert isinstance(EmptyCalendar(), CalendarProvider)
    assert isinstance(EmptyNews(), NewsProvider)
    assert isinstance(EmptyAnalyzer(), Analyzer)
    assert EmptyCalendar().fetch(date(2026, 9, 1), date(2026, 9, 30)) == []
    assert EmptyNews().fetch(datetime(2026, 9, 1, tzinfo=UTC)) == []
    assert EmptyAnalyzer().tag([], []) == []
