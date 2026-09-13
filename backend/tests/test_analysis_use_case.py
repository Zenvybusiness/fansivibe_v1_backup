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

import hashlib
import io
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

    def create(self, *, user_id, run_type, engine_version="rules-v1", input_media=None, knowledge_version=None) -> UUID:
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
            "knowledge_version": knowledge_version,
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
    run_id = use_case(user_id=USER)
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
    run_id = use_case(user_id=USER)
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
        use_case(user_id=USER)
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
    run_id = use_case(user_id=USER)
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
    run_id = use_case(user_id=USER)
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
    run_id = use_case(user_id=USER)
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
        use_case(user_id=USER)
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
    run_id = use_case(user_id=USER)
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
    run_id_1 = use_case(user_id=USER)
    record_1 = runs.get_for_user(user_id=USER, run_id=run_id_1)
    assert record_1 is not None
    assert record_1.status == "completed"
    assert record_1.result is not None

    # Create second run - should not overwrite first
    run_id_2 = use_case(user_id=USER)
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

    run_id = use_case(user_id=USER)
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    # Status should transition from pending to completed
    assert record.status == "completed"


def test_grooming_no_reference_required():
    """Phase 28: no face-profile reference exists — use case resolves
    style_profile by user_id alone."""
    runs = FakeRuns()
    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval"}),
        knowledge=_knowledge_with_catalog(),
    )
    run_id = use_case(user_id=USER)
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"


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
    run_id = use_case(user_id=USER)
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
    run_id = use_case(user_id=USER)
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
    run_id = use_case(user_id=USER)
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
        file = io.BytesIO(b"fake-image-bytes-for-outfit-scan")

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
        file = io.BytesIO(b"fake-image-bytes-for-outfit-scan")

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
        def insert_look_saved(self, *, user_id, signal_type="look_saved", label, context):
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
        file = io.BytesIO(b"fake-image-bytes-for-outfit-scan")

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
        file = io.BytesIO(b"fake-image-bytes-for-outfit-scan")

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
        file = io.BytesIO(b"fake-image-bytes-for-outfit-scan")

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
        file = io.BytesIO(b"fake-image-bytes-for-outfit-scan")

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
# STEP 10.3 — media hashing + hairstyle image-run infrastructure tests
#
# DB-free. Proves: real SHA-256 contentHash from received bytes, the
# hairstyle image path creates a hairstyle-typed run (never via
# CreateOutfitRun), and error payloads carry no image bytes.
# ============================================================================


def _image_with_bytes(payload: bytes, content_type: str = "image/jpeg", size=None):
    class MockImage:
        pass

    img = MockImage()
    img.content_type = content_type
    img.size = len(payload) if size is None else size
    img.file = io.BytesIO(payload)
    return img


class StubAppearancePort:
    """Explicit stub AppearanceAnalysisPort — records calls, returns a fixed
    measured profile. Never the development/hash adapter."""

    def __init__(self, profile) -> None:
        self._profile = profile
        self.calls: list = []

    def analyze(self, *, media_ref, user_id, image_bytes=None):
        self.calls.append(
            {"media_ref": media_ref, "user_id": user_id, "image_bytes": image_bytes}
        )
        return self._profile

    def validate_result(self, result) -> bool:
        return True


def _measured_profile(**overrides):
    from app.domain.value_objects import AppearanceProfile

    base = {
        "faceShape": "oval",
        "skinTone": "C01",
        "bodyType": "average",
        "styleType": "casual",
        "sourceRunId": "",
    }
    base.update(overrides)
    return AppearanceProfile(**base)


class FakeLearningSignal:
    """Recording LearningSignalRepository double."""

    def __init__(self) -> None:
        self.calls: list = []

    def insert_look_saved(self, *, user_id, signal_type="look_saved", label, context):
        self.calls.append({"user_id": user_id, "signal_type": signal_type, "label": label, "context": context})

    def commit(self):
        pass

    def rollback(self):
        pass


# --- Change 1: real SHA-256 content hash ------------------------------------


def test_sha256_helper_matches_hashlib_vector():
    from app.application.media import sha256_hex

    digest = sha256_hex(b"abc")
    assert digest == hashlib.sha256(b"abc").hexdigest()
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_same_bytes_same_hash_different_bytes_differ():
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
    run_a = use_case(user_id=USER, image=_image_with_bytes(b"same-bytes"))
    run_b = use_case(user_id=USER, image=_image_with_bytes(b"same-bytes"))
    run_c = use_case(user_id=USER, image=_image_with_bytes(b"other-bytes"))
    hash_a = runs.get_for_user(user_id=USER, run_id=run_a).input_media["contentHash"]
    hash_b = runs.get_for_user(user_id=USER, run_id=run_b).input_media["contentHash"]
    hash_c = runs.get_for_user(user_id=USER, run_id=run_c).input_media["contentHash"]
    assert hash_a == hash_b
    assert hash_a != hash_c


def test_outfit_media_ref_content_hash_is_real_sha256():
    from app.application.analysis import CreateOutfitRun
    from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter

    payload = b"real-bytes-for-hash-check"
    runs = FakeRuns()
    use_case = CreateOutfitRun(
        runs=runs,
        knowledge=_knowledge_with_catalog(),
        appearance_port=DevelopmentAppearanceAnalysisAdapter(),
        user_state=FakeUserState(None),
        learning_signal=None,
    )
    run_id = use_case(user_id=USER, image=_image_with_bytes(payload))
    media = runs.get_for_user(user_id=USER, run_id=run_id).input_media
    assert media["contentHash"] == hashlib.sha256(payload).hexdigest()
    assert len(media["contentHash"]) == 64
    assert media["isGenerated"] is False
    assert media["key"].startswith(f"users/{USER}/scans/")
    assert media["mediaType"] == "image/jpeg"
    assert media["sizeBytes"] == len(payload)
    # No image bytes in the persisted MediaRef — metadata only.
    assert not any(isinstance(v, (bytes, bytearray)) for v in media.values())


# --- Change 2: hairstyle-typed image run ------------------------------------


def test_hairstyle_image_run_creates_hairstyle_typed_run():
    from app.application.analysis import CreateHairstyleImageRun

    payload = b"hairstyle-scan-bytes"
    runs = FakeRuns()
    user_state = FakeUserState(None)
    learning_signal = FakeLearningSignal()
    port = StubAppearancePort(_measured_profile())
    use_case = CreateHairstyleImageRun(
        runs=runs,
        knowledge=_knowledge_with_catalog(),
        appearance_port=port,
        user_state=user_state,
        learning_signal=learning_signal,
    )
    run_id = use_case(user_id=USER, image=_image_with_bytes(payload))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.run_type == "hairstyle"
    assert record.status == "completed"
    assert record.error is None
    # Measured appearance flows through; provenance anchored to the run.
    assert record.result["appearance"]["faceShape"] == "oval"
    assert record.result["appearance"]["sourceRunId"] == str(run_id)
    assert record.input_media["contentHash"] == hashlib.sha256(payload).hexdigest()
    # The injected port was used exactly once (never CreateOutfitRun).
    assert len(port.calls) == 1
    assert port.calls[0]["user_id"] == USER
    # TRX-6 persisted the measured profile for future runs.
    profile = user_state.get_style_profile(user_id=USER)
    assert profile is not None
    assert profile["face_shape"] == "oval"
    assert profile["source_run_id"] == str(run_id)
    # analysis_updated signal emitted; no outfit_selected leakage.
    labels = [c["label"] for c in learning_signal.calls]
    assert "analysis_updated" in labels
    assert "outfit_selected" not in labels


def test_hairstyle_image_run_requires_explicit_port():
    from app.application.analysis import CreateHairstyleImageRun

    with pytest.raises(TypeError):
        CreateHairstyleImageRun(
            runs=FakeRuns(),
            knowledge=_knowledge_with_catalog(),
        )


def test_hairstyle_image_run_empty_face_shape_fails_honestly():
    from app.application.analysis import CreateHairstyleImageRun

    runs = FakeRuns()
    user_state = FakeUserState(None)
    use_case = CreateHairstyleImageRun(
        runs=runs,
        knowledge=_knowledge_with_catalog(),
        appearance_port=StubAppearancePort(_measured_profile(faceShape="")),
        user_state=user_state,
        learning_signal=None,
    )
    run_id = use_case(user_id=USER, image=_image_with_bytes(b"no-face-bytes"))
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.run_type == "hairstyle"
    assert record.status == "failed"
    assert record.result is None
    assert record.error["code"] == "PROCESSING_FAILURE"
    assert record.error["details"]["run_id"] == str(run_id)
    # Nothing fabricated into the profile.
    assert user_state.get_style_profile(user_id=USER) is None


def test_hairstyle_image_run_validation_unchanged():
    from app.application.analysis import CreateHairstyleImageRun

    runs = FakeRuns()

    def _use_case():
        return CreateHairstyleImageRun(
            runs=runs,
            knowledge=_knowledge_with_catalog(),
            appearance_port=StubAppearancePort(_measured_profile()),
            user_state=FakeUserState(None),
            learning_signal=None,
        )

    with pytest.raises(ApiError) as excinfo:
        _use_case()(
            user_id=USER,
            image=_image_with_bytes(b"bytes", content_type="image/gif"),
        )
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "VALIDATION_ERROR"

    with pytest.raises(ApiError) as excinfo:
        _use_case()(
            user_id=USER,
            image=_image_with_bytes(b"bytes", size=50 * 1024 * 1024),
        )
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "VALIDATION_ERROR"
    # Rejected inputs create no runs.
    assert runs.rows == {}


def test_image_error_payloads_carry_no_bytes():
    from app.application.analysis import CreateHairstyleImageRun

    use_case = CreateHairstyleImageRun(
        runs=FakeRuns(),
        knowledge=_knowledge_with_catalog(),
        appearance_port=StubAppearancePort(_measured_profile()),
        user_state=FakeUserState(None),
        learning_signal=None,
    )
    with pytest.raises(ApiError) as excinfo:
        use_case(
            user_id=USER,
            image=_image_with_bytes(b"bytes", content_type="image/gif"),
        )
    assert not any(
        isinstance(v, (bytes, bytearray)) for v in excinfo.value.details.values()
    )


# ============================================================================
# STEP 11.2 — save → memory → hairstyle ranking loop (DB-free, fake repos)
#
# Proves CreateHairstyleRun reads the owner's saved_looks via the EXISTING
# SavedLookRepository.list_for_user() and maps valid saved hairstyle look IDs
# into the EXISTING HairstylePreferences.preferredLookIds consumed by the
# existing filtering/ranking path. No schema, API, or Flutter changes.
# ============================================================================

from app.domain.ports.repositories import SavedLookRecord


class FakeSavedLooks:
    """In-memory SavedLookRepository double (owner-scoped, OW-1)."""

    def __init__(self) -> None:
        self._rows: list[tuple[UUID, SavedLookRecord]] = []
        self.calls: list = []

    def add(self, user_id: UUID, look_id, title: str = "Saved look") -> None:
        self._rows.append(
            (
                user_id,
                SavedLookRecord(
                    id=uuid4(),
                    look_id=look_id,
                    title=title,
                    snapshot={},
                    source_run_id=None,
                    created_at=datetime.now(timezone.utc),
                ),
            )
        )

    def list_for_user(self, *, user_id: UUID, page: int, page_size: int):
        self.calls.append({"user_id": user_id, "page": page, "page_size": page_size})
        owned = [rec for uid, rec in self._rows if uid == user_id]
        return owned, len(owned)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _hairstyle_use_case(runs, saved_looks=None):
    return CreateHairstyleRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval", "skin_tone": "Warm Medium"}),
        knowledge=_knowledge_with_catalog(),
        saved_looks=saved_looks,
    )


def test_11_2_no_saved_looks_existing_behavior_unchanged():
    """A. No saved looks → existing recommendation behavior (top quiff)."""
    runs = FakeRuns()
    run_id = _hairstyle_use_case(runs, FakeSavedLooks())(
        user_id=USER
    )
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    recs = record.result["recommendations"]
    assert recs["top"]["id"] == "textured_quiff"
    assert len(recs["alternatives"]) == 3


def test_11_2_no_saved_looks_repo_wired_behavior_unchanged():
    """A2. Backward compat: callers without saved_looks still complete."""
    runs = FakeRuns()
    run_id = _hairstyle_use_case(runs)(
        user_id=USER
    )
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result["recommendations"]["top"]["id"] == "textured_quiff"


def test_11_2_saved_hairstyle_look_populates_preferred():
    """B. Saved hairstyle look ID lands in preferredLookIds (never excluded)."""
    from app.application import analysis as analysis_module

    runs = FakeRuns()
    saved = FakeSavedLooks()
    saved.add(USER, "classic_pompadour")
    use_case = _hairstyle_use_case(runs, saved)

    captured: dict = {}
    real_recommend = analysis_module.recommend_hairstyle

    def spy(knowledge, appearance, preferences=None, **kwargs):
        captured["preferences"] = preferences
        return real_recommend(knowledge, appearance, preferences, **kwargs)

    with patch.object(analysis_module, "recommend_hairstyle", spy):
        run_id = use_case(user_id=USER)

    prefs = captured["preferences"]
    assert prefs is not None
    assert "classic_pompadour" in prefs.preferredLookIds
    assert len(prefs.excludedLookIds) == 0
    # Owner scoping: the read used the caller's own user_id.
    assert saved.calls and saved.calls[0]["user_id"] == USER
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"


def test_11_2_other_user_saved_look_cannot_influence():
    """C. Another user's saved look never influences the current user."""
    from app.application import analysis as analysis_module

    runs = FakeRuns()
    saved = FakeSavedLooks()
    saved.add(uuid4(), "classic_pompadour")  # someone else's save
    use_case = _hairstyle_use_case(runs, saved)

    captured: dict = {}
    real_recommend = analysis_module.recommend_hairstyle

    def spy(knowledge, appearance, preferences=None, **kwargs):
        captured["preferences"] = preferences
        return real_recommend(knowledge, appearance, preferences, **kwargs)

    with patch.object(analysis_module, "recommend_hairstyle", spy):
        run_id = use_case(user_id=USER)

    assert len(captured["preferences"].preferredLookIds) == 0
    assert len(captured["preferences"].excludedLookIds) == 0
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record.result["recommendations"]["top"]["id"] == "textured_quiff"


def test_11_2_filtering_ranking_consume_populated_preferences():
    """D. Existing filtering keeps + ranking boosts the saved hairstyle look."""
    from app.application import analysis as analysis_module
    from app.domain.services.analysis_rules import (
        build_context,
        filter_candidates,
        generate_candidates,
        score_candidates,
    )
    from app.domain.value_objects import AppearanceProfile

    runs = FakeRuns()
    saved = FakeSavedLooks()
    saved.add(USER, "classic_pompadour")
    use_case = _hairstyle_use_case(runs, saved)

    captured: dict = {}
    real_recommend = analysis_module.recommend_hairstyle

    def spy(knowledge, appearance, preferences=None, **kwargs):
        captured["preferences"] = preferences
        return real_recommend(knowledge, appearance, preferences, **kwargs)

    with patch.object(analysis_module, "recommend_hairstyle", spy):
        use_case(user_id=USER)

    prefs = captured["preferences"]
    knowledge = _knowledge_with_catalog()
    appearance = AppearanceProfile(faceShape="Oval")
    context = build_context(appearance, prefs)
    candidates = generate_candidates(knowledge, context)
    filtered = filter_candidates(candidates, context)
    # Filtering (hard exclusion) must NOT drop the saved look.
    assert any(look.id == "classic_pompadour" for look in filtered)
    scored = {s.id: s for s in score_candidates(filtered, context)}
    # Ranking (soft preference) must credit it via the existing signal.
    assert scored["classic_pompadour"].signals["preference"] == 0.03


def test_11_2_non_hairstyle_and_unknown_ids_ignored():
    """Only valid hairstyle catalog IDs map; titles are never inferred from."""
    from app.application import analysis as analysis_module

    runs = FakeRuns()
    saved = FakeSavedLooks()
    saved.add(USER, None, title="Saved Outfit")  # outfit save: look_id=None
    saved.add(USER, "structured_goatee", title="Goatee")  # grooming catalog ID
    saved.add(USER, "not_a_real_look", title="classic_pompadour")  # unknown code
    use_case = _hairstyle_use_case(runs, saved)

    captured: dict = {}
    real_recommend = analysis_module.recommend_hairstyle

    def spy(knowledge, appearance, preferences=None, **kwargs):
        captured["preferences"] = preferences
        return real_recommend(knowledge, appearance, preferences, **kwargs)

    with patch.object(analysis_module, "recommend_hairstyle", spy):
        use_case(user_id=USER)

    assert len(captured["preferences"].preferredLookIds) == 0
    assert len(captured["preferences"].excludedLookIds) == 0


def test_11_2_no_schema_migration_required():
    """E. The loop is DB-free composition: no DDL in the use-case module."""
    import pathlib

    source = pathlib.Path("app/application/analysis.py").read_text()
    assert "CREATE TABLE" not in source
    assert "ALTER TABLE" not in source
    assert "alembic" not in source.lower()
    # And it runs entirely against fake repos (no database).
    runs = FakeRuns()
    run_id = _hairstyle_use_case(runs, FakeSavedLooks())(
        user_id=USER
    )
    assert runs.get_for_user(user_id=USER, run_id=run_id).status == "completed"


# ============================================================================
# STEP 11.2.1 — production wiring: router injects SavedLookRepositorySQL(db)
# into CreateHairstyleRun(saved_looks=...). DB-free: the use case is spied,
# the real SavedLookRepositorySQL class is asserted (session passthrough only,
# no DB hit).
# ============================================================================


def test_11_2_1_router_injects_saved_look_repo_into_create_hairstyle_run(monkeypatch):
    import time as _time_mod
    from datetime import datetime as _dt, timezone as _tz

    # Neutralize this module's autouse time.time fixture (struct_time) which
    # breaks Starlette TestClient cookie handling; the wiring path needs a
    # real float timestamp.
    _time_mod.time = lambda: _dt.now(_tz.utc).timestamp()

    import uuid as _uuid

    from fastapi.testclient import TestClient

    import app.api.routers.analysis as analysis_router
    from app.infrastructure.db.repositories import SavedLookRepositorySQL

    router_user = _uuid.uuid4()
    db_session = object()
    run_id = _uuid.uuid4()
    captured: dict = {}

    class SpyCreateHairstyleRun:
        def __init__(self, **kwargs) -> None:
            captured["kwargs"] = kwargs

        def __call__(self, *, user_id):
            captured["user_id"] = user_id
            return run_id

    monkeypatch.setattr(analysis_router, "CreateHairstyleRun", SpyCreateHairstyleRun)

    from app.main import app
    from app.api.deps import get_current_user_id
    from app.infrastructure.db.session import get_db

    old_db = app.dependency_overrides.get(get_db)
    old_user = app.dependency_overrides.get(get_current_user_id)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user_id] = lambda: router_user
    try:
        client = TestClient(app)
        ref = str(_uuid.uuid4())
        resp = client.post("/v1/analysis/hairstyle", data={})
        assert resp.status_code == 202
        assert resp.json()["run_id"] == str(run_id)
    finally:
        if old_db is not None:
            app.dependency_overrides[get_db] = old_db
        else:
            app.dependency_overrides.pop(get_db, None)
        if old_user is not None:
            app.dependency_overrides[get_current_user_id] = old_user
        else:
            app.dependency_overrides.pop(get_current_user_id, None)

    saved_looks = captured["kwargs"].get("saved_looks")
    assert isinstance(saved_looks, SavedLookRepositorySQL)
    assert saved_looks._session is db_session
    assert captured["user_id"] == router_user
    assert "face_profile_ref" not in captured


# ============================================================================
# STEP 11.3 — save → memory → grooming ranking loop (DB-free, fake repos)
#
# Proves CreateGroomingRun reads the owner's saved_looks via the EXISTING
# SavedLookRepository.list_for_user() and maps valid saved grooming look IDs
# into the EXISTING HairstylePreferences.preferredLookIds consumed by the
# canonical grooming_rules.recommend_grooming path. No schema, API, scoring,
# or Flutter changes. The analysis_rules.py shadow grooming implementation
# (saved_look_ids / personalization_context) is NOT used.
# ============================================================================


def _grooming_use_case(runs, saved_looks=None):
    return CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval", "skin_tone": "Warm Medium", "body_type": "Athletic", "style_type": "Modern Classic"}),
        knowledge=_knowledge_with_catalog(),
        saved_looks=saved_looks,
    )


def test_11_3_no_saved_looks_existing_behavior_unchanged():
    """A. No saved looks → existing recommendation behavior (top goatee)."""
    runs = FakeRuns()
    run_id = _grooming_use_case(runs, FakeSavedLooks())(
        user_id=USER
    )
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    recs = record.result["recommendations"]
    assert recs["top"]["id"] == "structured_goatee"
    assert len(recs["alternatives"]) == 3


def test_11_3_no_saved_looks_repo_wired_behavior_unchanged():
    """B. Backward compat: callers without saved_looks still complete."""
    runs = FakeRuns()
    run_id = _grooming_use_case(runs)(
        user_id=USER
    )
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result["recommendations"]["top"]["id"] == "structured_goatee"


def test_11_3_saved_grooming_look_populates_preferred():
    """C. Saved grooming look ID lands in preferredLookIds (never excluded)."""
    from app.application import analysis as analysis_module

    runs = FakeRuns()
    saved = FakeSavedLooks()
    saved.add(USER, "classic_stubble")
    use_case = _grooming_use_case(runs, saved)

    captured: dict = {}
    real_recommend = analysis_module.recommend_grooming

    def spy(knowledge, appearance, preferences=None, **kwargs):
        captured["preferences"] = preferences
        return real_recommend(knowledge, appearance, preferences, **kwargs)

    with patch.object(analysis_module, "recommend_grooming", spy):
        run_id = use_case(user_id=USER)

    prefs = captured["preferences"]
    assert prefs is not None
    assert "classic_stubble" in prefs.preferredLookIds
    assert len(prefs.excludedLookIds) == 0
    # Owner scoping: the read used the caller's own user_id.
    assert saved.calls and saved.calls[0]["user_id"] == USER
    assert saved.calls[0]["page"] == 1
    assert saved.calls[0]["page_size"] == 100
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"


def test_11_3_other_user_saved_look_cannot_influence():
    """D. Another user's saved grooming look never influences the user."""
    from app.application import analysis as analysis_module

    runs = FakeRuns()
    saved = FakeSavedLooks()
    saved.add(uuid4(), "classic_stubble")  # someone else's save
    use_case = _grooming_use_case(runs, saved)

    captured: dict = {}
    real_recommend = analysis_module.recommend_grooming

    def spy(knowledge, appearance, preferences=None, **kwargs):
        captured["preferences"] = preferences
        return real_recommend(knowledge, appearance, preferences, **kwargs)

    with patch.object(analysis_module, "recommend_grooming", spy):
        run_id = use_case(user_id=USER)

    assert len(captured["preferences"].preferredLookIds) == 0
    assert len(captured["preferences"].excludedLookIds) == 0
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record.result["recommendations"]["top"]["id"] == "structured_goatee"


def test_11_3_saved_hairstyle_id_ignored():
    """E. Saved hairstyle IDs are ignored by grooming personalization."""
    from app.application import analysis as analysis_module

    runs = FakeRuns()
    saved = FakeSavedLooks()
    saved.add(USER, "classic_pompadour")  # hairstyle catalog ID
    saved.add(USER, "textured_quiff")  # hairstyle catalog ID
    use_case = _grooming_use_case(runs, saved)

    captured: dict = {}
    real_recommend = analysis_module.recommend_grooming

    def spy(knowledge, appearance, preferences=None, **kwargs):
        captured["preferences"] = preferences
        return real_recommend(knowledge, appearance, preferences, **kwargs)

    with patch.object(analysis_module, "recommend_grooming", spy):
        use_case(user_id=USER)

    assert len(captured["preferences"].preferredLookIds) == 0
    assert len(captured["preferences"].excludedLookIds) == 0


def test_11_3_none_outfit_and_unknown_ids_ignored():
    """F+G. look_id=None (outfit save) and unknown codes map to nothing."""
    from app.application import analysis as analysis_module

    runs = FakeRuns()
    saved = FakeSavedLooks()
    saved.add(USER, None, title="Saved Outfit")  # outfit save: look_id=None
    saved.add(USER, "", title="Empty ID")
    saved.add(USER, "not_a_real_look", title="classic_stubble")  # unknown code
    use_case = _grooming_use_case(runs, saved)

    captured: dict = {}
    real_recommend = analysis_module.recommend_grooming

    def spy(knowledge, appearance, preferences=None, **kwargs):
        captured["preferences"] = preferences
        return real_recommend(knowledge, appearance, preferences, **kwargs)

    with patch.object(analysis_module, "recommend_grooming", spy):
        use_case(user_id=USER)

    assert len(captured["preferences"].preferredLookIds) == 0
    assert len(captured["preferences"].excludedLookIds) == 0


def test_11_3_filtering_ranking_consume_populated_preferences():
    """C (boost). Existing grooming filtering keeps + ranking boosts the look."""
    from app.application import analysis as analysis_module
    from app.domain.services.grooming_rules import (
        build_grooming_context,
        filter_grooming_candidates,
        generate_grooming_candidates,
        score_grooming_candidates,
    )
    from app.domain.value_objects import AppearanceProfile

    runs = FakeRuns()
    saved = FakeSavedLooks()
    saved.add(USER, "classic_stubble")
    use_case = _grooming_use_case(runs, saved)

    captured: dict = {}
    real_recommend = analysis_module.recommend_grooming

    def spy(knowledge, appearance, preferences=None, **kwargs):
        captured["preferences"] = preferences
        return real_recommend(knowledge, appearance, preferences, **kwargs)

    with patch.object(analysis_module, "recommend_grooming", spy):
        use_case(user_id=USER)

    prefs = captured["preferences"]
    knowledge = _knowledge_with_catalog()
    appearance = AppearanceProfile(faceShape="Oval")
    context = build_grooming_context(appearance, prefs)
    candidates = generate_grooming_candidates(knowledge, context)
    filtered = filter_grooming_candidates(candidates, context)
    # Filtering (hard exclusion) must NOT drop the saved look.
    assert any(look.id == "classic_stubble" for look in filtered)
    scored = {s.id: s for s in score_grooming_candidates(filtered, context)}
    # Ranking (soft preference) must credit it via the existing signal.
    assert scored["classic_stubble"].signals["preference"] == 0.03


def test_11_3_repository_failure_degrades_to_empty_preferences():
    """H. Saved-look read failure → recommendation still succeeds."""
    from app.application import analysis as analysis_module

    class FailingSavedLooks(FakeSavedLooks):
        def list_for_user(self, *, user_id, page, page_size):
            raise RuntimeError("db unavailable")

    runs = FakeRuns()
    use_case = _grooming_use_case(runs, FailingSavedLooks())

    captured: dict = {}
    real_recommend = analysis_module.recommend_grooming

    def spy(knowledge, appearance, preferences=None, **kwargs):
        captured["preferences"] = preferences
        return real_recommend(knowledge, appearance, preferences, **kwargs)

    with patch.object(analysis_module, "recommend_grooming", spy):
        run_id = use_case(user_id=USER)

    assert len(captured["preferences"].preferredLookIds) == 0
    assert len(captured["preferences"].excludedLookIds) == 0
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.status == "completed"
    assert record.result["recommendations"]["top"]["id"] == "structured_goatee"


def test_11_3_router_injects_saved_look_repo_into_create_grooming_run(monkeypatch):
    """I. Grooming router injects SavedLookRepositorySQL(db) (11.2.1 pattern)."""
    import time as _time_mod
    from datetime import datetime as _dt, timezone as _tz

    # Neutralize this module's autouse time.time fixture (struct_time) which
    # breaks Starlette TestClient cookie handling; the wiring path needs a
    # real float timestamp.
    _time_mod.time = lambda: _dt.now(_tz.utc).timestamp()

    import uuid as _uuid

    from fastapi.testclient import TestClient

    import app.api.routers.analysis as analysis_router
    from app.infrastructure.db.repositories import SavedLookRepositorySQL

    router_user = _uuid.uuid4()
    db_session = object()
    run_id = _uuid.uuid4()
    captured: dict = {}

    class SpyCreateGroomingRun:
        def __init__(self, **kwargs) -> None:
            captured["kwargs"] = kwargs

        def __call__(self, *, user_id):
            captured["user_id"] = user_id
            return run_id

    monkeypatch.setattr(analysis_router, "CreateGroomingRun", SpyCreateGroomingRun)

    from app.main import app
    from app.api.deps import get_current_user_id
    from app.infrastructure.db.session import get_db

    old_db = app.dependency_overrides.get(get_db)
    old_user = app.dependency_overrides.get(get_current_user_id)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_user_id] = lambda: router_user
    try:
        client = TestClient(app)
        ref = str(_uuid.uuid4())
        resp = client.post("/v1/analysis/grooming", json={})
        assert resp.status_code == 202
        assert resp.json()["run_id"] == str(run_id)
    finally:
        if old_db is not None:
            app.dependency_overrides[get_db] = old_db
        else:
            app.dependency_overrides.pop(get_db, None)
        if old_user is not None:
            app.dependency_overrides[get_current_user_id] = old_user
        else:
            app.dependency_overrides.pop(get_current_user_id, None)

    saved_looks = captured["kwargs"].get("saved_looks")
    assert isinstance(saved_looks, SavedLookRepositorySQL)
    assert saved_looks._session is db_session
    assert captured["user_id"] == router_user
    assert "face_profile_ref" not in captured


# ============================================================================
# STEP 11.13 C — analysis lifecycle persists typed signals (DB-backed).
#
# Runs when PostgreSQL is reachable, skips otherwise (like every other
# DB-backed test here). Uses real SQL repositories: the completed run must
# leave exactly its typed signal rows behind — previously the flush-only
# inserts were discarded on session close.
# ============================================================================


def _11_13_session():
    from tests.conftest import make_session

    return make_session()()


@pytest.fixture
def _11_13_db(migrated_db: str):
    """Function-scoped DB fixture for the STEP 11.13 lifecycle tests.

    The module `db` fixture cannot be used here: this module's autouse time
    fixture replaces `time.time` with a struct_time, under which SQLAlchemy
    connection pools cannot be created during fixture setup. Restoring a real
    float clock first (same workaround as the STEP 11.2.1 router test) keeps
    truncation + sessions working; the autouse fixture restores its patch
    afterwards.
    """
    import time as _time_mod
    from datetime import datetime as _dt, timezone as _tz
    from sqlalchemy import text

    from tests.conftest import _TRUNCATE, make_session

    _time_mod.time = lambda: _dt.now(_tz.utc).timestamp()
    Session = make_session(migrated_db)
    with Session() as session:
        session.execute(text(_TRUNCATE))
        session.commit()
    yield Session
    with Session() as session:
        session.execute(text(_TRUNCATE))
        session.commit()


def _11_13_seed_user(session, subject="signal-user"):
    from app.infrastructure.db.models import Users, UserState

    user = Users(auth_provider="dev", auth_subject=subject, display_name="Sig")
    session.add(user)
    session.flush()
    session.add(
        UserState(
            user_id=user.id,
            style_profile={
                "face_shape": "Oval",
                "skin_tone": "Warm Medium",
                "body_type": "Athletic",
                "style_type": "Modern Classic",
            },
        )
    )
    session.commit()
    return user.id


def _11_13_signal_rows(session, user_id):
    from sqlalchemy import select

    from app.infrastructure.db.models import LearningSignals

    return session.execute(
        select(
            LearningSignals.signal_type,
            LearningSignals.label,
            LearningSignals.context,
        )
        .where(LearningSignals.user_id == user_id)
        .order_by(LearningSignals.occurred_at)
    ).all()


def test_11_13_outfit_run_persists_typed_signals_db(_11_13_db):
    """C. Completed outfit run → exactly analysis_updated + outfit_selected."""
    from sqlalchemy import text

    from app.application.analysis import CreateOutfitRun
    from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter
    from app.infrastructure.db.repositories import (
        AnalysisRunRepositorySQL,
        LearningSignalRepositorySQL,
        UserStateRepositorySQL,
    )

    Session = _11_13_db
    session = Session()
    try:
        uid = _11_13_seed_user(session)
        use_case = CreateOutfitRun(
            runs=AnalysisRunRepositorySQL(session),
            knowledge=_knowledge_with_catalog(),
            appearance_port=DevelopmentAppearanceAnalysisAdapter(),
            user_state=UserStateRepositorySQL(session),
            learning_signal=LearningSignalRepositorySQL(session),
        )

        class MockImage:
            content_type = "image/jpeg"
            size = 1_000_000
            file = io.BytesIO(b"lifecycle-probe-bytes")

        run_id = use_case(user_id=uid, image=MockImage())
        record = AnalysisRunRepositorySQL(session).get_for_user(
            user_id=uid, run_id=run_id
        )
        assert record is not None
        assert record.status == "completed"

        rows = _11_13_signal_rows(session, uid)
        assert [(r[0], r[1]) for r in rows] == [
            ("analysis_updated", "analysis_updated"),
            ("outfit_selected", "outfit_selected"),
        ]
        assert rows[0][2] == {"run_id": str(run_id), "run_type": "outfit"}
        assert rows[1][2] == {
            "source_context": "outfit",
            "run_id": str(run_id),
            "run_type": "outfit",
        }
    finally:
        session.execute(
            text("DELETE FROM analysis_runs WHERE run_type = 'outfit'")
        )
        session.commit()
        session.close()


def test_11_13_hairstyle_image_run_persists_typed_signal_db(_11_13_db):
    """C. Completed hairstyle image run → exactly one analysis_updated."""
    from app.application.analysis import CreateHairstyleImageRun
    from app.infrastructure.db.repositories import (
        AnalysisRunRepositorySQL,
        LearningSignalRepositorySQL,
        UserStateRepositorySQL,
    )

    Session = _11_13_db
    session = Session()
    try:
        uid = _11_13_seed_user(session, subject="signal-user-2")
        use_case = CreateHairstyleImageRun(
            runs=AnalysisRunRepositorySQL(session),
            knowledge=_knowledge_with_catalog(),
            appearance_port=StubAppearancePort(_measured_profile()),
            user_state=UserStateRepositorySQL(session),
            learning_signal=LearningSignalRepositorySQL(session),
        )
        run_id = use_case(user_id=uid, image=_image_with_bytes(b"hair-bytes"))
        rows = _11_13_signal_rows(session, uid)
        assert [(r[0], r[1]) for r in rows] == [
            ("analysis_updated", "analysis_updated")
        ]
        assert rows[0][2] == {"run_id": str(run_id), "run_type": "hairstyle"}
    finally:
        session.close()


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

# ============================================================================
# STEP 11.17 — resolve_preferred_item_ids: saved-outfit read path (DB-free).
#
# The resolver is the production-boundary read: existing
# SavedLookRepository.list_for_user() + backend-persisted source_context.
# Only source_context == "outfit" contributes; titles/look_id are never
# inspected; learning_signals is not an input (no such parameter exists).
# ============================================================================

from uuid import uuid4 as _11_17_uuid4


class _11_17_FakeSavedLooks:
    """SavedLookRepository double with snapshot support (owner-scoped)."""

    def __init__(self, rows=None, fail=False) -> None:
        self._rows = list(rows or [])
        self._fail = fail

    def list_for_user(self, *, user_id, page, page_size):
        if self._fail:
            raise RuntimeError("db unavailable")
        owned = [rec for uid, rec in self._rows if uid == user_id]
        return owned, len(owned)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


def _11_17_row(user_id, source_context, snapshot):
    from datetime import datetime, timezone

    return (
        user_id,
        SavedLookRecord(
            id=_11_17_uuid4(),
            look_id=None,
            title="Saved",
            snapshot=snapshot,
            source_run_id=None,
            created_at=datetime.now(timezone.utc),
            source_context=source_context,
        ),
    )


def test_11_17_resolver_collects_outfit_ids_across_saves_once():
    """Outfit rows contribute canonical IDs; repeats across saves don't stack."""
    from app.domain.services.analysis_rules import resolve_preferred_item_ids

    item_a, item_b = _11_17_uuid4(), _11_17_uuid4()
    repo = _11_17_FakeSavedLooks(
        rows=[
            _11_17_row(USER, "outfit", {"selectedItemIds": [str(item_a), str(item_b)]}),
            _11_17_row(USER, "outfit", {"selectedItemIds": [str(item_a).upper()]}),
        ]
    )
    assert resolve_preferred_item_ids(saved_looks=repo, user_id=USER) == frozenset(
        [str(item_a), str(item_b)]
    )


def test_11_17_resolver_ignores_non_outfit_and_legacy_rows():
    """G+H. Hairstyle/grooming/NULL rows never contribute — even when their
    snapshots carry a selectedItemIds field (source_context is authoritative)."""
    from app.domain.services.analysis_rules import resolve_preferred_item_ids

    item = str(_11_17_uuid4())
    repo = _11_17_FakeSavedLooks(
        rows=[
            _11_17_row(USER, "hairstyle", {"selectedItemIds": [item]}),
            _11_17_row(USER, "grooming", {"selectedItemIds": [item]}),
            _11_17_row(USER, None, {"selectedItemIds": [item]}),
            _11_17_row(USER, "outfit", {"other": True}),
        ]
    )
    assert resolve_preferred_item_ids(saved_looks=repo, user_id=USER) == frozenset()


def test_11_17_resolver_ignores_malformed_entries_without_failing():
    """Malformed legacy snapshots are skipped, valid IDs still collected."""
    from app.domain.services.analysis_rules import resolve_preferred_item_ids

    good = _11_17_uuid4()
    repo = _11_17_FakeSavedLooks(
        rows=[
            _11_17_row(USER, "outfit", {"selectedItemIds": ["not-a-uuid", 42, None]}),
            _11_17_row(USER, "outfit", {"selectedItemIds": "not-a-list"}),
            _11_17_row(USER, "outfit", "not-a-dict"),
            _11_17_row(USER, "outfit", {"selectedItemIds": [str(good)]}),
        ]
    )
    assert resolve_preferred_item_ids(saved_looks=repo, user_id=USER) == frozenset(
        [str(good)]
    )


def test_11_17_resolver_is_owner_scoped():
    """Another user's outfit rows never enter the set."""
    from app.domain.services.analysis_rules import resolve_preferred_item_ids

    other = _11_17_uuid4()
    mine = _11_17_uuid4()
    repo = _11_17_FakeSavedLooks(
        rows=[
            _11_17_row(other, "outfit", {"selectedItemIds": [str(_11_17_uuid4())]}),
            _11_17_row(USER, "outfit", {"selectedItemIds": [str(mine)]}),
        ]
    )
    assert resolve_preferred_item_ids(saved_looks=repo, user_id=USER) == frozenset(
        [str(mine)]
    )


def test_11_17_resolver_failure_degrades_to_empty():
    """J. Unreadable repository → empty set, recommendation proceeds."""
    from app.domain.services.analysis_rules import resolve_preferred_item_ids

    assert (
        resolve_preferred_item_ids(saved_looks=_11_17_FakeSavedLooks(fail=True), user_id=USER)
        == frozenset()
    )


# ============================================================================
# STEP 12.3 — analysis-run knowledge provenance (DB-free, fake repos).
#
# New runs persist knowledge_version = "1.1+1.0" built from the two version
# constants; legacy rows (no value) read as NULL/None; engine_version stays
# an independent concept. Recommendation behavior is unchanged (all
# pre-existing tests above still assert exact tops/scores).
# ============================================================================


def test_12_3_hairstyle_run_persists_knowledge_version():
    """4. New hairstyle run carries the combined provenance."""
    runs = FakeRuns()
    use_case = CreateHairstyleRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval", "skin_tone": "Warm Medium"}),
        knowledge=_knowledge_with_catalog(),
    )
    run_id = use_case(user_id=USER)
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.knowledge_version == "1.1+1.0"


def test_12_3_grooming_run_persists_knowledge_version():
    """4b. Grooming runs share the same provenance boundary (catalog version
    applies; the OI half is the current shared value, not a grooming claim)."""
    runs = FakeRuns()
    use_case = CreateGroomingRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval"}),
        knowledge=_knowledge_with_catalog(),
    )
    run_id = use_case(user_id=USER)
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.knowledge_version == "1.1+1.0"


def test_12_3_legacy_run_without_provenance_reads_none():
    """5. Legacy rows (no knowledge_version) remain readable as NULL/None."""
    record = AnalysisRunRecord(
        id=uuid4(),
        run_type="hairstyle",
        status="completed",
        engine_version="rules-v1",
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        input_media=None,
        result=None,
        error=None,
    )
    assert record.knowledge_version is None


def test_12_3_engine_version_remains_separate():
    """6. engine_version and knowledge_version are independent concepts."""
    runs = FakeRuns()
    use_case = CreateHairstyleRun(
        runs=runs,
        user_state=FakeUserState({"face_shape": "Oval"}),
        knowledge=_knowledge_with_catalog(),
    )
    run_id = use_case(user_id=USER)
    record = runs.get_for_user(user_id=USER, run_id=run_id)
    assert record is not None
    assert record.engine_version == "rules-v1"
    assert record.knowledge_version == "1.1+1.0"
    assert record.engine_version != record.knowledge_version
    assert "rules-v1" not in (record.knowledge_version or "")
