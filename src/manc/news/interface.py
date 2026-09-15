from datetime import datetime
from typing import Protocol, runtime_checkable

from manc.models import NewsItem


@runtime_checkable
class NewsProvider(Protocol):
    def fetch(self, since: datetime) -> list[NewsItem]: ...
