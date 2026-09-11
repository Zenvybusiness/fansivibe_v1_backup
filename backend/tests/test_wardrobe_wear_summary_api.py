"""API tests for the read-only wear summary (W-9, STEP 17.3, DEC-012).

`GET /v1/wardrobe/wear-summary` exposes the `GetWearSummary` foundation
over HTTP with the accepted §10 wire shape — counts only, no names, no
judgments. Writes go through the real `POST /v1/wardrobe/wears`
contract; the summary route itself must commit nothing.

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.infrastructure.db.models import (
    Colors,
    Materials,
    Users,
    UserState,
    WardrobeCategories,
    WardrobeItems,
)

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}

_T1 = "2024-01-10T12:00:00Z"
_T2 = "2024-01-20T12:00:00Z"
_T3 = "2024-01-25T12:00:00Z"
_T4 = "2024-01-28T12:00:00Z"
_T5 = "2024-02-01T12:00:00Z"


def _instant(iso):
    return datetime.fromisoformat(iso)


@pytest.fixture
def dev_user_id(db):
    """Get or create the dev user ID (mirrors test_wardrobe_wears_api.py)."""
    Session = db
    with Session() as session:
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
            session.commit()
        return user.id


def _seed_vocab(db):
    Session = db
    with Session() as session:
        for code, label in (
            ("tops", "Tops"),
            ("bottoms", "Bottoms"),
            ("outerwear", "Outerwear"),
            ("footwear", "Footwear"),
            ("accessories", "Accessories"),
        ):
            if session.get(WardrobeCategories, code) is None:
                session.add(
                    WardrobeCategories(code=code, label=label, sort_order=1, active=True)
                )
        for code, label in (("charcoal", "Charcoal"), ("white", "White")):
            if session.get(Colors, code) is None:
                session.add(Colors(code=code, label=label, sort_order=1, active=True))
        for code, label in (("wool", "Wool"), ("cotton", "Cotton")):
            if session.get(Materials, code) is None:
                session.add(
                    Materials(code=code, label=label, sort_order=1, active=True)
                )
        session.commit()


def _seed_item(db, user_id, **kwargs):
    defaults = dict(
        name="Merino Crew Neck",
        category="tops",
        color="charcoal",
        material="wool",
        isFavorite=False,
    )
    defaults.update(kwargs)
    Session = db
    with Session() as session:
        item = WardrobeItems(
            user_id=user_id,
            name=defaults["name"],
            category_id=defaults["category"],
            color_id=defaults["color"],
            material_id=defaults.get("material"),
            is_favorite=defaults["isFavorite"],
            image_ref=None,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return item


def _make_other_user(db):
    """A second owner (unique subject per call; the dev seam stays dev)."""
    Session = db
    with Session() as session:
        other = Users(
            auth_provider="dev",
            auth_subject=f"other-user-{uuid4().hex}",
            display_name="Other",
        )
        session.add(other)
        session.flush()
        session.add(UserState(user_id=other.id))
        session.commit()
        session.refresh(other)
        return other.id


def _post(item_ids, key, worn_at=None):
    body = {"itemIds": item_ids}
    if worn_at is not None:
        body["wornAt"] = worn_at
    return client.post(
        "/v1/wardrobe/wears", json=body, headers={**HEADERS, "Idempotency-Key": key}
    )


def _get():
    return client.get("/v1/wardrobe/wear-summary", headers=HEADERS)


def _wear_count(db):
    Session = db
    with Session() as session:
        return session.execute(
            select(text("count(*)")).select_from(text("wardrobe_wear_events"))
        ).scalar_one()


def _group_count(db):
    Session = db
    with Session() as session:
        return session.execute(
            select(text("count(*)")).select_from(text("wardrobe_wear_groups"))
        ).scalar_one()


def _assert_invariants(body):
    assert body["totalWears"] == sum(body["wearCounts"].values())
    assert body["totalWears"] == sum(body["wearsByCategory"].values())


# --- shape ------------------------------------------------------------------


def test_wear_summary_exact_shape(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    assert _post([str(item_a.id)], "sum-shape-1", worn_at=_T1).status_code == 201
    assert _post([str(item_b.id)], "sum-shape-2", worn_at=_T2).status_code == 201
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {
        "totalWears",
        "wearCounts",
        "lastWorn",
        "mostWornItemIds",
        "leastWornItemIds",
        "unwornItemIds",
        "recentlyWornItemIds",
        "wearsByCategory",
    }
    assert isinstance(body["totalWears"], int)
    assert isinstance(body["wearCounts"], dict)
    assert isinstance(body["lastWorn"], dict)
    assert isinstance(body["mostWornItemIds"], list)
    assert isinstance(body["leastWornItemIds"], list)
    assert isinstance(body["unwornItemIds"], list)
    assert isinstance(body["recentlyWornItemIds"], list)
    assert isinstance(body["wearsByCategory"], dict)
    # No names, judgments, or recommendations leak into the shape.
    flat = " ".join(
        [str(body["totalWears"])]
        + list(body["wearCounts"].keys())
        + list(body["wearsByCategory"].keys())
    )
    assert "Tee" not in flat and "Jeans" not in flat


def test_wear_summary_empty_wardrobe_returns_200_zero_object(db, dev_user_id):
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalWears"] == 0
    assert body["wearCounts"] == {}
    assert body["lastWorn"] == {}
    assert body["mostWornItemIds"] == []
    assert body["leastWornItemIds"] == []
    assert body["unwornItemIds"] == []
    assert body["recentlyWornItemIds"] == []
    assert body["wearsByCategory"] == {}


def test_wear_summary_no_history_zero_most(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalWears"] == 0
    assert body["wearCounts"] == {str(item_a.id): 0, str(item_b.id): 0}
    assert body["lastWorn"] == {str(item_a.id): None, str(item_b.id): None}
    assert body["mostWornItemIds"] == []
    assert body["leastWornItemIds"] == sorted([str(item_a.id), str(item_b.id)])
    assert body["unwornItemIds"] == sorted([str(item_a.id), str(item_b.id)])
    assert body["recentlyWornItemIds"] == []
    assert body["wearsByCategory"] == {"bottoms": 0, "tops": 0}
    _assert_invariants(body)


# --- ownership --------------------------------------------------------------


def test_wear_summary_owner_isolation(db, dev_user_id):
    """Another owner's items and events never appear in this owner's summary."""
    from app.application.wardrobe import LogWearEvents
    from app.infrastructure.db.repositories import (
        WardrobeItemRepositorySQL,
        WearEventRepositorySQL,
        WearGroupRepositorySQL,
    )

    _seed_vocab(db)
    mine = _seed_item(db, dev_user_id, name="Mine")
    other_id = _make_other_user(db)
    theirs = _seed_item(db, other_id, name="Theirs", category="bottoms")
    assert _post([str(mine.id)], "sum-isolation-1", worn_at=_T1).status_code == 201
    Session = db
    with Session() as session:
        LogWearEvents(
            wardrobe=WardrobeItemRepositorySQL(session),
            wears=WearEventRepositorySQL(session),
            groups=WearGroupRepositorySQL(session),
        )(
            user_id=other_id,
            item_ids=[theirs.id],
            worn_at=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            idempotency_key="sum-isolation-other-1",
        )
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalWears"] == 1
    assert set(body["wearCounts"].keys()) == {str(mine.id)}
    assert set(body["lastWorn"].keys()) == {str(mine.id)}
    assert str(theirs.id) not in body["mostWornItemIds"]
    assert str(theirs.id) not in body["leastWornItemIds"]
    assert str(theirs.id) not in body["unwornItemIds"]
    assert str(theirs.id) not in body["recentlyWornItemIds"]
    assert body["wearsByCategory"] == {"tops": 1}
    _assert_invariants(body)


# --- counts / instants / recency --------------------------------------------


def test_wear_summary_counts_and_last_worn(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    assert _post([str(item_a.id)], "sum-counts-1", worn_at=_T1).status_code == 201
    assert _post([str(item_b.id)], "sum-counts-2", worn_at=_T2).status_code == 201
    assert _post([str(item_a.id)], "sum-counts-3", worn_at=_T3).status_code == 201
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalWears"] == 3
    assert body["wearCounts"] == {str(item_a.id): 2, str(item_b.id): 1}
    assert _instant(body["lastWorn"][str(item_a.id)]) == _instant(_T3)
    assert _instant(body["lastWorn"][str(item_b.id)]) == _instant(_T2)
    _assert_invariants(body)


def test_wear_summary_recently_worn_window(db, dev_user_id):
    _seed_vocab(db)
    recent = _seed_item(db, dev_user_id, name="Tee")
    old = _seed_item(db, dev_user_id, name="Coat", category="outerwear")
    assert _post([str(recent.id)], "sum-recent-1").status_code == 201
    assert _post([str(old.id)], "sum-recent-2", worn_at=_T1).status_code == 201
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    assert body["recentlyWornItemIds"] == [str(recent.id)]
    assert body["lastWorn"][str(old.id)] is not None
    _assert_invariants(body)


# --- rankings -----------------------------------------------------------------


def test_wear_summary_most_worn_ties_ordering(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Shirt", color="white")
    item_c = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    assert _post([str(item_a.id)], "sum-most-1", worn_at=_T1).status_code == 201
    assert _post([str(item_a.id)], "sum-most-2", worn_at=_T3).status_code == 201
    assert _post([str(item_b.id)], "sum-most-3", worn_at=_T2).status_code == 201
    assert _post([str(item_b.id)], "sum-most-4", worn_at=_T4).status_code == 201
    assert _post([str(item_c.id)], "sum-most-5", worn_at=_T1).status_code == 201
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    # Both at count 2; B's last wear (T4) beats A's (T3): last-worn desc.
    assert body["mostWornItemIds"] == [str(item_b.id), str(item_a.id)]
    _assert_invariants(body)


def test_wear_summary_least_worn_includes_unworn(db, dev_user_id):
    _seed_vocab(db)
    worn = _seed_item(db, dev_user_id, name="Tee")
    fresh = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    assert _post([str(worn.id)], "sum-least-1", worn_at=_T1).status_code == 201
    assert _post([str(worn.id)], "sum-least-2", worn_at=_T2).status_code == 201
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    assert body["mostWornItemIds"] == [str(worn.id)]
    assert body["leastWornItemIds"] == [str(fresh.id)]
    assert body["unwornItemIds"] == [str(fresh.id)]
    _assert_invariants(body)


def test_wear_summary_least_worn_tie_ordering(db, dev_user_id):
    _seed_vocab(db)
    top = _seed_item(db, dev_user_id, name="Tee")
    early = _seed_item(db, dev_user_id, name="Shirt", color="white")
    late = _seed_item(
        db, dev_user_id, name="Jeans", category="bottoms", color="white"
    )
    assert _post([str(top.id)], "sum-leasttie-1", worn_at=_T1).status_code == 201
    assert _post([str(top.id)], "sum-leasttie-2", worn_at=_T3).status_code == 201
    assert _post([str(top.id)], "sum-leasttie-3", worn_at=_T5).status_code == 201
    assert _post([str(early.id)], "sum-leasttie-4", worn_at=_T1).status_code == 201
    assert _post([str(late.id)], "sum-leasttie-5", worn_at=_T2).status_code == 201
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    # Floor is 1 over worn items; earliest last-worn first.
    assert body["leastWornItemIds"] == [str(early.id), str(late.id)]
    assert body["mostWornItemIds"] == [str(top.id)]
    _assert_invariants(body)


def test_wear_summary_unworn_ordering(db, dev_user_id):
    _seed_vocab(db)
    worn = _seed_item(db, dev_user_id, name="Tee")
    u1 = _seed_item(db, dev_user_id, name="Shirt", color="white")
    u2 = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    u3 = _seed_item(
        db, dev_user_id, name="Coat", category="outerwear", color="white"
    )
    assert _post([str(worn.id)], "sum-unworn-1", worn_at=_T1).status_code == 201
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    assert body["unwornItemIds"] == sorted([str(u1.id), str(u2.id), str(u3.id)])
    _assert_invariants(body)


# --- categories / invariant / staleness / read-only ---------------------------


def test_wear_summary_categories_zero_filled(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    assert _post([str(item_a.id)], "sum-cats-1", worn_at=_T1).status_code == 201
    assert _post([str(item_a.id)], "sum-cats-2", worn_at=_T2).status_code == 201
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    # Only current-item categories appear; the unworn one is zero-filled.
    assert body["wearsByCategory"] == {"bottoms": 0, "tops": 2}
    _assert_invariants(body)


def test_wear_summary_invariant(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    item_c = _seed_item(
        db, dev_user_id, name="Coat", category="outerwear", color="white"
    )
    assert _post([str(item_a.id)], "sum-inv-1", worn_at=_T1).status_code == 201
    assert _post([str(item_a.id)], "sum-inv-2", worn_at=_T2).status_code == 201
    assert _post([str(item_b.id)], "sum-inv-3", worn_at=_T3).status_code == 201
    assert _post(
        [str(item_b.id), str(item_c.id)], "sum-inv-4", worn_at=_T4
    ).status_code == 201
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalWears"] == 5
    _assert_invariants(body)


def test_wear_summary_ignores_deleted_items(db, dev_user_id):
    _seed_vocab(db)
    item = _seed_item(db, dev_user_id, name="Tee")
    assert _post([str(item.id)], "sum-stale-1", worn_at=_T1).status_code == 201
    assert _post([str(item.id)], "sum-stale-2", worn_at=_T2).status_code == 201
    gone = client.delete(f"/v1/wardrobe/items/{item.id}", headers=HEADERS)
    assert gone.status_code == 204
    resp = _get()
    assert resp.status_code == 200
    body = resp.json()
    # The history row survives deletion but contributes to nothing.
    assert _wear_count(db) == 2
    assert body["totalWears"] == 0
    assert body["wearCounts"] == {}
    assert body["lastWorn"] == {}
    assert body["mostWornItemIds"] == []
    assert body["leastWornItemIds"] == []
    assert body["unwornItemIds"] == []
    assert body["recentlyWornItemIds"] == []
    assert body["wearsByCategory"] == {}
    _assert_invariants(body)


def test_wear_summary_read_only_and_deterministic(db, dev_user_id):
    _seed_vocab(db)
    item_a = _seed_item(db, dev_user_id, name="Tee")
    item_b = _seed_item(db, dev_user_id, name="Jeans", category="bottoms")
    assert _post([str(item_a.id)], "sum-ro-1", worn_at=_T1).status_code == 201
    assert _post([str(item_b.id)], "sum-ro-2", worn_at=_T2).status_code == 201
    before_item = client.get(
        f"/v1/wardrobe/items/{item_a.id}", headers=HEADERS
    ).json()
    wears_before, groups_before = _wear_count(db), _group_count(db)
    first = _get()
    second = _get()
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert _wear_count(db) == wears_before
    assert _group_count(db) == groups_before
    after_item = client.get(
        f"/v1/wardrobe/items/{item_a.id}", headers=HEADERS
    ).json()
    assert after_item["updatedAt"] == before_item["updatedAt"]


def test_wear_summary_unauthenticated_401():
    """Unauthenticated summary access follows the existing auth convention."""
    resp = client.get("/v1/wardrobe/wear-summary")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"
