"""Turn a horizon as stated ("12 months", "Q4 2026", "year-end") into one target date.

The date is the end of the stated period, relative to when the forecast was published, so
calls from different institutions line up on one axis (blueprint §4). Unknown phrasing is
`None` and the caller drops the forecast with a warning.
"""

import calendar
import re
from datetime import date, datetime

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "eighteen": 18,
}  # fmt: skip
_MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
_MONTHS |= {name.lower(): number for number, name in enumerate(calendar.month_abbr) if name}
_QUARTER_END_MONTH = {1: 3, 2: 6, 3: 9, 4: 12}
_YEAR = r"(?:20)?(\d{2})"  # 2027 or 27


def normalise(label: str, published_at: datetime) -> date | None:
    text = label.strip().lower().replace("\u2013", "-")  # en dash
    if not text:
        return None
    published = published_at.date()
    for parse in (_iso, _relative, _quarter, _half, _month_year, _month_only, _year_only):
        target = parse(text, published)
        if target is not None:
            return target
    return None


def _iso(text: str, published: date) -> date | None:
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _relative(text: str, published: date) -> date | None:
    """'12 months', '6-month', '6M', '1 year', 'two years' → published + that much."""
    match = re.search(
        rf"\b(\d+|{'|'.join(_NUMBER_WORDS)})\s*-?\s*(months?|m\b|years?|yrs?|y\b)", text
    )
    if match is None:
        return None
    amount = int(match.group(1)) if match.group(1).isdigit() else _NUMBER_WORDS[match.group(1)]
    months = amount * (12 if match.group(2).startswith("y") else 1)
    return _add_months(published, months)


def _quarter(text: str, published: date) -> date | None:
    """'Q4 2026', '4Q26', 'Q2' (next occurrence)."""
    match = re.search(rf"\bq([1-4])\s*{_YEAR}\b", text) or re.search(rf"\b([1-4])q{_YEAR}\b", text)
    if match:
        return _month_end(_full_year(match.group(2)), _QUARTER_END_MONTH[int(match.group(1))])
    match = re.search(r"\bq([1-4])\b", text)
    if match:
        return _next_period_end(published, _QUARTER_END_MONTH[int(match.group(1))])
    return None


def _half(text: str, published: date) -> date | None:
    """'H1 2027', 'second half of 2027', 'mid-2027' (= end of H1)."""
    match = re.search(rf"\b(?:h([12])|(first|second) half(?: of)?|(mid))\s*-?\s*{_YEAR}\b", text)
    if match is None:
        return None
    year = _full_year(match.group(4))
    if match.group(1) == "2" or match.group(2) == "second":
        return _month_end(year, 12)
    return _month_end(year, 6)


def _month_year(text: str, published: date) -> date | None:
    """'March 2027', 'end-March 2027', 'mar 27'."""
    match = re.search(rf"\b({'|'.join(_MONTHS)})\.?\s+{_YEAR}\b", text)
    if match is None:
        return None
    return _month_end(_full_year(match.group(2)), _MONTHS[match.group(1)])


def _month_only(text: str, published: date) -> date | None:
    """'by June' → the next June end after publication."""
    match = re.search(rf"\b({'|'.join(_MONTHS)})\b", text)
    if match is None:
        return None
    return _next_period_end(published, _MONTHS[match.group(1)])


def _year_only(text: str, published: date) -> date | None:
    """'year-end', 'end-2027', '2027 average', 'next year', 'this year' → 31 December."""
    if "next year" in text:
        return _month_end(published.year + 1, 12)
    if "this year" in text or re.search(r"year[\s-]*end|end[\s-]*of[\s-]*(?:the[\s-]*)?year", text):
        match = re.search(r"\b(20\d{2})\b", text)
        return _month_end(int(match.group(1)) if match else published.year, 12)
    match = re.search(r"\b(20\d{2})\b", text)
    return _month_end(int(match.group(1)), 12) if match else None


def _full_year(two_or_four: str) -> int:
    return 2000 + int(two_or_four)


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _next_period_end(published: date, month: int) -> date:
    """End of that month in the publication year, or the year after if already past."""
    candidate = _month_end(published.year, month)
    return candidate if candidate >= published else _month_end(published.year + 1, month)
