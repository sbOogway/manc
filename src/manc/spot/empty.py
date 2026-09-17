"""Offline stand-in until the Stooq adapter lands (M2)."""

from collections.abc import Sequence
from datetime import date

from manc.formulas.contract import AssetSpec
from manc.models import SpotPrice


class EmptySpot:
    def fetch(self, assets: Sequence[AssetSpec], day: date) -> list[SpotPrice]:
        return []
