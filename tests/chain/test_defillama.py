"""DefiLlama (blueprint section 4): daily fees, TVL and stablecoin supply per chain, no key."""

import json
import logging
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from manc.chain.defillama import DefiLlama, fees_url, stablecoins_url, tvl_url
from manc.chain.interface import ChainProvider
from manc.config import load_config

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "chain"
SOL = next(asset for asset in load_config().assets if asset.symbol == "SOLUSD")
START, END = date(2026, 9, 17), date(2026, 9, 20)


def serve_solana() -> None:
    for url, name in (
        (fees_url("solana"), "defillama-fees-solana.json"),
        (tvl_url("solana"), "defillama-tvl-solana.json"),
        (stablecoins_url("solana"), "defillama-stablecoins-solana.json"),
    ):
        respx.get(url).mock(
            return_value=httpx.Response(200, json=json.loads((FIXTURES / name).read_text()))
        )


def test_satisfies_protocol() -> None:
    assert isinstance(DefiLlama(), ChainProvider)


@respx.mock
def test_three_series_per_chain_windowed_to_the_range() -> None:
    serve_solana()
    metrics = DefiLlama().fetch([SOL], START, END)
    by_key = {(row.date, row.metric): row.value for row in metrics}
    assert by_key[(date(2026, 9, 20), "fees_usd")] == pytest.approx(14277506.29, abs=0.01)
    assert by_key[(date(2026, 9, 20), "tvl_usd")] == 6126275871
    assert by_key[(date(2026, 9, 20), "stablecoins_usd")] == pytest.approx(15739176805.58, abs=0.01)
    assert {row.asset for row in metrics} == {"SOLUSD"}
    assert {row.source for row in metrics} == {"defillama"}
    assert min(row.date for row in metrics) >= START
    assert len([row for row in metrics if row.metric == "fees_usd"]) == 4


@respx.mock
def test_a_failing_series_is_a_warning_and_the_others_still_come(
    caplog: pytest.LogCaptureFixture,
) -> None:
    serve_solana()
    respx.get(tvl_url("solana")).mock(return_value=httpx.Response(500))
    with caplog.at_level(logging.WARNING, logger="manc.chain"):
        metrics = DefiLlama().fetch([SOL], START, END)
    assert {row.metric for row in metrics} == {"fees_usd", "stablecoins_usd"}
    assert "defillama" in caplog.text and "500" in caplog.text


def test_assets_without_a_defillama_chain_are_skipped() -> None:
    eurusd = next(asset for asset in load_config().assets if asset.symbol == "EURUSD")
    assert DefiLlama().fetch([eurusd], START, END) == []
