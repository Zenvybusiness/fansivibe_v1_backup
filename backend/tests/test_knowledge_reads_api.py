"""API tests for the M5 knowledge reads (#18–#22, STEP 19.5, DEC-014).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`; schema migrates to `head`, which seeds the
`wardrobe_categories` (5) and `colors` (17) vocabularies).

Covers: #18 list/pagination/empty/invalid-pagination/occasion→422/
style→422/version-header; #19 exact categories/order/envelope/header;
#20 exact colors/order/envelope/header; #21 exact 9 codes/labels/
sortOrders/no-extras/envelope/header/public; #22 frozen wire shape/
system-owned/no-user-leakage/empty-gated/envelope/header/public;
all five public (no auth AND bogus-token proof); malformed pagination.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.schemas.knowledge import ItemReference
from app.data import catalog
from app.infrastructure.db.models import Users, WardrobeItems
from tests.conftest import make_session

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
BASE = "/v1/knowledge"
VERSION_HEADER = "X-Knowledge-Version"
BOGUS = {"Authorization": "Bearer not-a-real-token"}

EXPECTED_CATEGORIES = {
    "tops": "Tops",
    "bottoms": "Bottoms",
    "outerwear": "Outerwear",
    "footwear": "Footwear",
    "accessories": "Accessories",
}

EXPECTED_COLORS = {
    "black": "Black",
    "white": "White",
    "navy": "Navy",
    "charcoal": "Charcoal",
    "grey": "Grey",
    "beige": "Beige",
    "burgundy": "Burgundy",
    "olive": "Olive",
    "khaki": "Khaki",
    "cream": "Cream",
    "light_blue": "Light Blue",
    "blush": "Blush",
    "tan": "Tan",
    "silver": "Silver",
    "gold": "Gold",
    "indigo": "Indigo",
    "stone": "Stone",
}

EXPECTED_OCCASIONS = [
    ("casual", "Casual", 1),
    ("formal", "Formal", 2),
    ("business", "Business", 3),
    ("date", "Date Night", 4),
    ("party", "Party", 5),
    ("travel", "Travel", 6),
    ("workout", "Workout", 7),
    ("other", "Other", 8),
    ("office", "Office", 9),
]

EXPECTED_LOOK_CODES = [
    "textured_quiff",
    "classic_pompadour",
    "side_part",
    "brushed_up_undercut",
    "structured_goatee",
    "classic_stubble",
    "full_beard",
    "goatee_with_mustache",
]


def _versioned(response) -> None:
    """Every success carries the single authoritative knowledge version."""
    assert response.headers.get(VERSION_HEADER) == catalog.KNOWLEDGE_VERSION


# --- #18 looks ---------------------------------------------------------------

def test_looks_list_success_envelope_order_and_version():
    resp = client.get(f"{BASE}/looks")
    assert resp.status_code == 200
    _versioned(resp)
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 8
    assert [item["code"] for item in body["items"]] == EXPECTED_LOOK_CODES
    first = body["items"][0]
    assert first["title"] == "Textured Quiff"
    assert first["description"]
    assert first["reasons"]
    assert first["stylingTips"]
    assert first["maintenance"]
    assert first["bestFor"]
    # No invented occasion/style attributes on any row.
    for item in body["items"]:
        assert "occasion" not in item
        assert "style" not in item


def test_looks_pagination():
    resp = client.get(f"{BASE}/looks", params={"page": 2, "page_size": 3})
    assert resp.status_code == 200
    _versioned(resp)
    body = resp.json()
    assert body["page"] == 2
    assert body["page_size"] == 3
    assert body["total"] == 8
    assert [item["code"] for item in body["items"]] == EXPECTED_LOOK_CODES[3:6]


def test_looks_empty_page_is_200_with_empty_items():
    resp = client.get(f"{BASE}/looks", params={"page": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 8


def test_looks_invalid_pagination_is_422():
    for params in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        resp = client.get(f"{BASE}/looks", params=params)
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_looks_occasion_filter_is_truthful_422():
    resp = client.get(f"{BASE}/looks", params={"occasion": "casual"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "allowed" not in resp.text
    fields = [e["field"] for e in body["error"]["details"]["field_errors"]]
    assert "occasion" in fields


def test_looks_style_filter_is_truthful_422():
    resp = client.get(f"{BASE}/looks", params={"style": "classic"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "allowed" not in resp.text
    fields = [e["field"] for e in body["error"]["details"]["field_errors"]]
    assert "style" in fields


# --- #19 categories ----------------------------------------------------------

def test_categories_exact_codes_labels_order_envelope_version():
    resp = client.get(f"{BASE}/categories")
    assert resp.status_code == 200
    _versioned(resp)
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 5
    items = body["items"]
    assert {item["code"] for item in items} == set(EXPECTED_CATEGORIES)
    for item in items:
        assert item["label"] == EXPECTED_CATEGORIES[item["code"]]
    # Deterministic source order is preserved verbatim.
    assert items == sorted(items, key=lambda i: (i["sortOrder"], i["code"]))
    # No Flutter-only conflicting codes leak in.
    assert {item["code"] for item in items}.isdisjoint({"shoes", "layers", "all"})


# --- #20 colors --------------------------------------------------------------

def test_colors_exact_catalog_order_envelope_version():
    resp = client.get(f"{BASE}/colors")
    assert resp.status_code == 200
    _versioned(resp)
    body = resp.json()
    assert body["total"] == 17
    items = body["items"]
    assert {item["code"] for item in items} == set(EXPECTED_COLORS)
    for item in items:
        assert item["label"] == EXPECTED_COLORS[item["code"]]
    assert items == sorted(items, key=lambda i: (i["sortOrder"], i["code"]))


# --- #21 occasions -----------------------------------------------------------

def test_occasions_exact_frozen_nine():
    resp = client.get(f"{BASE}/occasions")
    assert resp.status_code == 200
    _versioned(resp)
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 9
    assert [
        (item["code"], item["label"], item["sortOrder"]) for item in body["items"]
    ] == EXPECTED_OCCASIONS


def test_occasions_no_extra_or_discover_only_codes():
    resp = client.get(f"{BASE}/occasions")
    codes = {item["code"] for item in resp.json()["items"]}
    assert len(codes) == 9
    assert codes.isdisjoint({"work", "evening", "weekend", "event", "all"})


def test_occasions_public_no_auth_and_bogus_token():
    assert client.get(f"{BASE}/occasions").status_code == 200
    assert client.get(f"{BASE}/occasions", headers=BOGUS).status_code == 200


# --- #22 items ---------------------------------------------------------------

def test_item_reference_wire_shape_is_frozen():
    ref = ItemReference(code="t-shirt", label="T-Shirt", category="tops", sortOrder=1)
    assert ref.model_dump() == {
        "code": "t-shirt",
        "label": "T-Shirt",
        "category": "tops",
        "sortOrder": 1,
    }
    # No ownership/pricing/media fields exist on the frozen shape.
    assert set(ItemReference.model_fields) == {"code", "label", "category", "sortOrder"}


def test_items_empty_gated_envelope_and_version():
    resp = client.get(f"{BASE}/items")
    assert resp.status_code == 200
    _versioned(resp)
    body = resp.json()
    assert body == {"items": [], "page": 1, "page_size": 20, "total": 0}


def test_items_public_no_auth_and_bogus_token():
    assert client.get(f"{BASE}/items").status_code == 200
    assert client.get(f"{BASE}/items", headers=BOGUS).status_code == 200


def test_items_expose_no_user_wardrobe_rows():
    Session = make_session()
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
        session.add(
            WardrobeItems(
                user_id=user.id,
                name="Probe Garment SECRET-ITEM-NAME",
                category_id="tops",
                color_id="black",
            )
        )
        session.commit()
    resp = client.get(f"{BASE}/items")
    assert resp.status_code == 200
    assert resp.json()["items"] == []
    assert "user_id" not in resp.text
    assert "SECRET-ITEM-NAME" not in resp.text


# --- cross-endpoint ----------------------------------------------------------

def test_all_five_endpoints_public_without_auth():
    for path in ("looks", "categories", "colors", "occasions", "items"):
        resp = client.get(f"{BASE}/{path}")
        assert resp.status_code == 200, path
        _versioned(resp)


def test_all_five_endpoints_public_with_bogus_token():
    for path in ("looks", "categories", "colors", "occasions", "items"):
        resp = client.get(f"{BASE}/{path}", headers=BOGUS)
        assert resp.status_code == 200, path


def test_all_five_reject_malformed_pagination():
    for path in ("looks", "categories", "colors", "occasions", "items"):
        resp = client.get(f"{BASE}/{path}", params={"page_size": 101})
        assert resp.status_code == 422, path
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
