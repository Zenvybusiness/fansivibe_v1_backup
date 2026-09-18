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

import os

# D-AUTH-1: the shared dev-token fallback (`Bearer dev` → seeded dev
# user) is DISABLED by default and enabled here for the test suite
# only, so the existing suites keep their historical identity while
# production can never silently inherit it. Set before any `app.*`
# import because settings are cached at first access.
os.environ.setdefault("FANSIVIBE_ALLOW_DEV_TOKEN", "true")
os.environ.setdefault("FANSIVIBE_AUTH_SECRET", "test-only-auth-secret")
# 21.2: the local auth rate limiter stays OFF for the historical suite
# (deterministic tests must never 429); dedicated rate-limit tests
# enable it explicitly per-test.
os.environ.setdefault("FANSIVIBE_RATE_LIMIT_ENABLED", "false")

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.infrastructure.db.session import DATABASE_URL

# Phase-13: DB-backed tests NEVER touch the authoritative database.
# Set FANSIVIBE_TEST_DATABASE_URL to an isolated database (e.g. the
# `fansivibe_test` database in the same container); without it the
# DB-backed tests skip instead of destroying production QA data.
# Applied to DATABASE_URL before any `app.*` import because settings
# (and alembic's env.py, which re-reads the imported default) cache it
# at first access.
_TEST_DATABASE_URL = os.environ.get("FANSIVIBE_TEST_DATABASE_URL", "")
if _TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
TEST_DATABASE_URL = _TEST_DATABASE_URL

_TRUNCATE = (
    "TRUNCATE learning_signals, activity_days, saved_looks, analysis_runs, "
    "feedback_events, user_events, wardrobe_wear_events, wardrobe_wear_groups, "
    "user_sessions, user_state, users CASCADE"
)


def _run_migrations(url: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def migrated_db() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip(
            "FANSIVIBE_TEST_DATABASE_URL is not set — refusing to TRUNCATE "
            "the authoritative database. Create an isolated test database "
            "(e.g. `CREATE DATABASE fansivibe_test`) and set the variable."
        )
    if TEST_DATABASE_URL == DATABASE_URL:
        pytest.fail(
            "FANSIVIBE_TEST_DATABASE_URL points at the authoritative "
            "database — refusing to TRUNCATE it.",
            pytrace=False,
        )
    try:
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        pytest.skip(
            "Test PostgreSQL not reachable at FANSIVIBE_TEST_DATABASE_URL."
        )
    _run_migrations(TEST_DATABASE_URL)
    return TEST_DATABASE_URL


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


@pytest.fixture(autouse=True)
def _cleanup_dependency_overrides():
    from app.main import app

    yield
    app.dependency_overrides.clear()
