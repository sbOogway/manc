"""World Bank Commodity Markets Outlook (blueprint section 4): gold's annual averages.

The commodity-markets page links the latest `CMO-<Month>-<Year>-Forecasts.pdf`; the same path
with `.xlsx` is the forecast table. Its one sheet has the release date in the title row, a
header row with the forecast years as `2026f`, and one row per commodity with the unit and
the annual averages. Brent and gold map to tracked assets.
"""

import logging
import re
from datetime import UTC, date, datetime
from io import BytesIO
from typing import Any

import httpx
import openpyxl

from manc.http import Client
from manc.models import ForecastAsset, Forecasts

log = logging.getLogger(__name__)

OUTLOOK_URL = "https://www.worldbank.org/en/research/commodity-markets"
COMMODITIES = {"Crude oil, Brent": "BRENT", "Gold": "XAUUSD"}
_FORECASTS_LINK = re.compile(
    r'href="(https://thedocs\.worldbank\.org/[^"]*/CMO-[^"/]*-Forecasts)\.pdf"'
)
_RELEASED = re.compile(r"Released:\s*(\w+ \d{1,2}, \d{4})")
_FORECAST_YEAR = re.compile(r"^(\d{4})f$")


class WorldBankOutlook:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or Client()

    def fetch(self, since: datetime) -> Forecasts:
        """The latest edition's gold averages, when it was released on or after `since`."""
        url = self._workbook_url()
        if url is None:
            return Forecasts()
        try:
            response = self.client.get(url)
            response.raise_for_status()
            released, averages = parse_workbook(response.content)
        except (httpx.HTTPError, ValueError) as error:
            log.warning("world bank outlook skipped: %s", error)
            return Forecasts()
        if released < since.date():
            log.debug("world bank outlook of %s predates %s", released, since.date())
            return Forecasts()
        rows = tuple(
            ForecastAsset.new(
                institution="world_bank",
                asset=asset,
                horizon_date=date(year, 12, 31),
                horizon_label=f"{year} average",
                value=value,
                published_at=datetime(released.year, released.month, released.day, tzinfo=UTC),
                source_url=url,
                source_kind="structured",
                confidence=1.0,
            )
            for asset, year, value in averages
        )
        log.debug("world bank outlook %s: %d averages", released, len(rows))
        return Forecasts(asset=rows)

    def _workbook_url(self) -> str | None:
        try:
            response = self.client.get(OUTLOOK_URL)
            response.raise_for_status()
        except httpx.HTTPError as error:
            log.warning("world bank outlook skipped: %s", error)
            return None
        match = _FORECASTS_LINK.search(response.text)
        if match is None:
            log.warning("world bank outlook skipped: no forecasts link on %s", OUTLOOK_URL)
            return None
        return f"{match.group(1)}.xlsx"


def parse_workbook(content: bytes) -> tuple[date, list[tuple[str, int, float]]]:
    """(release date, [(asset, forecast year, annual average)]) from the forecast sheet."""
    try:
        sheet = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)["Forecast"]
    except Exception as error:  # openpyxl raises zipfile, KeyError and its own errors
        raise ValueError(f"unreadable workbook: {error}") from error
    rows = [list(row) for row in sheet.iter_rows(values_only=True)]
    released = _release_date(rows)
    year_columns = _year_columns(rows)
    averages = []
    for row in rows:
        asset = COMMODITIES.get(str(row[0]).strip()) if row and row[0] is not None else None
        if asset is None:
            continue
        for year, column in year_columns:
            if isinstance(row[column], int | float):
                averages.append((asset, year, float(row[column])))
    return released, averages


def _release_date(rows: list[list[Any]]) -> date:
    for row in rows[:3]:
        for cell in row:
            match = _RELEASED.search(str(cell)) if cell is not None else None
            if match:
                return datetime.strptime(match.group(1), "%B %d, %Y").date()
    raise ValueError("unreadable workbook: no release date in the title rows")


def _year_columns(rows: list[list[Any]]) -> list[tuple[int, int]]:
    """(forecast year, column) for the level columns: the first `YYYYf` cell of each year."""
    for row in rows[:6]:
        columns: dict[int, int] = {}
        for index, cell in enumerate(row):
            match = _FORECAST_YEAR.match(str(cell)) if cell is not None else None
            if match:
                columns.setdefault(int(match.group(1)), index)
        if columns:
            return sorted(columns.items())
    raise ValueError("unreadable workbook: no forecast-year header")
