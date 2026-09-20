"""Engine construction and programmatic Alembic entry points."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine

DEFAULT_URL = "sqlite:///data/manc.db"
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"  # inside the package, no checkout


def database_url() -> str:
    return os.environ.get("MANC_DB_URL", DEFAULT_URL)


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url())


def _config(url: str) -> Config:
    cfg = Config()  # no ini file: the CLI's alembic.ini only serves `alembic revision`
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["url"] = url
    return cfg


def upgrade(url: str | None = None, revision: str = "head") -> None:
    command.upgrade(_config(url or database_url()), revision)


def downgrade(url: str | None = None, revision: str = "-1") -> None:
    command.downgrade(_config(url or database_url()), revision)


def head_revision() -> str:
    return ScriptDirectory.from_config(_config(DEFAULT_URL)).get_current_head() or ""


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def is_at_head(engine: Engine) -> bool:
    return current_revision(engine) == head_revision()
