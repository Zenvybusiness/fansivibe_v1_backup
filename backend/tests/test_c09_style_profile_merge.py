"""Tests for C-09 Style Profile Non-Empty Field Merge Semantics.

Verifies:
A. Existing non-empty fields survive incoming empty strings.
B. Incoming non-empty field replaces old value.
C. Existing unrelated JSONB keys survive.
D. source_run_id updates to the latest successful run.
E. Empty existing profile + populated incoming profile works.
F. All-empty incoming profile does not destroy existing attributes.
G. Existing C-09 readers still receive the same StyleProfile wire shape.
H. SQL emission uses PostgreSQL JSONB || concatenation with proper casting.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.api.routers.users import _completeness, _to_style_profile
from app.api.schemas.users import ProfileView, StyleProfile
from app.domain.ports.repositories import UserProfileRecord
from app.infrastructure.db.repositories import UserStateRepositorySQL


# --- Test doubles for SQL inspection ------------------------------------------

class _RecordingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []
        self.commits = 0

    def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        return None

    def commit(self) -> None:
        self.commits += 1


USER_A = uuid4()


# --- SQL Emission & Compilation Tests ------------------------------------------

def test_sql_emits_jsonb_merge_with_proper_operator():
    """H. Emits UPDATE ... SET style_profile = coalesce(style_profile, '{}'::jsonb) || :patch."""
    session = _RecordingSession()
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    repo.update_style_profile(
        user_id=USER_A,
        face_shape="round",
        skin_tone="",
        body_type="",
        style_type="",
        source_run_id="run-101",
    )

    assert session.commits == 1
    assert len(session.statements) == 1

    sql = str(session.statements[0].compile(dialect=postgresql.dialect()))
    assert "||" in sql
    assert "CAST" in sql and "JSONB" in sql
    assert "user_state" in sql
    assert "user_id" in sql
    assert "style_profile" in sql


def test_empty_strings_and_nulls_omitted_from_patch():
    """Only non-empty attributes are included in the JSONB patch parameter."""
    session = _RecordingSession()
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    repo.update_style_profile(
        user_id=USER_A,
        face_shape="oval",
        skin_tone="",
        body_type="   ",  # whitespace treated as empty
        style_type=None,
        source_run_id="run-new",
    )

    assert len(session.statements) == 1
    stmt = session.statements[0]
    compiled = stmt.compile(dialect=postgresql.dialect())

    # Find the patch parameter passed to JSONB cast
    params = compiled.params
    # At least one param must be the patch dict
    patch_params = [
        v for v in params.values()
        if isinstance(v, dict) and "source_run_id" in v
    ]
    assert len(patch_params) == 1
    patch = patch_params[0]

    assert patch["face_shape"] == "oval"
    assert patch["source_run_id"] == "run-new"
    assert "_provenance_face_shape" in patch
    assert patch["_provenance_face_shape"]["value"] == "oval"
    assert patch["_provenance_face_shape"]["source"] == "vision"
    assert patch["_provenance_face_shape"]["confirmed_by_user"] is False
    assert "skin_tone" not in patch
    assert "_provenance_skin_tone" not in patch
    assert "body_type" not in patch
    assert "_provenance_body_type" not in patch
    assert "style_type" not in patch
    assert "_provenance_style_type" not in patch


def test_all_empty_incoming_profile_does_not_execute_sql():
    """F. If all incoming attributes and source_run_id are empty/None, no SQL is emitted."""
    session = _RecordingSession()
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    repo.update_style_profile(
        user_id=USER_A,
        face_shape="",
        skin_tone="",
        body_type="",
        style_type="",
        source_run_id="",
    )

    assert len(session.statements) == 0
    assert session.commits == 0


# --- Merge Semantics Proofs (A - F) -------------------------------------------

def _apply_jsonb_merge(existing: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Mathematical equivalent of PostgreSQL `existing || patch` on JSONB."""
    return {**existing, **patch}


def _extract_patch(
    *,
    face_shape: str | None = None,
    skin_tone: str | None = None,
    body_type: str | None = None,
    style_type: str | None = None,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    """Helper verifying repository patch construction."""
    session = _RecordingSession()
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]
    repo.update_style_profile(
        user_id=USER_A,
        face_shape=face_shape,
        skin_tone=skin_tone,
        body_type=body_type,
        style_type=style_type,
        source_run_id=source_run_id,
    )
    if not session.statements:
        return {}
    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    for v in compiled.params.values():
        if isinstance(v, dict) and ("source_run_id" in v or "face_shape" in v):
            return v
    return {}


def test_a_existing_non_empty_fields_survive_incoming_empty_strings():
    """A. Existing non-empty fields survive incoming empty strings."""
    existing = {
        "face_shape": "oval",
        "skin_tone": "medium",
        "body_type": "pear",
        "style_type": "casual",
        "source_run_id": "old-run",
    }

    # Vision adapter provides face_shape="round", but empty strings for others
    patch = _extract_patch(
        face_shape="round",
        skin_tone="",
        body_type="",
        style_type="",
        source_run_id="new-run",
    )

    merged = _apply_jsonb_merge(existing, patch)

    assert merged["face_shape"] == "round"
    assert merged["skin_tone"] == "medium"  # SURVIVED
    assert merged["body_type"] == "pear"    # SURVIVED
    assert merged["style_type"] == "casual"  # SURVIVED
    assert merged["source_run_id"] == "new-run"


def test_b_incoming_non_empty_field_replaces_old_value():
    """B. Incoming non-empty field replaces the old value."""
    existing = {
        "face_shape": "oval",
        "skin_tone": "fair",
        "body_type": "rectangle",
        "style_type": "minimalist",
        "source_run_id": "run-1",
    }

    patch = _extract_patch(
        face_shape="square",
        skin_tone="medium",
        body_type=None,
        style_type="boho",
        source_run_id="run-2",
    )

    merged = _apply_jsonb_merge(existing, patch)

    assert merged["face_shape"] == "square"      # Replaced
    assert merged["skin_tone"] == "medium"       # Replaced
    assert merged["body_type"] == "rectangle"    # Preserved (None incoming)
    assert merged["style_type"] == "boho"        # Replaced
    assert merged["source_run_id"] == "run-2"    # Replaced


def test_c_existing_unrelated_jsonb_keys_survive():
    """C. Existing unrelated JSONB keys survive."""
    existing = {
        "face_shape": "oval",
        "skin_tone": "medium",
        "body_type": "pear",
        "style_type": "casual",
        "source_run_id": "old-run",
        "unrelated_attribute": "kept",
        "version_tag": 42,
        "metadata": {"source": "legacy_import"},
    }

    patch = _extract_patch(
        face_shape="heart",
        skin_tone="",
        body_type="",
        style_type="",
        source_run_id="run-new",
    )

    merged = _apply_jsonb_merge(existing, patch)

    assert merged["face_shape"] == "heart"
    assert merged["unrelated_attribute"] == "kept"
    assert merged["version_tag"] == 42
    assert merged["metadata"] == {"source": "legacy_import"}


def test_d_source_run_id_updates_to_latest_successful_run():
    """D. source_run_id updates to the latest successful run."""
    existing = {
        "face_shape": "oval",
        "skin_tone": "medium",
        "body_type": "pear",
        "style_type": "casual",
        "source_run_id": "old-run",
    }

    # Only source_run_id provided, all appearance attributes empty
    patch = _extract_patch(
        face_shape="",
        skin_tone="",
        body_type="",
        style_type="",
        source_run_id="latest-successful-run",
    )

    merged = _apply_jsonb_merge(existing, patch)

    assert merged["source_run_id"] == "latest-successful-run"
    assert merged["face_shape"] == "oval"
    assert merged["skin_tone"] == "medium"
    assert merged["body_type"] == "pear"
    assert merged["style_type"] == "casual"


def test_e_empty_existing_profile_plus_populated_incoming():
    """E. Empty existing profile + populated incoming profile works."""
    existing: dict[str, Any] = {}

    patch = _extract_patch(
        face_shape="oval",
        skin_tone="deep",
        body_type="hourglass",
        style_type="streetwear",
        source_run_id="run-first",
    )

    merged = _apply_jsonb_merge(existing, patch)

    assert merged["face_shape"] == "oval"
    assert merged["skin_tone"] == "deep"
    assert merged["body_type"] == "hourglass"
    assert merged["style_type"] == "streetwear"
    assert merged["source_run_id"] == "run-first"
    assert "_provenance_face_shape" in merged
    assert "_provenance_skin_tone" in merged
    assert "_provenance_body_type" in merged
    assert "_provenance_style_type" in merged


def test_f_all_empty_incoming_profile_does_not_destroy_existing_attributes():
    """F. All-empty incoming profile does not destroy existing attributes."""
    existing = {
        "face_shape": "diamond",
        "skin_tone": "olive",
        "body_type": "inverted_triangle",
        "style_type": "vintage",
        "source_run_id": "run-established",
    }

    # Case 1: All attributes empty, but run_id present
    patch1 = _extract_patch(
        face_shape="",
        skin_tone="",
        body_type="",
        style_type="",
        source_run_id="run-partial",
    )
    merged1 = _apply_jsonb_merge(existing, patch1)
    assert merged1["face_shape"] == "diamond"
    assert merged1["skin_tone"] == "olive"
    assert merged1["body_type"] == "inverted_triangle"
    assert merged1["style_type"] == "vintage"
    assert merged1["source_run_id"] == "run-partial"

    # Case 2: All attributes empty, run_id empty
    patch2 = _extract_patch(
        face_shape="",
        skin_tone="",
        body_type="",
        style_type="",
        source_run_id="",
    )
    merged2 = _apply_jsonb_merge(existing, patch2)
    assert merged2 == existing


# --- Reader Compatibility Tests (G) -------------------------------------------

def test_g_readers_receive_same_style_profile_wire_shape():
    """G. Existing C-09 readers still receive the exact same StyleProfile wire shape."""
    merged_profile = {
        "face_shape": "round",
        "skin_tone": "medium",
        "body_type": "pear",
        "style_type": "casual",
        "source_run_id": "run-xyz",
        "unrelated_key": "survived",  # should be ignored by wire mapping
    }

    # Reader 1: _to_style_profile
    wire = _to_style_profile(merged_profile)
    assert isinstance(wire, StyleProfile)
    assert wire.faceShape == "round"
    assert wire.skinTone == "medium"
    assert wire.bodyType == "pear"
    assert wire.styleType == "casual"
    assert wire.sourceRunId == "run-xyz"

    # Verify JSON serialization keys match camelCase contract §6.2
    wire_dict = wire.model_dump(by_alias=True)
    assert wire_dict == {
        "faceShape": "round",
        "skinTone": "medium",
        "bodyType": "pear",
        "styleType": "casual",
        "sourceRunId": "run-xyz",
    }

    # Reader 2: _completeness calculation
    assert _completeness(merged_profile) == 1.0

    # Partial completeness calculation
    partial = {"face_shape": "round", "source_run_id": "run-1"}
    assert _completeness(partial) == 0.25

    # Reader 3: Full ProfileView shape
    record = UserProfileRecord(
        user_id=USER_A,
        display_name="User A",
        style_profile=merged_profile,
        preferences={"preferred_occasions": ["weekend"]},
        settings={},
        flags={},
        version=1,
    )
    from app.api.routers.users import _record_to_schema
    view = _record_to_schema(record)
    assert isinstance(view, ProfileView)
    assert view.styleProfile.faceShape == "round"
    assert view.styleProfile.skinTone == "medium"
    assert view.memorySummary is not None
    assert view.memorySummary["appearanceVerified"] is True
    assert view.memorySummary["appearanceConfidence"] == 1.0


# --- PostgreSQL Live Integration (Skipped when PG not configured) -------------

def test_postgresql_live_merge_roundtrip(migrated_db: str) -> None:
    """PostgreSQL live round-trip: JSONB || correctly merges non-empty attributes into DB."""
    from tests.conftest import make_session
    from app.infrastructure.db.models import Users, UserState
    from sqlalchemy import select

    Session = make_session(migrated_db)
    with Session() as session:
        user = Users(auth_provider="dev", auth_subject=f"c09-user-{uuid4()}", display_name="C09 User")
        session.add(user)
        session.flush()

        initial_profile = {
            "face_shape": "oval",
            "skin_tone": "medium",
            "body_type": "pear",
            "style_type": "casual",
            "source_run_id": "run-initial",
            "custom_key": "preserved",
        }
        session.add(UserState(user_id=user.id, style_profile=initial_profile))
        session.commit()

        repo = UserStateRepositorySQL(session)
        # Update with new face_shape, new source_run_id, empty strings for others
        repo.update_style_profile(
            user_id=user.id,
            face_shape="round",
            skin_tone="",
            body_type="",
            style_type="",
            source_run_id="run-merged",
        )

        row = session.execute(
            select(UserState.style_profile).where(UserState.user_id == user.id)
        ).scalar_one()

        assert row["face_shape"] == "round"
        assert row["skin_tone"] == "medium"
        assert row["body_type"] == "pear"
        assert row["style_type"] == "casual"
        assert row["source_run_id"] == "run-merged"
        assert row["custom_key"] == "preserved"


# --- CAS Optimistic Concurrency and Provenance Tests ---------------------------

class _MockCASDatabaseSession:
    """In-memory database session executing real CAS versioning and JSONB merge."""

    def __init__(self, initial_profile: dict[str, Any] | None = None, initial_version: int = 0) -> None:
        self.user_state: dict[str, Any] = {
            "style_profile": dict(initial_profile or {}),
            "version": initial_version,
        }
        self.statements: list[Any] = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, stmt: Any) -> Any:
        self.statements.append(stmt)
        # Handle select
        if hasattr(stmt, "is_select") and stmt.is_select:
            profile = dict(self.user_state["style_profile"])
            version = self.user_state["version"]

            class _SelectResult:
                def __init__(self, row):
                    self._row = row

                def one_or_none(self):
                    return self._row

                def scalar_one_or_none(self):
                    return self._row[0] if self._row else None

            cols = [str(c) for c in getattr(stmt, "selected_columns", [])]
            if any("version" in c for c in cols):
                return _SelectResult((version, profile))
            return _SelectResult((profile,))

        # Handle update
        if hasattr(stmt, "is_update") and stmt.is_update:
            class _ExecResult:
                def __init__(self, count):
                    self.rowcount = count

            # Extract expected_version from WHERE criteria
            expected_version_in_where = None
            if hasattr(stmt, "_where_criteria"):
                for crit in stmt._where_criteria:
                    if hasattr(crit, "left") and getattr(crit.left, "name", "") == "version":
                        expected_version_in_where = crit.right.value
                        break

            if expected_version_in_where is not None and self.user_state["version"] != expected_version_in_where:
                return _ExecResult(0)

            # Apply JSONB merge from params
            compiled = stmt.compile(dialect=postgresql.dialect())
            params = compiled.params
            patch_param = None
            for v in params.values():
                if isinstance(v, dict) and ("source_run_id" in v or any(k.startswith("_provenance") for k in v)):
                    patch_param = v
                    break

            if patch_param:
                self.user_state["style_profile"].update(patch_param)
            self.user_state["version"] += 1

            return _ExecResult(1)

        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def test_sql_emits_cas_expected_version_and_version_increment():
    """CAS update emits WHERE version = :version and SET version = user_state.version + 1."""
    session = _RecordingSession()
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    repo.update_style_profile(
        user_id=USER_A,
        face_shape="round",
        expected_version=2,
    )

    assert len(session.statements) == 1
    stmt = session.statements[0]
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "user_state.version = " in sql
    assert "user_state.version +" in sql
    assert "style_profile" in sql


def test_cas_version_increments_on_successful_update():
    """Version increments atomically on successful profile update."""
    session = _MockCASDatabaseSession(initial_profile={"face_shape": "oval"}, initial_version=0)
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    success = repo.update_style_profile(
        user_id=USER_A,
        face_shape="round",
        expected_version=0,
    )
    assert success is True
    assert session.user_state["version"] == 1
    assert session.user_state["style_profile"]["face_shape"] == "round"
    assert session.commits == 1


def test_cas_version_mismatch_returns_conflict_false():
    """Stale version check fails with False without modifying data."""
    session = _MockCASDatabaseSession(initial_profile={"face_shape": "oval"}, initial_version=1)
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    # Expected version 0, but DB is at version 1
    success = repo.update_style_profile(
        user_id=USER_A,
        face_shape="square",
        expected_version=0,
        max_retries=0,
    )
    assert success is False
    assert session.user_state["version"] == 1  # Untouched
    assert session.user_state["style_profile"]["face_shape"] == "oval"  # Untouched


def test_cas_two_concurrent_updates_different_attributes():
    """Two concurrent updates against the same base version: first succeeds, second conflicts."""
    session = _MockCASDatabaseSession(
        initial_profile={"face_shape": "oval", "skin_tone": "fair"},
        initial_version=5,
    )
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    # Thread 1 updates face_shape expecting version 5
    t1_success = repo.update_style_profile(
        user_id=USER_A,
        face_shape="round",
        expected_version=5,
    )
    assert t1_success is True
    assert session.user_state["version"] == 6

    # Thread 2 (concurrent, read stale version 5) updates skin_tone
    t2_success = repo.update_style_profile(
        user_id=USER_A,
        skin_tone="medium",
        expected_version=5,
        max_retries=0,
    )
    assert t2_success is False
    assert session.user_state["version"] == 6
    # Thread 1's write is safe, Thread 2 was rejected
    assert session.user_state["style_profile"]["face_shape"] == "round"
    assert session.user_state["style_profile"]["skin_tone"] == "fair"


def test_cas_bounded_retry_preserves_both_concurrent_updates():
    """With bounded retry, second concurrent update reloads fresh state and reapplies only intended change."""
    session = _MockCASDatabaseSession(
        initial_profile={"face_shape": "oval", "skin_tone": "fair"},
        initial_version=1,
    )
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    # Update 1 updates face_shape
    assert repo.update_style_profile(user_id=USER_A, face_shape="round", expected_version=1) is True
    assert session.user_state["version"] == 2

    # Update 2 started with stale expected_version=1, but has max_retries=2
    success = repo.update_style_profile(
        user_id=USER_A,
        skin_tone="deep",
        expected_version=1,
        max_retries=2,
    )
    assert success is True
    assert session.user_state["version"] == 3
    # BOTH attributes are preserved!
    assert session.user_state["style_profile"]["face_shape"] == "round"
    assert session.user_state["style_profile"]["skin_tone"] == "deep"


def test_preservation_of_unrelated_profile_fields_and_unrelated_provenance():
    """Unrelated scalar attributes and unrelated provenance keys survive partial updates."""
    initial = {
        "face_shape": "oval",
        "_provenance_face_shape": {
            "value": "oval",
            "source": "user",
            "source_run_id": "run-0",
            "confidence": 1.0,
            "confirmed_by_user": True,
        },
        "unrelated_custom_flag": "preserved",
    }
    session = _MockCASDatabaseSession(initial_profile=initial, initial_version=1)
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    success = repo.update_style_profile(
        user_id=USER_A,
        body_type="athletic",
        source_run_id="run-1",
    )
    assert success is True
    profile = session.user_state["style_profile"]

    # Unrelated attributes and provenance survived
    assert profile["face_shape"] == "oval"
    assert profile["_provenance_face_shape"]["confirmed_by_user"] is True
    assert profile["unrelated_custom_flag"] == "preserved"
    # New attribute and its provenance added
    assert profile["body_type"] == "athletic"
    assert profile["_provenance_body_type"]["value"] == "athletic"
    assert profile["_provenance_body_type"]["source"] == "vision"


def test_confirmed_user_value_protected_from_lower_confidence_ai():
    """Confirmed user value cannot be overwritten by unconfirmed AI vision observation."""
    initial = {
        "face_shape": "oval",
        "_provenance_face_shape": {
            "value": "oval",
            "source": "user",
            "source_run_id": None,
            "confidence": 1.0,
            "confirmed_by_user": True,
            "confirmed_at": "2026-10-31T10:00:00Z",
        },
        "skin_tone": "medium",
    }
    session = _MockCASDatabaseSession(initial_profile=initial, initial_version=1)
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    # AI vision arrives with face_shape="round" and skin_tone="deep"
    success = repo.update_style_profile(
        user_id=USER_A,
        face_shape="round",
        skin_tone="deep",
        confirmed_by_user=False,
        confidence=0.82,
        source_run_id="ai-run-99",
    )
    assert success is True
    profile = session.user_state["style_profile"]

    # face_shape was user-confirmed -> protected as "oval"!
    assert profile["face_shape"] == "oval"
    assert profile["_provenance_face_shape"]["confirmed_by_user"] is True
    # skin_tone was unconfirmed -> successfully updated to "deep"
    assert profile["skin_tone"] == "deep"
    assert profile["_provenance_skin_tone"]["value"] == "deep"


def test_user_confirmed_value_overwrites_ai_observation():
    """User confirmed edit overwrites previous AI observation and sets confirmed_by_user=True."""
    initial = {
        "face_shape": "round",
        "_provenance_face_shape": {
            "value": "round",
            "source": "vision",
            "confidence": 0.85,
            "confirmed_by_user": False,
        },
    }
    session = _MockCASDatabaseSession(initial_profile=initial, initial_version=1)
    repo = UserStateRepositorySQL(session)  # type: ignore[arg-type]

    # User explicitly updates face_shape to square
    success = repo.update_style_profile(
        user_id=USER_A,
        face_shape="square",
        confirmed_by_user=True,
    )
    assert success is True
    profile = session.user_state["style_profile"]

    assert profile["face_shape"] == "square"
    assert profile["_provenance_face_shape"]["value"] == "square"
    assert profile["_provenance_face_shape"]["confirmed_by_user"] is True
    assert profile["_provenance_face_shape"]["source"] == "user"
    assert profile["_provenance_face_shape"]["confirmed_at"] is not None


def test_get_attribute_provenance_explicit_and_legacy_compatibility():
    """get_attribute_provenance returns explicit metadata when present and synthesizes legacy when absent."""
    repo = UserStateRepositorySQL(None)  # type: ignore[arg-type]

    profile = {
        "face_shape": "oval",
        "_provenance_face_shape": {
            "value": "oval",
            "source": "vision",
            "source_run_id": "run-42",
            "confidence": 0.94,
            "confirmed_by_user": True,
        },
        "skin_tone": "warm_medium",  # Legacy record with no _provenance_skin_tone
        "source_run_id": "legacy-run-1",
    }

    # Explicit provenance
    prov_face = repo.get_attribute_provenance(profile, "face_shape")
    assert prov_face is not None
    assert prov_face["value"] == "oval"
    assert prov_face["source"] == "vision"
    assert prov_face["confidence"] == 0.94
    assert prov_face["confirmed_by_user"] is True

    # Legacy synthesized provenance
    prov_skin = repo.get_attribute_provenance(profile, "skin_tone")
    assert prov_skin is not None
    assert prov_skin["value"] == "warm_medium"
    assert prov_skin["source"] == "legacy"
    assert prov_skin["source_run_id"] == "legacy-run-1"
    assert prov_skin["confidence"] == 1.0
    assert prov_skin["confirmed_by_user"] is False

    # Non-existent attribute
    assert repo.get_attribute_provenance(profile, "body_type") is None
    assert repo.get_attribute_provenance({}, "face_shape") is None
