"""Ephemeral in-memory user state repository adapter for guest outfit recommendations.

Preserves the canonical GenerateOutfit use case and UserStateRepository
protocol for guest users without database access, without persisted identity,
and without fabricating appearance attributes (TRX-4, C-01, D10).
"""

from __future__ import annotations

from typing import Any, Optional, Sequence
from uuid import UUID

from app.domain.ports.repositories import (
    UserProfileRecord,
    UserStateRepository,
)

_GUEST_SENTINEL_USER_ID = UUID("00000000-0000-0000-0000-000000000000")

# Appearance keys that MUST NOT be accepted or fabricated for guests (D10 / Requirement 7)
_APPEARANCE_KEYS = frozenset(
    {"face_shape", "skin_tone", "body_type", "style_type", "style_profile", "appearance"}
)


class EphemeralUserStateRepository:
    """In-memory UserStateRepository adapter for guest recommendations.

    Supplies guest preferences (such as preferred occasions) to GenerateOutfit
    without querying or writing to PostgreSQL, and strictly excludes guest
    appearance data (Decision D10 Option A).
    """

    def __init__(
        self,
        preferred_occasions: Optional[Sequence[str]] = None,
        preferences: Optional[dict[str, Any]] = None,
        settings: Optional[dict[str, Any]] = None,
        *,
        user_id: Optional[UUID] = None,
    ) -> None:
        self._user_id = user_id
        occasions: list[str] = []
        if preferred_occasions:
            occasions.extend(
                str(o).strip().lower()
                for o in preferred_occasions
                if isinstance(o, str) and o.strip()
            )

        merged_prefs: dict[str, Any] = {}
        if preferences and isinstance(preferences, dict):
            for k, v in preferences.items():
                if k in _APPEARANCE_KEYS:
                    continue
                if k == "preferred_occasions" and isinstance(v, (list, tuple)):
                    for o in v:
                        if isinstance(o, str) and o.strip():
                            clean_o = o.strip().lower()
                            if clean_o not in occasions:
                                occasions.append(clean_o)
                else:
                    merged_prefs[k] = v

        merged_prefs["preferred_occasions"] = occasions
        self._preferences = merged_prefs
        self._preferred_occasions = occasions
        self._settings: dict[str, Any] = dict(settings or {})

    def get_profile(
        self, *, user_id: Optional[UUID] = None
    ) -> Optional[UserProfileRecord]:
        """Return the guest UserProfileRecord with empty appearance and valid preferences."""
        resolved_id = user_id or self._user_id or _GUEST_SENTINEL_USER_ID
        return UserProfileRecord(
            user_id=resolved_id,
            display_name="Guest",
            style_profile={},  # Zero appearance fabrication (D10 / Requirement 7)
            preferences=dict(self._preferences),
            settings=dict(self._settings),
            flags={},
            version=1,
        )

    def update_settings(
        self, *, user_id: Optional[UUID] = None, settings: dict
    ) -> None:
        """In-memory settings update for guests without DB writes."""
        if not isinstance(settings, dict):
            return
        self._settings.update(settings)

    def get_style_profile(
        self, *, user_id: Optional[UUID] = None
    ) -> Optional[dict]:
        """Always returns an empty dict for guests — zero appearance fabrication."""
        return {}

    def update_preferences(
        self, *, user_id: Optional[UUID] = None, preferences: dict
    ) -> None:
        """In-memory preference update without DB writes."""
        if not isinstance(preferences, dict):
            return
        for k, v in preferences.items():
            if k in _APPEARANCE_KEYS:
                continue
            if k == "preferred_occasions" and isinstance(v, (list, tuple)):
                self._preferred_occasions = [
                    str(o).strip().lower()
                    for o in v
                    if isinstance(o, str) and o.strip()
                ]
                self._preferences["preferred_occasions"] = list(self._preferred_occasions)
            else:
                self._preferences[k] = v

    def update_style_profile(
        self,
        *,
        user_id: Optional[UUID] = None,
        face_shape: Optional[str] = None,
        skin_tone: Optional[str] = None,
        body_type: Optional[str] = None,
        style_type: Optional[str] = None,
        source_run_id: Optional[str] = None,
        confidence: Optional[float] = None,
        confirmed_by_user: bool = False,
        source: Optional[str] = None,
        expected_version: Optional[int] = None,
        max_retries: int = 0,
    ) -> bool:
        """No-op; guest appearance data is NEVER persisted (D10 / Requirement 8)."""
        return False

    def get_attribute_provenance(
        self, style_profile: dict[str, Any], attribute: str
    ) -> Optional[dict[str, Any]]:
        return None
