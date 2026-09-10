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
    assert signal_types == ["analysis_updated", "look_saved", "outfit_selected"]


# ============================================================================
# STEP 11.13 — typed learning signals + JSONB dict adaptation (DB-backed).
#
# A. Each seeded signal_type persists verbatim; unknown codes are rejected by
#    the existing FK and leave no row.
# D/E. complete()/fail() accept plain Python dicts (the psycopg3 adaptation
#    failure made every live completion/failure raise) and reach the intended
#    terminal states. Dicts are passed as dicts — never pre-serialized.
# ============================================================================


def _signal_user(session):
    from app.infrastructure.db.models import Users, UserState

    user = Users(
        auth_provider="dev", auth_subject="signal-user", display_name="Sig"
    )
    session.add(user)
    session.flush()
    session.add(UserState(user_id=user.id))
    session.commit()
    return user.id


def test_signal_insert_persists_requested_type(db):
    from app.infrastructure.db.models import LearningSignals
    from app.infrastructure.db.repositories import LearningSignalRepositorySQL

    Session = make_session()
    with Session() as session:
        uid = _signal_user(session)
        repo = LearningSignalRepositorySQL(session)
        for code in ("look_saved", "analysis_updated", "outfit_selected"):
            repo.insert_look_saved(
                user_id=uid,
                signal_type=code,
                label=f"label-{code}",
                context={"code": code},
            )
        session.commit()
        rows = session.execute(
            select(text("signal_type"), text("label"))
            .select_from(text("learning_signals"))
            .where(text("user_id = :uid"))
            .order_by(text("label")),
            {"uid": str(uid)},
        ).all()
    assert [(r[0], r[1]) for r in rows] == [
        ("analysis_updated", "label-analysis_updated"),
        ("look_saved", "label-look_saved"),
        ("outfit_selected", "label-outfit_selected"),
    ]


def test_signal_insert_rejects_unknown_type_without_row(db):
    import sqlalchemy.exc

    from app.infrastructure.db.models import LearningSignals
    from app.infrastructure.db.repositories import LearningSignalRepositorySQL

    Session = make_session()
    with Session() as session:
        uid = _signal_user(session)
        repo = LearningSignalRepositorySQL(session)
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            repo.insert_look_saved(
                user_id=uid,
                signal_type="not_a_signal",
                label="nope",
                context={},
            )
        session.rollback()
        count = session.execute(
            select(text("count(*)")).select_from(text("learning_signals"))
        ).scalar_one()
    assert count == 0


def test_complete_with_dict_result_succeeds(db):
    """D. Plain-dict `result` completes the run (old code: adapt error)."""
    from app.infrastructure.db.repositories import AnalysisRunRepositorySQL

    Session = make_session()
    with Session() as session:
        uid = _signal_user(session)
        repo = AnalysisRunRepositorySQL(session)
        run_id = repo.create(
            user_id=uid, run_type="hairstyle", input_media={"key": "k"}
        )
        result = {
            "appearance": {"faceShape": "Oval", "sourceRunId": str(run_id)},
            "confidence": 0.62,
            "needs_more_data": True,
            "recommendations": {"top": {"id": "textured_quiff"}, "alternatives": []},
        }
        assert (
            repo.complete(
                run_id=run_id, user_id=uid, status="completed", result=result
            )
            is True
        )
        record = repo.get_for_user(user_id=uid, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result == result
    assert record.error is None


def test_fail_with_dict_error_reaches_terminal_failed(db):
    """E. Plain-dict `error` marks the run failed (never stuck pending)."""
    from app.infrastructure.db.repositories import AnalysisRunRepositorySQL

    Session = make_session()
    with Session() as session:
        uid = _signal_user(session)
        repo = AnalysisRunRepositorySQL(session)
        run_id = repo.create(user_id=uid, run_type="hairstyle")
        error = {
            "code": "PROCESSING_FAILURE",
            "message": "We couldn't finish this request. Please try again.",
            "details": {"run_id": str(run_id)},
        }
        assert repo.fail(run_id=run_id, user_id=uid, error=error) is True
        record = repo.get_for_user(user_id=uid, run_id=run_id)
    assert record is not None
    assert record.status == "failed"
    assert record.result is None
    assert record.error == error


# --- STEP 12.5: catalog/DB seed version parity (homogeneous 1.1) --------------


_HAIRSTYLE_CODES = (
    "textured_quiff",
    "classic_pompadour",
    "side_part",
    "brushed_up_undercut",
)

_GROOMING_CODES = (
    "structured_goatee",
    "classic_stubble",
    "full_beard",
    "goatee_with_mustache",
)


def _look_versions():
    Session = make_session()
    with Session() as session:
        return {
            row[0]: row[1]
            for row in session.execute(
                text("SELECT code, content_version FROM looks")
            ).all()
        }


def test_12_5_all_seeded_look_versions_match_catalog_version(db):
    """1. Every seeded look carries KNOWLEDGE_VERSION."""
    from app.data import catalog

    versions = _look_versions()
    assert len(versions) == 8
    assert set(versions.values()) == {catalog.KNOWLEDGE_VERSION}
    assert catalog.KNOWLEDGE_VERSION == "1.1"


def test_12_5_hairstyle_rows_are_1_1(db):
    """2. The four corrected hairstyle rows read 1.1."""
    versions = _look_versions()
    assert [versions[code] for code in _HAIRSTYLE_CODES] == ["1.1"] * 4


def test_12_5_grooming_rows_remain_1_1(db):
    """3. Grooming rows untouched at 1.1."""
    versions = _look_versions()
    assert [versions[code] for code in _GROOMING_CODES] == ["1.1"] * 4


def test_12_5_catalog_db_content_parity(db):
    """4. Code payloads are content-identical to app/data/catalog.py."""
    from app.data import catalog

    Session = make_session()
    with Session() as session:
        payloads = {
            row[0]: row[1]
            for row in session.execute(text("SELECT code, payload FROM looks")).all()
        }
    entries = {e["code"]: e for e in catalog.HAIRSTYLE_LOOKS + catalog.GROOMING_LOOKS}
    assert set(payloads) == set(entries)
    for code, entry in entries.items():
        payload = payloads[code]
        assert payload["description"] == entry["description"]
        assert payload["reasons"] == entry["reasons"]
        assert payload["scoreSeed"] == entry["scoreSeed"]


def test_12_5_migration_downgrade_upgrade_round_trip(db):
    """5. 0011 downgrade restores only hairstyle rows to 1.0; upgrade returns
    the homogeneous 1.1 state (established alembic pattern, same as the
    idempotency test above)."""
    config = _alembic_config()
    command.downgrade(config, "0010")
    versions = _look_versions()
    assert [versions[code] for code in _HAIRSTYLE_CODES] == ["1.0"] * 4
    assert [versions[code] for code in _GROOMING_CODES] == ["1.1"] * 4
    command.upgrade(config, "head")
    versions = _look_versions()
    assert set(versions.values()) == {"1.1"}
    assert len(versions) == 8
