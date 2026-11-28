"""Application use cases — user/profile surface (M2, UC-6).

Each use case is a thin orchestration unit that composes the repository ports
and raises typed `ApiError`s on failure. Business rules live here, not in the
routers (BA-7).
"""

from __future__ import annotations

from datetime import datetime, timezone
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


class _Unset:
    pass


UNSET = _Unset()
_UNSET = UNSET

STYLE_PROFILE_KEYS = {
    "faceShape": "face_shape",
    "skinTone": "skin_tone",
    "bodyType": "body_type",
    "hairType": "hair_type",
    "hairDensity": "hair_density",
    "styleType": "style_type",
}
STYLE_PROFILE_ALIASES = {snake: snake for snake in STYLE_PROFILE_KEYS.values()}
PREFERENCE_KEYS = {
    "preferredOccasions": "preferred_occasions",
    "appearanceGoals": "appearance_goals",
    "dislikes": "dislikes",
    "maintenancePreference": "maintenance_preference",
    "maxBudget": "max_budget",
}
PREFERENCE_ALIASES = {snake: snake for snake in PREFERENCE_KEYS.values()}

_CHOICES = {
    "face_shape": {"oval", "round", "square", "heart", "diamond", "rectangular"},
    "skin_tone": {f"{prefix}{index:02d}" for prefix in ("w", "c") for index in range(6)},
    "body_type": {"slim", "average", "curvy", "plus"},
    "hair_type": {"straight", "wavy", "curly", "coily"},
    "hair_density": {"sparse", "medium", "dense"},
    "maintenance_preference": {"low", "medium", "high"},
}
_ALIASES = {
    "face_shape": {"rectangle": "rectangular"},
    "skin_tone": {},
    "body_type": {},
    "hair_type": {},
    "hair_density": {},
    "maintenance_preference": {},
}
_TEXT_LIMITS = {"appearance_goals": 500, "dislikes": 500}


def _choice(field: str, value: Any, errors: list[dict[str, str]]) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append({"field": field, "error": "must be a supported value"})
        return None
    normalized = _ALIASES[field].get(
        value.strip().lower().replace(" ", "_").replace("-", "_"),
        value.strip().lower().replace(" ", "_").replace("-", "_"),
    )
    if normalized not in _CHOICES[field]:
        errors.append({"field": field, "error": "must be a supported value"})
        return None
    return normalized


def _text(field: str, value: Any, errors: list[dict[str, str]]) -> Any:
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append({"field": field, "error": "must be a string"})
        return None
    clean = value.strip()
    if len(clean) > _TEXT_LIMITS[field]:
        errors.append(
            {"field": field, "error": f"must be at most {_TEXT_LIMITS[field]} characters"}
        )
        return None
    return clean or None


def _budget(value: Any, errors: list[dict[str, str]]) -> Any:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append({"field": "maxBudget", "error": "must be a number"})
        return None
    if value < 0 or value > 1_000_000:
        errors.append({"field": "maxBudget", "error": "must be between 0 and 1000000"})
        return None
    return float(value)


class UpdatePreferences:
    """PATCH /v1/users/me — validate and persist sparse profile patches.

    Omitted fields remain untouched. A field explicitly supplied as null is
    cleared. Style-profile fields, preferences, and settings merge without
    replacing sibling keys; the SQL adapter applies all three in one
    owner-scoped update.
    """

    def __init__(self, *, user_state: UserStateRepository) -> None:
        self._user_state = user_state

    def __call__(
        self,
        *,
        user_id: UUID,
        preferred_occasions: Any = UNSET,
        style_type: Any = UNSET,
        style_profile: Any = UNSET,
        appearance_goals: Any = UNSET,
        dislikes: Any = UNSET,
        maintenance_preference: Any = UNSET,
        max_budget: Any = UNSET,
        settings: Any = UNSET,
    ) -> UserProfileRecord:
        errors: list[dict[str, str]] = []
        style_patch: dict[str, Any] = {}
        style_clear: set[str] = set()
        preferences_patch: dict[str, Any] = {}
        preferences_clear: set[str] = set()
        settings_patch: dict[str, Any] = {}
        clear_settings = False

        def apply_style(field: str, value: Any, wire: str) -> None:
            if field == "style_type":
                if value is None:
                    style_clear.add(field)
                elif not isinstance(value, str):
                    errors.append({"field": wire, "error": "must be a string"})
                else:
                    clean = value.strip()
                    if clean:
                        style_patch[field] = clean
                    else:
                        style_clear.add(field)
                return
            cleaned = _choice(field, value, errors)
            if cleaned is None:
                style_clear.add(field)
            else:
                style_patch[field] = cleaned

        if preferred_occasions is not UNSET:
            if preferred_occasions is None:
                preferences_patch["preferred_occasions"] = []
            elif not isinstance(preferred_occasions, list) or any(
                not isinstance(item, str) for item in preferred_occasions
            ):
                errors.append(
                    {
                        "field": "preferredOccasions",
                        "error": "must be a list of strings",
                    }
                )
            else:
                preferences_patch["preferred_occasions"] = list(preferred_occasions)

        if style_type is not UNSET:
            apply_style("style_type", style_type, "styleType")

        if style_profile is not UNSET:
            if not isinstance(style_profile, dict):
                errors.append(
                    {"field": "styleProfile", "error": "must be a dictionary"}
                )
            else:
                for wire, value in style_profile.items():
                    if wire == "sourceRunId" or wire == "source_run_id":
                        continue
                    field = STYLE_PROFILE_KEYS.get(wire) or STYLE_PROFILE_ALIASES.get(wire)
                    if field is not None:
                        apply_style(field, value, wire)

        if appearance_goals is not UNSET:
            cleaned = _text("appearance_goals", appearance_goals, errors)
            if cleaned is None:
                preferences_clear.add("appearance_goals")
            else:
                preferences_patch["appearance_goals"] = cleaned

        if dislikes is not UNSET:
            cleaned = _text("dislikes", dislikes, errors)
            if cleaned is None:
                preferences_clear.add("dislikes")
            else:
                preferences_patch["dislikes"] = cleaned

        if maintenance_preference is not UNSET:
            cleaned = _choice("maintenance_preference", maintenance_preference, errors)
            if cleaned is None:
                preferences_clear.add("maintenance_preference")
            else:
                preferences_patch["maintenance_preference"] = cleaned

        if max_budget is not UNSET:
            cleaned = _budget(max_budget, errors)
            if cleaned is None:
                preferences_clear.add("max_budget")
            else:
                preferences_patch["max_budget"] = cleaned

        if settings is not UNSET:
            if settings is None:
                clear_settings = True
            elif not isinstance(settings, dict):
                errors.append(
                    {
                        "field": "settings",
                        "error": "must be a dictionary",
                    }
                )
            else:
                settings_patch = dict(settings)
                if "timezone" in settings_patch:
                    tz_val = settings_patch["timezone"]
                    if tz_val is not None:
                        if not isinstance(tz_val, str) or not tz_val.strip():
                            errors.append(
                                {
                                    "field": "settings.timezone",
                                    "error": "must be a valid IANA timezone name",
                                }
                            )
                        else:
                            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

                            try:
                                ZoneInfo(tz_val.strip())
                                settings_patch["timezone"] = tz_val.strip()
                            except (ZoneInfoNotFoundError, KeyError, ValueError):
                                errors.append(
                                    {
                                        "field": "settings.timezone",
                                        "error": "must be a valid IANA timezone name",
                                    }
                                )
                for loc_key in ("weather_location", "weatherLocation", "location"):
                    if loc_key in settings_patch:
                        loc_val = settings_patch[loc_key]
                        if loc_val is not None and not isinstance(loc_val, dict):
                            errors.append(
                                {
                                    "field": f"settings.{loc_key}",
                                    "error": "must be a dictionary",
                                }
                            )
                        elif isinstance(loc_val, dict):
                            sanitized_loc = dict(loc_val)
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
                            lat_key = (
                                "latitude" if "latitude" in sanitized_loc else "lat"
                            )
                            lon_key = (
                                "longitude" if "longitude" in sanitized_loc else "lon"
                            )
                            for key, low, high in (
                                (lat_key, -90.0, 90.0),
                                (lon_key, -180.0, 180.0),
                            ):
                                if key not in sanitized_loc or sanitized_loc[key] is None:
                                    continue
                                coord = sanitized_loc[key]
                                if (
                                    not isinstance(coord, (int, float))
                                    or isinstance(coord, bool)
                                ):
                                    errors.append(
                                        {
                                            "field": f"settings.{loc_key}.{key}",
                                            "error": "must be a numeric coordinate",
                                        }
                                    )
                                elif not (low <= float(coord) <= high):
                                    errors.append(
                                        {
                                            "field": f"settings.{loc_key}.{key}",
                                            "error": f"must be between {low} and {high}",
                                        }
                                    )
                                else:
                                    sanitized_loc[key] = round(float(coord), 2)
                            settings_patch[loc_key] = sanitized_loc

        if errors:
            raise validation(errors)

        now_iso = datetime.now(timezone.utc).isoformat()
        for field in list(style_clear):
            style_patch.pop(field, None)
            style_patch.pop(f"_provenance_{field}", None)
            style_patch[field] = None
            style_patch[f"_provenance_{field}"] = None
        for field, value in list(style_patch.items()):
            if field.startswith("_provenance_") or value is None:
                continue
            style_patch[f"_provenance_{field}"] = {
                "value": value,
                "source": "user",
                "source_run_id": None,
                "confidence": 1.0,
                "observed_at": now_iso,
                "confirmed_by_user": True,
                "confirmed_at": now_iso,
            }
        for field in preferences_clear:
            preferences_patch.pop(field, None)
            preferences_patch[field] = None
        if clear_settings:
            settings_patch = {"__clear__": True}

        atomic_update = getattr(self._user_state, "update_profile", None)
        if callable(atomic_update):
            updated = atomic_update(
                user_id=user_id,
                style_profile=style_patch,
                preferences=preferences_patch,
                settings=settings_patch,
            )
            if not updated:
                raise not_found()
        else:
            self._legacy_write(
                user_id=user_id,
                style_patch=style_patch,
                preferences_patch=preferences_patch,
                settings_patch=settings_patch,
            )

        record = self._user_state.get_profile(user_id=user_id)
        if record is None:
            raise not_found()
        return record

    def _legacy_write(
        self,
        *,
        user_id: UUID,
        style_patch: dict[str, Any],
        preferences_patch: dict[str, Any],
        settings_patch: dict[str, Any],
    ) -> None:
        style_fields = {
            "face_shape",
            "skin_tone",
            "body_type",
            "hair_type",
            "hair_density",
            "style_type",
        }
        for field in style_fields:
            value = style_patch.get(field)
            if value is None or field != "style_type":
                continue
            self._user_state.update_style_profile(
                user_id=user_id,
                style_type=value,
                confirmed_by_user=True,
                source="user",
                confidence=1.0,
            )
        if preferences_patch:
            self._user_state.update_preferences(
                user_id=user_id, preferences=preferences_patch
            )
        if settings_patch and settings_patch != {"__clear__": True}:
            self._user_state.update_settings(user_id=user_id, settings=settings_patch)
