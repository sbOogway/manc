"""Coin Metrics Community API (docs/on-chain-sources.md): coins with an id, one request, no key.

Daily rows complete about 02:30 UTC the next day. Data licensed CC BY-NC 4.0; the site
credits the source.
"""

import logging
from collections.abc import Sequence
from datetime import date, datetime

import httpx

from manc.formulas.contract import AssetSpec
from manc.http import Client
from manc.models import ChainMetric

log = logging.getLogger(__name__)

SOURCE = "coinmetrics"
ENDPOINT = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
METRICS = {  # Coin Metrics name -> ours
    "AdrActCnt": "active_addresses",
    "CapMVRVCur": "mvrv",
    "FlowInExUSD": "exchange_inflow_usd",
    "FlowOutExUSD": "exchange_outflow_usd",
}
PAGE_SIZE = 10000


class CoinMetrics:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or Client()

    def fetch(self, assets: Sequence[AssetSpec], start: date, end: date) -> list[ChainMetric]:
        symbols = {asset.chain[SOURCE]: asset.symbol for asset in assets if SOURCE in asset.chain}
        if not symbols:
            return []
        params = {
            "assets": ",".join(symbols),
            "metrics": ",".join(METRICS),
            "frequency": "1d",
            "start_time": start.isoformat(),
            "end_time": end.isoformat(),
            "page_size": PAGE_SIZE,
        }
        rows: list[ChainMetric] = []
        url: str | None = ENDPOINT
        try:
            while url:
                response = self.client.get(url, params=params if url == ENDPOINT else None)
                response.raise_for_status()
                body = response.json()
                rows.extend(_rows(body.get("data", []), symbols))
                url = body.get("next_page_url")
        except (httpx.HTTPError, ValueError) as error:
            log.warning("%s: %s; keeping %d rows", SOURCE, error, len(rows))
        return rows


def _rows(data: list[dict], symbols: dict[str, str]) -> list[ChainMetric]:
    rows = []
    for record in data:
        symbol = symbols.get(record.get("asset", ""))
        if symbol is None:
            continue
        day = datetime.fromisoformat(record["time"].replace("Z", "+00:00")).date()
        for name, metric in METRICS.items():
            value = record.get(name)
            if value in (None, ""):
                continue
            rows.append(
                ChainMetric(
                    asset=symbol, date=day, metric=metric, value=float(value), source=SOURCE
                )
            )
    return rows
