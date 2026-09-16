"""RSS news provider (blueprint section 4): every feed in config, deduped, failures isolated."""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from html import unescape
from html.parser import HTMLParser
from time import struct_time

import feedparser
import httpx

from manc.config import FeedSpec
from manc.models import NewsItem

log = logging.getLogger(__name__)

USER_AGENT = "manc/0.1 (+https://github.com/sbOogway/manc)"
DEFAULT_TIMEOUT = 15.0


class RssNews:
    def __init__(self, feeds: Sequence[FeedSpec], client: httpx.Client | None = None) -> None:
        self.feeds = tuple(feeds)
        self.client = client or httpx.Client(
            timeout=DEFAULT_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )

    def fetch(self, since: datetime) -> list[NewsItem]:
        """Newest first; a URL seen in several feeds is attributed to the first feed."""
        seen: dict[str, NewsItem] = {}
        for feed in self.feeds:
            for item in self._fetch_feed(feed, since):
                seen.setdefault(item.id, item)
        return sorted(seen.values(), key=lambda item: item.published_at, reverse=True)

    def _fetch_feed(self, feed: FeedSpec, since: datetime) -> list[NewsItem]:
        try:
            response = self.client.get(feed.url)
            response.raise_for_status()
        except httpx.HTTPError as error:
            log.warning("feed %s skipped: %s", feed.name, error)
            return []
        parsed = feedparser.parse(response.content)
        if not parsed.version:  # not a feed at all, e.g. an HTML error page
            log.warning("feed %s skipped: not a feed", feed.name)
            return []
        items = [item for entry in parsed.entries if (item := _to_item(feed, entry, since))]
        log.debug("feed %s: %d of %d entries kept", feed.name, len(items), len(parsed.entries))
        return items


def _to_item(feed: FeedSpec, entry: feedparser.FeedParserDict, since: datetime) -> NewsItem | None:
    url = entry.get("link")
    published_at = _published_at(entry)
    if not url or published_at is None or published_at < since:
        return None
    return NewsItem.from_feed(
        source=feed.name,
        title=unescape(entry.get("title", "")).strip(),
        url=url,
        published_at=published_at,
        summary=strip_html(entry.get("summary", "")),
    )


def _published_at(entry: feedparser.FeedParserDict) -> datetime | None:
    parsed: struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed is None:
        return None
    return datetime(*parsed[:6], tzinfo=UTC)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.pieces: list[str] = []

    def handle_data(self, data: str) -> None:
        self.pieces.append(data)


def strip_html(text: str) -> str:
    """Tags removed, entities decoded, whitespace collapsed."""
    extractor = _TextExtractor()
    extractor.feed(text)
    extractor.close()
    return " ".join(unescape(" ".join(extractor.pieces)).split())
