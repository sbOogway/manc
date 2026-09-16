"""RSS provider (blueprint section 4): every feed pulled, deduped by URL, failures isolated."""

import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha1
from pathlib import Path

import httpx
import pytest
import respx

from manc.config import FeedSpec, load_config
from manc.news.interface import NewsProvider
from manc.news.rss import RssNews

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "news"
SINCE = datetime(2026, 6, 1, tzinfo=UTC)  # older than every fixture entry

FED = FeedSpec(name="fed", url="https://feeds.test/fed.xml", weight=1.0)
BBC = FeedSpec(name="bbc_business", url="https://feeds.test/bbc.xml", weight=0.7)
EDGE = FeedSpec(name="edge", url="https://feeds.test/edge.xml", weight=0.5)


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def serve(feed: FeedSpec, body: bytes | None = None, **response_kwargs: object) -> None:
    if body is None:
        respx.get(feed.url).mock(return_value=httpx.Response(**response_kwargs))
    else:
        respx.get(feed.url).mock(return_value=httpx.Response(200, content=body))


def test_satisfies_protocol() -> None:
    assert isinstance(RssNews([FED]), NewsProvider)


@respx.mock
def test_parses_recorded_feed_into_news_items() -> None:
    serve(FED, fixture("fed_press_all.xml"))

    items = RssNews([FED]).fetch(SINCE)

    assert len(items) == 20
    newest = items[0]
    assert newest.source == "fed"
    assert newest.title.startswith("Agencies seek comment on proposed third-party risk")
    assert (
        newest.url == "https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260911a.htm"
    )
    assert newest.id == sha1(newest.url.encode()).hexdigest()
    assert newest.published_at == datetime(2026, 9, 11, 14, 0, tzinfo=UTC)
    assert newest.published_at.tzinfo is not None
    assert "<" not in newest.summary
    assert [item.published_at for item in items] == sorted(
        (item.published_at for item in items), reverse=True
    )


@respx.mock
def test_summary_is_html_stripped_and_unescaped() -> None:
    serve(EDGE, fixture("edge_cases.xml"))

    items = RssNews([EDGE]).fetch(SINCE)

    fed_item = next(item for item in items if item.url == "https://example.test/fed-holds")
    assert fed_item.title == "Fed holds rates & signals patience"
    assert fed_item.summary == "The Federal Reserve kept rates unchanged on Wednesday. Read more."


@respx.mock
def test_entries_without_link_or_parsable_date_are_skipped() -> None:
    serve(EDGE, fixture("edge_cases.xml"))

    urls = {item.url for item in RssNews([EDGE]).fetch(SINCE)}

    assert urls == {"https://example.test/fed-holds", "https://example.test/old"}


@respx.mock
def test_entries_before_since_are_dropped() -> None:
    serve(EDGE, fixture("edge_cases.xml"))

    urls = {item.url for item in RssNews([EDGE]).fetch(datetime(2026, 9, 10, tzinfo=UTC))}

    assert urls == {"https://example.test/fed-holds"}


@respx.mock
def test_same_url_in_two_feeds_is_kept_once_for_the_first_feed() -> None:
    serve(FED, fixture("fed_press_all.xml"))
    serve(BBC, fixture("fed_press_all.xml"))

    items = RssNews([FED, BBC]).fetch(SINCE)

    assert len(items) == 20
    assert {item.source for item in items} == {"fed"}


@respx.mock
def test_all_feeds_are_pulled_and_merged() -> None:
    serve(FED, fixture("fed_press_all.xml"))
    serve(BBC, fixture("bbc_business.xml"))

    items = RssNews([FED, BBC]).fetch(SINCE)

    assert len(items) == 20 + 45  # the BBC fixture repeats two links; kept once
    assert {item.source for item in items} == {"fed", "bbc_business"}


@respx.mock
def test_http_error_on_one_feed_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    serve(FED, fixture("fed_press_all.xml"))
    serve(BBC, status_code=403)

    with caplog.at_level(logging.WARNING, logger="manc.news.rss"):
        items = RssNews([FED, BBC]).fetch(SINCE)

    assert len(items) == 20
    assert any("bbc_business" in record.message for record in caplog.records)


@respx.mock
def test_connection_error_on_one_feed_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    serve(FED, fixture("fed_press_all.xml"))
    respx.get(BBC.url).mock(side_effect=httpx.ConnectTimeout("slow"))

    with caplog.at_level(logging.WARNING, logger="manc.news.rss"):
        items = RssNews([FED, BBC]).fetch(SINCE)

    assert len(items) == 20
    assert any("bbc_business" in record.message for record in caplog.records)


@respx.mock
def test_empty_feed_yields_nothing() -> None:
    serve(FED, b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>')

    assert RssNews([FED]).fetch(SINCE) == []


@respx.mock
def test_unparsable_body_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    serve(FED, b"<html><body>Access denied</body></html>")

    with caplog.at_level(logging.WARNING, logger="manc.news.rss"):
        assert RssNews([FED]).fetch(SINCE) == []

    assert any("fed" in record.message for record in caplog.records)


@pytest.mark.live
def test_live_feeds_return_recent_items() -> None:
    items = RssNews(load_config().feeds).fetch(datetime.now(UTC) - timedelta(days=3))

    assert items
    assert len({item.source for item in items}) > 1
