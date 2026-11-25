#!/usr/bin/env python3
"""Safe live Cloudflare R2 connectivity verification script (Phase 5F.3A).

Reads configuration from gitignored ``backend/.env`` (via Pydantic ``Settings``),
verifies bucket connectivity, uploads a synthetic non-personal 64x64 WebP probe,
confirms private bucket enforcement (unsigned access blocked), verifies signed GET
URL generation, expiration configuration, and content integrity, and deletes the
probe object with cleanup confirmation.

Safety guarantees:
- Zero real user photographs (synthetic solid-color Pillow image in memory only).
- Zero Genlook API calls or paid try-on credits consumed.
- Never prints credentials, access keys, secrets, complete signed URLs, or
  sensitive headers (``X-Amz-Signature``, ``X-Amz-Credential``, etc.).

Exit codes:
- 0: PASS (live R2 round-trip and cleanup verified)
- 1: FAIL (live R2 probe encountered an error)
- 2: BLOCKED (R2 provider/credentials not configured in ``backend/.env``)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import sys
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse
import uuid

import httpx
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import Settings  # noqa: E402
from app.domain.ports.storage import ObjectStoragePort, StoragePayloadError  # noqa: E402
from app.infrastructure.external.storage import (  # noqa: E402
    CloudflareR2StorageAdapter,
    _sanitize_message,
    create_storage_adapter,
)

PROBE_USER_ID = "00000000-0000-0000-0000-000000000000"
PROBE_SIGNED_TTL_S = 60
PROBE_GENLOOK_TTL_S = 300


@dataclass(frozen=True)
class ProbeResult:
    """Structured result of the live R2 connectivity probe (secret-free)."""

    status: str  # "PASS" | "FAIL" | "BLOCKED"
    exit_code: int
    summary: str
    bucket: str | None = None
    health: dict[str, Any] | None = None
    unsigned_status_code: int | None = None
    signed_status_code: int | None = None
    post_delete_status_code: int | None = None
    bytes_verified: int | None = None
    sha256: str | None = None
    missing_fields: tuple[str, ...] = ()


def _build_synthetic_webp_bytes() -> bytes:
    """Create a tiny synthetic non-personal 64x64 WebP image in memory."""
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (24, 96, 152)).save(buf, format="WEBP")
    return buf.getvalue()


def _load_settings_from_backend_env(env_path: Path | None = None) -> tuple[Settings | None, str | None]:
    """Load Settings from gitignored backend/.env without enabling Genlook."""
    target_env = env_path or (BACKEND_DIR / ".env")
    try:
        if target_env.exists():
            return Settings(_env_file=target_env), None
        return Settings(_env_file=None), None
    except Exception as exc:
        return None, _sanitize_message(f"{type(exc).__name__}: {exc}")


def _check_r2_readiness(settings: Settings) -> tuple[str, ...]:
    """Return missing configuration fields if R2 live testing is not yet enabled."""
    missing: list[str] = []
    if settings.media_storage_provider != "r2":
        missing.append("MEDIA_STORAGE_PROVIDER=r2")
    if not settings.r2_bucket_name:
        missing.append("R2_BUCKET_NAME")
    if not settings.r2_access_key_id:
        missing.append("R2_ACCESS_KEY_ID")
    if not settings.r2_secret_access_key:
        missing.append("R2_SECRET_ACCESS_KEY")
    if not settings.effective_r2_endpoint_url:
        missing.append("R2_ACCOUNT_ID or R2_ENDPOINT_URL")
    return tuple(missing)


def _redact_url_host_and_path(url: str) -> str:
    """Return only scheme/host/path without query parameters or signatures."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def _verify_signed_url_expiration_config(
    signed_url: str,
    *,
    expected_ttl_s: int,
    expected_bucket: str,
    expected_key: str,
) -> None:
    """Assert SigV4 signed URL structure and X-Amz-Expires without logging the URL."""
    parsed = urlparse(signed_url)
    qs = parse_qs(parsed.query)
    if parsed.scheme != "https":
        raise AssertionError(f"Expected https scheme on signed URL, got {parsed.scheme!r}")
    expected_path = f"/{expected_bucket}/{expected_key}"
    if parsed.path != expected_path:
        raise AssertionError(f"Signed URL path mismatch: got {parsed.path!r}")
    if qs.get("X-Amz-Algorithm") != ["AWS4-HMAC-SHA256"]:
        raise AssertionError("Signed URL missing AWS4-HMAC-SHA256 algorithm parameter")
    if qs.get("X-Amz-Expires") != [str(expected_ttl_s)]:
        raise AssertionError(
            f"Signed URL X-Amz-Expires={qs.get('X-Amz-Expires')} != [{expected_ttl_s}]"
        )
    sig = qs.get("X-Amz-Signature", [""])[0]
    if len(sig) != 64:
        raise AssertionError("Signed URL missing valid 64-hex SigV4 signature")


async def run_live_r2_probe(
    *,
    settings: Settings | None = None,
    env_path: Path | None = None,
    adapter: ObjectStoragePort | None = None,
    http_get: Callable[[str], httpx.Response] | None = None,
) -> ProbeResult:
    """Execute the safe live R2 round-trip verification probe."""
    if settings is None:
        settings, load_err = _load_settings_from_backend_env(env_path)
        if settings is None:
            return ProbeResult(
                status="FAIL",
                exit_code=1,
                summary=f"Failed to load backend settings: {load_err}",
            )

    if adapter is None:
        missing = _check_r2_readiness(settings)
        if missing:
            return ProbeResult(
                status="BLOCKED",
                exit_code=2,
                summary=(
                    "Live R2 credentials/configuration not provisioned in backend/.env: "
                    + ", ".join(missing)
                ),
                missing_fields=missing,
            )

        try:
            adapter = create_storage_adapter(settings)
        except Exception as exc:
            return ProbeResult(
                status="FAIL",
                exit_code=1,
                summary=f"Failed to create R2 adapter: {type(exc).__name__}: {_sanitize_message(str(exc))}",
            )

        if not isinstance(adapter, CloudflareR2StorageAdapter):
            return ProbeResult(
                status="BLOCKED",
                exit_code=2,
                summary="Storage adapter is not CloudflareR2StorageAdapter.",
                missing_fields=("MEDIA_STORAGE_PROVIDER=r2",),
            )

    bucket_name = settings.r2_bucket_name or getattr(adapter, "bucket_name", "unknown")
    probe_key = f"users/{PROBE_USER_ID}/tryon/r2-live-probe-{uuid.uuid4()}/probe.webp"
    payload = _build_synthetic_webp_bytes()
    expected_sha256 = hashlib.sha256(payload).hexdigest()

    client: httpx.Client | None = None
    if http_get is None:
        client = httpx.Client(timeout=15.0, follow_redirects=False)
        http_get_fn = client.get
    else:
        http_get_fn = http_get

    uploaded = False
    unsigned_status: int | None = None
    signed_status: int | None = None
    post_delete_status: int | None = None
    health: dict[str, Any] | None = None

    try:
        # 1. Verify bucket connectivity (HeadBucket)
        check_fn = getattr(adapter, "check_health", None)
        if callable(check_fn):
            health = await check_fn()
            if health.get("status") != "healthy":
                return ProbeResult(
                    status="FAIL",
                    exit_code=1,
                    summary=f"R2 bucket health check unhealthy: {health}",
                    bucket=bucket_name,
                    health=health,
                )

        # 2. Verify URL expiration bounds and TTL encoding (local SigV4 validation)
        for bad_ttl in (0, 604801):
            try:
                await adapter.generate_presigned_get_url(key=probe_key, expires_in_s=bad_ttl)
            except StoragePayloadError:
                pass
            else:
                raise AssertionError(f"Expected StoragePayloadError for expires_in_s={bad_ttl}")

        genlook_ttl_url = await adapter.generate_presigned_get_url(
            key=probe_key,
            expires_in_s=PROBE_GENLOOK_TTL_S,
        )
        _verify_signed_url_expiration_config(
            genlook_ttl_url,
            expected_ttl_s=PROBE_GENLOOK_TTL_S,
            expected_bucket=bucket_name,
            expected_key=probe_key,
        )

        # 3. Upload synthetic non-personal test image
        meta = await adapter.put_object(
            probe_key,
            payload,
            content_type="image/webp",
            custom_metadata={"purpose": "r2_live_connectivity_probe"},
        )
        uploaded = True
        if meta.size_bytes != len(payload):
            raise AssertionError(f"Uploaded size mismatch: {meta.size_bytes} != {len(payload)}")

        if not await adapter.object_exists(probe_key):
            raise AssertionError("object_exists returned False immediately after put_object")

        # 4. Confirm unsigned public access to the private bucket is rejected
        if settings.effective_r2_endpoint_url:
            unsigned_url = (
                f"{settings.effective_r2_endpoint_url.rstrip('/')}/{bucket_name}/{probe_key}"
            )
            r_unsigned = await asyncio.to_thread(http_get_fn, unsigned_url)
            unsigned_status = r_unsigned.status_code
            if unsigned_status not in (400, 401, 403, 404):
                raise AssertionError(
                    f"Private bucket check failed: unsigned URL returned HTTP {unsigned_status} "
                    f"at {_redact_url_host_and_path(unsigned_url)}"
                )

        # 5. Generate signed GET URL and verify expiration config
        signed_url = await adapter.generate_presigned_get_url(
            key=probe_key,
            expires_in_s=PROBE_SIGNED_TTL_S,
            response_content_type="image/webp",
        )
        _verify_signed_url_expiration_config(
            signed_url,
            expected_ttl_s=PROBE_SIGNED_TTL_S,
            expected_bucket=bucket_name,
            expected_key=probe_key,
        )

        # 6. Retrieve object via signed URL and verify content integrity
        r_signed = await asyncio.to_thread(http_get_fn, signed_url)
        signed_status = r_signed.status_code
        if signed_status != 200:
            raise AssertionError(f"Signed GET returned HTTP {signed_status}")

        fetched_bytes = r_signed.content
        if fetched_bytes != payload:
            raise AssertionError("Downloaded bytes did not match uploaded synthetic image bytes")
        if hashlib.sha256(fetched_bytes).hexdigest() != expected_sha256:
            raise AssertionError("Downloaded SHA-256 digest mismatch")

        with Image.open(io.BytesIO(fetched_bytes)) as img:
            img.load()
            if img.format != "WEBP" or img.size != (64, 64):
                raise AssertionError(
                    f"Decoded image mismatch: format={img.format!r}, size={img.size!r}"
                )

        # 7. Delete test object and confirm cleanup
        deleted = await adapter.delete_object(probe_key)
        if not deleted:
            raise AssertionError("delete_object returned False")
        uploaded = False

        if await adapter.object_exists(probe_key):
            raise AssertionError("object_exists returned True after delete_object")

        r_after_delete = await asyncio.to_thread(http_get_fn, signed_url)
        post_delete_status = r_after_delete.status_code
        if post_delete_status != 404:
            raise AssertionError(
                f"Expected HTTP 404 after object deletion, got {post_delete_status}"
            )

        return ProbeResult(
            status="PASS",
            exit_code=0,
            summary=(
                "Live R2 probe passed: health check, private upload, unsigned block, "
                "signed GET integrity, expiration config, and cleanup verified."
            ),
            bucket=bucket_name,
            health=health,
            unsigned_status_code=unsigned_status,
            signed_status_code=signed_status,
            post_delete_status_code=post_delete_status,
            bytes_verified=len(payload),
            sha256=expected_sha256,
        )
    except Exception as exc:
        safe_err = _sanitize_message(f"{type(exc).__name__}: {exc}")
        return ProbeResult(
            status="FAIL",
            exit_code=1,
            summary=f"Live R2 probe failed: {safe_err}",
            bucket=bucket_name,
            health=health,
            unsigned_status_code=unsigned_status,
            signed_status_code=signed_status,
            post_delete_status_code=post_delete_status,
        )
    finally:
        if uploaded:
            try:
                await adapter.delete_object(probe_key)
            except Exception:
                pass
        if client is not None:
            client.close()
        try:
            await adapter.close()
        except Exception:
            pass


def main() -> int:
    result = asyncio.run(run_live_r2_probe())
    print(f"R2_LIVE_PROBE_STATUS={result.status}")
    print(f"SUMMARY={result.summary}")
    if result.bucket:
        print(f"BUCKET={result.bucket}")
    if result.health:
        print(
            f"HEALTH=status:{result.health.get('status')} latency_ms:{result.health.get('latency_ms')}"
        )
    if result.unsigned_status_code is not None:
        print(f"UNSIGNED_GET_HTTP={result.unsigned_status_code}")
    if result.signed_status_code is not None:
        print(f"SIGNED_GET_HTTP={result.signed_status_code}")
    if result.post_delete_status_code is not None:
        print(f"POST_DELETE_GET_HTTP={result.post_delete_status_code}")
    if result.bytes_verified is not None:
        print(f"BYTES_VERIFIED={result.bytes_verified} SHA256={result.sha256}")
    if result.missing_fields:
        print(f"MISSING={','.join(result.missing_fields)}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

