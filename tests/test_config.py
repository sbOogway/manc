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
