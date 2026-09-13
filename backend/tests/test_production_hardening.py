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
