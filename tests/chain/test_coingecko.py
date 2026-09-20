"""CoinGecko's per-coin community votes, keyless: a snapshot per coin, rate limited by IP."""

import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from manc.chain.coingecko import CoinGecko, coin_url
from manc.chain.interface import ChainProvider
from manc.config import load_config

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "chain"
COINS = [asset for asset in load_config().assets if asset.kind == "crypto"]
BTC = next(coin for coin in COINS if coin.symbol == "BTCUSD")
TODAY = date(2026, 9, 20)


def test_satisfies_protocol() -> None:
    assert isinstance(CoinGecko(pause=lambda seconds: None), ChainProvider)


@respx.mock
def test_votes_and_watchlist_for_the_end_day_only() -> None:
    body = json.loads((FIXTURES / "coingecko-bitcoin.json").read_text())
    route = respx.get(coin_url("bitcoin")).mock(return_value=httpx.Response(200, json=body))
    metrics = CoinGecko(pause=lambda seconds: None).fetch([BTC], date(2026, 9, 1), TODAY)
    assert route.call_count == 1
    assert route.calls[0].request.url.params["market_data"] == "false"
    assert {(row.metric, row.date, row.value, row.source) for row in metrics} == {
        ("sentiment_votes_up_pct", TODAY, 78.57, "coingecko"),
        ("watchlist_users", TODAY, 2452031.0, "coingecko"),
    }


@respx.mock
def test_pauses_between_coins_and_retries_a_rate_limit() -> None:
    pauses: list[float] = []
    body = json.loads((FIXTURES / "coingecko-bitcoin.json").read_text())
    for coin in COINS:
        respx.get(coin_url(coin.chain["coingecko"])).mock(
            side_effect=[
                httpx.Response(429),
                httpx.Response(200, json={**body, "id": coin.chain["coingecko"]}),
            ]
            if coin.symbol == "ETHUSD"
            else httpx.Response(200, json=body)
        )
    metrics = CoinGecko(pause=pauses.append).fetch(COINS, TODAY, TODAY)
    assert {row.asset for row in metrics} == {coin.symbol for coin in COINS}
    assert len(pauses) >= len(COINS)  # one pause per coin, plus the retry's back-off
    assert max(pauses) > min(pauses)  # the retry waited longer than the usual pause


@respx.mock
def test_a_coin_that_keeps_failing_is_a_warning_and_the_others_still_come(
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = json.loads((FIXTURES / "coingecko-bitcoin.json").read_text())
    respx.get(coin_url("bitcoin")).mock(return_value=httpx.Response(429))
    respx.get(coin_url("ethereum")).mock(return_value=httpx.Response(200, json=body))
    eth = next(coin for coin in COINS if coin.symbol == "ETHUSD")
    with caplog.at_level(logging.WARNING, logger="manc.chain"):
        metrics = CoinGecko(pause=lambda seconds: None).fetch([BTC, eth], TODAY, TODAY)
    assert {row.asset for row in metrics} == {"ETHUSD"}
    assert "coingecko" in caplog.text and "BTCUSD" in caplog.text


@respx.mock
def test_missing_votes_are_skipped() -> None:
    respx.get(coin_url("bitcoin")).mock(return_value=httpx.Response(200, json={"id": "bitcoin"}))
    assert CoinGecko(pause=lambda seconds: None).fetch([BTC], TODAY, TODAY) == []
