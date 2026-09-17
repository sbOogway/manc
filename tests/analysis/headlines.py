"""Recorded headlines with the direction a market reader expects, shared by the tagger tests.

`tests/fixtures/analysis/*.json` rows carry `expected` per asset: +1 / -1, 0 for no
directional call (a 0 tag or none), an empty mapping for nothing directional on any asset.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from manc.models import NewsItem, NewsTag

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "analysis"
FETCHED = datetime(2026, 9, 16, 17, 0, tzinfo=UTC)

Directions = dict[tuple[str, str], int]


@dataclass(frozen=True)
class Case:
    item: NewsItem
    expected: dict[str, int]


def load_cases(name: str) -> list[Case]:
    rows = json.loads((FIXTURES / f"{name}_headlines.json").read_text())
    return [
        Case(
            item=NewsItem.from_feed(
                source=row["source"],
                title=row["title"],
                url=f"https://{row['source']}/{index}",
                published_at=FETCHED,
                summary=row.get("summary", ""),
            ),
            expected=row["expected"],
        )
        for index, row in enumerate(rows)
    ]


def directions(tags: list[NewsTag]) -> Directions:
    return {(tag.news_id, tag.asset): tag.direction for tag in tags}


def mismatches(case: Case, found: Directions) -> list[str]:
    """What the tags got wrong for one headline; empty when they meet the expectation."""
    if not case.expected:
        return [
            f"{asset} {direction:+d}"
            for (news_id, asset), direction in found.items()
            if news_id == case.item.id and direction != 0
        ]
    wrong = []
    for asset, wanted in case.expected.items():
        got = found.get((case.item.id, asset))
        if wanted == 0 and got in (None, 0):
            continue
        if got != wanted:
            shown = "no tag" if got is None else f"{got:+d}"
            wrong.append(f"{asset}: wanted {wanted:+d}, got {shown}")
    return wrong
