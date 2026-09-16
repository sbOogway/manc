"""Build ScoringInputs for one asset from what the store holds."""

from datetime import datetime, timedelta

from manc.config import Config
from manc.formulas.contract import AssetSpec, EventObservation, ScoringInputs, TaggedHeadline
from manc.models import CalendarEvent
from manc.store.interface import Store

UNKNOWN_SOURCE_WEIGHT = 1.0


def build_inputs(store: Store, asset: AssetSpec, as_of: datetime, config: Config) -> ScoringInputs:
    windows = config.scoring.windows
    feed_weights = {feed.name: feed.weight for feed in config.feeds}

    news_since = as_of - timedelta(hours=windows["news_hours"])
    tags = tuple(
        TaggedHeadline(
            direction=tag.direction,
            confidence=tag.confidence,
            source_weight=feed_weights.get(item.source, UNKNOWN_SOURCE_WEIGHT),
            published_at=item.published_at,
        )
        for item, tag in store.news.tagged(asset.symbol, news_since)
    )

    released_start = (as_of - timedelta(days=windows["released_days"])).date()
    upcoming_end = (as_of + timedelta(days=windows["upcoming_days"])).date()
    relevant = [
        event
        for event in store.events.between(released_start, upcoming_end)
        if event.country in asset.economies
    ]
    released = tuple(
        _observe(event) for event in relevant if event.released and event.date <= as_of
    )
    upcoming = tuple(_observe(event) for event in relevant if event.date > as_of)

    return ScoringInputs(
        asset=asset,
        as_of=as_of,
        tags=tags,
        released=released,
        upcoming=upcoming,
        params=config.scoring.params,
    )


def _observe(event: CalendarEvent) -> EventObservation:
    return EventObservation(
        date=event.date,
        country=event.country,
        category=event.category,
        importance=event.importance,
        consensus=event.consensus,
        previous=event.previous,
        actual=event.actual,
    )
