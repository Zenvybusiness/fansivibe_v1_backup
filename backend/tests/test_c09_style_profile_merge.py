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

    assert patch == {
        "face_shape": "oval",
        "source_run_id": "run-new",
    }
    assert "skin_tone" not in patch
    assert "body_type" not in patch
    assert "style_type" not in patch


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

    assert merged == {
        "face_shape": "oval",
        "skin_tone": "deep",
        "body_type": "hourglass",
        "style_type": "streetwear",
        "source_run_id": "run-first",
    }


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
