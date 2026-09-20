"""Typed configuration loaded from the YAML files in config/ (blueprint section 8)."""

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

from manc.formulas.contract import AssetSpec
from manc.formulas.registry import get_formula

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent  # the YAML files ship inside the package
_VALID_SIGNS = {-1, 0, 1}
_VALID_CATEGORIES = {"inflation", "employment", "growth", "rates"}
_VALID_IMPORTANCE = {1, 2, 3}
FORECASTER_KINDS = ("bank", "official", "survey", "specialist")


@dataclass(frozen=True)
class FeedSpec:
    name: str
    url: str
    weight: float  # 0..1


@dataclass(frozen=True)
class ScoringConfig:
    formula: str
    params: Mapping[str, float]
    windows: Mapping[str, int]


@dataclass(frozen=True)
class LlmConfig:
    model: str
    fallback: str | None
    temperature: float
    batch_size: int


@dataclass(frozen=True)
class CalendarConfig:
    """Regex maps on the event name (first match wins) and country name aliases."""

    categories: tuple[tuple[re.Pattern[str], str], ...]
    importances: tuple[tuple[re.Pattern[str], int], ...]
    countries: Mapping[str, str]

    def category(self, event: str) -> str:
        return next(
            (category for pattern, category in self.categories if pattern.search(event)), "other"
        )

    def importance(self, event: str) -> int:
        return next(
            (importance for pattern, importance in self.importances if pattern.search(event)), 1
        )

    def country(self, name: str) -> str:
        return self.countries.get(name, name.strip().lower().replace(" ", "_"))


@dataclass(frozen=True)
class LexiconConfig:
    """Whole-word regexes for the offline analyzer (lexicon.yaml here explains the rules)."""

    economies: tuple[tuple[re.Pattern[str], str], ...]  # (term, economy key)
    categories: tuple[tuple[re.Pattern[str], str], ...]  # (term, event category)
    assets: tuple[
        tuple[re.Pattern[str], str, int], ...
    ]  # (term, symbol, sign of a positive phrase)
    polarity: tuple[tuple[re.Pattern[str], int], ...]  # (phrase, -1 | 0 | +1), in order


@dataclass(frozen=True)
class InstitutionSpec:
    name: str  # canonical, stored in the database: "goldman_sachs"
    aliases: tuple[str, ...]  # spellings seen in headlines
    kind: str  # bank | official | survey | specialist
    weight: float  # 0..1, orders the dashboard panel


@dataclass(frozen=True)
class ForecastQuery:
    asset: str
    feed: FeedSpec  # a Google News RSS query, fetched like any other feed


@dataclass(frozen=True)
class ForecastsConfig:
    institutions: tuple[InstitutionSpec, ...]
    signals: tuple[re.Pattern[str], ...]  # what makes a headline sound like a forecast
    metrics: tuple[str, ...]  # macro metrics the extractor may return
    queries: tuple[ForecastQuery, ...]
    min_confidence: float

    @property
    def query_feeds(self) -> tuple[FeedSpec, ...]:
        return tuple(query.feed for query in self.queries)

    @cached_property
    def alias_patterns(self) -> tuple[tuple[re.Pattern[str], str], ...]:
        """(whole-word, case-insensitive alias regex, canonical name), longest alias first."""
        pairs = [
            (alias, institution.name)
            for institution in self.institutions
            for alias in (institution.name, *institution.aliases)
        ]
        pairs.sort(key=lambda pair: -len(pair[0]))
        return tuple(
            (re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE), name)
            for alias, name in pairs
        )

    def canonical(self, name: str) -> str:
        """Alias → canonical name; anything unknown becomes its snake_case form."""
        wanted = name.strip().lower()
        for institution in self.institutions:
            if wanted in {alias.lower() for alias in (institution.name, *institution.aliases)}:
                return institution.name
        return re.sub(r"[^a-z0-9]+", "_", wanted).strip("_")


@dataclass(frozen=True)
class Config:
    assets: tuple[AssetSpec, ...]  # everything defined: tagging and old history know them all
    feeds: tuple[FeedSpec, ...]
    scoring: ScoringConfig
    llm: LlmConfig
    calendar: CalendarConfig
    forecasts: ForecastsConfig
    lexicon: LexiconConfig
    active_kinds: tuple[str, ...] = ()  # the kinds a run scores and the site lists; empty = all

    @property
    def active_assets(self) -> tuple[AssetSpec, ...]:
        if not self.active_kinds:
            return self.assets
        return tuple(asset for asset in self.assets if asset.kind in self.active_kinds)


def load_config(config_dir: Path = DEFAULT_CONFIG_DIR) -> Config:
    """One YAML file per Config field, each parsed by the loader registered in _SECTIONS."""
    raw_assets = _read(config_dir / "assets.yaml")
    config = Config(
        **{
            section: load(_read(config_dir / f"{section}.yaml"))
            for section, load in _SECTIONS.items()
        },
        active_kinds=tuple(raw_assets.get("active_kinds") or ()),
    )
    kinds = {asset.kind for asset in config.assets}
    for kind in config.active_kinds:
        if kind not in kinds:
            raise ValueError(f"assets: active kind {kind!r} matches no asset")
    symbols = {asset.symbol for asset in config.assets}
    for query in config.forecasts.queries:
        if query.asset not in symbols:
            raise ValueError(f"forecasts: query for unknown asset {query.asset!r}")
    economies = {economy for asset in config.assets for economy in asset.economies}
    for _pattern, economy in config.lexicon.economies:
        if economy not in economies:
            raise ValueError(f"lexicon: unknown economy {economy!r}")
    for _pattern, symbol, _sign in config.lexicon.assets:
        if symbol not in symbols:
            raise ValueError(f"lexicon: unknown asset {symbol!r}")
    return config


def _read(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"missing config file {path.name} in {path.parent}")
    with path.open() as handle:
        return yaml.safe_load(handle) or {}


def _load_assets(raw: dict[str, Any]) -> tuple[AssetSpec, ...]:
    specs = []
    for symbol, fields in raw.get("assets", {}).items():
        signs = {
            country: dict(categories) for country, categories in fields.get("signs", {}).items()
        }
        for country, categories in signs.items():
            for category, sign in categories.items():
                if sign not in _VALID_SIGNS:
                    raise ValueError(
                        f"{symbol}: sign for {country}/{category} must be -1, 0 or 1, got {sign}"
                    )
        specs.append(
            AssetSpec(
                symbol=symbol,
                kind=fields["kind"],
                economies=tuple(fields["economies"]),
                signs=signs,
                spot={source: str(ticker) for source, ticker in fields.get("spot", {}).items()},
                chain={source: str(name) for source, name in fields.get("chain", {}).items()},
            )
        )
    return tuple(specs)


def _unit_interval(value: Any, what: str) -> float:
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{what} must be within 0..1, got {number}")
    return number


def _load_feeds(raw: dict[str, Any]) -> tuple[FeedSpec, ...]:
    return tuple(
        FeedSpec(
            name=entry["name"],
            url=entry["url"],
            weight=_unit_interval(entry["weight"], f"feed {entry['name']}: weight"),
        )
        for entry in raw.get("feeds", [])
    )


def _load_scoring(raw: dict[str, Any]) -> ScoringConfig:
    formula = raw["formula"]
    get_formula(formula)  # raises ValueError for an unknown name
    return ScoringConfig(
        formula=formula,
        params={key: float(value) for key, value in (raw.get("params") or {}).items()},
        windows={key: int(value) for key, value in (raw.get("windows") or {}).items()},
    )


def _load_llm(raw: dict[str, Any]) -> LlmConfig:
    """`MANC_LLM_MODEL` wins over the file, for a machine without a Claude Code login."""
    fields = raw["llm"]
    return LlmConfig(
        model=os.environ.get("MANC_LLM_MODEL") or fields["model"],
        fallback=fields.get("fallback"),
        temperature=float(fields.get("temperature", 0)),
        batch_size=int(fields.get("batch_size", 40)),
    )


def _load_calendar(raw: dict[str, Any]) -> CalendarConfig:
    categories = []
    for entry in raw.get("categories") or []:
        if entry["category"] not in _VALID_CATEGORIES:
            raise ValueError(
                f"calendar: unknown category {entry['category']!r} for {entry['pattern']!r}"
            )
        categories.append((re.compile(entry["pattern"], re.IGNORECASE), entry["category"]))
    importances = []
    for entry in raw.get("importance") or []:
        importance = int(entry["importance"])
        if importance not in _VALID_IMPORTANCE:
            raise ValueError(
                f"calendar: importance must be 1, 2 or 3 for {entry['pattern']!r}, got {importance}"
            )
        importances.append((re.compile(entry["pattern"], re.IGNORECASE), importance))
    return CalendarConfig(
        categories=tuple(categories),
        importances=tuple(importances),
        countries=dict(raw.get("countries") or {}),
    )


def _load_forecasts(raw: dict[str, Any]) -> ForecastsConfig:
    institutions = []
    for entry in raw.get("institutions") or []:
        if entry["kind"] not in FORECASTER_KINDS:
            raise ValueError(
                f"forecasts: institution {entry['name']} has unknown kind {entry['kind']!r}"
            )
        institutions.append(
            InstitutionSpec(
                name=entry["name"],
                aliases=tuple(entry.get("aliases") or ()),
                kind=entry["kind"],
                weight=_unit_interval(entry["weight"], f"forecasts: {entry['name']} weight"),
            )
        )
    queries = tuple(
        ForecastQuery(
            asset=entry["asset"],
            feed=FeedSpec(
                name=f"forecasts_{entry['asset'].lower()}",
                url=entry["url"],
                weight=_unit_interval(entry["weight"], f"forecasts: {entry['asset']} query weight"),
            ),
        )
        for entry in raw.get("queries") or []
    )
    return ForecastsConfig(
        institutions=tuple(institutions),
        signals=tuple(re.compile(pattern, re.IGNORECASE) for pattern in raw.get("signals") or []),
        metrics=tuple(raw.get("metrics") or ()),
        queries=queries,
        min_confidence=_unit_interval(raw.get("min_confidence", 0.5), "forecasts: min_confidence"),
    )


def _term(term: str) -> re.Pattern[str]:
    """Whole-word match; a term with an uppercase letter is case-sensitive ("Fed", not "fed up")."""
    flags = 0 if any(char.isupper() for char in term) else re.IGNORECASE
    return re.compile(rf"(?<!\w)(?:{term})(?!\w)", flags)


def _load_lexicon(raw: dict[str, Any]) -> LexiconConfig:
    categories = []
    for category, terms in (raw.get("categories") or {}).items():
        if category not in _VALID_CATEGORIES:
            raise ValueError(f"lexicon: unknown category {category!r}")
        categories.extend((_term(term), category) for term in terms)
    assets = []
    for symbol, mentions in (raw.get("assets") or {}).items():
        for term, sign in mentions.items():
            if sign not in (-1, 1):
                raise ValueError(f"lexicon: sign for {symbol} {term!r} must be -1 or 1, got {sign}")
            assets.append((_term(term), symbol, int(sign)))
    polarity = []
    for entry in raw.get("polarity") or []:
        if entry["sign"] not in _VALID_SIGNS:
            raise ValueError(
                f"lexicon: sign for {entry['pattern']!r} must be -1, 0 or 1, got {entry['sign']}"
            )
        polarity.append((_term(entry["pattern"]), int(entry["sign"])))
    return LexiconConfig(
        economies=tuple(
            (_term(term), economy)
            for economy, terms in (raw.get("economies") or {}).items()
            for term in terms
        ),
        categories=tuple(categories),
        assets=tuple(assets),
        polarity=tuple(polarity),
    )


_SECTIONS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "assets": _load_assets,
    "feeds": _load_feeds,
    "scoring": _load_scoring,
    "llm": _load_llm,
    "calendar": _load_calendar,
    "forecasts": _load_forecasts,
    "lexicon": _load_lexicon,
}
