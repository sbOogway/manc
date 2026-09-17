"""The LLM tagger batches headlines, validates the schema and maps replies to NewsTags."""

import logging
import os
from collections.abc import Sequence
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


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="OPENROUTER_API_KEY not set")
def test_live_configured_model_tags_clear_headlines_the_right_way(
    capsys: pytest.CaptureFixture,
) -> None:
    """Benchmark of the configured model; run with `-m live -s` to see every tag it produced."""
    hot_cpi = _item(
        "US CPI runs hot at 4.1% vs 3.6% expected",
        summary="Treasury yields and the dollar jump as traders price out Fed cuts",
    )
    ecb_hike = _item("ECB surprises markets with a 50bp hike, signals more to come")
    btc_inflows = _item("Bitcoin spot ETF inflows hit a record $2bn in a day")
    noise = _item("Local bakery wins regional pie contest")
    headlines = [hot_cpi, ecb_hike, btc_inflows, noise]

    tags = LlmAnalyzer(CONFIG).tag(headlines, CONFIG.assets)

    titles = {item.id: item.title for item in headlines}
    with capsys.disabled():
        print()
        for tag in tags:
            title = titles[tag.news_id][:48]
            print(f"  {title:<48} {tag.asset:<7} {tag.direction:+d} {tag.confidence:.2f}")
        print(f"  model: {tags[0].model if tags else '-'}")

    by_key = {(tag.news_id, tag.asset): tag.direction for tag in tags}
    assert by_key.get((hot_cpi.id, "EURUSD")) == -1
    assert by_key.get((hot_cpi.id, "XAUUSD")) == -1
    assert by_key.get((ecb_hike.id, "EURUSD")) == 1
    assert by_key.get((btc_inflows.id, "BTCUSD")) == 1
    assert not [tag for tag in tags if tag.news_id == noise.id and tag.direction != 0]
    assert all(tag.model and tag.prompt_version == PROMPT_VERSION for tag in tags)
