"""Store implementation over SQLAlchemy Core: one repository per table in schema.py."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Engine, Table, case, func, select, update
from sqlalchemy.dialects import postgresql, sqlite

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
from manc.store import db, schema

_SIGHTING_COLUMNS = ("published_at", "source_url", "confidence", "model")


def _utc(value: datetime) -> datetime:
    """SQLite drops the timezone; everything stored is UTC, so put it back on read."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _insert(engine: Engine, table: Table, rows: list[dict[str, Any]]) -> Any:
    insert = {"sqlite": sqlite.insert, "postgresql": postgresql.insert}[engine.dialect.name]
    return insert(table).values(rows)


CHUNK_ROWS = 500  # a backfill can be tens of thousands of rows; SQLite caps the variables


def _upsert(
    engine: Engine, table: Table, rows: list[dict[str, Any]], keep: tuple[str, ...] = ()
) -> None:
    """Insert or overwrite by primary key; the `keep` columns follow the existing row."""
    if not rows:
        return
    key_columns = [column.name for column in table.primary_key.columns]
    with engine.begin() as connection:
        for start in range(0, len(rows), CHUNK_ROWS):
            statement = _insert(engine, table, rows[start : start + CHUNK_ROWS])
            statement = statement.on_conflict_do_update(
                index_elements=key_columns,
                set_={
                    column.name: getattr(statement.excluded, column.name)
                    for column in table.columns
                    if column.name not in key_columns and column.name not in keep
                },
            )
            connection.execute(statement)


def _upsert_keep_earliest(engine: Engine, table: Table, rows: list[dict[str, Any]]) -> None:
    """Forecast vintages: on an existing id, the sighting columns follow the earlier one."""
    if not rows:
        return
    with engine.begin() as connection:
        for start in range(0, len(rows), CHUNK_ROWS):
            statement = _insert(engine, table, rows[start : start + CHUNK_ROWS])
            is_earlier = statement.excluded.published_at < table.c.published_at
            set_ = {
                name: case((is_earlier, getattr(statement.excluded, name)), else_=table.c[name])
                for name in _SIGHTING_COLUMNS
            }
            set_["fetched_at"] = statement.excluded.fetched_at
            statement = statement.on_conflict_do_update(index_elements=["id"], set_=set_)
            connection.execute(statement)


class SqlNewsRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, *items: NewsItem) -> None:
        now = datetime.now(UTC)
        _upsert(
            self._engine,
            schema.news,
            [
                {
                    "id": item.id,
                    "source": item.source,
                    "title": item.title,
                    "url": item.url,
                    "published_at": item.published_at,
                    "summary": item.summary,
                    "fetched_at": now,
                }
                for item in items
            ],
            keep=("analyzed_at",),
        )

    def since(self, published_after: datetime) -> list[NewsItem]:
        statement = (
            select(schema.news)
            .where(schema.news.c.published_at >= published_after)
            .order_by(schema.news.c.published_at)
        )
        with self._engine.connect() as connection:
            return [_news_item(row) for row in connection.execute(statement).mappings()]

    def unanalyzed(self, published_after: datetime) -> list[NewsItem]:
        statement = (
            select(schema.news)
            .where(schema.news.c.published_at >= published_after)
            .where(schema.news.c.analyzed_at.is_(None))
            .order_by(schema.news.c.published_at)
        )
        with self._engine.connect() as connection:
            return [_news_item(row) for row in connection.execute(statement).mappings()]

    def mark_analyzed(self, *items: NewsItem) -> None:
        if not items:
            return
        statement = (
            update(schema.news)
            .where(schema.news.c.id.in_([item.id for item in items]))
            .values(analyzed_at=datetime.now(UTC))
        )
        with self._engine.begin() as connection:
            connection.execute(statement)

    def tagged(self, asset: str, published_after: datetime) -> list[tuple[NewsItem, NewsTag]]:
        statement = (
            select(schema.news, schema.news_tags)
            .join(schema.news_tags, schema.news_tags.c.news_id == schema.news.c.id)
            .where(schema.news_tags.c.asset == asset)
            .where(schema.news.c.published_at >= published_after)
            .order_by(schema.news.c.published_at)
        )
        with self._engine.connect() as connection:
            return [
                (_news_item(row), _news_tag(row))
                for row in connection.execute(statement).mappings()
            ]


class SqlTagRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, *tags: NewsTag) -> None:
        now = datetime.now(UTC)
        _upsert(
            self._engine,
            schema.news_tags,
            [
                {
                    "news_id": tag.news_id,
                    "asset": tag.asset,
                    "direction": tag.direction,
                    "confidence": tag.confidence,
                    "model": tag.model,
                    "prompt_version": tag.prompt_version,
                    "tagged_at": now,
                }
                for tag in tags
            ],
        )


class SqlEventRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, *events: CalendarEvent) -> None:
        now = datetime.now(UTC)
        _upsert(
            self._engine,
            schema.calendar_events,
            [
                {
                    "id": event.id,
                    "date": event.date,
                    "country": event.country,
                    "event": event.event,
                    "category": event.category,
                    "importance": event.importance,
                    "consensus": event.consensus,
                    "previous": event.previous,
                    "actual": event.actual,
                    "fetched_at": now,
                }
                for event in events
            ],
        )

    def between(self, start: date, end: date) -> list[CalendarEvent]:
        start_at = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
        end_at = datetime.combine(end, datetime.max.time(), tzinfo=UTC)
        statement = (
            select(schema.calendar_events)
            .where(schema.calendar_events.c.date.between(start_at, end_at))
            .order_by(schema.calendar_events.c.date)
        )
        with self._engine.connect() as connection:
            return [_calendar_event(row) for row in connection.execute(statement).mappings()]


class SqlScoreRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, *scores: IndexScore) -> None:
        now = datetime.now(UTC)
        _upsert(
            self._engine,
            schema.scores,
            [
                {
                    "asset": score.asset,
                    "date": score.date.isoformat(),
                    "formula": score.formula,
                    "score": score.score,
                    "components_json": dict(score.components),
                    "n_news": score.n_news,
                    "n_events": score.n_events,
                    "report_md": score.report_md,
                    "created_at": now,
                }
                for score in scores
            ],
        )

    def series(self, asset: str, formula: str, start: date, end: date) -> list[IndexScore]:
        statement = (
            select(schema.scores)
            .where(schema.scores.c.asset == asset)
            .where(schema.scores.c.formula == formula)
            .where(schema.scores.c.date.between(start.isoformat(), end.isoformat()))
            .order_by(schema.scores.c.date)
        )
        with self._engine.connect() as connection:
            return [_index_score(row) for row in connection.execute(statement).mappings()]

    def latest_day(self) -> date | None:
        statement = select(func.max(schema.scores.c.date))
        with self._engine.connect() as connection:
            newest = connection.execute(statement).scalar()
        return date.fromisoformat(newest) if newest else None


class SqlForecastRepository:
    """Both forecast tables behave the same; only the subject columns differ."""

    def __init__(
        self,
        engine: Engine,
        table: Table,
        subject_column: str,
        vintage_columns: tuple[str, ...],
        row_factory: Callable[[Any], Any],
    ) -> None:
        self._engine = engine
        self._table = table
        self._subject = table.c[subject_column]
        self._vintage_columns = vintage_columns  # what makes a call distinct, besides the value
        self._row_factory = row_factory

    def add(self, *forecasts: Any) -> None:
        now = datetime.now(UTC)
        rows = []
        for forecast in forecasts:
            row = {
                column.name: getattr(forecast, column.name)
                for column in self._table.columns
                if column.name != "fetched_at"
            }
            rows.append({**row, "fetched_at": now})
        _upsert_keep_earliest(self._engine, self._table, rows)

    def latest(self, subject: str) -> list[Any]:
        newest: dict[tuple[Any, ...], Any] = {}
        for forecast in self._select(self._subject == subject):
            key = tuple(getattr(forecast, name) for name in self._vintage_columns)
            newest[key] = forecast  # rows arrive oldest first, so the last one wins
        return list(newest.values())

    def vintages(self, institution: str, *subject_and_horizon: Any) -> list[Any]:
        *subject_values, horizon_date = subject_and_horizon
        conditions = [
            self._table.c.institution == institution,
            self._table.c.horizon_date == horizon_date,
        ]
        for name, value in zip(self._vintage_columns[1:-1], subject_values, strict=True):
            conditions.append(self._table.c[name] == value)
        return self._select(*conditions)

    def as_of(self, subject: str, day: date) -> list[Any]:
        end_of_day = datetime.combine(day, datetime.max.time(), tzinfo=UTC)
        return self._select(self._subject == subject, self._table.c.published_at <= end_of_day)

    def _select(self, *conditions: Any) -> list[Any]:
        statement = (
            select(self._table)
            .where(*conditions)
            .order_by(self._table.c.published_at, self._table.c.id)
        )
        with self._engine.connect() as connection:
            return [self._row_factory(row) for row in connection.execute(statement).mappings()]


class SqlChainRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, *metrics: ChainMetric) -> None:
        now = datetime.now(UTC)
        _upsert(
            self._engine,
            schema.chain_metrics,
            [
                {
                    "asset": metric.asset,
                    "date": metric.date,
                    "metric": metric.metric,
                    "value": metric.value,
                    "source": metric.source,
                    "fetched_at": now,
                }
                for metric in metrics
            ],
        )

    def series(self, asset: str, metric: str, start: date, end: date) -> list[ChainMetric]:
        statement = (
            select(schema.chain_metrics)
            .where(schema.chain_metrics.c.asset == asset)
            .where(schema.chain_metrics.c.metric == metric)
            .where(schema.chain_metrics.c.date.between(start, end))
            .order_by(schema.chain_metrics.c.date)
        )
        with self._engine.connect() as connection:
            return [_chain_metric(row) for row in connection.execute(statement).mappings()]

    def latest(self, asset: str) -> dict[str, ChainMetric]:
        statement = (
            select(schema.chain_metrics)
            .where(schema.chain_metrics.c.asset == asset)
            .order_by(schema.chain_metrics.c.date)
        )
        with self._engine.connect() as connection:
            rows = [_chain_metric(row) for row in connection.execute(statement).mappings()]
        return {row.metric: row for row in rows}  # ascending dates: the last one wins


class SqlSpotRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, *prices: SpotPrice) -> None:
        now = datetime.now(UTC)
        _upsert(
            self._engine,
            schema.spot_prices,
            [
                {
                    "asset": price.asset,
                    "date": price.date,
                    "close": price.close,
                    "source": price.source,
                    "fetched_at": now,
                }
                for price in prices
            ],
        )

    def latest(self, asset: str) -> SpotPrice | None:
        statement = (
            select(schema.spot_prices)
            .where(schema.spot_prices.c.asset == asset)
            .order_by(schema.spot_prices.c.date.desc())
            .limit(1)
        )
        with self._engine.connect() as connection:
            row = connection.execute(statement).mappings().first()
        return _spot_price(row) if row else None

    def between(self, asset: str, start: date, end: date) -> list[SpotPrice]:
        statement = (
            select(schema.spot_prices)
            .where(schema.spot_prices.c.asset == asset)
            .where(schema.spot_prices.c.date.between(start, end))
            .order_by(schema.spot_prices.c.date)
        )
        with self._engine.connect() as connection:
            return [_spot_price(row) for row in connection.execute(statement).mappings()]


class SqlStore:
    """Composes one SQL repository per table. Refuses a database that is not migrated."""

    def __init__(self, engine: Engine) -> None:
        if not db.is_at_head(engine):
            raise RuntimeError(
                f"database at {engine.url} is at revision {db.current_revision(engine)}, "
                f"head is {db.head_revision()}: run `manc migrate`"
            )
        self.news = SqlNewsRepository(engine)
        self.tags = SqlTagRepository(engine)
        self.events = SqlEventRepository(engine)
        self.scores = SqlScoreRepository(engine)
        self.forecasts_asset = SqlForecastRepository(
            engine,
            schema.forecasts_asset,
            "asset",
            ("institution", "asset", "horizon_date"),
            _forecast_asset,
        )
        self.forecasts_macro = SqlForecastRepository(
            engine,
            schema.forecasts_macro,
            "economy",
            ("institution", "economy", "metric", "horizon_date"),
            _forecast_macro,
        )
        self.spot = SqlSpotRepository(engine)
        self.chain = SqlChainRepository(engine)


def _news_item(row: Any) -> NewsItem:
    return NewsItem(
        id=row["id"],
        source=row["source"],
        title=row["title"],
        url=row["url"],
        published_at=_utc(row["published_at"]),
        summary=row["summary"],
    )


def _news_tag(row: Any) -> NewsTag:
    return NewsTag(
        news_id=row["news_id"],
        asset=row["asset"],
        direction=row["direction"],
        confidence=row["confidence"],
        model=row["model"],
        prompt_version=row["prompt_version"],
    )


def _calendar_event(row: Any) -> CalendarEvent:
    return CalendarEvent(
        id=row["id"],
        date=_utc(row["date"]),
        country=row["country"],
        event=row["event"],
        category=row["category"],
        importance=row["importance"],
        consensus=row["consensus"],
        previous=row["previous"],
        actual=row["actual"],
    )


def _index_score(row: Any) -> IndexScore:
    return IndexScore(
        asset=row["asset"],
        date=date.fromisoformat(row["date"]),
        score=row["score"],
        formula=row["formula"],
        components=row["components_json"],
        n_news=row["n_news"],
        n_events=row["n_events"],
        report_md=row["report_md"],
    )


def _forecast_fields(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "institution": row["institution"],
        "horizon_date": row["horizon_date"],
        "horizon_label": row["horizon_label"],
        "value": row["value"],
        "published_at": _utc(row["published_at"]),
        "source_url": row["source_url"],
        "source_kind": row["source_kind"],
        "confidence": row["confidence"],
        "model": row["model"],
    }


def _forecast_asset(row: Any) -> ForecastAsset:
    return ForecastAsset(asset=row["asset"], **_forecast_fields(row))


def _forecast_macro(row: Any) -> ForecastMacro:
    return ForecastMacro(economy=row["economy"], metric=row["metric"], **_forecast_fields(row))


def _chain_metric(row: Any) -> ChainMetric:
    return ChainMetric(
        asset=row["asset"],
        date=row["date"],
        metric=row["metric"],
        value=row["value"],
        source=row["source"],
    )


def _spot_price(row: Any) -> SpotPrice:
    return SpotPrice(asset=row["asset"], date=row["date"], close=row["close"], source=row["source"])
