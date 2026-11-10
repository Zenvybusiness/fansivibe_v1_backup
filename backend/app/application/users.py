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

        clean_settings = None
        if settings is not None:
            if not isinstance(settings, dict):
                errors.append(
                    {
                        "field": "settings",
                        "error": "must be a dictionary",
                    }
                )
            else:
                clean_settings = dict(settings)
                # Validate and sanitize location settings if present (P1-3)
                for loc_key in ("weather_location", "weatherLocation", "location"):
                    if loc_key in clean_settings:
                        loc_val = clean_settings[loc_key]
                        if loc_val is not None and not isinstance(loc_val, dict):
                            errors.append(
                                {
                                    "field": f"settings.{loc_key}",
                                    "error": "must be a dictionary",
                                }
                            )
                        elif isinstance(loc_val, dict):
                            sanitized_loc = dict(loc_val)
                            # Validate city if present
                            c_val = sanitized_loc.get("city")
                            if c_val is not None:
                                if not isinstance(c_val, str) or len(c_val) > 100:
                                    errors.append(
                                        {
                                            "field": f"settings.{loc_key}.city",
                                            "error": "must be a string up to 100 characters",
                                        }
                                    )
                                else:
                                    sanitized_loc["city"] = c_val.strip()

                            # Validate and enforce coarse resolution on lat/lon (~1.1km / 2 decimals)
                            lat_key = "latitude" if "latitude" in sanitized_loc else "lat"
                            lon_key = "longitude" if "longitude" in sanitized_loc else "lon"
                            if lat_key in sanitized_loc and sanitized_loc[lat_key] is not None:
                                lat_v = sanitized_loc[lat_key]
                                if not isinstance(lat_v, (int, float)) or isinstance(lat_v, bool):
                                    errors.append(
                                        {
                                            "field": f"settings.{loc_key}.{lat_key}",
                                            "error": "must be a numeric latitude",
                                        }
                                    )
                                elif not (-90.0 <= float(lat_v) <= 90.0):
                                    errors.append(
                                        {
                                            "field": f"settings.{loc_key}.{lat_key}",
                                            "error": "latitude must be between -90.0 and 90.0",
                                        }
                                    )
                                else:
                                    sanitized_loc[lat_key] = round(float(lat_v), 2)

                            if lon_key in sanitized_loc and sanitized_loc[lon_key] is not None:
                                lon_v = sanitized_loc[lon_key]
                                if not isinstance(lon_v, (int, float)) or isinstance(lon_v, bool):
                                    errors.append(
                                        {
                                            "field": f"settings.{loc_key}.{lon_key}",
                                            "error": "must be a numeric longitude",
                                        }
                                    )
                                elif not (-180.0 <= float(lon_v) <= 180.0):
                                    errors.append(
                                        {
                                            "field": f"settings.{loc_key}.{lon_key}",
                                            "error": "longitude must be between -180.0 and 180.0",
                                        }
                                    )
                                else:
                                    sanitized_loc[lon_key] = round(float(lon_v), 2)

                            clean_settings[loc_key] = sanitized_loc

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

        if clean_settings is not None:
            self._user_state.update_settings(
                user_id=user_id,
                settings=clean_settings,
            )

        record = self._user_state.get_profile(user_id=user_id)
        if record is None:
            raise not_found()
        return record
