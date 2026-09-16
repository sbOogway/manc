"""Offline stand-in until the RSS provider lands (M2)."""

from datetime import datetime

from manc.models import NewsItem


class EmptyNews:
    def fetch(self, since: datetime) -> list[NewsItem]:
        return []
