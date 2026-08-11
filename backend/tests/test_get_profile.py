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
