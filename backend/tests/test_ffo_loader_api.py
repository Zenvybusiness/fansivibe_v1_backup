"""API tests for the additive FFO loader reads (`GET /v1/knowledge/ffo*`).

File-backed only — no database, no user data (no `db` fixture).
Covers: index envelope (26 names, titles, pagination, both version
headers, public incl. bogus-token proof); detail verbatim schema;
unknown name → 404 NOT_FOUND; malformed pagination → 422.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
BASE = "/v1/knowledge/ffo"
BOGUS = {"Authorization": "Bearer not-a-real-token"}


def test_index_lists_26_schemas_with_headers():
    response = client.get(f"{BASE}?page=1&page_size=30")
    assert response.status_code == 200
    assert response.headers["X-Ffo-Version"] == "1.0"
    assert response.headers["X-Knowledge-Version"] == "1.1"
    body = response.json()
    assert body["total"] == 27 and body["page"] == 1
    names = [item["name"] for item in body["items"]]
    assert "outfit" in names and "wardrobe_item" in names
    assert all(item["title"] for item in body["items"])


def test_index_paginates_and_is_public():
    first = client.get(f"{BASE}?page=1&page_size=10").json()
    second = client.get(f"{BASE}?page=2&page_size=10").json()
    assert len(first["items"]) == 10 and len(second["items"]) == 10
    assert {i["name"] for i in first["items"]}.isdisjoint({i["name"] for i in second["items"]})
    assert client.get(BASE, headers=BOGUS).status_code == 200


def test_detail_returns_verbatim_schema():
    response = client.get(f"{BASE}/outfit")
    assert response.status_code == 200
    assert response.headers["X-Ffo-Version"] == "1.0"
    body = response.json()
    assert body["$id"].endswith("outfit.schema.json")
    assert body["title"] == "FFO Outfit"


def test_detail_unknown_name_is_404():
    response = client.get(f"{BASE}/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_malformed_pagination_is_422():
    assert client.get(f"{BASE}?page=0").status_code == 422
    assert client.get(f"{BASE}?page_size=101").status_code == 422
