"""Forecasts out of headlines: prefilter, one LLM call per batch, map to the models (§4)."""

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from itertools import batched
from typing import Any

from pydantic import BaseModel, Field

from manc import llm
from manc.config import Config
from manc.forecasts.horizon import normalise
from manc.forecasts.prefilter import candidates
from manc.models import ForecastAsset, ForecastMacro, Forecasts, NewsItem
from manc.store.interface import NewsRepository

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You extract explicit numeric forecasts made by named institutions from financial headlines.

Each input line is "[index] title — summary (source, published YYYY-MM-DD)". For every
forecast that an institution states in a line, return one object:
- item: the line's index
- institution: the institution as named in the line (a bank, central bank, agency or survey)
- subject: one of the asset symbols below, or "economy:metric" using the economies and
  metrics below
- value: the forecast number. FX pairs as the quoted rate (EURUSD 1.18), gold, oil, indices
  and bitcoin in US dollars, rates and macro metrics in percent
- horizon: the period as stated ("12 months", "year-end", "Q4 2026", "end-2027")
- confidence: 0..1, how sure you are that the line states this forecast from this institution

Skip technical-analysis levels, options-implied levels, past values, and anything the
institution is merely quoted about. Return an empty list when there is nothing.

Assets: {assets}
Economies: {economies}
Metrics: {metrics}
Known institutions (any spelling is fine): {institutions}
"""


class ExtractedForecast(BaseModel):
    item: int
    institution: str
    subject: str
    value: float
    horizon: str
    confidence: float = Field(ge=0.0, le=1.0)


class Extraction(BaseModel):
    """What the LLM returns, as JSON constrained to this schema through `response_format`.

    Example: {"forecasts": [{"item": 3, "institution": "Goldman Sachs", "subject": "XAUUSD",
    "value": 4900, "horizon": "2026", "confidence": 0.95}]}
    """

    forecasts: list[ExtractedForecast]


Complete = Callable[..., tuple[Any, str]]


class LlmExtractor:
    """ForecastProvider over the news already in the store."""

    def __init__(
        self,
        config: Config,
        news: NewsRepository,
        *,
        complete: Complete = llm.complete,
        batch_size: int | None = None,
    ) -> None:
        self.config = config
        self.news = news
        self.complete = complete
        self.batch_size = batch_size or config.llm.batch_size
        self.symbols = {asset.symbol for asset in config.assets}
        self.economies = {economy for asset in config.assets for economy in asset.economies}
        self.system_prompt = SYSTEM_PROMPT.format(
            assets=", ".join(sorted(self.symbols)),
            economies=", ".join(sorted(self.economies)),
            metrics=", ".join(config.forecasts.metrics),
            institutions=", ".join(
                institution.name for institution in config.forecasts.institutions
            ),
        )

    def fetch(self, since: datetime) -> Forecasts:
        items = candidates(self.news.since(since), self.config.forecasts)
        asset_rows: dict[str, ForecastAsset] = {}
        macro_rows: dict[str, ForecastMacro] = {}
        for batch in batched(items, self.batch_size):
            for forecast in self._extract(batch):
                rows: dict[str, Any] = (
                    asset_rows if isinstance(forecast, ForecastAsset) else macro_rows
                )
                existing = rows.get(forecast.id)
                if existing is None or forecast.published_at < existing.published_at:
                    rows[forecast.id] = forecast
        log.info(
            "forecasts: %d candidates → %d asset, %d macro",
            len(items),
            len(asset_rows),
            len(macro_rows),
        )
        return Forecasts(asset=tuple(asset_rows.values()), macro=tuple(macro_rows.values()))

    def _extract(self, batch: Sequence[NewsItem]) -> list[ForecastAsset | ForecastMacro]:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": "\n".join(_line(index, item) for index, item in enumerate(batch)),
            },
        ]
        try:
            extraction, model = self.complete(self.config.llm, messages, Extraction)
        except llm.LlmError as error:
            log.warning("forecasts: batch of %d items skipped: %s", len(batch), error)
            return []
        mapped = []
        for found in extraction.forecasts:
            forecast = self._to_model(found, batch, model)
            if forecast is None:
                log.warning("forecasts: dropped %s", found.model_dump())
            else:
                mapped.append(forecast)
        return mapped

    def _to_model(
        self, found: ExtractedForecast, batch: Sequence[NewsItem], model: str
    ) -> ForecastAsset | ForecastMacro | None:
        if not 0 <= found.item < len(batch):
            return None
        item = batch[found.item]
        horizon_date = normalise(found.horizon, item.published_at)
        if horizon_date is None:
            return None
        common = dict(
            institution=self.config.forecasts.canonical(found.institution),
            horizon_date=horizon_date,
            horizon_label=found.horizon.strip(),
            value=found.value,
            published_at=item.published_at,
            source_url=item.url,
            source_kind="extracted",
            confidence=found.confidence,
            model=model,
        )
        subject = found.subject.strip()
        if subject.upper() in self.symbols:
            return ForecastAsset.new(asset=subject.upper(), **common)
        economy, _, metric = subject.lower().partition(":")
        economy = economy.strip().replace(" ", "_")
        metric = metric.strip()
        if economy in self.economies and metric in self.config.forecasts.metrics:
            return ForecastMacro.new(economy=economy, metric=metric, **common)
        return None


def _line(index: int, item: NewsItem) -> str:
    summary = item.summary[:300].replace("\n", " ")
    published = item.published_at.strftime("%Y-%m-%d")
    return f"[{index}] {item.title} — {summary} ({item.source}, published {published})"
