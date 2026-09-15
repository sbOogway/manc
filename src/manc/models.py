"""Domain value objects shared by every module (blueprint section 3).

Score-side types (AssetSpec, IndexScore, ...) live in manc.formulas.contract so the
formula package stays free of app imports; they are re-exported here for convenience.
"""

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha1

from manc.formulas.contract import AssetSpec, IndexScore

__all__ = ["AssetSpec", "CalendarEvent", "IndexScore", "NewsItem", "NewsTag"]


@dataclass(frozen=True)
class CalendarEvent:
    id: str  # provider id or hash(date, country, event)
    date: datetime  # UTC
    country: str  # "united_states"
    event: str  # "Consumer Price Index (YoY)"
    category: str  # inflation | employment | growth | rates | other
    importance: int  # 1 low, 2 medium, 3 high
    consensus: float | None
    previous: float | None
    actual: float | None

    @property
    def released(self) -> bool:
        return self.actual is not None


@dataclass(frozen=True)
class NewsItem:
    id: str  # sha1(url)
    source: str  # "reuters", "cnbc", "ecb"
    title: str
    url: str
    published_at: datetime
    summary: str = ""  # feed summary, HTML stripped

    @classmethod
    def from_feed(
        cls, *, source: str, title: str, url: str, published_at: datetime, summary: str = ""
    ) -> "NewsItem":
        return cls(
            id=sha1(url.encode()).hexdigest(),
            source=source,
            title=title,
            url=url,
            published_at=published_at,
            summary=summary,
        )


@dataclass(frozen=True)
class NewsTag:
    news_id: str
    asset: str
    direction: int  # -1 bearish, 0 neutral/irrelevant, +1 bullish
    confidence: float  # 0..1

    def __post_init__(self) -> None:
        if self.direction not in (-1, 0, 1):
            raise ValueError(f"direction must be -1, 0 or 1, got {self.direction}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within 0..1, got {self.confidence}")
