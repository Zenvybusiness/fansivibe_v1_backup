"""Users API router — endpoint #06 (`GET /v1/users/me`).

Owner-only read of the caller's own profile (OW-1, 404-not-403) per
`AUTH_API.md` §5.5. The response is always the authenticated user's own
identity; a valid token whose profile projection is gone → 404.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.api.schemas.users import ProfileView, StyleProfile
from app.application.users import GetProfile
from app.domain.ports.repositories import UserProfileRecord
from app.infrastructure.db.repositories import UserStateRepositorySQL
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/v1/users", tags=["users"])

_STYLE_PROFILE_KEYS = {
    "face_shape": "faceShape",
    "skin_tone": "skinTone",
    "body_type": "bodyType",
    "style_type": "styleType",
    "source_run_id": "sourceRunId",
}


def _to_style_profile(style: dict[str, Any]) -> StyleProfile:
    mapped = {
        wire: style[db_key]
        for db_key, wire in _STYLE_PROFILE_KEYS.items()
        if style.get(db_key) is not None
    }
    return StyleProfile(**mapped)


def _to_preferences(preferences: dict[str, Any]) -> dict[str, Any]:
    """Map the stored snake_case key to the contract's camelCase wire key."""
    return {
        "preferredOccasions" if key == "preferred_occasions" else key: value
        for key, value in preferences.items()
    }


def _record_to_schema(record: UserProfileRecord) -> ProfileView:
    return ProfileView(
        displayName=record.display_name,
        styleProfile=_to_style_profile(record.style_profile),
        preferences=_to_preferences(record.preferences),
        settings=record.settings,
        flags=record.flags,
        version=record.version,
    )


@router.get(
    "/me",
    response_model=ProfileView,
    responses={401: {"model": dict}, 404: {"model": dict}},
)
def get_me(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProfileView:
    """Return the authenticated user's profile (`ProfileView`, bare)."""
    use_case = GetProfile(user_state=UserStateRepositorySQL(db))
    record = use_case(user_id=user_id)
    return _record_to_schema(record)
