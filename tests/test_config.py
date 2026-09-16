"""Typed configuration from config/*.yaml."""

from pathlib import Path

import pytest
import yaml

from manc.config import load_config
from manc.formulas.registry import get_formula

REPO_CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_repo_config_loads() -> None:
    config = load_config(REPO_CONFIG)
    assert [asset.symbol for asset in config.assets] == [
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "XAUUSD",
        "WTI",
        "SPX",
        "BTCUSD",
    ]
    assert all(0.0 <= feed.weight <= 1.0 for feed in config.feeds)
    assert get_formula(config.scoring.formula).name == config.scoring.formula
    assert config.llm.model


def test_signs_are_nested_country_then_category() -> None:
    config = load_config(REPO_CONFIG)
    eurusd = next(asset for asset in config.assets if asset.symbol == "EURUSD")
    assert eurusd.signs["euro_area"]["inflation"] == 1
    assert eurusd.signs["united_states"]["inflation"] == -1


def _write(config_dir: Path, overrides: dict[str, dict]) -> Path:
    """Copy the repo config into a temp dir, replacing whole files given in overrides."""
    for source in REPO_CONFIG.glob("*.yaml"):
        (config_dir / source.name).write_text(source.read_text())
    for name, content in overrides.items():
        (config_dir / f"{name}.yaml").write_text(yaml.safe_dump(content))
    return config_dir


def test_bad_sign_value_is_rejected(tmp_path: Path) -> None:
    assets = {"assets": {"X": {"kind": "forex", "economies": ["a"], "signs": {"a": {"growth": 2}}}}}
    with pytest.raises(ValueError, match="sign"):
        load_config(_write(tmp_path, {"assets": assets}))


def test_feed_weight_out_of_range_is_rejected(tmp_path: Path) -> None:
    feeds = {"feeds": [{"name": "x", "url": "https://x/rss", "weight": 1.5}]}
    with pytest.raises(ValueError, match="weight"):
        load_config(_write(tmp_path, {"feeds": feeds}))


def test_unknown_formula_is_rejected(tmp_path: Path) -> None:
    scoring = {"formula": "v99", "params": {}, "windows": {}}
    with pytest.raises(ValueError, match="unknown formula"):
        load_config(_write(tmp_path, {"scoring": scoring}))


def test_missing_file_names_it(tmp_path: Path) -> None:
    _write(tmp_path, {})
    (tmp_path / "llm.yaml").unlink()
    with pytest.raises(FileNotFoundError, match=r"llm\.yaml"):
        load_config(tmp_path)


def test_feed_names_are_unique_and_urls_are_https() -> None:
    feeds = load_config(REPO_CONFIG).feeds
    assert len({feed.name for feed in feeds}) == len(feeds)
    assert all(feed.url.startswith("https://") for feed in feeds)
    
    
def test_calendar_maps_load_and_resolve() -> None:
    calendar = load_config(REPO_CONFIG).calendar
    assert calendar.category("Nonfarm Payrolls") == "employment"
    assert calendar.category("Core CPI") == "inflation"
    assert calendar.category("Fed Interest Rate Decision") == "rates"
    assert calendar.category("Retail Sales") == "growth"
    assert calendar.category("MBA Mortgage Applications") == "other"
    assert calendar.importance("Nonfarm Payrolls") == 3
    assert calendar.importance("Initial Jobless Claims") == 2
    assert calendar.importance("MBA Mortgage Applications") == 1
    assert calendar.country("Euro Zone") == "euro_area"
    assert calendar.country("United Kingdom") == "united_kingdom"


def test_calendar_importance_out_of_range_is_rejected(tmp_path: Path) -> None:
    calendar = {"importance": [{"pattern": "CPI", "importance": 4}]}
    with pytest.raises(ValueError, match="importance"):
        load_config(_write(tmp_path, {"calendar": calendar}))


def test_calendar_unknown_category_is_rejected(tmp_path: Path) -> None:
    calendar = {"categories": [{"pattern": "CPI", "category": "prices"}]}
    with pytest.raises(ValueError, match="category"):
        load_config(_write(tmp_path, {"calendar": calendar}))
