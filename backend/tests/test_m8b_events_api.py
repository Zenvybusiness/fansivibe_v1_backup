"""API tests for the M8-B event calendar CRUD + R36 (endpoints #26–29).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; each test starts truncated-clean).

Covers the task §10 matrix: CREATE (+response exactness, bounds,
formats, retries, no signal), R36 on create (append/no-dupe/preserve/
failure-leaves-event), LIST (isolation, upcoming default, from,
deterministic date/time-NULLS-LAST/id ordering, pagination,
envelope exactness), UPDATE (full replace, clearing, bounds,
UUID/ownership, updated_at, conditional R36), DELETE (204/404s,
prefs/history untouched), and AUTH (401 throughout).

Does NOT touch the event outfit (#30) or Flutter — later M8 steps.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.application.events import CreateEvent, UpdateEvent
from app.infrastructure.db.models import EventType, LearningSignals, UserEvent, Users
from app.infrastructure.db.repositories import (
    EventTypeRepositorySQL,
    UserEventRepositorySQL,
)
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}

FUTURE_1 = "2030-07-20"
FUTURE_2 = "2030-08-15"
FUTURE_3 = "2030-08-16"
PAST = "2000-01-01"


def _payload(**overrides):
    body = {
        "title": "Company Gala",
        "eventType": "formal",
        "eventDate": FUTURE_2,
        "time": "19:00",
        "location": "Grand Ballroom",
        "notes": "Black tie",
    }
    body.update(overrides)
    return body


def _create(_body=None, headers=HEADERS, **overrides):
    body = _payload()
    if _body is not None:
        body.update(_body)
    body.update(overrides)
    return client.post("/v1/events", json=body, headers=headers)


def _dev_user_id():
    from app.infrastructure.db.models import UserState

    Session = make_session()
    with Session() as session:
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


def _prefs():
    Session = make_session()
    with Session() as session:
        row = session.execute(
            select(Users).where(
                Users.auth_provider == "dev", Users.auth_subject == "dev-user"
            )
        ).scalar_one()
        prefs = session.execute(
            text("SELECT preferences FROM user_state WHERE user_id = :id"),
            {"id": str(row.id)},
        ).scalar_one()
        return dict(prefs or {})


def _preferred_occasions():
    raw = _prefs().get("preferred_occasions")
    return list(raw) if isinstance(raw, list) else []


def _signal_count():
    Session = make_session()
    with Session() as session:
        user_id = _dev_user_id()
        return session.execute(
            select(func.count())
            .select_from(LearningSignals)
            .where(LearningSignals.user_id == user_id)
        ).scalar_one()


def _seed_foreign_event():
    """Seed one event for a non-dev user directly; returns (user_id, event_id)."""
    Session = make_session()
    with Session() as session:
        user = Users(
            auth_provider="m8b",
            auth_subject=f"foreign-{uuid4()}",
            display_name="Foreign",
        )
        session.add(user)
        session.flush()
        row = UserEvent(
            user_id=user.id,
            title="Foreign Gala",
            event_type_id="formal",
            event_date=date(2030, 9, 1),
        )
        session.add(row)
        session.commit()
        return user.id, row.id


class _FailingUserState:
    """UserState port double whose preference write always fails (R36)."""

    def get_profile(self, *, user_id):
        return None

    def update_preferences(self, *, user_id, preferences):
        raise RuntimeError("preference store unavailable")


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


def test_create_valid_event_returns_201_with_exact_fields():
    """Valid create → 201 with the exact frozen UserEvent keys."""
    resp = _create()
    assert resp.status_code == 201
    body = resp.json()
    assert set(body) == {
        "id",
        "title",
        "eventType",
        "eventDate",
        "time",
        "location",
        "notes",
        "createdAt",
        "updatedAt",
    }
    assert body["title"] == "Company Gala"
    assert body["eventType"] == "formal"
    assert body["eventDate"] == FUTURE_2
    assert body["time"] == "19:00"
    assert body["location"] == "Grand Ballroom"
    assert body["notes"] == "Black tie"
    UUID(body["id"])


def test_create_all_optionals_null():
    """Omitted time/location/notes persist and echo as null."""
    resp = client.post(
        "/v1/events",
        json={"title": "Bare", "eventType": "casual", "eventDate": FUTURE_1},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["time"] is None
    assert body["location"] is None
    assert body["notes"] is None


def test_create_today_allowed():
    """eventDate == server-UTC today is not in the past → 201."""
    today = datetime.now(timezone.utc).date().isoformat()
    resp = _create({"eventDate": today})
    assert resp.status_code == 201


def test_create_invalid_type_rejected():
    """Unknown code (incl. M5-only `office`) → 422 with allowed values."""
    for bad in ("office", "nope", ""):
        resp = _create({"eventType": bad})
        assert resp.status_code == 422, bad
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_inactive_type_rejected():
    """Inactive vocab row → 422; row removed afterwards (seed hygiene)."""
    Session = make_session()
    with Session() as session:
        session.add(
            EventType(code="archived_test", label="Archived", sort_order=99, active=False)
        )
        session.commit()
    try:
        resp = _create({"eventType": "archived_test"})
        assert resp.status_code == 422
    finally:
        with Session() as session:
            session.execute(text("DELETE FROM event_types WHERE code = 'archived_test'"))
            session.commit()


def test_create_past_date_rejected():
    """Past event_date → 422 (UC-18)."""
    resp = _create({"eventDate": PAST})
    assert resp.status_code == 422


def test_create_malformed_date_rejected():
    """Non-ISO date → 422."""
    resp = _create({"eventDate": "not-a-date"})
    assert resp.status_code == 422


def test_create_invalid_time_formats_rejected():
    """Seconds, 12h labels, and empty time → 422; HH:mm accepted."""
    for bad in ("19:30:00", "7:30 PM", "", "24:00", "9:5"):
        resp = _create({"time": bad})
        assert resp.status_code == 422, bad
    assert _create({"time": "09:05"}).json()["time"] == "09:05"


def test_create_text_bounds():
    """location 200/notes 2000 accepted; 201/2001 and empties → 422."""
    assert _create({"location": "x" * 200}).status_code == 201
    assert _create({"location": "x" * 201}).status_code == 422
    assert _create({"notes": "x" * 2000}).status_code == 201
    assert _create({"notes": "x" * 2001}).status_code == 422
    assert _create({"location": ""}).status_code == 422
    assert _create({"notes": ""}).status_code == 422
    assert _create({"title": ""}).status_code == 422
    assert _create({"title": "x" * 201}).status_code == 422


def test_create_retries_append_separate_events():
    """No Idempotency-Key: identical retries → two rows, two ids."""
    first = _create()
    second = _create()
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    listed = client.get("/v1/events", headers=HEADERS).json()
    assert listed["total"] == 2


def test_create_writes_no_learning_signal():
    """CREATE writes no learning signal."""
    before = _signal_count()
    assert _create().status_code == 201
    assert _signal_count() == before


# ---------------------------------------------------------------------------
# R36 on CREATE
# ---------------------------------------------------------------------------


def test_r36_create_appends_new_type():
    """New event type code is appended to preferredOccasions."""
    assert _create({"eventType": "party"}).status_code == 201
    assert "party" in _preferred_occasions()


def test_r36_create_no_duplicate_and_preserves_existing():
    """Existing code is not duplicated; sibling values survive."""
    client.patch("/v1/users/me", json={"preferredOccasions": ["casual"]}, headers=HEADERS)
    assert _create({"eventType": "formal"}).status_code == 201
    assert _preferred_occasions() == ["casual", "formal"]
    assert _create({"eventType": "formal", "title": "Again"}).status_code == 201
    assert _preferred_occasions() == ["casual", "formal"]


def test_r36_create_failure_leaves_event_committed():
    """Preference-store failure still returns the created event (201-stands)."""
    Session = make_session()
    with Session() as session:
        user = session.execute(
            select(Users).where(
                Users.auth_provider == "dev", Users.auth_subject == "dev-user"
            )
        ).scalar_one_or_none()
        if user is None:
            user = Users(auth_provider="dev", auth_subject="dev-user", display_name="Dev User")
            session.add(user)
            session.commit()
        use_case = CreateEvent(
            events=UserEventRepositorySQL(session),
            event_types=EventTypeRepositorySQL(session),
            user_state=_FailingUserState(),
        )
        record = use_case(
            user_id=user.id,
            title="Stands",
            event_type="travel",
            event_date=date(2030, 5, 5),
        )
        found = session.execute(
            select(UserEvent).where(UserEvent.id == record.id)
        ).scalar_one_or_none()
        assert found is not None
        assert found.title == "Stands"


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


def test_list_empty_returns_200_envelope():
    """Empty calendar → 200 with the exact envelope and no items."""
    resp = client.get("/v1/events", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"items", "page", "page_size", "total"}
    assert body == {"items": [], "page": 1, "page_size": 20, "total": 0}


def test_list_owner_isolation():
    """Another user's events never appear in the dev user's list."""
    _, _ = _seed_foreign_event()
    assert _create().status_code == 201
    body = client.get("/v1/events", headers=HEADERS).json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "Company Gala"


def test_list_upcoming_default_excludes_past():
    """Default window is upcoming: directly-seeded past rows are hidden."""
    Session = make_session()
    with Session() as session:
        user_id = _dev_user_id()
        session.add(
            UserEvent(
                user_id=user_id,
                title="Old",
                event_type_id="casual",
                event_date=date(2000, 2, 2),
            )
        )
        session.commit()
    assert _create().status_code == 201
    body = client.get("/v1/events", headers=HEADERS).json()
    assert [i["title"] for i in body["items"]] == ["Company Gala"]
    backfill = client.get("/v1/events", params={"from": PAST}, headers=HEADERS).json()
    assert backfill["total"] == 2


def test_list_from_filter_and_summary_shape():
    """`from` is on/after; rows are EventSummary cards (exact keys)."""
    _create({"title": "Early", "eventDate": FUTURE_1, "time": None})
    _create({"title": "Late", "eventDate": FUTURE_3, "time": "08:00"})
    body = client.get("/v1/events", params={"from": FUTURE_2}, headers=HEADERS).json()
    assert [i["title"] for i in body["items"]] == ["Late"]
    assert set(body["items"][0]) == {"id", "title", "eventType", "eventDate", "time"}


def test_list_deterministic_date_time_id_ordering():
    """Date asc, time asc NULLS LAST, id asc; repeats byte-identical."""
    _create({"title": "NoTime", "eventDate": FUTURE_2, "time": None})
    _create({"title": "Evening", "eventDate": FUTURE_2, "time": "18:00"})
    _create({"title": "Morning", "eventDate": FUTURE_2, "time": "09:00"})
    first = client.get("/v1/events", headers=HEADERS).json()
    assert [i["title"] for i in first["items"]] == ["Morning", "Evening", "NoTime"]
    second = client.get("/v1/events", headers=HEADERS).json()
    assert [i["id"] for i in second["items"]] == [i["id"] for i in first["items"]]


def test_list_order_desc():
    """order=desc reverses the date axis for the past window."""
    Session = make_session()
    with Session() as session:
        user_id = _dev_user_id()
        session.add(
            UserEvent(
                user_id=user_id, title="Old", event_type_id="casual",
                event_date=date(2000, 2, 2),
            )
        )
        session.commit()
    assert _create().status_code == 201
    body = client.get(
        "/v1/events", params={"from": PAST, "order": "desc"}, headers=HEADERS
    ).json()
    assert [i["title"] for i in body["items"]] == ["Company Gala", "Old"]


def test_list_pagination_defaults_and_bounds():
    """page 1 / page_size 20 defaults; slices; 100 ok; 101 and 0 → 422."""
    for day in range(1, 4):
        _create({"title": f"E{day}", "eventDate": f"2030-10-0{day}", "time": None})
    default = client.get("/v1/events", headers=HEADERS).json()
    assert (default["page"], default["page_size"], default["total"]) == (1, 20, 3)
    page1 = client.get(
        "/v1/events", params={"page": 1, "page_size": 2}, headers=HEADERS
    ).json()
    assert [i["title"] for i in page1["items"]] == ["E1", "E2"]
    assert page1["total"] == 3
    page2 = client.get(
        "/v1/events", params={"page": 2, "page_size": 2}, headers=HEADERS
    ).json()
    assert [i["title"] for i in page2["items"]] == ["E3"]
    assert client.get("/v1/events", params={"page_size": 100}, headers=HEADERS).status_code == 200
    assert client.get("/v1/events", params={"page_size": 101}, headers=HEADERS).status_code == 422
    assert client.get("/v1/events", params={"page": 0}, headers=HEADERS).status_code == 422


def test_list_invalid_sort_order_from_rejected():
    """Unknown sort/order and malformed from → 422."""
    assert client.get("/v1/events", params={"sort": "title"}, headers=HEADERS).status_code == 422
    assert client.get("/v1/events", params={"order": "sideways"}, headers=HEADERS).status_code == 422
    assert client.get("/v1/events", params={"from": "soon"}, headers=HEADERS).status_code == 422


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


def _created_id(body=None):
    resp = _create(body)
    assert resp.status_code == 201
    return resp.json()["id"]


def _full_update(event_id, body=None, headers=HEADERS):
    return client.put(f"/v1/events/{event_id}", json=body or _payload(), headers=headers)


def test_update_full_replacement():
    """PUT replaces every field and returns the updated UserEvent."""
    event_id = _created_id()
    resp = _full_update(
        event_id,
        {
            "title": "Renamed",
            "eventType": "party",
            "eventDate": FUTURE_3,
            "time": "20:30",
            "location": "Rooftop",
            "notes": "Bring gift",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == event_id
    assert (body["title"], body["eventType"], body["eventDate"]) == ("Renamed", "party", FUTURE_3)
    assert (body["time"], body["location"], body["notes"]) == ("20:30", "Rooftop", "Bring gift")


def test_update_nullable_clearing():
    """Explicit nulls clear time/location/notes."""
    event_id = _created_id()
    resp = _full_update(
        event_id,
        {
            "title": "Cleared",
            "eventType": "formal",
            "eventDate": FUTURE_2,
            "time": None,
            "location": None,
            "notes": None,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["time"] is None and body["location"] is None and body["notes"] is None


def test_update_validation():
    """Bounds, past dates, bad types/times, and empties → 422."""
    event_id = _created_id()
    assert _full_update(event_id, _payload(eventDate=PAST)).status_code == 422
    assert _full_update(event_id, _payload(eventType="nope")).status_code == 422
    assert _full_update(event_id, _payload(time="19:00:00")).status_code == 422
    assert _full_update(event_id, _payload(location="")).status_code == 422
    assert _full_update(event_id, _payload(notes="")).status_code == 422
    assert _full_update(event_id, _payload(title="x" * 201)).status_code == 422
    assert _full_update(event_id, _payload(location="x" * 201)).status_code == 422
    assert _full_update(event_id, _payload(notes="x" * 2001)).status_code == 422


def test_update_ownership_and_uuid():
    """Missing/foreign → 404 (never 403); malformed UUID → 422."""
    event_id = _created_id()
    _, foreign_id = _seed_foreign_event()
    assert _full_update(str(uuid4())).status_code == 404
    assert _full_update(str(foreign_id)).status_code == 404
    assert _full_update("not-a-uuid").status_code == 422
    # The failed updates changed nothing.
    assert client.get("/v1/events", headers=HEADERS).json()["total"] == 1
    assert event_id is not None


def test_update_bumps_updated_at():
    """updated_at advances on edit."""
    before = _create().json()
    after = _full_update(before["id"], _payload(title="Bumped")).json()
    assert after["updatedAt"] > before["updatedAt"]
    assert after["createdAt"] == before["createdAt"]


def test_update_writes_no_learning_signal():
    """UPDATE writes no learning signal."""
    event_id = _created_id()
    before = _signal_count()
    assert _full_update(event_id).status_code == 200
    assert _signal_count() == before


def test_r36_update_only_on_type_change():
    """Type change appends the new code (old kept); date-only → no-op."""
    event_id = _created_id({"eventType": "casual", "eventDate": FUTURE_1, "time": None})
    assert _preferred_occasions() == ["casual"]
    assert _full_update(
        event_id, _payload(eventType="party", eventDate=FUTURE_1, time=None)
    ).status_code == 200
    assert _preferred_occasions() == ["casual", "party"]
    assert _full_update(
        event_id, _payload(eventType="party", eventDate=FUTURE_3, time=None)
    ).status_code == 200
    assert _preferred_occasions() == ["casual", "party"]


def test_r36_update_failure_leaves_update_committed():
    """Preference-store failure still commits the event update."""
    Session = make_session()
    with Session() as session:
        user_id = _dev_user_id()
        repo_events = UserEventRepositorySQL(session)
        use_case = UpdateEvent(
            events=repo_events,
            event_types=EventTypeRepositorySQL(session),
            user_state=_FailingUserState(),
        )
        created = repo_events.create(
            user_id=user_id, title="Orig", event_type="casual",
            event_date=date(2030, 6, 6),
        )
        session.commit()
        updated = use_case(
            user_id=user_id, event_id=created.id, title="Changed",
            event_type="date", event_date=date(2030, 6, 7),
        )
        assert updated.title == "Changed"
        assert session.execute(
            select(UserEvent).where(UserEvent.id == created.id)
        ).scalar_one().title == "Changed"


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def test_delete_owned_event_returns_204_empty_and_removes_row():
    """Owner DELETE → 204 empty body; row gone; repeat → 404."""
    event_id = _created_id()
    resp = client.delete(f"/v1/events/{event_id}", headers=HEADERS)
    assert resp.status_code == 204
    assert resp.content == b""
    assert client.get("/v1/events", headers=HEADERS).json()["total"] == 0
    assert client.delete(f"/v1/events/{event_id}", headers=HEADERS).status_code == 404


def test_delete_missing_foreign_malformed():
    """Missing/foreign → 404 (never 403); malformed UUID → 422."""
    assert client.delete(f"/v1/events/{uuid4()}", headers=HEADERS).status_code == 404
    _, foreign_id = _seed_foreign_event()
    assert client.delete(f"/v1/events/{foreign_id}", headers=HEADERS).status_code == 404
    assert client.delete("/v1/events/not-a-uuid", headers=HEADERS).status_code == 422


def test_delete_leaves_preferences_history_and_signals():
    """DELETE touches no preferences and writes no signal."""
    client.patch("/v1/users/me", json={"preferredOccasions": ["formal"]}, headers=HEADERS)
    event_id = _created_id()
    before_signals = _signal_count()
    assert client.delete(f"/v1/events/{event_id}", headers=HEADERS).status_code == 204
    assert _preferred_occasions() == ["formal"]
    assert _signal_count() == before_signals


# ---------------------------------------------------------------------------
# AUTH
# ---------------------------------------------------------------------------


def test_unauthenticated_requests_rejected_401():
    """All four surfaces require auth."""
    event_id = _created_id()
    assert client.post("/v1/events", json=_payload()).status_code == 401
    assert client.get("/v1/events").status_code == 401
    assert client.put(f"/v1/events/{event_id}", json=_payload()).status_code == 401
    assert client.delete(f"/v1/events/{event_id}").status_code == 401


def test_cross_layer_lifecycle():
    """create → list → update → delete → list confirms the full loop."""
    assert client.get("/v1/events", headers=HEADERS).json()["total"] == 0
    event_id = _created_id()
    assert client.get("/v1/events", headers=HEADERS).json()["total"] == 1
    assert _full_update(event_id, _payload(title="Final")).status_code == 200
    assert client.delete(f"/v1/events/{event_id}", headers=HEADERS).status_code == 204
    assert client.get("/v1/events", headers=HEADERS).json() == {
        "items": [],
        "page": 1,
        "page_size": 20,
        "total": 0,
    }
