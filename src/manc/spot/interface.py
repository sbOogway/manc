from collections.abc import Sequence
from datetime import date
from typing import Protocol, runtime_checkable

from manc.formulas.contract import AssetSpec
from manc.models import SpotPrice


@runtime_checkable
class SpotProvider(Protocol):
    def fetch(self, assets: Sequence[AssetSpec], day: date) -> list[SpotPrice]: ...
