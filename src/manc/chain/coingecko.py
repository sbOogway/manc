"""CoinGecko's community votes per coin, keyless: a snapshot for the run's day, no history.

The keyless tier is rate limited by IP, so the coins are fetched one at a time with a pause
between them and a longer wait after a 429.
"""

import logging
import time
from collections.abc import Callable, Sequence
from datetime import date

import httpx

from manc.formulas.contract import AssetSpec
from manc.http import Client
from manc.models import ChainMetric

log = logging.getLogger(__name__)

SOURCE = "coingecko"
API = "https://api.coingecko.com/api/v3"
PAUSE_SECONDS = (
    15.0  # between coins: the keyless tier allowed about five calls a minute on 2026-09-20
)
RETRY_SECONDS = 60.0  # after a 429, once
FIELDS = {  # CoinGecko field -> ours
    "sentiment_votes_up_percentage": "sentiment_votes_up_pct",
    "watchlist_portfolio_users": "watchlist_users",
}
PARAMS = {
    "localization": "false",
    "tickers": "false",
    "market_data": "false",
    "community_data": "false",
    "developer_data": "false",
    "sparkline": "false",
}


def coin_url(coin_id: str) -> str:
    return f"{API}/coins/{coin_id}"


class CoinGecko:
    def __init__(
        self, client: httpx.Client | None = None, pause: Callable[[float], object] = time.sleep
    ) -> None:
        self.client = client or Client()
        self.pause = pause

    def fetch(self, assets: Sequence[AssetSpec], start: date, end: date) -> list[ChainMetric]:
        rows: list[ChainMetric] = []
        for asset in assets:
            coin_id = asset.chain.get(SOURCE)
            if coin_id is None:
                continue
            body = self._coin(asset.symbol, coin_id)
            if body is None:
                continue
            for field, metric in FIELDS.items():
                value = body.get(field)
                if value is None:
                    continue
                rows.append(ChainMetric(asset.symbol, end, metric, float(value), SOURCE))
            self.pause(PAUSE_SECONDS)
        return rows

    def _coin(self, symbol: str, coin_id: str) -> dict | None:
        for attempt in range(2):
            try:
                response = self.client.get(coin_url(coin_id), params=PARAMS)
                if response.status_code == 429 and attempt == 0:
                    self.pause(RETRY_SECONDS)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as error:
                log.warning("%s %s (%s): %s", SOURCE, symbol, coin_id, error)
                return None
        log.warning("%s %s (%s): still rate limited after a retry", SOURCE, symbol, coin_id)
        return None
