"""The lexicon analyzer tags titles offline from config/lexicon.yaml and the asset signs."""

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st

from manc.analysis.interface import Analyzer
from manc.analysis.lexicon import CONFIDENCE, LexiconAnalyzer
from manc.config import load_config
from manc.models import NewsItem
from tests.analysis.headlines import FETCHED, Case, directions, load_cases, mismatches

CONFIG = load_config()
ANALYZER = LexiconAnalyzer(CONFIG.lexicon)
CASES = load_cases("synthetic")


def _item(title: str, summary: str = "") -> NewsItem:
    return NewsItem.from_feed(
        source="fxstreet",
        title=title,
        url=f"https://x/{title}",
        published_at=FETCHED,
        summary=summary,
    )


def _tags(title: str, summary: str = "") -> dict[str, int]:
    return {
        tag.asset: tag.direction for tag in ANALYZER.tag([_item(title, summary)], CONFIG.assets)
    }


def test_is_an_analyzer() -> None:
    assert isinstance(ANALYZER, Analyzer)


@pytest.mark.parametrize("case", CASES, ids=[case.item.title[:60] for case in CASES])
def test_synthetic_headline(case: Case) -> None:
    tags = ANALYZER.tag([case.item], CONFIG.assets)
    assert mismatches(case, directions(tags)) == []


def test_tags_are_offline_with_a_fixed_confidence() -> None:
    tags = ANALYZER.tag([_item("US CPI runs hot")], CONFIG.assets)
    assert tags and {(tag.model, tag.prompt_version, tag.confidence) for tag in tags} == {
        ("", "", CONFIDENCE)
    }
    assert len({tag.asset for tag in tags}) == len(tags)


def test_data_print_follows_the_sign_map() -> None:
    assert _tags("US CPI runs hot") == {
        "EURUSD": -1,
        "GBPUSD": -1,
        "USDJPY": 1,
        "XAUUSD": -1,
        "SPX": -1,
        "BTCUSD": -1,
    }  # BRENT has sign 0 for US inflation, so no tag
    assert _tags("ECB hikes 50bp") == {"EURUSD": 1}


def test_first_economy_and_category_mentioned_win() -> None:
    assert _tags("BoJ hikes as US inflation cools")["USDJPY"] == 0  # hike and cool disagree
    assert _tags("Yen jumps after BoJ rate hike") == {"USDJPY": -1}


def test_asset_mention_carries_its_sign() -> None:
    assert _tags("Gold jumps to a record") == {"XAUUSD": 1}
    assert _tags("Dollar slides") == {"EURUSD": 1, "GBPUSD": 1, "USDJPY": -1}
    assert _tags("Crude tumbles 5%") == {"BRENT": -1}


def test_mixed_or_balanced_titles_tag_zero() -> None:
    assert _tags("Gold jumps then slides") == {"XAUUSD": 0}
    assert _tags("Stocks flat ahead of the Fed") == {"SPX": 0}
    assert _tags("US CPI cools but core prices jump")["EURUSD"] == 0


def test_mention_without_polarity_and_polarity_without_mention_tag_nothing() -> None:
    assert _tags("Bitcoin conference draws a crowd") == {}
    assert _tags("Quarterly results beat estimates") == {}


def test_summary_is_ignored() -> None:
    assert _tags("Weekly wrap", summary="Gold jumps to a record as the dollar slides") == {}


def test_uppercase_terms_are_case_sensitive() -> None:
    assert _tags("Airline fed up with delays cuts routes") == {}
    assert _tags("Fed cuts rates")["EURUSD"] == 1
    assert _tags("gold jumps") == {"XAUUSD": 1}


def _literal_terms(pairs: list[tuple[re.Pattern[str], str]]) -> list[tuple[str, str]]:
    """(term, key) for terms that are plain words, usable verbatim in a title."""
    found = []
    for pattern, key in pairs:
        term = pattern.pattern.removeprefix("(?<!\\w)(?:").removesuffix(")(?!\\w)")
        if re.escape(term) == term and " " not in term:
            found.append((term, key))
    return found


ECONOMY_TERMS = _literal_terms(list(CONFIG.lexicon.economies))
CATEGORY_TERMS = [  # "hawkish" and "dovish" name the rates category and carry a polarity
    (term, key)
    for term, key in _literal_terms(list(CONFIG.lexicon.categories))
    if ANALYZER.polarity(term) is None
]
POLARITY_TERMS = [
    (term, sign) for term, sign in _literal_terms(list(CONFIG.lexicon.polarity)) if sign != 0
]


@given(
    economy=st.sampled_from(ECONOMY_TERMS),
    category=st.sampled_from(CATEGORY_TERMS),
    polarity=st.sampled_from(POLARITY_TERMS),
)
def test_data_print_direction_is_polarity_times_sign(
    economy: tuple[str, str], category: tuple[str, str], polarity: tuple[str, int]
) -> None:
    (economy_term, economy_key), (category_term, category_key), (polarity_term, sign) = (
        economy,
        category,
        polarity,
    )
    tags = _tags(f"{economy_term} {category_term} {polarity_term}")
    for asset in CONFIG.assets:
        wanted = asset.signs.get(economy_key, {}).get(category_key, 0) * sign
        if wanted:
            assert tags[asset.symbol] == wanted, asset.symbol
        elif economy_key in asset.economies:
            assert asset.symbol not in tags or tags[asset.symbol] == 0
