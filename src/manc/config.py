"""Typed configuration loaded from the four YAML files in config/ (blueprint section 8)."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from manc.formulas.contract import AssetSpec
from manc.formulas.registry import get_formula

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
_VALID_SIGNS = {-1, 0, 1}


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
class Config:
    assets: tuple[AssetSpec, ...]
    feeds: tuple[FeedSpec, ...]
    scoring: ScoringConfig
    llm: LlmConfig


def load_config(config_dir: Path = DEFAULT_CONFIG_DIR) -> Config:
    return Config(
        assets=_load_assets(_read(config_dir / "assets.yaml")),
        feeds=_load_feeds(_read(config_dir / "feeds.yaml")),
        scoring=_load_scoring(_read(config_dir / "scoring.yaml")),
        llm=_load_llm(_read(config_dir / "llm.yaml")),
    )


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
            )
        )
    return tuple(specs)


def _load_feeds(raw: dict[str, Any]) -> tuple[FeedSpec, ...]:
    feeds = []
    for entry in raw.get("feeds", []):
        weight = float(entry["weight"])
        if not 0.0 <= weight <= 1.0:
            raise ValueError(f"feed {entry['name']}: weight must be within 0..1, got {weight}")
        feeds.append(FeedSpec(name=entry["name"], url=entry["url"], weight=weight))
    return tuple(feeds)


def _load_scoring(raw: dict[str, Any]) -> ScoringConfig:
    formula = raw["formula"]
    get_formula(formula)  # raises ValueError for an unknown name
    return ScoringConfig(
        formula=formula,
        params={key: float(value) for key, value in (raw.get("params") or {}).items()},
        windows={key: int(value) for key, value in (raw.get("windows") or {}).items()},
    )


def _load_llm(raw: dict[str, Any]) -> LlmConfig:
    fields = raw["llm"]
    return LlmConfig(
        model=fields["model"],
        fallback=fields.get("fallback"),
        temperature=float(fields.get("temperature", 0)),
        batch_size=int(fields.get("batch_size", 40)),
    )
