"""API tests for M14 Discover feed + detail (#43–44, UC-31).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; each test starts truncated-clean).

Covers: auth (401s), feed cursor envelope shape (no `total`), exact
summary/detail DTO shapes with banned-key scans (no invented
imageUrl/occasion/tags/ensemble/ownership/trending fields), honest-422
filter behavior (DEC-014 P-3: any occasion/style/fit → 422 with no
`allowed` list), engine-ranked determinism (scoreSeed-desc, code-asc
tiebreak — the canonical ordering, no second engine), full cursor walk
over all 8 catalog rows, limit default/bounds, malformed/unknown cursor
422s (never silently reset), detail 200/404 with feed-detail score
parity, route-ordering guard (`/today*` + `/saved*` unaffected), and
read-only proof (zero writes anywhere).
"""

from __future__ import annotations

import base64
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.infrastructure.db.models import Users
from app.infrastructure.db.session import DATABASE_URL

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}

# Expected engine rank order: catalog scoreSeed desc
# (0.94, 0.92, 0.87, 0.85, 0.82, 0.78, 0.75, 0.71), code-asc tiebreak.
EXPECTED_ORDER = [
    ("textured_quiff", 94),
    ("structured_goatee", 92),
    ("classic_pompadour", 87),
    ("classic_stubble", 85),
    ("side_part", 82),
    ("brushed_up_undercut", 78),
    ("full_beard", 75),
    ("goatee_with_mustache", 71),
]

SUMMARY_KEYS = {"id", "title", "description", "matchScore", "reasons"}
DETAIL_KEYS = SUMMARY_KEYS | {"stylingTips", "maintenance", "bestFor"}

# Fields with no grounded source for these rows (AI-0: absent, never
# fabricated) — must never appear on the wire.
BANNED_KEYS = {
    "imageUrl",
    "imageRef",
    "occasion",
    "styleTags",
    "fitTags",
    "wardrobeMatchCount",
    "matchScoreDetails",
    "recommendationReasons",
    "ensembleComponents",
    "wardrobeAlternatives",
    "isTrending",
    "isOwned",
    "confidence",
    "tradeOffs",
    "weather",
    "colorHex",
    "total",
    "page",
    "page_size",
    "code",
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

# Module-shared engine for helpers: one small pool for the whole file
# (per-call engines exhaust connection slots across a full-file run).
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


def _error_body(response) -> dict:
    return response.json()["error"]


# ---------------------------------------------------------------------------
# A. Auth
# ---------------------------------------------------------------------------


def test_feed_requires_auth():
    response = client.get("/v1/looks")
    assert response.status_code == 401
    assert _error_body(response)["code"] == "AUTHENTICATION_ERROR"


def test_feed_rejects_bad_token():
    response = client.get("/v1/looks", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_detail_requires_auth():
    response = client.get("/v1/looks/textured_quiff")
    assert response.status_code == 401
    assert _error_body(response)["code"] == "AUTHENTICATION_ERROR"


def test_detail_rejects_bad_token():
    response = client.get(
        "/v1/looks/textured_quiff", headers={"Authorization": "Bearer nope"}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# B. Feed shape
# ---------------------------------------------------------------------------


def test_feed_envelope_shape():
    response = client.get("/v1/looks", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "next_cursor", "has_more"}
    assert isinstance(body["items"], list)
    assert body["has_more"] is False
    assert body["next_cursor"] is None


def test_feed_summary_item_shape_and_no_banned_keys():
    response = client.get("/v1/looks", headers=HEADERS)
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 8
    for item in items:
        assert set(item.keys()) == SUMMARY_KEYS
        assert BANNED_KEYS.isdisjoint(item.keys())
        assert isinstance(item["id"], str) and item["id"]
        # `id` is the stable catalog code (PR-3) — never a UUID.
        try:
            UUID(item["id"])
        except ValueError:
            pass
        else:
            raise AssertionError(f"catalog id must not be a UUID: {item['id']}")
        assert isinstance(item["title"], str) and item["title"]
        assert isinstance(item["description"], str) and item["description"]
        assert isinstance(item["matchScore"], int)
        assert 0 <= item["matchScore"] <= 100
        assert isinstance(item["reasons"], list) and item["reasons"]
        assert all(isinstance(reason, str) and reason for reason in item["reasons"])


def test_feed_serves_verbatim_catalog_content():
    """Reasons/titles/descriptions are catalog facts, never invented."""
    from app.infrastructure.external.knowledge import CatalogKnowledgeSource

    source = CatalogKnowledgeSource()
    catalog = {
        look.id: look
        for look in (
            *source.retrieve_hairstyle_looks(),
            *source.retrieve_grooming_looks(),
        )
    }
    response = client.get("/v1/looks", headers=HEADERS)
    assert response.status_code == 200
    for item in response.json()["items"]:
        source_look = catalog[item["id"]]
        assert item["title"] == source_look.name
        assert item["description"] == source_look.description
        assert item["reasons"] == list(source_look.reasons)
        assert item["matchScore"] == int(round(float(source_look.matchScore) * 100))


# ---------------------------------------------------------------------------
# C. Engine-ranked deterministic ordering
# ---------------------------------------------------------------------------


def test_feed_rank_order_is_scoreseed_desc():
    response = client.get("/v1/looks", headers=HEADERS)
    assert response.status_code == 200
    items = response.json()["items"]
    assert [(item["id"], item["matchScore"]) for item in items] == EXPECTED_ORDER


def test_feed_repeated_calls_are_byte_identical():
    first = client.get("/v1/looks", headers=HEADERS).json()
    second = client.get("/v1/looks", headers=HEADERS).json()
    assert first == second


# ---------------------------------------------------------------------------
# D. Cursor walk
# ---------------------------------------------------------------------------


def test_feed_cursor_walk_covers_all_rows_once_in_rank_order():
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        params = {"limit": 3}
        if cursor is not None:
            params["cursor"] = cursor
        response = client.get("/v1/looks", headers=HEADERS, params=params)
        assert response.status_code == 200
        body = response.json()
        pages += 1
        assert pages <= 4
        seen.extend(item["id"] for item in body["items"])
        if body["has_more"]:
            assert body["next_cursor"]
            cursor = body["next_cursor"]
        else:
            assert body["next_cursor"] is None
            break
    assert pages == 3
    assert seen == [code for code, _ in EXPECTED_ORDER]


def test_feed_first_page_cursor_shape():
    response = client.get("/v1/looks", headers=HEADERS, params={"limit": 3})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 3
    assert body["has_more"] is True
    assert isinstance(body["next_cursor"], str) and body["next_cursor"]
    raw = base64.urlsafe_b64decode(body["next_cursor"].encode("ascii")).decode("utf-8")
    assert raw == "87:classic_pompadour"


def test_feed_last_page_signals_end():
    first = client.get("/v1/looks", headers=HEADERS, params={"limit": 7}).json()
    assert first["has_more"] is True
    last = client.get(
        "/v1/looks", headers=HEADERS, params={"limit": 7, "cursor": first["next_cursor"]}
    )
    assert last.status_code == 200
    assert [item["id"] for item in last.json()["items"]] == ["goatee_with_mustache"]
    assert last.json()["has_more"] is False
    assert last.json()["next_cursor"] is None


# ---------------------------------------------------------------------------
# E. Limit bounds
# ---------------------------------------------------------------------------


def test_feed_default_limit_returns_all_rows_without_more():
    body = client.get("/v1/looks", headers=HEADERS).json()
    assert len(body["items"]) == 8
    assert body["has_more"] is False


@pytest.mark.parametrize("limit", [0, -1, 51, 100, 101])
def test_feed_limit_out_of_range_is_422(limit: int):
    response = client.get("/v1/looks", headers=HEADERS, params={"limit": limit})
    assert response.status_code == 422
    assert _error_body(response)["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("limit", [1, 8, 50])
def test_feed_limit_in_range_ok(limit: int):
    response = client.get("/v1/looks", headers=HEADERS, params={"limit": limit})
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# F. Cursor errors (never silently reset)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cursor",
    ["not-a-cursor", "!!!", "", "aHR0cHM6Ly9mYWtl", "OTQ6bm8tc3VjaC1jb2Rl"],
)
def test_feed_bad_cursor_is_422(cursor: str):
    response = client.get("/v1/looks", headers=HEADERS, params={"cursor": cursor})
    assert response.status_code == 422
    assert _error_body(response)["code"] == "VALIDATION_ERROR"


def test_feed_wellformed_unknown_cursor_is_422():
    # Valid `<score>:<code>` shape, but never issued by the server.
    cursor = (
        base64.urlsafe_b64encode(b"94:textured_quiff_extra").decode("ascii")
    )
    response = client.get("/v1/looks", headers=HEADERS, params={"cursor": cursor})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# G. Honest filter behavior (DEC-014 P-3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        {"occasion": "casual"},
        {"style": "minimalist"},
        {"fit": "slim"},
        {"occasion": "casual", "style": "minimalist", "fit": "slim"},
        {"occasion": "anything-at-all"},
    ],
)
def test_feed_supplied_filters_are_truthful_422(params: dict):
    response = client.get("/v1/looks", headers=HEADERS, params=params)
    assert response.status_code == 422
    body = _error_body(response)
    assert body["code"] == "VALIDATION_ERROR"
    fields = {error["field"] for error in body["details"]["field_errors"]}
    assert fields == set(params.keys())
    # No `allowed` list is claimed for values the catalog cannot honor.
    for error in body["details"]["field_errors"]:
        assert "allowed" not in error


def test_feed_combined_filter_reports_all_three_fields():
    response = client.get(
        "/v1/looks",
        headers=HEADERS,
        params={"occasion": "casual", "style": "x", "fit": "y"},
    )
    assert response.status_code == 422
    assert len(_error_body(response)["details"]["field_errors"]) == 3


# ---------------------------------------------------------------------------
# H. Detail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code,_", EXPECTED_ORDER)
def test_detail_serves_every_catalog_row(code: str, _):
    response = client.get(f"/v1/looks/{code}", headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == DETAIL_KEYS
    assert BANNED_KEYS.isdisjoint(body.keys())
    assert body["id"] == code
    assert body["stylingTips"] and body["maintenance"] and body["bestFor"]


def test_detail_unknown_code_is_404():
    for code in ("no-such-look", "fy_1", "00000000-0000-0000-0000-000000000000"):
        response = client.get(f"/v1/looks/{code}", headers=HEADERS)
        assert response.status_code == 404
        assert _error_body(response)["code"] == "NOT_FOUND"


def test_detail_scores_match_feed_scores():
    feed = {
        item["id"]: item["matchScore"]
        for item in client.get("/v1/looks", headers=HEADERS).json()["items"]
    }
    for code in feed:
        detail = client.get(f"/v1/looks/{code}", headers=HEADERS).json()
        assert detail["matchScore"] == feed[code]
        assert detail["title"]


# ---------------------------------------------------------------------------
# I. Route-ordering guard
# ---------------------------------------------------------------------------


def test_specific_looks_routes_not_shadowed_by_detail_param():
    # `/{look_id}` is registered last: the specific routes keep serving.
    today = client.get("/v1/looks/today", headers=HEADERS)
    assert today.status_code == 404  # honest empty (no wardrobe), not a look
    saved = client.get("/v1/looks/saved", headers=HEADERS)
    assert saved.status_code == 200
    assert set(saved.json().keys()) == {"items", "page", "page_size", "total"}


# ---------------------------------------------------------------------------
# J. Read-only proof + K. determinism across users
# ---------------------------------------------------------------------------


def test_feed_and_detail_write_nothing():
    before = _snapshot()
    client.get("/v1/looks", headers=HEADERS)
    client.get("/v1/looks", headers=HEADERS, params={"limit": 3})
    for code, _ in EXPECTED_ORDER:
        client.get(f"/v1/looks/{code}", headers=HEADERS)
    client.get("/v1/looks/unknown-code", headers=HEADERS)
    client.get("/v1/looks", headers=HEADERS, params={"occasion": "casual"})
    after = _snapshot()
    # Auth auto-seeds the dev user + state on first call only; every row
    # count besides those two bootstrap rows is unchanged.
    for table in _READ_TABLES:
        if table in ("users", "user_state"):
            assert after[table] - before[table] <= 1
        else:
            assert after[table] == before[table], table
    with _session() as session:
        assert session.execute(select(func.count()).select_from(Users)).scalar() == 1
