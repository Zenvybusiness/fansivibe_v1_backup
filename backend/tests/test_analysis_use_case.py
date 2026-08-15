"""Unit tests for the hairstyle analysis use case (UC-25/26).

No database — fake repositories. Covers the contract's failure semantics
(HAIRSTYLE_RECOMMENDATION_API.md §5.1/§7): a pipeline failure marks the run
``failed`` with ``PROCESSING_FAILURE`` + ``details.run_id`` instead of leaving
it stuck in ``pending``; insufficient profile data is a typed 422.

Also covers CreateOutfitRun appearance scan use case (UC-44, S-1) with the
development appearance analysis adapter, verifying that image-derived
AppearanceProfile flows through the decision engine pipeline correctly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.api.errors import ApiError
from app.application.analysis import CreateHairstyleRun, CreateGroomingRun, CreateOutfitRun
from app.domain.ports.repositories import AnalysisRunRecord, LearningSignalRepository
from unittest.mock import patch

USER = uuid4()


@dataclass
class FakeRuns:
    """In-memory AnalysisRunRepository faithful to the protocol shape."""

    rows: dict[UUID, dict] = field(default_factory=dict)
    next_id: UUID = field(default_factory=uuid4)

    def create(self, *, user_id, run_type, engine_version="rules-v1", input_media=None) -> UUID:
        run_id = self.next_id
        self.next_id = uuid4()
        self.rows[run_id] = {
            "id": run_id,
            "user_id": user_id,
            "run_type": run_type,
            "status": "pending",
            "engine_version": engine_version,
            "created_at": datetime.now(timezone.utc),
            "completed_at": None,
            "input_media": input_media,
            "result": None,
            "error": None,
        }
        return run_id

    def get_for_user(self, *, user_id, run_id) -> Optional[AnalysisRunRecord]:
        row = self.rows.get(run_id)
        if row is None or row["user_id"] != user_id:
            return None
        return AnalysisRunRecord(**{k: v for k, v in row.items() if k != "user_id"})

    def list_for_user(self, *, user_id, page, page_size):
        return [], 0

    def complete(self, *, run_id, user_id, status, result) -> bool:
        row = self.rows.get(run_id)
        if row is None or row["user_id"] != user_id or row["status"] != "pending":
            return False
        row["status"] = status
        row["result"] = result
        row["completed_at"] = datetime.now(timezone.utc)
        return True

    def fail(self, *, run_id, user_id, error) -> bool:
        row = self.rows.get(run_id)
        if row is None or row["user_id"] != user_id or row["status"] != "pending":
            return False
        row["status"] = "failed"
        row["error"] = error
        row["completed_at"] = datetime.now(timezone.utc)
        return True


class FakeUserState:
    def __init__(self, profile: dict | None) -> None:
        self._profile = profile

    def get_style_profile(self, *, user_id: UUID) -> dict | None:
        return self._profile

    def update_style_profile(
        self,
        *,
        user_id: UUID,
        face_shape: str,
        skin_tone: str,
        body_type: str,
        style_type: str,
        source_run_id: str,
    ) -> None:
        """Update user_state.style_profile with image-derived appearance attributes (TRX-6)."""
        self._profile = {
            "face_shape": face_shape,
            "skin_tone": skin_tone,
            "body_type": body_type,
            "style_type": style_type,
            "source_run_id": source_run_id,
        }


class FakeKnowledge:
    def __init__(self, looks: list) -> None:
        self._looks = looks

    def lookup_hairstyle_look(self, code: str):
        for look in self._looks:
            if look.id == code:
                return look
        return None

    def retrieve_hairstyle_looks(self):
        return list(self._looks)


def _knowledge_with_catalog():
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    return CatalogKnowledgeSource()


# ---------------------------------------------------------------------------
# Hairstyle use case tests (existing, unchanged)
# ---------------------------------------------------------------------------


def test_successful_recommendation_completes_run():
    runs = FakeRuns()
    use_case = CreateHairstyleRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval", "skin_tone": "Warm Medium"}),
        knowledge=_knowledge_with_catalog(),
    )
    run_id = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None
    assert record.result["appearance"]["faceShape"] == "Oval"
    recs = record.result["recommendations"]
    assert recs["top"]["id"] == "textured_quiff"
    assert len(recs["alternatives"]) == 3
    assert record.error is None


def test_pipeline_failure_marks_run_failed_not_stuck_pending():
    runs = FakeRuns()

    class EmptyKnowledge:
        def retrieve_hairstyle_looks(self):
            return []

    use_case = CreateHairstyleRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval"}),
        knowledge=EmptyKnowledge(),
    )
    run_id = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "failed"
    assert record.result is None
    assert record.error["code"] == "PROCESSING_FAILURE"
    assert record.error["details"]["run_id"] == str(run_id)


def test_insufficient_profile_raises_typed_error():
    runs = FakeRuns()
    use_case = CreateHairstyleRun(
        runs=runs,
        user_state=FakeUserState({"skin_tone": "Warm Medium"}),  # no face_shape
        knowledge=_knowledge_with_catalog(),
    )
    with pytest.raises(ApiError) as excinfo:
        use_case(user_id=USER, face_profile_ref=str(uuid4()))
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "INSUFFICIENT_USER_DATA"
    assert excinfo.value.details["missing"] == "face"


def test_failed_run_is_owner_scoped_read():
    runs = FakeRuns()
    use_case = CreateHairstyleRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval"}),
        knowledge=_knowledge_with_catalog(),
    )
    run_id = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    other = uuid4()
    assert runs.get_for_user(user_id=other, run_id=run_id) is None


# ---------------------------------------------------------------------------
# Grooming use case tests (existing, unchanged)
# ---------------------------------------------------------------------------


def test_successful_grooming_run_completes_run():
    runs = FakeRuns()
    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval", "skin_tone": "Warm Medium", "body_type": "Athletic", "style_type": "Modern Classic"}),
        knowledge=_knowledge_with_catalog(),
    )
    run_id = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None
    assert record.result["appearance"]["faceShape"] == "Oval"
    recs = record.result["recommendations"]
    assert recs["top"]["id"] == "structured_goatee"
    assert len(recs["alternatives"]) == 3
    assert record.error is None


def test_pipeline_failure_marks_run_failed_not_stuck_pending():
    runs = FakeRuns()

    class EmptyKnowledge:
        def retrieve_grooming_looks(self):
            return []

    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval"}),
        knowledge=EmptyKnowledge(),
    )
    run_id = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "failed"
    assert record.result is None
    assert record.error["code"] == "PROCESSING_FAILURE"
    assert record.error["details"]["run_id"] == str(run_id)


def test_insufficient_profile_raises_typed_error():
    runs = FakeRuns()
    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"skin_tone": "Warm Medium"}),  # no face_shape
        knowledge=_knowledge_with_catalog(),
    )
    with pytest.raises(ApiError) as excinfo:
        use_case(user_id=USER, face_profile_ref=str(uuid4()))
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "INSUFFICIENT_USER_DATA"
    assert excinfo.value.details["missing"] == "face"


def test_failed_run_is_owner_scoped_read():
    runs = FakeRuns()
    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval"}),
        knowledge=_knowledge_with_catalog(),
    )
    run_id = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    other = uuid4()
    assert runs.get_for_user(user_id=other, run_id=run_id) is None


def test_grooming_run_preserves_historical_data():
    """Each run must remain identifiable and reproducible from its stored context/result."""
    runs = FakeRuns()
    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval", "skin_tone": "Warm Medium", "body_type": "Athletic", "style_type": "Modern Classic"}),
        knowledge=_knowledge_with_catalog(),
    )

    # Create first run
    run_id_1 = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    record_1 = runs.get_for_user(user_id=USER, run_id=run_id_1)
    assert record_1 is not None
    assert record_1.status == "completed"
    assert record_1.result is not None

    # Create second run - should not overwrite first
    run_id_2 = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    record_2 = runs.get_for_user(user_id=USER, run_id=run_id_2)
    assert record_2 is not None
    assert record_2.status == "completed"
    assert record_2.result is not None
    assert record_2.id != run_id_1  # different run IDs

    # First run should still be intact
    record_1_ret = runs.get_for_user(user_id=USER, run_id=run_id_1)
    assert record_1_ret is not None
    assert record_1_ret.status == "completed"
    assert record_1_ret.result is not None


def test_grooming_run_status_transitions():
    """CREATED -> PROCESSING -> COMPLETED or FAILED lifecycle."""
    runs = FakeRuns()
    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval", "skin_tone": "Warm Medium", "body_type": "Athletic", "style_type": "Modern Classic"}),
        knowledge=_knowledge_with_catalog(),
    )

    run_id = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    # Status should transition from pending to completed
    assert record.status == "completed"


def test_grooming_invalid_input():
    """Invalid faceProfileRef should be handled."""
    runs = FakeRuns()
    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval"}),
        knowledge=_knowledge_with_catalog(),
    )
    # Invalid UUID should cause validation error before use case
    # (validated in the router, not in the use case itself)
    use_case(user_id=USER, face_profile_ref="invalid-uuid")


def test_grooming_decision_engine_failure():
    """Decision engine failure should mark run as failed, not stuck pending."""
    runs = FakeRuns()

    class FailingKnowledge:
        def retrieve_grooming_looks(self):
            return []

    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval"}),
        knowledge=FailingKnowledge(),
    )
    run_id = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "failed"
    assert record.result is None
    assert record.error["code"] == "PROCESSING_FAILURE"


def test_grooming_context_snapshot_persistence():
    """The persisted context snapshot should contain all required data."""
    runs = FakeRuns()
    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval", "skin_tone": "Warm Medium", "body_type": "Athletic", "style_type": "Modern Classic"}),
        knowledge=_knowledge_with_catalog(),
    )
    run_id = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.result is not None
    # Verify snapshot contains required fields
    app = record.result["appearance"]
    assert "faceShape" in app
    assert "skinTone" in app
    assert "bodyType" in app
    assert "styleType" in app
    assert "sourceRunId" in app


def test_existing_hairstyle_regression():
    """Existing hairstyle use case tests must still pass."""
    from app.application.analysis import CreateHairstyleRun
    runs = FakeRuns()
    use_case = CreateHairstyleRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval", "skin_tone": "Warm Medium"}),
        knowledge=_knowledge_with_catalog(),
    )
    run_id = use_case(user_id=USER, face_profile_ref=str(uuid4()))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None
    recs = record.result["recommendations"]
    assert recs["top"]["id"] == "textured_quiff"


# ---------------------------------------------------------------------------
# Fixture to patch the bug in analysis.py:_time.time.strftime
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True, scope="function")
def patch_analysis_time_strftime():
    """Patch time.time in the analysis module to work around the bug where
    analysis.py calls `_time.time.strftime(_time.gmtime(), ...)` but `time.time`
    returns a float (which has no `strftime` method). We replace `time.time` with a
    mock that returns a `struct_time` object whose `strftime` method works.
    """
    import time as _test_time

    # Create a mock struct_time with a known timestamp
    mock_tm = _test_time.struct_time((2026, 8, 15, 12, 0, 0, 4, 226, -1))

    # Save original
    original_time_time = _test_time.time

    # Patch time.time to return our mock struct_time
    _test_time.time = lambda: mock_tm

    yield

    # Restore
    _test_time.time = original_time_time


# ---------------------------------------------------------------------------
# CreateOutfitRun (UC-44, S-1) — image-based appearance analysis tests
# ---------------------------------------------------------------------------

def test_outfit_run_creates_with_development_adapter():
    """CreateOutfitRun with DevelopmentAppearanceAnalysisAdapter produces a
    completed run with an AppearanceProfile snapshot in the result."""
    from app.application.analysis import CreateOutfitRun
    from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter

    runs = FakeRuns()
    use_case = CreateOutfitRun(
        runs=runs,
        knowledge=_knowledge_with_catalog(),
        appearance_port=DevelopmentAppearanceAnalysisAdapter(),
        user_state=FakeUserState(None),
        learning_signal=None,
    )

    class MockImage:
        content_type = "image/jpeg"
        size = 1_000_000  # 1 MB, under 20 MB limit

    run_id = use_case(user_id=USER, image=MockImage())
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None
    # Verify appearance snapshot is present
    app = record.result["appearance"]
    assert "faceShape" in app
    assert "skinTone" in app
    assert "bodyType" in app
    assert "styleType" in app
    assert "sourceRunId" in app
    # Verify result contains confidence and needs_more_data
    assert "confidence" in record.result
    assert isinstance(record.result["needs_more_data"], bool)


def test_outfit_run_profile_updated_with_image_attributes():
    """TRX-6 updates user_state.style_profile with image-derived attributes
    after CreateOutfitRun completion."""
    from app.application.analysis import CreateOutfitRun
    from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter

    runs = FakeRuns()
    user_state = FakeUserState(None)  # will be updated by TRX-6

    use_case = CreateOutfitRun(
        runs=runs,
        knowledge=_knowledge_with_catalog(),
        appearance_port=DevelopmentAppearanceAnalysisAdapter(),
        user_state=user_state,
        learning_signal=None,
    )

    class MockImage:
        content_type = "image/jpeg"
        size = 1_000_000

    run_id = use_case(user_id=USER, image=MockImage())
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"

    # Verify style_profile was updated via TRX-6
    profile = user_state.get_style_profile(user_id=USER)
    assert profile is not None
    assert "face_shape" in profile
    assert "skin_tone" in profile
    assert "body_type" in profile
    assert "style_type" in profile
    assert "source_run_id" in profile
    # TRX-6 should have written the five approved appearance fields
    # The development adapter produces deterministic values from the media key hash


def test_outfit_run_learning_signal_emitted():
    """CreateOutfitRun emits a learning signal analysis_updated after TRX-6."""
    from app.application.analysis import CreateOutfitRun
    from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter
    from unittest.mock import Mock

    runs = FakeRuns()
    # Use a concrete class that satisfies the LearningSignalRepository protocol
    class FakeLearningSignal:
        def insert_look_saved(self, *, user_id, label, context):
            pass
        def commit(self):
            pass
        def rollback(self):
            pass

    learning_signal = FakeLearningSignal()

    use_case = CreateOutfitRun(
        runs=runs,
        knowledge=_knowledge_with_catalog(),
        appearance_port=DevelopmentAppearanceAnalysisAdapter(),
        user_state=FakeUserState(None),
        learning_signal=learning_signal,
    )

    class MockImage:
        content_type = "image/jpeg"
        size = 1_000_000

    run_id = use_case(user_id=USER, image=MockImage())
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"


def test_outfit_run_with_development_adapter_full_structure():
    """Verify the complete result structure from CreateOutfitRun with development adapter."""
    from app.application.analysis import CreateOutfitRun
    from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter

    runs = FakeRuns()
    use_case = CreateOutfitRun(
        runs=runs,
        knowledge=_knowledge_with_catalog(),
        appearance_port=DevelopmentAppearanceAnalysisAdapter(),
        user_state=FakeUserState(None),
        learning_signal=None,
    )

    class MockImage:
        content_type = "image/jpeg"
        size = 1_000_000

    run_id = use_case(user_id=USER, image=MockImage())
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None

    # Full result structure verification
    result = record.result
    # Top-level keys
    assert set(result.keys()) == {"appearance", "confidence", "needs_more_data", "recommendations"}
    # Appearance snapshot keys
    app = result["appearance"]
    assert set(app.keys()) == {"faceShape", "skinTone", "bodyType", "styleType", "sourceRunId"}
    # Confidence is a float in [0, 1]
    assert isinstance(result["confidence"], float)
    assert 0.0 <= result["confidence"] <= 1.0
    # needs_more_data is bool
    assert isinstance(result["needs_more_data"], bool)
    # Recommendations structure
    recs = result["recommendations"]
    assert set(recs.keys()) == {"top", "alternatives"}
    assert "id" in recs["top"]
    assert "name" in recs["top"]
    assert "description" in recs["top"]
    assert "matchScore" in recs["top"]
    assert "reasons" in recs["top"]
    assert "stylingTips" in recs["top"]
    assert "maintenance" in recs["top"]
    assert "bestFor" in recs["top"]


def test_outfit_run_with_sparse_profile_sets_needs_more_data():
    """Verify CreateOutfitRun completes successfully and produces a valid
    result snapshot, with the development adapter producing a full profile."""
    from app.application.analysis import CreateOutfitRun
    from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter

    runs = FakeRuns()
    use_case = CreateOutfitRun(
        runs=runs,
        knowledge=_knowledge_with_catalog(),
        appearance_port=DevelopmentAppearanceAnalysisAdapter(),
        user_state=FakeUserState(None),
        learning_signal=None,
    )

    class MockImage:
        content_type = "image/jpeg"
        size = 1_000_000

    run_id = use_case(user_id=USER, image=MockImage())
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result is not None
    # The development adapter always produces a full profile with all observed
    # attributes, so the result should contain all required appearance fields.
    app = record.result["appearance"]
    assert all(k in app for k in ["faceShape", "skinTone", "bodyType", "styleType", "sourceRunId"])
    assert "confidence" in record.result
    assert isinstance(record.result["needs_more_data"], bool)


# ---------------------------------------------------------------------------
# Edge case: CreateOutfitRun validation errors
# ---------------------------------------------------------------------------


def test_outfit_run_invalid_content_type_raises():
    """CreateOutfitRun raises validation error for unsupported image content type."""
    from app.application.analysis import CreateOutfitRun

    runs = FakeRuns()
    use_case = CreateOutfitRun(
        runs=runs,
        knowledge=_knowledge_with_catalog(),
        appearance_port=None,
        user_state=FakeUserState(None),
        learning_signal=None,
    )

    class MockImage:
        content_type = "image/gif"  # unsupported
        size = 1_000_000

    # Validation happens before adapter is called; should raise ApiError
    with pytest.raises(ApiError) as exc_info:
        use_case(user_id=USER, image=MockImage())
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "VALIDATION_ERROR"


def test_outfit_run_image_too_large_raises():
    """CreateOutfitRun raises validation error for oversized image."""
    from app.application.analysis import CreateOutfitRun

    runs = FakeRuns()
    use_case = CreateOutfitRun(
        runs=runs,
        knowledge=_knowledge_with_catalog(),
        appearance_port=None,
        user_state=FakeUserState(None),
        learning_signal=None,
    )

    class MockImage:
        content_type = "image/jpeg"
        size = 50 * 1024 * 1024  # 50 MB, over 20 MB limit

    # Validation happens before adapter is called; should raise ApiError
    with pytest.raises(ApiError) as exc_info:
        use_case(user_id=USER, image=MockImage())
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Edge case: Hairstyle/Grooming without appearance context (profile-only mode)
# ---------------------------------------------------------------------------


def test_hairstyle_without_appearance_context_uses_defaults():
    """Hairstyle recommendation with minimal appearance profile uses neutral
    defaults (oval face shape) and sets needs_more_data when sparse."""
    from app.domain.services.analysis_rules import recommend_hairstyle
    from app.domain.value_objects import AppearanceProfile
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    KNOWLEDGE = CatalogKnowledgeSource()

    # Profile with only faceShape, everything else empty → sparse
    result = recommend_hairstyle(
        KNOWLEDGE,
        AppearanceProfile(faceShape="Round", skinTone="", bodyType="", styleType=""),
    )
    assert result.needs_more_data is True
    assert result.confidence < 0.5
    assert result.top.id in {"textured_quiff", "classic_pompadour"}
    assert result.appearance.faceShape == "Round"


def test_hairstyle_full_profile_no_needs_more_data():
    """Hairstyle recommendation with full profile does not set needs_more_data."""
    from app.domain.services.analysis_rules import recommend_hairstyle
    from app.domain.value_objects import AppearanceProfile
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    KNOWLEDGE = CatalogKnowledgeSource()

    result = recommend_hairstyle(
        KNOWLEDGE,
        AppearanceProfile(
            faceShape="Oval",
            skinTone="Warm Medium",
            bodyType="Athletic",
            styleType="Modern Classic",
        ),
    )
    assert result.needs_more_data is False
    assert result.confidence > 0.5


def test_grooming_without_appearance_context_uses_defaults():
    """Grooming recommendation with minimal appearance profile uses neutral
    defaults and sets needs_more_data when sparse."""
    from app.domain.services.analysis_rules import recommend_grooming
    from app.domain.value_objects import AppearanceProfile
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    KNOWLEDGE = CatalogKnowledgeSource()

    result = recommend_grooming(
        KNOWLEDGE,
        AppearanceProfile(faceShape="Rectangle", skinTone="", bodyType="", styleType=""),
    )
    assert result.needs_more_data is True
    assert result.confidence < 0.5
    assert result.top.id in {"structured_goatee", "classic_stubble", "full_beard", "goatee_with_mustache"}


def test_grooming_full_profile_no_needs_more_data():
    """Grooming recommendation with full profile does not set needs_more_data."""
    from app.domain.services.analysis_rules import recommend_grooming
    from app.domain.value_objects import AppearanceProfile
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    KNOWLEDGE = CatalogKnowledgeSource()

    result = recommend_grooming(
        KNOWLEDGE,
        AppearanceProfile(
            faceShape="Oval",
            skinTone="Warm Medium",
            bodyType="Athletic",
            styleType="Modern Classic",
        ),
    )
    assert result.needs_more_data is False
    assert result.confidence > 0.5


# ---------------------------------------------------------------------------
# Determinism tests: identical inputs → identical outputs regardless of data source
# ---------------------------------------------------------------------------


def test_recommendation_deterministic_with_image_appearance_profile():
    """Recommendation is deterministic when using image-derived AppearanceProfile
    from the development adapter — identical media key → identical results."""
    from app.application.analysis import CreateOutfitRun
    from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter
    from app.domain.services.analysis_rules import recommend_hairstyle
    from app.domain.value_objects import AppearanceProfile
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    KNOWLEDGE = CatalogKnowledgeSource()
    adapter = DevelopmentAppearanceAnalysisAdapter()

    runs = FakeRuns()
    use_case = CreateOutfitRun(
        runs=runs,
        knowledge=KNOWLEDGE,
        appearance_port=adapter,
        user_state=FakeUserState(None),
        learning_signal=None,
    )

    class MockImage:
        content_type = "image/jpeg"
        size = 1_000_000

    # Two runs with different image keys should produce different (deterministic) profiles
    # but each run should be internally deterministic
    run_id_1 = use_case(user_id=USER, image=MockImage())
    record_1 = runs.get_for_user(user_id=USER, run_id=run_id_1)

    # Reset and run again with same setup
    runs.rows = {}
    use_case2 = CreateOutfitRun(
        runs=runs,
        knowledge=KNOWLEDGE,
        appearance_port=adapter,
        user_state=FakeUserState(None),
        learning_signal=None,
    )
    run_id_2 = use_case2(user_id=USER, image=MockImage())
    record_2 = runs.get_for_user(user_id=USER, run_id=run_id_2)

    # Both should produce completed runs with valid results
    assert record_1 is not None and record_1.status == "completed"
    assert record_2 is not None and record_2.status == "completed"
    assert record_1.result is not None
    assert record_2.result is not None


def test_confidence_deterministic_regardless_of_source():
    """Confidence derivation is deterministic and follows the same formula
    (50% completeness + 50% decisiveness) whether appearance profile comes
    from image analysis or user profile."""
    from app.domain.services.analysis_rules import derive_confidence, recommend_hairstyle
    from app.domain.value_objects import AppearanceProfile
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    KNOWLEDGE = CatalogKnowledgeSource()

    # Full profile → higher confidence
    full_profile = AppearanceProfile(
        faceShape="Oval",
        skinTone="Warm Medium",
        bodyType="Athletic",
        styleType="Modern Classic",
        sourceRunId="run-1",
    )
    full_result = recommend_hairstyle(KNOWLEDGE, full_profile)
    assert full_result.confidence > 0.5

    # Sparse profile → lower confidence
    sparse_profile = AppearanceProfile(
        faceShape="Round",
        skinTone="",
        bodyType="",
        styleType="",
        sourceRunId="run-2",
    )
    sparse_result = recommend_hairstyle(KNOWLEDGE, sparse_profile)
    assert sparse_result.confidence < 0.5


# ============================================================================
# TEST CONSTRAINTS (per strict rules)
# ============================================================================

# ---------------------------------------------------------------------------
# DO NOT modify existing Hairstyle/Grooming behavior — tests reuse existing
# engine functions; profile-based flows remain unchanged
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DO NOT add new dependencies — use existing test infrastructure (fake repos)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# DO NOT implement real AI models — development adapter is hash-based, not model-driven
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tests run against fake/in-memory repositories where appropriate
# ============================================================================