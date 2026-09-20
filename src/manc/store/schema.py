"""Declared schema, the single source of truth for Alembic autogenerate.

See docs/blueprint.md section 6. Change a table here, then run
``uv run alembic revision --autogenerate -m "..."`` and review the generated file.
"""

from sqlalchemy import (
    JSON,
    Column,
    Date,
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
    Column("analyzed_at", DateTime(timezone=True)),  # when a daily run tagged it; null until then
)

news_tags = Table(
    "news_tags",
    metadata,
    Column("news_id", String(40), ForeignKey("news.id", ondelete="CASCADE"), primary_key=True),
    Column("asset", String(16), primary_key=True),
    Column("direction", Integer, nullable=False),  # -1, 0, +1
    Column("confidence", Float, nullable=False),  # 0..1
    Column("model", String(128), nullable=False, default=""),
    Column("prompt_version", String(16), nullable=False, default=""),
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


# Forecasts are point-in-time: a row is one vintage and is never overwritten (blueprint §6).
def _forecast_columns() -> list[Column]:
    """The tail both forecast tables share; fresh Column objects each call."""
    return [
        Column("horizon_date", Date, nullable=False),
        Column("horizon_label", String(64), nullable=False),
        Column("value", Float, nullable=False),
        Column("published_at", DateTime(timezone=True), nullable=False),
        Column("source_url", Text, nullable=False),
        Column("source_kind", String(16), nullable=False),  # extracted | structured
        Column("confidence", Float, nullable=False),  # 0..1
        Column("model", String(128), nullable=False, default=""),
        Column("fetched_at", DateTime(timezone=True), nullable=False),
    ]


forecasts_asset = Table(
    "forecasts_asset",
    metadata,
    Column("id", String(40), primary_key=True),  # sha1(institution | asset | horizon | value)
    Column("institution", String(64), nullable=False),
    Column("asset", String(16), nullable=False),
    *_forecast_columns(),
)

forecasts_macro = Table(
    "forecasts_macro",
    metadata,
    Column("id", String(40), primary_key=True),  # sha1(institution | economy:metric | ...)
    Column("institution", String(64), nullable=False),
    Column("economy", String(64), nullable=False),
    Column("metric", String(32), nullable=False),  # policy_rate | cpi | gdp | unemployment
    *_forecast_columns(),
)

spot_prices = Table(
    "spot_prices",
    metadata,
    Column("asset", String(16), primary_key=True),
    Column("date", Date, primary_key=True),
    Column("close", Float, nullable=False),
    Column("source", String(32), nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
)
