"""Offline headline tagger over config/lexicon.yaml (in the package); the LLM fallback (§4)."""

import re
from collections import defaultdict
from collections.abc import Sequence

from manc.config import LexiconConfig
from manc.models import AssetSpec, NewsItem, NewsTag

CONFIDENCE = 0.5  # every lexicon tag; the LLM's own confidence usually outranks it


class LexiconAnalyzer:
    """Reads the title only. The rules are documented at the top of src/manc/config/lexicon.yaml."""

    def __init__(self, lexicon: LexiconConfig) -> None:
        self.lexicon = lexicon

    def tag(self, items: Sequence[NewsItem], assets: Sequence[AssetSpec]) -> list[NewsTag]:
        tags: list[NewsTag] = []
        for item in items:
            polarity = self.polarity(item.title)
            if polarity is None:
                continue
            votes = self._votes(item.title, polarity, assets)
            tags.extend(
                NewsTag(
                    news_id=item.id,
                    asset=asset.symbol,
                    direction=next(iter(directions)) if len(directions) == 1 else 0,
                    confidence=CONFIDENCE,
                )
                for asset in assets
                if (directions := votes.get(asset.symbol))
            )
        return tags

    def polarity(self, title: str) -> int | None:
        """+1 hot/up, -1 cold/down, 0 balanced or contradictory, None when nothing matched."""
        signs: set[int] = set()
        remaining = title
        for pattern, sign in self.lexicon.polarity:
            remaining, count = pattern.subn(" ", remaining)
            if count:
                signs.add(sign)
        if not signs:
            return None
        return next(iter(signs)) if len(signs) == 1 else 0

    def _votes(self, title: str, polarity: int, assets: Sequence[AssetSpec]) -> dict[str, set[int]]:
        votes: dict[str, set[int]] = defaultdict(set)
        economy = _first(self.lexicon.economies, title)
        category = _first(self.lexicon.categories, title)
        if economy and category:
            for asset in assets:
                sign = asset.signs.get(economy, {}).get(category, 0)
                if sign:
                    votes[asset.symbol].add(polarity * sign)
        symbols = {asset.symbol for asset in assets}
        for pattern, symbol, sign in self.lexicon.assets:
            if symbol in symbols and pattern.search(title):
                votes[symbol].add(polarity * sign)
        return votes


def _first(terms: Sequence[tuple[re.Pattern[str], str]], title: str) -> str | None:
    """The key of the term that appears earliest in the title; ties go to the first listed."""
    hits = [
        (match.start(), position, key)
        for position, (pattern, key) in enumerate(terms)
        if (match := pattern.search(title))
    ]
    return min(hits)[2] if hits else None
