"""Which news items are worth an LLM call: an institution alias next to a forecast signal."""

from collections.abc import Iterable

from manc.config import ForecastsConfig
from manc.models import NewsItem


def institution_in(text: str, config: ForecastsConfig) -> str | None:
    """Canonical name of the first institution alias found in `text`, longest alias first."""
    for pattern, name in config.alias_patterns:
        if pattern.search(text):
            return name
    return None


def candidates(items: Iterable[NewsItem], config: ForecastsConfig) -> list[NewsItem]:
    """Items that name an institution and use a forecast signal, in title or summary."""
    kept = []
    for item in items:
        text = f"{item.title}\n{item.summary}"
        if institution_in(text, config) and any(signal.search(text) for signal in config.signals):
            kept.append(item)
    return kept
