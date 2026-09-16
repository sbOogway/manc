"""One httpx client for every provider: identified agent, one timeout, redirects followed."""

import httpx
import respx

from manc import http
from manc.calendar.nasdaq import NasdaqCalendar
from manc.config import load_config
from manc.news.rss import RssNews


def test_default_agent_is_a_browser() -> None:
    assert http.USER_AGENT.startswith("Mozilla/5.0")
    assert "manc" not in http.USER_AGENT
    assert http.Client().headers["user-agent"] == http.USER_AGENT


def test_default_timeout_and_override() -> None:
    assert http.Client().timeout == httpx.Timeout(http.DEFAULT_TIMEOUT)
    assert http.Client(timeout=3.0).timeout == httpx.Timeout(3.0)


def test_headers_merge_over_the_default_agent() -> None:
    client = http.Client(headers={"Accept": "application/json"})
    assert client.headers["user-agent"] == http.USER_AGENT
    assert client.headers["accept"] == "application/json"

    browser = http.Client(headers={"User-Agent": "Mozilla/5.0"})
    assert browser.headers["user-agent"] == "Mozilla/5.0"


@respx.mock
def test_redirects_are_followed_and_agent_is_sent() -> None:
    respx.get("https://x.test/old").mock(
        return_value=httpx.Response(301, headers={"Location": "https://x.test/new"})
    )
    route = respx.get("https://x.test/new").mock(return_value=httpx.Response(200, text="ok"))

    response = http.Client().get("https://x.test/old")

    assert response.status_code == 200
    assert route.calls.last.request.headers["user-agent"] == http.USER_AGENT


def test_rss_provider_uses_the_shared_client() -> None:
    assert isinstance(RssNews([]).client, http.Client)


def test_calendar_provider_uses_the_shared_client() -> None:
    client = NasdaqCalendar(load_config().calendar).client
    assert isinstance(client, http.Client)
    assert client.headers["user-agent"] == http.USER_AGENT
