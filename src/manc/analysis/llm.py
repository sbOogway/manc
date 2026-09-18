"""Headline tagger: one LLM call per batch, a direction per asset the headline moves (§4)."""

import logging
from collections.abc import Callable, Sequence
from itertools import batched
from typing import Any, Literal

from pydantic import BaseModel, Field

from manc import llm
from manc.analysis.interface import Analyzer
from manc.config import Config
from manc.models import AssetSpec, NewsItem, NewsTag

log = logging.getLogger(__name__)

PROMPT_VERSION = "v1"  # bump when SYSTEM_PROMPT changes; stored on every tag

SYSTEM_PROMPT = """\
You read financial headlines and judge which tracked assets each one moves, and which way.

Each input line is "[index] title — summary (source)". For every asset a line gives a
directional signal about, return one object:
- item: the line's index
- asset: the asset symbol, from the list below
- direction: 1 if the news pushes the asset's price up, -1 if down, 0 if it is relevant but
  balanced
- confidence: 0..1, how clear the signal is

Judge each asset by its own drivers: a hotter-than-expected US print lifts the dollar (so
it is -1 for EURUSD, +1 for USDJPY) and weighs on gold, equities and bitcoin; risk-on
sentiment lifts equities, bitcoin and AUDUSD; dovish central-bank talk weakens its
currency. Skip assets a line says nothing about, and skip lines that are pure noise.
Return an empty list when nothing applies.

Assets (symbol, kind, economies whose data drive it):
{assets}
"""


class HeadlineTag(BaseModel):
    item: int
    asset: str
    direction: Literal[-1, 0, 1]
    confidence: float = Field(ge=0.0, le=1.0)


class Tagging(BaseModel):
    """What the LLM returns, as JSON constrained to this schema through `response_format`.

    Example: {"tags": [{"item": 2, "asset": "EURUSD", "direction": -1, "confidence": 0.8}]}
    """

    tags: list[HeadlineTag]


Complete = Callable[..., tuple[Any, str]]


class LlmAnalyzer:
    """Analyzer over LiteLLM; the model string and batch size come from `config/llm.yaml`.

    A batch every configured model fails on goes to `fallback` (the lexicon analyzer in
    `manc run`), or is skipped when there is none.
    """

    def __init__(
        self,
        config: Config,
        *,
        complete: Complete = llm.complete,
        batch_size: int | None = None,
        fallback: Analyzer | None = None,
    ) -> None:
        self.config = config
        self.complete = complete
        self.batch_size = batch_size or config.llm.batch_size
        self.fallback = fallback

    def tag(self, items: Sequence[NewsItem], assets: Sequence[AssetSpec]) -> list[NewsTag]:
        symbols = {asset.symbol for asset in assets}
        system_prompt = SYSTEM_PROMPT.format(
            assets="\n".join(
                f"- {asset.symbol}: {asset.kind}, {', '.join(asset.economies)}" for asset in assets
            )
        )
        batches = list(batched(items, self.batch_size))
        tags: list[NewsTag] = []
        for number, batch in enumerate(batches, start=1):
            found, tagged_by = self._tag_batch(batch, symbols, system_prompt, assets)
            tags.extend(found)
            log.info(
                "analysis: batch %d/%d, %d headlines → %d tags (%s)",
                number,
                len(batches),
                len(batch),
                len(found),
                tagged_by,
            )
        return tags

    def _tag_batch(
        self,
        batch: Sequence[NewsItem],
        symbols: set[str],
        system_prompt: str,
        assets: Sequence[AssetSpec],
    ) -> tuple[list[NewsTag], str]:
        """The batch's tags and who produced them: the model, the fallback, or "skipped"."""
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "\n".join(_line(index, item) for index, item in enumerate(batch)),
            },
        ]
        try:
            tagging, model = self.complete(self.config.llm, messages, Tagging)
        except llm.LlmError as error:
            if self.fallback is None:
                log.warning("analysis: batch of %d headlines skipped: %s", len(batch), error)
                return [], "skipped"
            fallback = type(self.fallback).__name__
            log.warning(
                "analysis: batch of %d headlines tagged by %s: %s", len(batch), fallback, error
            )
            return self.fallback.tag(batch, assets), fallback
        tags = []
        for found in tagging.tags:
            symbol = found.asset.strip().upper()
            if symbol not in symbols or not 0 <= found.item < len(batch):
                log.warning("analysis: dropped %s", found.model_dump())
                continue
            tags.append(
                NewsTag(
                    news_id=batch[found.item].id,
                    asset=symbol,
                    direction=found.direction,
                    confidence=found.confidence,
                    model=model,
                    prompt_version=PROMPT_VERSION,
                )
            )
        return tags, model


def _line(index: int, item: NewsItem) -> str:
    summary = item.summary[:300].replace("\n", " ")
    context = f" — {summary}" if summary else ""
    return f"[{index}] {item.title}{context} ({item.source})"
