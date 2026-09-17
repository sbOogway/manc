"""Empty providers satisfy their Protocols and return nothing."""

from datetime import UTC, date, datetime

from manc.calendar.empty import EmptyCalendar
from manc.calendar.interface import CalendarProvider
from manc.forecasts.empty import EmptyForecasts
from manc.forecasts.interface import ForecastProvider
from manc.formulas.contract import AssetSpec
from manc.models import Forecasts
from manc.news.empty import EmptyNews
from manc.news.interface import NewsProvider
from manc.spot.empty import EmptySpot
from manc.spot.interface import SpotProvider


def test_empty_providers() -> None:
    assert isinstance(EmptyCalendar(), CalendarProvider)
    assert isinstance(EmptyNews(), NewsProvider)
    assert isinstance(EmptyForecasts(), ForecastProvider)
    assert isinstance(EmptySpot(), SpotProvider)
    assert EmptyCalendar().fetch(date(2026, 9, 1), date(2026, 9, 30)) == []
    assert EmptyNews().fetch(datetime(2026, 9, 1, tzinfo=UTC)) == []
    assert EmptyForecasts().fetch(datetime(2026, 9, 1, tzinfo=UTC)) == Forecasts()
    asset = AssetSpec(symbol="EURUSD", kind="forex", economies=("euro_area",))
    assert EmptySpot().fetch([asset], date(2026, 9, 1)) == []
