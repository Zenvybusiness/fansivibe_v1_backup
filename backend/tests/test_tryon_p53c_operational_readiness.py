"""P5.3C Try-On operational readiness & monitoring regression tests.

Covers:
- Low provider credits warning & Prometheus gauge exposition.
- Genlook credit-check auth failure telemetry & logging without secret leakage.
- Retention cleanup success & partial-failure metrics/logging.
- Result image download storage failure telemetry.
- Interrupted & stale job recovery telemetry.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_storage_adapter, get_tryon_repository, get_tryon_wardrobe_repository
from app.application import tryon as tryon_app
from app.config.settings import clear_settings_cache
from app.domain.ports.tryon_provider import ProviderAuthError
from app.infrastructure.external import genlook_tryon
from app.main import app
from app.telemetry.metrics import get_metrics_collector
from tests.fakes.fake_storage import FakeStorageAdapter


class _WardrobeStub:
    def get_by_id(self, *, user_id, item_id):
        return None


@pytest.fixture
def p53c_env(monkeypatch):
    clear_settings_cache()
    tryon_app.reset_for_tests()
    repo = tryon_app.InMemoryTryOnJobRepository()
    storage = FakeStorageAdapter()
    app.dependency_overrides[get_tryon_repository] = lambda: repo
    app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: _WardrobeStub()
    app.dependency_overrides[get_storage_adapter] = lambda: storage
    monkeypatch.setenv("FANSIVIBE_OPERATOR_API_KEY", "op-secret-key-p53c-test-1234567890")
    clear_settings_cache()
    yield {"repo": repo, "storage": storage}
    app.dependency_overrides.clear()
    tryon_app.reset_for_tests()
    clear_settings_cache()


def test_health_credits_records_balance_and_warns_when_low(p53c_env, monkeypatch, caplog):
    monkeypatch.setenv("FANSIVIBE_TRYON_PROVIDER", "genlook")
    monkeypatch.setenv("GENLOOK_API_KEY", "gk_test_secret_do_not_leak_999")
    clear_settings_cache()

    monkeypatch.setattr(
        genlook_tryon.GenlookTryOnProvider,
        "check_credits",
        lambda self: 5,
    )

    with caplog.at_level(logging.WARNING):
        resp = TestClient(app).get(
            "/v1/tryon/health/credits",
            headers={"X-Operator-Key": "op-secret-key-p53c-test-1234567890"},
        )

    assert resp.status_code == 200
    assert resp.json()["credit_balance"] == 5
    assert "event=tryon_low_provider_credits" in caplog.text
    assert "gk_test_secret_do_not_leak_999" not in caplog.text

    prom = TestClient(app).get("/metrics").text
    assert 'fansivibe_tryon_provider_credit_balance{provider="genlook"} 5.0' in prom


def test_health_credits_auth_error_records_metric_and_logs(p53c_env, monkeypatch, caplog):
    monkeypatch.setenv("FANSIVIBE_TRYON_PROVIDER", "genlook")
    monkeypatch.setenv("GENLOOK_API_KEY", "gk_test_secret_do_not_leak_888")
    clear_settings_cache()

    def _raise_auth(self):
        raise ProviderAuthError("invalid key", provider_id="genlook")

    monkeypatch.setattr(genlook_tryon.GenlookTryOnProvider, "check_credits", _raise_auth)

    before = get_metrics_collector().get_summary()["tryon_provider_outcomes"].get("genlook:auth_error", 0)
    with caplog.at_level(logging.ERROR):
        resp = TestClient(app).get(
            "/v1/tryon/health/credits",
            headers={"X-Operator-Key": "op-secret-key-p53c-test-1234567890"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "unavailable"
    assert resp.json()["error"] == "ProviderAuthError"
    assert "event=tryon_credits_auth_failed" in caplog.text
    assert "gk_test_secret_do_not_leak_888" not in caplog.text
    after = get_metrics_collector().get_summary()["tryon_provider_outcomes"].get("genlook:auth_error", 0)
    assert after == before + 1


def test_retention_cleanup_records_success_and_partial_failure_metrics(p53c_env, monkeypatch, caplog):
    repo = p53c_env["repo"]
    storage = p53c_env["storage"]
    client = TestClient(app)

    before_success = get_metrics_collector().get_summary()["tryon_retention_cleanup_runs"].get("success", 0)
    resp_ok = client.post(
        "/v1/tryon/maintenance/retention-cleanup",
        headers={"X-Operator-Key": "op-secret-key-p53c-test-1234567890"},
    )
    assert resp_ok.status_code == 200
    summary = get_metrics_collector().get_summary()
    assert summary["tryon_retention_cleanup_runs"].get("success", 0) == before_success + 1
    assert summary["tryon_retention_last_success_timestamp_seconds"] > 0

    # Create an expired failed job whose storage deletion fails
    uid = uuid4()
    jid = uuid4()
    old_ts = datetime.now(timezone.utc) - timedelta(hours=48)
    repo.create(
        job_id=jid,
        user_id=uid,
        outfit_source="wardrobe",
        garment_id=None,
        garment_ids=[],
        provider="mock",
        status="failed",
        consent_version="tryon-v1",
        consent_accepted_at=old_ts,
        person_media_ref={"key": f"users/{uid}/tryon/{jid}/person.jpg"},
    )
    repo._jobs[jid] = tryon_app.TryOnJobRecord(
        **{
            **repo._jobs[jid].__dict__,
            "created_at": old_ts,
            "updated_at": old_ts,
            "completed_at": old_ts,
        }
    )

    async def _fail_delete(key: str):
        raise RuntimeError("R2 delete outage")

    monkeypatch.setattr(storage, "delete_object", _fail_delete)
    before_partial = get_metrics_collector().get_summary()["tryon_retention_cleanup_runs"].get("partial_failure", 0)
    with caplog.at_level(logging.WARNING):
        resp_partial = client.post(
            "/v1/tryon/maintenance/retention-cleanup",
            headers={"X-Operator-Key": "op-secret-key-p53c-test-1234567890"},
        )

    assert resp_partial.status_code == 200
    assert resp_partial.json()["storage_errors"] >= 1
    assert "event=tryon_retention_cleanup_partial_failure" in caplog.text
    after_partial = get_metrics_collector().get_summary()["tryon_retention_cleanup_runs"].get("partial_failure", 0)
    assert after_partial == before_partial + 1


def test_result_image_download_storage_error_records_metric(p53c_env, monkeypatch, caplog):
    repo = p53c_env["repo"]
    storage = p53c_env["storage"]
    uid = uuid4()
    jid = uuid4()
    now = datetime.now(timezone.utc)

    repo.create(
        job_id=jid,
        user_id=uid,
        outfit_source="wardrobe",
        garment_id=None,
        garment_ids=[],
        provider="genlook",
        status="processing",
        consent_version="tryon-v1",
        consent_accepted_at=now,
    )
    repo.update_result(
        job_id=jid,
        result_media_ref={"key": f"users/{uid}/tryon/{jid}/result.png"},
        completed_at=now,
    )

    async def _fail_read(key: str, max_bytes: int = 0):
        raise RuntimeError("R2 read timeout")

    monkeypatch.setattr(storage, "read_object", _fail_read)
    from app.api.deps import get_current_user_id

    app.dependency_overrides[get_current_user_id] = lambda: uid
    before = get_metrics_collector().get_summary()["tryon_storage_errors"].get("result_download", 0)
    with caplog.at_level(logging.WARNING):
        resp = TestClient(app).get(f"/v1/tryon/jobs/{jid}/image")

    assert resp.status_code == 404
    assert "event=tryon_storage_error" in caplog.text
    after = get_metrics_collector().get_summary()["tryon_storage_errors"].get("result_download", 0)
    assert after == before + 1


def test_recovery_functions_record_metrics_and_logs(p53c_env, caplog):
    repo = p53c_env["repo"]
    uid = uuid4()
    j1 = uuid4()
    j2 = uuid4()
    old_ts = datetime.now(timezone.utc) - timedelta(minutes=15)

    repo.create(
        job_id=j1,
        user_id=uid,
        outfit_source="wardrobe",
        garment_id=None,
        garment_ids=[],
        provider="genlook",
        status="processing",
        consent_version="tryon-v1",
        consent_accepted_at=old_ts,
    )
    before_int = get_metrics_collector().get_summary()["tryon_interrupted_jobs_recovered_total"]
    with caplog.at_level(logging.WARNING):
        assert tryon_app.recover_interrupted_jobs(repo) == 1
    assert "event=tryon_interrupted_job_recovered" in caplog.text
    assert get_metrics_collector().get_summary()["tryon_interrupted_jobs_recovered_total"] == before_int + 1

    repo.create(
        job_id=j2,
        user_id=uid,
        outfit_source="wardrobe",
        garment_id=None,
        garment_ids=[],
        provider="genlook",
        status="processing",
        consent_version="tryon-v1",
        consent_accepted_at=old_ts,
    )
    repo._jobs[j2] = tryon_app.TryOnJobRecord(
        **{**repo._jobs[j2].__dict__, "created_at": old_ts, "updated_at": old_ts, "processing_started_at": old_ts}
    )
    before_stale = get_metrics_collector().get_summary()["tryon_stale_jobs_recovered_total"]
    assert tryon_app.recover_stale_jobs(job_repo=repo, stale_after_s=60) == 1
    assert get_metrics_collector().get_summary()["tryon_stale_jobs_recovered_total"] == before_stale + 1

    prom = TestClient(app).get("/metrics").text
    assert "fansivibe_tryon_interrupted_jobs_recovered_total" in prom
    assert "fansivibe_tryon_stale_jobs_recovered_total" in prom


def test_recover_stale_jobs_skips_active_in_process_execution(p53c_env):
    repo = p53c_env["repo"]
    uid = uuid4()
    jid = uuid4()
    old_ts = datetime.now(timezone.utc) - timedelta(minutes=15)

    repo.create(
        job_id=jid,
        user_id=uid,
        outfit_source="wardrobe",
        garment_id=None,
        garment_ids=[],
        provider="genlook",
        status="processing",
        consent_version="tryon-v1",
        consent_accepted_at=old_ts,
    )
    repo._jobs[jid] = tryon_app.TryOnJobRecord(
        **{**repo._jobs[jid].__dict__, "created_at": old_ts, "updated_at": old_ts, "processing_started_at": old_ts}
    )

    assert repo.claim_processing_lease(
        job_id=jid,
        worker_id="active-worker-1",
        lease_token=uuid4(),
        lease_seconds=120,
    )
    assert tryon_app.recover_stale_jobs(job_repo=repo, stale_after_s=60, worker_id="other-worker") == 0
    assert repo.get_by_id(user_id=uid, job_id=jid).status == "processing"


@pytest.mark.anyio
async def test_interrupted_genlook_job_resumes_existing_generation_without_double_billing(p53c_env, monkeypatch):
    repo = p53c_env["repo"]
    storage = p53c_env["storage"]
    uid = uuid4()
    jid = uuid4()
    gid = uuid4()
    now = datetime.now(timezone.utc)

    person_key = f"users/{uid}/tryon/{jid}/person.jpg"
    garment_key = f"users/{uid}/wardrobe/{gid}/garment.jpg"
    await storage.put_object(person_key, b"\xff\xd8\xff\xe0" + b"\x00" * 64, content_type="image/jpeg")
    await storage.put_object(garment_key, b"\xff\xd8\xff\xe0" + b"\x00" * 64, content_type="image/jpeg")

    class _GarmentRepoStub:
        def get_by_id(self, *, user_id, item_id):
            if user_id == uid and item_id == gid:
                return SimpleNamespace(
                    id=gid,
                    user_id=uid,
                    name="Test Shirt",
                    category="tops",
                    color="navy",
                    material="cotton",
                    fit="regular",
                    image_ref={"key": garment_key},
                )
            return None

    repo.create(
        job_id=jid,
        user_id=uid,
        outfit_source="wardrobe",
        garment_id=gid,
        garment_ids=[str(gid)],
        provider="genlook",
        status="processing",
        consent_version="tryon-v1",
        consent_accepted_at=now,
        person_media_ref={
            "key": person_key,
            "contentHash": "abc123",
            "genlook": {
                "imageId": "img_existing_1",
                "generationId": "gen_existing_1",
                "generationStatus": "PROCESSING",
                "attemptSeq": 0,
            },
        },
    )

    # Simulate process restart recovery
    assert tryon_app.recover_interrupted_jobs(repo) == 1
    failed = repo.get_by_id(user_id=uid, job_id=jid)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_code == "INTERRUPTED_BY_RESTART"
    assert failed.person_media_ref["genlook"]["generationId"] == "gen_existing_1"

    monkeypatch.setenv("FANSIVIBE_TRYON_PROVIDER", "genlook")
    monkeypatch.setenv("GENLOOK_API_KEY", "gk_test_resume_key_123")
    clear_settings_cache()

    calls: list[dict] = []

    def _fake_render(self, **kwargs):
        calls.append(kwargs)
        # 1x1 valid PNG
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
            b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    monkeypatch.setattr(genlook_tryon.GenlookTryOnProvider, "render", _fake_render)

    retried = tryon_app.retry_job(user_id=str(uid), job_id=str(jid), job_repo=repo)
    assert retried.status == "processing"
    assert retried.retry_count == 1

    await tryon_app.execute_tryon_inference(
        job_id=jid,
        user_id=uid,
        job_repo=repo,
        storage=storage,
        wardrobe_repo=_GarmentRepoStub(),
    )

    assert len(calls) == 1
    assert calls[0]["existing_generation_id"] == "gen_existing_1"
    completed = repo.get_by_id(user_id=uid, job_id=jid)
    assert completed is not None
    assert completed.status == "completed"
