"""Benchmark of the configured tagger model on recorded headlines, one test per headline.

`tests/fixtures/analysis/*.json` hold the headlines with the direction a market reader
expects per asset (+1 / -1; 0 means no directional call, a 0 tag or none; an empty
mapping means nothing directional on any asset):

- `synthetic_headlines.json`: textbook cases, market-flavoured noise and two-sided prints
- `real_headlines.json`: rows copied verbatim from the store as fetched 2026-09-13..16, the
  pipeline's first days (the Iran war had oil above $100 and Hormuz traffic in single
  digits, the 10-year Treasury yield had crossed 5%, the Fed was expected to hike on the
  16th, the Senate had just rejected the Clarity Act and the BoJ was about to raise rates)

One model call per fixture file, skipped by default. Run with
`uv run pytest tests/analysis/test_live_tagger.py -m live -s -vv --no-cov`: `-s` prints every
tag the model produced, `-vv` every wrong one. `MANC_LIVE_MODEL=openrouter/<vendor>/<model>`
benchmarks another model without touching config/llm.yaml (no fallback, so its own failures
show), `MANC_LIVE_BATCH=<n>` overrides `llm.batch_size`, and an Ollama server works too:
`OLLAMA_API_BASE=https://host MANC_LIVE_MODEL=ollama_chat/gemma4:12b`.

Checked 2026-09-17 on the synthetic set: nex-agi/nex-n2.5-pro:free passes everything,
nemotron-3-super-120b and nex-n2.5-mini miss one each, liquid/lfm-2.5-2.6b never tags
EURUSD, and the openrouter/free router lands on any of them. On the real set nemotron tags
every asset for the first few lines of a batch and then stops, whatever the batch size.
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from manc.analysis.llm import LlmAnalyzer
from manc.config import load_config
from manc.models import NewsItem

CONFIG = load_config()
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "analysis"
SETS = ("synthetic", "real")
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


CASES = {name: load_cases(name) for name in SETS}


@pytest.mark.parametrize("name", SETS)
def test_fixture_expectations_name_tracked_assets_and_valid_directions(name: str) -> None:
    symbols = {asset.symbol for asset in CONFIG.assets}
    for case in CASES[name]:
        assert set(case.expected) <= symbols, case.item.title
        assert set(case.expected.values()) <= {-1, 0, 1}, case.item.title
    assert len({case.item.id for case in CASES[name]}) == len(CASES[name])


def _mismatches(case: Case, directions: Directions) -> list[str]:
    if not case.expected:
        return [
            f"{asset} {direction:+d}"
            for (news_id, asset), direction in directions.items()
            if news_id == case.item.id and direction != 0
        ]
    mismatches = []
    for asset, wanted in case.expected.items():
        got = directions.get((case.item.id, asset))
        if wanted == 0 and got in (None, 0):
            continue
        if got != wanted:
            shown = "no tag" if got is None else f"{got:+d}"
            mismatches.append(f"{asset}: wanted {wanted:+d}, got {shown}")
    return mismatches


@pytest.fixture(scope="module")
def tagged() -> Callable[[str], Directions]:
    """One model call per fixture set, shared by every test of that set."""
    config = CONFIG
    override = os.environ.get("MANC_LIVE_MODEL")
    if override:
        config = replace(CONFIG, llm=replace(CONFIG.llm, model=override, fallback=None))
    batch_size = int(os.environ.get("MANC_LIVE_BATCH") or config.llm.batch_size)
    analyzer = LlmAnalyzer(config, batch_size=batch_size)
    cache: dict[str, Directions] = {}

    def directions_for(name: str) -> Directions:
        if name not in cache:
            items = [case.item for case in CASES[name]]
            tags = analyzer.tag(items, config.assets)
            titles = {item.id: item.title for item in items}
            print(f"\n  --- {name}")
            for tag in tags:
                title = titles[tag.news_id][:52]
                print(f"  {title:<52} {tag.asset:<7} {tag.direction:+d} {tag.confidence:.2f}")
            print(f"  {len(tags)} tags from {tags[0].model if tags else 'no model'}")
            cache[name] = {(tag.news_id, tag.asset): tag.direction for tag in tags}
        return cache[name]

    return directions_for


@pytest.mark.live
@pytest.mark.skipif(
    not (os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OLLAMA_API_BASE")),
    reason="neither OPENROUTER_API_KEY nor OLLAMA_API_BASE is set",
)
@pytest.mark.parametrize(
    ("name", "case"),
    [(name, case) for name in SETS for case in CASES[name]],
    ids=[f"{name}: {case.item.title[:60]}" for name in SETS for case in CASES[name]],
)
def test_live_headline(name: str, case: Case, tagged: Callable[[str], Directions]) -> None:
    assert _mismatches(case, tagged(name)) == []
