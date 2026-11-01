"""Unit tests for the `GetProfile` use case (UC-6).

No database — uses a fake `UserStateRepository` keyed by `user_id`, mirroring
the owner-scoping (OW-1) the SQL adapter enforces.
"""

from __future__ import annotations

import pytest
from uuid import UUID, uuid4

from app.api.errors import ApiError
from app.application.users import GetProfile
from app.domain.ports.repositories import UserProfileRecord

A = uuid4()
B = uuid4()


class FakeUserState:
    def __init__(self, profiles: dict[UUID, UserProfileRecord]) -> None:
        self._profiles = profiles

    def get_style_profile(self, *, user_id: UUID) -> dict | None:
        record = self._profiles.get(user_id)
        return record.style_profile if record else None

    def get_profile(self, *, user_id: UUID) -> UserProfileRecord | None:
        return self._profiles.get(user_id)


def _record(user_id: UUID, display_name: str, style: dict) -> UserProfileRecord:
    return UserProfileRecord(
        user_id=user_id,
        display_name=display_name,
        style_profile=style,
        preferences={"preferred_occasions": ["smart_casual"]},
        settings={},
        flags={},
        version=1,
    )


def test_returns_the_requested_users_own_profile():
    use_case = GetProfile(user_state=FakeUserState({A: _record(A, "Alex", {"face_shape": "Oval"})}))
    record = use_case(user_id=A)
    assert record.display_name == "Alex"
    assert record.style_profile == {"face_shape": "Oval"}
    assert record.preferences == {"preferred_occasions": ["smart_casual"]}


def test_missing_profile_raises_not_found():
    use_case = GetProfile(user_state=FakeUserState({}))
    with pytest.raises(ApiError) as excinfo:
        use_case(user_id=A)
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "NOT_FOUND"


def test_read_is_owner_scoped():
    profiles = {
        A: _record(A, "Alex", {"face_shape": "Oval"}),
        B: _record(B, "Bea", {"face_shape": "Round"}),
    }
    use_case = GetProfile(user_state=FakeUserState(profiles))
    assert use_case(user_id=A).display_name == "Alex"
    assert use_case(user_id=B).display_name == "Bea"
    assert use_case(user_id=A).style_profile == {"face_shape": "Oval"}
    assert use_case(user_id=B).style_profile == {"face_shape": "Round"}


def test_empty_profile_returns_cleanly():
    """An empty or unassessed profile has empty style_profile and preserves version."""
    empty_record = UserProfileRecord(
        user_id=A,
        display_name="New User",
        style_profile={},
        preferences={},
        settings={},
        flags={},
        version=0,
    )
    use_case = GetProfile(user_state=FakeUserState({A: empty_record}))
    record = use_case(user_id=A)
    assert record.display_name == "New User"
    assert record.style_profile == {}
    assert record.version == 0


def test_profile_schema_serialization_and_legacy_compatibility():
    """ProfileView schema maps DB fields to wire camelCase and handles legacy profiles."""
    from app.api.routers.users import _record_to_schema

    # Full record with style_profile attributes and provenance
    full_record = UserProfileRecord(
        user_id=A,
        display_name="Alex Rivera",
        style_profile={
            "face_shape": "Oval",
            "skin_tone": "Warm Medium",
            "body_type": "Athletic",
            "style_type": "Modern Classic",
            "source_run_id": "run-456",
            "_provenance_face_shape": {
                "value": "Oval",
                "source": "vision_scan",
                "confidence": 0.88,
            },
        },
        preferences={"preferred_occasions": ["casual", "work"]},
        settings={},
        flags={},
        version=3,
    )

    view = _record_to_schema(full_record, saved_looks_count=2, preferred_occasions=["casual", "work"])
    assert view.displayName == "Alex Rivera"
    assert view.version == 3
    assert view.styleProfile.faceShape == "Oval"
    assert view.styleProfile.skinTone == "Warm Medium"
    assert view.styleProfile.bodyType == "Athletic"
    assert view.styleProfile.styleType == "Modern Classic"
    assert view.styleProfile.sourceRunId == "run-456"
    assert view.preferences == {"preferredOccasions": ["casual", "work"]}
    assert view.memorySummary["appearanceVerified"] is True
    assert view.memorySummary["savedLooksCount"] == 2
    assert view.memorySummary["appearanceConfidence"] == 1.0

    # Legacy record with only face_shape and no provenance
    legacy_record = UserProfileRecord(
        user_id=A,
        display_name="Legacy User",
        style_profile={"face_shape": "Round"},
        preferences={},
        settings={},
        flags={},
        version=1,
    )
    legacy_view = _record_to_schema(legacy_record)
    assert legacy_view.styleProfile.faceShape == "Round"
    assert legacy_view.styleProfile.skinTone is None
    assert legacy_view.styleProfile.bodyType is None
    assert legacy_view.styleProfile.styleType is None
    assert legacy_view.memorySummary["appearanceVerified"] is False
    assert legacy_view.memorySummary["appearanceConfidence"] == 0.25
