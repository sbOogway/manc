"""Render the inputs behind a score as markdown, with an LLM-written summary on top.

The sections are fixed so the dashboard can render the report with a plain markdown
component: header, summary, components, released data, ahead, headlines, footer. The band
and the headline weights come from `manc.queries`, so they are computed once.
"""

import logging
from collections.abc import Callable, Sequence
from datetime import timedelta
from typing import Any

from pydantic import BaseModel

from manc import llm, queries
from manc.config import Config
from manc.formulas.contract import AssetSpec, IndexScore
from manc.store.interface import Store

log = logging.getLogger(__name__)

Complete = Callable[..., tuple[Any, str]]

IMPORTANCE_LABELS = {1: "low", 2: "medium", 3: "high"}
AHEAD_MIN_IMPORTANCE = 2  # the events worth a line; the formula's R still sums every one
HEADLINES = 10  # the API serves the full list
DIRECTION_GLYPHS = {1: "▲", -1: "▼"}
SYSTEM_PROMPT = """\
You write the opening paragraph of a daily macro report for {symbol} ({kind}; economies: \
{economies}). The report below scores the macro backdrop from 0 (strong headwind) to 100 \
(strong tailwind); it is not a price forecast. In three or four plain sentences, say what \
the score is, what drove it (the data surprises, the headlines) and what scheduled risk lies \
ahead. Use only the facts in the report; no advice, no hedging, no bullet points."""


class Summary(BaseModel):
    paragraph: str


def build_report(
    store: Store, config: Config, score: IndexScore, *, complete: Complete | None
) -> str:
    """The markdown report for `score`; `complete=None` skips the LLM summary."""
    asset = _asset(config, score.asset)
    template = _template(store, config, asset, score)
    if complete is None:
        return template
    try:
        summary, model = complete(config.llm, _messages(asset, template), Summary)
    except llm.LlmError as error:
        log.warning("report: %s %s without summary: %s", score.asset, score.date, error)
        return template
    header, body = template.split("\n\n", 1)
    return f"{header}\n\n{summary.paragraph.strip()}\n\n{body}\n---\n\nSummary by {model}.\n"


def _template(store: Store, config: Config, asset: AssetSpec, score: IndexScore) -> str:
    windows = config.scoring.windows
    released_start = score.date - timedelta(days=windows["released_days"])
    upcoming_end = score.date + timedelta(days=windows["upcoming_days"])
    events = [
        event
        for event in store.events.between(released_start, upcoming_end)
        if event.country in asset.economies
    ]
    # released: only what can surprise, a consensus and a category the asset reacts to
    released = sorted(
        (
            event
            for event in events
            if event.released
            and event.date.date() <= score.date
            and event.consensus is not None
            and asset.signs.get(event.country, {}).get(event.category, 0) != 0
        ),
        key=lambda event: (-event.importance, event.date),
    )
    ahead = [
        event
        for event in events
        if event.date.date() > score.date and event.importance >= AHEAD_MIN_IMPORTANCE
    ]
    headlines = queries.headlines_behind(store, config, asset.symbol, score.date)[:HEADLINES]

    sections = [
        f"# {score.asset} {score.date.isoformat()}: {score.score:.0f} "
        f"{queries.band(score.score, queries.scale_of(score.formula)).replace('_', ' ')}",
        "## Components\n\n"
        + "\n".join(f"- {name}: {value:+.2f}" for name, value in score.components.items())
        + f"\n\n{_count(score.n_news, 'headline')}, {_count(score.n_events, 'released event')}",
        "## Released data\n\n"
        + (
            _table(
                ("Date", "Country", "Event", "Actual", "Consensus", "Previous"),
                [
                    (
                        event.date.date().isoformat(),
                        event.country,
                        event.event,
                        _number(event.actual),
                        _number(event.consensus),
                        _number(event.previous),
                    )
                    for event in released
                ],
            )
            if released
            else "No releases in the window."
        ),
        "## Ahead\n\n"
        + (
            _table(
                ("Date", "Country", "Event", "Importance"),
                [
                    (
                        event.date.date().isoformat(),
                        event.country,
                        event.event,
                        IMPORTANCE_LABELS.get(event.importance, str(event.importance)),
                    )
                    for event in ahead
                ],
            )
            if ahead
            else "Nothing scheduled."
        ),
        "## Headlines\n\n"
        + (
            "\n".join(
                f"- {DIRECTION_GLYPHS[view.direction]} {view.title} "
                f"({view.source}, {view.published_at.date().isoformat()}, {view.confidence:.2f})"
                for view in headlines
            )
            if headlines
            else "No directional headlines."
        ),
    ]
    return "\n\n".join(sections) + "\n"


def _messages(asset: AssetSpec, template: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                symbol=asset.symbol, kind=asset.kind, economies=", ".join(asset.economies)
            ),
        },
        {"role": "user", "content": template},
    ]


def _asset(config: Config, symbol: str) -> AssetSpec:
    for asset in config.assets:
        if asset.symbol == symbol:
            return asset
    raise KeyError(symbol)


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = [_row(header), _row("---" for _column in header)]
    lines.extend(_row(row) for row in rows)
    return "\n".join(lines)


def _row(cells: Any) -> str:
    return "| " + " | ".join(cells) + " |"


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.12g}"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}{'' if number == 1 else 's'}"
