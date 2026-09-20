"""CoinMarketCap's Crypto Fear & Greed index through the keyless public API.

One market-wide reading a day (0 fear .. 100 greed), stored under every coin so the per-coin
panel shows it without a special case. History is paged newest first.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime

import httpx

from manc.formulas.contract import AssetSpec
from manc.http import Client
from manc.models import ChainMetric

log = logging.getLogger(__name__)

SOURCE = "coinmarketcap"
METRIC = "fear_greed"
ENDPOINT = "https://pro-api.coinmarketcap.com/public-api/v3/fear-and-greed/historical"
PAGE = 500  # the most the endpoint returns per call; `start` is 1-based from the newest row


class FearGreed:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or Client()

    def fetch(self, assets: Sequence[AssetSpec], start: date, end: date) -> list[ChainMetric]:
        coins = [asset for asset in assets if asset.chain]
        if not coins:
            return []
        readings: dict[date, float] = {}
        offset = 1
        try:
            while True:
                response = self.client.get(ENDPOINT, params={"limit": PAGE, "start": offset})
                response.raise_for_status()
                rows = response.json().get("data", [])
                for row in rows:
                    day = datetime.fromtimestamp(int(row["timestamp"]), tz=UTC).date()
                    if start <= day <= end:
                        readings[day] = float(row["value"])
                oldest = min(
                    (datetime.fromtimestamp(int(row["timestamp"]), tz=UTC).date() for row in rows),
                    default=None,
                )
                if len(rows) < PAGE or oldest is None or oldest <= start:
                    break
                offset += PAGE
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            log.warning("%s fear & greed: %s; keeping %d days", SOURCE, error, len(readings))
        return [
            ChainMetric(asset=coin.symbol, date=day, metric=METRIC, value=value, source=SOURCE)
            for coin in coins
            for day, value in sorted(readings.items())
        ]
