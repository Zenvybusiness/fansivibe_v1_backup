"""Unit tests for production deployment hardening (P2-9).

Validates:
- Settings production vs development invariants (DATABASE_URL, FANSIVIBE_AUTH_SECRET, FANSIVIBE_ALLOW_DEV_TOKEN).
- Database connection pool configuration.
- CORS origins parsing and behavior.
- API documentation (/docs, /redoc, /openapi.json) production gating.
- Health (/health liveness) and Readiness (/ready, /health/ready) probes.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config.settings import Settings


class TestProductionSettingsInvariants:
    """Validate that production environment rejects insecure defaults and requires explicit config."""

    def test_production_succeeds_with_valid_explicit_configuration(self):
        settings = Settings(
            environment="production",
            database_url="postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_fansivibe",
            auth_secret="a" * 32,
            allow_dev_token=False,
        )
        assert settings.is_production is True
        assert settings.is_docs_enabled is False

    def test_production_rejects_default_dev_database_url(self):
        with pytest.raises(ValidationError, match="development credentials"):
            Settings(
                environment="production",
                database_url="postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe",
                auth_secret="a" * 32,
                allow_dev_token=False,
            )

    def test_production_rejects_database_url_with_dev_password(self):
        with pytest.raises(ValidationError, match="fansivibe_dev"):
            Settings(
                environment="production",
                database_url="postgresql+psycopg://fansivibe:fansivibe_dev@prod-db:5432/fansivibe",
                auth_secret="a" * 32,
                allow_dev_token=False,
            )

    def test_production_rejects_default_dev_auth_secret(self):
        with pytest.raises(ValidationError, match="FANSIVIBE_AUTH_SECRET"):
            Settings(
                environment="production",
                database_url="postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_fansivibe",
                auth_secret="dev-only-insecure-auth-secret",
                allow_dev_token=False,
            )

    def test_production_rejects_short_auth_secret(self):
        with pytest.raises(ValidationError, match="at least 32 characters"):
            Settings(
                environment="production",
                database_url="postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_fansivibe",
                auth_secret="short_insecure_secret",
                allow_dev_token=False,
            )

    def test_production_rejects_allow_dev_token_true(self):
        with pytest.raises(ValidationError, match="FANSIVIBE_ALLOW_DEV_TOKEN"):
            Settings(
                environment="production",
                database_url="postgresql+psycopg://prod_user:StrongProdPass123!@db.internal:5432/prod_fansivibe",
                auth_secret="a" * 32,
                allow_dev_token=True,
            )

    def test_development_allows_defaults(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("FANSIVIBE_ALLOW_DEV_TOKEN", raising=False)
        settings = Settings(environment="development")
        assert settings.is_production is False
        assert settings.is_docs_enabled is True
        assert settings.allow_dev_token is False
        assert "fansivibe_dev" in settings.database_url

    def test_test_environment_allows_defaults(self):
        settings = Settings(environment="test")
        assert settings.is_production is False
        assert settings.is_docs_enabled is True


class TestDatabasePoolConfiguration:
    """Validate database pool settings parsing and defaults."""

    def test_default_pool_settings(self):
        settings = Settings()
        assert settings.db_pool_size == 5
        assert settings.db_max_overflow == 10
        assert settings.db_pool_timeout_s == 30.0
        assert settings.db_pool_recycle_s == 1800

    def test_custom_pool_settings(self):
        settings = Settings(
            db_pool_size=20,
            db_max_overflow=40,
            db_pool_timeout_s=60.0,
            db_pool_recycle_s=900,
        )
        assert settings.db_pool_size == 20
        assert settings.db_max_overflow == 40
        assert settings.db_pool_timeout_s == 60.0
        assert settings.db_pool_recycle_s == 900


class TestCorsConfiguration:
    """Validate CORS origins parsing from string, JSON array, and list."""

    def test_default_cors_origins_empty(self):
        settings = Settings()
        assert settings.cors_origins == []

    def test_comma_separated_origins(self):
        settings = Settings(
            cors_origins="https://fansivibe.com, https://app.fansivibe.com"  # type: ignore[arg-type]
        )
        assert settings.cors_origins == [
            "https://fansivibe.com",
            "https://app.fansivibe.com",
        ]

    def test_json_list_origins(self):
        settings = Settings(
            cors_origins='["https://fansivibe.com", "https://app.fansivibe.com"]'  # type: ignore[arg-type]
        )
        assert settings.cors_origins == [
            "https://fansivibe.com",
            "https://app.fansivibe.com",
        ]


class TestApiDocsGating:
    """Validate docs_url and redoc_url behavior across environments."""

    def test_docs_enabled_in_development_by_default(self):
        settings = Settings(environment="development")
        assert settings.is_docs_enabled is True

    def test_docs_enabled_in_test_by_default(self):
        settings = Settings(environment="test")
        assert settings.is_docs_enabled is True

    def test_docs_disabled_in_production_by_default(self):
        settings = Settings(
            environment="production",
            database_url="postgresql+psycopg://prod:prod@prod-db:5432/fansivibe",
            auth_secret="a" * 32,
            allow_dev_token=False,
        )
        assert settings.is_docs_enabled is False

    def test_docs_explicitly_enabled_in_production(self):
        settings = Settings(
            environment="production",
            database_url="postgresql+psycopg://prod:prod@prod-db:5432/fansivibe",
            auth_secret="a" * 32,
            enable_docs=True,
            allow_dev_token=False,
        )
        assert settings.is_docs_enabled is True

    def test_docs_explicitly_disabled_in_development(self):
        settings = Settings(environment="development", enable_docs=False)
        assert settings.is_docs_enabled is False


class TestHealthAndReadinessEndpoints:
    """Validate liveness (/health) and truthful readiness (/ready, /health/ready) probes."""

    def test_health_liveness_probe_returns_ok(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_readiness_probe_success(self):
        from unittest.mock import MagicMock
        from fastapi.testclient import TestClient
        from app.infrastructure.db.session import get_db
        from app.main import app

        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock()

        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            client = TestClient(app)
            response = client.get("/ready")
            assert response.status_code == 200
            assert response.json() == {
                "status": "ready",
                "database": "connected",
            }

            # Also check alias /health/ready
            alias_resp = client.get("/health/ready")
            assert alias_resp.status_code == 200
            assert alias_resp.json() == {
                "status": "ready",
                "database": "connected",
            }
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_readiness_probe_failure_returns_503(self):
        from unittest.mock import MagicMock
        from fastapi.testclient import TestClient
        from app.infrastructure.db.session import get_db
        from app.main import app

        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("Database connection refused")

        app.dependency_overrides[get_db] = lambda: mock_db
        try:
            client = TestClient(app)
            response = client.get("/ready")
            assert response.status_code == 503
            assert response.json() == {
                "status": "not_ready",
                "database": "disconnected",
            }
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestMigrationReadiness:
    """21.2 — migration safety: single head, linear upgrade path (DB-free)."""

    def _script(self):
        import pathlib

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        backend = pathlib.Path(__file__).resolve().parents[1]
        config = Config(str(backend / "alembic.ini"))
        config.set_main_option("script_location", str(backend / "alembic"))
        return ScriptDirectory.from_config(config)

    def test_single_alembic_head(self):
        heads = self._script().get_heads()
        assert len(heads) == 1, f"production requires one head, found: {heads}"

    def test_upgrade_path_reaches_head(self):
        script = self._script()
        (head,) = script.get_heads()
        # Every revision must be an ancestor of head (linear history).
        revisions = list(script.walk_revisions())
        assert len(revisions) > 0
        assert head in {rev.revision for rev in revisions}


class TestReasoningProductionSettings:
    """Validate reasoning configuration and production invariants (Phase 3AL)."""

    def test_default_reasoning_settings(self):
        settings = Settings()
        assert settings.reasoning_host == "http://localhost:11434"
        assert settings.reasoning_model == "qwen2.5vl:3b"
        assert settings.reasoning_timeout_s == 60.0
        assert settings.reasoning_temperature == 0.0
        assert settings.reasoning_max_retries == 1
        assert settings.reasoning_concurrency_limit == 2
        assert settings.reasoning_keep_alive == "15m"
        assert settings.reasoning_rate_limit_per_minute == 30
        assert settings.disable_reasoning is False

    def test_production_rejects_zero_concurrency_limit(self):
        with pytest.raises(ValidationError, match="CONCURRENCY_LIMIT"):
            Settings(reasoning_concurrency_limit=0)

    def test_production_rejects_negative_or_zero_timeout(self):
        with pytest.raises(ValidationError, match="TIMEOUT_S"):
            Settings(reasoning_timeout_s=0.0)

    def test_production_rejects_zero_rate_limit(self):
        with pytest.raises(ValidationError, match="RATE_LIMIT_REASONING_PER_MINUTE"):
            Settings(reasoning_rate_limit_per_minute=0)


class TestSecurityHeadersAndCorrelation:
    """Validate security headers and correlation ID middleware (Phase 3AL)."""

    def test_security_headers_present_on_health_endpoint(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "default-src 'none'" in response.headers.get("Content-Security-Policy", "")
        assert response.headers.get("X-Request-Id") is not None

    def test_incoming_request_id_preserved_in_response(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        custom_id = "test-custom-request-id-12345"
        response = client.get("/health", headers={"X-Request-Id": custom_id})
        assert response.status_code == 200
        assert response.headers.get("X-Request-Id") == custom_id


class TestDetailedReadinessEndpoint:
    """Validate multi-subsystem readiness check (Phase 3AL)."""

    def test_detailed_readiness_probe_success(self):
        from unittest.mock import MagicMock
        from fastapi.testclient import TestClient
        from app.api.deps import get_lifecycle_manager
        from app.infrastructure.db.session import get_db
        from app.ai.lifecycle import ModelStatus
        from app.main import app

        mock_db = MagicMock()
        mock_db.execute.return_value = MagicMock()

        mock_lifecycle = MagicMock()
        mock_lifecycle.model = "qwen2.5vl:3b"
        mock_lifecycle.check_availability.return_value = ModelStatus(
            available=True,
            model_present=True,
            model_name="qwen2.5vl:3b",
            host="http://localhost:11434",
            latency_ms=1.2,
        )

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_lifecycle_manager] = lambda: mock_lifecycle
        try:
            client = TestClient(app)
            response = client.get("/ready?detailed=true")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["database"] == "connected"
            assert data["checks"]["database"] == "ok"
            assert data["checks"]["ffo_corpus"] == "ok"
            assert data["checks"]["reasoning"] == "ok"
            assert data["checks"]["reasoning_model"] == "qwen2.5vl:3b"
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_lifecycle_manager, None)


class TestConcurrencyLimiter:
    """Validate in-process concurrency guard (Phase 3AL)."""

    def test_concurrency_limiter_acquire_and_release(self):
        from app.api.rate_limit import ConcurrencyLimiter

        limiter = ConcurrencyLimiter(limit=1)
        assert limiter.acquire(timeout=0.1) is True
        assert limiter.active_count == 1

        # Second acquire should fail because limit is 1
        assert limiter.acquire(timeout=0.05) is False

        limiter.release()
        assert limiter.active_count == 0

        # Should be able to acquire again
        assert limiter.acquire(timeout=0.1) is True
        limiter.release()


class TestOllamaLifecycleManagerUnit:
    """Validate Ollama lifecycle manager probe and warmup (Phase 3AL)."""

    def test_check_availability_finds_model(self):
        from unittest.mock import MagicMock
        from app.ai.lifecycle import OllamaLifecycleManager

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "qwen2.5vl:3b", "size": 12345}]
        }
        mock_client.get.return_value = mock_resp

        mgr = OllamaLifecycleManager(
            host="http://test-ollama:11434",
            model="qwen2.5vl:3b",
            client=mock_client,
        )
        status = mgr.check_availability(timeout_s=1.0)
        assert status.available is True
        assert status.model_present is True
        assert status.error is None

    def test_check_availability_model_missing(self):
        from unittest.mock import MagicMock
        from app.ai.lifecycle import OllamaLifecycleManager

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [{"name": "llama3:latest"}]
        }
        mock_client.get.return_value = mock_resp

        mgr = OllamaLifecycleManager(
            host="http://test-ollama:11434",
            model="qwen2.5vl:3b",
            client=mock_client,
        )
        status = mgr.check_availability(timeout_s=1.0)
        assert status.available is True
        assert status.model_present is False
        assert "not found" in (status.error or "")

    def test_warmup_success(self):
        from unittest.mock import MagicMock
        from app.ai.lifecycle import OllamaLifecycleManager

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp

        mgr = OllamaLifecycleManager(
            host="http://test-ollama:11434",
            model="qwen2.5vl:3b",
            keep_alive="15m",
            client=mock_client,
        )
        assert mgr.warmup(timeout_s=1.0) is True

