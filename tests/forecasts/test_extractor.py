"""The extractor sends prefilter candidates to the LLM and maps what comes back to forecasts."""

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from pydantic import BaseModel

from manc.config import LlmConfig, load_config
from manc.forecasts.extractor import ExtractedForecast, Extraction, LlmExtractor
from manc.llm import LlmError
from manc.models import ForecastAsset, ForecastMacro, NewsItem
from tests.fakes import FakeStore

NOW = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
DAY = timedelta(days=1)
CONFIG = load_config()


def _item(title: str, published_at: datetime = NOW, summary: str = "") -> NewsItem:
    return NewsItem.from_feed(
        source="fxstreet",
        title=title,
        url=f"https://x/{abs(hash(title))}",
        published_at=published_at,
        summary=summary,
    )


class FakeComplete:
    """Replays one canned Extraction per call and records what it was asked."""

    def __init__(self, *responses: Extraction | Exception, model: str = "free/model") -> None:
        self.responses = list(responses)
        self.model = model
        self.calls: list[list[dict[str, str]]] = []

    def __call__(
        self, config: LlmConfig, messages: Sequence[dict[str, str]], response_model: type[BaseModel]
    ) -> tuple[Any, str]:
        self.calls.append(list(messages))
        response = self.responses.pop(0) if self.responses else Extraction(forecasts=[])
        if isinstance(response, Exception):
            raise response
        return response, self.model


def _found(item: int, subject: str, value: float, **overrides: Any) -> ExtractedForecast:
    fields: dict[str, Any] = dict(
        item=item,
        institution="Goldman Sachs",
        subject=subject,
        value=value,
        horizon="year-end",
        confidence=0.8,
    )
    fields.update(overrides)
    return ExtractedForecast(**fields)


def _extractor(store: FakeStore, complete: FakeComplete) -> LlmExtractor:
    return LlmExtractor(CONFIG, store.news, complete=complete)


def test_sends_only_candidates_numbered_in_batches() -> None:
    store = FakeStore()
    candidates = [
        _item(f"Goldman Sachs raises gold target to {3900 + index}") for index in range(3)
    ]
    noise = _item("Markets wrap: stocks drift lower")
    store.news.add(noise, *candidates)
    complete = FakeComplete()
    small_batches = LlmExtractor(CONFIG, store.news, complete=complete, batch_size=2)
    small_batches.fetch(NOW - DAY)
    assert len(complete.calls) == 2
    user_messages = [call[-1]["content"] for call in complete.calls]
    assert "[0]" in user_messages[0] and "[1]" in user_messages[0] and "[2]" not in user_messages[0]
    assert "[0]" in user_messages[1]
    assert not any("Markets wrap" in message for message in user_messages)
    assert all(call[0]["role"] == "system" for call in complete.calls)


def test_nothing_to_send_means_no_call() -> None:
    store = FakeStore()
    store.news.add(_item("Markets wrap: stocks drift lower"))
    complete = FakeComplete()
    assert _extractor(store, complete).fetch(NOW - DAY).asset == ()
    assert complete.calls == []


def test_asset_subject_becomes_a_forecast_asset() -> None:
    store = FakeStore()
    item = _item("Goldman Sachs raises gold target to 4,000 by year-end", published_at=NOW - DAY)
    store.news.add(item)
    complete = FakeComplete(Extraction(forecasts=[_found(0, "XAUUSD", 4000.0)]), model="router/x")
    forecasts = _extractor(store, complete).fetch(NOW - 2 * DAY)
    assert forecasts.macro == ()
    [forecast] = forecasts.asset
    assert forecast == ForecastAsset.new(
        institution="goldman_sachs",
        asset="XAUUSD",
        horizon_date=date(2026, 12, 31),
        horizon_label="year-end",
        value=4000.0,
        published_at=NOW - DAY,
        source_url=item.url,
        source_kind="extracted",
        confidence=0.8,
        model="router/x",
    )


def test_economy_metric_subject_becomes_a_forecast_macro() -> None:
    store = FakeStore()
    item = _item("Fed dot plot sees funds rate at 3.4% by end-2026")
    store.news.add(item)
    complete = FakeComplete(
        Extraction(
            forecasts=[
                _found(0, "united_states:policy_rate", 3.4, institution="Fed", horizon="end-2026")
            ]
        )
    )
    forecasts = _extractor(store, complete).fetch(NOW - DAY)
    assert forecasts.asset == ()
    [forecast] = forecasts.macro
    assert isinstance(forecast, ForecastMacro)
    assert (forecast.institution, forecast.economy, forecast.metric) == (
        "fed",
        "united_states",
        "policy_rate",
    )
    assert forecast.horizon_date == date(2026, 12, 31)


@pytest.mark.parametrize(
    "bad",
    [
        _found(0, "XXXUSD", 0.85),  # asset not tracked
        _found(0, "mars:cpi", 2.0),  # unknown economy
        _found(0, "united_states:house_prices", 2.0),  # unknown metric
        _found(0, "XAUUSD", 4000.0, horizon="when the Fed cuts"),  # unparseable horizon
        _found(7, "XAUUSD", 4000.0),  # item index outside the batch
    ],
)
def test_unmappable_forecasts_are_dropped_with_a_warning(
    bad: ExtractedForecast, caplog: pytest.LogCaptureFixture
) -> None:
    store = FakeStore()
    store.news.add(_item("Goldman Sachs raises gold target to 4,000"))
    complete = FakeComplete(Extraction(forecasts=[bad, _found(0, "XAUUSD", 4100.0)]))
    with caplog.at_level(logging.WARNING, logger="manc.forecasts"):
        forecasts = _extractor(store, complete).fetch(NOW - DAY)
    assert [forecast.value for forecast in forecasts.asset] == [4100.0]
    assert any("dropped" in record.message for record in caplog.records)


def test_same_call_in_two_articles_keeps_the_earliest_sighting() -> None:
    store = FakeStore()
    later = _item("Goldman Sachs sees gold at 4,000 by year-end", published_at=NOW)
    earlier = _item("Goldman raises gold target to $4,000", published_at=NOW - 3 * DAY)
    store.news.add(later, earlier)  # the repository returns oldest first
    complete = FakeComplete(
        Extraction(forecasts=[_found(0, "XAUUSD", 4000.0), _found(1, "XAUUSD", 4000.0)])
    )
    [forecast] = _extractor(store, complete).fetch(NOW - 7 * DAY).asset
    assert forecast.published_at == NOW - 3 * DAY
    assert forecast.source_url == earlier.url


def test_a_failing_batch_contributes_nothing_and_others_still_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = FakeStore()
    store.news.add(
        _item("UBS raises gold target to 3,900"),
        _item("JPMorgan expects EUR/USD at 1.20 in 12 months"),
    )
    complete = FakeComplete(
        LlmError("every model failed"),
        Extraction(
            forecasts=[_found(0, "EURUSD", 1.20, institution="JPMorgan", horizon="12 months")]
        ),
    )
    extractor = LlmExtractor(CONFIG, store.news, complete=complete, batch_size=1)
    with caplog.at_level(logging.WARNING, logger="manc.forecasts"):
        forecasts = extractor.fetch(NOW - DAY)
    assert [forecast.asset for forecast in forecasts.asset] == ["EURUSD"]
    assert any("batch" in record.message for record in caplog.records)


def test_prompt_names_assets_economies_metrics_and_institutions() -> None:
    store = FakeStore()
    store.news.add(_item("UBS raises gold target to 3,900"))
    complete = FakeComplete()
    _extractor(store, complete).fetch(NOW - DAY)
    system = complete.calls[0][0]["content"]
    for needle in ("EURUSD", "united_states", "policy_rate", "goldman_sachs", "economy:metric"):
        assert needle in system
