"""Genlook Commercial Virtual Try-On API Adapter (Phase 5F).

Integrates the official Genlook Try-On API (https://api.genlook.app/tryon/v1)
behind Fansivibe's ``TryOnProvider`` port.

API Workflow:
1. ``POST /images/upload`` (multipart ``file``) -> ``imageId`` (reusable within retention)
2. ``POST /try-on`` (JSON ``products`` + ``person.image.source.id`` + ``Idempotency-Key``) -> ``generationId``
3. ``GET /generations/{generationId}`` (bounded polling) -> ``COMPLETED`` + temporary ``resultImageUrl``
4. Server-side download & Pillow validation of ``resultImageUrl`` bytes (never stored permanently)

Security & Privacy:
- ``GENLOOK_API_KEY`` is passed exclusively via ``x-api-key`` to Genlook API endpoints
  (never to third-party result image CDN URLs, never logged, never in exceptions or repr).
- Person images are validated (MIME, magic bytes, Pillow decode, <= 10 MB) before upload.
- Genlook retention is bounded (``keepForDays`` in {1, 3, 7}, default 1 day; Genlook max 7 days).
- ``aiLabel`` transparency marking defaults to enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import logging
import re
import time
from typing import Any, Callable
from urllib.parse import quote, urlparse
from uuid import uuid4

import httpx

from app.domain.ports.tryon_provider import (
    CommercialProviderConfigurationError,
    ProviderAuthError,
    ProviderPayloadError,
    ProviderQuotaExceededError,
    ProviderTransientError,
    TryOnProviderError,
    validate_raster_image_bytes,
)

logger = logging.getLogger("fansivibe.tryon.genlook")

GENLOOK_DEFAULT_BASE_URL = "https://api.genlook.app/tryon/v1"
GENLOOK_MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB Genlook upload limit
GENLOOK_MAX_RESULT_BYTES = 20 * 1024 * 1024  # 20 MB Fansivibe output ceiling
GENLOOK_ALLOWED_MIMES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

_GENLOOK_SECRET_RE = re.compile(r"\bgk_[A-Za-z0-9_\-\.]{4,}\b")
_HEADER_KEY_RE = re.compile(r"(x-api-key[:=]\s*)([^\s,;]+)", re.IGNORECASE)


def sanitize_genlook_text(text: str, api_key: str | None = None) -> str:
    """Strip any API key or x-api-key header material from log/error strings."""
    if not text:
        return ""
    sanitized = text
    if api_key and api_key.strip():
        sanitized = sanitized.replace(api_key.strip(), "[REDACTED]")
    sanitized = _GENLOOK_SECRET_RE.sub("[REDACTED]", sanitized)
    sanitized = _HEADER_KEY_RE.sub(r"\1[REDACTED]", sanitized)
    return sanitized


class GenlookCancelledError(TryOnProviderError):
    """Raised when a job is cancelled while polling Genlook."""


class GenlookImageExpiredError(ProviderPayloadError):
    """Raised when a reused Genlook imageId is no longer valid/found."""


@dataclass(frozen=True)
class GenlookTryOnConfig:
    """Configuration for Genlook commercial VTON provider."""

    api_key: str
    base_url: str = GENLOOK_DEFAULT_BASE_URL
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 30.0
    poll_interval_s: float = 1.0
    poll_timeout_s: float = 120.0
    max_retries: int = 2
    backoff_factor: float = 1.5
    keep_for_days: int = 1
    ai_label: bool = True
    allow_insecure_urls: bool = False

    def __repr__(self) -> str:
        key = self.api_key or ""
        masked = key[:4] + "..." + key[-4:] if len(key) > 8 else "[REDACTED]"
        return (
            f"GenlookTryOnConfig(base_url={self.base_url!r}, "
            f"api_key={masked!r}, poll_timeout_s={self.poll_timeout_s}, "
            f"keep_for_days={self.keep_for_days})"
        )


@dataclass(frozen=True)
class GenlookProductSpec:
    """Inline garment specification formatted for Genlook ``POST /try-on``."""

    external_id: str
    title: str
    description: str
    image_url: str


@dataclass(frozen=True)
class GenlookImageUploadResult:
    """Response metadata from ``POST /images/upload``."""

    image_id: str
    keep_for_days: int
    request_id: str | None = None


@dataclass(frozen=True)
class GenlookTryOnCreateResult:
    """Response metadata from ``POST /try-on``."""

    generation_id: str
    status: str
    product_external_ids: tuple[str, ...] = ()
    request_id: str | None = None
    idempotency_replayed: bool = False
    rate_limit_limit: int | None = None
    rate_limit_remaining: int | None = None


@dataclass(frozen=True)
class GenlookGenerationStatus:
    """Normalized response from ``GET /generations/{generationId}``."""

    generation_id: str
    status: str
    result_image_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    request_id: str | None = None


def build_genlook_product_spec(
    *,
    item_id: str,
    name: str,
    category: str | None = None,
    color: str | None = None,
    material: str | None = None,
    fit: str | None = None,
    image_url: str,
) -> GenlookProductSpec:
    """Build a factual Genlook inline product payload from wardrobe metadata."""
    clean_id = (item_id or "").strip()
    if not clean_id:
        raise ProviderPayloadError(
            "Wardrobe garment ID is required for Genlook try-on",
            provider_id="genlook",
        )
    if clean_id.startswith("_anon_"):
        raise ProviderPayloadError(
            "Reserved externalId prefix '_anon_' cannot be used",
            provider_id="genlook",
        )
    clean_title = (name or "").strip()[:200] or f"Wardrobe item {clean_id}"
    parts: list[str] = []
    if category and category.strip():
        parts.append(f"Category: {category.strip()}")
    if color and color.strip():
        parts.append(f"Color: {color.strip()}")
    if material and material.strip():
        parts.append(f"Material: {material.strip()}")
    if fit and fit.strip():
        parts.append(f"Fit: {fit.strip()}")
    description = ". ".join(parts) if parts else clean_title
    return GenlookProductSpec(
        external_id=clean_id,
        title=clean_title,
        description=description[:500],
        image_url=image_url,
    )


def _parse_int_header(headers: Any, name: str) -> int | None:
    if not headers:
        return None
    val = headers.get(name)
    if val is None and hasattr(headers, "items"):
        lower_name = name.lower()
        for k, v in headers.items():
            if str(k).lower() == lower_name:
                val = v
                break
    if val is None:
        return None
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return None


def _parse_retry_after(headers: Any, details: dict[str, Any] | None = None) -> float | None:
    if headers:
        raw = headers.get("retry-after") or headers.get("Retry-After")
        if raw is not None:
            try:
                return max(0.1, float(str(raw).strip()))
            except (TypeError, ValueError):
                pass
    if isinstance(details, dict) and details.get("retryAfter") is not None:
        try:
            return max(0.1, float(details["retryAfter"]))
        except (TypeError, ValueError):
            pass
    return None


def _is_valid_http_url(url: str, *, allow_http: bool) -> bool:
    if not url or not isinstance(url, str):
        return False
    lower = url.strip().lower()
    if lower.startswith("https://"):
        return True
    if allow_http and lower.startswith("http://"):
        return True
    return False


def _is_safe_result_url(url: str, *, allow_http: bool) -> bool:
    """Validate untrusted provider resultImageUrl against SSRF and unsafe schemes."""
    if not _is_valid_http_url(url, allow_http=allow_http):
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    if parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    if not allow_http:
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            ip_obj = ipaddress.ip_address(host)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_multicast
                or ip_obj.is_reserved
                or ip_obj.is_unspecified
            ):
                return False
        except ValueError:
            pass
    return True


class GenlookTryOnProvider:
    """Genlook Commercial Virtual Try-On API provider implementing ``TryOnProvider``."""

    provider_id = "genlook"

    def __init__(
        self,
        config: GenlookTryOnConfig,
        *,
        http_client: Any = None,
    ) -> None:
        if not config.api_key or not config.api_key.strip():
            raise CommercialProviderConfigurationError(
                "Genlook try-on provider requires a non-empty GENLOOK_API_KEY",
                provider_id=self.provider_id,
            )
        if not config.base_url or not config.base_url.strip():
            raise CommercialProviderConfigurationError(
                "Genlook try-on provider requires a non-empty base_url",
                provider_id=self.provider_id,
            )
        if config.keep_for_days not in (1, 3, 7):
            raise CommercialProviderConfigurationError(
                "Genlook keep_for_days must be 1, 3, or 7",
                provider_id=self.provider_id,
            )
        self.config = config
        self._base_url = config.base_url.rstrip("/")
        self._http_client = http_client

    @property
    def _allow_http_urls(self) -> bool:
        return self.config.allow_insecure_urls or self._base_url.lower().startswith("http://")

    def _auth_headers(self, correlation_id: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "x-api-key": self.config.api_key.strip(),
            "X-Correlation-ID": correlation_id,
        }
        if extra:
            headers.update(extra)
        return headers

    def _extract_error(self, resp: Any) -> tuple[str | None, str, dict[str, Any] | None]:
        code: str | None = None
        message = f"HTTP {getattr(resp, 'status_code', 'unknown')}"
        details: dict[str, Any] | None = None
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                raw_code = payload.get("code") or payload.get("errorCode")
                if raw_code:
                    code = str(raw_code).strip()
                raw_msg = payload.get("message") or payload.get("errorMessage")
                if raw_msg:
                    message = str(raw_msg)
                if isinstance(payload.get("details"), dict):
                    details = payload["details"]
        except Exception:
            pass
        safe_msg = sanitize_genlook_text(message, self.config.api_key)
        return code, safe_msg, details

    def _raise_for_http_error(self, resp: Any, correlation_id: str) -> None:
        status_code = int(getattr(resp, "status_code", 0))
        code, safe_msg, details = self._extract_error(resp)
        headers = getattr(resp, "headers", None) or {}
        retry_after = _parse_retry_after(headers, details)

        if status_code in (401, 403):
            err = ProviderAuthError(
                f"Genlook authentication failed ({code or status_code})",
                provider_id=self.provider_id,
                correlation_id=correlation_id,
            )
            err.provider_error_code = code  # type: ignore[attr-defined]
            raise err

        if status_code == 402 or code in (
            "INSUFFICIENT_CREDITS",
            "API_KEY_LIMIT_REACHED",
            "QUOTA_EXCEEDED",
        ):
            err = ProviderQuotaExceededError(
                f"Genlook credit or quota limit reached ({code or 'HTTP_402'}): {safe_msg}",
                provider_id=self.provider_id,
                correlation_id=correlation_id,
            )
            err.provider_error_code = code or "INSUFFICIENT_CREDITS"  # type: ignore[attr-defined]
            raise err

        if status_code == 429 or code == "RATE_LIMITED":
            err = ProviderQuotaExceededError(
                f"Genlook rate limit exceeded (HTTP 429): {safe_msg}",
                provider_id=self.provider_id,
                correlation_id=correlation_id,
            )
            err.provider_error_code = code or "RATE_LIMITED"  # type: ignore[attr-defined]
            err.retry_after_s = retry_after  # type: ignore[attr-defined]
            raise err

        if status_code == 409 and code == "IDEMPOTENCY_IN_PROGRESS":
            err = ProviderTransientError(
                "Genlook generation with this Idempotency-Key is still in progress",
                provider_id=self.provider_id,
                correlation_id=correlation_id,
            )
            err.provider_error_code = code  # type: ignore[attr-defined]
            err.retry_after_s = retry_after or 5.0  # type: ignore[attr-defined]
            raise err

        if status_code in (400, 404, 409, 413, 422):
            if code in ("CUSTOMER_IMAGE_NOT_FOUND", "IMAGE_NOT_FOUND") or (
                status_code == 404 and "image" in safe_msg.lower()
            ):
                err = GenlookImageExpiredError(
                    f"Genlook image reference expired or missing ({code or status_code})",
                    provider_id=self.provider_id,
                    correlation_id=correlation_id,
                )
            else:
                err = ProviderPayloadError(
                    f"Genlook rejected request ({code or status_code}): {safe_msg}",
                    provider_id=self.provider_id,
                    correlation_id=correlation_id,
                )
            err.provider_error_code = code  # type: ignore[attr-defined]
            raise err

        if status_code in (408, 500, 502, 503, 504):
            err = ProviderTransientError(
                f"Genlook transient server error ({code or status_code})",
                provider_id=self.provider_id,
                correlation_id=correlation_id,
            )
            err.provider_error_code = code  # type: ignore[attr-defined]
            err.retry_after_s = retry_after  # type: ignore[attr-defined]
            raise err

        raise TryOnProviderError(
            f"Genlook returned unexpected HTTP {status_code}: {safe_msg}",
            provider_id=self.provider_id,
            correlation_id=correlation_id,
        )

    def _send(
        self,
        method: str,
        url: str,
        *,
        timeout: httpx.Timeout,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        if self._http_client is not None:
            fn = getattr(self._http_client, method.lower())
            return fn(url, headers=headers, timeout=timeout, **kwargs)
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            fn = getattr(client, method.lower())
            return fn(url, headers=headers, **kwargs)

    def upload_person_image(
        self,
        *,
        person_bytes: bytes,
        mime_type: str | None = None,
        filename: str | None = None,
        external_user_id: str | None = None,
        crop: bool = True,
        keep_for_days: int | None = None,
        correlation_id: str | None = None,
    ) -> GenlookImageUploadResult:
        """Upload customer person photo to ``POST /images/upload`` and return ``imageId``."""
        corr_id = correlation_id or str(uuid4())
        if not person_bytes:
            raise ProviderPayloadError(
                "Person image payload is empty",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )
        if len(person_bytes) > GENLOOK_MAX_IMAGE_BYTES:
            raise ProviderPayloadError(
                f"Person image exceeds Genlook 10 MB upload limit ({len(person_bytes)} bytes)",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )

        detected_mime = validate_raster_image_bytes(
            person_bytes,
            "Person image",
            correlation_id=corr_id,
            provider_id=self.provider_id,
        )
        if detected_mime not in GENLOOK_ALLOWED_MIMES:
            raise ProviderPayloadError(
                f"Unsupported person image MIME type for Genlook: {detected_mime!r}",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )
        if mime_type:
            declared = mime_type.split(";")[0].strip().lower()
            if declared != detected_mime:
                raise ProviderPayloadError(
                    f"Declared MIME {declared!r} does not match image content {detected_mime!r}",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                )

        effective_days = keep_for_days if keep_for_days is not None else self.config.keep_for_days
        if effective_days not in (1, 3, 7):
            raise ProviderPayloadError(
                f"Genlook keepForDays must be 1, 3, or 7 (got {effective_days!r})",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )

        ext = _MIME_TO_EXT[detected_mime]
        upload_name = filename or f"person.{ext}"
        form_data: dict[str, str] = {
            "crop": "true" if crop else "false",
            "keepForDays": str(effective_days),
        }
        if external_user_id and external_user_id.strip():
            form_data["externalUserId"] = external_user_id.strip()

        timeout = httpx.Timeout(
            timeout=self.config.request_timeout_s,
            connect=self.config.connect_timeout_s,
        )
        url = f"{self._base_url}/images/upload"

        attempts = 0
        last_exc: Exception | None = None
        while attempts <= self.config.max_retries:
            attempts += 1
            try:
                resp = self._send(
                    "POST",
                    url,
                    timeout=timeout,
                    headers=self._auth_headers(corr_id),
                    files={"file": (upload_name, person_bytes, detected_mime)},
                    data=form_data,
                )
                status_code = int(resp.status_code)
                if status_code in (200, 201):
                    body = resp.json()
                    image_id = body.get("imageId") if isinstance(body, dict) else None
                    if not isinstance(image_id, str) or not image_id.strip():
                        raise ProviderPayloadError(
                            "Genlook upload response missing valid imageId",
                            provider_id=self.provider_id,
                            correlation_id=corr_id,
                        )
                    req_id = (getattr(resp, "headers", None) or {}).get("x-request-id")
                    logger.info(
                        "Genlook person image uploaded (correlation_id=%s, bytes=%d, mime=%s, keep_days=%d, req_id=%s)",
                        corr_id,
                        len(person_bytes),
                        detected_mime,
                        effective_days,
                        req_id,
                    )
                    return GenlookImageUploadResult(
                        image_id=image_id.strip(),
                        keep_for_days=effective_days,
                        request_id=req_id,
                    )

                self._raise_for_http_error(resp, corr_id)
            except (ProviderAuthError, ProviderPayloadError):
                raise
            except ProviderQuotaExceededError as exc:
                retry_after = getattr(exc, "retry_after_s", None)
                is_rate_limit = getattr(exc, "provider_error_code", None) == "RATE_LIMITED"
                if is_rate_limit and retry_after and retry_after <= 5.0 and attempts <= self.config.max_retries:
                    last_exc = exc
                    time.sleep(retry_after)
                    continue
                raise
            except (ProviderTransientError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempts <= self.config.max_retries:
                    delay = self.config.backoff_factor ** attempts
                    logger.warning(
                        "Genlook upload transient failure (%s); retrying %d/%d in %.1fs",
                        type(exc).__name__,
                        attempts,
                        self.config.max_retries,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    break
            except Exception as exc:
                raise TryOnProviderError(
                    f"Unexpected Genlook upload error: {sanitize_genlook_text(str(exc), self.config.api_key)}",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                    cause=exc,
                )

        raise ProviderTransientError(
            f"Genlook image upload failed after {attempts} attempts: {type(last_exc).__name__}",
            provider_id=self.provider_id,
            correlation_id=corr_id,
            cause=last_exc,
        )

    def create_tryon(
        self,
        *,
        image_id: str,
        product: GenlookProductSpec,
        idempotency_key: str,
        external_user_id: str | None = None,
        ai_label: bool | None = None,
        correlation_id: str | None = None,
    ) -> GenlookTryOnCreateResult:
        """Submit a single-garment try-on request to ``POST /try-on`` with Idempotency-Key."""
        corr_id = correlation_id or str(uuid4())
        if not image_id or not image_id.strip():
            raise ProviderPayloadError(
                "Genlook try-on requires a valid uploaded imageId",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )
        if not _is_valid_http_url(product.image_url, allow_http=self._allow_http_urls):
            raise ProviderPayloadError(
                "Genlook try-on requires a valid product signed image URL",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )
        clean_idem = (idempotency_key or "").strip()
        if not clean_idem or len(clean_idem) > 255 or not clean_idem.isascii():
            raise ProviderPayloadError(
                "Genlook Idempotency-Key must be 1..255 ASCII characters",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )

        body: dict[str, Any] = {
            "products": [
                {
                    "externalId": product.external_id,
                    "title": product.title,
                    "description": product.description,
                    "images": [
                        {
                            "source": {
                                "url": product.image_url,
                            }
                        }
                    ],
                }
            ],
            "person": {
                "image": {
                    "source": {
                        "id": image_id.strip(),
                    }
                }
            },
            "output": {
                "aiLabel": self.config.ai_label if ai_label is None else bool(ai_label),
            },
        }
        if external_user_id and external_user_id.strip():
            body["externalUserId"] = external_user_id.strip()

        timeout = httpx.Timeout(
            timeout=self.config.request_timeout_s,
            connect=self.config.connect_timeout_s,
        )
        url = f"{self._base_url}/try-on"
        headers = self._auth_headers(corr_id, {"Idempotency-Key": clean_idem})

        attempts = 0
        last_exc: Exception | None = None
        while attempts <= self.config.max_retries:
            attempts += 1
            try:
                resp = self._send(
                    "POST",
                    url,
                    timeout=timeout,
                    headers=headers,
                    json=body,
                )
                status_code = int(resp.status_code)
                if status_code in (200, 201):
                    data = resp.json()
                    gen_id = data.get("generationId") if isinstance(data, dict) else None
                    if not isinstance(gen_id, str) or not gen_id.strip():
                        raise ProviderPayloadError(
                            "Genlook try-on response missing generationId",
                            provider_id=self.provider_id,
                            correlation_id=corr_id,
                        )
                    resp_headers = getattr(resp, "headers", None) or {}
                    ext_ids = data.get("productExternalIds") or []
                    if not isinstance(ext_ids, list):
                        ext_ids = []
                    result = GenlookTryOnCreateResult(
                        generation_id=gen_id.strip(),
                        status=str(data.get("status") or "PENDING").upper(),
                        product_external_ids=tuple(str(x) for x in ext_ids),
                        request_id=resp_headers.get("x-request-id"),
                        idempotency_replayed=str(
                            resp_headers.get("Idempotency-Replayed")
                            or resp_headers.get("idempotency-replayed")
                            or ""
                        ).lower()
                        == "true",
                        rate_limit_limit=_parse_int_header(resp_headers, "X-RateLimit-Limit")
                        or _parse_int_header(resp_headers, "x-ratelimit-limit"),
                        rate_limit_remaining=_parse_int_header(resp_headers, "X-RateLimit-Remaining")
                        or _parse_int_header(resp_headers, "x-ratelimit-remaining"),
                    )
                    logger.info(
                        "Genlook try-on created (correlation_id=%s, generation_id=%s, status=%s, replayed=%s, rl_remaining=%s)",
                        corr_id,
                        result.generation_id,
                        result.status,
                        result.idempotency_replayed,
                        result.rate_limit_remaining,
                    )
                    return result

                self._raise_for_http_error(resp, corr_id)
            except (ProviderAuthError, ProviderPayloadError):
                raise
            except ProviderQuotaExceededError as exc:
                retry_after = getattr(exc, "retry_after_s", None)
                is_rate_limit = getattr(exc, "provider_error_code", None) == "RATE_LIMITED"
                if is_rate_limit and retry_after and retry_after <= 5.0 and attempts <= self.config.max_retries:
                    last_exc = exc
                    time.sleep(retry_after)
                    continue
                raise
            except (ProviderTransientError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempts <= self.config.max_retries:
                    delay = getattr(exc, "retry_after_s", None) or (self.config.backoff_factor ** attempts)
                    logger.warning(
                        "Genlook try-on transient failure (%s); retrying with same Idempotency-Key %d/%d in %.1fs",
                        type(exc).__name__,
                        attempts,
                        self.config.max_retries,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    break
            except Exception as exc:
                raise TryOnProviderError(
                    f"Unexpected Genlook try-on creation error: {sanitize_genlook_text(str(exc), self.config.api_key)}",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                    cause=exc,
                )

        raise ProviderTransientError(
            f"Genlook try-on creation failed after {attempts} attempts: {type(last_exc).__name__}",
            provider_id=self.provider_id,
            correlation_id=corr_id,
            cause=last_exc,
        )

    def get_generation_status(
        self,
        generation_id: str,
        *,
        correlation_id: str | None = None,
    ) -> GenlookGenerationStatus:
        """Fetch current status from ``GET /generations/{generationId}``."""
        corr_id = correlation_id or str(uuid4())
        clean_gid = (generation_id or "").strip()
        if not clean_gid:
            raise ProviderPayloadError(
                "generationId is required for Genlook status polling",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )

        timeout = httpx.Timeout(
            timeout=self.config.request_timeout_s,
            connect=self.config.connect_timeout_s,
        )
        url = f"{self._base_url}/generations/{clean_gid}"
        try:
            resp = self._send(
                "GET",
                url,
                timeout=timeout,
                headers=self._auth_headers(corr_id),
            )
            if int(resp.status_code) == 200:
                data = resp.json()
                if not isinstance(data, dict):
                    raise ProviderPayloadError(
                        "Genlook generation status response is not a JSON object",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                status = str(data.get("status") or "").strip().upper()
                if not status:
                    raise ProviderPayloadError(
                        "Genlook generation status response missing status",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                req_id = (getattr(resp, "headers", None) or {}).get("x-request-id")
                return GenlookGenerationStatus(
                    generation_id=str(data.get("generationId") or clean_gid),
                    status=status,
                    result_image_url=data.get("resultImageUrl"),
                    error_code=data.get("errorCode"),
                    error_message=sanitize_genlook_text(
                        str(data.get("errorMessage") or ""), self.config.api_key
                    )
                    or None,
                    created_at=data.get("createdAt"),
                    updated_at=data.get("updatedAt"),
                    request_id=req_id,
                )

            self._raise_for_http_error(resp, corr_id)
        except (ProviderAuthError, ProviderPayloadError, ProviderQuotaExceededError, ProviderTransientError):
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderTransientError(
                f"Genlook status poll network error: {type(exc).__name__}",
                provider_id=self.provider_id,
                correlation_id=corr_id,
                cause=exc,
            )
        except Exception as exc:
            raise TryOnProviderError(
                f"Unexpected Genlook status poll error: {sanitize_genlook_text(str(exc), self.config.api_key)}",
                provider_id=self.provider_id,
                correlation_id=corr_id,
                cause=exc,
            )

        raise TryOnProviderError(
            "Unreachable Genlook status branch",
            provider_id=self.provider_id,
            correlation_id=corr_id,
        )

    def _map_failed_generation(
        self,
        status: GenlookGenerationStatus,
        correlation_id: str,
    ) -> TryOnProviderError:
        err_code = (status.error_code or "GENERATION_FAILED").strip().upper()
        safe_msg = sanitize_genlook_text(
            status.error_message or "Genlook generation failed",
            self.config.api_key,
        )
        if err_code in ("INSUFFICIENT_CREDITS", "API_KEY_LIMIT_REACHED", "QUOTA_EXCEEDED"):
            err: TryOnProviderError = ProviderQuotaExceededError(
                f"Genlook generation failed ({err_code}): {safe_msg}",
                provider_id=self.provider_id,
                correlation_id=correlation_id,
            )
        elif err_code in (
            "PRODUCT_IMAGE_FETCH_FAILED",
            "MISSING_REQUIRED_CLASSIFICATION",
            "CONTENT_POLICY_VIOLATION",
            "MULTI_PRODUCT_NOT_SUPPORTED",
            "VALIDATION_FAILED",
        ) or err_code.startswith("PERSON_") or err_code == "NO_PERSON_DETECTED":
            err = ProviderPayloadError(
                f"Genlook generation rejected ({err_code}): {safe_msg}",
                provider_id=self.provider_id,
                correlation_id=correlation_id,
            )
        else:
            err = ProviderTransientError(
                f"Genlook generation failed ({err_code}): {safe_msg}",
                provider_id=self.provider_id,
                correlation_id=correlation_id,
            )
        err.provider_error_code = err_code  # type: ignore[attr-defined]
        return err

    def poll_generation(
        self,
        generation_id: str,
        *,
        is_cancelled_fn: Callable[[], bool] | None = None,
        correlation_id: str | None = None,
    ) -> GenlookGenerationStatus:
        """Poll ``GET /generations/{generationId}`` until terminal state or bounded timeout."""
        corr_id = correlation_id or str(uuid4())
        deadline = time.monotonic() + self.config.poll_timeout_s
        interval = max(0.01, self.config.poll_interval_s)
        max_polls = max(3, int(self.config.poll_timeout_s / interval) + 5)
        consecutive_transient = 0
        max_consecutive_transient = 5

        for _ in range(max_polls):
            if is_cancelled_fn is not None and is_cancelled_fn():
                raise GenlookCancelledError(
                    "Genlook try-on job cancelled during polling",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                )

            try:
                gen_status = self.get_generation_status(
                    generation_id, correlation_id=corr_id
                )
                consecutive_transient = 0
            except ProviderQuotaExceededError as exc:
                is_rate_limit = getattr(exc, "provider_error_code", None) == "RATE_LIMITED"
                if not is_rate_limit:
                    raise
                consecutive_transient += 1
                if consecutive_transient > max_consecutive_transient:
                    raise
                wait_s = min(
                    getattr(exc, "retry_after_s", None) or interval,
                    max(0.0, deadline - time.monotonic()),
                )
                if wait_s <= 0:
                    break
                time.sleep(wait_s)
                continue
            except ProviderTransientError:
                consecutive_transient += 1
                if consecutive_transient > max_consecutive_transient:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(interval, remaining))
                continue

            if gen_status.status == "COMPLETED":
                if not gen_status.result_image_url or not _is_safe_result_url(
                    gen_status.result_image_url, allow_http=self._allow_http_urls
                ):
                    raise ProviderPayloadError(
                        "Genlook COMPLETED generation missing valid resultImageUrl",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                return gen_status

            if gen_status.status == "FAILED":
                raise self._map_failed_generation(gen_status, corr_id)

            if gen_status.status not in ("PENDING", "PROCESSING", "RUNNING"):
                raise ProviderPayloadError(
                    f"Genlook returned unknown generation status: {gen_status.status!r}",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))

        raise ProviderTransientError(
            f"Genlook generation {generation_id} timed out after {self.config.poll_timeout_s:.1f}s",
            provider_id=self.provider_id,
            correlation_id=corr_id,
        )

    def download_result_image(
        self,
        result_image_url: str,
        *,
        correlation_id: str | None = None,
    ) -> bytes:
        """Download temporary Genlook resultImageUrl server-side and validate raster pixels."""
        corr_id = correlation_id or str(uuid4())
        if not _is_safe_result_url(result_image_url, allow_http=self._allow_http_urls):
            err = ProviderPayloadError(
                "Genlook resultImageUrl is missing or failed URL safety validation",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )
            err.provider_error_code = "RESULT_DOWNLOAD_REJECTED"  # type: ignore[attr-defined]
            raise err

        timeout = httpx.Timeout(
            timeout=self.config.request_timeout_s,
            connect=self.config.connect_timeout_s,
        )
        # Never forward Genlook API key to third-party signed result URLs
        headers = {"Accept": "image/*"}

        try:
            if self._http_client is not None:
                resp = self._send("GET", result_image_url, timeout=timeout, headers=headers)
                status_code = int(resp.status_code)
                if status_code != 200:
                    if status_code in (408, 500, 502, 503, 504):
                        err_t = ProviderTransientError(
                            f"Failed to download Genlook result image (HTTP {status_code})",
                            provider_id=self.provider_id,
                            correlation_id=corr_id,
                        )
                        err_t.provider_error_code = "RESULT_DOWNLOAD_TRANSIENT"  # type: ignore[attr-defined]
                        raise err_t
                    err_p = ProviderPayloadError(
                        f"Genlook result image download rejected (HTTP {status_code})",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                    err_p.provider_error_code = "RESULT_DOWNLOAD_REJECTED"  # type: ignore[attr-defined]
                    raise err_p

                content_len = _parse_int_header(getattr(resp, "headers", None), "content-length")
                if content_len is not None and content_len > GENLOOK_MAX_RESULT_BYTES:
                    err_p = ProviderPayloadError(
                        f"Genlook result image size out of bounds ({content_len} bytes)",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                    err_p.provider_error_code = "RESULT_DOWNLOAD_REJECTED"  # type: ignore[attr-defined]
                    raise err_p

                raw_bytes = resp.content
            else:
                chunks: list[bytes] = []
                total_read = 0
                with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                    with client.stream("GET", result_image_url, headers=headers) as resp:
                        status_code = int(resp.status_code)
                        if status_code != 200:
                            if status_code in (408, 500, 502, 503, 504):
                                err_t = ProviderTransientError(
                                    f"Failed to download Genlook result image (HTTP {status_code})",
                                    provider_id=self.provider_id,
                                    correlation_id=corr_id,
                                )
                                err_t.provider_error_code = "RESULT_DOWNLOAD_TRANSIENT"  # type: ignore[attr-defined]
                                raise err_t
                            err_p = ProviderPayloadError(
                                f"Genlook result image download rejected (HTTP {status_code})",
                                provider_id=self.provider_id,
                                correlation_id=corr_id,
                            )
                            err_p.provider_error_code = "RESULT_DOWNLOAD_REJECTED"  # type: ignore[attr-defined]
                            raise err_p

                        content_len = _parse_int_header(resp.headers, "content-length")
                        if content_len is not None and content_len > GENLOOK_MAX_RESULT_BYTES:
                            err_p = ProviderPayloadError(
                                f"Genlook result image size out of bounds ({content_len} bytes)",
                                provider_id=self.provider_id,
                                correlation_id=corr_id,
                            )
                            err_p.provider_error_code = "RESULT_DOWNLOAD_REJECTED"  # type: ignore[attr-defined]
                            raise err_p

                        for chunk in resp.iter_bytes():
                            total_read += len(chunk)
                            if total_read > GENLOOK_MAX_RESULT_BYTES:
                                err_p = ProviderPayloadError(
                                    f"Genlook result image size out of bounds (>{GENLOOK_MAX_RESULT_BYTES} bytes)",
                                    provider_id=self.provider_id,
                                    correlation_id=corr_id,
                                )
                                err_p.provider_error_code = "RESULT_DOWNLOAD_REJECTED"  # type: ignore[attr-defined]
                                raise err_p
                            chunks.append(chunk)
                raw_bytes = b"".join(chunks)

            if not raw_bytes or len(raw_bytes) > GENLOOK_MAX_RESULT_BYTES:
                err_p = ProviderPayloadError(
                    f"Genlook result image size out of bounds ({len(raw_bytes) if raw_bytes else 0} bytes)",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                )
                err_p.provider_error_code = "RESULT_DOWNLOAD_REJECTED"  # type: ignore[attr-defined]
                raise err_p
            validate_raster_image_bytes(
                raw_bytes,
                "Genlook result image",
                correlation_id=corr_id,
                provider_id=self.provider_id,
            )
            return raw_bytes
        except ProviderPayloadError as exc:
            if not getattr(exc, "provider_error_code", None):
                exc.provider_error_code = "RESULT_DOWNLOAD_REJECTED"  # type: ignore[attr-defined]
            raise
        except ProviderTransientError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            err_t = ProviderTransientError(
                f"Genlook result image download network error: {type(exc).__name__}",
                provider_id=self.provider_id,
                correlation_id=corr_id,
                cause=exc,
            )
            err_t.provider_error_code = "RESULT_DOWNLOAD_TRANSIENT"  # type: ignore[attr-defined]
            raise err_t
        except Exception as exc:
            raise TryOnProviderError(
                f"Unexpected Genlook result download error: {type(exc).__name__}",
                provider_id=self.provider_id,
                correlation_id=corr_id,
                cause=exc,
            )

    def delete_customer(
        self,
        external_user_id: str,
        *,
        correlation_id: str | None = None,
    ) -> bool:
        """Delete customer images and references via ``DELETE /customers/{externalUserId}``.

        Returns True if deleted (HTTP 200/204), False if already absent (HTTP 404).
        Retries bounded transient/rate-limit errors; raises TryOnProviderError on failure.
        """
        corr_id = correlation_id or str(uuid4())
        clean_uid = (external_user_id or "").strip()
        if not clean_uid:
            raise ProviderPayloadError(
                "externalUserId is required for Genlook customer deletion",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )

        timeout = httpx.Timeout(
            timeout=self.config.request_timeout_s,
            connect=self.config.connect_timeout_s,
        )
        encoded_uid = quote(clean_uid, safe="")
        url = f"{self._base_url}/customers/{encoded_uid}"

        attempts = 0
        last_exc: Exception | None = None
        while attempts <= self.config.max_retries:
            attempts += 1
            try:
                resp = self._send(
                    "DELETE",
                    url,
                    timeout=timeout,
                    headers=self._auth_headers(corr_id),
                )
                status_code = int(resp.status_code)
                if status_code in (200, 204):
                    logger.info(
                        "Genlook customer data erased (correlation_id=%s, status=%d)",
                        corr_id,
                        status_code,
                    )
                    return True
                if status_code == 404:
                    logger.info(
                        "Genlook customer already absent (correlation_id=%s, status=404)",
                        corr_id,
                    )
                    return False

                self._raise_for_http_error(resp, corr_id)
            except (ProviderAuthError, ProviderPayloadError):
                raise
            except ProviderQuotaExceededError as exc:
                retry_after = getattr(exc, "retry_after_s", None)
                is_rate_limit = getattr(exc, "provider_error_code", None) == "RATE_LIMITED"
                if is_rate_limit and retry_after and retry_after <= 5.0 and attempts <= self.config.max_retries:
                    last_exc = exc
                    time.sleep(retry_after)
                    continue
                raise
            except (ProviderTransientError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempts <= self.config.max_retries:
                    delay = getattr(exc, "retry_after_s", None) or (self.config.backoff_factor ** attempts)
                    time.sleep(delay)
                else:
                    break
            except Exception as exc:
                raise TryOnProviderError(
                    f"Unexpected Genlook customer deletion error: {sanitize_genlook_text(str(exc), self.config.api_key)}",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                    cause=exc,
                )

        raise ProviderTransientError(
            f"Genlook customer deletion failed after {attempts} attempts: {type(last_exc).__name__}",
            provider_id=self.provider_id,
            correlation_id=corr_id,
            cause=last_exc,
        )

    def check_credits(self, *, correlation_id: str | None = None) -> int:
        """Query remaining credit balance from ``GET /account/credits``."""
        corr_id = correlation_id or str(uuid4())
        timeout = httpx.Timeout(timeout=5.0, connect=3.0)
        url = f"{self._base_url}/account/credits"
        resp = self._send("GET", url, timeout=timeout, headers=self._auth_headers(corr_id))
        if int(resp.status_code) == 200:
            data = resp.json()
            if isinstance(data, dict) and "creditBalance" in data:
                return int(data["creditBalance"])
            raise ProviderPayloadError(
                "Genlook credits response missing creditBalance",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )
        self._raise_for_http_error(resp, corr_id)
        return 0  # pragma: no cover

    def check_health(self) -> dict[str, Any]:
        """Operational health check verifying Genlook API key and credit endpoint reachability."""
        t0 = time.monotonic()
        try:
            credits_left = self.check_credits()
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            return {
                "provider": self.provider_id,
                "status": "healthy" if credits_left > 0 else "degraded",
                "latency_ms": latency_ms,
                "credit_balance": credits_left,
            }
        except ProviderAuthError:
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            return {
                "provider": self.provider_id,
                "status": "unavailable",
                "latency_ms": latency_ms,
                "error": "ProviderAuthError",
            }
        except Exception as exc:
            latency_ms = round((time.monotonic() - t0) * 1000, 2)
            return {
                "provider": self.provider_id,
                "status": "unavailable",
                "latency_ms": latency_ms,
                "error": type(exc).__name__,
            }

    def render(
        self,
        *,
        person_digest: str,
        garment_labels: list[str],
        seed: str,
        outfit_source: str,
        person_bytes: bytes | None = None,
        garment_bytes: bytes | None = None,
        category: str = "upper",
        correlation_id: str | None = None,
        job_id: str | None = None,
        person_image_url: str | None = None,
        garment_image_url: str | None = None,
        result_upload_url: str | None = None,
        is_cancelled_fn: Callable[[], bool] | None = None,
        **kwargs: Any,
    ) -> bytes:
        """Execute end-to-end Genlook VTON workflow conforming to ``TryOnProvider``."""
        corr_id = correlation_id or str(uuid4())
        existing_generation_id: str | None = kwargs.get("existing_generation_id")
        existing_image_id: str | None = kwargs.get("existing_image_id")
        idempotency_key: str = (
            kwargs.get("idempotency_key")
            or f"fv-tryon-{job_id or corr_id}"
        )
        external_user_id: str | None = kwargs.get("external_user_id")
        product_spec: GenlookProductSpec | None = kwargs.get("product_spec")
        on_image_uploaded: Callable[[GenlookImageUploadResult], None] | None = kwargs.get(
            "on_image_uploaded"
        )
        on_generation_created: Callable[[GenlookTryOnCreateResult], None] | None = kwargs.get(
            "on_generation_created"
        )

        if existing_generation_id and existing_generation_id.strip():
            gen_id = existing_generation_id.strip()
        else:
            if is_cancelled_fn is not None and is_cancelled_fn():
                raise GenlookCancelledError(
                    "Genlook try-on job cancelled before image upload",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                )
            if product_spec is None:
                if not garment_labels or len(garment_labels) != 1:
                    raise ProviderPayloadError(
                        "Genlook try-on requires exactly 1 garment",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                if not garment_image_url:
                    raise ProviderPayloadError(
                        "Genlook try-on requires a garment signed image URL",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                product_spec = build_genlook_product_spec(
                    item_id=garment_labels[0],
                    name=f"Garment {garment_labels[0]}",
                    category=category,
                    image_url=garment_image_url,
                )

            image_id = existing_image_id.strip() if isinstance(existing_image_id, str) and existing_image_id.strip() else None
            if image_id is None:
                if not person_bytes:
                    raise ProviderPayloadError(
                        "Genlook try-on requires person image bytes",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                upload_res = self.upload_person_image(
                    person_bytes=person_bytes,
                    external_user_id=external_user_id,
                    correlation_id=corr_id,
                )
                image_id = upload_res.image_id
                if on_image_uploaded is not None:
                    on_image_uploaded(upload_res)

            if is_cancelled_fn is not None and is_cancelled_fn():
                raise GenlookCancelledError(
                    "Genlook try-on job cancelled before generation creation",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                )

            try:
                create_res = self.create_tryon(
                    image_id=image_id,
                    product=product_spec,
                    idempotency_key=idempotency_key,
                    external_user_id=external_user_id,
                    correlation_id=corr_id,
                )
            except GenlookImageExpiredError:
                if is_cancelled_fn is not None and is_cancelled_fn():
                    raise GenlookCancelledError(
                        "Genlook try-on job cancelled before image re-upload",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                if not person_bytes:
                    raise
                upload_res = self.upload_person_image(
                    person_bytes=person_bytes,
                    external_user_id=external_user_id,
                    correlation_id=corr_id,
                )
                image_id = upload_res.image_id
                if on_image_uploaded is not None:
                    on_image_uploaded(upload_res)
                if is_cancelled_fn is not None and is_cancelled_fn():
                    raise GenlookCancelledError(
                        "Genlook try-on job cancelled before generation retry",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                create_res = self.create_tryon(
                    image_id=image_id,
                    product=product_spec,
                    idempotency_key=idempotency_key,
                    external_user_id=external_user_id,
                    correlation_id=corr_id,
                )

            if on_generation_created is not None:
                on_generation_created(create_res)
            gen_id = create_res.generation_id

        final_status = self.poll_generation(
            gen_id,
            is_cancelled_fn=is_cancelled_fn,
            correlation_id=corr_id,
        )
        return self.download_result_image(
            final_status.result_image_url or "",
            correlation_id=corr_id,
        )
