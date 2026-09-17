"""Alembic migrations bring any database to the schema declared in manc.store.schema."""

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from manc.store import db, schema

EXPECTED_TABLES = {
    "news",
    "news_tags",
    "calendar_events",
    "scores",
    "forecasts_asset",
    "forecasts_macro",
    "spot_prices",
}


@pytest.fixture
def url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


def _tables(url: str) -> set[str]:
    engine = db.make_engine(url)
    try:
        return set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_head_creates_all_tables(url: str) -> None:
    db.upgrade(url)
    assert _tables(url) == EXPECTED_TABLES


def test_upgrade_is_idempotent(url: str) -> None:
    db.upgrade(url)
    db.upgrade(url)
    assert _tables(url) == EXPECTED_TABLES


def test_downgrade_base_removes_all_tables(url: str) -> None:
    db.upgrade(url)
    db.downgrade(url, "base")
    assert _tables(url) == set()


def test_migrations_match_declared_schema(url: str) -> None:
    """If schema.py changes without a new migration, this fails."""
    db.upgrade(url)
    engine = db.make_engine(url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            diff = compare_metadata(ctx, schema.metadata)
    finally:
        engine.dispose()
    assert diff == [], f"schema drift between migrations and schema.py: {diff}"


def test_database_url_defaults_to_sqlite_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MANC_DB_URL", raising=False)
    assert db.database_url() == "sqlite:///data/manc.db"


def test_database_url_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MANC_DB_URL", "postgresql+psycopg://u:p@h/manc")
    assert db.database_url() == "postgresql+psycopg://u:p@h/manc"
