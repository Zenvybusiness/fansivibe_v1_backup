"""M11 P3: persisted wardrobe (incl. M11 P2 garment-shaped items) → outfit builder.

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(same `db` fixture as `test_m13_outfits_api.py`; truncated-clean per test).

Proves the required flow at the HTTP boundary with no mocks:
M11 P2 save shape (`POST /v1/wardrobe/items` with `imageRef`) →
persisted row → backend reload (`GET /v1/wardrobe/items`) →
`POST /v1/outfits/generate` uses the real persisted UUIDs and the
persisted color/category/material values. Deleted IDs can never appear.

Ownership isolation, empty-wardrobe 204, determinism, and read-only
derivation are already proven in `test_m13_outfits_api.py`
(`test_generate_ignores_foreign_items`,
`test_generate_valid_wardrobe_returns_outfit_with_owned_uuids`,
`test_generate_empty_wardrobe_is_204`,
`test_generate_is_deterministic`, `test_generate_has_no_side_effects`)
and are not duplicated here.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}

PREFS = {
    "occasion": "office",
    "mood": "classic",
    "fit": "tailored",
    "colorPalette": "warm",
}

# M11 P2 save shape: analysis-confirmed garment with media provenance.
GARMENT_TOP = {
    "name": "Analyzed Oxford Shirt",
    "category": "tops",
    "color": "navy",
    "material": "cotton",
    "imageRef": {
        "key": "users/dev/scans/run-1/input.jpg",
        "contentHash": "abc123",
        "sourceRunId": "run-1",
    },
}
GARMENT_BOTTOM = {
    "name": "Analyzed Chinos",
    "category": "bottoms",
    "color": "black",
    "material": "cotton",
    "imageRef": {
        "key": "users/dev/scans/run-2/input.jpg",
        "contentHash": "def456",
        "sourceRunId": "run-2",
    },
}


def _create(payload: dict) -> dict:
    resp = client.post("/v1/wardrobe/items", json=payload, headers=HEADERS)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _reload() -> dict:
    resp = client.get("/v1/wardrobe/items", headers=HEADERS)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _generate() -> object:
    return client.post("/v1/outfits/generate", json=PREFS, headers=HEADERS)


def test_garment_shaped_items_persist_reload_and_drive_generation():
    top = _create(GARMENT_TOP)
    bottom = _create(GARMENT_BOTTOM)

    # Persisted rows carry real backend UUIDs.
    UUID(top["id"])
    UUID(bottom["id"])
    assert top["id"] != bottom["id"]

    # Backend reload (the same GET the wardrobe screen issues after save)
    # returns the persisted rows with persisted values intact.
    reloaded = _reload()
    by_id = {item["id"]: item for item in reloaded["items"]}
    assert top["id"] in by_id and bottom["id"] in by_id
    assert by_id[top["id"]]["category"] == "tops"
    assert by_id[top["id"]]["color"] == "navy"
    assert by_id[top["id"]]["material"] == "cotton"
    assert by_id[bottom["id"]]["category"] == "bottoms"

    # Generation uses the persisted IDs and persisted values — no substitutes.
    resp = _generate()
    assert resp.status_code == 200, resp.text
    body = resp.json()
    component_ids = [item["id"] for item in body["components"]]
    assert set(component_ids) <= set(by_id)
    assert top["id"] in component_ids
    assert bottom["id"] in component_ids
    by_component = {item["id"]: item for item in body["components"]}
    assert by_component[top["id"]]["category"] == "tops"
    assert by_component[top["id"]]["color"] == "navy"
    assert "top_" not in resp.text and "acc_" not in resp.text


def test_deleted_item_id_never_appears_in_generated_outfit():
    top = _create(GARMENT_TOP)
    bottom = _create(GARMENT_BOTTOM)
    doomed = _create(
        {
            "name": "Doomed Tee",
            "category": "tops",
            "color": "white",
        }
    )

    resp = client.delete(f"/v1/wardrobe/items/{doomed['id']}", headers=HEADERS)
    assert resp.status_code == 204, resp.text

    reloaded_ids = {item["id"] for item in _reload()["items"]}
    assert doomed["id"] not in reloaded_ids
    assert top["id"] in reloaded_ids and bottom["id"] in reloaded_ids

    resp = _generate()
    assert resp.status_code == 200, resp.text
    component_ids = {item["id"] for item in resp.json()["components"]}
    assert doomed["id"] not in component_ids
    assert component_ids <= reloaded_ids
