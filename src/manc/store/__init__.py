"""Persistence: SQLAlchemy Core tables (schema.py) and Alembic migrations (manc/migrations/)."""

from manc.store import schema  # re-exported so paracelsus can reach `manc.store:schema`

__all__ = ["schema"]
