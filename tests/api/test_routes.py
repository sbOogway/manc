"""Every section 7 route on TestClient against FakeStore: status, shape, errors."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from manc.api.app import create_app
from manc.api.routes import MAX_RANGE_DAYS
from manc.config import load_config
from manc.formulas.contract import IndexScore
from manc.models import (
    CalendarEvent,
    ChainMetric,
    ForecastAsset,
    ForecastMacro,
    NewsItem,
    NewsTag,
    SpotPrice,
)
from tests.fakes import FakeStore

CONFIG = replace(
    load_config(), scoring=replace(load_config().scoring, formula="v1"), active_kinds=()
)  # the fake holds v1 rows for a forex pair and an equity index
TODAY = datetime.now(UTC).date()
DAY = timedelta(days=1)
NOON = datetime.combine(TODAY, datetime.min.time(), tzinfo=UTC) + timedelta(hours=12)


def _score(asset: str, day: date, value: float, formula: str = "v1") -> IndexScore:
    return IndexScore(
        asset=asset,
        date=day,
        score=value,
        formula=formula,
        components={"N": 0.1, "S": -0.2, "R": 0.5},
        n_news=3,
        n_events=1,
        report_md=f"# {asset} {day}",
    )


def _event(event_id: str, when: datetime, importance: int = 3) -> CalendarEvent:
    return CalendarEvent(
        id=event_id,
        date=when,
        country="united_states",
        event="CPI",
        category="inflation",
        importance=importance,
        consensus=3.0,
        previous=2.9,
        actual=None,
    )


@pytest.fixture
def store() -> FakeStore:
    store = FakeStore()
    store.scores.add(
        _score("EURUSD", TODAY - DAY, 40.0),
        _score("EURUSD", TODAY, 62.0),
        _score("SPX", TODAY, 30.0),
        _score("EURUSD", TODAY, 70.0, formula="v2"),
    )
    item = NewsItem.from_feed(
        source="reuters", title="Euro rallies", url="https://x/1", published_at=NOON - DAY
    )
    store.news.add(item)
    store.tags.add(NewsTag(item.id, "EURUSD", 1, 0.8, model="m"))
    store.events.add(_event("cpi", NOON + 2 * DAY), _event("far", NOON + 40 * DAY))
    store.forecasts_asset.add(
        ForecastAsset.new(
            institution="goldman_sachs",
            asset="EURUSD",
            horizon_date=TODAY + 100 * DAY,
            horizon_label="12 months",
            value=1.2,
            published_at=NOON - DAY,
            source_url="https://x/gs",
            source_kind="extracted",
            confidence=0.9,
            model="m",
        )
    )
    store.forecasts_macro.add(
        ForecastMacro.new(
            institution="goldman_sachs",
            economy="united_states",
            metric="policy_rate",
            horizon_date=TODAY + 100 * DAY,
            horizon_label="year-end",
            value=3.5,
            published_at=NOON - DAY,
            source_url="https://x/gs",
            source_kind="structured",
            confidence=1.0,
        )
    )
    store.spot.add(SpotPrice("EURUSD", TODAY, 1.1, "yahoo"))
    store.chain.add(
        ChainMetric("BTCUSD", TODAY - DAY, "mvrv", 1.4, "coinmetrics"),
        ChainMetric("BTCUSD", TODAY, "mvrv", 1.5, "coinmetrics"),
        ChainMetric("BTCUSD", TODAY, "fees_usd", 10000.0, "defillama"),
    )
    return store


@pytest.fixture
def client(store: FakeStore) -> TestClient:
    return TestClient(create_app(CONFIG, store))


def test_assets(client: TestClient) -> None:
    response = client.get("/api/v1/assets")
    assert response.status_code == 200
    assert response.json()[0] == {
        "symbol": "EURUSD",
        "kind": "forex",
        "economies": ["euro_area", "united_states"],
        "tradingview": "FX:EURUSD",
    }
    assert len(response.json()) == len(CONFIG.assets)


def test_assets_lists_the_active_kinds_only(store: FakeStore) -> None:
    client = TestClient(create_app(replace(CONFIG, active_kinds=("crypto",)), store))
    listed = client.get("/api/v1/assets").json()
    assert listed[0]["symbol"] == "BTCUSD"
    assert {asset["kind"] for asset in listed} == {"crypto"}
    assert 0 < len(listed) < len(CONFIG.assets)


def test_overview_defaults_to_today_farthest_from_fifty_first(client: TestClient) -> None:
    response = client.get("/api/v1/overview")
    assert response.status_code == 200
    [spx, eurusd] = response.json()
    assert (spx["symbol"], spx["score"], spx["band"]) == ("SPX", 30.0, "lean_against")
    assert (eurusd["delta"], eurusd["sparkline"], eurusd["event_risk"]) == (22.0, [40.0, 62.0], 0.5)
    assert eurusd["date"] == TODAY.isoformat()


def test_overview_as_of_a_past_day(client: TestClient) -> None:
    response = client.get("/api/v1/overview", params={"as_of": (TODAY - DAY).isoformat()})
    [eurusd] = response.json()
    assert (eurusd["score"], eurusd["delta"]) == (40.0, None)


def test_scores_series_with_components(client: TestClient) -> None:
    response = client.get("/api/v1/assets/EURUSD/scores")
    assert response.status_code == 200
    body = response.json()
    assert (body["symbol"], body["formula"]) == ("EURUSD", "v1")
    assert [point["score"] for point in body["points"]] == [40.0, 62.0]
    assert body["points"][1]["components"] == {"N": 0.1, "S": -0.2, "R": 0.5}
    assert body["points"][1]["band"] == "lean_for"
    assert body["scale"] == {
        "low": 0.0,
        "high": 100.0,
        "neutral": 50.0,
        "edges": [30.0, 45.0, 55.0, 70.0],
    }


def test_scores_formula_and_range(client: TestClient) -> None:
    response = client.get(
        "/api/v1/assets/EURUSD/scores",
        params={"formula": "v2", "from": TODAY.isoformat(), "to": TODAY.isoformat()},
    )
    assert [point["score"] for point in response.json()["points"]] == [70.0]


def test_chain_series_for_a_coin_and_nothing_for_the_rest(client: TestClient) -> None:
    response = client.get("/api/v1/assets/BTCUSD/chain")
    assert response.status_code == 200
    body = response.json()
    assert [(one["metric"], one["label"], one["source"], one["group"]) for one in body] == [
        ("fees_usd", "Fees paid (USD)", "defillama", "chain"),
        ("mvrv", "MVRV", "coinmetrics", "chain"),
    ]
    assert body[1]["points"] == [
        {"date": (TODAY - DAY).isoformat(), "value": 1.4},
        {"date": TODAY.isoformat(), "value": 1.5},
    ]
    windowed = client.get("/api/v1/assets/BTCUSD/chain", params={"from": TODAY.isoformat()})
    assert [len(one["points"]) for one in windowed.json()] == [1, 1]
    assert client.get("/api/v1/assets/EURUSD/chain").json() == []
    assert client.get("/api/v1/assets/NOPE/chain").status_code == 404


def test_report_defaults_to_today_and_the_configured_formula(client: TestClient) -> None:
    response = client.get("/api/v1/assets/EURUSD/report")
    assert response.status_code == 200
    assert response.json() == {
        "symbol": "EURUSD",
        "date": TODAY.isoformat(),
        "formula": "v1",
        "report_md": f"# EURUSD {TODAY}",
    }
    other = client.get("/api/v1/assets/EURUSD/report", params={"formula": "v2"})
    assert other.json()["formula"] == "v2"  # the fake holds a v2 row for today too


def test_report_missing_day_is_404(client: TestClient) -> None:
    response = client.get(
        "/api/v1/assets/EURUSD/report", params={"date": (TODAY - 30 * DAY).isoformat()}
    )
    assert response.status_code == 404


def test_headlines(client: TestClient) -> None:
    response = client.get("/api/v1/assets/EURUSD/headlines")
    assert response.status_code == 200
    [headline] = response.json()
    assert (headline["title"], headline["direction"], headline["source"], headline["weight"]) == (
        "Euro rallies",
        1,
        "reuters",
        0.8,
    )


def test_events_default_to_the_next_thirty_days(client: TestClient) -> None:
    response = client.get("/api/v1/events")
    assert response.status_code == 200
    assert [event["id"] for event in response.json()] == ["cpi"]


def test_events_importance_floor(client: TestClient) -> None:
    high = client.get("/api/v1/events", params={"min_importance": 3}).json()
    assert [event["id"] for event in high] == ["cpi"]
    assert client.get("/api/v1/events", params={"min_importance": 4}).status_code == 422


def test_forecast_panel(client: TestClient) -> None:
    response = client.get("/api/v1/assets/EURUSD/forecasts")
    assert response.status_code == 200
    body = response.json()
    assert body["spot"] == 1.1
    [row] = body["rows"]
    assert (row["institution"], row["value"], row["previous_value"]) == ("goldman_sachs", 1.2, None)
    assert row["vs_spot"] == pytest.approx(1.2 / 1.1 - 1)
    assert [median["value"] for median in body["medians"]] == [1.2]
    assert [macro["metric"] for macro in body["macro"]] == ["policy_rate"]


def test_forecast_panel_confidence_floor(client: TestClient) -> None:
    response = client.get("/api/v1/assets/EURUSD/forecasts", params={"min_confidence": 0.95})
    assert response.json()["rows"] == []


def test_spot(client: TestClient) -> None:
    response = client.get("/api/v1/assets/EURUSD/spot")
    assert response.status_code == 200
    assert response.json() == [
        {"asset": "EURUSD", "date": TODAY.isoformat(), "close": 1.1, "source": "yahoo"}
    ]


def test_macro_forecasts(client: TestClient) -> None:
    response = client.get("/api/v1/macro/forecasts", params={"economy": "united_states"})
    assert response.status_code == 200
    [row] = response.json()
    assert (row["institution"], row["metric"], row["value"]) == (
        "goldman_sachs",
        "policy_rate",
        3.5,
    )
    other = client.get(
        "/api/v1/macro/forecasts", params={"economy": "united_states", "metric": "cpi"}
    )
    assert other.json() == []
    assert client.get("/api/v1/macro/forecasts").status_code == 422


def test_formulas(client: TestClient) -> None:
    assert client.get("/api/v1/formulas").json() == {"default": "v1", "known": ["v1", "v2"]}


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "last_run": TODAY.isoformat()}


def test_health_without_scores() -> None:
    client = TestClient(create_app(CONFIG, FakeStore()))
    assert client.get("/health").json() == {"status": "ok", "last_run": None}


@pytest.mark.parametrize(
    "path",
    ["scores", "report", "headlines", "forecasts", "spot"],
)
def test_unknown_asset_is_404(client: TestClient, path: str) -> None:
    response = client.get(f"/api/v1/assets/XXXUSD/{path}")
    assert response.status_code == 404
    assert response.json() == {"detail": "unknown asset XXXUSD"}


def test_malformed_date_is_422(client: TestClient) -> None:
    assert client.get("/api/v1/overview", params={"as_of": "yesterday"}).status_code == 422


@pytest.mark.parametrize(
    "path", ["assets/EURUSD/scores", "assets/BTCUSD/chain", "assets/EURUSD/spot", "events"]
)
def test_a_range_is_bounded_and_ordered(client: TestClient, path: str) -> None:
    """One client must not make the process scan the whole history on every request."""
    widest = {"from": (TODAY - timedelta(days=MAX_RANGE_DAYS)).isoformat(), "to": TODAY.isoformat()}
    assert client.get(f"/api/v1/{path}", params=widest).status_code == 200
    too_wide = {**widest, "from": (TODAY - timedelta(days=MAX_RANGE_DAYS + 1)).isoformat()}
    response = client.get(f"/api/v1/{path}", params=too_wide)
    assert response.status_code == 422
    assert response.json() == {"detail": f"from..to spans more than {MAX_RANGE_DAYS} days"}
    backwards = {"from": TODAY.isoformat(), "to": (TODAY - timedelta(days=1)).isoformat()}
    response = client.get(f"/api/v1/{path}", params=backwards)
    assert response.status_code == 422
    assert response.json() == {"detail": "from is after to"}


@pytest.mark.parametrize(
    "origin",
    ["https://mattiapapaccioli.com", "https://sboogway.github.io", "http://localhost:8050"],
)
def test_the_site_origins_may_read_across_origins_with_credentials(
    client: TestClient, origin: str
) -> None:
    response = client.get("/api/v1/formulas", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_other_origins_get_no_cross_origin_grant(client: TestClient) -> None:
    """Browsers only: curl ignores CORS. Access control is Cloudflare Access on the tunnel."""
    response = client.get("/api/v1/formulas", headers={"Origin": "https://evil.test"})
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
