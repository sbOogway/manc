"""Offline stand-in until the extractor and the publishers land (M2)."""

from datetime import datetime

from manc.models import Forecasts


class EmptyForecasts:
    def fetch(self, since: datetime) -> Forecasts:
        return Forecasts()
