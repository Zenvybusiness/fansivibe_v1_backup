"""Focused tests for STEP 11.6 preference persistence (`PATCH /v1/users/me`).

DB-free by default: a fake `UserStateRepository` (owner-scoped, merge
semantics mirroring the SQL `||`), a recording session proving the real SQL
statement concatenates (not replaces) under an owner-scoped predicate, and
`TestClient` router tests with patched deps. The DB-backed section runs when
PostgreSQL is reachable and skips otherwise (see `tests/conftest.py`) — the
real `||` merge is never faked there.

No assistant, scoring, TRX-6, or Flutter behavior is covered here beyond
asserting it is untouched.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.api.errors import ApiError
from app.application.users import UpdatePreferences
from app.domain.ports.repositories import UserProfileRecord

A = uuid4()
B = uuid4()


class FakeUserState:
    """In-memory UserStateRepository: owner-keyed rows, `|` merge on write
    (mirrors SQL `||`), no-op update on a missing row (mirrors zero-row
    UPDATE match). Records every call for the TRX-6 isolation check."""

    def __init__(self) -> None:
        self._rows: dict[UUID, dict] = {}
        self.calls: list = []

    def seed(
        self,
        user_id: UUID,
        *,
        display_name: str = "Alex",
        style_profile: dict | None = None,
        preferences: dict | None = None,
    ) -> None:
        self._rows[user_id] = {
            "display_name": display_name,
            "style_profile": dict(style_profile or {}),
            "preferences": dict(preferences or {}),
        }

    def get_style_profile(self, *, user_id: UUID) -> dict | None:
        row = self._rows.get(user_id)
        return dict(row["style_profile"]) if row else None

    def update_preferences(self, *, user_id: UUID, preferences: dict) -> None:
        self.calls.append(("update_preferences", user_id, dict(preferences)))
        row = self._rows.get(user_id)
        if row is None:
            return
        merged = dict(row["preferences"])
        merged.update(preferences)
        row["preferences"] = merged

    def update_style_profile(self, *args, **kwargs) -> None:  # pragma: no cover
        self.calls.append(("update_style_profile", args, kwargs))

    def get_profile(self, *, user_id: UUID) -> UserProfileRecord | None:
        row = self._rows.get(user_id)
        if row is None:
            return None
        return UserProfileRecord(
            user_id=user_id,
            display_name=row["display_name"],
            style_profile=dict(row["style_profile"]),
            preferences=dict(row["preferences"]),
            settings={},
            flags={},
            version=1,
        )


def _use_case(state: FakeUserState) -> UpdatePreferences:
    return UpdatePreferences(user_state=state)


# --- A/B/C: set / replace / clear -------------------------------------------


def test_set_preferred_occasions():
    """A. Setting occasions on empty preferences persists the list."""
    state = FakeUserState()
    state.seed(A)
    record = _use_case(state)(user_id=A, preferred_occasions=["smart_casual"])
    assert record.preferences == {"preferred_occasions": ["smart_casual"]}


def test_replace_existing_preferred_occasions():
    """B. A second write replaces the whole occasions list."""
    state = FakeUserState()
    state.seed(A, preferences={"preferred_occasions": ["business"]})
    record = _use_case(state)(user_id=A, preferred_occasions=["weekend", "date"])
    assert record.preferences == {"preferred_occasions": ["weekend", "date"]}


def test_empty_list_clears_preferred_occasions():
    """C. `[]` clears the preference (key present, empty)."""
    state = FakeUserState()
    state.seed(A, preferences={"preferred_occasions": ["business"]})
    record = _use_case(state)(user_id=A, preferred_occasions=[])
    assert record.preferences == {"preferred_occasions": []}


# --- D: merge preserves sibling keys -----------------------------------------


def test_merge_preserves_other_preference_keys():
    """D. Sibling keys survive the occasions patch."""
    state = FakeUserState()
    state.seed(
        A,
        preferences={
            "preferred_occasions": ["business"],
            "future_key": "preserve-me",
        },
    )
    record = _use_case(state)(user_id=A, preferred_occasions=["weekend"])
    assert record.preferences == {
        "preferred_occasions": ["weekend"],
        "future_key": "preserve-me",
    }


# --- E: owner scoping ----------------------------------------------------------


def test_update_is_owner_scoped():
    """E. User A cannot update user B's preferences; unknown user → 404."""
    state = FakeUserState()
    state.seed(A, preferences={"preferred_occasions": ["business"]})
    state.seed(B, preferences={"preferred_occasions": ["date"]})
    _use_case(state)(user_id=A, preferred_occasions=["weekend"])
    assert state.get_profile(user_id=A).preferences["preferred_occasions"] == [
        "weekend"
    ]
    assert state.get_profile(user_id=B).preferences["preferred_occasions"] == ["date"]

    with pytest.raises(ApiError) as excinfo:
        _use_case(state)(user_id=uuid4(), preferred_occasions=["weekend"])
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "NOT_FOUND"


# --- F: validation ---------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ["smart_casual", 123, None, ["date", 1], ["date", None], [b"date"]],
)
def test_invalid_preferred_occasions_rejected(bad):
    """F. Non-list or non-string members → typed 422, nothing written."""
    state = FakeUserState()
    state.seed(A, preferences={"preferred_occasions": ["business"]})
    with pytest.raises(ApiError) as excinfo:
        _use_case(state)(user_id=A, preferred_occasions=bad)
    assert excinfo.value.status_code == 422
    assert excinfo.value.code == "VALIDATION_ERROR"
    assert state.get_profile(user_id=A).preferences == {
        "preferred_occasions": ["business"]
    }


# --- SQL statement shape (real impl, recording session, no DB) -----------------


class _RecordingSession:
    def __init__(self) -> None:
        self.statements: list = []
        self.commits = 0

    def execute(self, statement):
        self.statements.append(statement)
        return None

    def commit(self) -> None:
        self.commits += 1


def test_sql_merges_with_concat_under_owner_scope():
    """The real `UserStateRepositorySQL.update_preferences` emits a single
    `UPDATE ... SET preferences = preferences || CAST(... AS JSONB)` scoped
    to `user_id` — merge, not replace; owner-scoped, not global."""
    from sqlalchemy.dialects import postgresql

    from app.infrastructure.db.repositories import UserStateRepositorySQL

    session = _RecordingSession()
    UserStateRepositorySQL(session).update_preferences(
        user_id=A, preferences={"preferred_occasions": ["weekend"]}
    )
    assert session.commits == 1
    assert len(session.statements) == 1
    sql = str(
        session.statements[0].compile(dialect=postgresql.dialect())
    )
    assert "||" in sql
    assert "CAST" in sql and "JSONB" in sql
    assert "user_state" in sql
    assert "user_id" in sql
    assert "style_profile" not in sql


# --- I: TRX-6 isolation ------------------------------------------------------------


def test_preference_update_does_not_touch_style_profile():
    """I. `style_profile` bytes are identical before/after; the use case never
    calls the style-profile writer."""
    style = {
        "face_shape": "Oval",
        "skin_tone": "Warm Medium",
        "body_type": "Athletic",
        "style_type": "Modern Classic",
        "source_run_id": "run-1",
    }
    state = FakeUserState()
    state.seed(A, style_profile=style)
    _use_case(state)(user_id=A, preferred_occasions=["date"])
    assert state.get_style_profile(user_id=A) == style
    assert all(call[0] == "update_preferences" for call in state.calls)


# --- G/H: router (DB-free, patched deps) -------------------------------------------


def _router_client(monkeypatch, state: FakeUserState, user_id: UUID):
    """Yield a TestClient with router SQL repos faked and auth/db overridden.

    Restores `app.dependency_overrides` on exit (same pattern as the
    STEP 11.2.1 wiring tests).
    """
    import time as _time_mod
    from contextlib import contextmanager
    from datetime import datetime as _dt, timezone as _tz

    # Neutralize any struct_time time patching for Starlette TestClient.
    _time_mod.time = lambda: _dt.now(_tz.utc).timestamp()

    from fastapi.testclient import TestClient

    import app.api.routers.users as users_router
    from app.main import app
    from app.api.deps import get_current_user_id
    from app.infrastructure.db.session import get_db

    class FakeRepos:
        def __init__(self, db=None) -> None:
            self._state = state

        def get_profile(self, *, user_id):
            return self._state.get_profile(user_id=user_id)

        def update_preferences(self, *, user_id, preferences):
            return self._state.update_preferences(
                user_id=user_id, preferences=preferences
            )

    monkeypatch.setattr(users_router, "UserStateRepositorySQL", FakeRepos)

    old_db = app.dependency_overrides.get(get_db)
    old_user = app.dependency_overrides.get(get_current_user_id)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user_id] = lambda: user_id

    @contextmanager
    def _client():
        try:
            yield TestClient(app)
        finally:
            if old_db is not None:
                app.dependency_overrides[get_db] = old_db
            else:
                app.dependency_overrides.pop(get_db, None)
            if old_user is not None:
                app.dependency_overrides[get_current_user_id] = old_user
            else:
                app.dependency_overrides.pop(get_current_user_id, None)

    return _client()


def test_patch_returns_updated_profile(monkeypatch):
    """G. `PATCH /v1/users/me` persists and returns the updated ProfileView."""
    state = FakeUserState()
    state.seed(A, display_name="Alex")
    with _router_client(monkeypatch, state, A) as client:
        resp = client.patch(
            "/v1/users/me", json={"preferredOccasions": ["smart_casual"]}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["displayName"] == "Alex"
        assert body["preferences"] == {"preferredOccasions": ["smart_casual"]}
        assert body["memorySummary"]["preferredOccasions"] == ["smart_casual"]


def test_patch_rejects_invalid_body(monkeypatch):
    """G (invalid). A non-list body value → frozen 422, nothing written."""
    state = FakeUserState()
    state.seed(A, preferences={"preferred_occasions": ["business"]})
    with _router_client(monkeypatch, state, A) as client:
        resp = client.patch("/v1/users/me", json={"preferredOccasions": "nope"})
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert state.get_profile(user_id=A).preferences == {
        "preferred_occasions": ["business"]
    }


def test_get_me_still_compatible(monkeypatch):
    """H. `GET /v1/users/me` contract unchanged (passthrough + summary)."""
    state = FakeUserState()
    state.seed(
        A,
        display_name="Alex",
        style_profile={"face_shape": "Oval"},
        preferences={"preferred_occasions": ["smart_casual"]},
    )
    with _router_client(monkeypatch, state, A) as client:
        resp = client.get("/v1/users/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["preferences"] == {"preferredOccasions": ["smart_casual"]}
        assert body["memorySummary"]["preferredOccasions"] == ["smart_casual"]
        assert body["styleProfile"]["faceShape"] == "Oval"


# --- DB-backed (runs when PostgreSQL is reachable, skips otherwise) --------------


def _dev_user_id(session):
    from sqlalchemy import select

    from app.infrastructure.db.models import Users, UserState

    user = session.execute(
        select(Users).where(
            Users.auth_provider == "dev", Users.auth_subject == "dev-user"
        )
    ).scalar_one_or_none()
    if user is None:
        user = Users(
            auth_provider="dev", auth_subject="dev-user", display_name="Dev User"
        )
        session.add(user)
        session.flush()
        session.add(UserState(user_id=user.id))
    return user.id


def test_patch_persists_and_get_reflects_db(db):
    """DB-backed: PATCH writes `||`-merged JSONB; GET reflects it."""
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.infrastructure.db.models import UserState
    from app.main import app

    Session = db
    with Session() as session:
        user_id = _dev_user_id(session)
        state = session.get(UserState, user_id)
        state.preferences = {
            "preferred_occasions": ["business"],
            "future_key": "preserve-me",
        }
        session.commit()

    client = TestClient(app)
    resp = client.patch(
        "/v1/users/me",
        json={"preferredOccasions": ["weekend"]},
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 200
    assert resp.json()["preferences"] == {
        "preferredOccasions": ["weekend"],
        "future_key": "preserve-me",
    }

    with Session() as session:
        stored = session.execute(
            select(UserState.preferences).where(UserState.user_id == user_id)
        ).scalar_one()
    assert stored == {
        "preferred_occasions": ["weekend"],
        "future_key": "preserve-me",
    }

    got = client.get("/v1/users/me", headers={"Authorization": "Bearer dev"})
    assert got.status_code == 200
    assert got.json()["memorySummary"]["preferredOccasions"] == ["weekend"]


def test_patch_requires_auth_db(db):
    """DB-backed: PATCH without a token → 401, same convention as GET."""
    from fastapi.testclient import TestClient

    from app.main import app

    resp = TestClient(app).patch(
        "/v1/users/me", json={"preferredOccasions": ["date"]}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"
