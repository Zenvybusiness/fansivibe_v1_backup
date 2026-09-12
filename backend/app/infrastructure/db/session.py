"""Database engine/session setup for the Fansivibe backend.

Reads the connection URL from the configured ``Settings.database_url``
(``DATABASE_URL`` env var, default
``postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe``).

This module is intentionally the only place that knows how to build a
connection. Application code depends on the ``get_db`` generator (FastAPI
dependency) or on a session factory for tests.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import get_settings

_settings = get_settings()
DATABASE_URL = _settings.database_url


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_engine_kwargs: dict = {"pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(
        {
            "pool_size": _settings.db_pool_size,
            "max_overflow": _settings.db_max_overflow,
            "pool_timeout": _settings.db_pool_timeout_s,
            "pool_recycle": _settings.db_pool_recycle_s,
        }
    )

engine: Engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency yielding a session and closing it afterwards."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
