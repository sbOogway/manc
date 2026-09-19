"""Build ScoringInputs for one asset from what the store holds."""

from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timedelta

from manc.config import Config
from manc.formulas.contract import AssetSpec, EventObservation, ScoringInputs, TaggedHeadline
from manc.models import CalendarEvent
from manc.store.interface import Store

UNKNOWN_SOURCE_WEIGHT = 1.0
DEFAULT_SURPRISE_HISTORY_DAYS = 730


def build_inputs(
    store: Store,
    asset: AssetSpec,
    as_of: datetime,
    config: Config,
    windows: Mapping[str, int] | None = None,
) -> ScoringInputs:
    """`windows` are the formula's overrides of the config windows (v2 looks further back)."""
    windows = {**config.scoring.windows, **(windows or {})}
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
    history_start = (
        as_of - timedelta(days=windows.get("surprise_history_days", DEFAULT_SURPRISE_HISTORY_DAYS))
    ).date()
    past = _past_surprises(store.events.between(history_start, as_of.date()), asset)
    released = tuple(
        _observe(event, past[(event.country, event.event)])
        for event in relevant
        if event.released and event.date <= as_of
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


def _past_surprises(
    history: list[CalendarEvent], asset: AssetSpec
) -> dict[tuple[str, str], list[tuple[datetime, float]]]:
    """(country, event name) -> (date, actual - consensus) of every release with both."""
    surprises: dict[tuple[str, str], list[tuple[datetime, float]]] = defaultdict(list)
    for event in sorted(history, key=lambda row: row.date):
        if (
            event.country in asset.economies
            and event.actual is not None
            and event.consensus is not None
        ):
            surprises[(event.country, event.event)].append(
                (event.date, event.actual - event.consensus)
            )
    return surprises


def _observe(
    event: CalendarEvent, history: list[tuple[datetime, float]] | None = None
) -> EventObservation:
    return EventObservation(
        date=event.date,
        country=event.country,
        category=event.category,
        importance=event.importance,
        consensus=event.consensus,
        previous=event.previous,
        actual=event.actual,
        past_surprises=tuple(surprise for when, surprise in history or [] if when < event.date),
    )
