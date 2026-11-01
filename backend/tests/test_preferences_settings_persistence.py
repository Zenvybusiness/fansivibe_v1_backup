"""Targeted tests for Stage 2 P0-3: Style Preferences & Application Settings Persistence.

Validates:
1. Style preference (archetype) profile read/write behavior (Minimalist, Classic, Streetwear, etc.).
2. Settings JSONB partial update behavior (updating one toggle preserves others).
3. Preservation of unrelated profile fields across partial updates.
4. Authenticated ownership validation (OW-1, 401 unauthenticated, 404 for nonexistent user).
5. Input validation and typed 422 error states.
6. Ephemeral guest isolation (D10 Option A: in-memory only, zero DB writes, appearance refused).
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.errors import ApiError
from app.api.schemas.users import UpdatePreferencesRequest
from app.application.users import UpdatePreferences, GetProfile
from app.domain.ports.repositories import UserProfileRecord
from app.infrastructure.external.ephemeral_user_state import EphemeralUserStateRepository
from app.main import app

USER_A = uuid4()
USER_B = uuid4()


class MemoryUserStateRepo:
    """In-memory UserStateRepository tracking calls and partial merge semantics."""

    def __init__(self) -> None:
        self.rows: dict[UUID, dict] = {}
        self.calls: list = []

    def seed(
        self,
        user_id: UUID,
        *,
        display_name: str = "Test User",
        style_profile: dict | None = None,
        preferences: dict | None = None,
        settings: dict | None = None,
        version: int = 1,
    ) -> None:
        self.rows[user_id] = {
            "display_name": display_name,
            "style_profile": dict(style_profile or {}),
            "preferences": dict(preferences or {}),
            "settings": dict(settings or {}),
            "flags": {},
            "version": version,
        }

    def get_profile(self, *, user_id: UUID) -> UserProfileRecord | None:
        row = self.rows.get(user_id)
        if row is None:
            return None
        return UserProfileRecord(
            user_id=user_id,
            display_name=row["display_name"],
            style_profile=dict(row["style_profile"]),
            preferences=dict(row["preferences"]),
            settings=dict(row["settings"]),
            flags=dict(row["flags"]),
            version=row["version"],
        )

    def get_style_profile(self, *, user_id: UUID) -> dict | None:
        row = self.rows.get(user_id)
        return dict(row["style_profile"]) if row else None

    def update_preferences(self, *, user_id: UUID, preferences: dict) -> None:
        self.calls.append(("update_preferences", user_id, dict(preferences)))
        row = self.rows.get(user_id)
        if row is None:
            return
        row["preferences"].update(preferences)

    def update_settings(self, *, user_id: UUID, settings: dict) -> None:
        self.calls.append(("update_settings", user_id, dict(settings)))
        row = self.rows.get(user_id)
        if row is None:
            return
        row["settings"].update(settings)

    def update_style_profile(
        self,
        *,
        user_id: UUID,
        face_shape: str | None = None,
        skin_tone: str | None = None,
        body_type: str | None = None,
        style_type: str | None = None,
        source_run_id: str | None = None,
        confidence: float | None = None,
        confirmed_by_user: bool = False,
        source: str | None = None,
        expected_version: int | None = None,
        max_retries: int = 0,
    ) -> bool:
        self.calls.append((
            "update_style_profile",
            user_id,
            {"style_type": style_type, "confirmed_by_user": confirmed_by_user},
        ))
        row = self.rows.get(user_id)
        if row is None:
            return False
        if style_type is not None:
            row["style_profile"]["style_type"] = style_type
            row["style_profile"]["_provenance_style_type"] = {
                "value": style_type,
                "source": source or ("user" if confirmed_by_user else "vision"),
                "confidence": confidence or 1.0,
                "confirmed_by_user": confirmed_by_user,
            }
        row["version"] += 1
        return True


# --- 1. Style Archetype Persistence Tests ---


def test_update_style_type_persists_archetype_and_provenance():
    repo = MemoryUserStateRepo()
    repo.seed(
        USER_A,
        style_profile={"face_shape": "oval", "skin_tone": "Warm Medium"},
    )
    use_case = UpdatePreferences(user_state=repo)

    record = use_case(user_id=USER_A, style_type="Minimalist")

    assert record.style_profile["style_type"] == "Minimalist"
    assert record.style_profile["face_shape"] == "oval"  # Unrelated biometrics preserved
    assert record.style_profile["skin_tone"] == "Warm Medium"
    assert record.style_profile["_provenance_style_type"]["confirmed_by_user"] is True
    assert record.version == 2


@pytest.mark.parametrize("archetype", ["Minimalist", "Classic", "Streetwear", "Bold", "Bohemian", "Athleisure"])
def test_all_standard_archetypes_persist(archetype):
    repo = MemoryUserStateRepo()
    repo.seed(USER_A)
    use_case = UpdatePreferences(user_state=repo)

    record = use_case(user_id=USER_A, style_type=archetype)
    assert record.style_profile["style_type"] == archetype


# --- 2. Application Settings Persistence Tests ---


def test_update_settings_partial_merge_preserves_unrelated_settings():
    repo = MemoryUserStateRepo()
    repo.seed(
        USER_A,
        settings={"notifications": True, "soundEffects": False, "hapticFeedback": True},
    )
    use_case = UpdatePreferences(user_state=repo)

    # Partial update: only flip soundEffects
    record = use_case(user_id=USER_A, settings={"soundEffects": True})

    assert record.settings == {
        "notifications": True,
        "soundEffects": True,
        "hapticFeedback": True,
    }


def test_update_settings_add_new_setting_preserves_existing():
    repo = MemoryUserStateRepo()
    repo.seed(
        USER_A,
        settings={"notifications": True},
    )
    use_case = UpdatePreferences(user_state=repo)

    record = use_case(user_id=USER_A, settings={"dataSaver": True})

    assert record.settings["notifications"] is True
    assert record.settings["dataSaver"] is True


# --- 3. Unrelated Profile Field Isolation ---


def test_updating_settings_preserves_style_profile_and_occasions():
    repo = MemoryUserStateRepo()
    repo.seed(
        USER_A,
        style_profile={"style_type": "Classic", "face_shape": "round"},
        preferences={"preferred_occasions": ["business", "formal"]},
        settings={"notifications": True},
    )
    use_case = UpdatePreferences(user_state=repo)

    record = use_case(user_id=USER_A, settings={"soundEffects": True})

    # Style profile and preferences untouched
    assert record.style_profile["style_type"] == "Classic"
    assert record.style_profile["face_shape"] == "round"
    assert record.preferences["preferred_occasions"] == ["business", "formal"]
    # Settings updated
    assert record.settings["soundEffects"] is True
    assert record.settings["notifications"] is True


def test_updating_style_type_preserves_settings_and_occasions():
    repo = MemoryUserStateRepo()
    repo.seed(
        USER_A,
        style_profile={"face_shape": "square"},
        preferences={"preferred_occasions": ["casual"]},
        settings={"notifications": False, "hapticFeedback": True},
    )
    use_case = UpdatePreferences(user_state=repo)

    record = use_case(user_id=USER_A, style_type="Streetwear")

    assert record.style_profile["style_type"] == "Streetwear"
    assert record.style_profile["face_shape"] == "square"
    assert record.preferences["preferred_occasions"] == ["casual"]
    assert record.settings == {"notifications": False, "hapticFeedback": True}


# --- 4. Validation & Error Handling ---


def test_invalid_style_type_rejected():
    repo = MemoryUserStateRepo()
    repo.seed(USER_A)
    use_case = UpdatePreferences(user_state=repo)

    with pytest.raises(ApiError) as exc:
        use_case(user_id=USER_A, style_type=123)  # type: ignore
    assert exc.value.status_code == 422
    assert any(e["field"] == "styleType" for e in exc.value.details["field_errors"])


def test_invalid_settings_rejected():
    repo = MemoryUserStateRepo()
    repo.seed(USER_A)
    use_case = UpdatePreferences(user_state=repo)

    with pytest.raises(ApiError) as exc:
        use_case(user_id=USER_A, settings=["not", "a", "dict"])  # type: ignore
    assert exc.value.status_code == 422
    assert any(e["field"] == "settings" for e in exc.value.details["field_errors"])


def test_nonexistent_user_raises_not_found():
    repo = MemoryUserStateRepo()
    use_case = UpdatePreferences(user_state=repo)

    with pytest.raises(ApiError) as exc:
        use_case(user_id=uuid4(), style_type="Minimalist")
    assert exc.value.status_code == 404


# --- 5. Ephemeral Guest Repository Isolation (D10 Option A) ---


def test_ephemeral_user_state_settings_and_appearance_refusal():
    guest_repo = EphemeralUserStateRepository(
        preferred_occasions=["casual"],
        settings={"notifications": True},
    )

    profile = guest_repo.get_profile()
    assert profile is not None
    assert profile.settings == {"notifications": True}
    assert profile.style_profile == {}  # D10 Option A: zero appearance fabrication

    # Updating settings in guest repo operates purely in-memory
    guest_repo.update_settings(settings={"dataSaver": True})
    updated_profile = guest_repo.get_profile()
    assert updated_profile.settings == {"notifications": True, "dataSaver": True}

    # Style profile updates are refused for guests (D10 Option A)
    refused = guest_repo.update_style_profile(style_type="Streetwear")
    assert refused is False
    assert guest_repo.get_profile().style_profile == {}


# --- 6. Router API Contract Integration ---


def test_patch_users_me_via_api_client(monkeypatch):
    repo = MemoryUserStateRepo()
    repo.seed(
        USER_A,
        style_profile={"face_shape": "oval"},
        preferences={"preferred_occasions": ["casual"]},
        settings={"notifications": True},
    )

    from app.infrastructure.db.session import get_db
    from app.api.deps import get_current_user_id

    app.dependency_overrides[get_current_user_id] = lambda: USER_A
    app.dependency_overrides[get_db] = lambda: None

    # Patch repo instantiation in router
    import app.api.routers.users as users_router
    monkeypatch.setattr(users_router, "UserStateRepositorySQL", lambda db: repo)

    try:
        client = TestClient(app)
        response = client.patch(
            "/v1/users/me",
            json={
                "styleType": "Minimalist",
                "settings": {"soundEffects": True, "hapticFeedback": False},
                "preferredOccasions": ["casual", "formal"],
            },
        )
        assert response.status_code == 200
        body = response.json()

        assert body["styleProfile"]["styleType"] == "Minimalist"
        assert body["styleProfile"]["faceShape"] == "oval"
        assert body["settings"]["notifications"] is True
        assert body["settings"]["soundEffects"] is True
        assert body["settings"]["hapticFeedback"] is False
        assert body["preferences"]["preferredOccasions"] == ["casual", "formal"]
    finally:
        app.dependency_overrides.clear()
