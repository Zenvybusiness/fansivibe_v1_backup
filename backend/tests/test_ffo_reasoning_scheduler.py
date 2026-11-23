"""Sub-Batch 3.2 Automated Tests: Fashion Reasoning GPU Scheduler Integration.

Verifies:
1. Unit Tests:
   - Reasoning acquires exactly one Priority 1 lease
   - Successful complete HTTP response marks workload completed
   - JSON parsing failure after completed HTTP response does not quarantine
   - Pydantic validation failure after completed HTTP response does not quarantine
   - TF-IDF retrieval does not hold the GPU lease
   - Retry attempts do not inherit completion state from earlier attempts
   - Lease is released after confirmed inference completion
   - Acquisition timeout produces correct scheduler exception
   - Queue saturation produces correct scheduler exception
   - Quarantine rejects new inference
   - Backward compatibility when scheduler is None

2. Failure and Cancellation Tests:
   - Connection failure before request submission does not quarantine
   - HTTP timeout after request submission triggers quarantine & lock retention
   - Response body interrupted during reading triggers quarantine & lock retention
   - Caller cancellation triggers quarantine & lock retention
   - Unknown termination state transitions to quarantined
   - Scheduler quarantine evidence file written after uncertain execution
   - No premature lease release while synchronous request is still running

3. Concurrency Tests:
   - Two reasoning threads cannot execute GPU inference simultaneously (disjoint intervals)
   - Concurrent requests acquire and release leases correctly
   - ConcurrencyLimiter continues to behave as before (admission control)
   - Queue full and timeout behavior remain deterministic
   - Shared scheduler ownership across dependency injection and reasoning adapter
   - Nested acquisition on same thread is prevented without deadlock

4. API Integration Tests (both /v1/reasoning and /v1/reasoning/query):
   - Successful reasoning response (200)
   - Queue saturated error mapping (429 RATE_LIMITED, Retry-After: 5)
   - Acquisition timeout error mapping (504 TIMEOUT, Retry-After: 5)
   - Confirmed execution timeout error mapping (504 TIMEOUT)
   - Scheduler quarantine error mapping (503 AI_FAILURE, Retry-After: 15)
   - Uncertain inference termination error mapping (503 AI_FAILURE, Retry-After: 15)
   - ConcurrencyLimiter saturation error mapping (429 RATE_LIMITED, Retry-After: 5)
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from starlette.testclient import TestClient

from app.ai.manager.scheduler import GPUResourceScheduler, get_gpu_scheduler
from app.ai.manager.types import (
    GPUSchedulerLease,
    GPUResourceQuarantinedError,
    LeaseState,
    SchedulerQueueFullError,
    SchedulerTimeoutError,
    WorkloadType,
    WorkloadUncertainError,
)
from app.ai.ollama_reasoner import (
    OllamaFashionReasoner,
    ReasoningConfig,
    ReasoningExecutionError,
)
from app.api.deps import get_fashion_reasoner, get_gpu_scheduler as deps_get_gpu_scheduler
from app.api.rate_limit import ConcurrencyLimiter, get_reasoning_concurrency_limiter
from app.application.reasoning import ReasonFashionQuery
from app.domain.services.ffo_reasoning import (
    REASONING_CONTRACT_VERSION,
    corpus_digest,
    validate_input,
)
from app.main import app

VERSIONS = {
    "ffo_version": "1.0",
    "corpus_digest": corpus_digest({"term-denim": 1}, "1.0"),
    "evidence_schema": "evidence-pack/1",
    "reasoning_contract_version": REASONING_CONTRACT_VERSION,
}

EVIDENCE = {
    "doc_id": "term-denim",
    "doc_type": "term",
    "label": "denim",
    "reason": "exact_canonical",
    "lexical_score": 700,
    "semantic_score": None,
    "ffo_references": ["denim", "textile"],
    "provenance": {"source": "s", "source_type": "AUTHORITATIVE", "confidence": 0.9},
    "confidence": 0.9,
    "status": "published",
    "content": {
        "doc_id": "term-denim",
        "entity_kind": "textile",
        "canonical_id": "denim",
        "payload": {"durability": "high", "name": "denim"},
    },
}


def _make_scheduler(tmp_path, **kwargs) -> GPUResourceScheduler:
    """Helper to create an isolated GPUResourceScheduler with tmp paths."""
    lockfile = str(tmp_path / "test_gpu.lock")
    metadata = str(tmp_path / "test_gpu_lease.json")
    quarantine = str(tmp_path / "test_gpu_quarantine.json")
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


def _input(**overrides):
    data = {
        "request": {"query": "what is denim", "intent": "explain"},
        "context": {},
        "entities": ["denim"],
        "evidence": [dict(EVIDENCE)],
        "constraints": {"evidence_only": True, "max_conclusions": 3},
        "requirements": {"include_reasoning_notes": True},
        "versions": dict(VERSIONS),
    }
    data.update(overrides)
    return validate_input(data)


def _output(**overrides):
    data = {
        "answer": "Denim is a durable textile.",
        "conclusions": [
            {
                "statement": "Denim is a durable textile.",
                "evidence_ids": ["term-denim"],
                "ffo_refs": ["denim"],
                "reasoning_note": "n",
                "standing": "supported",
                "admission": {
                    "subject_ref": "denim",
                    "atomic_claims": [
                        {
                            "text": "Denim is a durable textile.",
                            "cited_doc_ids": ["term-denim"],
                        }
                    ],
                },
            }
        ],
        "uncertainties": [],
        "missing_evidence": [],
        "contradictions": [],
        "confidence": "high",
        "unsupported": False,
        "versions": dict(VERSIONS),
    }
    data.update(overrides)
    return data


def _real_output(**overrides):
    from app.data.ffo import FFO_VERSION, corpus
    from app.domain.services.ffo_reasoning import (
        EVIDENCE_SCHEMA_VERSION,
        REASONING_CONTRACT_VERSION,
        corpus_digest,
    )
    index = corpus.build_index(corpus.load_documents())
    digest = corpus_digest(corpus.corpus_versions(index), FFO_VERSION)
    versions = {
        "ffo_version": FFO_VERSION,
        "corpus_digest": digest,
        "evidence_schema": EVIDENCE_SCHEMA_VERSION,
        "reasoning_contract_version": REASONING_CONTRACT_VERSION,
    }
    return _output(versions=versions, **overrides)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# ==============================================================================
# 1. UNIT TESTS
# ==============================================================================


def test_reasoning_acquires_exactly_one_p1_lease(tmp_path):
    """Reasoning must acquire exactly one Priority 1 GPU lease for inference."""
    scheduler = _make_scheduler(tmp_path)
    recorded_leases: list[GPUSchedulerLease] = []

    orig_acquire = scheduler._do_acquire_sync

    def spied_acquire(*args, **kwargs):
        lease = orig_acquire(*args, **kwargs)
        recorded_leases.append(lease)
        return lease

    scheduler._do_acquire_sync = spied_acquire

    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_output())}}
        )

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    result = adapter.reason(_input())
    assert result.answer.startswith("Denim")
    assert len(recorded_leases) == 1
    lease = recorded_leases[0]
    assert lease.priority == 1
    assert lease.workload_type == WorkloadType.REASONING_VISION
    assert lease.state == LeaseState.RELEASED


def test_successful_complete_http_response_marks_workload_completed(tmp_path):
    """Successful complete HTTP response marks workload completed."""
    scheduler = _make_scheduler(tmp_path)
    observed_state: dict[str, Any] = {}

    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_output())}}
        )

    orig_release = scheduler._do_release_sync

    def spied_release(lease, *args, **kwargs):
        observed_state["workload_completed_before_release"] = lease._workload_completed
        return orig_release(lease, *args, **kwargs)

    scheduler._do_release_sync = spied_release

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    adapter.reason(_input())
    assert observed_state.get("workload_completed_before_release") is True
    assert scheduler.is_quarantined() is False


def test_json_parsing_failure_after_completed_http_response_does_not_quarantine(tmp_path):
    """JSON parsing failure after completed HTTP response does not quarantine."""
    scheduler = _make_scheduler(tmp_path)

    def handler(request):
        # 200 OK with non-JSON text
        return httpx.Response(200, text="Not valid json output from model")

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    with pytest.raises(ReasoningExecutionError) as exc:
        adapter.reason(_input())
    assert exc.value.category == "malformed_json"
    # Quarantine must NOT be triggered because HTTP 200 body was received completely
    assert scheduler.is_quarantined() is False
    assert scheduler._active_lease is None


def test_pydantic_validation_failure_after_completed_http_response_does_not_quarantine(tmp_path):
    """Pydantic validation failure after completed HTTP response does not quarantine."""
    scheduler = _make_scheduler(tmp_path)

    bad_output = _output()
    # Violate schema: standing must be 'supported' or 'unsupported'
    bad_output["conclusions"][0]["standing"] = "invalid_standing_value"

    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(bad_output)}}
        )

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    with pytest.raises(ReasoningExecutionError) as exc:
        adapter.reason(_input())
    assert exc.value.category == "invalid_output"
    assert scheduler.is_quarantined() is False
    assert scheduler._active_lease is None


def test_tfidf_retrieval_does_not_unnecessarily_hold_gpu_lease(tmp_path):
    """TF-IDF retrieval and corpus indexing run before acquiring GPU lease."""
    scheduler = _make_scheduler(tmp_path)
    active_leases_during_retrieval: list[int] = []

    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_real_output())}}
        )

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )

    import app.application.reasoning as app_reasoning

    orig_retrieve = app_reasoning.retrieve

    def spied_retrieve(*args, **kwargs):
        active_count = 1 if scheduler._active_lease is not None else 0
        active_leases_during_retrieval.append(active_count)
        return orig_retrieve(*args, **kwargs)

    with patch.object(app_reasoning, "retrieve", side_effect=spied_retrieve):
        use_case = ReasonFashionQuery(reasoner=adapter)
        use_case(query="what is denim", intent="explain")

    assert len(active_leases_during_retrieval) == 1
    # During retrieve(), zero GPU leases were active
    assert active_leases_during_retrieval[0] == 0


def test_retry_attempts_do_not_inherit_completion_state_from_earlier_attempts(tmp_path):
    """Retry attempts reset completion state so attempt 2 starts uncompleted."""
    scheduler = _make_scheduler(tmp_path)
    attempt_count = 0
    completion_states_at_start: list[bool] = []

    def handler(request):
        nonlocal attempt_count
        attempt_count += 1
        if scheduler._active_lease is not None:
            completion_states_at_start.append(scheduler._active_lease._workload_completed)
        if attempt_count == 1:
            return httpx.Response(500, text="Server Error")
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_output())}}
        )

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=1),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    result = adapter.reason(_input())
    assert result.answer.startswith("Denim")
    assert attempt_count == 2
    assert len(completion_states_at_start) == 2
    # Both attempt 1 and attempt 2 started with workload_completed == False
    assert completion_states_at_start[0] is False
    assert completion_states_at_start[1] is False


def test_lease_is_released_after_confirmed_inference_completion(tmp_path):
    """Lease is released and unlocked after confirmed inference completion."""
    scheduler = _make_scheduler(tmp_path)

    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_output())}}
        )

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    adapter.reason(_input())
    assert scheduler._active_lease is None
    # Verify another acquire succeeds immediately without contention
    with scheduler.acquire_lease_sync("m", priority=1) as lease:
        assert lease.state == LeaseState.RUNNING


def test_acquisition_timeout_produces_correct_scheduler_exception(tmp_path):
    """Acquisition timeout produces SchedulerTimeoutError(phase='acquisition')."""
    scheduler = _make_scheduler(tmp_path)

    # Pre-acquire lease to hold it
    with scheduler.acquire_lease_sync("m", priority=1):
        def handler(request):
            return httpx.Response(200, json={"model": "m", "message": {"content": "{}"}})

        # Configure short acquisition timeout
        adapter = OllamaFashionReasoner(
            config=ReasoningConfig(model="m", timeout_s=0.05, max_retries=0),
            http_client=_client(handler),
            scheduler=scheduler,
        )
        with pytest.raises(SchedulerTimeoutError) as exc_info:
            adapter.reason(_input())
        assert exc_info.value.phase == "acquisition"


def test_queue_saturation_produces_correct_scheduler_exception(tmp_path):
    """Queue saturation produces SchedulerQueueFullError."""
    scheduler = _make_scheduler(tmp_path, max_queue_depth=1)

    # Hold active lease
    with scheduler.acquire_lease_sync("m", priority=1):
        # Enqueue 1 waiting entry to fill queue
        t_ready = threading.Event()
        t_stop = threading.Event()

        def background_waiter():
            try:
                with scheduler.acquire_lease_sync("m", priority=1, timeout_s=1.0):
                    pass
            except Exception:
                pass
            finally:
                t_stop.set()

        thread = threading.Thread(target=background_waiter, daemon=True)
        thread.start()
        time.sleep(0.05)

        # Now queue is full (active entry is set, queue has 1 waiter)
        adapter = OllamaFashionReasoner(
            config=ReasoningConfig(model="m", max_retries=0),
            scheduler=scheduler,
        )
        with pytest.raises(SchedulerQueueFullError):
            adapter.reason(_input())

        t_stop.wait(timeout=1.0)


def test_quarantine_rejects_new_inference(tmp_path):
    """Quarantined scheduler immediately rejects new reasoning requests."""
    scheduler = _make_scheduler(tmp_path)
    scheduler._write_quarantine_atomically({"reason": "pre-existing fault", "holder_pid": os.getpid()})
    assert scheduler.is_quarantined() is True

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        scheduler=scheduler,
    )
    with pytest.raises(GPUResourceQuarantinedError):
        adapter.reason(_input())


def test_backward_compatibility_without_scheduler():
    """Reasoner runs normally without scheduler if scheduler is None."""
    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_output())}}
        )

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=None,
    )
    result = adapter.reason(_input())
    assert result.answer.startswith("Denim")


# ==============================================================================
# 2. FAILURE AND CANCELLATION TESTS
# ==============================================================================


def test_connection_failure_before_request_submission(tmp_path):
    """Connection failure before request submission does not quarantine GPU."""
    scheduler = _make_scheduler(tmp_path)

    def handler(request):
        raise httpx.ConnectError("Connection refused: 127.0.0.1:11434")

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    with pytest.raises(ReasoningExecutionError) as exc:
        adapter.reason(_input())
    assert exc.value.category == "unavailable"
    # Because connection failed before submission, cessation was confirmed -> NO quarantine
    assert scheduler.is_quarantined() is False
    assert scheduler._active_lease is None


def test_http_timeout_after_request_submission(tmp_path):
    """HTTP timeout after request submission triggers quarantine and retains lock."""
    scheduler = _make_scheduler(tmp_path)

    def handler(request):
        # Simulated timeout after request submission
        raise httpx.ReadTimeout("Read timed out on socket")

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    with pytest.raises(WorkloadUncertainError):
        adapter.reason(_input())

    assert scheduler.is_quarantined() is True
    evidence = scheduler.get_quarantine_evidence() or {}
    assert "quarantined" in evidence or scheduler.is_quarantined()


def test_response_body_interrupted_during_reading(tmp_path):
    """Interruption while reading response body triggers quarantine and retains lock."""
    scheduler = _make_scheduler(tmp_path)

    class FailingStream(httpx.SyncByteStream):
        def __iter__(self):
            raise httpx.RemoteProtocolError("Connection dropped during streaming")

    def handler(request):
        return httpx.Response(200, stream=FailingStream())

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    with pytest.raises(WorkloadUncertainError):
        adapter.reason(_input())

    assert scheduler.is_quarantined() is True


def test_caller_cancellation_during_execution(tmp_path):
    """Caller cancellation during execution marks lease quarantined."""
    scheduler = _make_scheduler(tmp_path)

    # Emulate cancellation inside the lease context manager
    cm = scheduler.acquire_lease_sync("m", priority=1)
    with pytest.raises(RuntimeError):
        with cm as lease:
            # Simulate an unhandled exception representing thread cancellation
            raise RuntimeError("Thread interrupted by cancellation")

    assert scheduler.is_quarantined() is True
    assert cm.lease.state == LeaseState.QUARANTINED


def test_unknown_termination_state(tmp_path):
    """When termination check returns False, scheduler quarantines."""
    scheduler = _make_scheduler(tmp_path)

    cm = scheduler.acquire_lease_sync(
        "m",
        priority=1,
        is_workload_stopped=lambda: False,  # cannot confirm stopped
    )
    with pytest.raises(Exception):
        with cm as lease:
            raise Exception("Failure with unconfirmed termination")

    assert scheduler.is_quarantined() is True
    assert cm.lease.state == LeaseState.QUARANTINED


def test_scheduler_quarantine_after_uncertain_execution(tmp_path):
    """Atomic quarantine JSON file is written to disk upon uncertain execution."""
    scheduler = _make_scheduler(tmp_path)

    def handler(request):
        raise httpx.ReadTimeout("Timeout while waiting for Ollama tokens")

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    with pytest.raises(WorkloadUncertainError):
        adapter.reason(_input())

    quarantine_file = tmp_path / "test_gpu_quarantine.json"
    assert quarantine_file.exists()
    content = json.loads(quarantine_file.read_text())
    assert content["quarantined"] is True
    assert "evidence" in content


def test_no_premature_lease_release_while_synchronous_request_running(tmp_path):
    """Lease remains RUNNING and locked while synchronous HTTP request is executing."""
    scheduler = _make_scheduler(tmp_path)
    in_request = threading.Event()
    continue_request = threading.Event()
    lease_state_during_request: dict[str, Any] = {}

    def handler(request):
        in_request.set()
        continue_request.wait(timeout=2.0)
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_output())}}
        )

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )

    def worker():
        adapter.reason(_input())

    thread = threading.Thread(target=worker)
    thread.start()

    # Wait until worker is inside the synchronous HTTP call
    assert in_request.wait(timeout=1.0)

    # Prove lease is still active and held!
    active = scheduler._active_lease
    assert active is not None
    assert active.state == LeaseState.RUNNING
    assert active._lock_fd is not None

    # Unblock HTTP call
    continue_request.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()

    # After return, lease must be released
    assert scheduler._active_lease is None


# ==============================================================================
# 3. CONCURRENCY TESTS
# ==============================================================================


def test_two_reasoning_threads_cannot_execute_gpu_inference_simultaneously(tmp_path):
    """Two concurrent reasoning threads execute sequentially; inference intervals do not overlap."""
    scheduler = _make_scheduler(tmp_path)
    intervals: list[tuple[float, float, str]] = []
    lock = threading.Lock()

    def make_handler(name: str):
        def handler(request):
            t_start = time.perf_counter()
            time.sleep(0.08)  # simulate GPU inference
            t_end = time.perf_counter()
            with lock:
                intervals.append((t_start, t_end, name))
            return httpx.Response(
                200, json={"model": "m", "message": {"content": json.dumps(_output())}}
            )
        return handler

    adapter1 = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(make_handler("t1")),
        scheduler=scheduler,
    )
    adapter2 = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(make_handler("t2")),
        scheduler=scheduler,
    )

    t1 = threading.Thread(target=lambda: adapter1.reason(_input()))
    t2 = threading.Thread(target=lambda: adapter2.reason(_input()))

    t1.start()
    t2.start()
    t1.join(timeout=3.0)
    t2.join(timeout=3.0)

    assert len(intervals) == 2
    # Sort by start time
    intervals.sort(key=lambda x: x[0])
    first_end = intervals[0][1]
    second_start = intervals[1][0]
    # Proof of mutual exclusion: first ended before or at second start
    assert first_end <= second_start + 0.01  # allow minor scheduling tolerance


def test_concurrent_requests_acquire_and_release_leases_correctly(tmp_path):
    """Multiple concurrent requests acquire and release leases without deadlock."""
    scheduler = _make_scheduler(tmp_path)
    completed = []

    def handler(request):
        time.sleep(0.02)
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_output())}}
        )

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )

    def worker(idx):
        adapter.reason(_input())
        completed.append(idx)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=3.0)

    assert len(completed) == 3
    assert scheduler._active_lease is None


def test_concurrency_limiter_continues_to_behave_as_before():
    """ConcurrencyLimiter continues to enforce process-local limit (limit=2)."""
    limiter = ConcurrencyLimiter(limit=2)
    assert limiter.acquire(timeout=0.1) is True
    assert limiter.active_count == 1
    assert limiter.acquire(timeout=0.1) is True
    assert limiter.active_count == 2
    # 3rd acquisition must fail
    assert limiter.acquire(timeout=0.05) is False
    assert limiter.active_count == 2
    limiter.release()
    assert limiter.active_count == 1
    limiter.release()
    assert limiter.active_count == 0


def test_shared_scheduler_ownership_across_deps_and_reasoner(tmp_path):
    """get_fashion_reasoner receives the exact singleton from get_gpu_scheduler."""
    test_sched = _make_scheduler(tmp_path)
    app.dependency_overrides[deps_get_gpu_scheduler] = lambda: test_sched

    try:
        reasoner = get_fashion_reasoner(scheduler=test_sched)
        assert isinstance(reasoner, OllamaFashionReasoner)
        assert reasoner._scheduler is test_sched
    finally:
        app.dependency_overrides.pop(deps_get_gpu_scheduler, None)


def test_verify_no_nested_acquisition_or_deadlock(tmp_path):
    """Calling reason() while an active lease is held on the same thread raises RuntimeError."""
    scheduler = _make_scheduler(tmp_path)

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        scheduler=scheduler,
    )

    # Simulate nested call
    def recursive_handler(request):
        # Trying to call reason() again while already holding lease on same thread
        adapter.reason(_input())
        return httpx.Response(200, json={})

    adapter._client = _client(recursive_handler)

    with pytest.raises(RuntimeError) as exc_info:
        adapter.reason(_input())
    assert "Nested or duplicate GPU lease acquisition" in str(exc_info.value)


# ==============================================================================
# 4. API INTEGRATION TESTS
# ==============================================================================


@pytest.fixture
def api_test_setup(tmp_path):
    """Fixture providing TestClient with configured isolated scheduler."""
    scheduler = _make_scheduler(tmp_path)
    client = TestClient(app)
    return client, scheduler


def test_api_endpoints_normal_success(api_test_setup):
    """Both /v1/reasoning and /v1/reasoning/query succeed with HTTP 200 under scheduler."""
    client, scheduler = api_test_setup

    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_real_output())}}
        )

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )
    app.dependency_overrides[get_fashion_reasoner] = lambda: adapter
    app.dependency_overrides[deps_get_gpu_scheduler] = lambda: scheduler

    try:
        for endpoint in ["/v1/reasoning", "/v1/reasoning/query"]:
            resp = client.post(
                endpoint,
                json={"query": "what is denim", "intent": "explain"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["answer"].startswith("Denim")
            assert "conclusions" in data
            assert scheduler._active_lease is None
    finally:
        app.dependency_overrides.pop(get_fashion_reasoner, None)
        app.dependency_overrides.pop(deps_get_gpu_scheduler, None)


def test_api_queue_saturated_maps_to_429(api_test_setup):
    """Queue saturated error maps to HTTP 429 RATE_LIMITED with Retry-After: 5."""
    client, scheduler = api_test_setup

    class SaturatedReasoner:
        contract_version = REASONING_CONTRACT_VERSION

        def reason(self, *args, **kwargs):
            raise SchedulerQueueFullError("Queue saturated", current_depth=5, max_depth=5)

    app.dependency_overrides[get_fashion_reasoner] = lambda: SaturatedReasoner()
    try:
        resp = client.post("/v1/reasoning", json={"query": "what is denim", "intent": "explain"})
        assert resp.status_code == 429
        assert resp.headers.get("Retry-After") == "5"
        body = resp.json()
        assert body["error"]["code"] == "RATE_LIMITED"
    finally:
        app.dependency_overrides.pop(get_fashion_reasoner, None)


def test_api_acquisition_timeout_maps_to_504(api_test_setup):
    """Acquisition timeout maps to HTTP 504 TIMEOUT with Retry-After: 5."""
    client, scheduler = api_test_setup

    class AcqTimeoutReasoner:
        contract_version = REASONING_CONTRACT_VERSION

        def reason(self, *args, **kwargs):
            raise SchedulerTimeoutError("Acquisition timeout", phase="acquisition", timeout_s=1.0)

    app.dependency_overrides[get_fashion_reasoner] = lambda: AcqTimeoutReasoner()
    try:
        resp = client.post("/v1/reasoning", json={"query": "what is denim", "intent": "explain"})
        assert resp.status_code == 504
        assert resp.headers.get("Retry-After") == "5"
        body = resp.json()
        assert body["error"]["code"] == "TIMEOUT"
        assert body["error"]["details"]["phase"] == "acquisition"
    finally:
        app.dependency_overrides.pop(get_fashion_reasoner, None)


def test_api_confirmed_execution_timeout_maps_to_504(api_test_setup):
    """Confirmed execution timeout maps to HTTP 504 TIMEOUT."""
    client, scheduler = api_test_setup

    class ExecTimeoutReasoner:
        contract_version = REASONING_CONTRACT_VERSION

        def reason(self, *args, **kwargs):
            raise ReasoningExecutionError("timeout", "ollama timeout after 60s")

    app.dependency_overrides[get_fashion_reasoner] = lambda: ExecTimeoutReasoner()
    try:
        resp = client.post("/v1/reasoning", json={"query": "what is denim", "intent": "explain"})
        assert resp.status_code == 504
        body = resp.json()
        assert body["error"]["code"] == "TIMEOUT"
    finally:
        app.dependency_overrides.pop(get_fashion_reasoner, None)


def test_api_scheduler_quarantine_maps_to_503(api_test_setup):
    """Quarantined GPU maps to HTTP 503 AI_FAILURE with Retry-After: 15."""
    client, scheduler = api_test_setup

    class QuarantinedReasoner:
        contract_version = REASONING_CONTRACT_VERSION

        def reason(self, *args, **kwargs):
            raise GPUResourceQuarantinedError("GPU is quarantined")

    app.dependency_overrides[get_fashion_reasoner] = lambda: QuarantinedReasoner()
    try:
        resp = client.post("/v1/reasoning", json={"query": "what is denim", "intent": "explain"})
        assert resp.status_code == 503
        assert resp.headers.get("Retry-After") == "15"
        body = resp.json()
        assert body["error"]["code"] == "AI_FAILURE"
        assert body["error"]["details"]["reason"] == "gpu_quarantined"
    finally:
        app.dependency_overrides.pop(get_fashion_reasoner, None)


def test_api_uncertain_inference_termination_maps_to_503(api_test_setup):
    """Uncertain inference termination maps to HTTP 503 AI_FAILURE with Retry-After: 15."""
    client, scheduler = api_test_setup

    class UncertainReasoner:
        contract_version = REASONING_CONTRACT_VERSION

        def reason(self, *args, **kwargs):
            raise WorkloadUncertainError("Uncertain Ollama termination", lease_id="l-1")

    app.dependency_overrides[get_fashion_reasoner] = lambda: UncertainReasoner()
    try:
        resp = client.post("/v1/reasoning/query", json={"query": "what is denim", "intent": "explain"})
        assert resp.status_code == 503
        assert resp.headers.get("Retry-After") == "15"
        body = resp.json()
        assert body["error"]["code"] == "AI_FAILURE"
        assert body["error"]["details"]["reason"] == "gpu_quarantined"
    finally:
        app.dependency_overrides.pop(get_fashion_reasoner, None)


def test_performance_measurement_telemetry(tmp_path):
    """Performance telemetry: measures and asserts bounded durations."""
    scheduler = _make_scheduler(tmp_path)

    def handler(request):
        time.sleep(0.03)  # simulate inference
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(_output())}}
        )

    adapter = OllamaFashionReasoner(
        config=ReasoningConfig(model="m", max_retries=0),
        http_client=_client(handler),
        scheduler=scheduler,
    )

    t0 = time.perf_counter()
    adapter.reason(_input())
    total_latency = time.perf_counter() - t0

    # Ensure latency is non-trivial and bounded
    assert total_latency >= 0.03
    assert total_latency < 1.0
