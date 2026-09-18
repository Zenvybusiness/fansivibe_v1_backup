"""M11 P4: typed 204 empty reasons (`X-Outfit-Empty-Reason`).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(same `db` fixture as `test_m13_outfits_api.py`; truncated-clean per test).

The header is always emitted on 204 with an empty body, so older
clients ignoring it see byte-identical behavior. Reasons come from the
same deterministic backend state that produced zero candidates (no
LLM, no text parsing): `empty_wardrobe` (no owned rows),
`missing_required_category` (tops or bottoms absent).
`no_legal_candidate` is defensive and currently unreachable via the API
(tops+bottoms always pair), so it is covered by construction, not by a
live case. 200 behavior is unchanged (no header).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}
REASON_HEADER = "x-outfit-empty-reason"

PREFS = {
    "occasion": "office",
    "mood": "classic",
    "fit": "tailored",
    "colorPalette": "warm",
}


def _create(name: str, category: str, color: str) -> dict:
    resp = client.post(
        "/v1/wardrobe/items",
        json={"name": name, "category": category, "color": color},
        headers=HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _generate() -> object:
    return client.post("/v1/outfits/generate", json=PREFS, headers=HEADERS)


def test_empty_wardrobe_reports_typed_reason_with_empty_body():
    resp = _generate()
    assert resp.status_code == 204, resp.text
    assert resp.content == b""
    assert resp.headers[REASON_HEADER] == "empty_wardrobe"


def test_tops_only_reports_missing_required_category():
    _create("Lonely Tee", "tops", "black")
    resp = _generate()
    assert resp.status_code == 204, resp.text
    assert resp.content == b""
    assert resp.headers[REASON_HEADER] == "missing_required_category"


def test_bottoms_only_reports_missing_required_category():
    _create("Lonely Jeans", "bottoms", "black")
    resp = _generate()
    assert resp.status_code == 204, resp.text
    assert resp.content == b""
    assert resp.headers[REASON_HEADER] == "missing_required_category"


def test_successful_generation_has_no_empty_reason_header():
    _create("Tee", "tops", "black")
    _create("Jeans", "bottoms", "white")
    resp = _generate()
    assert resp.status_code == 200, resp.text
    assert REASON_HEADER not in resp.headers
    body = resp.json()
    assert body["components"]
    assert {item["category"] for item in body["components"]} >= {"tops", "bottoms"}
