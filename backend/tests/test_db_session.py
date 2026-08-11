"""DB-backed integration tests for the session/migration foundation.

Covers the plan's §11 item 4:
- session factory produces a working session
- the foundation migration is idempotent (`upgrade head` is a no-op re-run)
- the slice knowledge seed is present (`looks`, `run_types`, `signal_types`)

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, text

from app.infrastructure.db.session import DATABASE_URL
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    return config


def test_session_factory_connects(db):
    Session = make_session()
    with Session() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1


def test_migration_upgrade_head_is_idempotent(db):
    config = _alembic_config()
    command.upgrade(config, "head")
    command.upgrade(config, "head")


def test_knowledge_seed_looks_present(db):
    Session = make_session()
    with Session() as session:
        rows = session.execute(
            select(text("code"))
            .select_from(text("looks"))
            .order_by(text("code"))
        ).scalars().all()
    assert rows == [
        "brushed_up_undercut",
        "classic_pompadour",
        "side_part",
        "textured_quiff",
    ]


def test_knowledge_seed_run_and_signal_types(db):
    Session = make_session()
    with Session() as session:
        run_types = session.execute(
            select(text("code")).select_from(text("run_types"))
        ).scalars().all()
        signal_types = session.execute(
            select(text("code")).select_from(text("signal_types"))
        ).scalars().all()
    assert run_types == ["hairstyle"]
    assert signal_types == ["analysis_updated", "look_saved"]
