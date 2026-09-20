"""CoinMarketCap's Fear & Greed index, keyless: one market-wide reading a day, stored per coin."""

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from manc.chain.fear_greed import ENDPOINT, PAGE, FearGreed
from manc.chain.interface import ChainProvider
from manc.config import load_config

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "chain"
COINS = [asset for asset in load_config().assets if asset.kind == "crypto"]


def test_satisfies_protocol() -> None:
    assert isinstance(FearGreed(), ChainProvider)


@respx.mock
def test_one_reading_per_day_copied_to_every_coin_in_the_window() -> None:
    body = json.loads((FIXTURES / "cmc-fear-greed.json").read_text())  # 09-17, 09-18, 09-19
    route = respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=body))
    metrics = FearGreed().fetch(COINS, date(2026, 9, 18), date(2026, 9, 20))
    assert route.call_count == 1
    assert "X-CMC_PRO_API_KEY" not in route.calls[0].request.headers
    assert {row.metric for row in metrics} == {"fear_greed"}
    assert {row.source for row in metrics} == {"coinmarketcap"}
    assert sorted({row.date for row in metrics}) == [date(2026, 9, 18), date(2026, 9, 19)]
    assert {row.asset for row in metrics} == {coin.symbol for coin in COINS}
    by_key = {(row.asset, row.date): row.value for row in metrics}
    assert by_key[("BTCUSD", date(2026, 9, 19))] == 73
    assert by_key[("SOLUSD", date(2026, 9, 18))] == 73


@respx.mock
def test_pages_back_until_the_start_of_the_range() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params.get("start", "1"))
        first_day = 1789862400 - (start - 1) * 86400  # 2026-09-20 minus the offset, one row a day
        rows = [
            {
                "timestamp": str(first_day - offset * 86400),
                "value": 50 + offset,
                "value_classification": "Neutral",
            }
            for offset in range(PAGE)
        ]
        return httpx.Response(200, json={"data": rows})

    route = respx.get(ENDPOINT).mock(side_effect=page)
    metrics = FearGreed().fetch(
        COINS[:1],
        date(2026, 9, 20) - timedelta(days=PAGE + 10),
        date(2026, 9, 20),
    )
    assert route.call_count == 2  # the first page did not reach the start of the range
    assert len(metrics) == PAGE + 11
    assert min(row.date for row in metrics) == date(2026, 9, 20) - (PAGE + 10) * __import__(
        "datetime"
    ).timedelta(days=1)


@respx.mock
def test_failure_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    respx.get(ENDPOINT).mock(return_value=httpx.Response(503))
    with caplog.at_level(logging.WARNING, logger="manc.chain"):
        assert FearGreed().fetch(COINS, date(2026, 9, 19), date(2026, 9, 20)) == []
    assert "coinmarketcap" in caplog.text


def test_nothing_without_coins() -> None:
    assert FearGreed().fetch([], date(2026, 9, 19), date(2026, 9, 20)) == []
