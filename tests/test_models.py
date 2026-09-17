"""Domain models are immutable value objects."""

from datetime import UTC, date, datetime, timedelta

import pytest

from manc.models import AssetForecast, CalendarEvent, MacroForecast, NewsItem, NewsTag, SpotPrice

NOW = datetime(2026, 9, 15, 8, 0, tzinfo=UTC)


def test_news_item_id_is_derived_from_url() -> None:
    a = NewsItem.from_feed(source="cnbc", title="A", url="https://x/1", published_at=NOW)
    b = NewsItem.from_feed(source="cnbc", title="B", url="https://x/1", published_at=NOW)
    assert a.id == b.id
    assert len(a.id) == 40  # sha1 hex


def test_models_are_frozen_and_hashable() -> None:
    item = NewsItem.from_feed(source="cnbc", title="A", url="https://x/1", published_at=NOW)
    tag = NewsTag(news_id=item.id, asset="EURUSD", direction=1, confidence=0.8)
    event = CalendarEvent(
        id="e1",
        date=NOW,
        country="united_states",
        event="CPI",
        category="inflation",
        importance=3,
        consensus=3.0,
        previous=2.9,
        actual=None,
    )
    for obj in (item, tag, event):
        hash(obj)
        with pytest.raises(AttributeError):
            obj.asset = "x"  # type: ignore[attr-defined,misc]


def test_news_tag_rejects_bad_direction_and_confidence() -> None:
    with pytest.raises(ValueError):
        NewsTag(news_id="n", asset="EURUSD", direction=2, confidence=0.5)
    with pytest.raises(ValueError):
        NewsTag(news_id="n", asset="EURUSD", direction=1, confidence=1.5)


def test_calendar_event_released_only_when_actual_present() -> None:
    kw = dict(id="e", date=NOW, country="u", event="x", category="c", importance=1)
    assert not CalendarEvent(**kw, consensus=1.0, previous=1.0, actual=None).released
    assert CalendarEvent(**kw, consensus=1.0, previous=1.0, actual=1.2).released


def _asset_forecast(**overrides: object) -> "AssetForecast":
    fields: dict[str, object] = dict(
        institution="goldman_sachs",
        asset="XAUUSD",
        horizon_date=date(2026, 12, 31),
        horizon_label="year-end",
        value=4000.0,
        published_at=NOW,
        source_url="https://x/gold",
        source_kind="extracted",
        confidence=0.8,
        model="openrouter/free",
    )
    fields.update(overrides)
    return AssetForecast.new(**fields)  # type: ignore[arg-type]


def test_asset_forecast_id_is_the_vintage_key() -> None:
    """Same call, other outlet, other day: same id. A new value or horizon: a new id."""
    first = _asset_forecast()
    re_report = _asset_forecast(published_at=NOW + timedelta(days=3), source_url="https://y/gold")
    assert first.id == re_report.id
    assert len(first.id) == 40
    assert _asset_forecast(value=4200.0).id != first.id
    assert _asset_forecast(horizon_date=date(2027, 6, 30)).id != first.id
    assert _asset_forecast(institution="ubs").id != first.id
    assert _asset_forecast(asset="WTI").id != first.id


def test_asset_forecast_id_ignores_float_noise() -> None:
    assert _asset_forecast(value=1.18).id == _asset_forecast(value=1.18 + 1e-12).id


def test_macro_forecast_id_keys_on_economy_and_metric() -> None:
    base = dict(
        institution="fed",
        horizon_date=date(2026, 12, 31),
        horizon_label="2026",
        value=3.4,
        published_at=NOW,
        source_url="https://fed/sep",
        source_kind="structured",
        confidence=1.0,
        model="",
    )
    cpi = MacroForecast.new(economy="united_states", metric="cpi", **base)  # type: ignore[arg-type]
    rate = MacroForecast.new(economy="united_states", metric="policy_rate", **base)  # type: ignore[arg-type]
    euro = MacroForecast.new(economy="euro_area", metric="cpi", **base)  # type: ignore[arg-type]
    assert len({cpi.id, rate.id, euro.id}) == 3
    assert MacroForecast.new(economy="united_states", metric="cpi", **base).id == cpi.id  # type: ignore[arg-type]


def test_forecasts_reject_bad_confidence_and_source_kind() -> None:
    with pytest.raises(ValueError, match="confidence"):
        _asset_forecast(confidence=1.5)
    with pytest.raises(ValueError, match="source_kind"):
        _asset_forecast(source_kind="guessed")


def test_forecast_and_spot_models_are_frozen() -> None:
    spot = SpotPrice(asset="XAUUSD", date=NOW.date(), close=3650.5, source="stooq")
    for obj in (_asset_forecast(), spot):
        hash(obj)
        with pytest.raises(AttributeError):
            obj.asset = "x"  # type: ignore[attr-defined,misc]
