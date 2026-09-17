"""The LLM tagger batches headlines, validates the schema and maps replies to NewsTags."""

import logging
import os
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel

from manc.analysis.interface import Analyzer
from manc.analysis.llm import PROMPT_VERSION, HeadlineTag, LlmAnalyzer, Tagging
from manc.config import LlmConfig, load_config
from manc.llm import LlmError
from manc.models import NewsItem, NewsTag

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
CONFIG = load_config()


def _item(title: str, summary: str = "") -> NewsItem:
    return NewsItem.from_feed(
        source="fxstreet",
        title=title,
        url=f"https://x/{abs(hash(title))}",
        published_at=NOW,
        summary=summary,
    )


class FakeComplete:
    """Replays one canned Tagging per call and records what it was asked."""

    def __init__(self, *responses: Tagging | Exception, model: str = "free/model") -> None:
        self.responses = list(responses)
        self.model = model
        self.calls: list[list[dict[str, str]]] = []

    def __call__(
        self, config: LlmConfig, messages: Sequence[dict[str, str]], response_model: type[BaseModel]
    ) -> tuple[Any, str]:
        self.calls.append(list(messages))
        response = self.responses.pop(0) if self.responses else Tagging(tags=[])
        if isinstance(response, Exception):
            raise response
        return response, self.model


def _tag(item: int, asset: str, direction: int, confidence: float = 0.8) -> HeadlineTag:
    return HeadlineTag(item=item, asset=asset, direction=direction, confidence=confidence)


def test_satisfies_the_protocol() -> None:
    assert isinstance(LlmAnalyzer(CONFIG, complete=FakeComplete()), Analyzer)


def test_sends_numbered_lines_in_batches_under_a_system_prompt() -> None:
    items = [_item(f"Headline {index}", summary="some context") for index in range(3)]
    complete = FakeComplete()
    LlmAnalyzer(CONFIG, complete=complete, batch_size=2).tag(items, CONFIG.assets)
    assert len(complete.calls) == 2
    user_messages = [call[-1]["content"] for call in complete.calls]
    assert "[0] Headline 0 — some context (fxstreet)" in user_messages[0]
    assert "[1] Headline 1" in user_messages[0] and "[2]" not in user_messages[0]
    assert "[0] Headline 2" in user_messages[1]
    assert all(call[0]["role"] == "system" for call in complete.calls)


def test_system_prompt_names_every_asset_with_kind_and_economies() -> None:
    complete = FakeComplete()
    LlmAnalyzer(CONFIG, complete=complete).tag([_item("x")], CONFIG.assets)
    system = complete.calls[0][0]["content"]
    for asset in CONFIG.assets:
        assert asset.symbol in system
        assert asset.kind in system
        for economy in asset.economies:
            assert economy in system


def test_no_headlines_means_no_call() -> None:
    complete = FakeComplete()
    assert LlmAnalyzer(CONFIG, complete=complete).tag([], CONFIG.assets) == []
    assert complete.calls == []


def test_reply_maps_to_tags_with_the_reported_model_and_prompt_version() -> None:
    hot_cpi, quiet = _item("US CPI runs hot"), _item("Markets wrap: stocks drift")
    complete = FakeComplete(
        Tagging(tags=[_tag(0, "EURUSD", -1, 0.9), _tag(0, "XAUUSD", -1, 0.7)]),
        model="router/x",
    )
    tags = LlmAnalyzer(CONFIG, complete=complete).tag([hot_cpi, quiet], CONFIG.assets)
    assert tags == [
        NewsTag(
            news_id=hot_cpi.id,
            asset="EURUSD",
            direction=-1,
            confidence=0.9,
            model="router/x",
            prompt_version=PROMPT_VERSION,
        ),
        NewsTag(
            news_id=hot_cpi.id,
            asset="XAUUSD",
            direction=-1,
            confidence=0.7,
            model="router/x",
            prompt_version=PROMPT_VERSION,
        ),
    ]


@pytest.mark.parametrize(
    "bad",
    [
        _tag(0, "EURGBP", 1),  # asset not tracked
        _tag(5, "EURUSD", 1),  # index outside the batch
    ],
)
def test_unmappable_tags_are_dropped_with_a_warning(
    bad: HeadlineTag, caplog: pytest.LogCaptureFixture
) -> None:
    complete = FakeComplete(Tagging(tags=[bad, _tag(0, "eurusd", 1)]))
    with caplog.at_level(logging.WARNING, logger="manc.analysis"):
        tags = LlmAnalyzer(CONFIG, complete=complete).tag([_item("x")], CONFIG.assets)
    assert [tag.asset for tag in tags] == ["EURUSD"]
    assert any("dropped" in record.message for record in caplog.records)


def test_schema_rejects_directions_and_confidences_outside_the_contract() -> None:
    with pytest.raises(ValueError):
        _tag(0, "EURUSD", 2)
    with pytest.raises(ValueError):
        _tag(0, "EURUSD", 1, confidence=1.5)


def test_a_failing_batch_is_skipped_and_the_others_still_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    first, second = _item("first"), _item("second")
    complete = FakeComplete(LlmError("every model failed"), Tagging(tags=[_tag(0, "BTCUSD", 1)]))
    analyzer = LlmAnalyzer(CONFIG, complete=complete, batch_size=1)
    with caplog.at_level(logging.WARNING, logger="manc.analysis"):
        tags = analyzer.tag([first, second], CONFIG.assets)
    assert [(tag.news_id, tag.asset) for tag in tags] == [(second.id, "BTCUSD")]
    assert any("batch" in record.message for record in caplog.records)


# --- live benchmark -----------------------------------------------------------------------
#
# One call to the configured model over every headline below, then one test per theme.
# Run with `uv run pytest tests/analysis/test_llm.py -m live -s -vv --no-cov`: `-s` prints
# every tag the model produced, `-vv` every wrong one. `MANC_LIVE_MODEL=openrouter/<vendor>/
# <model>` benchmarks another model without touching config/llm.yaml (no fallback, so its
# own failures show). Checked 2026-09-17: nex-agi/nex-n2.5-pro:free passes everything,
# nex-n2.5-mini:free only calls gold +1 on a hot CPI print, liquid/lfm-2.5-2.6b:free never
# tags EURUSD and flips SPX on an earnings beat, and the openrouter/free router lands on any
# of them.

live = pytest.mark.live
needs_key = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set"
)

HOT_CPI = _item(
    "US CPI runs hot at 4.1% vs 3.6% expected",
    summary="Treasury yields and the dollar jump as traders price out Fed cuts",
)
WEAK_PAYROLLS = _item(
    "US payrolls miss badly at 20k, unemployment jumps to 4.6%",
    summary="Markets now price three Fed cuts by year-end; dollar slides",
)
DOVISH_FED = _item("Powell says the time has come to cut rates, sees inflation on track to 2%")
ECB_HIKE = _item("ECB surprises markets with a 50bp hike, signals more to come")
BOJ_HIKE = _item("BoJ raises rates to 1%, yen surges to a six-month high")
UK_GDP = _item("UK GDP unexpectedly contracts 0.3% in Q2, recession fears grow")
OPEC_CUT = _item("OPEC+ deepens output cuts by 1m barrels a day, crude jumps 4%")
BANK_MISS = _item("S&P 500 futures slide as big-bank earnings miss and guidance is cut")
CHIP_RALLY = _item("Nvidia beats on every line, chip stocks rally in after-hours trade")
BTC_INFLOWS = _item("Bitcoin spot ETF inflows hit a record $2bn in a day")
# Market-flavoured but signal-free: the right answer is no tag, or a 0 at most.
NOISE = (
    _item("Local bakery wins regional pie contest"),
    _item("Goldman Sachs names new head of European equities"),
    _item("ECB publishes the schedule of its 2027 monetary policy meetings"),
    _item("NYSE and Nasdaq to close on Monday for the public holiday"),
    _item("How to read a candlestick chart: a beginner's guide"),
    _item("Bitcoin conference draws 20,000 attendees to Nashville"),
    _item("Weekly markets wrap: stocks flat, dollar little changed, gold steady"),
)
# Two-sided for the assets named: a directional call either way is a guess.
BALANCED = (
    (
        _item(
            "US CPI cools to 2.1% headline but core services inflation re-accelerates",
            summary="Traders see the mixed print leaving the Fed's next move a coin flip",
        ),
        ("EURUSD", "XAUUSD", "USDJPY"),
    ),
    (
        _item(
            "Fed cuts 25bp but a split committee leaves December wide open",
            summary="Three officials wanted 50bp, two wanted no change; Powell offers no guidance",
        ),
        ("EURUSD", "XAUUSD", "USDJPY"),
    ),
    (
        _item("OPEC+ extends output cuts as the IEA trims its demand forecast again"),
        ("BRENT",),
    ),
    (
        _item("Bitcoin holds near $100k as ETF inflows offset miner selling"),
        ("BTCUSD",),
    ),
    (
        _item("Sterling flat as UK inflation lands exactly in line with forecasts"),
        ("GBPUSD",),
    ),
)
DIRECTIONLESS = {item.id for item in NOISE} | {item.id for item, _ in BALANCED}
HEADLINES = [
    HOT_CPI,
    WEAK_PAYROLLS,
    DOVISH_FED,
    ECB_HIKE,
    BOJ_HIKE,
    UK_GDP,
    OPEC_CUT,
    BANK_MISS,
    CHIP_RALLY,
    BTC_INFLOWS,
    *NOISE,
    *(item for item, _ in BALANCED),
]

Directions = dict[tuple[str, str], int]


def _mismatches(directions: Directions, *expected: tuple[NewsItem, str, int]) -> list[str]:
    """Readable diff of what the model said against what a market reader would, all at once."""
    return [
        f"{item.title[:40]!r} {asset}: wanted {wanted:+d}, got "
        f"{'no tag' if (item.id, asset) not in directions else f'{directions[item.id, asset]:+d}'}"
        for item, asset, wanted in expected
        if directions.get((item.id, asset)) != wanted
    ]


@pytest.fixture(scope="module")
def live_tags() -> list[NewsTag]:
    config = CONFIG
    override = os.environ.get("MANC_LIVE_MODEL")
    if override:
        config = replace(CONFIG, llm=replace(CONFIG.llm, model=override, fallback=None))
    tags = LlmAnalyzer(config).tag(HEADLINES, config.assets)
    titles = {item.id: item.title for item in HEADLINES}
    print()
    for tag in tags:
        title = titles[tag.news_id][:52]
        print(f"  {title:<52} {tag.asset:<7} {tag.direction:+d} {tag.confidence:.2f}")
    print(f"  {len(tags)} tags from {tags[0].model if tags else 'no model'}")
    return tags


@pytest.fixture(scope="module")
def directions(live_tags: list[NewsTag]) -> Directions:
    return {(tag.news_id, tag.asset): tag.direction for tag in live_tags}


@live
@needs_key
def test_live_tags_are_well_formed(live_tags: list[NewsTag]) -> None:
    assert live_tags, "the model returned nothing"
    assert all(tag.model and tag.prompt_version == PROMPT_VERSION for tag in live_tags)
    assert len({(tag.news_id, tag.asset) for tag in live_tags}) == len(live_tags)  # no repeats


@live
@needs_key
def test_live_every_market_headline_gets_at_least_one_tag(live_tags: list[NewsTag]) -> None:
    tagged = {tag.news_id for tag in live_tags}
    missed = [
        item.title for item in HEADLINES if item.id not in DIRECTIONLESS and item.id not in tagged
    ]
    assert missed == []


@live
@needs_key
def test_live_hot_us_data_lifts_the_dollar_and_hurts_gold(directions: Directions) -> None:
    assert (
        _mismatches(
            directions,
            (HOT_CPI, "EURUSD", -1),
            (HOT_CPI, "GBPUSD", -1),
            (HOT_CPI, "USDJPY", 1),
            (HOT_CPI, "XAUUSD", -1),
        )
        == []
    )


@live
@needs_key
def test_live_weak_us_data_and_a_dovish_fed_do_the_opposite(directions: Directions) -> None:
    assert (
        _mismatches(
            directions,
            (WEAK_PAYROLLS, "EURUSD", 1),
            (WEAK_PAYROLLS, "XAUUSD", 1),
            (WEAK_PAYROLLS, "USDJPY", -1),
            (DOVISH_FED, "EURUSD", 1),
            (DOVISH_FED, "XAUUSD", 1),
            (DOVISH_FED, "USDJPY", -1),
        )
        == []
    )


@live
@needs_key
def test_live_foreign_central_banks_and_data_move_their_own_currency(
    directions: Directions,
) -> None:
    assert (
        _mismatches(
            directions,
            (ECB_HIKE, "EURUSD", 1),
            (BOJ_HIKE, "USDJPY", -1),  # a stronger yen is a lower USDJPY
            (UK_GDP, "GBPUSD", -1),
        )
        == []
    )


@live
@needs_key
def test_live_commodity_equity_and_crypto_headlines(directions: Directions) -> None:
    assert (
        _mismatches(
            directions,
            (OPEC_CUT, "BRENT", 1),
            (BANK_MISS, "SPX", -1),
            (CHIP_RALLY, "SPX", 1),
            (BTC_INFLOWS, "BTCUSD", 1),
        )
        == []
    )


@live
@needs_key
def test_live_market_noise_carries_no_direction(live_tags: list[NewsTag]) -> None:
    titles = {item.id: item.title[:40] for item in NOISE}
    directional = [
        f"{titles[tag.news_id]!r} {tag.asset} {tag.direction:+d}"
        for tag in live_tags
        if tag.news_id in titles and tag.direction != 0
    ]
    assert directional == []


@live
@needs_key
def test_live_two_sided_headlines_get_no_directional_call(directions: Directions) -> None:
    guessed = [
        f"{item.title[:40]!r} {asset} {directions[item.id, asset]:+d}"
        for item, assets in BALANCED
        for asset in assets
        if directions.get((item.id, asset), 0) != 0
    ]
    assert guessed == []


@live
@needs_key
def test_live_unrelated_assets_are_not_tagged(directions: Directions) -> None:
    """A UK print says nothing about oil or bitcoin; OPEC says nothing about the yen."""
    unrelated = [
        (UK_GDP, "BRENT"),
        (UK_GDP, "BTCUSD"),
        (OPEC_CUT, "USDJPY"),
    ]
    assert [
        (item.title[:40], asset) for item, asset in unrelated if (item.id, asset) in directions
    ] == []
