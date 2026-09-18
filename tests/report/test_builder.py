"""The report builder renders the stored inputs behind a score as markdown."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from manc.config import LlmConfig, load_config
from manc.formulas.contract import IndexScore
from manc.llm import LlmError
from manc.models import CalendarEvent, NewsItem, NewsTag
from manc.report.builder import Summary, build_report
from tests.fakes import FakeStore

CONFIG = load_config()
TODAY = date(2026, 9, 15)
NOON = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
DAY = timedelta(days=1)
SCORE = IndexScore(
    asset="EURUSD",
    date=TODAY,
    score=49.25,
    formula="v1",
    components={"N": 0.3, "S": -0.5, "R": 0.5},
    n_news=2,
    n_events=1,
)


class FakeComplete:
    """Replays one canned Summary per call and records what it was asked."""

    def __init__(self, *responses: Summary | Exception, model: str = "free/model") -> None:
        self.responses = list(responses)
        self.model = model
        self.calls: list[list[dict[str, str]]] = []

    def __call__(
        self, config: LlmConfig, messages: Sequence[dict[str, str]], response_model: type[BaseModel]
    ) -> tuple[Any, str]:
        self.calls.append(list(messages))
        response = self.responses.pop(0) if self.responses else Summary(paragraph="Quiet day.")
        if isinstance(response, Exception):
            raise response
        return response, self.model


def _event(
    event_id: str,
    when: datetime,
    *,
    country: str = "united_states",
    actual: float | None = None,
    importance: int = 3,
) -> CalendarEvent:
    return CalendarEvent(
        id=event_id,
        date=when,
        country=country,
        event="CPI YoY",
        category="inflation",
        importance=importance,
        consensus=3.0,
        previous=2.9,
        actual=actual,
    )


def _headline(store: FakeStore, title: str, direction: int, confidence: float) -> None:
    item = NewsItem.from_feed(
        source="reuters", title=title, url=f"https://x/{title}", published_at=NOON - DAY
    )
    store.news.add(item)
    store.tags.add(NewsTag(item.id, "EURUSD", direction, confidence, model="m"))


def _populated_store() -> FakeStore:
    store = FakeStore()
    store.events.add(
        _event("cpi", NOON - 2 * DAY, actual=3.1),
        _event("nfp", NOON + 3 * DAY),
        _event("ecb", NOON + 2 * DAY, country="euro_area"),
        _event("boj", NOON + DAY, country="japan"),  # not one of EURUSD's economies
        _event("stale", NOON - 10 * DAY, actual=2.0),  # outside the surprise window
        _event("far", NOON + 20 * DAY),  # outside the risk window
    )
    _headline(store, "Euro slips on hot US CPI", -1, 0.9)
    _headline(store, "ECB officials hint at a pause", 1, 0.4)
    _headline(store, "Nothing to see", 0, 0.9)
    return store


def test_header_carries_score_band_and_counts() -> None:
    report = build_report(FakeStore(), CONFIG, SCORE, complete=None)
    assert report.startswith("# EURUSD 2026-09-15: 49 neutral\n")
    assert "2 headlines, 1 released event" in report


def test_components_section_lists_every_component() -> None:
    report = build_report(FakeStore(), CONFIG, SCORE, complete=None)
    assert "## Components\n\n- N: +0.30\n- S: -0.50\n- R: +0.50\n" in report


def test_released_events_of_the_asset_economies_in_the_surprise_window() -> None:
    report = build_report(_populated_store(), CONFIG, SCORE, complete=None)
    released = report.split("## Released data\n")[1].split("## ")[0]
    assert "| 2026-09-13 | united_states | CPI YoY | 3.1 | 3 | 2.9 |" in released
    assert "stale" not in released and "2026-09-05" not in released


def test_events_ahead_of_the_asset_economies_in_the_risk_window() -> None:
    report = build_report(_populated_store(), CONFIG, SCORE, complete=None)
    ahead = report.split("## Ahead\n")[1].split("## ")[0]
    rows = [line for line in ahead.splitlines() if line.startswith("| 2026")]
    assert rows == [
        "| 2026-09-17 | euro_area | CPI YoY | high |",
        "| 2026-09-18 | united_states | CPI YoY | high |",
    ]


def test_headlines_carry_direction_source_confidence_strongest_first() -> None:
    report = build_report(_populated_store(), CONFIG, SCORE, complete=None)
    headlines = report.split("## Headlines\n")[1].split("\n---")[0]
    rows = [line for line in headlines.splitlines() if line.startswith("- ")]
    assert rows == [
        "- ▼ Euro slips on hot US CPI (reuters, 2026-09-14, 0.90)",
        "- ▲ ECB officials hint at a pause (reuters, 2026-09-14, 0.40)",
    ]


def test_empty_sections_say_so() -> None:
    report = build_report(FakeStore(), CONFIG, SCORE, complete=None)
    assert "## Released data\n\nNo releases in the window.\n" in report
    assert "## Ahead\n\nNothing scheduled.\n" in report
    assert "## Headlines\n\nNo directional headlines.\n" in report


def test_summary_paragraph_and_model_footer_when_the_llm_answers() -> None:
    complete = FakeComplete(Summary(paragraph="A hot CPI print outweighed euro-positive talk."))
    report = build_report(_populated_store(), CONFIG, SCORE, complete=complete)
    _header, summary, _rest = report.split("\n\n", 2)
    assert summary == "A hot CPI print outweighed euro-positive talk."
    assert report.endswith("\n---\n\nSummary by free/model.\n")


def test_llm_is_given_the_template_and_the_asset() -> None:
    complete = FakeComplete()
    build_report(_populated_store(), CONFIG, SCORE, complete=complete)
    [messages] = complete.calls
    assert messages[0]["role"] == "system"
    assert "EURUSD" in messages[0]["content"]
    assert "## Headlines" in messages[1]["content"]
    assert "Euro slips on hot US CPI" in messages[1]["content"]


def test_llm_failure_degrades_to_the_template() -> None:
    complete = FakeComplete(LlmError("all models failed"))
    report = build_report(_populated_store(), CONFIG, SCORE, complete=complete)
    assert report == build_report(_populated_store(), CONFIG, SCORE, complete=None)
    assert "Summary by" not in report
