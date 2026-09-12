"""API tests for M8-C event outfit generation (endpoint #30, UC-21).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; each test starts truncated-clean).

Covers the task A–Z matrix: owned generation (200), UUID/ownership
errors, TYPE-CODE occasion, owner-only UUIDs, determinism, the frozen
occasion-context rule (event code first, prefs deduped), exact
no-candidate 204, canonical shape (0..1 score, grounded reasons,
mood/palette/hex absent, no alternatives), and side-effect safety
(no save/signal/activity/wear/event/wardrobe/preference writes —
DB-count/snapshot proofs).

Does NOT touch Flutter — later M8 step.
"""

from __future__ import annotations

import json
import re
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

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


def _create_event(event_type="formal", title="Gala"):
    resp = client.post(
        "/v1/events",
        json={"title": title, "eventType": event_type, "eventDate": "2030-08-15"},
        headers=HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _generate(event_id, headers=HEADERS):
    return client.post(f"/v1/events/{event_id}/outfit", headers=headers)


def _seed_foreign_event_and_item():
    """Direct-seeded other user with one event + one wardrobe item."""
    with _session() as session:
        user = Users(
            auth_provider="m8c", auth_subject=f"foreign-{uuid4()}", display_name="Foreign"
        )
        session.add(user)
        session.flush()
        event = UserEvent(
            user_id=user.id, title="Foreign Gala", event_type_id="party",
            event_date=date(2030, 9, 1),
        )
        session.add(event)
        session.flush()
        session.execute(
            text(
                "INSERT INTO wardrobe_items (user_id, name, category_id, color_id) "
                "VALUES (:u, 'Foreign Jacket', 'outerwear', 'navy')"
            ),
            {"u": str(user.id)},
        )
        session.commit()
        return user.id, event.id


def _snapshot(user_id, event_id):
    """DB-count + row snapshots proving read/derive purity."""
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
        event = session.execute(
            text(
                "SELECT title, event_type_id, event_date, event_time, location, "
                "notes, created_at, updated_at FROM user_events WHERE id = :id"
            ),
            {"id": str(event_id)},
        ).one()
        wardrobe = session.execute(
            text(
                "SELECT id, name, category_id, color_id, material_id, is_favorite "
                "FROM wardrobe_items WHERE user_id = :u ORDER BY id"
            ),
            {"u": str(user_id)},
        ).all()
        prefs = session.execute(
            text("SELECT preferences FROM user_state WHERE user_id = :u"),
            {"u": str(user_id)},
        ).scalar_one()
        return {
            "counts": counts,
            "event": tuple(event),
            "wardrobe": [tuple(row) for row in wardrobe],
            "prefs": json.dumps(prefs, sort_keys=True, default=str),
        }


# ---------------------------------------------------------------------------
# A–D: happy path + ownership
# ---------------------------------------------------------------------------


def test_A_owned_event_generates_200():
    """A. Owned event + legal wardrobe → 200 bare OutfitRecommendation."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    event_id = _create_event()
    resp = _generate(event_id)
    assert resp.status_code == 200
    body = resp.json()
    assert body["selectedOccasion"] == "formal"
    assert len(body["components"]) >= 2


def test_B_malformed_uuid_rejected_422():
    """B. Malformed event id → 422 VALIDATION_ERROR."""
    resp = _generate("not-a-uuid")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_C_missing_event_returns_404():
    """C. Unknown event id → 404 (never 403)."""
    resp = _generate(str(uuid4()))
    assert resp.status_code == 404


def test_D_foreign_event_returns_404():
    """D. Another user's event → 404 (never 403)."""
    _, foreign_event_id = _seed_foreign_event_and_item()
    resp = _generate(str(foreign_event_id))
    assert resp.status_code == 404


def test_past_event_generates_freely():
    """Past events are allowed to generate (no date gate — DEC-015)."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    with _session() as session:
        row = UserEvent(
            user_id=user_id, title="Old Gala", event_type_id="formal",
            event_date=date(2000, 5, 5),
        )
        session.add(row)
        session.commit()
        past_id = row.id
    resp = _generate(str(past_id))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# E–G: occasion code + owner-only UUIDs
# ---------------------------------------------------------------------------


def test_E_selected_occasion_is_event_type_code():
    """E. selectedOccasion echoes the TYPE CODE (never a label)."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    event_id = _create_event(event_type="date")
    body = _generate(event_id).json()
    assert body["selectedOccasion"] == "date"


def test_F_only_owner_wardrobe_uuids_appear():
    """F. Every component id is an owned backend UUID; foreign items never."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    _, foreign_event_id = _seed_foreign_event_and_item()
    event_id = _create_event()
    assert _generate(str(foreign_event_id)).status_code == 404
    body = _generate(event_id).json()
    own_ids = _owner_item_ids(user_id)
    got_ids = [item["id"] for item in body["components"]]
    assert got_ids and set(got_ids) <= own_ids


def test_G_no_local_or_mock_ids():
    """G. No numeric/mock/invented ids — every id parses as UUID."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    body = _generate(_create_event()).json()
    for item in body["components"]:
        UUID(item["id"])
        assert not re.fullmatch(r"\d+", item["id"])
        assert "comp_" not in item["id"] and "mock" not in item["id"].lower()


# ---------------------------------------------------------------------------
# H–J: determinism + occasion context rule
# ---------------------------------------------------------------------------


def test_H_repeated_request_is_identical():
    """H. Same inputs → byte-identical response (deterministic engine)."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    event_id = _create_event()
    assert _generate(event_id).json() == _generate(event_id).json()


def test_I_preferred_occasions_feed_scoring_context():
    """I. Persisted prefs join the scoring occasions (frozen composition).

    `formal` suits no engine category (neutral alone); adding `casual`
    fires the +5 occasion term for every member, so matchScore rises by
    exactly 0.05 while the event code keeps priority.
    """
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    event_id = _create_event()
    plain = _generate(event_id).json()["matchScore"]
    client.patch("/v1/users/me", json={"preferredOccasions": ["casual"]}, headers=HEADERS)
    seeded = _generate(event_id).json()
    assert seeded["matchScore"] == plain + 0.05
    assert seeded["selectedOccasion"] == "formal"


def test_J_event_code_has_priority_over_preferences():
    """J. selectedOccasion is the event code even with competing prefs."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    client.patch("/v1/users/me", json={"preferredOccasions": ["party"]}, headers=HEADERS)
    body = _generate(_create_event()).json()
    assert body["selectedOccasion"] == "formal"


# ---------------------------------------------------------------------------
# K–R: empty behavior + canonical shape
# ---------------------------------------------------------------------------


def test_K_empty_wardrobe_returns_204_empty():
    """K1. No wardrobe items → 204 empty (not an error, #41 precedent)."""
    event_id = _create_event()
    resp = _generate(event_id)
    assert resp.status_code == 204
    assert resp.content == b""


def test_K_sparse_wardrobe_returns_204_empty():
    """K2. Wardrobe without tops+bottoms → 204 empty (no fabrication)."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id, [("Lonely Tee", "tops", "black", None, False)])
    event_id = _create_event()
    resp = _generate(event_id)
    assert resp.status_code == 204
    assert resp.content == b""


def test_L_response_exact_canonical_shape():
    """L. Exact honest key set on the DTO and every component."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    body = _generate(_create_event()).json()
    assert set(body) == {"title", "matchScore", "components", "reasons", "selectedOccasion"}
    assert body["title"] == "Formal Outfit"
    assert len(body["components"]) >= 2
    for item in body["components"]:
        assert set(item) <= {"id", "name", "category", "color", "material", "reason"}
        assert {"id", "name", "category", "color", "reason"} <= set(item)


def test_M_match_score_range_0_to_1():
    """M. matchScore is the family 0..1 float scale (mock 0.91 precedent)."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    score = _generate(_create_event()).json()["matchScore"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_N_grounded_reasons_only():
    """N. Reasons are non-empty factual strings with no banned claims."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id, [("Tee", "tops", "black", "cotton", True),
                             ("Jeans", "bottoms", "white", None, False),
                             ("Sneaks", "footwear", "white", None, False)])
    body = _generate(_create_event()).json()
    assert body["reasons"] and all(isinstance(r, str) and r for r in body["reasons"])
    for text in body["reasons"] + [c["reason"] for c in body["components"]]:
        assert not BANNED_REASON.search(text), text
    assert any("favorite" in r.lower() for r in body["reasons"])


def test_OPQ_sourceless_keys_absent():
    """O/P/Q. selectedMood, selectedColorPalette, colorHex are absent."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    body = _generate(_create_event()).json()
    assert "selectedMood" not in body
    assert "selectedColorPalette" not in body
    assert "colorHarmony" not in body
    assert "bodyFit" not in body
    assert "occasionMatch" not in body
    assert "styleScoreImpact" not in body
    assert "improvementSuggestion" not in body
    assert "colorHex" not in json.dumps(body)


def test_R_no_alternatives_field():
    """R. The canonical DTO carries no alternatives (never fabricated)."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    assert "alternatives" not in _generate(_create_event()).json()


# ---------------------------------------------------------------------------
# S–Y: side-effect safety (DB-count/snapshot proofs)
# ---------------------------------------------------------------------------


def test_S_to_Y_generation_is_read_derive_only():
    """S–Y. One generation changes no table, row, or preference."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    client.patch("/v1/users/me", json={"preferredOccasions": ["casual"]}, headers=HEADERS)
    event_id = _create_event()
    before = _snapshot(user_id, event_id)
    resp = _generate(event_id)
    assert resp.status_code == 200
    after = _snapshot(user_id, event_id)
    assert after == before


# ---------------------------------------------------------------------------
# Z: auth
# ---------------------------------------------------------------------------


def test_Z_unauthenticated_rejected_401():
    """Z. No token → 401 (event id never leaks)."""
    user_id = _dev_user_id()
    _seed_wardrobe(user_id)
    event_id = _create_event()
    assert _generate(event_id, headers={}).status_code == 401
