"""API tests for the save surface (#23, `POST /v1/looks/saved`).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).
"""

from __future__ import annotations

import pytest
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.infrastructure.db.models import AnalysisRuns, LearningSignals, SavedLooks, Users
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}

SNAPSHOT = {
    "appearance": {
        "faceShape": "Oval",
        "sourceRunId": "00000000-0000-0000-0000-000000000001",
    },
    "recommendations": {
        "top": {
            "id": "textured_quiff",
            "name": "Textured Quiff",
            "description": "A modern take on the classic quiff.",
            "matchScore": 0.94,
            "reasons": ["Oval face shapes benefit from volume on top"],
            "stylingTips": "Apply mousse.",
            "maintenance": "Medium",
            "bestFor": "Oval",
        },
        "alternatives": [],
    },
}


def _counts():
    Session = make_session()
    with Session() as session:
        looks = session.execute(select(func.count()).select_from(SavedLooks)).scalar_one()
        signals = session.execute(
            select(func.count()).select_from(LearningSignals)
        ).scalar_one()
        return looks, signals


def _make_user():
    Session = make_session()
    with Session() as session:
        user = session.execute(
            select(Users).where(Users.auth_provider == "dev", Users.auth_subject == "dev-user")
        ).scalar_one_or_none()
        if user is None:
            user = Users(auth_provider="dev", auth_subject="dev-user", display_name="Dev User")
            session.add(user)
            session.flush()
        run_id = UUID("00000000-0000-0000-0000-000000000001")
        run = session.execute(select(AnalysisRuns).where(AnalysisRuns.id == run_id)).scalar_one_or_none()
        if run is None:
            run = AnalysisRuns(
                id=run_id,
                user_id=user.id,
                run_type="hairstyle",
                status="completed",
                engine_version="1.0",
            )
            session.add(run)
        session.commit()
        return user.id


def _payload(**overrides):
    body = {
        "lookId": "textured_quiff",
        "title": "Textured Quiff",
        "sourceContext": "hairstyle",
        "snapshot": SNAPSHOT,
    }
    body.update(overrides)
    return body


def test_save_requires_idempotency_key(db):
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(),
        headers={"Authorization": "Bearer dev"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_save_creates_saved_look_and_signal_together(db):
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(),
        headers={**HEADERS, "Idempotency-Key": "key-1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["lookId"] == "textured_quiff"
    assert body["title"] == "Textured Quiff"
    assert body["sourceRunId"] == "00000000-0000-0000-0000-000000000001"
    assert body["createdAt"] is not None

    looks, signals = _counts()
    assert looks == 1
    assert signals == 1


def test_save_idempotent_replay_returns_original(db):
    _make_user()
    first = client.post(
        "/v1/looks/saved",
        json=_payload(),
        headers={**HEADERS, "Idempotency-Key": "key-replay"},
    )
    assert first.status_code == 201
    replay = client.post(
        "/v1/looks/saved",
        json=_payload(),
        headers={**HEADERS, "Idempotency-Key": "key-replay"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    looks, signals = _counts()
    assert looks == 1
    assert signals == 1


def test_save_conflicting_replay_returns_409(db):
    _make_user()
    client.post(
        "/v1/looks/saved",
        json=_payload(),
        headers={**HEADERS, "Idempotency-Key": "key-conflict"},
    )
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(title="Different Title"),
        headers={**HEADERS, "Idempotency-Key": "key-conflict"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFLICT"


def test_save_unknown_look_returns_404(db):
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(lookId="no_such_look"),
        headers={**HEADERS, "Idempotency-Key": "key-x"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_save_unknown_source_context_returns_422(db):
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(sourceContext="wardrobe"),
        headers={**HEADERS, "Idempotency-Key": "key-y"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_save_title_bounds_validate(db):
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(title=""),
        headers={**HEADERS, "Idempotency-Key": "key-z"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- GET /v1/looks/saved (endpoint #24) --------------------------------------


def test_list_returns_saved_looks_for_owner(db):
    _make_user()
    client.post(
        "/v1/looks/saved",
        json=_payload(title="Textured Quiff"),
        headers={**HEADERS, "Idempotency-Key": "list-key-1"},
    )
    client.post(
        "/v1/looks/saved",
        json=_payload(title="Classic Pompadour", lookId="classic_pompadour"),
        headers={**HEADERS, "Idempotency-Key": "list-key-2"},
    )

    resp = client.get("/v1/looks/saved", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    titles = [item["title"] for item in body["items"]]
    assert set(titles) == {"Textured Quiff", "Classic Pompadour"}
    assert body["page"] == 1
    assert body["page_size"] == 20


def test_list_respects_pagination(db):
    _make_user()
    for i in range(5):
        client.post(
            "/v1/looks/saved",
            json=_payload(title=f"Look {i}"),
            headers={**HEADERS, "Idempotency-Key": f"page-key-{i}"},
        )

    resp = client.get("/v1/looks/saved?page=2&page_size=2", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["page"] == 2


def test_list_is_empty_for_owner_without_saves(db):
    _make_user()
    resp = client.get("/v1/looks/saved", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


# --- STEP 11.13 B: typed save signal (DB-backed) ------------------------------
# Uses a snapshot WITHOUT sourceRunId so no analysis_runs FK is involved
# (the shared SNAPSHOT above references a nonexistent run id).


def _clean_snapshot():
    import copy

    snapshot = copy.deepcopy(SNAPSHOT)
    snapshot["appearance"].pop("sourceRunId", None)
    return snapshot


def _signal_rows():
    Session = make_session()
    with Session() as session:
        return session.execute(
            select(
                LearningSignals.signal_type,
                LearningSignals.label,
                LearningSignals.context,
            ).order_by(LearningSignals.occurred_at)
        ).all()


def test_save_stores_typed_look_saved_signal(db):
    """B. One save → 1 look + 1 signal with type look_saved, label = title."""
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(title="Textured Quiff", snapshot=_clean_snapshot()),
        headers={**HEADERS, "Idempotency-Key": "typed-key-1"},
    )
    assert resp.status_code == 201

    looks, signals = _counts()
    assert looks == 1
    assert signals == 1
    rows = _signal_rows()
    assert [(r[0], r[1]) for r in rows] == [("look_saved", "Textured Quiff")]
    assert rows[0][2] == {"source_context": "hairstyle", "look_id": "textured_quiff"}

    # Idempotent replay: same id, no new rows of either kind.
    replay = client.post(
        "/v1/looks/saved",
        json=_payload(title="Textured Quiff", snapshot=_clean_snapshot()),
        headers={**HEADERS, "Idempotency-Key": "typed-key-1"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == resp.json()["id"]
    looks, signals = _counts()
    assert looks == 1
    assert signals == 1


# --- STEP 11.16: source_context contract + outfit selectedItemIds (DB-backed) -


def _make_wardrobe_item(user_id, name="Navy Blazer"):
    """Insert one wardrobe item owned by `user_id`; returns its UUID string."""
    import uuid

    from app.infrastructure.db.models import WardrobeItems

    Session = make_session()
    with Session() as session:
        item = WardrobeItems(
            user_id=user_id,
            name=name,
            category_id="tops",
            color_id="black",
            material_id="cotton",
            is_favorite=False,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return str(item.id)


def _outfit_payload(**overrides):
    import copy

    body = {
        "lookId": None,
        "title": "Date Night Outfit",
        "sourceContext": "outfit",
        "snapshot": {"outfit": {"occasion": "date"}},
    }
    body.update(overrides)
    return copy.deepcopy(body)


def test_11_16_post_returns_source_context():
    """POST persists sourceContext and returns it on the response body."""
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_payload(snapshot=_clean_snapshot()),
        headers={**HEADERS, "Idempotency-Key": "ctx-post-1"},
    )
    assert resp.status_code == 201
    assert resp.json()["sourceContext"] == "hairstyle"


def test_11_16_get_returns_source_context():
    """GET /v1/looks/saved round-trips the persisted sourceContext."""
    _make_user()
    client.post(
        "/v1/looks/saved",
        json=_payload(title="Quiff", snapshot=_clean_snapshot()),
        headers={**HEADERS, "Idempotency-Key": "ctx-get-1"},
    )
    resp = client.get("/v1/looks/saved", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["items"][0]["sourceContext"] == "hairstyle"


def test_11_16_outfit_save_persists_canonical_item_ids():
    """Outfit save with owner items → 201, sourceContext outfit, sorted ids."""
    user_id = _make_user()
    item_b = _make_wardrobe_item(user_id, name="Second")
    item_a = _make_wardrobe_item(user_id, name="First")
    resp = client.post(
        "/v1/looks/saved",
        json=_outfit_payload(
            snapshot={
                "outfit": {"occasion": "date"},
                "selectedItemIds": [item_b, item_a.upper(), item_b],
            }
        ),
        headers={**HEADERS, "Idempotency-Key": "ctx-outfit-1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["sourceContext"] == "outfit"
    assert body["lookId"] is None
    assert body["snapshot"]["selectedItemIds"] == sorted([item_a, item_b])

    listed = client.get("/v1/looks/saved", headers=HEADERS).json()
    assert listed["items"][0]["sourceContext"] == "outfit"
    assert listed["items"][0]["snapshot"]["selectedItemIds"] == sorted(
        [item_a, item_b]
    )


def test_11_16_outfit_save_unknown_item_rejected():
    """Unknown wardrobe ID → 404, no saved row, no signal."""
    import uuid

    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_outfit_payload(
            snapshot={"selectedItemIds": [str(uuid.uuid4())]}
        ),
        headers={**HEADERS, "Idempotency-Key": "ctx-outfit-unknown"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
    looks, signals = _counts()
    assert looks == 0
    assert signals == 0


def test_11_16_outfit_save_foreign_item_rejected():
    """Another user's item ID → 404 (OW-1, 404-not-403), nothing stored."""
    from sqlalchemy import select

    from app.infrastructure.db.models import Users

    owner = _make_user()
    Session = make_session()
    with Session() as session:
        other = Users(
            auth_provider="dev", auth_subject="other-user", display_name="Other"
        )
        session.add(other)
        session.commit()
        session.refresh(other)
        foreign_id = _make_wardrobe_item(other.id)
    void = owner  # owner saves; item belongs to `other`
    assert void is not None
    resp = client.post(
        "/v1/looks/saved",
        json=_outfit_payload(snapshot={"selectedItemIds": [foreign_id]}),
        headers={**HEADERS, "Idempotency-Key": "ctx-outfit-foreign"},
    )
    assert resp.status_code == 404
    looks, signals = _counts()
    assert looks == 0
    assert signals == 0


def test_11_16_outfit_save_malformed_item_id_rejected():
    """Non-UUID member → 422, nothing stored."""
    _make_user()
    resp = client.post(
        "/v1/looks/saved",
        json=_outfit_payload(snapshot={"selectedItemIds": ["nope"]}),
        headers={**HEADERS, "Idempotency-Key": "ctx-outfit-malformed"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
    looks, signals = _counts()
    assert looks == 0
    assert signals == 0
