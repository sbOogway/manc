from collections.abc import Sequence
from datetime import date
from typing import Protocol, runtime_checkable

from manc.formulas.contract import AssetSpec
from manc.models import ChainMetric


@runtime_checkable
class ChainProvider(Protocol):
    def fetch(self, assets: Sequence[AssetSpec], start: date, end: date) -> list[ChainMetric]:
        """Daily readings in [start, end] for every asset the source knows; never raises."""
        ...
