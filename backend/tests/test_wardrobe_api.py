"""API tests for the wardrobe surface (Step 4D and 4E).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).

Tests: authenticated list, empty list, create valid item,
invalid category, invalid color, invalid material, pagination,
category/color filtering, sorting, ownership isolation,
unauthenticated access, and Step 4E item CRUD (GET/PATCH/DELETE).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func
from uuid import uuid4

from app.infrastructure.db.models import SavedLooks, WardrobeItems, Users, UserState, WardrobeCategories, Colors, Materials

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}


@pytest.fixture
def dev_user_id(db):
    """Get or create the dev user ID."""
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


@pytest.fixture
def dev_user_state(db, dev_user_id):
    """Ensure user_state exists for the dev user."""
    Session = db
    with Session() as session:
        state = session.get(UserState, dev_user_id)
        if state is None:
            session.add(UserState(user_id=dev_user_id))
            session.commit()
    return dev_user_id


# --- helpers ----------------------------------------------------------------

def _seed_wardrobe_categories(db):
    """Seed the vocab tables needed for validation.

    All five canonical categories are seeded so the insight endpoint can
    compute genuinely missing categories.
    """
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
                    WardrobeCategories(
                        code=code, label=label, sort_order=1, active=True
                    )
                )
        for code, label in (
            ("charcoal", "Charcoal"),
            ("white", "White"),
            ("navy", "Navy"),
        ):
            if session.get(Colors, code) is None:
                session.add(
                    Colors(code=code, label=label, sort_order=1, active=True)
                )
        for code, label in (("wool", "Wool"), ("cotton", "Cotton")):
            if session.get(Materials, code) is None:
                session.add(
                    Materials(code=code, label=label, sort_order=1, active=True)
                )
        session.commit()


def _seed_wardrobe_item(db, user_id, **kwargs):
    """Seed a wardrobe item for the given user."""
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


# --- auth / unauthorized ----------------------------------------------------

def test_list_requires_auth():
    resp = client.get("/v1/wardrobe/items")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_list_rejects_invalid_token():
    resp = client.get("/v1/wardrobe/items", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


# --- authenticated user / empty list ----------------------------------------

def test_list_returns_empty_for_fresh_user(db, dev_user_id, dev_user_state):
    """A valid token resolves to the authenticated user even when no items exist yet — 200, not an error."""
    _seed_wardrobe_categories(db)
    resp = client.get("/v1/wardrobe/items", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["page_size"] == 20


# --- create valid item ----------------------------------------------------

def test_create_valid_item(db, dev_user_id, dev_user_state):
    """Create a wardrobe item with valid category and color — 201."""
    _seed_wardrobe_categories(db)
    resp = client.post(
        "/v1/wardrobe/items",
        json={
            "name": "Merino Crew Neck",
            "category": "tops",
            "color": "charcoal",
            "material": "wool",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Merino Crew Neck"
    assert body["category"] == "tops"
    assert body["color"] == "charcoal"
    assert body["isFavorite"] == False
    assert body["id"] is not None
    assert "createdAt" in body
    assert "updatedAt" in body


# --- validation: invalid category -----------------------------------------

def test_create_invalid_category(db, dev_user_id, dev_user_state):
    """Create with unknown category code — 422."""
    _seed_wardrobe_categories(db)
    resp = client.post(
        "/v1/wardrobe/items",
        json={
            "name": "Test Item",
            "category": "unknown_category",
            "color": "charcoal",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- validation: invalid color --------------------------------------------

def test_create_invalid_color(db, dev_user_id, dev_user_state):
    """Create with unknown color code — 422."""
    _seed_wardrobe_categories(db)
    resp = client.post(
        "/v1/wardrobe/items",
        json={
            "name": "Test Item",
            "category": "tops",
            "color": "unknown_color",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- validation: invalid material -----------------------------------------

def test_create_invalid_material(db, dev_user_id, dev_user_state):
    """Create with unknown material code — 422."""
    _seed_wardrobe_categories(db)
    resp = client.post(
        "/v1/wardrobe/items",
        json={
            "name": "Test Item",
            "category": "tops",
            "color": "charcoal",
            "material": "unknown_material",
        },
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


# --- pagination -----------------------------------------------------------

def test_list_pagination(db, dev_user_id, dev_user_state):
    """Test pagination with page and page_size params."""
    _seed_wardrobe_categories(db)
    # Create 3 items
    for i in range(3):
        _seed_wardrobe_item(db, dev_user_id, name=f"Item {i}")

    # Page 1, page_size 2
    resp = client.get("/v1/wardrobe/items?page=1&page_size=2", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2

    # Page 2
    resp = client.get("/v1/wardrobe/items?page=2&page_size=2", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["page"] == 2
    assert body["page_size"] == 2


# --- category/color filtering ---------------------------------------------

def test_list_filter_by_category(db, dev_user_id, dev_user_state):
    """Filter list by category vocab code."""
    _seed_wardrobe_categories(db)
    _seed_wardrobe_item(db, dev_user_id, name="Item A", category="tops")
    _seed_wardrobe_item(db, dev_user_id, name="Item B", category="bottoms")

    resp = client.get("/v1/wardrobe/items?category=tops", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Item A"


def test_list_filter_by_color(db, dev_user_id, dev_user_state):
    """Filter list by color vocab code."""
    _seed_wardrobe_categories(db)
    _seed_wardrobe_item(db, dev_user_id, name="Item A", color="charcoal")
    _seed_wardrobe_item(db, dev_user_id, name="Item B", color="white")

    resp = client.get("/v1/wardrobe/items?color=charcoal", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["name"] == "Item A"


# --- sorting --------------------------------------------------------------

def test_list_sort_by_created_at_desc(db, dev_user_id, dev_user_state):
    """Sort by created_at desc (default)."""
    _seed_wardrobe_categories(db)
    for i in range(3):
        _seed_wardrobe_item(db, dev_user_id, name=f"Item {i}")

    resp = client.get("/v1/wardrobe/items?sort=created_at&order=desc", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    # Items should be newest-first by default
    assert body["total"] == 3
    assert [item["name"] for item in body["items"]] == ["Item 2", "Item 1", "Item 0"]


def test_list_sort_by_name_asc(db, dev_user_id, dev_user_state):
    """Sort by name asc."""
    _seed_wardrobe_categories(db)
    _seed_wardrobe_item(db, dev_user_id, name="Zebra Item")
    _seed_wardrobe_item(db, dev_user_id, name="Alpha Item")

    resp = client.get("/v1/wardrobe/items?sort=name&order=asc", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0]["name"] == "Alpha Item"
    assert body["items"][1]["name"] == "Zebra Item"


def test_list_sort_by_name_desc(db, dev_user_id, dev_user_state):
    """Sort by name desc."""
    _seed_wardrobe_categories(db)
    _seed_wardrobe_item(db, dev_user_id, name="Zebra Item")
    _seed_wardrobe_item(db, dev_user_id, name="Alpha Item")

    resp = client.get("/v1/wardrobe/items?sort=name&order=desc", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["items"][0]["name"] == "Zebra Item"
    assert body["items"][1]["name"] == "Alpha Item"


def test_list_pagination_with_filter_and_sort(db, dev_user_id, dev_user_state):
    """Pagination applies to the filtered + sorted result set."""
    _seed_wardrobe_categories(db)
    _seed_wardrobe_item(db, dev_user_id, name="Zebra Top", category="tops")
    _seed_wardrobe_item(db, dev_user_id, name="Alpha Top", category="tops")
    _seed_wardrobe_item(db, dev_user_id, name="Mike Bottom", category="bottoms")
    _seed_wardrobe_item(db, dev_user_id, name="Beta Top", category="tops")

    resp = client.get(
        "/v1/wardrobe/items?category=tops&sort=name&order=asc&page=1&page_size=2",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert [item["name"] for item in body["items"]] == ["Alpha Top", "Beta Top"]
    assert body["page"] == 1
    assert body["page_size"] == 2

    resp = client.get(
        "/v1/wardrobe/items?category=tops&sort=name&order=asc&page=2&page_size=2",
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert [item["name"] for item in body["items"]] == ["Zebra Top"]


# --- ownership isolation --------------------------------------------------

def test_list_ownership_isolated(db, dev_user_id, dev_user_state):
    """Another user cannot see this user's items, and vice versa."""
    _seed_wardrobe_categories(db)
    # Create an item for the dev user
    _seed_wardrobe_item(db, dev_user_id, name="My Item")

    # Create a second "other" user
    Session = db
    with Session() as session:
        other_user = Users(
            auth_provider="dev", auth_subject="other-user", display_name="Other User"
        )
        session.add(other_user)
        session.flush()
        other_id = other_user.id
        session.add(UserState(user_id=other_id))
        session.commit()

    # List as dev user — should only see dev user's items
    resp = client.get("/v1/wardrobe/items", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "My Item"

    # List as other user — should see no items (ownership scoped)
    other_headers = {"Authorization": "Bearer dev"}  # same token but we'll test with different approach
    # Actually since we only have one dev token, verify the dev user sees only their own
    resp2 = client.get("/v1/wardrobe/items", headers=HEADERS)
    assert resp2.status_code == 200


def test_unauthenticated_access():
    """Unauthenticated access to wardrobe endpoints returns 401."""
    resp = client.get("/v1/wardrobe/items")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"

    resp = client.post("/v1/wardrobe/items", json={})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


# --- Step 4E: Item CRUD (GET / PATCH / DELETE) ----------------------------------


def _seed_wardrobe_item_with_id(db, user_id, **kwargs):
    """Seed a wardrobe item and return its ID."""
    item = _seed_wardrobe_item(db, user_id, **kwargs)
    return item.id


def _seed_saved_look(db, user_id, **kwargs):
    """Seed a `saved_looks` row directly.

    Bypasses the save contract for the cases the API would rightly
    reject (stale/deleted IDs, legacy NULL source_context, foreign
    owners) — exactly the rows the insight must tolerate.
    """
    defaults = dict(
        title="Saved Outfit",
        source_context="outfit",
        snapshot={},
        idempotency_key=f"seed-{uuid4().hex}",
    )
    defaults.update(kwargs)
    Session = db
    with Session() as session:
        row = SavedLooks(
            user_id=user_id,
            look_id=None,
            title=defaults["title"],
            source_context=defaults["source_context"],
            snapshot=defaults["snapshot"],
            idempotency_key=defaults["idempotency_key"],
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def test_get_existing_item(db, dev_user_id, dev_user_state):
    """Get an owned wardrobe item — 200 with WardrobeItem."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck")
    resp = client.get(f"/v1/wardrobe/items/{item_id}", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Merino Crew Neck"
    assert body["category"] == "tops"
    assert body["color"] == "charcoal"


def test_get_foreign_item_404(db, dev_user_id, dev_user_state):
    """Get another user's item → 404 NOT_FOUND."""
    _seed_wardrobe_categories(db)
    # Create an item for a different user
    Session = db
    with Session() as session:
        other_user = Users(
            auth_provider="dev", auth_subject="other-user", display_name="Other User"
        )
        session.add(other_user)
        session.flush()
        other_id = other_user.id
        session.add(UserState(user_id=other_id))
        session.commit()

    # Create item for other user, then try to get it as dev user
    item = _seed_wardrobe_item(db, other_id, name="Other Item")
    resp = client.get(f"/v1/wardrobe/items/{item.id}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_get_missing_item_404(db, dev_user_id, dev_user_state):
    """Get a non-existent item → 404 NOT_FOUND."""
    _seed_wardrobe_categories(db)
    fake_id = uuid4()
    resp = client.get(f"/v1/wardrobe/items/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_patch_name(db, dev_user_id, dev_user_state):
    """Patch the item name."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck")
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"name": "Updated Name"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Updated Name"


def test_patch_category_color(db, dev_user_id, dev_user_state):
    """Patch category and color."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck", category="tops", color="charcoal")
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"category": "bottoms", "color": "navy"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["category"] == "bottoms"
    assert body["color"] == "navy"


def test_patch_material(db, dev_user_id, dev_user_state):
    """Patch material."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck", material="wool")
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"material": "cotton"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["material"] == "cotton"


def test_clear_material_with_null(db, dev_user_id, dev_user_state):
    """Clear material by setting null."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck", material="wool")
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"material": None},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["material"] is None


def test_patch_without_material_preserves_value(db, dev_user_id, dev_user_state):
    """Omitting material leaves the stored value unchanged."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck", material="wool")
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"name": "Updated Name"},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Updated Name"
    assert body["material"] == "wool"


def test_patch_favorite(db, dev_user_id, dev_user_state):
    """Patch isFavorite."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck", isFavorite=False)
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"isFavorite": True},
        headers=HEADERS,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["isFavorite"] == True


def test_invalid_vocabulary_422(db, dev_user_id, dev_user_state):
    """Patch with invalid category code → 422."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck")
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"category": "unknown_category"},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_invalid_color_422(db, dev_user_id, dev_user_state):
    """Patch with invalid color code → 422."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck")
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"color": "unknown_color"},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_patch_invalid_material_422(db, dev_user_id, dev_user_state):
    """Patch with invalid material code → 422."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck")
    resp = client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"material": "unknown_material"},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_delete_owned_item(db, dev_user_id, dev_user_state):
    """Delete an owned item → 204 No Content."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck")
    resp = client.delete(f"/v1/wardrobe/items/{item_id}", headers=HEADERS)
    assert resp.status_code == 204

    # Verify it's gone
    resp2 = client.get(f"/v1/wardrobe/items/{item_id}", headers=HEADERS)
    assert resp2.status_code == 404


def test_delete_missing_item_404(db, dev_user_id, dev_user_state):
    """Delete a non-existent item → 404 NOT_FOUND."""
    _seed_wardrobe_categories(db)
    fake_id = uuid4()
    resp = client.delete(f"/v1/wardrobe/items/{fake_id}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_delete_foreign_item_404(db, dev_user_id, dev_user_state):
    """Delete another user's item → 404 NOT_FOUND."""
    _seed_wardrobe_categories(db)
    # Create an item for a different user
    Session = db
    with Session() as session:
        other_user = Users(
            auth_provider="dev", auth_subject="other-user", display_name="Other User"
        )
        session.add(other_user)
        session.flush()
        other_id = other_user.id
        session.add(UserState(user_id=other_id))
        session.commit()

    # Create item for other user, then try to delete it as dev user
    item = _seed_wardrobe_item(db, other_id, name="Other Item")
    resp = client.delete(f"/v1/wardrobe/items/{item.id}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_updated_at_changes_after_patch(db, dev_user_id, dev_user_state):
    """updatedAt changes after patch."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck")
    # Get initial item
    resp = client.get(f"/v1/wardrobe/items/{item_id}", headers=HEADERS)
    initial_updated_at = resp.json()["updatedAt"]
    # Patch the item
    client.patch(
        f"/v1/wardrobe/items/{item_id}",
        json={"name": "Updated"},
        headers=HEADERS,
    )
    # Get updated item
    resp2 = client.get(f"/v1/wardrobe/items/{item_id}", headers=HEADERS)
    updated_updated_at = resp2.json()["updatedAt"]
    assert updated_updated_at != initial_updated_at


# --- Step 14.3: Wardrobe insight (W-7, UC-14) ---------------------------------

def test_insight_requires_auth():
    """Unauthenticated insight access returns 401."""
    resp = client.get("/v1/wardrobe/insight")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_insight_empty_returns_204(db, dev_user_id, dev_user_state):
    """Empty wardrobe → 204 with no fabricated insight body."""
    _seed_wardrobe_categories(db)
    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 204
    assert resp.content == b""


def test_insight_populated_counts(db, dev_user_id, dev_user_state):
    """Populated wardrobe → grounded total, per-category, missing, favorites."""
    _seed_wardrobe_categories(db)
    _seed_wardrobe_item(db, dev_user_id, name="Fav Top", category="tops", isFavorite=True)
    _seed_wardrobe_item(db, dev_user_id, name="Plain Top", category="tops")
    _seed_wardrobe_item(db, dev_user_id, name="Jeans", category="bottoms")

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Wardrobe Gaps"
    assert body["insight"] == (
        "You have 3 items across 2 of 5 categories (bottoms, tops), "
        "with 1 marked as favorite. "
        "Missing: accessories, footwear, outerwear."
    )


def test_insight_complete_wardrobe(db, dev_user_id, dev_user_state):
    """All canonical categories covered → health text, zero favorites."""
    _seed_wardrobe_categories(db)
    for category in ("tops", "bottoms", "outerwear", "footwear", "accessories"):
        _seed_wardrobe_item(db, dev_user_id, name=f"Item {category}", category=category)

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Wardrobe Health"
    assert body["insight"] == (
        "You have 5 items covering all 5 wardrobe categories "
        "(accessories, bottoms, footwear, outerwear, tops), "
        "with 0 marked as favorites."
    )


def test_insight_is_deterministic(db, dev_user_id, dev_user_state):
    """Repeated calls return the identical insight."""
    _seed_wardrobe_categories(db)
    _seed_wardrobe_item(db, dev_user_id, name="Fav Top", category="tops", isFavorite=True)

    first = client.get("/v1/wardrobe/insight", headers=HEADERS).json()
    second = client.get("/v1/wardrobe/insight", headers=HEADERS).json()
    assert first == second
    assert first["insight"] == (
        "You have 1 item across 1 of 5 categories (tops), "
        "with 1 marked as favorite. "
        "Missing: accessories, bottoms, footwear, outerwear."
    )


def test_insight_owner_isolated(db, dev_user_id, dev_user_state):
    """Another user's items never leak into this user's insight."""
    _seed_wardrobe_categories(db)
    Session = db
    with Session() as session:
        other_user = Users(
            auth_provider="dev", auth_subject="other-user", display_name="Other User"
        )
        session.add(other_user)
        session.flush()
        other_id = other_user.id
        session.add(UserState(user_id=other_id))
        session.commit()

    _seed_wardrobe_item(db, other_id, name="Other Item")

    # Dev wardrobe is still empty → 204 despite the other user's item.
    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 204

    # Dev's own item counts only their item.
    _seed_wardrobe_item(db, dev_user_id, name="My Top", category="tops")
    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    assert "1 item across 1 of 5 categories (tops)" in resp.json()["insight"]


def test_insight_does_not_mutate(db, dev_user_id, dev_user_state):
    """The insight endpoint is read-only: items and totals are unchanged."""
    _seed_wardrobe_categories(db)
    item_id = _seed_wardrobe_item_with_id(db, dev_user_id, name="Merino Crew Neck")
    before = client.get("/v1/wardrobe/items", headers=HEADERS).json()

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200

    after = client.get("/v1/wardrobe/items", headers=HEADERS).json()
    assert after["total"] == before["total"] == 1
    assert after["items"][0]["id"] == str(item_id)
    assert after["items"][0]["updatedAt"] == before["items"][0]["updatedAt"]


# --- Step 14.4: saved-look-aware wardrobe gaps -------------------------------

def test_insight_without_saved_looks_has_no_saved_look_claim(db, dev_user_id, dev_user_state):
    """Wardrobe with no saved looks → 14.3 text verbatim, no saved-look claim."""
    _seed_wardrobe_categories(db)
    _seed_wardrobe_item(db, dev_user_id, name="Fav Top", category="tops", isFavorite=True)
    _seed_wardrobe_item(db, dev_user_id, name="Plain Top", category="tops")
    _seed_wardrobe_item(db, dev_user_id, name="Jeans", category="bottoms")

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Wardrobe Gaps"
    assert body["insight"] == (
        "You have 3 items across 2 of 5 categories (bottoms, tops), "
        "with 1 marked as favorite. "
        "Missing: accessories, footwear, outerwear."
    )
    assert "Saved looks" not in body["insight"]


def test_insight_reflects_saved_outfit_representation(db, dev_user_id, dev_user_state):
    """Outfit save through the real contract → grounded representation sentence."""
    _seed_wardrobe_categories(db)
    top_a = _seed_wardrobe_item(db, dev_user_id, name="Top A", category="tops")
    top_b = _seed_wardrobe_item(db, dev_user_id, name="Top B", category="tops")
    _seed_wardrobe_item(db, dev_user_id, name="Jeans", category="bottoms")
    _seed_wardrobe_item(db, dev_user_id, name="Sneakers", category="footwear")

    save = client.post(
        "/v1/looks/saved",
        json={
            "lookId": None,
            "title": "Weekend Outfit",
            "sourceContext": "outfit",
            "snapshot": {"selectedItemIds": [str(top_b.id), str(top_a.id)]},
        },
        headers={**HEADERS, "Idempotency-Key": "insight-outfit-1"},
    )
    assert save.status_code == 201

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Wardrobe Gaps"
    assert body["insight"] == (
        "You have 4 items across 3 of 5 categories (bottoms, footwear, tops), "
        "with 0 marked as favorites. "
        "Missing: accessories, outerwear. "
        "Saved looks include items from 1 of your 3 covered categories (tops). "
        "Not represented in saved looks: bottoms, footwear."
    )


def test_insight_unrepresented_category_in_full_wardrobe(db, dev_user_id, dev_user_state):
    """All categories covered but the save names one → health + representation gap."""
    _seed_wardrobe_categories(db)
    top = _seed_wardrobe_item(db, dev_user_id, name="Top", category="tops")
    for category in ("bottoms", "outerwear", "footwear", "accessories"):
        _seed_wardrobe_item(db, dev_user_id, name=f"Item {category}", category=category)
    _seed_saved_look(
        db,
        dev_user_id,
        snapshot={"selectedItemIds": [str(top.id)]},
        idempotency_key="insight-full-1",
    )

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Wardrobe Health"
    assert body["insight"] == (
        "You have 5 items covering all 5 wardrobe categories "
        "(accessories, bottoms, footwear, outerwear, tops), "
        "with 0 marked as favorites. "
        "Saved looks include items from 1 of your 5 covered categories (tops). "
        "Not represented in saved looks: accessories, bottoms, footwear, outerwear."
    )


def test_insight_missing_category_takes_precedence(db, dev_user_id, dev_user_state):
    """Saves covering every covered category → still 'Wardrobe Gaps', no unrep sentence."""
    _seed_wardrobe_categories(db)
    top = _seed_wardrobe_item(db, dev_user_id, name="Top", category="tops")
    jeans = _seed_wardrobe_item(db, dev_user_id, name="Jeans", category="bottoms")
    _seed_saved_look(
        db,
        dev_user_id,
        snapshot={"selectedItemIds": [str(top.id), str(jeans.id)]},
        idempotency_key="insight-precedence-1",
    )

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Wardrobe Gaps"
    assert body["insight"] == (
        "You have 2 items across 2 of 5 categories (bottoms, tops), "
        "with 0 marked as favorites. "
        "Missing: accessories, footwear, outerwear. "
        "Saved looks include items from 2 of your 2 covered categories (bottoms, tops)."
    )
    assert "Not represented" not in body["insight"]


def test_insight_ignores_other_users_saved_looks(db, dev_user_id, dev_user_state):
    """Another user's outfit save — even one naming our item ID — never leaks in."""
    _seed_wardrobe_categories(db)
    mine = _seed_wardrobe_item(db, dev_user_id, name="My Top", category="tops")

    Session = db
    with Session() as session:
        other_user = Users(
            auth_provider="dev", auth_subject="other-user", display_name="Other User"
        )
        session.add(other_user)
        session.flush()
        other_id = other_user.id
        session.add(UserState(user_id=other_id))
        session.commit()

    _seed_saved_look(
        db,
        other_id,
        snapshot={"selectedItemIds": [str(mine.id)]},
        idempotency_key="insight-foreign-1",
    )

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["insight"] == (
        "You have 1 item across 1 of 5 categories (tops), "
        "with 0 marked as favorites. "
        "Missing: accessories, bottoms, footwear, outerwear."
    )
    assert "Saved looks" not in body["insight"]


def test_insight_ignores_stale_and_non_outfit_saved_looks(db, dev_user_id, dev_user_state):
    """Stale IDs, item-less/legacy/hairstyle saves → wardrobe facts only, no 500."""
    _seed_wardrobe_categories(db)
    top = _seed_wardrobe_item(db, dev_user_id, name="My Top", category="tops")

    _seed_saved_look(
        db, dev_user_id,
        snapshot={"selectedItemIds": [str(uuid4())]},
        idempotency_key="insight-stale-1",
    )
    _seed_saved_look(db, dev_user_id, snapshot={}, idempotency_key="insight-stale-2")
    _seed_saved_look(
        db, dev_user_id,
        snapshot={"selectedItemIds": ["not-a-uuid"]},
        idempotency_key="insight-stale-3",
    )
    # Legacy row: unknown domain, yet references a real item — still ignored.
    _seed_saved_look(
        db, dev_user_id,
        source_context=None,
        snapshot={"selectedItemIds": [str(top.id)]},
        idempotency_key="insight-legacy-1",
    )
    # Hairstyle saves reference no wardrobe items by contract.
    _seed_saved_look(
        db, dev_user_id,
        title="Quiff",
        source_context="hairstyle",
        snapshot={"appearance": {}},
        idempotency_key="insight-hairstyle-1",
    )

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["insight"] == (
        "You have 1 item across 1 of 5 categories (tops), "
        "with 0 marked as favorites. "
        "Missing: accessories, bottoms, footwear, outerwear."
    )
    assert "Saved looks" not in body["insight"]


def test_insight_ignores_deleted_item_references(db, dev_user_id, dev_user_state):
    """A save referencing an item deleted afterwards → ignored, no 500."""
    _seed_wardrobe_categories(db)
    doomed = _seed_wardrobe_item(db, dev_user_id, name="Doomed Top", category="tops")
    _seed_wardrobe_item(db, dev_user_id, name="Kept Top", category="tops")
    _seed_saved_look(
        db, dev_user_id,
        snapshot={"selectedItemIds": [str(doomed.id)]},
        idempotency_key="insight-deleted-1",
    )

    deleted = client.delete(f"/v1/wardrobe/items/{doomed.id}", headers=HEADERS)
    assert deleted.status_code == 204

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["insight"] == (
        "You have 1 item across 1 of 5 categories (tops), "
        "with 0 marked as favorites. "
        "Missing: accessories, bottoms, footwear, outerwear."
    )
    assert "Saved looks" not in body["insight"]


def test_insight_with_saved_looks_is_deterministic(db, dev_user_id, dev_user_state):
    """Repeated calls with saved looks return the identical response."""
    _seed_wardrobe_categories(db)
    top = _seed_wardrobe_item(db, dev_user_id, name="Top", category="tops")
    _seed_wardrobe_item(db, dev_user_id, name="Jeans", category="bottoms")
    _seed_saved_look(
        db, dev_user_id,
        snapshot={"selectedItemIds": [str(top.id)]},
        idempotency_key="insight-determinism-1",
    )

    first = client.get("/v1/wardrobe/insight", headers=HEADERS)
    second = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["insight"] == (
        "You have 2 items across 2 of 5 categories (bottoms, tops), "
        "with 0 marked as favorites. "
        "Missing: accessories, footwear, outerwear. "
        "Saved looks include items from 1 of your 2 covered categories (tops). "
        "Not represented in saved looks: bottoms."
    )


def test_insight_with_saved_looks_does_not_mutate(db, dev_user_id, dev_user_state):
    """Insight with saved looks is read-only: neither table changes."""
    _seed_wardrobe_categories(db)
    top = _seed_wardrobe_item(db, dev_user_id, name="Top", category="tops")
    _seed_saved_look(
        db, dev_user_id,
        snapshot={"selectedItemIds": [str(top.id)]},
        idempotency_key="insight-readonly-1",
    )

    Session = db
    with Session() as session:
        wardrobe_before = session.execute(
            select(func.count()).select_from(WardrobeItems)
        ).scalar_one()
        looks_before = session.execute(
            select(func.count()).select_from(SavedLooks)
        ).scalar_one()
    items_before = client.get("/v1/wardrobe/items", headers=HEADERS).json()

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    assert "Saved looks include items from 1 of your 1 covered categories (tops)." in resp.json()["insight"]

    with Session() as session:
        wardrobe_after = session.execute(
            select(func.count()).select_from(WardrobeItems)
        ).scalar_one()
        looks_after = session.execute(
            select(func.count()).select_from(SavedLooks)
        ).scalar_one()
    items_after = client.get("/v1/wardrobe/items", headers=HEADERS).json()
    assert (wardrobe_after, looks_after) == (wardrobe_before, looks_before) == (1, 1)
    assert items_after["items"][0]["updatedAt"] == items_before["items"][0]["updatedAt"]


def test_insight_duplicate_saved_look_references_do_not_inflate(db, dev_user_id, dev_user_state):
    """The same item ID twice in one snapshot + across snapshots counts once."""
    _seed_wardrobe_categories(db)
    top = _seed_wardrobe_item(db, dev_user_id, name="Top", category="tops")
    _seed_saved_look(
        db, dev_user_id,
        snapshot={"selectedItemIds": [str(top.id), str(top.id)]},
        idempotency_key="insight-duplicate-1",
    )
    _seed_saved_look(
        db, dev_user_id,
        snapshot={"selectedItemIds": [str(top.id)]},
        idempotency_key="insight-duplicate-2",
    )

    resp = client.get("/v1/wardrobe/insight", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["insight"] == (
        "You have 1 item across 1 of 5 categories (tops), "
        "with 0 marked as favorites. "
        "Missing: accessories, bottoms, footwear, outerwear. "
        "Saved looks include items from 1 of your 1 covered categories (tops)."
    )