"""API tests for M13 outfit generation + save (#41–42, UC-28/29/30).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; each test starts truncated-clean).

Covers: auth, empty/sparse wardrobe 204s, preference validation,
exact ensemble DTO shape (0..1 score, UUID-only components, no
alternatives, no fabricated keys/claims), deterministic generation +
seed selection, occasion echo isolation from events/prefs, read-only
derivation proof, M7 save delegation (outfit sourceContext, replay,
409, fail-closed IDs, TRX-3 row+signal), and side-effect safety
(no wear, no extra signals).
"""

from __future__ import annotations

import json
import re
from uuid import UUID, uuid4

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

BANNED_PROSE = re.compile(
    r"weather|perfect|comfort|flatter|AI-|artificial|body type|silhouette",
    re.IGNORECASE,
)

# (name, category, color, material, is_favorite)
RICH_WARDROBE = [
    ("Tee A", "tops", "black", None, False),
    ("Tee B", "tops", "white", None, False),
    ("Shirt", "tops", "navy", None, True),
    ("Jeans", "bottoms", "white", None, False),
    ("Chinos", "bottoms", "black", None, False),
    ("Blazer", "outerwear", "navy", None, False),
    ("Sneaks", "footwear", "white", None, False),
    ("Belt", "accessories", "black", None, False),
]

PREFS = {
    "occasion": "office",
    "mood": "classic",
    "fit": "tailored",
    "colorPalette": "warm",
}

REQUIRED_KEYS = {
    "title",
    "matchScore",
    "components",
    "reasons",
    "colorHarmony",
    "bodyFit",
    "occasionMatch",
    "styleScoreImpact",
    "improvementSuggestion",
    "selectedOccasion",
    "selectedMood",
    "selectedColorPalette",
}

BANNED_KEYS = {
    "colorHex",
    "alternatives",
    "description",
    "weather",
    "confidence",
    "tradeOffs",
    "expiresAt",
    "occasion",
    "styleDna",
    "wardrobeContext",
}


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


def _seed_wardrobe(user_id, items=RICH_WARDROBE):
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


def _seed_foreign_item():
    """Direct-seeded other user with one wardrobe item; returns its UUID string."""
    with _session() as session:
        user = Users(
            auth_provider="m13", auth_subject=f"foreign-{uuid4()}", display_name="Foreign"
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


def _generate(payload=None, headers=HEADERS):
    return client.post(
        "/v1/outfits/generate", json=dict(PREFS) if payload is None else payload,
        headers=headers,
    )


def _body(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()


# A. authentication -------------------------------------------------------

def test_generate_requires_auth():
    assert client.post("/v1/outfits/generate", json=PREFS).status_code == 401


def test_save_requires_auth():
    assert client.post("/v1/outfits/saved", json={}).status_code == 401


# B. empty / sparse wardrobe -> 204 ---------------------------------------

def test_generate_empty_wardrobe_is_204():
    _dev_user_id()
    resp = _generate()
    assert resp.status_code == 204, resp.text
    assert resp.content == b""


def test_generate_tops_only_is_204():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id, items=[("Lonely Tee", "tops", "black", None, False)])
    assert _generate().status_code == 204


# C. preference validation -> 422 -----------------------------------------

def test_generate_missing_preference_is_422():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    for field in ("occasion", "mood", "fit", "colorPalette"):
        payload = dict(PREFS)
        del payload[field]
        assert _generate(payload).status_code == 422, field


def test_generate_blank_preference_is_422():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    for field in ("occasion", "mood", "fit", "colorPalette"):
        for bad in ("", "   "):
            payload = dict(PREFS)
            payload[field] = bad
            assert _generate(payload).status_code == 422, (field, bad)


def test_generate_overlong_preference_is_422():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    payload = dict(PREFS)
    payload["occasion"] = "x" * 201
    assert _generate(payload).status_code == 422


def test_generate_non_string_preference_is_422():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    payload = dict(PREFS)
    payload["fit"] = 42
    assert _generate(payload).status_code == 422


# D. seed validation -> 422 -----------------------------------------------

def test_generate_bad_seed_is_422():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    for bad in ("", "x" * 201, 42):
        payload = dict(PREFS)
        payload["seed"] = bad
        assert _generate(payload).status_code == 422, repr(bad)


# E. valid derivation + UUID ownership ------------------------------------

def test_generate_valid_wardrobe_returns_outfit_with_owned_uuids():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    owned = _owner_item_ids(user_id)
    body = _body(_generate())
    component_ids = [item["id"] for item in body["components"]]
    assert component_ids, "winner must cover owned items"
    for raw in component_ids:
        UUID(raw)  # parses as UUID — never a local numeric ID
    assert set(component_ids) <= owned
    assert "top_" not in json.dumps(body)
    assert "acc_" not in json.dumps(body)


def test_generate_ignores_foreign_items():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    foreign_id = _seed_foreign_item()
    body = _body(_generate())
    component_ids = {item["id"] for item in body["components"]}
    assert foreign_id not in component_ids


# F. exact DTO shape + honesty --------------------------------------------

def test_outfit_dto_shape_and_honesty():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    body = _body(_generate())
    assert REQUIRED_KEYS <= set(body)
    assert not (BANNED_KEYS & set(body))
    assert isinstance(body["matchScore"], float) and 0 <= body["matchScore"] <= 1
    assert body["title"] == "Office Outfit"
    assert body["components"] and body["reasons"]
    for item in body["components"]:
        assert {"id", "name", "category", "color", "reason"} <= set(item)
        assert "colorHex" not in item
    assert body["selectedOccasion"] == "office"
    assert body["selectedMood"] == "classic"
    assert body["selectedColorPalette"] == "warm"
    haystack = " ".join(
        [body["title"], *body["reasons"], body["colorHarmony"], body["bodyFit"],
         body["occasionMatch"], body["styleScoreImpact"],
         body["improvementSuggestion"]]
    )
    assert not BANNED_PROSE.search(haystack)


def test_outfit_reasons_are_grounded():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    owned_names = set()
    with _session() as session:
        rows = session.execute(
            text("SELECT name FROM wardrobe_items WHERE user_id = :u"),
            {"u": str(user_id)},
        ).scalars().all()
        owned_names = set(rows)
    body = _body(_generate())
    assert body["reasons"][0].startswith("Picked for a Office occasion")
    assert body["reasons"][1].startswith("Covers ")
    for extra in body["reasons"][2:]:
        assert extra.startswith("Includes your favorite ")
        assert extra[len("Includes your favorite "):] in owned_names


def test_metric_prose_states_facts_only():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    body = _body(_generate())
    n = len(body["components"])
    assert "warm" in body["colorHarmony"]
    assert str(n) in body["colorHarmony"]
    assert "tailored" in body["bodyFit"]
    assert "Office" in body["occasionMatch"]
    assert "%" in body["styleScoreImpact"]
    assert "owned pieces" in body["styleScoreImpact"]
    assert body["improvementSuggestion"], "must always carry a suggestion"


# G. determinism + seed selection -----------------------------------------

def test_repeated_generate_is_byte_identical():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    first = _body(_generate())
    second = _body(_generate())
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_same_seed_repeats_identically():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    payload = dict(PREFS)
    payload["seed"] = "outfit-7"
    first = _body(_generate(payload))
    second = _body(_generate(payload))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_different_seed_returns_valid_recommendation():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    payload = dict(PREFS)
    payload["seed"] = "outfit-zzz"
    body = _body(_generate(payload))
    assert REQUIRED_KEYS <= set(body)


# H. read-only derivation ---------------------------------------------------

def test_generate_has_no_side_effects():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _set_preferences(user_id, {"preferred_occasions": ["casual"]})
    before = _snapshot(user_id)
    _body(_generate())
    payload = dict(PREFS)
    payload["seed"] = "outfit-9"
    _body(_generate(payload))
    assert _snapshot(user_id) == before


# I. occasion echo isolation (no event/prefs leakage into echoes) ---------

def test_selected_echoes_come_from_request_not_events_or_prefs():
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _set_preferences(user_id, {"preferred_occasions": ["party"]})
    resp = client.post(
        "/v1/events",
        json={"title": "Gala", "eventType": "formal", "eventDate": "2030-08-15"},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    body = _body(_generate())
    assert body["selectedOccasion"] == "office"
    assert body["selectedMood"] == "classic"
    assert body["selectedColorPalette"] == "warm"


# J. save delegation --------------------------------------------------------

def _derived_snapshot():
    _seed_wardrobe(_dev_user_id())
    return _body(_generate())


def test_save_outfit_persists_row_and_single_signal():
    snapshot = _derived_snapshot()
    resp = client.post(
        "/v1/outfits/saved",
        json={"title": "Office Outfit", "sourceContext": "outfit", "snapshot": snapshot},
        headers={**HEADERS, "Idempotency-Key": "m13-key-1"},
    )
    assert resp.status_code == 201, resp.text
    saved = resp.json()
    assert saved["sourceContext"] == "outfit"
    assert saved["snapshot"]["components"] == snapshot["components"]
    with _session() as session:
        row = session.execute(
            text("SELECT source_context FROM saved_looks WHERE id = :i"),
            {"i": saved["id"]},
        ).scalar_one()
        assert row == "outfit"
        signals = session.execute(
            text('SELECT signal_type, label, "context" FROM learning_signals')
        ).all()
        assert len(signals) == 1
        assert signals[0][0] == "look_saved"
        assert signals[0][1] == "Office Outfit"
        assert signals[0][2] == {"source_context": "outfit", "look_id": None}


def test_save_replay_returns_original():
    snapshot = _derived_snapshot()
    payload = {"title": "Replay Look", "sourceContext": "outfit", "snapshot": snapshot}
    headers = {**HEADERS, "Idempotency-Key": "m13-key-2"}
    first = client.post("/v1/outfits/saved", json=payload, headers=headers)
    second = client.post("/v1/outfits/saved", json=payload, headers=headers)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    with _session() as session:
        total = session.execute(text("SELECT COUNT(*) FROM saved_looks")).scalar_one()
        assert total == 1


def test_save_conflicting_key_is_409():
    snapshot = _derived_snapshot()
    headers = {**HEADERS, "Idempotency-Key": "m13-key-3"}
    first = client.post(
        "/v1/outfits/saved",
        json={"title": "Original", "sourceContext": "outfit", "snapshot": snapshot},
        headers=headers,
    )
    assert first.status_code == 201
    conflict = client.post(
        "/v1/outfits/saved",
        json={"title": "Changed", "sourceContext": "outfit", "snapshot": snapshot},
        headers=headers,
    )
    assert conflict.status_code == 409


def test_save_requires_idempotency_key():
    snapshot = _derived_snapshot()
    resp = client.post(
        "/v1/outfits/saved",
        json={"title": "No Key", "sourceContext": "outfit", "snapshot": snapshot},
        headers=HEADERS,
    )
    assert resp.status_code == 422


def test_save_rejects_non_outfit_context():
    snapshot = _derived_snapshot()
    resp = client.post(
        "/v1/outfits/saved",
        json={"title": "Wrong", "sourceContext": "daily", "snapshot": snapshot},
        headers={**HEADERS, "Idempotency-Key": "m13-key-4"},
    )
    assert resp.status_code == 422


def test_save_local_ids_fail_closed():
    snapshot = _derived_snapshot()
    bad = json.loads(json.dumps(snapshot))
    bad["components"][0]["id"] = "1"
    resp = client.post(
        "/v1/outfits/saved",
        json={"title": "Local", "sourceContext": "outfit", "snapshot": bad},
        headers={**HEADERS, "Idempotency-Key": "m13-key-5"},
    )
    assert resp.status_code == 422
    with _session() as session:
        total = session.execute(text("SELECT COUNT(*) FROM saved_looks")).scalar_one()
        assert total == 0


def test_save_malformed_uuid_is_422():
    snapshot = _derived_snapshot()
    bad = json.loads(json.dumps(snapshot))
    bad["components"][0]["id"] = "not-a-uuid"
    resp = client.post(
        "/v1/outfits/saved",
        json={"title": "Malformed", "sourceContext": "outfit", "snapshot": bad},
        headers={**HEADERS, "Idempotency-Key": "m13-key-6"},
    )
    assert resp.status_code == 422


def test_save_unknown_uuid_is_404_with_nothing_stored():
    snapshot = _derived_snapshot()
    bad = json.loads(json.dumps(snapshot))
    bad["components"][0]["id"] = str(uuid4())
    resp = client.post(
        "/v1/outfits/saved",
        json={"title": "Unknown", "sourceContext": "outfit", "snapshot": bad},
        headers={**HEADERS, "Idempotency-Key": "m13-key-7"},
    )
    assert resp.status_code == 404
    with _session() as session:
        total = session.execute(text("SELECT COUNT(*) FROM saved_looks")).scalar_one()
        assert total == 0


def test_save_foreign_uuid_is_404_with_nothing_stored():
    snapshot = _derived_snapshot()
    foreign_id = _seed_foreign_item()
    bad = json.loads(json.dumps(snapshot))
    bad["components"][0]["id"] = foreign_id
    resp = client.post(
        "/v1/outfits/saved",
        json={"title": "Foreign", "sourceContext": "outfit", "snapshot": bad},
        headers={**HEADERS, "Idempotency-Key": "m13-key-8"},
    )
    assert resp.status_code == 404
    with _session() as session:
        total = session.execute(text("SELECT COUNT(*) FROM saved_looks")).scalar_one()
        assert total == 0


def test_save_empty_or_missing_components_is_422():
    snapshot = _derived_snapshot()
    for broken in ({**snapshot, "components": []}, {"title": "x"}):
        resp = client.post(
            "/v1/outfits/saved",
            json={"title": "Broken", "sourceContext": "outfit", "snapshot": broken},
            headers={**HEADERS, "Idempotency-Key": f"m13-key-9-{len(json.dumps(broken))}"},
        )
        assert resp.status_code == 422, broken


def test_save_writes_no_wear_and_single_signal():
    user_id = _dev_user_id()
    snapshot = _derived_snapshot()
    before = _snapshot(user_id)
    resp = client.post(
        "/v1/outfits/saved",
        json={"title": "Clean Save", "sourceContext": "outfit", "snapshot": snapshot},
        headers={**HEADERS, "Idempotency-Key": "m13-key-10"},
    )
    assert resp.status_code == 201
    after = _snapshot(user_id)
    assert after["wardrobe_wear_events"] == before["wardrobe_wear_events"] == 0
    assert after["wardrobe_wear_groups"] == before["wardrobe_wear_groups"] == 0
    assert after["saved_looks"] == before["saved_looks"] + 1
    assert after["learning_signals"] == before["learning_signals"] + 1
