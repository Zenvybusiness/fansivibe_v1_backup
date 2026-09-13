"""API error mapping — the frozen 12-category contract.

Wire body: ``{ "error": { "code", "message", "details"? } }``
(`API_ERROR_CONTRACT.md` §5). Only allow-listed `details` reach the client
(ER-1); internals never leak (C-7/C-8).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("fansivibe.api.errors")

_DB_URL_PASSWORD_REGEX = re.compile(r"(://[^:]+:)([^@]+)(@)")
_BEARER_REGEX = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE)
_JWT_REGEX = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
_PARAM_SECRET_REGEX = re.compile(
    r"(password|secret|token|access_token|refresh_token|api_key)=([^&\s]+)",
    re.IGNORECASE,
)


def _sanitize_log_message(msg: str) -> str:
    """Scrub database passwords, Bearer tokens, JWTs, and credential params from log messages."""
    if not msg:
        return msg
    s = _DB_URL_PASSWORD_REGEX.sub(r"\1[REDACTED]\3", msg)
    s = _BEARER_REGEX.sub("Bearer [REDACTED]", s)
    s = _JWT_REGEX.sub("[REDACTED_JWT]", s)
    s = _PARAM_SECRET_REGEX.sub(r"\1=[REDACTED]", s)
    return s


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


def rate_limited(retry_after_s: int = 60) -> ApiError:
    """Truthful 429 for the local rate limiter (21.2).

    `retry_after_s` travels in `details` (non-sensitive, allow-listed
    shape) so honest clients can back off. Never carries identity,
    token, or request-body material.
    """
    try:
        retry = max(1, int(retry_after_s))
    except (TypeError, ValueError):
        retry = 60
    return ApiError(
        status_code=429,
        code="RATE_LIMITED",
        message="Too many requests. Please slow down and try again shortly.",
        details={"retry_after": retry},
    )


def internal_error() -> ApiError:
    return ApiError(
        status_code=500,
        code="INTERNAL_ERROR",
        message="Something went wrong on our side. Please try again.",
    )


def _request_id(request: Request) -> str:
    """Resolve and cache correlation ID for the lifetime of this request."""
    state = getattr(request, "state", None)
    if state is not None:
        existing = getattr(state, "request_id", None)
        if existing:
            return str(existing)
    header_id = request.headers.get("X-Request-Id")
    req_id = header_id if header_id else str(uuid.uuid4())
    if state is not None:
        try:
            state.request_id = req_id
        except Exception:
            pass
    return req_id


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
        req_id = _request_id(request)
        headers = {"X-Request-Id": req_id}
        if exc.code == "AUTHENTICATION_ERROR":
            # Frozen contract (API-7, ERROR_HANDLING §5.2): every 401
            # carries the Bearer challenge.
            headers["WWW-Authenticate"] = "Bearer"

        if exc.status_code >= 500:
            logger.error(
                "API 5xx error %s (%s) on %s %s [request_id=%s]: %s",
                exc.code,
                exc.status_code,
                request.method,
                request.url.path,
                req_id,
                _sanitize_log_message(exc.message),
            )
        elif exc.status_code >= 400:
            logger.info(
                "API 4xx error %s (%s) on %s %s [request_id=%s]",
                exc.code,
                exc.status_code,
                request.method,
                request.url.path,
                req_id,
            )

        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc, request),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = _request_id(request)
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
        logger.warning(
            "Validation error on %s %s [request_id=%s]: %s field errors",
            request.method,
            request.url.path,
            req_id,
            len(field_errors),
        )
        return JSONResponse(
            status_code=error.status_code,
            content=_body(error, request),
            headers={"X-Request-Id": req_id},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        req_id = _request_id(request)
        if exc.status_code == 404:
            err = not_found()
        elif exc.status_code == 405:
            err = ApiError(
                status_code=405,
                code="METHOD_NOT_ALLOWED",
                message="Method not allowed for this resource.",
            )
        elif exc.status_code == 401:
            err = authentication_error()
        elif exc.status_code >= 500:
            err = internal_error()
            logger.error(
                "HTTP 5xx error on %s %s [request_id=%s]: %s",
                request.method,
                request.url.path,
                req_id,
                _sanitize_log_message(str(exc.detail)),
            )
        else:
            err = ApiError(
                status_code=exc.status_code,
                code="HTTP_ERROR",
                message="A request error occurred. Please verify and try again.",
            )

        headers = {"X-Request-Id": req_id}
        if err.code == "AUTHENTICATION_ERROR":
            headers["WWW-Authenticate"] = "Bearer"

        return JSONResponse(
            status_code=err.status_code,
            content=_body(err, request),
            headers=headers,
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        req_id = _request_id(request)
        error = internal_error()
        sanitized_exc = _sanitize_log_message(f"{type(exc).__name__}: {exc}")
        logger.error(
            "Unhandled server exception on %s %s [request_id=%s]: %s",
            request.method,
            request.url.path,
            req_id,
            sanitized_exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=error.status_code,
            content=_body(error, request),
            headers={"X-Request-Id": req_id},
        )
