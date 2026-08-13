"""API tests for the grooming analysis surface (#38).

DB-backed — runs when PostgreSQL is reachable, skips otherwise
(see `tests/conftest.py`).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from sqlalchemy import select

from app.infrastructure.db.models import UserState, Users

pytestmark = pytest.mark.usefixtures("db")

from app.main import app  # noqa: E402

client = TestClient(app)
HEADERS = {"Authorization": "Bearer dev"}


def _dev_user_id(session):
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


def _seed_profile(db, profile: dict):
    Session = db
    with Session() as session:
        user_id = _dev_user_id(session)
        state = session.get(UserState, user_id)
        state.style_profile = profile
        session.commit()


# --- auth / validation ------------------------------------------------------

def test_submit_requires_auth():
    resp = client.post("/v1/analysis/grooming", json={})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "AUTHENTICATION_ERROR"


def test_submit_requires_face_profile_ref():
    resp = client.post("/v1/analysis/grooming", json={}, headers=HEADERS)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_submit_rejects_malformed_profile_ref():
    resp = client.post(
        "/v1/analysis/grooming",
        json={"face_profile_ref": "not-a-uuid"},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_submit_without_profile_returns_insufficient_data():
    resp = client.post(
        "/v1/analysis/grooming",
        json={"face_profile_ref": str(uuid.uuid4())},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "INSUFFICIENT_USER_DATA"
    assert body["details"]["missing"] == "face"


# --- happy path -------------------------------------------------------------

def test_full_flow_202_then_completed_with_result(db):
    _seed_profile(
        db,
        {"face_shape": "Oval", "skin_tone": "Warm Medium", "style_type": "Modern Classic"},
    )
    resp = client.post(
        "/v1/analysis/grooming",
        json={"face_profile_ref": str(uuid.uuid4())},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    got = client.get(f"/v1/analysis/runs/{run_id}", headers=HEADERS)
    assert got.status_code == 200
    body = got.json()
    assert body["run_id"] == run_id
    assert body["run_type"] == "grooming"
    assert body["status"] == "completed"
    assert body["completed_at"] is not None
    assert body["engine_version"] is not None
    assert body["input_media"] is None

    result = body["result"]
    assert result["appearance"]["faceShape"] == "Oval"
    assert result["appearance"]["sourceRunId"] == run_id
    recs = result["recommendations"]
    assert recs["top"]["id"] == "structured_goatee"
    assert recs["top"]["matchScore"] <= 1.0
    assert len(recs["alternatives"]) == 3


def test_round_profile_ranks_goatee(db):
    _seed_profile(db, {"face_shape": "Round"})
    resp = client.post(
        "/v1/analysis/grooming",
        json={"face_profile_ref": str(uuid.uuid4())},
        headers=HEADERS,
    )
    run_id = resp.json()["run_id"]
    body = client.get(f"/v1/analysis/runs/{run_id}", headers=HEADERS).json()
    assert body["result"]["recommendations"]["top"]["id"] == "classic_stubble"


def test_recommendation_failure_marks_run_failed_with_processsing_failure(db, monkeypatch):
    # Pipeline failure (empty knowledge → engine raises) must yield a `failed`
    # run with PROCESSING_FAILURE + details.run_id — never a stuck pending run.
    _seed_profile(db, {"face_shape": "Oval"})

    def _empty_retrieve(self):
        return []

    monkeypatch.setattr(
        "app.infrastructure.external.knowledge.CatalogKnowledgeSource.retrieve_grooming_looks",
        _empty_retrieve,
    )

    resp = client.post(
        "/v1/analysis/grooming",
        json={"face_profile_ref": str(uuid.uuid4())},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    run_id = resp.json()["run_id"]

    got = client.get(f"/v1/analysis/runs/{run_id}", headers=HEADERS)
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "failed"
    assert body["completed_at"] is not None
    assert body["result"] is None
    assert body["error"]["code"] == "PROCESSING_FAILURE"
    assert body["error"]["details"]["run_id"] == run_id

# --- owner scoping / errors -------------------------------------------------


def test_get_foreign_or_missing_run_returns_404(db):
    _seed_profile(db, {"face_shape": "Oval"})
    resp = client.get(f"/v1/analysis/runs/{uuid.uuid4()}", headers=HEADERS)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_get_malformed_run_id_returns_422():
    resp = client.get("/v1/analysis/runs/not-a-uuid", headers=HEADERS)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_runs_returns_summaries_without_result(db):
    _seed_profile(db, {"face_shape": "Oval"})
    for _ in range(3):
        run_id = client.post(
            "/v1/analysis/grooming",
            json={"face_profile_ref": str(uuid.uuid4())},
            headers=HEADERS,
        ).json()["run_id"]
        assert run_id

    resp = client.get("/v1/analysis/runs", headers=HEADERS)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert body["page"] == 1
    assert body["page_size"] == 20
    for item in body["items"]:
        assert "result" not in item
        assert "error" not in item
        assert item["status"] == "completed"


# --- groom-specific validation ----------------------------------------------

def test_submit_rejects_empty_face_profile_ref():
    resp = client.post(
        "/v1/analysis/grooming",
        json={},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_submit_rejects_invalid_uuid_face_profile_ref():
    resp = client.post(
        "/v1/analysis/grooming",
        json={"face_profile_ref": "invalid-uuid"},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_submit_rejects_missing_face_profile_ref():
    resp = client.post(
        "/v1/analysis/grooming",
        json={},
        headers=HEADERS,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_correct_response_structure_202():
    """202 response contains run_id."""
    resp = client.post(
        "/v1/analysis/grooming",
        json={"face_profile_ref": str(uuid.uuid4())},
        headers=HEADERS,
    )
    assert resp.status_code == 202
    body = resp.json()
    assert "run_id" in body
    assert isinstance(body["run_id"], str)


def test_user_ownership_of_run(db):
    """A grooming run can only be read by its owner."""
    _seed_profile(db, {"face_shape": "Oval"})
    resp = client.post(
        "/v1/analysis/grooming",
        json={"face_profile_ref": str(uuid.uuid4())},
        headers=HEADERS,
    )
    run_id = resp.json()["run_id"]

    # Other user cannot read this run
    resp = client.get(f"/v1/analysis/runs/{run_id}", headers={"Authorization": "Bearer other"})
    assert resp.status_code == 401


def test_correct_run_status_after_completion(db):
    _seed_profile(db, {"face_shape": "Oval", "skin_tone": "Warm Medium", "style_type": "Modern Classic"})
    resp = client.post(
        "/v1/analysis/grooming",
        json={"face_profile_ref": str(uuid.uuid4())},
        headers=HEADERS,
    )
    assert resp.status_code == 202

    got = client.get(f"/v1/analysis/runs/{resp.json()['run_id']}", headers=HEADERS)
    assert got.status_code == 200
    assert got.json()["status"] == "completed"
    assert got.json()["result"] is not None