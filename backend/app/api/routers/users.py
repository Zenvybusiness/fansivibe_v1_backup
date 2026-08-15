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


def _completeness(style_profile: dict[str, Any]) -> float:
    keys = ["face_shape", "skin_tone", "body_type", "style_type"]
    present = sum(1 for k in keys if style_profile.get(k) not in (None, ""))
    return present / len(keys)


def _record_to_schema(record: UserProfileRecord, *, saved_looks_count: int = 0, preferred_occasions: list[str] | None = None) -> ProfileView:
    style_profile = record.style_profile or {}
    preferences = record.preferences or {}

    memory_summary: dict[str, Any] = {
        "appearanceVerified": all(
            style_profile.get(k) not in (None, "") for k in
            ["face_shape", "skin_tone", "body_type", "style_type"]
        ),
        "savedLooksCount": saved_looks_count,
        "preferredOccasions": preferred_occasions or _preferred_occasions_from_db(preferences),
        "appearanceConfidence": _completeness(style_profile),
    }

    return ProfileView(
        displayName=record.display_name,
        styleProfile=_to_style_profile(record.style_profile),
        preferences=_to_preferences(record.preferences),
        settings=record.settings,
        flags=record.flags,
        version=record.version,
        memorySummary=memory_summary,
    )


def _preferred_occasions_from_db(preferences: dict[str, Any]) -> list[str]:
    raw = preferences.get("preferred_occasions")
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [str(raw)]


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

    # Compute saved looks count from the database
    from sqlalchemy import select, func
    from app.infrastructure.db.models import SavedLooks
    saved_looks_count = 0
    try:
        count = db.execute(
            select(func.count()).select_from(SavedLooks).where(SavedLooks.user_id == user_id)
        ).scalar_one()
        saved_looks_count = int(count) if count is not None else 0
    except Exception:
        saved_looks_count = 0

    # Extract preferred occasions from preferences
    preferred_occasions = _preferred_occasions_from_db(record.preferences or {})

    return _record_to_schema(
        record,
        saved_looks_count=saved_looks_count,
        preferred_occasions=preferred_occasions,
    )