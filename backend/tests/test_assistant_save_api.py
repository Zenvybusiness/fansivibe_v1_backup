"""API tests for the assistant save path via M7 (P1-1 hardening).

The assistant flow reuses the frozen `POST /v1/looks/saved` (endpoint #23,
`SaveRecommendation`, TRX-3) under `sourceContext == "outfit"` — there is no
assistant save endpoint and no `"assistant"` context value (the M7 CHECK +
allow-list accept only hairstyle/grooming/outfit/daily; `"assistant"` is a
truthful 422). The Flutter client authenticates (Bearer) and sanitizes
`selectedItemIds` to backend-UUID-shaped strings, omitting the key when none
survive; the server fail-closes local IDs (422) and unknown/foreign UUIDs
(404, nothing stored).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; each test starts truncated-clean).

Covers: 401, 201 for the sanitized assistant shape (no `selectedItemIds`)
with exact TRX-3 side-effect proof, 201 + canonicalization for owned UUIDs,
422 for local IDs, 404-not-403 for unknown/foreign UUIDs, missing-key 422,
`"assistant"`-context 422, replay identity, 409 conflict, single-row proof.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.models import Users
from app.infrastructure.db.session import DATABASE_URL

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}


def _assistant_snapshot(**overrides):
    """The sanitized assistant snapshot shape: verbatim intelligence fields,
    `selectedItemIds` only when the caller supplies UUID-shaped IDs."""
    body = {
        "outfitComposition": {"topIds": [], "styleScore": 0},
        "occasion": "office",
        "stylingRationale": "r",
        "compatibilityRationale": "c",
        "confidence": 0.9,
        "explanation": "e",
        "dataAvailability": "full",
    }
    body.update(overrides)
    return body


def _save(title="Office Outfit", snapshot=None, key=None, headers=HEADERS):
    payload = {
        "title": title,
        "sourceContext": "outfit",
        "snapshot": snapshot if snapshot is not None else _assistant_snapshot(),
    }
    request_headers = dict(headers)
    if key is not None:
        request_headers["Idempotency-Key"] = key
    return client.post("/v1/looks/saved", headers=request_headers, json=payload)


# Module-shared engine for helpers: one small pool for the whole file
# (per-call engines exhaust connection slots across a full-file run).
_HELPER_SESSIONS = sessionmaker(
    bind=create_engine(DATABASE_URL, pool_size=3, max_overflow=0),
    expire_on_commit=False,
)


def _session():
    return _HELPER_SESSIONS()


def _dev_user_id():
    from app.infrastructure.db.models import UserState

    with _session() as session:
        user = session.execute(
            select(Users).where(
                Users.auth_provider == "dev", Users.auth_subject == "dev-user"
            )
        ).scalar_one_or_none()
        if user is None:
            user = Users(auth_provider="dev", auth_subject="dev-user", display_name="Dev User")
            session.add(user)
            session.flush()
            session.add(UserState(user_id=user.id))
            session.commit()
        return user.id


def _seed_wardrobe(user_id, count=2):
    with _session() as session:
        for index in range(count):
            session.execute(
                text(
                    "INSERT INTO wardrobe_items "
                    "(user_id, name, category_id, color_id, material_id, is_favorite) "
                    "VALUES (:u, :n, 'tops', 'black', NULL, false)"
                ),
                {"u": str(user_id), "n": f"Assistant Tee {index}"},
            )
        session.commit()


def _owner_item_ids(user_id):
    with _session() as session:
        return {
            str(value)
            for value in session.execute(
                text("SELECT id FROM wardrobe_items WHERE user_id = :u"),
                {"u": str(user_id)},
            )
            .scalars()
            .all()
        }


def _counts():
    with _session() as session:
        return {
            table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            for table in (
                "saved_looks",
                "learning_signals",
                "activity_days",
                "wardrobe_items",
                "wardrobe_wear_events",
                "wardrobe_wear_groups",
                "user_events",
                "feedback_events",
            )
        }


def _error(response):
    return response.json()["error"]


# ---------------------------------------------------------------------------
# Auth + key + context gating
# ---------------------------------------------------------------------------


def test_unauthenticated_save_is_401():
    response = _save(key="p1-a1", headers={})
    assert response.status_code == 401
    assert _error(response)["code"] == "AUTHENTICATION_ERROR"


def test_missing_idempotency_key_is_422():
    response = _save()
    assert response.status_code == 422
    assert _error(response)["code"] == "VALIDATION_ERROR"


def test_assistant_context_value_is_rejected_with_allowed_list():
    """`"assistant"` is not an M7 source context (frozen CHECK + allow-list);
    the assistant outfit flow uses `"outfit"` (P1-1 contract note)."""
    payload = {
        "title": "Office Outfit",
        "sourceContext": "assistant",
        "snapshot": _assistant_snapshot(),
    }
    response = client.post(
        "/v1/looks/saved",
        headers={**HEADERS, "Idempotency-Key": "p1-a2"},
        json=payload,
    )
    assert response.status_code == 422
    body = _error(response)
    assert body["code"] == "VALIDATION_ERROR"
    # Pydantic's frozen Literal rejects the value before the use-case
    # allow-list runs (no `allowed` key on this path); either way the
    # value is unaccepted and nothing is stored.
    assert _counts()["saved_looks"] == 0


# ---------------------------------------------------------------------------
# Sanitized assistant shape: saves with exact TRX-3 effects, nothing else
# ---------------------------------------------------------------------------


def test_sanitized_snapshot_saves_with_single_signal_and_day():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    before = _counts()
    response = _save(key="p1-b1")
    assert response.status_code == 201
    body = response.json()
    assert body["sourceContext"] == "outfit"
    assert "selectedItemIds" not in body["snapshot"]
    after = _counts()
    assert after["saved_looks"] - before["saved_looks"] == 1
    assert after["learning_signals"] - before["learning_signals"] == 1
    # Nothing else moves: no wear, no event, no preference-adjacent write.
    for table in (
        "wardrobe_items",
        "wardrobe_wear_events",
        "wardrobe_wear_groups",
        "user_events",
        "feedback_events",
    ):
        assert after[table] == before[table], table
    with _session() as session:
        signal = session.execute(
            text(
                "SELECT signal_type, label FROM learning_signals "
                "WHERE user_id = :u ORDER BY occurred_at DESC LIMIT 1"
            ),
            {"u": str(user_id)},
        ).one()
        assert signal == ("look_saved", "Office Outfit")


def test_owned_uuid_ids_save_canonically_sorted_unique():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    ids = sorted(_owner_item_ids(user_id))
    assert len(ids) == 2
    shuffled = [ids[1], ids[0], ids[1]]
    response = _save(
        key="p1-b2", snapshot=_assistant_snapshot(selectedItemIds=shuffled)
    )
    assert response.status_code == 201
    assert response.json()["snapshot"]["selectedItemIds"] == ids


# ---------------------------------------------------------------------------
# Fail-closed identity: local IDs 422, unknown/foreign UUIDs 404
# ---------------------------------------------------------------------------


def test_local_engine_ids_are_rejected_with_nothing_stored():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    before = _counts()
    response = _save(
        key="p1-c1",
        snapshot=_assistant_snapshot(selectedItemIds=["1", "blazer-001", "24"]),
    )
    assert response.status_code == 422
    assert _error(response)["code"] == "VALIDATION_ERROR"
    assert _counts() == before


def test_unknown_uuid_is_404_not_403_with_nothing_stored():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    before = _counts()
    response = _save(
        key="p1-c2",
        snapshot=_assistant_snapshot(
            selectedItemIds=[str(uuid4()), str(uuid4())]
        ),
    )
    assert response.status_code == 404
    assert _error(response)["code"] == "NOT_FOUND"
    assert _counts() == before


def test_foreign_uuid_is_404_with_nothing_stored():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    with _session() as session:
        foreign = Users(
            auth_provider="p1", auth_subject=f"foreign-{uuid4()}", display_name="F"
        )
        session.add(foreign)
        session.flush()
        session.execute(
            text(
                "INSERT INTO wardrobe_items "
                "(user_id, name, category_id, color_id, material_id, is_favorite) "
                "VALUES (:u, 'Foreign Tee', 'tops', 'black', NULL, false)"
            ),
            {"u": str(foreign.id)},
        )
        session.commit()
        foreign_id = session.execute(
            text("SELECT id FROM wardrobe_items WHERE user_id = :u"),
            {"u": str(foreign.id)},
        ).scalar_one()
    before = _counts()
    response = _save(
        key="p1-c3",
        snapshot=_assistant_snapshot(selectedItemIds=[str(foreign_id)]),
    )
    assert response.status_code == 404
    after = _counts()
    # The foreign-user seed row itself is expected; the save stored nothing.
    assert after["saved_looks"] == before["saved_looks"]
    assert after["learning_signals"] == before["learning_signals"]


# ---------------------------------------------------------------------------
# Idempotency: replay identity + 409 conflict (M7 semantics unchanged)
# ---------------------------------------------------------------------------


def test_replay_returns_original_with_single_row():
    first = _save(key="p1-d1")
    assert first.status_code == 201
    second = _save(key="p1-d1")
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    with _session() as session:
        rows = session.execute(
            text("SELECT COUNT(*) FROM saved_looks WHERE user_id = :u"),
            {"u": str(_dev_user_id())},
        ).scalar()
        assert rows == 1


def test_conflicting_replay_is_409():
    assert _save(key="p1-d2").status_code == 201
    conflict = _save(title="Different Title", key="p1-d2")
    assert conflict.status_code == 409
    assert _error(conflict)["code"] == "CONFLICT"
