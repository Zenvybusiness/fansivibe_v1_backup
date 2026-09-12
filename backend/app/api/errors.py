"""API error mapping — the frozen 12-category contract.

Wire body: ``{ "error": { "code", "message", "details"? } }``
(`API_ERROR_CONTRACT.md` §5). Only allow-listed `details` reach the client
(ER-1); internals never leak (C-7/C-8).
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """A typed API error mapped to the frozen taxonomy."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def not_found() -> ApiError:
    return ApiError(
        status_code=404,
        code="NOT_FOUND",
        message="The requested item was not found.",
    )


def authentication_error() -> ApiError:
    return ApiError(
        status_code=401,
        code="AUTHENTICATION_ERROR",
        message="Your session has expired or is invalid. Please sign in again.",
    )


def validation(field_errors: list[dict[str, Any]]) -> ApiError:
    return ApiError(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Some of the provided values are not valid. Please check your input.",
        details={"field_errors": field_errors},
    )


def conflict(kind: str = "duplicate") -> ApiError:
    return ApiError(
        status_code=409,
        code="CONFLICT",
        message="This action conflicts with the current state. Refresh and try again.",
        details={"kind": kind},
    )


def ai_failure() -> ApiError:
    return ApiError(
        status_code=503,
        code="AI_FAILURE",
        message="The style service is temporarily unavailable. Please try again shortly.",
    )


def external_failure() -> ApiError:
    """An external provider the request depends on is unreachable.

    D-AUTH-1 social sign-in answers this while no external identity
    provider is configured (AUTH_API §5.2: 502 on the social exchange).
    """
    return ApiError(
        status_code=502,
        code="EXTERNAL_SERVICE_FAILURE",
        message="The sign-in service is temporarily unavailable. Please try again shortly.",
    )


def database_failure() -> ApiError:
    return ApiError(
        status_code=500,
        code="DATABASE_FAILURE",
        message="Something went wrong while saving your data. Please try again.",
    )


def internal_error() -> ApiError:
    return ApiError(
        status_code=500,
        code="INTERNAL_ERROR",
        message="Something went wrong on our side. Please try again.",
    )


def _request_id(request: Request) -> str:
    return str(uuid.uuid4())


def _body(error: ApiError, request: Request) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": error.code, "message": error.message}
    if error.details:
        payload["details"] = error.details
    if error.status_code >= 500:
        payload.setdefault("details", {})
        payload["details"]["request_id"] = _request_id(request)
    return {"error": payload}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        headers = {"X-Request-Id": _request_id(request)}
        if exc.code == "AUTHENTICATION_ERROR":
            # Frozen contract (API-7, ERROR_HANDLING §5.2): every 401
            # carries the Bearer challenge.
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc, request),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        field_errors: list[dict[str, Any]] = []
        for err in exc.errors():
            item: dict[str, Any] = {
                "field": ".".join(str(part) for part in (err.get("loc") or [])[1:]),
                "error": err.get("msg", "invalid value"),
            }
            if err.get("ctx") is not None:
                if err.get("type") == "enum":
                    item["allowed"] = err["ctx"].get("expected")
            field_errors.append(item)
        error = validation(field_errors)
        return JSONResponse(
            status_code=error.status_code,
            content=_body(error, request),
            headers={"X-Request-Id": _request_id(request)},
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        error = internal_error()
        return JSONResponse(
            status_code=error.status_code,
            content=_body(error, request),
            headers={"X-Request-Id": _request_id(request)},
        )
