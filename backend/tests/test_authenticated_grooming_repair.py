"""Tests for Authenticated Grooming Analysis & Profile Repair (Stage 2 P0-2).

Covers:
1. Valid manual input without face shape.
2. Valid input with existing face-shape profile.
3. Missing required manual inputs raises 422 INSUFFICIENT_USER_DATA.
4. Unknown face shape is not fabricated (never defaults to oval).
5. Confirmed profile values are protected from overwrite.
6. Canonical grooming recommendation delegation remains active.
7. Guest appearance persistence remains prohibited (D10 Option A).
8. API endpoint /v1/analysis/grooming accepts manual grooming payloads.
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.errors import ApiError
from app.application.analysis import CreateGroomingRun, EphemeralGroomingAnalysis
from app.domain.ports.repositories import AnalysisRunRecord
from app.domain.services.grooming_rules import recommend_grooming
from app.domain.value_objects import AppearanceProfile, GroomingResult, HairstylePreferences
from app.infrastructure.external.knowledge import CatalogKnowledgeSource
from app.main import app
from app.api.deps import get_current_user_id
from app.infrastructure.db.session import get_db

USER = uuid4()
KNOWLEDGE = CatalogKnowledgeSource()


class FakeRuns:
    def __init__(self) -> None:
        self.rows: dict[UUID, dict[str, Any]] = {}

    def create(
        self,
        *,
        user_id: UUID,
        run_type: str,
        engine_version: str = "rules-v1",
        input_media: Optional[dict[str, Any]] = None,
        knowledge_version: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> UUID:
        from datetime import datetime, timezone
        run_id = uuid4()
        self.rows[run_id] = {
            "id": run_id,
            "user_id": user_id,
            "run_type": run_type,
            "status": "pending",
            "engine_version": engine_version,
            "knowledge_version": knowledge_version,
            "input_media": input_media,
            "result": None,
            "error": None,
            "idempotency_key": idempotency_key,
            "created_at": datetime.now(timezone.utc),
            "completed_at": None,
        }
        return run_id

    def complete(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
        status: str = "completed",
        result: Optional[dict[str, Any]] = None,
    ) -> bool:
        row = self.rows.get(run_id)
        if not row or row["user_id"] != user_id:
            return False
        row["status"] = status
        row["result"] = result
        return True

    def fail(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
        error: dict[str, Any],
    ) -> bool:
        row = self.rows.get(run_id)
        if not row or row["user_id"] != user_id:
            return False
        row["status"] = "failed"
        row["error"] = error
        return True

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional[AnalysisRunRecord]:
        for r in self.rows.values():
            if r["user_id"] == user_id and r["idempotency_key"] == idempotency_key:
                return AnalysisRunRecord(**{k: v for k, v in r.items() if k != "user_id"})
        return None

    def get_for_user(
        self, *, user_id: UUID, run_id: UUID
    ) -> Optional[AnalysisRunRecord]:
        r = self.rows.get(run_id)
        if r and r["user_id"] == user_id:
            return AnalysisRunRecord(**{k: v for k, v in r.items() if k != "user_id"})
        return None


class FakeUserState:
    def __init__(self, style_profile: Optional[dict[str, Any]] = None) -> None:
        self.profile = dict(style_profile or {})

    def get_style_profile(self, *, user_id: UUID) -> Optional[dict[str, Any]]:
        return dict(self.profile)

    def update_style_profile(
        self, *, user_id: UUID, updates: dict[str, Any], expected_version: Optional[int] = None
    ) -> bool:
        self.profile.update(updates)
        return True


def test_1_valid_manual_input_without_face_shape():
    """Authenticated user without face scan receives recommendations from manual inputs."""
    runs = FakeRuns()
    user_state = FakeUserState({})  # No face scan in style_profile

    use_case = CreateGroomingRun(
        runs=runs,
        user_state=user_state,
        knowledge=KNOWLEDGE,
    )
    run_id = use_case(
        user_id=USER,
        manual_inputs={"beard_style": "full_beard"},
    )
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None

    # Face shape remains empty string (unmeasured), not fabricated
    assert record.result["appearance"]["faceShape"] == ""
    assert record.result["needs_more_data"] is True

    # Recommendations include top and alternatives
    top = record.result["recommendations"]["top"]
    assert top is not None
    assert top["matchScore"] > 0.0

    # User's manual preference 'full_beard' was grounded and boosted by +0.03 (0.75 seed + 0.03 = 0.78)
    all_recs = [top] + record.result["recommendations"]["alternatives"]
    full_beard_rec = next(r for r in all_recs if r["id"] == "full_beard")
    assert full_beard_rec["matchScore"] == 0.78


def test_2_valid_input_with_existing_face_shape_profile():
    """Authenticated user with existing face scan preserves face shape and uses manual inputs."""
    runs = FakeRuns()
    user_state = FakeUserState({"face_shape": "Square", "skin_tone": "Warm Light"})

    use_case = CreateGroomingRun(
        runs=runs,
        user_state=user_state,
        knowledge=KNOWLEDGE,
    )
    run_id = use_case(
        user_id=USER,
        manual_inputs={"beard_style": "classic_stubble"},
    )
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None
    assert record.result["appearance"]["faceShape"] == "Square"
    assert record.result["appearance"]["skinTone"] == "Warm Light"


def test_3_missing_required_manual_inputs_raises_422():
    """When no profile exists and no manual inputs are provided, fails with 422."""
    runs = FakeRuns()
    user_state = FakeUserState({})

    use_case = CreateGroomingRun(
        runs=runs,
        user_state=user_state,
        knowledge=KNOWLEDGE,
    )
    with pytest.raises(ApiError) as excinfo:
        use_case(user_id=USER, manual_inputs={})

    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "INSUFFICIENT_USER_DATA"
    assert excinfo.value.details["missing"] == "face"


def test_4_unknown_face_shape_is_not_fabricated():
    """An unknown face shape never defaults to oval or any other guessed shape."""
    runs = FakeRuns()
    user_state = FakeUserState({})

    use_case = CreateGroomingRun(
        runs=runs,
        user_state=user_state,
        knowledge=KNOWLEDGE,
    )
    run_id = use_case(
        user_id=USER,
        manual_inputs={"beard_style": "stubble", "beard_density": "medium"},
    )
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.result["appearance"]["faceShape"] == ""
    assert record.result["needs_more_data"] is True


def test_5_confirmed_profile_values_are_protected():
    """Confirmed profile attributes take precedence and are never overwritten by manual inputs."""
    runs = FakeRuns()
    initial_profile = {"face_shape": "Round", "skin_tone": "Deep"}
    user_state = FakeUserState(initial_profile)

    use_case = CreateGroomingRun(
        runs=runs,
        user_state=user_state,
        knowledge=KNOWLEDGE,
    )
    run_id = use_case(
        user_id=USER,
        manual_inputs={"face_shape": "Square", "skin_tone": "Fair", "beard_style": "stubble"},
    )
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    # Confirmed server face shape wins over transient client input
    assert record.result["appearance"]["faceShape"] == "Round"
    assert record.result["appearance"]["skinTone"] == "Deep"

    # User state in repository remains untouched (zero persistence from grooming run)
    assert user_state.get_style_profile(user_id=USER) == initial_profile


def test_6_canonical_grooming_recommendation_delegation_active(monkeypatch):
    """Canonical grooming_rules.recommend_grooming remains the single recommendation authority."""
    runs = FakeRuns()
    user_state = FakeUserState({"face_shape": "Oval"})

    called = []
    import app.application.analysis as analysis_mod

    orig_recommend = analysis_mod.recommend_grooming

    def spy_recommend(knowledge, appearance, preferences=None):
        called.append((appearance, preferences))
        return orig_recommend(knowledge, appearance, preferences)

    monkeypatch.setattr(analysis_mod, "recommend_grooming", spy_recommend)

    use_case = CreateGroomingRun(
        runs=runs,
        user_state=user_state,
        knowledge=KNOWLEDGE,
    )
    use_case(user_id=USER, manual_inputs={"beard_style": "goatee"})

    assert len(called) == 1
    app_arg, pref_arg = called[0]
    assert app_arg.faceShape == "Oval"
    assert "structured_goatee" in pref_arg.preferredLookIds


def test_7_guest_appearance_persistence_remains_prohibited():
    """Guest ephemeral analysis executes statelessly with zero database writes (D10 Option A)."""
    use_case = EphemeralGroomingAnalysis(knowledge=KNOWLEDGE)
    result = use_case(
        face_shape="square",
        skin_tone="Warm Medium",
    )
    assert "appearance" in result
    assert result["appearance"]["faceShape"] == "square"
    assert "recommendations" in result
    assert result["recommendations"]["top"]["id"] in [
        "structured_goatee",
        "classic_stubble",
        "full_beard",
        "goatee_with_mustache",
    ]


def test_8_api_endpoint_accepts_manual_grooming_payload(monkeypatch):
    """FastAPI endpoint /v1/analysis/grooming accepts JSON payload and forwards to use case."""
    router_user = uuid4()
    db_session = object()
    run_id = uuid4()
    captured = {}

    import app.api.routers.analysis as analysis_router

    class SpyCreateGroomingRun:
        def __init__(self, **kwargs) -> None:
            captured["kwargs"] = kwargs

        def __call__(self, *, user_id, **kwargs):
            captured["user_id"] = user_id
            captured.update(kwargs)
            return run_id

    monkeypatch.setattr(analysis_router, "CreateGroomingRun", SpyCreateGroomingRun)

    old_db = app.dependency_overrides.get(get_db)
    old_user = app.dependency_overrides.get(get_current_user_id)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user_id] = lambda: router_user
    try:
        client = TestClient(app)
        resp = client.post(
            "/v1/analysis/grooming",
            json={
                "face_shape": "diamond",
                "beard_style": "stubble",
                "beard_density": "medium",
                "beard_color": "dark_brown",
            },
        )
        assert resp.status_code == 202
        assert resp.json()["run_id"] == str(run_id)
        assert captured["user_id"] == router_user
        inputs = captured["manual_inputs"]
        assert inputs.resolved_face_shape == "diamond"
        assert inputs.resolved_beard_style == "stubble"
        assert inputs.resolved_beard_density == "medium"
        assert inputs.resolved_beard_color == "dark_brown"
    finally:
        if old_db is not None:
            app.dependency_overrides[get_db] = old_db
        else:
            app.dependency_overrides.pop(get_db, None)
        if old_user is not None:
            app.dependency_overrides[get_current_user_id] = old_user
        else:
            app.dependency_overrides.pop(get_current_user_id, None)
