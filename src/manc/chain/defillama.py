"""DefiLlama (docs/on-chain-sources.md): daily fees, TVL and stablecoin supply per chain, no key."""

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime

import httpx

from manc.formulas.contract import AssetSpec
from manc.http import Client
from manc.models import ChainMetric

log = logging.getLogger(__name__)

SOURCE = "defillama"
API = "https://api.llama.fi"
STABLECOINS_API = "https://stablecoins.llama.fi"


def fees_url(chain: str) -> str:
    return f"{API}/overview/fees/{chain}"


def tvl_url(chain: str) -> str:
    return f"{API}/v2/historicalChainTvl/{chain}"


def stablecoins_url(chain: str) -> str:
    return f"{STABLECOINS_API}/stablecoincharts/{chain}"


def _fees(body: dict) -> list[tuple[int, float]]:
    return [(int(stamp), float(value)) for stamp, value in body.get("totalDataChart", [])]


def _tvl(body: list) -> list[tuple[int, float]]:
    return [(int(point["date"]), float(point["tvl"])) for point in body]


def _stablecoins(body: list) -> list[tuple[int, float]]:
    return [
        (int(point["date"]), float(point["totalCirculatingUSD"].get("peggedUSD", 0.0)))
        for point in body
    ]


Parser = Callable[[object], list[tuple[int, float]]]
SERIES: dict[str, tuple[Callable[[str], str], Parser, dict[str, str]]] = {
    "fees_usd": (
        fees_url,
        _fees,
        {"dataType": "dailyFees", "excludeTotalDataChartBreakdown": "true"},
    ),
    "tvl_usd": (tvl_url, _tvl, {}),
    "stablecoins_usd": (stablecoins_url, _stablecoins, {}),
}


class DefiLlama:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or Client()

    def fetch(self, assets: Sequence[AssetSpec], start: date, end: date) -> list[ChainMetric]:
        rows: list[ChainMetric] = []
        for asset in assets:
            chain = asset.chain.get(SOURCE)
            if chain is None:
                continue
            for metric, (url_of, parse, params) in SERIES.items():
                try:
                    response = self.client.get(url_of(chain), params=params)
                    response.raise_for_status()
                    points = parse(response.json())
                except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as error:
                    log.warning("%s %s %s: %s", SOURCE, asset.symbol, metric, error)
                    continue
                for stamp, value in points:
                    day = datetime.fromtimestamp(stamp, tz=UTC).date()
                    if start <= day <= end:
                        rows.append(ChainMetric(asset.symbol, day, metric, value, SOURCE))
        return rows
