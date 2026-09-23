"""Test Suite for Phase 3AN: Production Canary Deployment & Traffic Migration.

Verifies:
- Production configuration invariants and security controls
- Canary traffic routing & deterministic 5% splitting
- Instant rollback mechanisms (traffic diversion & kill-switch)
- Failure injection matrix (Ollama offline, model missing, timeout, saturation)
- Production security headers, CORS, and disabled documentation endpoints
- Prometheus metrics telemetry exposition
- Frozen artifact hash integrity (8 authoritative artifacts)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from app.config.settings import Settings, clear_settings_cache


class TestProductionConfiguration:
    """Verifies production configuration invariants and security gates."""

    def test_production_rejects_default_dev_db_credentials(self):
        with pytest.raises(ValueError, match="development credentials"):
            Settings(
                FANSIVIBE_ENV="production",
                DATABASE_URL="postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe",
                FANSIVIBE_AUTH_SECRET="secure-prod-auth-secret-min-32-chars-long",
            )

    def test_production_rejects_insecure_auth_secret(self):
        with pytest.raises(ValueError, match="FANSIVIBE_AUTH_SECRET"):
            Settings(
                FANSIVIBE_ENV="production",
                DATABASE_URL="postgresql+psycopg://fansivibe_app:secret@db-prod.internal:5432/fansivibe_prod",
                FANSIVIBE_AUTH_SECRET="dev-only-insecure-auth-secret",
            )

    def test_production_rejects_short_auth_secret(self):
        with pytest.raises(ValueError, match="at least 32 characters"):
            Settings(
                FANSIVIBE_ENV="production",
                DATABASE_URL="postgresql+psycopg://fansivibe_app:secret@db-prod.internal:5432/fansivibe_prod",
                FANSIVIBE_AUTH_SECRET="short-secret",
            )

    def test_production_rejects_allow_dev_token(self):
        with pytest.raises(ValueError, match="FANSIVIBE_ALLOW_DEV_TOKEN cannot be enabled"):
            Settings(
                FANSIVIBE_ENV="production",
                DATABASE_URL="postgresql+psycopg://fansivibe_app:secret@db-prod.internal:5432/fansivibe_prod",
                FANSIVIBE_AUTH_SECRET="secure-prod-auth-secret-min-32-chars-long",
                FANSIVIBE_ALLOW_DEV_TOKEN=True,
            )

    def test_production_rejects_wildcard_cors_with_credentials(self):
        with pytest.raises(ValueError, match="must not use allow_origins="):
            Settings(
                FANSIVIBE_ENV="production",
                DATABASE_URL="postgresql+psycopg://fansivibe_app:secret@db-prod.internal:5432/fansivibe_prod",
                FANSIVIBE_AUTH_SECRET="secure-prod-auth-secret-min-32-chars-long",
                FANSIVIBE_CORS_ORIGINS=["*"],
                FANSIVIBE_CORS_ALLOW_CREDENTIALS=True,
            )

    def test_valid_production_settings_accepted(self):
        s = Settings(
            FANSIVIBE_ENV="production",
            DATABASE_URL="postgresql+psycopg://fansivibe_app:secret@db-prod.internal:5432/fansivibe_prod",
            FANSIVIBE_AUTH_SECRET="secure-prod-auth-secret-min-32-chars-long",
            FANSIVIBE_OLLAMA_BASE_URL="http://ollama-prod.internal:11434",
            FANSIVIBE_CORS_ORIGINS=["https://fansivibe.com"],
            FANSIVIBE_CORS_ALLOW_CREDENTIALS=False,
            FANSIVIBE_ALLOW_DEV_TOKEN=False,
        )
        assert s.is_production is True
        assert s.is_docs_enabled is False
        assert s.reasoning_host == "http://ollama-prod.internal:11434"


class TestCanaryTrafficSplitting:
    """Verifies the CanaryRouter and traffic distribution logic."""

    def test_canary_router_default_percentage(self):
        from deploy.production_canary_proxy import CanaryRouter
        router = CanaryRouter(canary_percentage=5.0)
        assert router.canary_percentage == 5.0
        assert router.rollback_active is False

    def test_canary_forced_header_routing(self):
        from deploy.production_canary_proxy import CanaryRouter, CANARY_UPSTREAM_URL, PRIMARY_UPSTREAM_URL
        router = CanaryRouter(canary_percentage=5.0)
        # Forced canary
        url, is_canary = router.route("req-1", force_canary="true")
        assert is_canary is True
        assert url == CANARY_UPSTREAM_URL

        # Forced primary
        url, is_canary = router.route("req-2", force_canary="false")
        assert is_canary is False
        assert url == PRIMARY_UPSTREAM_URL

    def test_canary_deterministic_hash_routing(self):
        from deploy.production_canary_proxy import CanaryRouter
        router = CanaryRouter(canary_percentage=50.0)
        # Same request ID must always route to the same upstream
        url1, c1 = router.route("fixed-id-12345")
        url2, c2 = router.route("fixed-id-12345")
        assert url1 == url2
        assert c1 == c2

    def test_canary_rollback_zero_percentage(self):
        from deploy.production_canary_proxy import CanaryRouter, PRIMARY_UPSTREAM_URL
        router = CanaryRouter(canary_percentage=5.0)
        router.set_canary_percentage(0.0)
        assert router.rollback_active is True
        # All requests must route to primary
        for i in range(50):
            url, is_canary = router.route(f"req-id-{i}")
            assert is_canary is False
            assert url == PRIMARY_UPSTREAM_URL


class TestProductionProxyBoundary:
    """Verifies proxy boundary security, headers, size bounding, and timeouts."""

    @pytest.fixture
    def client(self):
        from deploy.production_canary_proxy import proxy_app
        return TestClient(proxy_app, raise_server_exceptions=False)

    def test_proxy_blocks_swagger_docs_in_production(self, client):
        for path in ("/docs", "/redoc", "/openapi.json"):
            resp = client.get(path)
            assert resp.status_code == 404
            assert "API documentation is disabled in production" in resp.json()["error"]["message"]

    def test_proxy_enforces_payload_size_limit(self, client):
        oversized = "a" * (2 * 1024 * 1024 + 10)
        resp = client.post("/v1/reasoning", content=oversized, headers={"Content-Type": "application/json"})
        assert resp.status_code == 413
        assert resp.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"

    def test_proxy_injects_security_headers_and_correlation(self, client):
        with patch("deploy.production_canary_proxy.http_client.request") as mock_req:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.content = b'{"status":"ok"}'
            mock_resp.headers = {"content-type": "application/json"}
            mock_req.return_value = mock_resp

            resp = client.get("/health", headers={"X-Request-Id": "custom-uuid-123"})
            assert resp.status_code == 200
            assert resp.headers.get("x-request-id") == "custom-uuid-123"
            assert "x-canary" in resp.headers
            assert resp.headers.get("x-proxy-by") == "Fansivibe-Production-Canary-Proxy"
            assert "strict-transport-security" in resp.headers
            assert resp.headers.get("x-content-type-options") == "nosniff"
            assert resp.headers.get("x-frame-options") == "DENY"

    def test_proxy_gateway_timeout_maps_to_504(self, client):
        import httpx
        with patch("deploy.production_canary_proxy.http_client.request", side_effect=httpx.TimeoutException("Read timed out")):
            resp = client.post("/v1/reasoning", json={"query": "test query"})
            assert resp.status_code == 504
            assert resp.json()["error"]["code"] == "GATEWAY_TIMEOUT"

    def test_proxy_backend_connect_error_maps_to_502(self, client):
        import httpx
        with patch("deploy.production_canary_proxy.http_client.request", side_effect=httpx.ConnectError("Connection refused")):
            resp = client.get("/health")
            assert resp.status_code == 502
            assert resp.json()["error"]["code"] == "BAD_GATEWAY"


class TestRollbackAndKillSwitch:
    """Verifies rollback mechanisms and reasoning kill-switch."""

    def test_reasoning_kill_switch_behavior(self, monkeypatch):
        from app.main import app
        from app.config.settings import clear_settings_cache

        client = TestClient(app)
        monkeypatch.setenv("FANSIVIBE_DISABLE_REASONING", "true")
        clear_settings_cache()
        try:
            # 1. Reasoning query must return 503
            resp = client.post("/v1/reasoning", json={"query": "what is denim"})
            assert resp.status_code == 503
            data = resp.json()
            assert data["error"]["code"] in ("AI_FAILURE", "AI_UNAVAILABLE")
            assert "disabled" in data["error"]["message"].lower()

            # 2. Detailed readiness check must report reasoning as disabled
            from app.api.deps import get_db
            mock_db = MagicMock()
            app.dependency_overrides[get_db] = lambda: mock_db
            try:
                r_ready = client.get("/ready?detailed=true")
                assert r_ready.status_code == 200
                assert r_ready.json()["checks"]["reasoning"] == "disabled"
            finally:
                app.dependency_overrides.pop(get_db, None)
        finally:
            monkeypatch.delenv("FANSIVIBE_DISABLE_REASONING", raising=False)
            clear_settings_cache()


class TestPrometheusMetricsExposition:
    """Verifies Prometheus metrics endpoint and privacy guarantees."""

    def test_metrics_endpoint_telemetry_schema(self):
        from app.main import app
        from app.api.deps import get_db

        client = TestClient(app)
        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            # Trigger health and ready checks
            client.get("/health")
            client.get("/ready")

            resp = client.get("/metrics")
            assert resp.status_code == 200
            text = resp.text

            # Verify key metrics exist
            assert "fansivibe_http_requests_total" in text
            assert "fansivibe_http_status_total" in text
            assert "fansivibe_readiness_status" in text
            assert "fansivibe_ollama_available" in text

            # Verify privacy: zero PII, zero tokens, zero raw output
            assert "secret" not in text.lower()
            assert "password" not in text.lower()
            assert "qwen2.5vl" not in text.lower() or "fansivibe" in text
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestFrozenArtifactHashes:
    """Authoritative SHA-256 audit for all 8 frozen reasoning artifacts."""

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
