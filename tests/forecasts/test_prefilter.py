"""The prefilter keeps only headlines that name an institution and sound like a forecast."""

from datetime import UTC, datetime

from manc.config import load_config
from manc.forecasts.prefilter import candidates, institution_in
from manc.models import NewsItem
from tests.test_config import REPO_CONFIG

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
FORECASTS = load_config(REPO_CONFIG).forecasts


def _item(title: str, summary: str = "") -> NewsItem:
    return NewsItem.from_feed(
        source="fxstreet",
        title=title,
        url=f"https://x/{hash(title)}",
        published_at=NOW,
        summary=summary,
    )


def test_keeps_alias_and_signal_in_title() -> None:
    item = _item("ING lifts year-end EUR/USD forecast to 1.18")
    assert candidates([item], FORECASTS) == [item]


def test_keeps_signal_found_only_in_summary() -> None:
    item = _item("Gold outlook from Goldman Sachs", summary="The bank now sees gold at $4,000.")
    assert candidates([item], FORECASTS) == [item]


def test_drops_alias_without_signal_and_signal_without_alias() -> None:
    hiring = _item("Goldman Sachs hires new head of European equities")
    technical = _item("EUR/USD forecast: technical levels to watch this week")
    assert candidates([hiring, technical], FORECASTS) == []


def test_alias_match_is_word_bounded_and_case_insensitive() -> None:
    pharma = _item("GSK raises guidance after strong quarter")
    bank = _item("gs sees oil at $70 by year-end")
    assert candidates([pharma, bank], FORECASTS) == [bank]


def test_order_is_preserved_and_empty_is_empty() -> None:
    first = _item("UBS raises gold target to 3,900")
    second = _item("JPMorgan expects EUR/USD at 1.20 in 12 months")
    assert candidates([first, second], FORECASTS) == [first, second]
    assert candidates([second, first], FORECASTS) == [second, first]
    assert candidates([], FORECASTS) == []


def test_institution_in_returns_the_first_canonical_match() -> None:
    assert institution_in("Goldman Sachs raises gold target", FORECASTS) == "goldman_sachs"
    assert institution_in("Fed funds path per the SEP", FORECASTS) == "fed"
    assert institution_in("A note from Rabobank on the euro", FORECASTS) is None
