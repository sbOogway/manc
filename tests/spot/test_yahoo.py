"""Yahoo spot adapter (blueprint section 4): last daily close on or before the day, per asset."""

import logging
from datetime import date, timedelta
from pathlib import Path

import pandas
import pytest

from manc.config import load_config
from manc.formulas.contract import AssetSpec
from manc.spot.interface import SpotProvider
from manc.spot.yahoo import YahooSpot

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "spot"
ASSETS = load_config().assets
DAY = date(2026, 9, 17)  # the fixtures were recorded on this day, a Thursday


def recorded(ticker: str, start: date, end: date) -> pandas.DataFrame:
    """Replay a recorded `Ticker.history` frame; the index is tz-aware like the real one."""
    assert start < end
    return pandas.read_csv(FIXTURES / f"{ticker}.csv", index_col="Date", parse_dates=["Date"])


def failing(ticker: str, start: date, end: date) -> pandas.DataFrame:
    raise ConnectionError(f"{ticker}: no route to host")


def empty(ticker: str, start: date, end: date) -> pandas.DataFrame:
    return pandas.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])


def by_ticker(**handlers: object) -> object:
    """Dispatch per ticker; anything not named replays the recording."""

    def history(ticker: str, start: date, end: date) -> pandas.DataFrame:
        return handlers.get(ticker.replace("=", "").replace("^", "").replace("-", ""), recorded)(
            ticker, start, end
        )

    return history


def test_satisfies_protocol() -> None:
    assert isinstance(YahooSpot(), SpotProvider)


def test_one_close_per_asset_dated_by_its_own_session() -> None:
    prices = {price.asset: price for price in YahooSpot(recorded).fetch(ASSETS, DAY)}

    assert set(prices) == {asset.symbol for asset in ASSETS}
    assert prices["EURUSD"].close == pytest.approx(1.1481, abs=1e-4)
    assert prices["EURUSD"].date == DAY
    assert prices["SPX"].close == pytest.approx(7551.81, abs=1e-2)
    assert prices["SPX"].date == date(2026, 9, 16)  # no US session row for the 17th yet
    assert all(price.source == "yahoo" for price in prices.values())


def test_weekend_returns_the_last_session_before_it() -> None:
    saturday = date(2026, 9, 12)
    prices = {price.asset: price for price in YahooSpot(recorded).fetch(ASSETS, saturday)}

    assert prices["EURUSD"].date == date(2026, 9, 11)
    assert prices["BTCUSD"].date == saturday  # crypto trades every day


def test_history_window_ends_the_day_after_and_covers_a_week() -> None:
    windows: list[tuple[date, date]] = []

    def spy(ticker: str, start: date, end: date) -> pandas.DataFrame:
        windows.append((start, end))
        return recorded(ticker, start, end)

    YahooSpot(spy).fetch(ASSETS[:1], DAY)

    assert windows == [(date(2026, 9, 10), date(2026, 9, 18))]  # yfinance's `end` is exclusive


def test_asset_without_a_yahoo_ticker_is_skipped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    untracked = AssetSpec(symbol="NZDUSD", kind="forex", economies=("new_zealand",))

    with caplog.at_level(logging.WARNING, logger="manc.spot"):
        prices = YahooSpot(recorded).fetch([untracked, ASSETS[0]], DAY)

    assert [price.asset for price in prices] == ["EURUSD"]
    assert "NZDUSD" in caplog.text and "no yahoo ticker" in caplog.text


def test_one_failing_ticker_does_not_stop_the_rest(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="manc.spot"):
        prices = YahooSpot(by_ticker(GCF=failing)).fetch(ASSETS, DAY)

    assert {price.asset for price in prices} == {asset.symbol for asset in ASSETS} - {"XAUUSD"}
    assert "XAUUSD" in caplog.text and "no route to host" in caplog.text


def test_empty_history_is_a_warning_not_a_price(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="manc.spot"):
        prices = YahooSpot(by_ticker(CLF=empty)).fetch(ASSETS, DAY)

    assert "WTI" not in {price.asset for price in prices}
    assert "WTI" in caplog.text and "no close" in caplog.text


def test_only_closes_up_to_the_day_count() -> None:
    before_the_fixture = date(2026, 9, 9)

    prices = YahooSpot(recorded).fetch(ASSETS, before_the_fixture)

    assert prices == []


@pytest.mark.live
def test_live_yahoo_returns_a_recent_close() -> None:
    prices = YahooSpot().fetch(ASSETS[:1], date.today())

    assert len(prices) == 1
    assert prices[0].close > 0
    assert date.today() - prices[0].date <= timedelta(days=4)
