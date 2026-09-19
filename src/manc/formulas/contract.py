"""What a formula receives and returns. The only thing the app depends on.

Everything here is a plain frozen dataclass or a Protocol; no imports from the rest of manc.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class AssetSpec:
    symbol: str  # "EURUSD"
    kind: str  # forex | metal | commodity | equity_index | crypto
    economies: tuple[str, ...]  # countries whose calendar events matter
    # country -> event category -> -1 | 0 | +1: the direction a hotter-than-expected print
    # pushes this asset. A hot US CPI is -1 for EURUSD, a hot euro-area CPI is +1.
    signs: Mapping[str, Mapping[str, int]] = field(default_factory=dict)
    # spot source -> its ticker for this asset ({"yahoo": "EURUSD=X"}); display only, no
    # formula reads it
    spot: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TaggedHeadline:
    """One headline's contribution for one asset, with what the formula needs to weight it."""

    direction: int  # -1, 0, +1
    confidence: float  # 0..1
    source_weight: float  # 0..1, from the feeds config
    published_at: datetime


@dataclass(frozen=True)
class EventObservation:
    """A calendar event as the formula sees it. `actual is None` means not yet released."""

    date: datetime
    country: str
    category: str
    importance: int  # 1 low, 2 medium, 3 high
    consensus: float | None
    previous: float | None
    actual: float | None


@dataclass(frozen=True)
class ScoringInputs:
    asset: AssetSpec
    as_of: datetime
    tags: tuple[TaggedHeadline, ...]
    released: tuple[EventObservation, ...]  # events with actual, within the lookback
    upcoming: tuple[EventObservation, ...]  # events in the look-ahead window
    params: Mapping[str, float]  # from config/scoring.yaml


BANDS = ("headwind", "lean_against", "neutral", "lean_for", "tailwind")


@dataclass(frozen=True)
class Scale:
    """Where a formula's scores live: the ends, the neutral point and the four band edges."""

    low: float
    high: float
    neutral: float
    edges: tuple[float, float, float, float]  # inner boundaries, lower bound inclusive

    def band(self, score: float) -> str:
        label = BANDS[0]
        for edge, name in zip(self.edges, BANDS[1:], strict=True):
            if score >= edge:
                label = name
        return label

    def clip(self, score: float) -> float:
        return min(self.high, max(self.low, score))


@dataclass(frozen=True)
class IndexScore:
    asset: str
    date: date
    score: float  # 0..100
    formula: str  # "v1"
    components: Mapping[str, float]  # whatever the formula exposes, e.g. N, S, R
    n_news: int
    n_events: int
    report_md: str = ""  # filled in by the report builder after scoring


@runtime_checkable
class IndexFormula(Protocol):
    name: str
    scale: Scale

    def compute(self, inputs: ScoringInputs) -> IndexScore: ...
