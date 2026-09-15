"""Store implementation over SQLAlchemy Core: one repository per table in schema.py."""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Engine, Table, select
from sqlalchemy.dialects import postgresql, sqlite

from manc.formulas.contract import IndexScore
from manc.models import CalendarEvent, NewsItem, NewsTag
from manc.store import db, schema


def _utc(value: datetime) -> datetime:
    """SQLite drops the timezone; everything stored is UTC, so put it back on read."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _upsert(engine: Engine, table: Table, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    insert = {"sqlite": sqlite.insert, "postgresql": postgresql.insert}[engine.dialect.name]
    key_columns = [column.name for column in table.primary_key.columns]
    statement = insert(table).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=key_columns,
        set_={
            column.name: getattr(statement.excluded, column.name)
            for column in table.columns
            if column.name not in key_columns
        },
    )
    with engine.begin() as connection:
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
        )

    def since(self, published_after: datetime) -> list[NewsItem]:
        statement = (
            select(schema.news)
            .where(schema.news.c.published_at >= published_after)
            .order_by(schema.news.c.published_at)
        )
        with self._engine.connect() as connection:
            return [_news_item(row) for row in connection.execute(statement).mappings()]

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


class SqlStore:
    """Composes one SQL repository per table. Refuses a database that is not migrated."""

    def __init__(self, engine: Engine) -> None:
        if not db.is_at_head(engine):
            raise RuntimeError(
                f"database at {engine.url} is at revision {db.current_revision(engine)}, "
                f"head is {db.head_revision()}: run `uv run alembic upgrade head`"
            )
        self.news = SqlNewsRepository(engine)
        self.tags = SqlTagRepository(engine)
        self.events = SqlEventRepository(engine)
        self.scores = SqlScoreRepository(engine)


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
