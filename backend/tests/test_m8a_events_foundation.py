"""M8-A events foundation tests (STEP 19.19, DEC-015/DEC-016).

DB-backed where persistence matters (runs when PostgreSQL is reachable,
skips otherwise — see `tests/conftest.py`; schema migrates to `head`,
which includes the 0017 `event_types`/`user_events` tables). The
migration-chain check is DB-free.

Covers the task A–Q matrix:
A. migration creates event_types
B. exactly 8 seeded codes
C. exact labels
D. sort_order=0
E. active=true
F. event_types codes are correct (incl. no office)
G. user_events schema exists
H. title constraint
I. location constraint
J. notes constraint
K. user_id -> users CASCADE
L. event_type_id -> event_types RESTRICT
M. user_events index(user_id,event_date)
N. duplicate events are allowed
O. event_time nullable
P. migration downgrade removes event tables cleanly
Q. migration upgrade after downgrade works again

Plus R: repository round-trip (create/get/list/update/delete,
owner isolation) and the read-only EventType lookup.

Does NOT touch CRUD routes, R36, outfit generation, or Flutter —
those belong to later M8 steps.
"""

from __future__ import annotations

from datetime import date, time
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.infrastructure.db.models import EventType, UserEvent, Users
from app.infrastructure.db.repositories import (
    EventTypeRepositorySQL,
    UserEventRepositorySQL,
)
from app.infrastructure.db.session import DATABASE_URL
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

EXPECTED_CODES = {
    "casual",
    "formal",
    "business",
    "date",
    "party",
    "travel",
    "workout",
    "other",
}

EXPECTED_LABELS = {
    "casual": "Casual",
    "formal": "Formal",
    "business": "Business",
    "date": "Date Night",
    "party": "Party",
    "travel": "Travel",
    "workout": "Workout",
    "other": "Other",
}


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("script_location", "alembic")
    config.set_main_option("sqlalchemy.url", DATABASE_URL)
    return config


def _seed_user(session, subject: str):
    user = Users(
        auth_provider="m8a", auth_subject=subject, display_name="M8-A User"
    )
    session.add(user)
    session.commit()
    return user.id


def _seed_event(
    session,
    user_id,
    *,
    title="Company Gala",
    event_type="formal",
    event_date=None,
    event_time=None,
    location=None,
    notes=None,
):
    row = UserEvent(
        user_id=user_id,
        title=title,
        event_type_id=event_type,
        event_date=event_date or date(2026, 8, 15),
        event_time=event_time,
        location=location,
        notes=notes,
    )
    session.add(row)
    session.flush()
    return row


# ---------------------------------------------------------------------------
# Chain: linear single head 0016 -> 0017 -> 0018 -> 0019 -> 0020 (DB-free)
# ---------------------------------------------------------------------------


def test_chain_linear_single_head_0016_to_0017():
    """Migration chain stays linear with 0021 as the single head.

    The M8-A link (0016 -> 0017) is preserved verbatim; the M9 save batch
    appends the linear 0017 -> 0018 CHECK-widen link (STEP 19.24); the
    M11 feedback batch appends the linear 0018 -> 0019 feedback_events
    link (STEP 19.27); D-AUTH-1 appends 0019 -> 0020 auth_sessions;
    0021 appends outfit_run_type seed.
    """
    script = ScriptDirectory.from_config(_alembic_config())
    assert tuple(script.get_heads()) == ("0021",)
    revision = script.get_revision("0017")
    assert revision is not None
    assert revision.down_revision == "0016"
    tip = script.get_revision("0018")
    assert tip is not None
    assert tip.down_revision == "0017"
    rev19 = script.get_revision("0019")
    assert rev19 is not None
    assert rev19.down_revision == "0018"
    rev20 = script.get_revision("0020")
    assert rev20 is not None
    assert rev20.down_revision == "0019"
    head = script.get_revision("0021")
    assert head is not None
    assert head.down_revision == "0020"


# ---------------------------------------------------------------------------
# A–F: event_types table + seed exactness
# ---------------------------------------------------------------------------


def test_A_migration_creates_event_types(db):
    """A. The 0017 migration creates the event_types table."""
    Session = make_session()
    with Session() as session:
        assert inspect(session.bind).has_table("event_types")


def test_B_exactly_8_seeded_codes(db):
    """B. Exactly the 8 frozen codes are seeded — no more, no fewer."""
    Session = make_session()
    with Session() as session:
        codes = set(session.execute(select(EventType.code)).scalars().all())
        assert codes == EXPECTED_CODES


def test_C_exact_labels(db):
    """C. Seed labels match the frozen mockTypes vocabulary verbatim."""
    Session = make_session()
    with Session() as session:
        rows = session.execute(select(EventType.code, EventType.label)).all()
        assert {code: label for code, label in rows} == EXPECTED_LABELS


def test_D_sort_order_zero(db):
    """D. Every seed row has sort_order=0 (0005 precedent, no invention)."""
    Session = make_session()
    with Session() as session:
        orders = set(session.execute(select(EventType.sort_order)).scalars().all())
        assert orders == {0}


def test_E_active_true(db):
    """E. Every seed row is active."""
    Session = make_session()
    with Session() as session:
        flags = set(session.execute(select(EventType.active)).scalars().all())
        assert flags == {True}


def test_F_codes_correct_no_office(db):
    """F. `office` (M5-only) is absent; all 8 M8 codes resolve read-only."""
    Session = make_session()
    with Session() as session:
        repo = EventTypeRepositorySQL(session)
        assert repo.get_by_code(code="office") is None
        assert {r.code for r in repo.list_active()} == EXPECTED_CODES
        assert repo.get_by_code(code="date").label == "Date Night"
        assert repo.get_by_code(code="nope") is None


# ---------------------------------------------------------------------------
# G–J: user_events schema + text constraints
# ---------------------------------------------------------------------------


def test_G_user_events_schema_exists(db):
    """G. user_events exists with the exact frozen columns."""
    Session = make_session()
    with Session() as session:
        insp = inspect(session.bind)
        assert insp.has_table("user_events")
        columns = {c["name"]: c for c in insp.get_columns("user_events")}
        assert set(columns) == {
            "id",
            "user_id",
            "title",
            "event_type_id",
            "event_date",
            "event_time",
            "location",
            "notes",
            "created_at",
            "updated_at",
        }
        assert columns["user_id"]["nullable"] is False
        assert columns["title"]["nullable"] is False
        assert columns["event_type_id"]["nullable"] is False
        assert columns["event_date"]["nullable"] is False
        assert columns["event_time"]["nullable"] is True
        assert columns["location"]["nullable"] is True
        assert columns["notes"]["nullable"] is True


def test_H_title_constraint(db):
    """H. title enforces char_length 1..200 (empty/overlong rejected)."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "h-user")
        with pytest.raises(IntegrityError):
            _seed_event(session, user_id, title="")
        session.rollback()
        with pytest.raises(IntegrityError):
            _seed_event(session, user_id, title="x" * 201)
        session.rollback()
        row = _seed_event(session, user_id, title="y" * 200)
        session.commit()
        assert row.id is not None


def test_I_location_constraint(db):
    """I. location is NULL or char_length 1..200 (empty/overlong rejected)."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "i-user")
        with pytest.raises(IntegrityError):
            _seed_event(session, user_id, location="")
        session.rollback()
        with pytest.raises(IntegrityError):
            _seed_event(session, user_id, location="x" * 201)
        session.rollback()
        row = _seed_event(session, user_id, location=None)
        session.commit()
        assert row.location is None


def test_J_notes_constraint(db):
    """J. notes is NULL or char_length 1..2000 (empty/overlong rejected)."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "j-user")
        with pytest.raises(IntegrityError):
            _seed_event(session, user_id, notes="")
        session.rollback()
        with pytest.raises(IntegrityError):
            _seed_event(session, user_id, notes="x" * 2001)
        session.rollback()
        row = _seed_event(session, user_id, notes="n" * 2000)
        session.commit()
        assert row.notes == "n" * 2000


# ---------------------------------------------------------------------------
# K–M: FK behavior + index
# ---------------------------------------------------------------------------


def test_K_user_delete_cascades_to_events(db):
    """K. Deleting a user removes their events (CASCADE, PR-10)."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "k-user")
        _seed_event(session, user_id)
        session.commit()
        assert (
            session.execute(
                select(UserEvent).where(UserEvent.user_id == user_id)
            ).scalar_one_or_none()
            is not None
        )
        session.execute(text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)})
        session.commit()
        assert (
            session.execute(
                select(UserEvent).where(UserEvent.user_id == user_id)
            ).scalar_one_or_none()
            is None
        )


def test_L_event_type_delete_restricted_while_referenced(db):
    """L. A referenced event_types row cannot be deleted (RESTRICT, R34)."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "l-user")
        _seed_event(session, user_id, event_type="party")
        session.commit()
        with pytest.raises(IntegrityError):
            session.execute(
                text("DELETE FROM event_types WHERE code = 'party'")
            )
            session.flush()
        session.rollback()
        # The event row survives the refused vocabulary delete.
        assert (
            session.execute(
                select(UserEvent).where(UserEvent.user_id == user_id)
            ).scalar_one_or_none()
            is not None
        )


def test_M_user_events_index(db):
    """M. The (user_id, event_date) list index exists (A9)."""
    Session = make_session()
    with Session() as session:
        indexes = inspect(session.bind).get_indexes("user_events")
        by_name = {ix["name"]: ix for ix in indexes}
        assert "ix_user_events_user_id_event_date" in by_name
        assert list(by_name["ix_user_events_user_id_event_date"]["column_names"]) == [
            "user_id",
            "event_date",
        ]


# ---------------------------------------------------------------------------
# N–O: duplicates + nullable time
# ---------------------------------------------------------------------------


def test_N_duplicate_events_allowed(db):
    """N. Retries/duplicates create separate rows (F-8, no unique beyond PK)."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "n-user")
        first = _seed_event(session, user_id)
        second = _seed_event(session, user_id)
        session.commit()
        assert first.id != second.id
        rows = (
            session.execute(
                select(UserEvent).where(UserEvent.user_id == user_id)
            )
            .scalars()
            .all()
        )
        assert len(rows) == 2


def test_O_event_time_nullable(db):
    """O. event_time is optional wall-clock TIME (None or HH:mm value)."""
    Session = make_session()
    with Session() as session:
        user_id = _seed_user(session, "o-user")
        absent = _seed_event(session, user_id, event_time=None)
        present = _seed_event(
            session, user_id, event_time=time(19, 0), title="Timed"
        )
        session.commit()
        assert absent.event_time is None
        assert (present.event_time.hour, present.event_time.minute) == (19, 0)
        fetched = session.get(UserEvent, present.id)
        assert (fetched.event_time.hour, fetched.event_time.minute) == (19, 0)


# ---------------------------------------------------------------------------
# P–Q: downgrade removes cleanly, upgrade restores (single test, safe)
# ---------------------------------------------------------------------------


def test_PQ_downgrade_removes_and_upgrade_restores(db):
    """P+Q. 0017 downgrade drops both tables; upgrade re-seeds exactly.

    Downgrade and upgrade run inside one test with a guaranteed
    restore so later files always observe `head`.
    """
    Session = make_session()
    config = _alembic_config()
    with Session() as session:
        assert inspect(session.bind).has_table("user_events")
        assert inspect(session.bind).has_table("event_types")
    try:
        command.downgrade(config, "0016")
        with Session() as session:
            assert not inspect(session.bind).has_table("user_events")
            assert not inspect(session.bind).has_table("event_types")
    finally:
        command.upgrade(config, "head")
    with Session() as session:
        assert inspect(session.bind).has_table("user_events")
        assert inspect(session.bind).has_table("event_types")
        codes = set(session.execute(select(EventType.code)).scalars().all())
        assert codes == EXPECTED_CODES


# ---------------------------------------------------------------------------
# R: repository round-trip (foundation plumbing for upcoming CRUD)
# ---------------------------------------------------------------------------


def test_R_repository_crud_round_trip_owner_scoped(db):
    """R. Port+SQL foundation supports the upcoming CRUD (owner-scoped)."""
    Session = make_session()
    with Session() as session:
        owner = _seed_user(session, "r-owner")
        stranger = _seed_user(session, "r-stranger")
        repo = UserEventRepositorySQL(session)

        created = repo.create(
            user_id=owner,
            title="Company Gala",
            event_type="formal",
            event_date=date(2026, 8, 15),
            event_time=time(19, 0),
            location="Grand Ballroom",
            notes="Black tie",
        )
        session.commit()
        assert created.id is not None
        assert created.event_type == "formal"
        assert created.created_at is not None
        assert created.updated_at is not None

        # Owner read; strangers resolve to nothing (404 maps later).
        assert repo.get_for_user(user_id=owner, event_id=created.id).id == created.id
        assert repo.get_for_user(user_id=stranger, event_id=created.id) is None
        assert repo.get_for_user(user_id=owner, event_id=uuid4()) is None

        # Second row for ordering/filter coverage.
        repo.create(
            user_id=owner,
            title="Brunch",
            event_type="casual",
            event_date=date(2026, 7, 20),
        )
        session.commit()
        items, total = repo.list_for_user(user_id=owner)
        assert total == 2
        assert [i.title for i in items] == ["Brunch", "Company Gala"]
        upcoming, upcoming_total = repo.list_for_user(
            user_id=owner, from_date=date(2026, 8, 1)
        )
        assert upcoming_total == 1
        assert upcoming[0].title == "Company Gala"
        foreign_items, foreign_total = repo.list_for_user(user_id=stranger)
        assert (foreign_items, foreign_total) == ([], 0)

        # Full-replace update incl. nullable clearing; foreign update is None.
        updated = repo.update(
            user_id=owner,
            event_id=created.id,
            title="Company Gala v2",
            event_type="party",
            event_date=date(2026, 8, 16),
            event_time=None,
            location=None,
            notes=None,
        )
        session.commit()
        assert updated.title == "Company Gala v2"
        assert updated.event_type == "party"
        assert updated.location is None
        assert (
            repo.update(
                user_id=stranger,
                event_id=created.id,
                title="Hijack",
                event_type="casual",
                event_date=date(2026, 8, 16),
            )
            is None
        )

        # Delete is owner-scoped; the row is gone afterwards.
        repo.delete(user_id=stranger, event_id=created.id)
        session.commit()
        assert repo.get_for_user(user_id=owner, event_id=created.id) is not None
        repo.delete(user_id=owner, event_id=created.id)
        session.commit()
        assert repo.get_for_user(user_id=owner, event_id=created.id) is None
