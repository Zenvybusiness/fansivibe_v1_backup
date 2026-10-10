"""D7 Trend Analysis API + FFO schema-validation tests.

Two layers:

- DB-free API tests exercise ``GET /v1/trends/analysis`` with the repository
  and auth dependencies stubbed, so they run everywhere.
- DB-backed tests (``db`` fixture) exercise the real repository path against the
  disposable database and assert read-only behaviour.

Plus direct tests that the D6 ``to_ffo_trend()`` projection validates against
the authoritative FFO ``trend.schema.json`` (and ``trend_signal.schema.json``).
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_current_user_id, get_trend_repository
from app.data.ffo.validation import trend_errors, trend_signal_errors
from app.domain.services.trends import (
    REASON_FIXTURE,
    REASON_NO_DEMAND,
    STAGE_INSUFFICIENT,
    ObservationEvidence,
    compute_trend_candidates,
    to_ffo_trend,
)
from app.main import app

PATH = "/v1/trends/analysis"
HEADERS = {"Authorization": "Bearer dev"}
client = TestClient(app)

NOW = datetime.now(timezone.utc)
WIN_START = NOW - timedelta(days=4)   # 4-day window, midpoint NOW-2d
WIN_END = NOW
EARLY = NOW - timedelta(days=3)       # first half
LATE = NOW - timedelta(days=1)        # second half
Q = {"window_start": WIN_START.isoformat(), "window_end": WIN_END.isoformat()}

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _obs(category, *, when, source="s1", product=None, price=None, availability=None, is_fixture=False):
    return ObservationEvidence(
        product_id=product or uuid4(),
        category=category,
        source=source,
        observed_at=when,
        price=price,
        availability=availability,
        is_fixture=is_fixture,
    )


def _balanced(category="outerwear", *, when, is_fixture=False):
    """4 observations = 2 sources x 2 distinct products, all at ``when``."""
    p1, p2 = uuid4(), uuid4()
    return tuple(
        _obs(category, when=when, source=s, product=p, is_fixture=is_fixture)
        for s in ("s1", "s2")
        for p in (p1, p2)
    )


class _FakeRepo:
    def __init__(self, evidence=()):
        self._evidence = tuple(evidence)

    def observations_in_window(self, *, window_start, window_end):
        return self._evidence


class _RaisingRepo:
    def observations_in_window(self, *, window_start, window_end):
        raise SQLAlchemyError("boom")


def _stub_client(repo):
    """DB-free client: stub auth (UUID) and the trend repository."""
    app.dependency_overrides[get_trend_repository] = lambda: repo
    app.dependency_overrides[get_current_user_id] = lambda: UUID(int=1)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Successful analysis, insufficient evidence, empty publication
# ---------------------------------------------------------------------------


def test_analysis_without_demand_provider_is_insufficient():
    repo = _FakeRepo(_balanced(when=EARLY) + _balanced(when=LATE))
    body = _stub_client(repo).get(PATH, headers=HEADERS, params=Q).json()

    assert body["demandTrendStatus"] == STAGE_INSUFFICIENT
    assert body["evidenceType"] == "catalog_activity"
    assert body["directDemandAvailable"] is False
    assert body["publishedCandidates"] == []
    assert body["insufficientEvidenceReason"] == REASON_NO_DEMAND
    assert body["sourceCoverage"] == 2
    assert body["observationCount"] == 8
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["publishable"] is False
    assert REASON_NO_DEMAND in body["candidates"][0]["reasons"]


def test_empty_evidence_returns_no_candidates():
    body = _stub_client(_FakeRepo(())).get(PATH, headers=HEADERS, params=Q).json()

    assert body["candidates"] == []
    assert body["publishedCandidates"] == []
    assert body["catalogActivityStatus"] == "no_observations"
    assert body["observationCount"] == 0
    assert body["sourceCoverage"] == 0
    assert body["demandTrendStatus"] == STAGE_INSUFFICIENT


def test_fixture_candidates_are_never_published():
    repo = _FakeRepo(_balanced(when=EARLY, is_fixture=True) + _balanced(when=LATE, is_fixture=True))
    body = _stub_client(repo).get(PATH, headers=HEADERS, params=Q).json()

    candidate = body["candidates"][0]
    assert candidate["fixtureDerived"] is True
    assert candidate["publishable"] is False
    assert REASON_FIXTURE in candidate["reasons"]
    assert candidate["ffoTrend"] is None
    assert body["publishedCandidates"] == []


def test_missing_metrics_stay_null_never_zero():
    repo = _FakeRepo(_balanced(when=EARLY) + _balanced(when=LATE))
    candidate = _stub_client(repo).get(PATH, headers=HEADERS, params=Q).json()["candidates"][0]

    assert candidate["priceChangeRatio"] is None
    assert candidate["inStockRatio"] is None
    assert candidate["catalogGrowth"] == 0.0  # present metric is not nulled


def test_catalog_activity_is_never_labelled_consumer_demand():
    repo = _FakeRepo(_balanced(when=EARLY) + _balanced(when=LATE))
    body = _stub_client(repo).get(PATH, headers=HEADERS, params=Q).json()

    assert body["evidenceType"] == "catalog_activity"
    assert body["directDemandAvailable"] is False
    assert body["demandTrendStatus"] == STAGE_INSUFFICIENT
    candidate = body["candidates"][0]
    assert candidate["evidenceType"] == "catalog_activity"
    assert candidate["catalogActivityStatus"] in {
        "rising", "plateau", "declining", "insufficient_evidence"
    }
    for signal in candidate["signals"]:
        if signal["kind"] == "direct_demand":
            assert signal["available"] is False
            assert signal["value"] is None


def test_deterministic_for_identical_inputs():
    repo = _FakeRepo(_balanced("outerwear", when=EARLY) + _balanced("bottoms", when=LATE))
    first = _stub_client(repo).get(PATH, headers=HEADERS, params=Q).json()
    second = _stub_client(repo).get(PATH, headers=HEADERS, params=Q).json()

    assert first["candidates"] == second["candidates"]
    assert first["windowStart"] == second["windowStart"]
    assert first["publishedCandidates"] == second["publishedCandidates"]


def test_no_internal_ids_or_raw_payloads_in_response():
    repo = _FakeRepo(_balanced(when=EARLY) + _balanced(when=LATE))
    raw = json.dumps(_stub_client(repo).get(PATH, headers=HEADERS, params=Q).json())

    assert "product_id" not in raw
    assert "payload" not in raw.lower()
    assert _UUID.search(raw) is None


# ---------------------------------------------------------------------------
# Window validation, auth, error handling
# ---------------------------------------------------------------------------


def test_reversed_window_is_422():
    params = {"window_start": WIN_END.isoformat(), "window_end": WIN_START.isoformat()}
    response = _stub_client(_FakeRepo()).get(PATH, headers=HEADERS, params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_partial_window_is_422():
    response = _stub_client(_FakeRepo()).get(
        PATH, headers=HEADERS, params={"window_start": WIN_START.isoformat()}
    )
    assert response.status_code == 422


def test_naive_datetime_is_422():
    params = {
        "window_start": datetime(2026, 1, 1, 0, 0, 0).isoformat(),  # no tz
        "window_end": WIN_END.isoformat(),
    }
    response = _stub_client(_FakeRepo()).get(PATH, headers=HEADERS, params=params)
    assert response.status_code == 422


def test_excessively_large_window_is_422():
    params = {
        "window_start": (NOW - timedelta(days=100)).isoformat(),
        "window_end": WIN_END.isoformat(),
    }
    response = _stub_client(_FakeRepo()).get(PATH, headers=HEADERS, params=params)
    assert response.status_code == 422


def test_requires_authentication():
    assert client.get(PATH).status_code == 401


def test_database_failure_is_500_not_fabricated():
    response = _stub_client(_RaisingRepo()).get(PATH, headers=HEADERS, params=Q)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "DATABASE_FAILURE"


# ---------------------------------------------------------------------------
# FFO schema validation (authoritative schemas)
# ---------------------------------------------------------------------------


def _publishable_candidate():
    analysis = compute_trend_candidates(
        _balanced(when=EARLY) + _balanced(when=LATE),
        window_start=WIN_START,
        window_end=WIN_END,
    )
    return replace(
        analysis.candidates[0],
        is_fixture=False,
        demand_signal_available=True,
        publishable=True,
        stage="rising",
    )


def test_ffo_projection_passes_authoritative_schema():
    projection = to_ffo_trend(_publishable_candidate())
    assert projection is not None
    assert trend_errors(projection) == []


def test_ffo_projection_missing_required_field_fails():
    projection = to_ffo_trend(_publishable_candidate())
    del projection["canonical_name"]
    assert trend_errors(projection)


def test_ffo_projection_invalid_type_fails():
    projection = to_ffo_trend(_publishable_candidate())
    projection["confidence"] = "high"
    assert trend_errors(projection)


def test_ffo_projection_invalid_enum_fails():
    projection = to_ffo_trend(_publishable_candidate())
    projection["provenance"]["source_type"] = "BOGUS"
    assert trend_errors(projection)


def test_ffo_projection_confidence_out_of_range_fails():
    projection = to_ffo_trend(_publishable_candidate())
    projection["confidence"] = 1.5
    assert trend_errors(projection)


def test_trend_signal_schema_validation():
    valid = {
        "trend": "oversized denim",
        "confidence": 0.5,
        "signals": [{"source": "s", "metric": "m", "value": 1.0}],
        "provenance": {"source_type": "INFERRED"},
    }
    assert trend_signal_errors(valid) == []
    del valid["trend"]
    assert trend_signal_errors(valid)


# ---------------------------------------------------------------------------
# DB-backed: real repository path, read-only, fixtures never published
# ---------------------------------------------------------------------------


def _run_fixture_collection():
    from app.application.collection import CollectSource, CollectionConfig
    from app.infrastructure.db.repositories import DiscoveryRepositorySQL
    from app.infrastructure.external.fixture_source import FixtureSourceAdapter
    from tests.conftest import make_session

    Session = make_session()
    adapter = FixtureSourceAdapter()
    with Session() as session:
        CollectSource(adapter=adapter, repository=DiscoveryRepositorySQL(session))(
            CollectionConfig(source=adapter.source_id)
        )
    return Session


def test_db_backed_empty_database_returns_insufficient(db):
    body = client.get(PATH, headers=HEADERS).json()
    assert body["candidates"] == []
    assert body["publishedCandidates"] == []
    assert body["demandTrendStatus"] == STAGE_INSUFFICIENT
    assert body["directDemandAvailable"] is False


def test_db_backed_fixture_run_is_read_only_and_never_published(db):
    from app.infrastructure.db.repositories import TrendRepositorySQL

    Session = _run_fixture_collection()
    with Session() as session:
        before = len(
            TrendRepositorySQL(session).observations_in_window(
                window_start=WIN_START, window_end=WIN_END + timedelta(days=1)
            )
        )

    body = client.get(PATH, headers=HEADERS).json()

    assert {c["concept"] for c in body["candidates"]} == {"outerwear", "bottoms"}
    assert all(c["fixtureDerived"] and not c["publishable"] for c in body["candidates"])
    assert body["publishedCandidates"] == []

    with Session() as session:
        after = len(
            TrendRepositorySQL(session).observations_in_window(
                window_start=WIN_START, window_end=WIN_END + timedelta(days=1)
            )
        )
    assert after == before  # read-only: the endpoint wrote nothing
