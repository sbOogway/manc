"""Yahoo Finance daily closes through `yfinance` (blueprint section 4), display only.

Stooq's CSV endpoint, the planned first source, sits behind a JavaScript challenge since
2026-09 and Yahoo's chart endpoint refuses plain requests; `yfinance` keeps the session Yahoo
wants, so it is the client here. One `history` call per asset, a failing ticker is a warning.
"""

import logging
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import TYPE_CHECKING

from manc.formulas.contract import AssetSpec
from manc.models import SpotPrice

if TYPE_CHECKING:
    from pandas import DataFrame

log = logging.getLogger(__name__)

SOURCE = "yahoo"
LOOKBACK_DAYS = 7  # enough to reach the last session across any weekend or holiday run
History = Callable[[str, date, date], "DataFrame"]  # ticker, start, end (exclusive)


def yfinance_history(ticker: str, start: date, end: date) -> "DataFrame":
    import yfinance  # slow import, and tests replay recorded frames instead

    return yfinance.Ticker(ticker).history(
        start=start.isoformat(), end=end.isoformat(), interval="1d", auto_adjust=False
    )


class YahooSpot:
    def __init__(self, history: History | None = None) -> None:
        self.history = history or yfinance_history

    def fetch(self, assets: Sequence[AssetSpec], day: date) -> list[SpotPrice]:
        """The last close on or before `day` for every asset with a yahoo ticker."""
        prices: list[SpotPrice] = []
        for asset in assets:
            ticker = asset.spot.get(SOURCE)
            if ticker is None:
                log.warning("spot %s skipped: no %s ticker in config", asset.symbol, SOURCE)
                continue
            try:
                frame = self.history(
                    ticker, day - timedelta(days=LOOKBACK_DAYS), day + timedelta(days=1)
                )
            except (
                Exception
            ) as error:  # yfinance raises many kinds; one ticker must not stop the rest
                log.warning("spot %s (%s) skipped: %s", asset.symbol, ticker, error)
                continue
            price = _last_close(asset.symbol, frame, day)
            if price is None:
                log.warning(
                    "spot %s (%s) skipped: no close on or before %s", asset.symbol, ticker, day
                )
                continue
            prices.append(price)
        return prices


def _last_close(symbol: str, frame: "DataFrame", day: date) -> SpotPrice | None:
    """Rows are one session each, indexed by the exchange's local midnight; keep the last <= day."""
    if "Close" not in frame:
        return None
    closes = [
        (session.date(), float(close))
        for session, close in frame["Close"].items()
        if close == close and session.date() <= day  # NaN != NaN drops sessions without a close
    ]
    if not closes:
        return None
    session_date, close = max(closes, key=lambda session_close: session_close[0])
    return SpotPrice(asset=symbol, date=session_date, close=close, source=SOURCE)
