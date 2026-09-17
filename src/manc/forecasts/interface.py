from datetime import datetime
from typing import Protocol, runtime_checkable

from manc.models import Forecasts


@runtime_checkable
class ForecastProvider(Protocol):
    def fetch(self, since: datetime) -> Forecasts: ...
