"""Domain value objects shared by every module (blueprint section 3).

Score-side types (AssetSpec, IndexScore, ...) live in manc.formulas.contract so the
formula package stays free of app imports; they are re-exported here for convenience.
"""

from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha1

from manc.formulas.contract import AssetSpec, IndexScore

__all__ = [
    "AssetSpec",
    "CalendarEvent",
    "ForecastAsset",
    "ForecastMacro",
    "Forecasts",
    "IndexScore",
    "NewsItem",
    "NewsTag",
    "SpotPrice",
]

SOURCE_KINDS = ("extracted", "structured")


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


def _forecast_id(institution: str, subject: str, horizon_date: date, value: float) -> str:
    """One id per vintage: re-reports of the same call collide, a new value is a new row."""
    return sha1(
        f"{institution}|{subject}|{horizon_date.isoformat()}|{value:.6g}".encode()
    ).hexdigest()


def _check_forecast(confidence: float, source_kind: str) -> None:
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be within 0..1, got {confidence}")
    if source_kind not in SOURCE_KINDS:
        raise ValueError(f"source_kind must be one of {SOURCE_KINDS}, got {source_kind!r}")


@dataclass(frozen=True)
class ForecastAsset:
    """An institution's price target for one asset, as first sighted (blueprint section 4)."""

    id: str  # sha1(institution | asset | horizon_date | value)
    institution: str  # canonical name from config/forecasts.yaml, e.g. "goldman_sachs"
    asset: str  # "EURUSD"
    horizon_date: date  # end of the stated period, normalised from published_at
    horizon_label: str  # as stated: "12 months", "year-end", "Q4 2026"
    value: float  # price level in the asset's quote unit
    published_at: datetime  # earliest sighting
    source_url: str
    source_kind: str  # "extracted" (from news) | "structured" (publisher data)
    confidence: float  # 0..1; 1.0 for structured sources
    model: str  # LLM that extracted it, "" for structured sources

    def __post_init__(self) -> None:
        _check_forecast(self.confidence, self.source_kind)

    @classmethod
    def new(
        cls,
        *,
        institution: str,
        asset: str,
        horizon_date: date,
        horizon_label: str,
        value: float,
        published_at: datetime,
        source_url: str,
        source_kind: str,
        confidence: float,
        model: str = "",
    ) -> "ForecastAsset":
        return cls(
            id=_forecast_id(institution, asset, horizon_date, value),
            institution=institution,
            asset=asset,
            horizon_date=horizon_date,
            horizon_label=horizon_label,
            value=value,
            published_at=published_at,
            source_url=source_url,
            source_kind=source_kind,
            confidence=confidence,
            model=model,
        )


@dataclass(frozen=True)
class ForecastMacro:
    """Like ForecastAsset, but about an economy: a policy rate, CPI, GDP or unemployment."""

    id: str  # sha1(institution | economy:metric | horizon_date | value)
    institution: str
    economy: str  # "united_states"
    metric: str  # policy_rate | cpi | gdp | unemployment
    horizon_date: date
    horizon_label: str
    value: float
    published_at: datetime
    source_url: str
    source_kind: str
    confidence: float
    model: str

    def __post_init__(self) -> None:
        _check_forecast(self.confidence, self.source_kind)

    @classmethod
    def new(
        cls,
        *,
        institution: str,
        economy: str,
        metric: str,
        horizon_date: date,
        horizon_label: str,
        value: float,
        published_at: datetime,
        source_url: str,
        source_kind: str,
        confidence: float,
        model: str = "",
    ) -> "ForecastMacro":
        return cls(
            id=_forecast_id(institution, f"{economy}:{metric}", horizon_date, value),
            institution=institution,
            economy=economy,
            metric=metric,
            horizon_date=horizon_date,
            horizon_label=horizon_label,
            value=value,
            published_at=published_at,
            source_url=source_url,
            source_kind=source_kind,
            confidence=confidence,
            model=model,
        )


@dataclass(frozen=True)
class Forecasts:
    """What one ForecastProvider.fetch returns: both kinds at once."""

    asset: tuple[ForecastAsset, ...] = ()
    macro: tuple[ForecastMacro, ...] = ()


@dataclass(frozen=True)
class SpotPrice:
    """One daily close, for display next to forecasts only; never a formula input."""

    asset: str
    date: date
    close: float
    source: str  # "stooq"
