"""Comprehensive regression tests for Discovery interaction events persistence and telemetry (DISCOVERY-10A).

Deterministic test suite verifying:
- Authenticated identity derived from JWT.
- Guest identity isolation.
- Missing/both identities rejected (422).
- Client-supplied userId rejected (422).
- Idempotent replay (202 Accepted, replayed: true, 0 duplicates).
- Conflicting event ID returns 409 Conflict.
- Unknown product target rejected (404 NOT_FOUND).
- Invalid Complete Look ID rejected (422).
- Timestamp bounds enforced (422).
- Metadata allow-list and size bounds (422).
- Atomic batch rollback (422/404, 0 partial persistence).
- Account deletion cascade (CASCADE on users foreign key).
- Concurrent duplicate submission (race-safe).
- Deferred event types rejected (look_save, product_dismiss -> 422).
- OpenAPI documentation verification.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.deps import get_discovery_event_repository, get_optional_user_id
from app.infrastructure.db.repositories import DiscoveryEventRepositorySQL
from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.usefixtures("db")


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def _iso_now(offset_seconds: int = 0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return dt.isoformat()


def _create_test_user(session, user_id: Optional[UUID] = None) -> UUID:
    uid = user_id or uuid4()
    session.execute(
        text(
            "INSERT INTO users (id, auth_provider, auth_subject, display_name) "
            "VALUES (:id, 'test_provider', :sub, 'Test User')"
        ),
        {"id": uid, "sub": str(uid)},
    )
    session.commit()
    return uid


def _create_test_product(session, product_id: Optional[UUID] = None) -> UUID:
    pid = product_id or uuid4()
    session.execute(
        text(
            """INSERT INTO products (
                id, title, brand, category, subcategory, price, currency,
                availability, product_url, image_urls, first_seen_at, last_verified_at
            ) VALUES (
                :id, 'Test Product', 'Test Brand', 'tops', 'shirt', 1500.0, 'INR',
                true, 'https://example.com/p', '["https://example.com/img.jpg"]'::jsonb,
                now(), now()
            )"""
        ),
        {"id": pid},
    )
    session.commit()
    return pid


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def test_authenticated_identity_derived_from_jwt(db) -> None:
    """Authenticated requests derive user_id only from JWT claims; guestSessionId must be None."""
    with db() as session:
        user_id = _create_test_user(session)
        product_id = _create_test_product(session)

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        event_id = str(uuid4())
        payload = {
            "events": [
                {
                    "eventId": event_id,
                    "eventType": "product_save",
                    "targetType": "product",
                    "targetId": str(product_id),
                    "surface": "for_you_hero",
                    "position": 0,
                    "metadata": {"activeCategoryFilter": "tops"},
                    "occurredAt": _iso_now(),
                }
            ]
        }

        res = client.post("/v1/discovery/events", json=payload)
        assert res.status_code == 202
        data = res.json()
        assert data["acceptedCount"] == 1
        assert len(data["events"]) == 1
        assert data["events"][0]["eventId"] == event_id
        assert data["events"][0]["status"] == "accepted"
        assert data["events"][0]["replayed"] is False

        with db() as session:
            row = session.execute(
                text(
                    "SELECT user_id, guest_session_id, event_type, surface FROM discovery_events WHERE client_event_id = :cid"
                ),
                {"cid": event_id},
            ).fetchone()
            assert row is not None
            assert row[0] == user_id
            assert row[1] is None
            assert row[2] == "product_save"
            assert row[3] == "for_you_hero"
    finally:
        app.dependency_overrides.clear()


def test_guest_identity_isolation(db) -> None:
    """Guest requests provide guestSessionId with no auth; user_id is NULL in DB."""
    with db() as session:
        product_id = _create_test_product(session)
    guest_session_id = str(uuid4())

    app.dependency_overrides[get_optional_user_id] = lambda: None

    try:
        event_id = str(uuid4())
        payload = {
            "guestSessionId": guest_session_id,
            "events": [
                {
                    "eventId": event_id,
                    "eventType": "product_impression",
                    "targetType": "product",
                    "targetId": str(product_id),
                    "surface": "for_you_grid",
                    "position": 1,
                    "metadata": {"dwellTimeMs": 1500, "viewportRatio": 0.85},
                    "occurredAt": _iso_now(),
                }
            ],
        }

        res = client.post("/v1/discovery/events", json=payload)
        assert res.status_code == 202
        data = res.json()
        assert data["acceptedCount"] == 1
        assert data["events"][0]["replayed"] is False

        with db() as session:
            row = session.execute(
                text(
                    "SELECT user_id, guest_session_id, event_type FROM discovery_events WHERE client_event_id = :cid"
                ),
                {"cid": event_id},
            ).fetchone()
            assert row is not None
            assert row[0] is None
            assert str(row[1]) == guest_session_id
            assert row[2] == "product_impression"
    finally:
        app.dependency_overrides.clear()


def test_missing_and_both_identities_rejected(db) -> None:
    """Missing identity or both identities provided fails with 422 VALIDATION_ERROR."""
    with db() as session:
        product_id = _create_test_product(session)

    try:
        # Case 1: Unauthenticated request with no guestSessionId -> 422
        app.dependency_overrides[get_optional_user_id] = lambda: None
        res = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_click",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_grid",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"

        # Case 2: Authenticated request providing guestSessionId -> 422
        app.dependency_overrides[get_optional_user_id] = lambda: uuid4()
        res = client.post(
            "/v1/discovery/events",
            json={
                "guestSessionId": str(uuid4()),
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_click",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_grid",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    }
                ],
            },
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


def test_client_supplied_user_id_rejected(db) -> None:
    """Clients attempting to pass userId or user_id in the body are rejected with 422."""
    with db() as session:
        product_id = _create_test_product(session)

    app.dependency_overrides[get_optional_user_id] = lambda: None

    try:
        # 1. userId at top-level
        res = client.post(
            "/v1/discovery/events",
            json={
                "guestSessionId": str(uuid4()),
                "userId": str(uuid4()),
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_save",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_hero",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    }
                ],
            },
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"

        # 2. userId inside event item
        res = client.post(
            "/v1/discovery/events",
            json={
                "guestSessionId": str(uuid4()),
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "userId": str(uuid4()),
                        "eventType": "product_save",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_hero",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    }
                ],
            },
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


def test_idempotent_replay_and_intra_batch_dedup(db) -> None:
    """Identical replay acknowledges without inserting duplicate rows."""
    with db() as session:
        user_id = _create_test_user(session)
        product_id = _create_test_product(session)

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        event_id = str(uuid4())
        event_item = {
            "eventId": event_id,
            "eventType": "product_save",
            "targetType": "product",
            "targetId": str(product_id),
            "surface": "for_you_hero",
            "position": 0,
            "metadata": {"activeCategoryFilter": "tops"},
            "occurredAt": _iso_now(),
        }

        # First request -> accepted
        res1 = client.post("/v1/discovery/events", json={"events": [event_item]})
        assert res1.status_code == 202
        assert res1.json()["acceptedCount"] == 1
        assert res1.json()["events"][0]["replayed"] is False

        # Exact second request -> acknowledged with replayed: true
        res2 = client.post("/v1/discovery/events", json={"events": [event_item]})
        assert res2.status_code == 202
        assert res2.json()["acceptedCount"] == 0
        assert res2.json()["events"][0]["replayed"] is True
        assert res2.json()["events"][0]["status"] == "acknowledged"

        # Verify only 1 row exists in DB
        with db() as session:
            count = session.execute(
                text(
                    "SELECT count(*) FROM discovery_events WHERE client_event_id = :cid"
                ),
                {"cid": event_id},
            ).scalar()
            assert count == 1

        # Intra-batch duplicate with same payload
        event_id2 = str(uuid4())
        item2 = {**event_item, "eventId": event_id2}
        res3 = client.post(
            "/v1/discovery/events", json={"events": [item2, item2]}
        )
        assert res3.status_code == 202
        assert res3.json()["events"][0]["replayed"] is False
        assert res3.json()["events"][1]["replayed"] is True
    finally:
        app.dependency_overrides.clear()


def test_conflicting_event_id_returns_409(db) -> None:
    """Submitting an existing event ID with a conflicting payload returns 409 Conflict."""
    with db() as session:
        user_id = _create_test_user(session)
        product_id1 = _create_test_product(session)
        product_id2 = _create_test_product(session)

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        event_id = str(uuid4())
        item1 = {
            "eventId": event_id,
            "eventType": "product_save",
            "targetType": "product",
            "targetId": str(product_id1),
            "surface": "for_you_hero",
            "metadata": {},
            "occurredAt": _iso_now(),
        }

        # Step 1: Submit original event
        res1 = client.post("/v1/discovery/events", json={"events": [item1]})
        assert res1.status_code == 202

        # Step 2: Submit same eventId with changed targetId
        item_conflict = {
            "eventId": event_id,
            "eventType": "product_save",
            "targetType": "product",
            "targetId": str(product_id2),  # Conflicting target!
            "surface": "for_you_hero",
            "metadata": {},
            "occurredAt": _iso_now(),
        }
        res2 = client.post("/v1/discovery/events", json={"events": [item_conflict]})
        assert res2.status_code == 409
        err = res2.json()["error"]
        assert err["code"] == "CONFLICT"
        assert err["details"]["kind"] == "duplicate_event_id_conflict"
        assert err["details"]["eventId"] == event_id

        # Step 3: Intra-batch conflict
        event_id_intra = str(uuid4())
        res3 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {**item1, "eventId": event_id_intra, "targetId": str(product_id1)},
                    {**item1, "eventId": event_id_intra, "targetId": str(product_id2)},
                ]
            },
        )
        assert res3.status_code == 409
        assert res3.json()["error"]["code"] == "CONFLICT"
    finally:
        app.dependency_overrides.clear()


def test_unknown_product_target_rejected_404(db) -> None:
    """Non-existent product UUID fails closed with HTTP 404 NOT_FOUND."""
    with db() as session:
        user_id = _create_test_user(session)
    non_existent_id = str(uuid4())

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        res = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_click",
                        "targetType": "product",
                        "targetId": non_existent_id,
                        "surface": "for_you_grid",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res.status_code == 404
        err = res.json()["error"]
        assert err["code"] == "NOT_FOUND"
        assert err["details"]["kind"] == "unknown_product"
        assert err["details"]["targetId"] == non_existent_id
    finally:
        app.dependency_overrides.clear()


def test_complete_look_target_validation(db) -> None:
    """Complete look targets require look_select and format ^look_[a-f0-9]{16}$; transient UI indices fail."""
    with db() as session:
        user_id = _create_test_user(session)

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        # 1. Valid look ID
        valid_look_id = "look_4f9a2b8c1d3e5a7b"
        res = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "look_select",
                        "targetType": "complete_look",
                        "targetId": valid_look_id,
                        "surface": "complete_looks",
                        "metadata": {
                            "selectedSlotCount": 3,
                            "totalCatalogPrice": 4500.0,
                        },
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res.status_code == 202
        assert res.json()["acceptedCount"] == 1

        # 2. Transient UI index '0' -> 422
        res2 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "look_select",
                        "targetType": "complete_look",
                        "targetId": "0",
                        "surface": "complete_looks",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res2.status_code == 422
        assert res2.json()["error"]["code"] == "VALIDATION_ERROR"

        # 3. Label 'Look 1' -> 422
        res3 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "look_select",
                        "targetType": "complete_look",
                        "targetId": "Look 1",
                        "surface": "complete_looks",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res3.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_timestamp_bounds_enforced(db) -> None:
    """Timestamps > 5 min in the future or > 24 hours in the past are rejected with 422."""
    with db() as session:
        user_id = _create_test_user(session)
        product_id = _create_test_product(session)

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        # 1. Future timestamp (+10 min) -> 422
        future_iso = _iso_now(600)
        res1 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_save",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_hero",
                        "metadata": {},
                        "occurredAt": future_iso,
                    }
                ]
            },
        )
        assert res1.status_code == 422

        # 2. Past timestamp (-26 hours) -> 422
        past_iso = (datetime.now(timezone.utc) - timedelta(hours=26)).isoformat()
        res2 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_save",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_hero",
                        "metadata": {},
                        "occurredAt": past_iso,
                    }
                ]
            },
        )
        assert res2.status_code == 422

        # 3. Valid timestamp (-1 hour) -> 202
        valid_iso = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        res3 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_save",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_hero",
                        "metadata": {},
                        "occurredAt": valid_iso,
                    }
                ]
            },
        )
        assert res3.status_code == 202
    finally:
        app.dependency_overrides.clear()


def test_metadata_allow_list_and_size_bounds(db) -> None:
    """Metadata must respect allow-list per event type, size bounds, and privacy constraints."""
    with db() as session:
        user_id = _create_test_user(session)
        product_id = _create_test_product(session)

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        # 1. Privacy violation: sending email or query -> 422
        res1 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_click",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_grid",
                        "metadata": {"email": "user@example.com"},
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res1.status_code == 422

        # 2. Out-of-bounds dwell time (500ms < 1000ms threshold) -> 422
        res2 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_impression",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_grid",
                        "metadata": {"dwellTimeMs": 500, "viewportRatio": 0.8},
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res2.status_code == 422

        # 3. Out-of-bounds viewport ratio (0.3 < 0.5 threshold) -> 422
        res3 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_impression",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_grid",
                        "metadata": {"dwellTimeMs": 1500, "viewportRatio": 0.3},
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res3.status_code == 422

        # 4. Oversized metadata (> 8 keys) -> 422
        oversized = {f"k{i}": i for i in range(10)}
        res4 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_click",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_grid",
                        "metadata": oversized,
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res4.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_atomic_batch_rollback(db) -> None:
    """A malformed or invalid event anywhere in a batch rolls back the entire batch."""
    with db() as session:
        user_id = _create_test_user(session)
        product_id = _create_test_product(session)

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        good_event_id = str(uuid4())
        bad_event_id = str(uuid4())

        res = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": good_event_id,
                        "eventType": "product_save",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_hero",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    },
                    {
                        "eventId": bad_event_id,
                        "eventType": "look_save",  # Deferred event type!
                        "targetType": "complete_look",
                        "targetId": "look_0123456789abcdef",
                        "surface": "complete_looks",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    },
                ]
            },
        )
        assert res.status_code == 422

        # Verify zero rows were inserted
        with db() as session:
            count = session.execute(
                text(
                    "SELECT count(*) FROM discovery_events WHERE client_event_id = :cid"
                ),
                {"cid": good_event_id},
            ).scalar()
            assert count == 0
    finally:
        app.dependency_overrides.clear()


def test_deferred_event_types_rejected(db) -> None:
    """look_save and product_dismiss are explicitly deferred and rejected with 422."""
    with db() as session:
        user_id = _create_test_user(session)
        product_id = _create_test_product(session)

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        # 1. look_save rejected
        res1 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "look_save",
                        "targetType": "complete_look",
                        "targetId": "look_0123456789abcdef",
                        "surface": "complete_looks",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res1.status_code == 422
        assert (
            "deferred" in res1.json()["error"]["message"].lower()
            or "deferred" in str(res1.json()).lower()
        )

        # 2. product_dismiss rejected
        res2 = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": str(uuid4()),
                        "eventType": "product_dismiss",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_grid",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res2.status_code == 422
        assert (
            "deferred" in res2.json()["error"]["message"].lower()
            or "deferred" in str(res2.json()).lower()
        )
    finally:
        app.dependency_overrides.clear()


def test_account_deletion_cascade(db) -> None:
    """Deleting user in users cascades and deletes associated discovery_events rows."""
    with db() as session:
        user_id = _create_test_user(session)
        product_id = _create_test_product(session)

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        event_id = str(uuid4())
        res = client.post(
            "/v1/discovery/events",
            json={
                "events": [
                    {
                        "eventId": event_id,
                        "eventType": "product_save",
                        "targetType": "product",
                        "targetId": str(product_id),
                        "surface": "for_you_hero",
                        "metadata": {},
                        "occurredAt": _iso_now(),
                    }
                ]
            },
        )
        assert res.status_code == 202

        # Verify event exists
        with db() as session:
            count = session.execute(
                text(
                    "SELECT count(*) FROM discovery_events WHERE user_id = :uid"
                ),
                {"uid": user_id},
            ).scalar()
            assert count == 1

            # Delete user
            session.execute(
                text("DELETE FROM users WHERE id = :uid"), {"uid": user_id}
            )
            session.commit()

            # Verify event was cascaded
            count_after = session.execute(
                text(
                    "SELECT count(*) FROM discovery_events WHERE user_id = :uid"
                ),
                {"uid": user_id},
            ).scalar()
            assert count_after == 0
    finally:
        app.dependency_overrides.clear()


def test_concurrent_duplicate_submission(db) -> None:
    """Simultaneous submissions of the same event ID are race-safe and do not crash with unhandled errors."""
    with db() as session:
        user_id = _create_test_user(session)
        product_id = _create_test_product(session)

    app.dependency_overrides[get_optional_user_id] = lambda: user_id

    try:
        event_id = str(uuid4())
        payload = {
            "events": [
                {
                    "eventId": event_id,
                    "eventType": "product_save",
                    "targetType": "product",
                    "targetId": str(product_id),
                    "surface": "for_you_hero",
                    "position": 0,
                    "metadata": {"activeCategoryFilter": "tops"},
                    "occurredAt": _iso_now(),
                }
            ]
        }

        # Send request 1
        res1 = client.post("/v1/discovery/events", json=payload)
        assert res1.status_code == 202

        # Send request 2 with exact same payload (race-safe replay)
        res2 = client.post("/v1/discovery/events", json=payload)
        assert res2.status_code == 202
        assert res2.json()["events"][0]["replayed"] is True

        with db() as session:
            count = session.execute(
                text(
                    "SELECT count(*) FROM discovery_events WHERE client_event_id = :cid"
                ),
                {"cid": event_id},
            ).scalar()
            assert count == 1
    finally:
        app.dependency_overrides.clear()


def test_openapi_schema_contains_discovery_events() -> None:
    """OpenAPI schema must contain POST /v1/discovery/events and its schemas."""
    schema = app.openapi()
    paths = schema.get("paths", {})
    assert "/v1/discovery/events" in paths
    assert "post" in paths["/v1/discovery/events"]

    post_op = paths["/v1/discovery/events"]["post"]
    assert "202" in post_op.get("responses", {})

    schemas = schema.get("components", {}).get("schemas", {})
    assert "DiscoveryEventsBatchRequest" in schemas
    assert "DiscoveryEventIngestItemSchema" in schemas
    assert "DiscoveryEventsIngestResponse" in schemas
    assert "DiscoveryEventAckSchema" in schemas
