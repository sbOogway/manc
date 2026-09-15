from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from manc.models import AssetSpec, NewsItem, NewsTag


@runtime_checkable
class Analyzer(Protocol):
    """Tags headlines with a direction per asset. Surprise math lives in the formula."""

    def tag(self, items: Sequence[NewsItem], assets: Sequence[AssetSpec]) -> list[NewsTag]: ...
