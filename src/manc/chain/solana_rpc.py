"""Solana public RPC (docs/on-chain-sources.md): throughput from the recent performance samples.

The node keeps at most 720 one-minute samples, so this is today's reading only: the mean
of non-vote transactions per second over the last hours. No history to backfill.
"""

import logging
from collections.abc import Sequence
from datetime import date

import httpx

from manc.formulas.contract import AssetSpec
from manc.http import Client
from manc.models import ChainMetric

log = logging.getLogger(__name__)

SOURCE = "solana_rpc"
RPC_URL = "https://api.mainnet-beta.solana.com"
SYMBOL = "SOLUSD"
SAMPLES = 720  # the most the node returns: twelve hours


class SolanaRpc:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or Client()

    def fetch(self, assets: Sequence[AssetSpec], start: date, end: date) -> list[ChainMetric]:
        if not any(asset.symbol == SYMBOL for asset in assets):
            return []
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getRecentPerformanceSamples",
            "params": [SAMPLES],
        }
        try:
            response = self.client.post(RPC_URL, json=request)
            response.raise_for_status()
            samples = response.json()["result"]
            rates = [
                sample["numNonVoteTransactions"] / sample["samplePeriodSecs"]
                for sample in samples
                if sample["samplePeriodSecs"]
            ]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            log.warning("%s: %s", SOURCE, error)
            return []
        if not rates:
            return []
        return [ChainMetric(SYMBOL, end, "tx_per_second", sum(rates) / len(rates), SOURCE)]
