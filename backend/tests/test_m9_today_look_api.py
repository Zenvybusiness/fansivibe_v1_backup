"""API tests for M9 Today's Look (endpoints #31–33, UC-16/UC-17).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; each test starts truncated-clean).

Covers the task A–AD matrix: auth, empty-wardrobe 404, valid
derivation, UUID ownership (no local numeric IDs), deterministic
GET/POST, variant/seed validation, seed variation (best-effort),
nearest-event selection + type priority + pref dedup, no-event and
past-event paths, weather absence, no-candidate 404s, exact TodayLook
DTO shape (0–100 int scores, additive selectedItemIds, minimal
alternatives, sourceless keys absent), M7 save delegation
(daily sourceContext, replay, 409, fail-closed IDs, TRX-3
row+signal), outfit-save non-regression, and side-effect safety
(no wear, no extra signals, read-only derivation).
"""

from __future__ import annotations

import json
import re
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.infrastructure.db.models import UserEvent, Users
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}

BANNED_REASON = re.compile(
    r"weather|mood|perfect|comfort|flatter|\bslim\b|AI-|artificial|body type|silhouette",
    re.IGNORECASE,
)

# (name, category, color, material, is_favorite)
STANDARD_WARDROBE = [
    ("Tee", "tops", "black", None, False),
    ("Jeans", "bottoms", "white", None, False),
    ("Sneaks", "footwear", "white", None, False),
]

REQUIRED_KEYS = {
    "title",
    "description",
    "matchScore",
    "styleScore",
    "components",
    "reasons",
    "wardrobeContext",
    "alternatives",
    "selectedItemIds",
}

BANNED_KEYS = {
    "weather",
    "colorHex",
    "selectedMood",
    "selectedColorPalette",
    "colorHarmony",
    "bodyFit",
    "occasionMatch",
    "styleScoreImpact",
    "improvementSuggestion",
    "aiSelectionReason",
    "confidenceBoost",
    "aiInsights",
    "dailyStyleTip",
}


def _session():
    return make_session()()


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


def _seed_wardrobe(user_id, items=STANDARD_WARDROBE):
    with _session() as session:
        for name, category, color, material, favorite in items:
            session.execute(
                text(
                    "INSERT INTO wardrobe_items "
                    "(user_id, name, category_id, color_id, material_id, is_favorite) "
                    "VALUES (:u, :n, :c, :col, :m, :f)"
                ),
                {"u": str(user_id), "n": name, "c": category, "col": color,
                 "m": material, "f": favorite},
            )
        session.commit()


def _owner_item_ids(user_id):
    with _session() as session:
        rows = session.execute(
            text("SELECT id FROM wardrobe_items WHERE user_id = :u"), {"u": str(user_id)}
        ).scalars().all()
        return {str(value) for value in rows}


def _set_preferences(user_id, preferences):
    with _session() as session:
        session.execute(
            text("UPDATE user_state SET preferences = CAST(:p AS JSONB) WHERE user_id = :u"),
            {"p": json.dumps(preferences), "u": str(user_id)},
        )
        session.commit()


def _set_style_profile(user_id, profile):
    with _session() as session:
        session.execute(
            text("UPDATE user_state SET style_profile = CAST(:p AS JSONB) WHERE user_id = :u"),
            {"p": json.dumps(profile), "u": str(user_id)},
        )
        session.commit()


def _create_event(event_type="formal", title="Gala", event_date="2030-08-15"):
    resp = client.post(
        "/v1/events",
        json={"title": title, "eventType": event_type, "eventDate": event_date},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _create_past_event(user_id, event_type="party"):
    with _session() as session:
        event = UserEvent(
            user_id=user_id, title="Old Party", event_type_id=event_type,
            event_date=date(2020, 1, 1),
        )
        session.add(event)
        session.commit()
        return event.id


def _seed_foreign_item():
    """Direct-seeded other user with one wardrobe item; returns its UUID string."""
    with _session() as session:
        user = Users(
            auth_provider="m9", auth_subject=f"foreign-{uuid4()}", display_name="Foreign"
        )
        session.add(user)
        session.flush()
        session.execute(
            text(
                "INSERT INTO wardrobe_items (user_id, name, category_id, color_id) "
                "VALUES (:u, 'Foreign Jacket', 'outerwear', 'navy')"
            ),
            {"u": str(user.id)},
        )
        session.commit()
        row = session.execute(
            text("SELECT id FROM wardrobe_items WHERE user_id = :u"), {"u": str(user.id)}
        ).scalar_one()
        return str(row)


def _snapshot(user_id):
    """DB-count + preference snapshots proving read/derive purity."""
    with _session() as session:
        counts = {}
        for table in (
            "saved_looks",
            "learning_signals",
            "activity_days",
            "wardrobe_wear_events",
            "wardrobe_wear_groups",
            "wardrobe_items",
            "user_events",
        ):
            counts[table] = session.execute(
                text(f"SELECT COUNT(*) FROM {table}")
            ).scalar_one()
        prefs = session.execute(
            text("SELECT preferences FROM user_state WHERE user_id = :u"),
            {"u": str(user_id)},
        ).scalar_one_or_none()
        counts["preferences"] = json.dumps(prefs, sort_keys=True, default=str)
        return counts


def _get(params="", headers=HEADERS):
    return client.get(f"/v1/looks/today{params}", headers=headers)


def _post(params="", headers=HEADERS):
    return client.post(f"/v1/looks/today{params}", headers=headers)


def _body(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()


# A. GET authentication -----------------------------------------------------

def test_get_requires_auth():
    resp = client.get("/v1/looks/today")
    assert resp.status_code == 401


def test_post_requires_auth():
    resp = client.post("/v1/looks/today")
    assert resp.status_code == 401


def test_save_requires_auth():
    resp = client.post("/v1/looks/today/save", json={})
    assert resp.status_code == 401


# B. GET empty wardrobe -> 404 ----------------------------------------------

def test_get_empty_wardrobe_is_404():
    _dev_user_id()
    resp = _get()
    assert resp.status_code == 404


# C/D/E. valid derivation + UUID ownership + no local IDs -------------------

def test_get_valid_wardrobe_returns_today_look_with_owned_uuids():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    owned = _owner_item_ids(user_id)
    body = _body(_get())
    component_ids = [item["id"] for item in body["components"]]
    assert component_ids, "winner must cover owned items"
    for raw in component_ids:
        UUID(raw)  # parses as UUID — never a local numeric ID
    assert set(component_ids) <= owned
    assert "comp_" not in json.dumps(body)
    assert "alt_" not in json.dumps(body)


# F. deterministic repeated GET ---------------------------------------------

def test_repeated_get_is_byte_identical():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    first = _body(_get())
    second = _body(_get())
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# G. no side effects ----------------------------------------------------------

def test_get_and_post_are_read_only():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _set_preferences(user_id, {"preferred_occasions": ["casual"]})
    before = _snapshot(user_id)
    _body(_get())
    _body(_post())
    _body(_post(params="?seed=abc"))
    assert _snapshot(user_id) == before


# H. malformed variant -> 422 -------------------------------------------------

def test_blank_variant_is_422():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    assert _get(params="?variant=").status_code == 422


def test_oversize_variant_is_422():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    assert _get(params=f"?variant={'v' * 201}").status_code == 422


def test_oversize_seed_is_422():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    assert _post(params=f"?seed={'s' * 201}").status_code == 422


# I/J/K. POST seed behavior ---------------------------------------------------

def test_post_no_seed_matches_get():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    assert _body(_post()) == _body(_get())


def test_post_same_seed_is_deterministic():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    first = _body(_post(params="?seed=friday"))
    second = _body(_post(params="?seed=friday"))
    assert first == second


def test_post_different_seed_varies_best_effort():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    default_ids = _body(_post())["selectedItemIds"]
    varied = None
    for n in range(1, 21):
        candidate = _body(_post(params=f"?seed=seed-{n}"))["selectedItemIds"]
        if candidate != default_ids:
            varied = candidate
            break
    assert varied is not None, "expected some seed to pick another ranked candidate"
    assert varied != default_ids


# L/M/N. event influence ------------------------------------------------------

def test_nearest_event_wins_over_later_event():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _create_event(event_type="formal", title="Far Gala", event_date="2030-09-01")
    _create_event(event_type="party", title="Near Party", event_date="2030-08-15")
    body = _body(_get())
    assert body["occasion"] == "party"


def test_event_type_has_priority_over_preferences():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _set_preferences(user_id, {"preferred_occasions": ["workout"]})
    _create_event(event_type="formal", title="Gala")
    body = _body(_get())
    assert body["occasion"] == "formal"
    assert body["reasons"][0] == "Picked for a Formal occasion"


def test_duplicate_preference_occasion_dedupes():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _create_event(event_type="formal", title="Gala")
    _set_preferences(user_id, {"preferred_occasions": ["formal"]})
    with_dupe = _body(_get())
    _set_preferences(user_id, {"preferred_occasions": []})
    without_dupe = _body(_get())
    assert with_dupe == without_dupe


# O/P. no-event + past-event paths ---------------------------------------------

def test_no_event_derives_from_preferences():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _set_preferences(user_id, {"preferred_occasions": ["casual"]})
    body = _body(_get())
    assert body["occasion"] == "casual"
    assert body["title"] == "casual Look"


def test_no_event_no_prefs_derives_without_occasion():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    body = _body(_get())
    assert body["title"] == "Today's Look"
    assert "occasion" not in body


def test_past_events_are_ignored():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _set_preferences(user_id, {"preferred_occasions": ["casual"]})
    _create_past_event(user_id, event_type="party")
    body = _body(_get())
    assert body["occasion"] == "casual"


# Q. weather absence ------------------------------------------------------------

def test_weather_is_absent_not_fabricated():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    body = _body(_get())
    assert "weather" not in body
    assert "weather" not in json.dumps(body).lower()


# R. no legal candidate -> 404 --------------------------------------------------

def test_tops_only_wardrobe_is_404():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id, items=[("Lonely Tee", "tops", "black", None, False)])
    assert _get().status_code == 404
    assert _post().status_code == 404


# S. exact DTO shape --------------------------------------------------------------

def test_today_look_dto_shape_and_honesty():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _create_event(event_type="formal", title="Gala")
    body = _body(_get())
    assert REQUIRED_KEYS <= set(body)
    assert not (BANNED_KEYS & set(body))
    assert isinstance(body["matchScore"], int) and 0 <= body["matchScore"] <= 100
    assert isinstance(body["styleScore"], int) and 0 <= body["styleScore"] <= 100
    # styleScore is the derivation's own score — never the banned 87 default.
    assert body["styleScore"] == body["matchScore"]
    assert body["components"] and body["reasons"]
    for item in body["components"]:
        assert {"id", "name", "category", "color"} <= set(item)
        assert "colorHex" not in item
        assert "reason" not in item
    assert set(body["wardrobeContext"]) == {"totalItems", "matchingItems"}
    assert body["wardrobeContext"]["totalItems"] == 3
    assert body["wardrobeContext"]["matchingItems"] == len(body["selectedItemIds"])
    for alt in body["alternatives"]:
        assert set(alt) == {"id", "matchScore"}
        assert isinstance(alt["matchScore"], int)
    assert "styleDna" not in body  # empty profile omits it (gap tolerance)
    haystack = " ".join([body["title"], body["description"], *body["reasons"]])
    assert not BANNED_REASON.search(haystack)


def test_style_dna_projects_present_subfields_only():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _set_style_profile(
        user_id, {"face_shape": "Oval", "skin_tone": "", "body_type": "Athletic"}
    )
    body = _body(_get())
    assert body["styleDna"] == {"bodyType": "Athletic", "faceShape": "Oval"}


# T/U. selectedItemIds + owned components ------------------------------------------

def test_selected_item_ids_sorted_unique_and_owned():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    owned = _owner_item_ids(user_id)
    body = _body(_get())
    ids = body["selectedItemIds"]
    assert ids == sorted(set(ids))
    assert set(ids) == {item["id"] for item in body["components"]}
    assert set(ids) <= owned


# V/W/X/Y/Z/AA. save delegation ------------------------------------------------------

def _derived_snapshot():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    return user_id, _body(_get())


def test_save_daily_persists_row_and_single_signal():
    user_id, snapshot = _derived_snapshot()
    resp = client.post(
        "/v1/looks/today/save",
        json={"title": "Friday Look", "sourceContext": "daily", "snapshot": snapshot},
        headers={**HEADERS, "Idempotency-Key": "m9-key-1"},
    )
    assert resp.status_code == 201, resp.text
    saved = resp.json()
    assert saved["sourceContext"] == "daily"
    assert saved["snapshot"]["selectedItemIds"] == snapshot["selectedItemIds"]
    with _session() as session:
        row = session.execute(
            text("SELECT source_context FROM saved_looks WHERE id = :i"),
            {"i": saved["id"]},
        ).scalar_one()
        assert row == "daily"
        signals = session.execute(
            text('SELECT signal_type, label, "context" FROM learning_signals')
        ).all()
        assert len(signals) == 1
        assert signals[0][0] == "look_saved"
        assert signals[0][1] == "Friday Look"
        assert signals[0][2] == {"source_context": "daily", "look_id": None}


def test_save_replay_returns_original():
    _, snapshot = _derived_snapshot()
    payload = {"title": "Replay Look", "sourceContext": "daily", "snapshot": snapshot}
    headers = {**HEADERS, "Idempotency-Key": "m9-key-2"}
    first = client.post("/v1/looks/today/save", json=payload, headers=headers)
    second = client.post("/v1/looks/today/save", json=payload, headers=headers)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    with _session() as session:
        total = session.execute(text("SELECT COUNT(*) FROM saved_looks")).scalar_one()
        assert total == 1


def test_save_conflicting_key_is_409():
    _, snapshot = _derived_snapshot()
    headers = {**HEADERS, "Idempotency-Key": "m9-key-3"}
    first = client.post(
        "/v1/looks/today/save",
        json={"title": "Original", "sourceContext": "daily", "snapshot": snapshot},
        headers=headers,
    )
    assert first.status_code == 201
    conflict = client.post(
        "/v1/looks/today/save",
        json={"title": "Changed", "sourceContext": "daily", "snapshot": snapshot},
        headers=headers,
    )
    assert conflict.status_code == 409


def test_save_requires_idempotency_key():
    _, snapshot = _derived_snapshot()
    resp = client.post(
        "/v1/looks/today/save",
        json={"title": "No Key", "sourceContext": "daily", "snapshot": snapshot},
        headers=HEADERS,
    )
    assert resp.status_code == 422


def test_save_rejects_non_daily_context():
    _, snapshot = _derived_snapshot()
    resp = client.post(
        "/v1/looks/today/save",
        json={"title": "Wrong", "sourceContext": "outfit", "snapshot": snapshot},
        headers={**HEADERS, "Idempotency-Key": "m9-key-4"},
    )
    assert resp.status_code == 422


def test_save_local_ids_fail_closed():
    _, snapshot = _derived_snapshot()
    bad = {**snapshot, "selectedItemIds": ["1"]}
    resp = client.post(
        "/v1/looks/today/save",
        json={"title": "Local", "sourceContext": "daily", "snapshot": bad},
        headers={**HEADERS, "Idempotency-Key": "m9-key-5"},
    )
    assert resp.status_code == 422
    with _session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM saved_looks")).scalar_one() == 0


def test_save_foreign_ids_fail_closed():
    _, snapshot = _derived_snapshot()
    foreign_id = _seed_foreign_item()
    bad = {**snapshot, "selectedItemIds": [foreign_id]}
    resp = client.post(
        "/v1/looks/today/save",
        json={"title": "Foreign", "sourceContext": "daily", "snapshot": bad},
        headers={**HEADERS, "Idempotency-Key": "m9-key-6"},
    )
    assert resp.status_code == 404
    with _session() as session:
        assert session.execute(text("SELECT COUNT(*) FROM saved_looks")).scalar_one() == 0


def test_save_malformed_uuid_fails_closed():
    _, snapshot = _derived_snapshot()
    bad = {**snapshot, "selectedItemIds": ["not-a-uuid"]}
    resp = client.post(
        "/v1/looks/today/save",
        json={"title": "Malformed", "sourceContext": "daily", "snapshot": bad},
        headers={**HEADERS, "Idempotency-Key": "m9-key-7"},
    )
    assert resp.status_code == 422


# AB. outfit-save non-regression -------------------------------------------------------

def test_outfit_save_still_works_and_wardrobe_still_422():
    user_id, snapshot = _derived_snapshot()
    owned = sorted(_owner_item_ids(user_id))
    outfit_snapshot = {**snapshot, "selectedItemIds": owned}
    ok = client.post(
        "/v1/looks/saved",
        json={"title": "Outfit", "sourceContext": "outfit", "snapshot": outfit_snapshot},
        headers={**HEADERS, "Idempotency-Key": "m9-key-8"},
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["sourceContext"] == "outfit"
    bad = client.post(
        "/v1/looks/saved",
        json={"title": "Bad", "sourceContext": "wardrobe", "snapshot": {}},
        headers={**HEADERS, "Idempotency-Key": "m9-key-9"},
    )
    assert bad.status_code == 422
    bad_daily = client.post(
        "/v1/looks/saved",
        json={"title": "Bad", "sourceContext": "wardrobe", "snapshot": {}},
        headers={**HEADERS, "Idempotency-Key": "m9-key-10"},
    )
    assert bad_daily.status_code == 422


def test_daily_save_visible_in_saved_list_and_deletable():
    _, snapshot = _derived_snapshot()
    saved = client.post(
        "/v1/looks/today/save",
        json={"title": "List Me", "sourceContext": "daily", "snapshot": snapshot},
        headers={**HEADERS, "Idempotency-Key": "m9-key-11"},
    )
    assert saved.status_code == 201
    listing = client.get("/v1/looks/saved", headers=HEADERS)
    assert listing.status_code == 200
    rows = [row for row in listing.json()["items"] if row["id"] == saved.json()["id"]]
    assert len(rows) == 1 and rows[0]["sourceContext"] == "daily"
    deleted = client.delete(f"/v1/looks/saved/{saved.json()['id']}", headers=HEADERS)
    assert deleted.status_code == 204
    gone = client.get("/v1/looks/saved", headers=HEADERS).json()["items"]
    assert all(row["id"] != saved.json()["id"] for row in gone)


# AC/AD. no wear, no extra signals --------------------------------------------------------

def test_save_writes_no_wear_and_no_extra_signals():
    _, snapshot = _derived_snapshot()
    before_wears = _snapshot_wears()
    resp = client.post(
        "/v1/looks/today/save",
        json={"title": "Clean", "sourceContext": "daily", "snapshot": snapshot},
        headers={**HEADERS, "Idempotency-Key": "m9-key-12"},
    )
    assert resp.status_code == 201
    assert _snapshot_wears() == before_wears
    with _session() as session:
        signals = session.execute(text("SELECT signal_type FROM learning_signals")).all()
        assert [row[0] for row in signals] == ["look_saved"]


def _snapshot_wears():
    with _session() as session:
        return {
            table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in ("wardrobe_wear_events", "wardrobe_wear_groups")
        }
