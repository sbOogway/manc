"""Engine construction and programmatic Alembic entry points."""

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

DEFAULT_URL = "sqlite:///data/manc.db"
_ROOT = Path(__file__).resolve().parents[3]


def database_url() -> str:
    return os.environ.get("MANC_DB_URL", DEFAULT_URL)


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or database_url())


def _config(url: str) -> Config:
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    cfg.attributes["url"] = url
    return cfg


def upgrade(url: str | None = None, revision: str = "head") -> None:
    command.upgrade(_config(url or database_url()), revision)


def downgrade(url: str | None = None, revision: str = "-1") -> None:
    command.downgrade(_config(url or database_url()), revision)
