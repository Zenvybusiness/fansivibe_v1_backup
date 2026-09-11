"""Test fixtures.

DB-backed tests opt in via ``pytestmark = pytest.mark.usefixtures("db")`` and
skip cleanly when PostgreSQL is unreachable (this environment cannot run one;
set `DATABASE_URL` to enable them). When a database IS reachable, the schema
is migrated to `head` once per session and tables are truncated around each
test so every test starts clean.

Unit tests that never touch the database (engine, intent, analysis rules)
do not request the `db` fixture and run everywhere.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.db.session import DATABASE_URL

_TRUNCATE = (
    "TRUNCATE learning_signals, saved_looks, analysis_runs, "
    "wardrobe_wear_events, wardrobe_wear_groups, user_state, users CASCADE"
)


def db_reachable() -> bool:
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _run_migrations(url: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def migrated_db() -> str:
    if not db_reachable():
        pytest.skip(
            "PostgreSQL not reachable at DATABASE_URL — set it to enable "
            "DB-backed tests (e.g. `docker compose up postgres`)."
        )
    _run_migrations(DATABASE_URL)
    return DATABASE_URL


@pytest.fixture
def db(migrated_db: str):
    """Session-scoped connection with tables truncated before/after the test."""
    Session: sessionmaker = make_session(migrated_db)
    with Session() as session:
        session.execute(text(_TRUNCATE))
        session.commit()
    yield Session
    with Session() as session:
        session.execute(text(_TRUNCATE))
        session.commit()


def make_session(url: str = DATABASE_URL) -> sessionmaker:
    engine = create_engine(url)
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
