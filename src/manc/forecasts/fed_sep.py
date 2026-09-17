"""Fed Summary of Economic Projections (blueprint section 4): the medians, one row per year.

The FOMC calendar page links the accessible projections page of every meeting that carried a
SEP (`fomcprojtabl<YYYYMMDD>.htm`, one older page spelled `fomcprojtable`). Its first table
lists, per variable, the median for each projection year and for the longer run; the "June
projection" rows below each variable repeat the previous release and are skipped, as is the
undated longer run.
"""

import logging
import re
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import httpx

from manc.http import Client
from manc.models import ForecastMacro, Forecasts

log = logging.getLogger(__name__)

CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
EASTERN = ZoneInfo("America/New_York")
RELEASE_CLOCK = (14, 0)  # the SEP comes out with the statement at 2 p.m. Eastern
METRICS = {
    "Change in real GDP": "gdp",
    "Unemployment rate": "unemployment",
    "PCE inflation": "pce",
    "Federal funds rate": "policy_rate",
}
_TABLE_LINK = re.compile(r"fomcprojtable?(\d{4})(\d{2})(\d{2})\.htm")
_YEAR = re.compile(r"^\d{4}$")


def table_url(day: date) -> str:
    return f"https://www.federalreserve.gov/monetarypolicy/fomcprojtabl{day:%Y%m%d}.htm"


class FedSep:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or Client()

    def fetch(self, since: datetime) -> Forecasts:
        """Every SEP released on or after `since`, newest last; a failing page is skipped."""
        rows: list[ForecastMacro] = []
        for day in self._releases(since.date()):
            rows.extend(self._fetch_release(day))
        return Forecasts(macro=tuple(rows))

    def _releases(self, since: date) -> list[date]:
        try:
            response = self.client.get(CALENDAR_URL)
            response.raise_for_status()
        except httpx.HTTPError as error:
            log.warning("fed sep calendar skipped: %s", error)
            return []
        found = {
            date(int(year), int(month), int(day))
            for year, month, day in _TABLE_LINK.findall(response.text)
        }
        return sorted(day for day in found if day >= since)

    def _fetch_release(self, day: date) -> list[ForecastMacro]:
        url = table_url(day)
        try:
            response = self.client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            log.warning("fed sep %s skipped: %s", day, error)
            return []
        medians = parse_medians(response.text)
        if not medians:
            log.warning("fed sep %s skipped: no projection table on %s", day, url)
            return []
        released_at = datetime(day.year, day.month, day.day, *RELEASE_CLOCK, tzinfo=EASTERN)
        rows = [
            ForecastMacro.new(
                institution="fed",
                economy="united_states",
                metric=metric,
                horizon_date=date(year, 12, 31),
                horizon_label=str(year),
                value=value,
                published_at=released_at.astimezone(UTC),
                source_url=url,
                source_kind="structured",
                confidence=1.0,
            )
            for metric, year, value in medians
        ]
        log.debug("fed sep %s: %d medians", day, len(rows))
        return rows


def parse_medians(page: str) -> list[tuple[str, int, float]]:
    """(metric, projection year, median) from the first table whose header says "Median"."""
    for table in _tables(page):
        if len(table) < 3 or not any("Median" in cell for cell in table[0]):
            continue
        years = _leading_years(table[1])  # the median block ends at "Longer run"
        medians = []
        for row in table[2:]:
            metric = METRICS.get(row[0]) if row else None
            if metric is None:
                continue
            for year, cell in zip(years, row[1:], strict=False):
                if cell:
                    medians.append((metric, year, float(cell)))
        return medians
    return []


def _leading_years(header: list[str]) -> list[int]:
    years: list[int] = []
    for cell in header:
        if not _YEAR.match(cell):
            break
        years.append(int(cell))
    return years


class _TableParser(HTMLParser):
    """Collects every <table> as rows of cell texts, tags stripped and whitespace collapsed."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _tables(page: str) -> list[list[list[str]]]:
    parser = _TableParser()
    parser.feed(page)
    return parser.tables
