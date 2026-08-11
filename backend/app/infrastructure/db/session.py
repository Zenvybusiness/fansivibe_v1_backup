"""Database engine/session setup for the Fansivibe backend.

Reads the connection URL from the ``DATABASE_URL`` environment variable
(default ``postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe``).

This module is intentionally the only place that knows how to build a
connection. Application code depends on the ``get_db`` generator (FastAPI
dependency) or on a session factory for tests.
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe"
)

DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


engine: Engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    """FastAPI dependency yielding a session and closing it afterwards."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
