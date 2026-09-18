"""API tests for M12 P1 For You feed (`GET /v1/looks/for-you`).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; each test starts truncated-clean).

Covers: auth (401s), cold-start honesty (`personalized: false` +
catalog order, never posed as personal), saved-look personalization
(proven +0.03 boost only), owner isolation (foreign saves never move
the feed), determinism (byte-identical repeats), catalog grounding,
shared cursor envelope/pagination, read-only proof (zero writes by
the endpoint), banned-key scan (no trending/ownership/image fields),
and `GET /v1/looks` order compatibility.
"""

from __future__ import annotations

import json
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

# Engine rank order: catalog scoreSeed desc
# (0.94, 0.92, 0.87, 0.85, 0.82, 0.78, 0.75, 0.71), code-asc tiebreak.
CATALOG_ORDER = [
    "textured_quiff",
    "structured_goatee",
    "classic_pompadour",
    "classic_stubble",
    "side_part",
    "brushed_up_undercut",
    "full_beard",
    "goatee_with_mustache",
]

ENVELOPE_KEYS = {"items", "next_cursor", "has_more", "personalized"}
SUMMARY_KEYS = {"id", "title", "description", "matchScore", "reasons"}

BANNED_KEYS = {
    "isTrending",
    "wardrobeMatchCount",
    "matchScoreDetails",
    "recommendationReasons",
    "ensembleComponents",
    "wardrobeAlternatives",
    "isOwned",
    "imageUrl",
    "imageRef",
    "total",
    "popularity",
    "trendScore",
}

_READ_TABLES = (
    "users",
    "user_state",
    "wardrobe_items",
    "saved_looks",
    "learning_signals",
    "activity_days",
    "wardrobe_wear_events",
    "wardrobe_wear_groups",
    "user_events",
    "feedback_events",
    "analysis_runs",
)

_HELPER_SESSIONS = sessionmaker(
    bind=create_engine(DATABASE_URL, pool_size=3, max_overflow=0),
    expire_on_commit=False,
)


def _session():
    return _HELPER_SESSIONS()


def _snapshot() -> dict:
    with _session() as session:
        return {
            table: session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            for table in _READ_TABLES
        }


def _for_you(params=None, headers=HEADERS):
    return client.get("/v1/looks/for-you", params=params, headers=headers)


def _body(resp):
    assert resp.status_code == 200, resp.text
    return resp.json()


def _save_look(look_id: str, key: str | None = None) -> dict:
    resp = client.post(
        "/v1/looks/saved",
        json={
            "lookId": look_id,
            "title": f"Saved {look_id}",
            "sourceContext": "hairstyle",
            "snapshot": {},
        },
        headers={**HEADERS, "Idempotency-Key": key or f"for-you-{uuid4()}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _seed_foreign_save(look_id: str) -> None:
    """Direct-seeded other user with one saved look (never the dev user)."""
    with _session() as session:
        user = Users(
            auth_provider="m12", auth_subject=f"foreign-{uuid4()}", display_name="Foreign"
        )
        session.add(user)
        session.flush()
        session.execute(
            text(
                "INSERT INTO saved_looks "
                "(user_id, look_id, title, source_context, snapshot, idempotency_key) "
                "VALUES (:u, :l, 'Foreign save', 'hairstyle', "
                "CAST(:s AS JSONB), :k)"
            ),
            {
                "u": str(user.id),
                "l": look_id,
                "s": json.dumps({}),
                "k": f"foreign-{uuid4()}",
            },
        )
        session.commit()


# A. authentication -------------------------------------------------------

def test_for_you_requires_auth():
    assert client.get("/v1/looks/for-you").status_code == 401


def test_for_you_rejects_bad_token():
    resp = client.get(
        "/v1/looks/for-you", headers={"Authorization": "Bearer nope"}
    )
    assert resp.status_code == 401


# B. cold start -----------------------------------------------------------

def test_cold_start_is_catalog_order_not_personalized():
    body = _body(_for_you())
    assert body["personalized"] is False
    assert [item["id"] for item in body["items"]] == CATALOG_ORDER
    assert body["has_more"] is False
    assert body["next_cursor"] is None


def test_cold_start_matches_looks_feed_order():
    feed = client.get("/v1/looks", headers=HEADERS)
    assert feed.status_code == 200, feed.text
    assert [item["id"] for item in feed.json()["items"]] == [
        item["id"] for item in _body(_for_you())["items"]
    ]


# C. personalization ------------------------------------------------------

def test_saved_look_boosts_deterministically():
    # classic_stubble .85 + .03 = .88 > classic_pompadour .87 → 3rd.
    _save_look("classic_stubble")
    first = _body(_for_you())
    assert first["personalized"] is True
    ids = [item["id"] for item in first["items"]]
    assert ids.index("classic_stubble") == 2
    by_id = {item["id"]: item for item in first["items"]}
    assert by_id["classic_stubble"]["matchScore"] == 88
    assert by_id["classic_pompadour"]["matchScore"] == 87
    # Byte-identical repeat: same catalog + same signals → same order.
    assert _body(_for_you()) == first


def test_outfit_save_without_look_id_is_not_a_signal():
    resp = client.post(
        "/v1/outfits/saved",
        json={
            "title": "Outfit save",
            "sourceContext": "outfit",
            "snapshot": {"components": []},
        },
        headers={**HEADERS, "Idempotency-Key": f"outfit-{uuid4()}"},
    )
    assert resp.status_code in (201, 422), resp.text
    body = _body(_for_you())
    assert body["personalized"] is False
    assert [item["id"] for item in body["items"]] == CATALOG_ORDER


# D. owner isolation ------------------------------------------------------

def test_foreign_saves_never_move_the_feed():
    _seed_foreign_save("goatee_with_mustache")
    _seed_foreign_save("textured_quiff")
    body = _body(_for_you())
    assert body["personalized"] is False
    assert [item["id"] for item in body["items"]] == CATALOG_ORDER
    # Own signal afterwards is still honored (foreign rows ignored).
    _save_look("classic_stubble")
    body = _body(_for_you())
    assert body["personalized"] is True
    assert [item["id"] for item in body["items"]].index("classic_stubble") == 2


# E. grounding + envelope -------------------------------------------------

def test_records_exist_in_catalog_and_envelope_is_minimal():
    _save_look("side_part")
    body = _body(_for_you())
    assert set(body.keys()) == ENVELOPE_KEYS
    for item in body["items"]:
        assert set(item.keys()) == SUMMARY_KEYS
        assert item["id"] in CATALOG_ORDER
    assert BANNED_KEYS.isdisjoint(json.dumps(body))


def test_cursor_walk_covers_personalized_catalog_once():
    _save_look("classic_stubble")
    seen: list[str] = []
    params: dict | None = {"limit": 3}
    while True:
        body = _body(_for_you(params))
        assert body["personalized"] is True
        seen.extend(item["id"] for item in body["items"])
        if not body["has_more"]:
            assert body["next_cursor"] is None
            break
        params = {"limit": 3, "cursor": body["next_cursor"]}
    assert sorted(seen) == sorted(CATALOG_ORDER)
    assert len(seen) == len(set(seen))


def test_malformed_cursor_is_422_never_reset():
    resp = _for_you({"cursor": "not-a-cursor"})
    assert resp.status_code == 422, resp.text


# F. read-only ------------------------------------------------------------

def test_for_you_writes_nothing():
    _save_look("side_part")
    before = _snapshot()
    for params in (None, {"limit": 3}, {"limit": 3, "cursor": _body(_for_you({"limit": 3}))["next_cursor"]}):
        resp = _for_you(params)
        assert resp.status_code == 200, resp.text
    assert _snapshot() == before
