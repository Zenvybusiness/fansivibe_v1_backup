"""Unit tests for the hairstyle analysis use case (UC-25/26).

No database — fake repositories. Covers the contract's failure semantics
(HAIRSTYLE_RECOMMENDATION_API.md §5.1/§7): a pipeline failure marks the run
``failed`` with ``PROCESSING_FAILURE`` + ``details.run_id`` instead of leaving
it stuck in ``pending``; insufficient profile data is a typed 422.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest

from app.api.errors import ApiError
from app.application.analysis import CreateHairstyleRun
from app.domain.ports.repositories import AnalysisRunRecord

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
