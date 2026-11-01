"""Application use cases — user/profile surface (M2, UC-6).

Each use case is a thin orchestration unit that composes the repository ports
and raises typed `ApiError`s on failure. Business rules live here, not in the
routers (BA-7).
"""

from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from app.api.errors import not_found, validation
from app.domain.ports.repositories import UserProfileRecord, UserStateRepository


class GetProfile:
    """UC-6 — `GET /v1/users/me`.

    Returns the caller's own profile projection (owner-only, OW-1). A valid
    token whose account/profile projection is gone resolves to `404` per
    `AUTH_API.md` §5.5 — never an existence oracle on another user.
    """

    def __init__(self, *, user_state: UserStateRepository) -> None:
        self._user_state = user_state

    def __call__(self, *, user_id: UUID) -> UserProfileRecord:
        record = self._user_state.get_profile(user_id=user_id)
        if record is None:
            raise not_found()
        return record


_UNSET = object()


class UpdatePreferences:
    """PATCH /v1/users/me — persist preferred occasions, style archetype, and settings.

    Validates provided fields, merges via repository ports (sibling keys preserved,
    owner-scoped), and returns the fresh profile projection — the same established
    pattern as `GetProfile` (the router renders the `ProfileView`). A missing profile
    projection resolves to `404`, mirroring `GET /me`.
    """

    def __init__(self, *, user_state: UserStateRepository) -> None:
        self._user_state = user_state

    def __call__(
        self,
        *,
        user_id: UUID,
        preferred_occasions: Any = _UNSET,
        style_type: Optional[str] = None,
        settings: Optional[dict] = None,
    ) -> UserProfileRecord:
        errors = []
        if preferred_occasions is not _UNSET:
            if not isinstance(preferred_occasions, list) or any(
                not isinstance(item, str) for item in preferred_occasions
            ):
                errors.append(
                    {
                        "field": "preferredOccasions",
                        "error": "must be a list of strings",
                    }
                )

        if style_type is not None:
            if not isinstance(style_type, str):
                errors.append(
                    {
                        "field": "styleType",
                        "error": "must be a string",
                    }
                )

        if settings is not None:
            if not isinstance(settings, dict):
                errors.append(
                    {
                        "field": "settings",
                        "error": "must be a dictionary",
                    }
                )

        if errors:
            raise validation(errors)

        if preferred_occasions is not _UNSET:
            self._user_state.update_preferences(
                user_id=user_id,
                preferences={"preferred_occasions": list(preferred_occasions)},
            )

        if style_type is not None:
            clean_style = style_type.strip()
            if clean_style:
                self._user_state.update_style_profile(
                    user_id=user_id,
                    style_type=clean_style,
                    confirmed_by_user=True,
                    source="user",
                    confidence=1.0,
                )

        if settings is not None:
            self._user_state.update_settings(
                user_id=user_id,
                settings=settings,
            )

        record = self._user_state.get_profile(user_id=user_id)
        if record is None:
            raise not_found()
        return record
