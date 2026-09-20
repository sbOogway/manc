"""Coin Metrics Community (blueprint section 4): daily on-chain metrics for six coins, no key."""

import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from manc.chain.coinmetrics import ENDPOINT, CoinMetrics
from manc.chain.interface import ChainProvider
from manc.config import load_config
from manc.models import ChainMetric

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "chain"
COINS = [asset for asset in load_config().assets if asset.kind == "crypto"]
START, END = date(2026, 9, 17), date(2026, 9, 19)


def serve(body: dict | None = None, **response_kwargs: object) -> respx.Route:
    if body is None and not response_kwargs:
        body = json.loads((FIXTURES / "coinmetrics.json").read_text())
    if body is not None:
        return respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=body))
    return respx.get(ENDPOINT).mock(return_value=httpx.Response(**response_kwargs))


def test_satisfies_protocol() -> None:
    assert isinstance(CoinMetrics(), ChainProvider)


@respx.mock
def test_one_request_for_every_coin_with_an_id_and_one_row_per_metric_and_day() -> None:
    route = serve()
    metrics = CoinMetrics().fetch(COINS, START, END)
    assert route.call_count == 1
    request = route.calls[0].request
    assert request.url.params["assets"] == "btc,eth,xrp,ada,ltc"  # SOL and BNB have no id
    assert request.url.params["frequency"] == "1d"
    assert request.url.params["start_time"] == "2026-09-17"
    assert request.url.params["end_time"] == "2026-09-19"
    assert "api_key" not in request.url.params
    by_key = {(row.asset, row.date, row.metric): row.value for row in metrics}
    assert by_key[("ADAUSD", date(2026, 9, 18), "active_addresses")] == 16702
    assert by_key[("ADAUSD", date(2026, 9, 18), "mvrv")] == pytest.approx(0.6114, abs=1e-4)
    assert by_key[("BTCUSD", date(2026, 9, 19), "exchange_inflow_usd")] == pytest.approx(
        1131196317.77, abs=0.01
    )
    assert ("ADAUSD", date(2026, 9, 18), "exchange_inflow_usd") not in by_key  # not offered
    assert {row.source for row in metrics} == {"coinmetrics"}
    assert all(isinstance(row, ChainMetric) for row in metrics)
    assert len({row.asset for row in metrics}) == 5


@respx.mock
def test_follows_the_next_page() -> None:
    first = {
        "data": [{"asset": "btc", "time": "2026-09-17T00:00:00.000000000Z", "AdrActCnt": "1"}],
        "next_page_url": f"{ENDPOINT}?next_page_token=abc",
    }
    second = {
        "data": [{"asset": "btc", "time": "2026-09-18T00:00:00.000000000Z", "AdrActCnt": "2"}]
    }
    route = respx.get(ENDPOINT).mock(
        side_effect=[httpx.Response(200, json=first), httpx.Response(200, json=second)]
    )
    metrics = CoinMetrics().fetch(COINS, START, END)
    assert route.call_count == 2
    assert [row.value for row in metrics] == [1.0, 2.0]


@respx.mock
def test_skips_blank_values_and_coins_without_an_id() -> None:
    serve({"data": [{"asset": "btc", "time": "2026-09-17T00:00:00.000000000Z", "AdrActCnt": None}]})
    assert CoinMetrics().fetch(COINS, START, END) == []
    assert (
        CoinMetrics().fetch([coin for coin in COINS if coin.symbol == "SOLUSD"], START, END) == []
    )


@respx.mock
def test_failure_is_a_warning_and_no_rows(caplog: pytest.LogCaptureFixture) -> None:
    serve(status_code=503, text="down")
    with caplog.at_level(logging.WARNING, logger="manc.chain"):
        assert CoinMetrics().fetch(COINS, START, END) == []
    assert "coinmetrics" in caplog.text and "503" in caplog.text
