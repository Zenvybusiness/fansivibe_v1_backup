"""Focused unit tests for global error handling, crash capture, and secret sanitization (P2-10).

Validates:
- Unexpected exceptions produce a truthful generic 500 INTERNAL_ERROR response.
- Response bodies never leak stack traces, SQL, file paths, or exception text.
- X-Request-Id response header exactly matches details.request_id.
- Client-provided X-Request-Id is faithfully preserved for distributed tracing.
- Server-side logging scrubs database passwords, Bearer tokens, and JWTs.
- Starlette HTTPExceptions (404, 405) conform to the frozen error contract.
- Existing typed ApiError behavior (401, 404, 409, 422, 502, 503) is completely preserved.
"""

from __future__ import annotations

import logging
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import errors
from app.api.errors import (
    ApiError,
    _sanitize_log_message,
    ai_failure,
    authentication_error,
    conflict,
    database_failure,
    external_failure,
    not_found,
)


@pytest.fixture
def error_test_app() -> FastAPI:
    """Create a minimal test FastAPI app with error handlers registered and synthetic test routes."""
    test_app = FastAPI()
    errors.register_error_handlers(test_app)

    @test_app.get("/test/unexpected-crash")
    def route_unexpected():
        raise RuntimeError("UNEXPECTED_DATABASE_CRASH: connection dropped at /var/run/postgresql")

    @test_app.get("/test/zero-division")
    def route_zero_division():
        return 1 / 0

    @test_app.get("/test/auth-error")
    def route_auth_error():
        raise authentication_error()

    @test_app.get("/test/not-found-error")
    def route_not_found():
        raise not_found()

    @test_app.get("/test/conflict-error")
    def route_conflict():
        raise conflict(kind="duplicate_wear")

    @test_app.get("/test/database-failure")
    def route_db_failure():
        raise database_failure()

    @test_app.get("/test/ai-failure")
    def route_ai_failure():
        raise ai_failure()

    @test_app.get("/test/external-failure")
    def route_external_failure():
        raise external_failure()

    return test_app


@pytest.fixture
def client(error_test_app: FastAPI) -> TestClient:
    return TestClient(error_test_app, raise_server_exceptions=False)


class TestUnexpectedExceptionHandling:
    """Validate that unhandled server crashes produce a safe 500 response without leaking internals."""

    def test_unexpected_runtime_error_returns_generic_500(self, client: TestClient):
        response = client.get("/test/unexpected-crash")
        assert response.status_code == 500

        data = response.json()
        assert "error" in data
        error = data["error"]
        assert error["code"] == "INTERNAL_ERROR"
        assert error["message"] == "Something went wrong on our side. Please try again."

        # Verify no internals leaked
        raw_text = response.text
        assert "UNEXPECTED_DATABASE_CRASH" not in raw_text
        assert "/var/run/postgresql" not in raw_text
        assert "RuntimeError" not in raw_text
        assert "Traceback" not in raw_text

    def test_zero_division_returns_generic_500(self, client: TestClient):
        response = client.get("/test/zero-division")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL_ERROR"
        assert "ZeroDivisionError" not in response.text

    def test_request_id_synchronized_between_header_and_body(self, client: TestClient):
        response = client.get("/test/unexpected-crash")
        assert response.status_code == 500

        header_id = response.headers.get("X-Request-Id")
        assert header_id is not None
        assert len(header_id) > 0

        body_id = response.json()["error"]["details"]["request_id"]
        assert header_id == body_id, "X-Request-Id header must exactly match details.request_id"

    def test_client_provided_request_id_preserved(self, client: TestClient):
        custom_req_id = "req-trace-p2-10-custom-uuid-98765"
        response = client.get(
            "/test/unexpected-crash",
            headers={"X-Request-Id": custom_req_id},
        )
        assert response.status_code == 500
        assert response.headers.get("X-Request-Id") == custom_req_id
        assert response.json()["error"]["details"]["request_id"] == custom_req_id


class TestSensitiveLogSanitization:
    """Validate that error logging scrubs credentials, passwords, and tokens."""

    def test_sanitizes_db_connection_url_passwords(self):
        msg = "Failed to connect to postgresql+psycopg://db_admin:SuperSecretPass123!@db-cluster.internal:5432/fansivibe"
        sanitized = _sanitize_log_message(msg)
        assert "SuperSecretPass123!" not in sanitized
        assert "postgresql+psycopg://db_admin:[REDACTED]@db-cluster.internal:5432/fansivibe" in sanitized

    def test_sanitizes_bearer_tokens(self):
        msg = "Token validation failed for Bearer eyJhbGciOiJIUzI1Ni.eyJzdWIiOiIxMjM0NTY3ODkwIn0.some_signature_part"
        sanitized = _sanitize_log_message(msg)
        assert "some_signature_part" not in sanitized
        assert "Bearer [REDACTED]" in sanitized

    def test_sanitizes_raw_jwt(self):
        msg = "Malformed token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
        sanitized = _sanitize_log_message(msg)
        assert "signature" not in sanitized
        assert "[REDACTED_JWT]" in sanitized

    def test_sanitizes_parameter_secrets(self):
        msg = "Query params rejected: user=alex&password=MyClearTextPassword&api_key=ak_secret_123"
        sanitized = _sanitize_log_message(msg)
        assert "MyClearTextPassword" not in sanitized
        assert "ak_secret_123" not in sanitized
        assert "password=[REDACTED]" in sanitized
        assert "api_key=[REDACTED]" in sanitized

    def test_server_error_logs_contain_sanitized_message(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ):
        with caplog.at_level(logging.ERROR, logger="fansivibe.api.errors"):
            response = client.get("/test/unexpected-crash")
            assert response.status_code == 500

        # Verify an ERROR log was generated with request_id and sanitized message
        matching_records = [r for r in caplog.records if r.name == "fansivibe.api.errors"]
        assert len(matching_records) >= 1
        record = matching_records[0]
        assert record.levelname == "ERROR"
        assert "Unhandled server exception" in record.message
        assert "request_id=" in record.message


class TestStarletteHttpExceptionHandling:
    """Validate that unmapped HTTP exceptions conform to the wire contract."""

    def test_nonexistent_route_returns_typed_not_found(self, client: TestClient):
        response = client.get("/v1/this/path/does/not/exist")
        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "NOT_FOUND"
        assert data["error"]["message"] == "The requested item was not found."
        assert response.headers.get("X-Request-Id") is not None

    def test_method_not_allowed_returns_typed_405(self, client: TestClient):
        response = client.post("/test/unexpected-crash")
        assert response.status_code == 405

        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "METHOD_NOT_ALLOWED"
        assert response.headers.get("X-Request-Id") is not None


class TestExistingTypedErrorsPreserved:
    """Validate that frozen typed ApiError behavior is completely unaffected."""

    def test_auth_error_preserves_bearer_challenge_and_code(self, client: TestClient):
        response = client.get("/test/auth-error")
        assert response.status_code == 401
        assert response.headers.get("WWW-Authenticate") == "Bearer"

        data = response.json()
        assert data["error"]["code"] == "AUTHENTICATION_ERROR"
        assert data["error"]["message"] == "Your session has expired or is invalid. Please sign in again."

    def test_not_found_error_preserves_contract(self, client: TestClient):
        response = client.get("/test/not-found-error")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_conflict_error_preserves_details(self, client: TestClient):
        response = client.get("/test/conflict-error")
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "CONFLICT"
        assert data["error"]["details"]["kind"] == "duplicate_wear"

    def test_database_failure_500_preserves_request_id_sync(self, client: TestClient):
        response = client.get("/test/database-failure")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "DATABASE_FAILURE"
        header_id = response.headers.get("X-Request-Id")
        body_id = data["error"]["details"]["request_id"]
        assert header_id == body_id

    def test_ai_failure_503_preserves_contract(self, client: TestClient):
        response = client.get("/test/ai-failure")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "AI_FAILURE"

    def test_external_failure_502_preserves_contract(self, client: TestClient):
        response = client.get("/test/external-failure")
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "EXTERNAL_SERVICE_FAILURE"
