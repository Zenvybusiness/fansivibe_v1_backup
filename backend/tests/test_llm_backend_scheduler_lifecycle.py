"""Regression tests for GPU scheduler lease lifecycle in AI Stylist LLM backend.

Verifies the complete inference lifecycle:
1. Acquire GPU lease (Priority 1, REASONING_VISION).
2. Submit Ollama inference request.
3. Receive HTTP response headers.
4. Read complete response body.
5. Complete parsing and handle inference result.
6. Mark workload completion at the correct point.

Critical Invariant:
Receiving HTTP 200 headers alone must NOT mark inference as completed.
The lease must remain active and uncompleted until the full response body has
been received. If the body is interrupted, workload termination remains
unconfirmed, triggering scheduler quarantine and lock retention.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.ai import llm_backend
from app.ai.manager.scheduler import GPUResourceScheduler
from app.ai.manager.types import GPUSchedulerLease, LeaseState, WorkloadType
from app.telemetry.metrics import get_metrics_collector


def _make_test_scheduler(tmp_path, **kwargs) -> GPUResourceScheduler:
    """Helper to create an isolated GPUResourceScheduler with tmp paths."""
    lockfile = str(tmp_path / "test_gpu_lifecycle.lock")
    metadata = str(tmp_path / "test_gpu_lifecycle_lease.json")
    quarantine = str(tmp_path / "test_gpu_lifecycle_quarantine.json")
    params = {
        "lockfile_path": lockfile,
        "metadata_path": metadata,
        "quarantine_path": quarantine,
        "poll_interval_s": 0.01,
        "grace_period_s": 0.05,
        "default_timeout_s": 2.0,
        "max_queue_depth": 5,
    }
    params.update(kwargs)
    return GPUResourceScheduler(**params)


def test_llm_backend_acquires_p1_lease_for_active_model(tmp_path, monkeypatch):
    """AI Stylist enrichment acquires a Priority 1 GPU lease for the active model."""
    scheduler = _make_test_scheduler(tmp_path)
    recorded_leases: list[GPUSchedulerLease] = []

    orig_acquire = scheduler._do_acquire_sync

    def spied_acquire(*args, **kwargs):
        lease = orig_acquire(*args, **kwargs)
        recorded_leases.append(lease)
        return lease

    scheduler._do_acquire_sync = spied_acquire

    monkeypatch.setattr("app.ai.manager.scheduler.get_gpu_scheduler", lambda: scheduler)

    mock_resp = {
        "model": "qwen3-vl:4b-instruct",
        "message": {"content": "This navy blazer pairs elegantly with your linen shirt."},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_resp)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = llm_backend.enrich_stylist_recommendation(
        user_query="What should I wear?",
        occasion="casual",
        selected_components=[{"name": "White Linen Shirt", "category": "tops", "color": "white"}],
        base_text="Base canonical recommendation.",
        client=client,
    )

    assert "navy blazer" in result
    assert len(recorded_leases) == 1
    lease = recorded_leases[0]
    assert lease.priority == 1
    assert lease.workload_type == WorkloadType.REASONING_VISION
    assert lease.model_id == llm_backend.get_active_model()
    assert lease.state == LeaseState.RELEASED
    assert lease._workload_completed is True
    assert scheduler.is_quarantined() is False


def test_receiving_http_200_headers_alone_does_not_mark_complete_when_body_interrupted(
    tmp_path, monkeypatch
):
    """Critical requirement: HTTP 200 headers alone must NOT mark workload completed.

    When the response body is interrupted during transmission, the lease must
    NOT be marked complete. Because workload termination is unconfirmed, the
    scheduler must transition to QUARANTINED, and the engine must fall back
    safely to base_text.
    """
    scheduler = _make_test_scheduler(tmp_path)
    recorded_leases: list[GPUSchedulerLease] = []

    orig_acquire = scheduler._do_acquire_sync

    def spied_acquire(*args, **kwargs):
        lease = orig_acquire(*args, **kwargs)
        recorded_leases.append(lease)
        return lease

    scheduler._do_acquire_sync = spied_acquire
    monkeypatch.setattr("app.ai.manager.scheduler.get_gpu_scheduler", lambda: scheduler)

    class FailingBodyStream(httpx.SyncByteStream):
        """Simulates receiving HTTP 200 OK headers followed by a dropped connection during body streaming."""
        def __iter__(self):
            # Headers have already succeeded (HTTP 200); body streaming fails:
            raise httpx.RemoteProtocolError("Connection dropped mid-stream while receiving body")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=FailingBodyStream())

    client = httpx.Client(transport=httpx.MockTransport(handler))

    base_text = "Base canonical recommendation for casual outfit."
    result = llm_backend.enrich_stylist_recommendation(
        user_query="What should I wear?",
        occasion="casual",
        selected_components=[{"name": "White Linen Shirt", "category": "tops"}],
        base_text=base_text,
        client=client,
    )

    # Engine safely falls back to base text
    assert result == base_text

    # Verify that the lease was NEVER marked completed
    assert len(recorded_leases) == 1
    lease = recorded_leases[0]
    assert lease._workload_completed is False

    # Scheduler must be quarantined because workload termination was unconfirmed
    assert scheduler.is_quarantined() is True
    assert lease.state == LeaseState.QUARANTINED


def test_lease_marked_complete_only_after_complete_body_received(tmp_path, monkeypatch):
    """Workload completion is marked upon confirmed receipt of the full body."""
    scheduler = _make_test_scheduler(tmp_path)
    observed_state: dict[str, Any] = {}

    orig_release = scheduler._do_release_sync

    def spied_release(lease, *args, **kwargs):
        observed_state["workload_completed_before_release"] = lease._workload_completed
        return orig_release(lease, *args, **kwargs)

    scheduler._do_release_sync = spied_release
    monkeypatch.setattr("app.ai.manager.scheduler.get_gpu_scheduler", lambda: scheduler)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"model": "m", "message": {"content": "Styling rationale output."}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = llm_backend.enrich_reply(
        intent="outfit",
        base_text="Base text",
        context="User profile context",
        client=client,
    )

    assert result == "Styling rationale output."
    assert observed_state.get("workload_completed_before_release") is True
    assert scheduler.is_quarantined() is False


def test_malformed_json_after_full_body_received_does_not_quarantine(tmp_path, monkeypatch):
    """Non-JSON response text received completely marks workload completed and does NOT quarantine."""
    scheduler = _make_test_scheduler(tmp_path)
    monkeypatch.setattr("app.ai.manager.scheduler.get_gpu_scheduler", lambda: scheduler)

    def handler(request: httpx.Request) -> httpx.Response:
        # 200 OK with non-JSON body: body is fully received, but json.loads fails
        return httpx.Response(200, text="Not a valid json response from model")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    base_text = "Base fallback recommendation."
    result = llm_backend.enrich_stylist_recommendation(
        user_query="What should I wear?",
        occasion="office",
        selected_components=[],
        base_text=base_text,
        client=client,
    )

    assert result == base_text
    # Quarantine must NOT be triggered because the full HTTP 200 body was received
    assert scheduler.is_quarantined() is False


def test_connection_error_before_submission_does_not_quarantine(tmp_path, monkeypatch):
    """Connection failure before request submission confirms cessation and does not quarantine."""
    scheduler = _make_test_scheduler(tmp_path)
    monkeypatch.setattr("app.ai.manager.scheduler.get_gpu_scheduler", lambda: scheduler)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Ollama port 11434 unreachable")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    base_text = "Base fallback."
    result = llm_backend.enrich_stylist_recommendation(
        user_query="Suggest an outfit",
        occasion="wedding",
        selected_components=[],
        base_text=base_text,
        client=client,
    )

    assert result == base_text
    assert scheduler.is_quarantined() is False


def test_fallback_provenance_is_private_and_recorded(monkeypatch):
    monkeypatch.setattr(
        llm_backend,
        "_acquire_gpu_lease_context",
        lambda model: nullcontext(None),
    )
    collector = get_metrics_collector()
    before = collector.get_summary().get("llm_enrichments", {})

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret prompt must never be logged")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    state = llm_backend.LlmProvenanceState()
    base_text = "Base fallback."

    result = llm_backend.enrich_reply(
        intent="outfit",
        base_text=base_text,
        context="private user context",
        client=client,
        provenance_out=state,
    )

    assert result == base_text
    assert state.status == "fallback"
    assert state.reason == "provider_unreachable"
    assert state.error_type == "ConnectError"
    assert state.duration_ms is not None
    assert state.to_dict()["errorType"] == "ConnectError"
    assert state.to_dict()["durationMs"] == state.duration_ms

    key = ":".join(
        [
            state.provider,
            state.model or "unknown",
            "fallback",
            "provider_unreachable",
            "ConnectError",
        ]
    )
    after = collector.get_summary().get("llm_enrichments", {})
    assert after.get(key, 0) == before.get(key, 0) + 1

    prom = collector.format_prometheus()
    assert 'reason="provider_unreachable"' in prom
    assert "secret prompt must never be logged" not in prom

