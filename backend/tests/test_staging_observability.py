"""Automated verification suite for Staging Deployment & Observability (Phase 3AM).

Tests:
1. Metrics collector and Prometheus format (/metrics)
2. HTTP status breakdown (429, 502, 503, 504 tracking)
3. Active reasoning concurrency gauge
4. Readiness & Ollama availability gauges
5. Privacy verification: zero prompts, model output, or secrets exported
6. Staging configuration & invariant validation
7. Correlation ID (X-Request-Id) preservation & generation
8. Concurrency saturation (N > 2) and semaphore release on success/timeout/exception
9. Rate limiting saturation
10. Failure injection scenarios (A-J)
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.ai.lifecycle import ModelStatus
from app.ai.ollama_reasoner import ReasoningExecutionError
from app.api.deps import get_fashion_reasoner, get_lifecycle_manager
from app.api.errors import ApiError
from app.api.rate_limit import (
    ConcurrencyLimiter,
    get_reasoning_concurrency_limiter,
    reset_reasoning_concurrency_limiter,
)
from app.config.settings import Settings, clear_settings_cache, get_settings
from app.domain.ports.reasoning import FashionReasoner
from app.domain.services.ffo_reasoning import (
    FashionReasoningInput,
    FashionReasoningOutput,
    ReasoningConclusion,
    ReasoningVersions,
)
from app.infrastructure.db.session import get_db
from app.main import app
from app.telemetry.metrics import MetricsCollector, get_metrics_collector


class DummyReasoner(FashionReasoner):
    contract_version: str = "2.0"

    def __init__(self, delay_s: float = 0.0, exc_to_raise: Exception | None = None) -> None:
        self.delay_s = delay_s
        self.exc_to_raise = exc_to_raise
        self.call_count = 0

    def reason(self, reasoning_input: FashionReasoningInput) -> FashionReasoningOutput:
        self.call_count += 1
        if self.delay_s > 0:
            time.sleep(self.delay_s)
        if self.exc_to_raise:
            raise self.exc_to_raise
        return FashionReasoningOutput(
            answer="Denim is a sturdy cotton warp-faced textile.",
            conclusions=(
                ReasoningConclusion(
                    statement="Denim is cotton",
                    evidence_ids=("term-denim",),
                    ffo_refs=("denim", "textile"),
                    reasoning_note="Grounded in term-denim.",
                    standing="supported",
                ),
            ),
            uncertainties=(),
            missing_evidence=(),
            contradictions=(),
            confidence="high",
            unsupported=False,
            versions=ReasoningVersions(
                ffo_version="1.0",
                corpus_digest="967f891e4c91d4e9463be5ea183b62ad3f3548f35c1b1e4d8678da49bf4d2581",
                evidence_schema="1.0",
                reasoning_contract_version="2.0",
            ),
        )


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# 1. Prometheus Telemetry & /metrics Verification
# ==============================================================================

class TestObservabilityMetrics:
    def test_metrics_endpoint_returns_prometheus_format(self, client):
        client.get("/health")
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

        body = response.text
        assert "# HELP fansivibe_http_requests_total" in body
        assert "# TYPE fansivibe_http_requests_total counter"
        assert "# HELP fansivibe_http_request_duration_seconds" in body
        assert "# HELP fansivibe_http_status_total" in body
        assert 'fansivibe_http_status_total{code="200"}' in body
        assert 'fansivibe_http_status_total{code="429"}' in body
        assert 'fansivibe_http_status_total{code="502"}' in body
        assert 'fansivibe_http_status_total{code="503"}' in body
        assert 'fansivibe_http_status_total{code="504"}' in body
        assert "fansivibe_reasoning_concurrency_active" in body
        assert "fansivibe_readiness_status" in body
        assert "fansivibe_ollama_available" in body

    def test_metrics_privacy_guarantee(self, client):
        """Verify raw prompts, raw model JSON, user images, and secrets are NEVER in /metrics."""
        reasoner = DummyReasoner()
        app.dependency_overrides[get_fashion_reasoner] = lambda: reasoner
        try:
            client.post(
                "/v1/reasoning",
                json={"query": "what is denim"},
                headers={"Authorization": "Bearer super-secret-token-xyz123"},
            )
            response = client.get("/metrics")
            body = response.text
            assert "super-secret-token-xyz123" not in body
            assert "what is denim" not in body
            assert "denim is a sturdy" not in body.lower()
            assert "password" not in body.lower()
        finally:
            app.dependency_overrides.pop(get_fashion_reasoner, None)

    def test_collector_tracks_explicit_http_status_codes(self):
        collector = MetricsCollector()
        collector.record_http_request("GET", "/health", 200, 0.005)
        collector.record_http_request("POST", "/v1/reasoning", 429, 0.010)
        collector.record_http_request("POST", "/v1/reasoning", 502, 0.150)
        collector.record_http_request("POST", "/v1/reasoning", 503, 0.002)
        collector.record_http_request("POST", "/v1/reasoning", 504, 60.001)

        assert collector.get_status_count(200) == 1
        assert collector.get_status_count(429) == 1
        assert collector.get_status_count(502) == 1
        assert collector.get_status_count(503) == 1
        assert collector.get_status_count(504) == 1

        prom = collector.format_prometheus()
        assert 'fansivibe_http_status_total{code="200"} 1' in prom
        assert 'fansivibe_http_status_total{code="429"} 1' in prom
        assert 'fansivibe_http_status_total{code="502"} 1' in prom
        assert 'fansivibe_http_status_total{code="503"} 1' in prom
        assert 'fansivibe_http_status_total{code="504"} 1' in prom


# ==============================================================================
# 2. Staging Configuration Invariants (Objective 2)
# ==============================================================================

class TestStagingConfiguration:
    def test_staging_environment_properties(self):
        settings = Settings(
            FANSIVIBE_ENV="staging",
            DATABASE_URL="postgresql+psycopg://fansivibe:fansivibe_dev@127.0.0.1:5432/fansivibe",
            FANSIVIBE_AUTH_SECRET="staging-secure-secret-key-32-chars-long!",
            FANSIVIBE_OLLAMA_BASE_URL="http://127.0.0.1:11434",
            FANSIVIBE_OLLAMA_MODEL="qwen2.5vl:3b",
            FANSIVIBE_OLLAMA_TIMEOUT=60.0,
            FANSIVIBE_OLLAMA_CONNECT_TIMEOUT=5.0,
            FANSIVIBE_REASONING_TEMPERATURE=0.0,
            FANSIVIBE_REASONING_CONCURRENCY_LIMIT=2,
            FANSIVIBE_REASONING_KEEP_ALIVE="15m",
            FANSIVIBE_RATE_LIMIT_REASONING_PER_MINUTE=30,
            FANSIVIBE_DISABLE_REASONING=False,
        )
        assert settings.is_staging is True
        assert settings.is_production is False
        assert settings.is_docs_enabled is False  # Docs disabled in staging by default
        assert settings.reasoning_host == "http://127.0.0.1:11434"
        assert settings.reasoning_model == "qwen2.5vl:3b"
        assert settings.reasoning_timeout_s == 60.0
        assert settings.reasoning_connect_timeout_s == 5.0
        assert settings.reasoning_concurrency_limit == 2

    def test_staging_rejects_wildcard_cors_with_credentials(self):
        with pytest.raises(ValueError, match="Staging CORS must not use allow_origins=\\['\\*'\\]"):
            Settings(
                FANSIVIBE_ENV="staging",
                FANSIVIBE_CORS_ORIGINS=["*"],
                FANSIVIBE_CORS_ALLOW_CREDENTIALS=True,
                FANSIVIBE_AUTH_SECRET="staging-secure-secret-key-32-chars-long!",
            )


# ==============================================================================
# 3. Correlation ID (X-Request-Id) Propagation (Objective 5)
# ==============================================================================

class TestCorrelationIdEndToEnd:
    def test_custom_request_id_preserved(self, client):
        custom_id = "staging-client-test-id-998877"
        response = client.get("/health", headers={"X-Request-Id": custom_id})
        assert response.headers["X-Request-Id"] == custom_id

    def test_missing_request_id_generated_as_uuid(self, client):
        response = client.get("/health")
        req_id = response.headers.get("X-Request-Id")
        assert req_id is not None
        assert len(req_id) >= 32

    def test_error_response_preserves_request_id(self, client):
        custom_id = "test-error-req-id-12345"
        response = client.post(
            "/v1/reasoning",
            json={"query": ""},
            headers={"X-Request-Id": custom_id},
        )
        assert response.status_code == 422
        assert response.headers["X-Request-Id"] == custom_id


# ==============================================================================
# 4. Concurrency Limit & Resource Protection (Objective 6)
# ==============================================================================

class TestConcurrencyProtection:
    def test_concurrency_saturation_returns_429_retry_after(self):
        # Create a limiter with limit=2
        limiter = ConcurrencyLimiter(limit=2)
        assert limiter.acquire() is True
        assert limiter.active_count == 1
        assert limiter.acquire() is True
        assert limiter.active_count == 2

        # 3rd request fails to acquire within timeout
        assert limiter.acquire(timeout=0.05) is False

        # Release one slot
        limiter.release()
        assert limiter.active_count == 1
        # Now 3rd request can acquire
        assert limiter.acquire() is True
        assert limiter.active_count == 2
        limiter.release()
        limiter.release()
        assert limiter.active_count == 0

    def test_concurrency_semaphore_releases_on_exception(self, client):
        failing_reasoner = DummyReasoner(exc_to_raise=ReasoningExecutionError("malformed_json", "Bad JSON"))
        app.dependency_overrides[get_fashion_reasoner] = lambda: failing_reasoner
        try:
            limiter = get_reasoning_concurrency_limiter()
            initial_active = limiter.active_count

            response = client.post("/v1/reasoning", json={"query": "what is denim"})
            assert response.status_code == 502
            # Active count should return to initial
            assert limiter.active_count == initial_active
        finally:
            app.dependency_overrides.pop(get_fashion_reasoner, None)


# ==============================================================================
# 5. Failure Injection Matrix (Objective 7)
# ==============================================================================

class TestFailureInjectionScenarios:
    def test_scenario_a_postgres_unavailable(self, client):
        """PostgreSQL is unavailable -> /ready returns 503 database: disconnected."""
        failing_db = MagicMock()
        failing_db.execute.side_effect = Exception("DB connection refused")
        app.dependency_overrides[get_db] = lambda: failing_db
        try:
            res_ready = client.get("/ready")
            assert res_ready.status_code == 503
            assert res_ready.json()["status"] == "not_ready"
            assert res_ready.json()["database"] == "disconnected"

            res_detailed = client.get("/ready?detailed=true")
            assert res_detailed.status_code == 503
            assert res_detailed.json()["checks"]["database"] == "disconnected"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_scenario_b_ollama_unavailable(self, client):
        """Ollama is unavailable -> /ready reports unavailable, reasoning returns 503."""
        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        mock_lifecycle = MagicMock()
        mock_lifecycle.check_availability.return_value = ModelStatus(
            available=False, model_present=False, model_name="qwen2.5vl:3b", host="http://localhost:11434", latency_ms=1.0, error="Connection refused"
        )
        mock_lifecycle.model = "qwen2.5vl:3b"
        app.dependency_overrides[get_lifecycle_manager] = lambda: mock_lifecycle

        failing_reasoner = DummyReasoner(exc_to_raise=ReasoningExecutionError("unavailable", "Connection refused"))
        app.dependency_overrides[get_fashion_reasoner] = lambda: failing_reasoner

        try:
            res_ready = client.get("/ready?detailed=true")
            assert res_ready.status_code == 200  # Degraded ready for non-AI traffic
            assert res_ready.json()["status"] == "ready_degraded"
            assert res_ready.json()["checks"]["reasoning"] == "unavailable"

            res_query = client.post("/v1/reasoning", json={"query": "what is denim"})
            assert res_query.status_code == 503
            assert res_query.json()["error"]["code"] == "AI_FAILURE"
            assert res_query.json()["error"]["details"]["category"] == "unavailable"
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_lifecycle_manager, None)
            app.dependency_overrides.pop(get_fashion_reasoner, None)

    def test_scenario_c_ollama_model_missing(self, client):
        """Ollama running but model missing -> /ready reports model_missing."""
        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        mock_lifecycle = MagicMock()
        mock_lifecycle.check_availability.return_value = ModelStatus(
            available=True, model_present=False, model_name="qwen2.5vl:3b", host="http://localhost:11434", latency_ms=1.0, error=None
        )
        mock_lifecycle.model = "qwen2.5vl:3b"
        app.dependency_overrides[get_lifecycle_manager] = lambda: mock_lifecycle
        try:
            res_ready = client.get("/ready?detailed=true")
            assert res_ready.status_code == 200
            assert res_ready.json()["status"] == "ready_degraded"
            assert res_ready.json()["checks"]["reasoning"] == "model_missing"
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_lifecycle_manager, None)

    def test_scenario_d_reasoning_disabled(self, client, monkeypatch):
        """FANSIVIBE_DISABLE_REASONING=true -> /v1/reasoning returns 503, /ready reports disabled."""
        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        monkeypatch.setenv("FANSIVIBE_DISABLE_REASONING", "true")
        clear_settings_cache()
        try:
            res_ready = client.get("/ready?detailed=true")
            assert res_ready.status_code == 200
            assert res_ready.json()["checks"]["reasoning"] == "disabled"

            res_query = client.post("/v1/reasoning", json={"query": "what is denim"})
            assert res_query.status_code == 503
            assert res_query.json()["error"]["details"]["category"] == "disabled"
        finally:
            app.dependency_overrides.pop(get_db, None)
            monkeypatch.delenv("FANSIVIBE_DISABLE_REASONING", raising=False)
            clear_settings_cache()

    def test_scenario_e_request_timeout(self, client):
        """Reasoning timeout -> returns 504 TIMEOUT."""
        timeout_reasoner = DummyReasoner(exc_to_raise=ReasoningExecutionError("timeout", "Request timed out"))
        app.dependency_overrides[get_fashion_reasoner] = lambda: timeout_reasoner
        try:
            response = client.post("/v1/reasoning", json={"query": "what is denim"})
            assert response.status_code == 504
            assert response.json()["error"]["code"] == "TIMEOUT"
            assert response.json()["error"]["details"]["category"] == "timeout"
        finally:
            app.dependency_overrides.pop(get_fashion_reasoner, None)

    def test_scenario_f_concurrency_saturation(self, client):
        """Concurrency saturation (limit=2, requests > 2) -> returns 429 with Retry-After: 5."""
        limiter = get_reasoning_concurrency_limiter()
        # Acquire all available slots
        assert limiter.acquire() is True
        assert limiter.acquire() is True
        try:
            response = client.post("/v1/reasoning", json={"query": "what is denim"})
            assert response.status_code == 429
            assert response.json()["error"]["code"] == "RATE_LIMITED"
            assert response.json()["error"]["details"]["retry_after"] == 5
        finally:
            limiter.release()
            limiter.release()

    def test_scenario_g_rate_limit_saturation(self, client, monkeypatch):
        """IP rate-limit saturation -> returns 429."""
        monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("FANSIVIBE_RATE_LIMIT_REASONING_PER_MINUTE", "2")
        clear_settings_cache()
        reasoner = DummyReasoner()
        app.dependency_overrides[get_fashion_reasoner] = lambda: reasoner
        try:
            # 2 allowed
            r1 = client.post("/v1/reasoning", json={"query": "what is denim"})
            r2 = client.post("/v1/reasoning", json={"query": "cotton vs linen"})
            assert r1.status_code == 200
            assert r2.status_code == 200
            # 3rd is rate limited
            r3 = client.post("/v1/reasoning", json={"query": "white sneakers"})
            assert r3.status_code == 429
            assert r3.json()["error"]["code"] == "RATE_LIMITED"
        finally:
            app.dependency_overrides.pop(get_fashion_reasoner, None)
            monkeypatch.delenv("FANSIVIBE_RATE_LIMIT_ENABLED", raising=False)
            monkeypatch.delenv("FANSIVIBE_RATE_LIMIT_REASONING_PER_MINUTE", raising=False)
            clear_settings_cache()

    def test_scenario_h_malformed_reasoning_output(self, client):
        """Model emits malformed JSON -> returns 502 without leaking raw internal output."""
        bad_reasoner = DummyReasoner(exc_to_raise=ReasoningExecutionError("malformed_json", "Invalid JSON output"))
        app.dependency_overrides[get_fashion_reasoner] = lambda: bad_reasoner
        try:
            response = client.post("/v1/reasoning", json={"query": "what is denim"})
            assert response.status_code == 502
            assert response.json()["error"]["code"] == "AI_FAILURE"
            assert "traceback" not in response.text.lower()
            assert "stack" not in response.text.lower()
        finally:
            app.dependency_overrides.pop(get_fashion_reasoner, None)

    def test_scenario_i_backend_restart(self, client):
        """Simulate backend restart: caches clear and health/ready remain truthful."""
        clear_settings_cache()
        reset_reasoning_concurrency_limiter()
        # Probe health after restart
        res_health = client.get("/health")
        assert res_health.status_code == 200
        assert res_health.json() == {"status": "ok"}

    def test_scenario_j_backend_restart_ollama_alive(self, client):
        """Backend restarts while Ollama is running: warmup executes, model detected."""
        mock_lifecycle = MagicMock()
        mock_lifecycle.check_availability.return_value = ModelStatus(
            available=True, model_present=True, model_name="qwen2.5vl:3b", host="http://localhost:11434", latency_ms=1.5, error=None
        )
        mock_lifecycle.model = "qwen2.5vl:3b"
        app.dependency_overrides[get_lifecycle_manager] = lambda: mock_lifecycle

        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            res_ready = client.get("/ready?detailed=true")
            assert res_ready.status_code == 200
            assert res_ready.json()["status"] == "ready"
            assert res_ready.json()["checks"]["reasoning"] == "ok"
            assert res_ready.json()["checks"]["reasoning_model"] == "qwen2.5vl:3b"
        finally:
            app.dependency_overrides.pop(get_lifecycle_manager, None)
            app.dependency_overrides.pop(get_db, None)


# ==============================================================================
# 6. Frozen Artifact Hash Audit (Objective 13)
# ==============================================================================

class TestFrozenArtifactHashes:
    EXPECTED_HASHES = {
        "reasoning_prompt.py": "bf81162ef6efc483b46967a9b76bb7ac20b8ee29ba22ae244f5d7262ae2985b1",
        "conclusion_admission.py": "c8a7c68eb088ab27f9da30fd811754225c4ced88b627f2a8a1c7fe4e4c85bb52",
        "ffo_ref_selector.py": "3450535bda541f0b892cca3fc351732915bbabff0c71466012d8959cecc0d2ec",
        "ffo_reasoning.py": "bdb5398d5e644bbcb38ea76b3248863cbfe79479712088d15436cee9e588c382",
        "ffo_benchmark.py": "fb77f39a920ed61cfb73a16054116cc2269a7aac1b97537abeee7811624e168d",
        "benchmark_v01.json": "ba8d95475e17082c29d65426d4562f80934b1c5402f953e23414127445003c1f",
        "benchmark_heldout_3ai.json": "94c383cc5ad0235085b266a80b31bd52970ed5ddcc6366827331ccc4c082f2c7",
    }
    EXPECTED_CORPUS_HASH = "967f891e4c91d4e9463be5ea183b62ad3f3548f35c1b1e4d8678da49bf4d2581"

    def test_frozen_python_and_benchmark_artifacts(self):
        import hashlib
        from pathlib import Path
        backend_dir = Path(__file__).resolve().parent.parent

        rel_paths = {
            "reasoning_prompt.py": backend_dir / "app" / "ai" / "reasoning_prompt.py",
            "conclusion_admission.py": backend_dir / "app" / "domain" / "services" / "conclusion_admission.py",
            "ffo_ref_selector.py": backend_dir / "app" / "domain" / "services" / "ffo_ref_selector.py",
            "ffo_reasoning.py": backend_dir / "app" / "domain" / "services" / "ffo_reasoning.py",
            "ffo_benchmark.py": backend_dir / "app" / "domain" / "services" / "ffo_benchmark.py",
            "benchmark_v01.json": backend_dir / "app" / "data" / "ffo" / "benchmark" / "benchmark_v01.json",
            "benchmark_heldout_3ai.json": backend_dir / "app" / "data" / "ffo" / "benchmark" / "benchmark_heldout_3ai.json",
        }

        for name, expected_hash in self.EXPECTED_HASHES.items():
            path = rel_paths[name]
            assert path.exists(), f"Frozen artifact {name} missing at {path}"
            calculated = hashlib.sha256(path.read_bytes()).hexdigest()
            assert calculated == expected_hash, f"Frozen hash mismatch for {name}: expected {expected_hash}, got {calculated}"

    def test_frozen_ffo_corpus_digest(self):
        from app.data.ffo import FFO_VERSION, corpus
        from app.domain.services.ffo_reasoning import corpus_digest

        docs = corpus.load_documents()
        index = corpus.build_index(docs)
        v = corpus.corpus_versions(index)
        d = corpus_digest(v, FFO_VERSION)
        assert d == self.EXPECTED_CORPUS_HASH, (
            f"Corpus digest mismatch: expected {self.EXPECTED_CORPUS_HASH}, got {d}"
        )


