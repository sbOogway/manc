"""Offline stand-in until the lexicon fallback lands (M3)."""

from collections.abc import Sequence

from manc.models import AssetSpec, NewsItem, NewsTag


class EmptyAnalyzer:
    def tag(self, items: Sequence[NewsItem], assets: Sequence[AssetSpec]) -> list[NewsTag]:
        return []
