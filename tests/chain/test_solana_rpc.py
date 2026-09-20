"""Solana public RPC (blueprint section 4): today's throughput from the performance samples."""

import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from manc.chain.interface import ChainProvider
from manc.chain.solana_rpc import RPC_URL, SolanaRpc
from manc.config import load_config

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "chain"
COINS = [asset for asset in load_config().assets if asset.kind == "crypto"]
TODAY = date(2026, 9, 20)


def test_satisfies_protocol() -> None:
    assert isinstance(SolanaRpc(), ChainProvider)


@respx.mock
def test_mean_non_vote_transactions_per_second_for_the_end_day_only() -> None:
    body = json.loads((FIXTURES / "solana-performance.json").read_text())
    route = respx.post(RPC_URL).mock(return_value=httpx.Response(200, json=body))
    metrics = SolanaRpc().fetch(COINS, date(2026, 9, 1), TODAY)
    assert route.call_count == 1
    assert json.loads(route.calls[0].request.content)["method"] == "getRecentPerformanceSamples"
    [row] = metrics  # one coin, one day: samples cover the last hours only, no history
    assert (row.asset, row.date, row.metric, row.source) == (
        "SOLUSD",
        TODAY,
        "tx_per_second",
        "solana_rpc",
    )
    samples = body["result"]
    expected = sum(s["numNonVoteTransactions"] / s["samplePeriodSecs"] for s in samples) / len(
        samples
    )
    assert row.value == pytest.approx(expected)


@respx.mock
def test_failure_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    respx.post(RPC_URL).mock(return_value=httpx.Response(429))
    with caplog.at_level(logging.WARNING, logger="manc.chain"):
        assert SolanaRpc().fetch(COINS, TODAY, TODAY) == []
    assert "solana_rpc" in caplog.text
