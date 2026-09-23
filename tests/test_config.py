"""Typed configuration from config/*.yaml."""

from pathlib import Path

import pytest
import yaml

from manc.config import FORECASTER_KINDS, load_config
from manc.formulas import v2
from manc.formulas.registry import get_formula

REPO_CONFIG = Path(__file__).resolve().parents[1] / "src" / "manc" / "config"


def test_repo_config_loads() -> None:
    config = load_config(REPO_CONFIG)
    symbols = [asset.symbol for asset in config.assets]
    assert symbols[:3] == ["EURUSD", "GBPUSD", "USDJPY"]
    assert len(symbols) == len(set(symbols)) == 63
    assert {asset.kind for asset in config.assets} == {
        "forex",
        "metal",
        "commodity",
        "equity_index",
        "crypto",
        "bond",
    }
    for asset in config.assets:
        assert asset.economies and asset.spot.get("yahoo"), asset.symbol
        assert set(asset.signs) == set(asset.economies), asset.symbol
    assert all(0.0 <= feed.weight <= 1.0 for feed in config.feeds)


def test_active_kinds_select_the_assets_a_run_touches() -> None:
    config = load_config(REPO_CONFIG)
    assert config.active_kinds == ("crypto",)
    assert config.active_assets
    assert all(asset.kind == "crypto" for asset in config.active_assets)
    assert len(config.active_assets) < len(config.assets)


def test_missing_active_kinds_means_every_asset(tmp_path: Path) -> None:
    assets = yaml.safe_load((REPO_CONFIG / "assets.yaml").read_text())
    del assets["active_kinds"]
    config = load_config(_write(tmp_path, {"assets": assets}))
    assert config.active_kinds == ()
    assert config.active_assets == config.assets


def test_unknown_active_kind_is_rejected(tmp_path: Path) -> None:
    assets = yaml.safe_load((REPO_CONFIG / "assets.yaml").read_text())
    assets["active_kinds"] = ["crypto", "stamps"]
    with pytest.raises(ValueError, match="stamps"):
        load_config(_write(tmp_path, {"assets": assets}))


def test_every_currency_pair_is_base_plus_quote_minus() -> None:
    config = load_config(REPO_CONFIG)
    for asset in config.assets:
        if asset.kind != "forex":
            continue
        base, quote = asset.economies
        assert set(asset.signs[base].values()) == {1}, asset.symbol
        assert set(asset.signs[quote].values()) == {-1}, asset.symbol
    assert get_formula(config.scoring.formula).name == config.scoring.formula == "v2"
    assert set(v2.DEFAULT_PARAMS) <= set(config.scoring.params)  # every v2 key is documented
    assert config.llm.model


def test_llm_model_env_var_overrides_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANC_LLM_MODEL", "mistral/ministral-14b-latest")
    config = load_config(REPO_CONFIG)
    assert config.llm.model == "mistral/ministral-14b-latest"
    assert config.llm.fallback  # the rest of the block is untouched
    monkeypatch.setenv("MANC_LLM_MODEL", "")
    assert load_config(REPO_CONFIG).llm.model == "claude_code/opus"  # blank means the file


def test_signs_are_nested_country_then_category() -> None:
    config = load_config(REPO_CONFIG)
    eurusd = next(asset for asset in config.assets if asset.symbol == "EURUSD")
    assert eurusd.signs["euro_area"]["inflation"] == 1
    assert eurusd.signs["united_states"]["inflation"] == -1


def test_every_asset_has_a_yahoo_and_a_tradingview_symbol() -> None:
    config = load_config(REPO_CONFIG)
    assert all(asset.spot["yahoo"] for asset in config.assets)
    assert all(":" in asset.spot["tradingview"] for asset in config.assets)  # EXCHANGE:TICKER
    assert next(asset.spot for asset in config.assets if asset.symbol == "EURUSD") == {
        "yahoo": "EURUSD=X",
        "tradingview": "FX:EURUSD",
    }


def test_every_coin_names_its_chain_data_ids_and_nothing_else_does() -> None:
    config = load_config(REPO_CONFIG)
    coins = [asset for asset in config.assets if asset.kind == "crypto"]
    assert [asset.symbol for asset in coins if not asset.chain.get("defillama")] == ["XAUTUSD"]
    assert [asset.symbol for asset in coins if not asset.chain.get("coinmetrics")] == [
        "SOLUSD",
        "BNBUSD",
    ]
    assert all(asset.chain.get("coingecko") for asset in coins)
    chains = {asset.symbol: asset.chain for asset in coins}
    assert chains["BTCUSD"] == {
        "coinmetrics": "btc",
        "defillama": "bitcoin",
        "coingecko": "bitcoin",
    }
    assert chains["ZECUSD"] == {"coinmetrics": "zec", "defillama": "zcash", "coingecko": "zcash"}
    assert chains["XAUTUSD"] == {"coinmetrics": "xaut", "coingecko": "tether-gold"}
    assert all(asset.chain == {} for asset in config.assets if asset.kind != "crypto")


def test_asset_without_spot_block_has_no_symbols(tmp_path: Path) -> None:
    assets = yaml.safe_load((REPO_CONFIG / "assets.yaml").read_text())
    del assets["assets"]["EURUSD"]["spot"]
    config = load_config(_write(tmp_path, {"assets": assets}))
    assert next(asset for asset in config.assets if asset.symbol == "EURUSD").spot == {}


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


def test_forecasts_config_loads() -> None:
    config = load_config(REPO_CONFIG)
    forecasts = config.forecasts
    names = [institution.name for institution in forecasts.institutions]
    assert len(names) == len(set(names))
    assert all(institution.aliases for institution in forecasts.institutions)
    assert all(institution.kind in FORECASTER_KINDS for institution in forecasts.institutions)
    assert all(0.0 <= institution.weight <= 1.0 for institution in forecasts.institutions)
    assert 0.0 <= forecasts.min_confidence <= 1.0
    assert set(forecasts.metrics) >= {"policy_rate", "cpi", "pce", "gdp", "unemployment"}
    queried = {query.asset for query in forecasts.queries}
    assert {"EURUSD", "XAUUSD", "BRENT", "SPX", "BTCUSD", "NDX", "ETHUSD"} <= queried
    assert queried <= {asset.symbol for asset in config.assets}
    assert all(query.feed.url.startswith("https://") for query in forecasts.queries)
    assert forecasts.signals  # at least one compiled regex


def test_forecasts_canonical_resolves_aliases_case_insensitively() -> None:
    forecasts = load_config(REPO_CONFIG).forecasts
    assert forecasts.canonical("Goldman Sachs") == "goldman_sachs"
    assert forecasts.canonical("GOLDMAN") == "goldman_sachs"
    assert forecasts.canonical("goldman_sachs") == "goldman_sachs"
    assert forecasts.canonical("Rabobank Research") == "rabobank_research"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (
            {"institutions": [{"name": "x", "aliases": ["X"], "kind": "hedge_fund", "weight": 1}]},
            "kind",
        ),
        (
            {"institutions": [{"name": "x", "aliases": ["X"], "kind": "bank", "weight": 2}]},
            "weight",
        ),
        ({"min_confidence": 1.5}, "min_confidence"),
        ({"queries": [{"asset": "NOPE", "url": "https://x/rss", "weight": 0.3}]}, "asset"),
    ],
)
def test_bad_forecasts_config_is_rejected(tmp_path: Path, override: dict, message: str) -> None:
    forecasts = yaml.safe_load((REPO_CONFIG / "forecasts.yaml").read_text())
    forecasts.update(override)
    with pytest.raises(ValueError, match=message):
        load_config(_write(tmp_path, {"forecasts": forecasts}))


def test_missing_forecasts_file_names_it(tmp_path: Path) -> None:
    _write(tmp_path, {})
    (tmp_path / "forecasts.yaml").unlink()
    with pytest.raises(FileNotFoundError, match=r"forecasts\.yaml"):
        load_config(tmp_path)


def test_lexicon_loads_and_compiles_whole_word_patterns() -> None:
    lexicon = load_config(REPO_CONFIG).lexicon
    economies = {economy for _pattern, economy in lexicon.economies}
    assert {"united_states", "euro_area", "united_kingdom", "japan", "china"} <= economies
    tracked = {economy for asset in load_config(REPO_CONFIG).assets for economy in asset.economies}
    assert economies <= tracked
    assert {category for _pattern, category in lexicon.categories} <= {
        "inflation",
        "employment",
        "growth",
        "rates",
    }
    mentioned = {symbol for _pattern, symbol, _sign in lexicon.assets}
    assert {"EURUSD", "XAUUSD", "BRENT", "SPX", "BTCUSD", "WTI", "ETHUSD"} <= mentioned
    assert {"ZECUSD", "XAUTUSD"} <= mentioned
    assert mentioned <= {asset.symbol for asset in load_config(REPO_CONFIG).assets}
    assert {sign for _pattern, sign in lexicon.polarity} == {-1, 0, 1}
    fed = next(pattern for pattern, _economy in lexicon.economies if pattern.search("Fed holds"))
    assert not fed.search("fed up") and not fed.search("Federal")
    gold = next(pattern for pattern, symbol, _sign in lexicon.assets if symbol == "XAUUSD")
    assert gold.search("Gold steady") and gold.search("gold steady") and not gold.search("Goldman")


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"economies": {"mars": ["Mars"]}}, "economy"),
        ({"categories": {"weather": ["rain"]}}, "category"),
        ({"assets": {"NOPE": {"nope": 1}}}, "asset"),
        ({"assets": {"XAUUSD": {"gold": 0}}}, "sign"),
        ({"polarity": [{"pattern": "hot", "sign": 2}]}, "sign"),
    ],
)
def test_bad_lexicon_config_is_rejected(tmp_path: Path, override: dict, message: str) -> None:
    lexicon = yaml.safe_load((REPO_CONFIG / "lexicon.yaml").read_text())
    lexicon.update(override)
    with pytest.raises(ValueError, match=message):
        load_config(_write(tmp_path, {"lexicon": lexicon}))
