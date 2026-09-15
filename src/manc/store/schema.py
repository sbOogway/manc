"""Declared schema, the single source of truth for Alembic autogenerate.

See docs/blueprint.md section 6. Change a table here, then run
``uv run alembic revision --autogenerate -m "..."`` and review the generated file.
"""

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

metadata = MetaData()

news = Table(
    "news",
    metadata,
    Column("id", String(40), primary_key=True),  # sha1(url)
    Column("source", String(64), nullable=False),
    Column("title", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False),
    Column("summary", Text, nullable=False, default=""),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
)

news_tags = Table(
    "news_tags",
    metadata,
    Column("news_id", String(40), ForeignKey("news.id", ondelete="CASCADE"), primary_key=True),
    Column("asset", String(16), primary_key=True),
    Column("direction", Integer, nullable=False),  # -1, 0, +1
    Column("confidence", Float, nullable=False),  # 0..1
    Column("tagged_at", DateTime(timezone=True), nullable=False),
)

calendar_events = Table(
    "calendar_events",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("date", DateTime(timezone=True), nullable=False),
    Column("country", String(64), nullable=False),
    Column("event", Text, nullable=False),
    Column("category", String(32), nullable=False),
    Column("importance", Integer, nullable=False),  # 1 low, 2 medium, 3 high
    Column("consensus", Float),
    Column("previous", Float),
    Column("actual", Float),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
)

scores = Table(
    "scores",
    metadata,
    Column("asset", String(16), primary_key=True),
    Column("date", String(10), primary_key=True),  # ISO date, e.g. 2026-09-15
    Column("formula", String(16), primary_key=True),
    Column("score", Float, nullable=False),
    Column("components_json", JSON, nullable=False),
    Column("n_news", Integer, nullable=False),
    Column("n_events", Integer, nullable=False),
    Column("report_md", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
