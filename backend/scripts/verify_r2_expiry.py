#!/usr/bin/env python3
"""Isolated live Cloudflare R2 signed URL expiration verification (Phase 5F.3C).

Proves actual time-elapsed expiration enforcement by Cloudflare R2 (not merely
local TTL config validation):
1. Uploads a synthetic 64x64 non-personal WebP image to the private R2 bucket.
2. Generates a short-lived SigV4 presigned GET URL (default TTL: 3 seconds).
3. Retrieves the object immediately via the signed URL and verifies HTTP 200 + SHA-256.
4. Waits past the TTL (plus clock-skew margin) and re-fetches the exact same signed URL.
5. Confirms Cloudflare R2 rejects the expired URL with HTTP 403.
6. Deletes the test object and confirms zero test objects remain.

Safety guarantees:
- Synthetic solid-color Pillow image in memory only (no real user photos).
- Zero Genlook API calls or paid try-on credits consumed.
- Never prints credentials, account IDs, or complete signed URLs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import sys
import time
from typing import Callable
import uuid
import xml.etree.ElementTree as ET

import httpx
from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config.settings import Settings  # noqa: E402
from app.domain.ports.storage import ObjectStoragePort  # noqa: E402
from app.infrastructure.external.storage import (  # noqa: E402
    CloudflareR2StorageAdapter,
    _sanitize_message,
    create_storage_adapter,
)

PROBE_USER_ID = "00000000-0000-0000-0000-000000000000"
DEFAULT_SHORT_TTL_S = 3
DEFAULT_MAX_WAIT_S = 12


@dataclass(frozen=True)
class ExpiryVerificationResult:
    """Secret-free result of actual signed URL expiration verification."""

    status: str  # "PASS" | "FAIL" | "BLOCKED"
    exit_code: int
    summary: str
    bucket: str | None = None
    ttl_seconds: int = DEFAULT_SHORT_TTL_S
    elapsed_seconds: float = 0.0
    pre_expiry_status_code: int | None = None
    post_expiry_status_code: int | None = None
    rejection_error_code: str | None = None
    rejection_message: str | None = None
    cleanup_verified: bool = False


def _build_synthetic_webp_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (16, 112, 168)).save(buf, format="WEBP")
    return buf.getvalue()


def _parse_s3_error(body: bytes) -> tuple[str | None, str | None]:
    """Extract sanitized S3 XML error Code and Message without leaking URLs."""
    try:
        root = ET.fromstring(body.decode("utf-8", errors="replace"))
        code = root.findtext("Code")
        msg = root.findtext("Message")
        return (
            _sanitize_message(code.strip()) if code else None,
            _sanitize_message(msg.strip()) if msg else None,
        )
    except Exception:
        return None, None


async def run_signed_url_expiry_verification(
    *,
    settings: Settings | None = None,
    env_path: Path | None = None,
    adapter: ObjectStoragePort | None = None,
    http_get: Callable[[str], httpx.Response] | None = None,
    ttl_s: int = DEFAULT_SHORT_TTL_S,
    wait_margin_s: float = 3.0,
    max_wait_s: float = DEFAULT_MAX_WAIT_S,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ExpiryVerificationResult:
    """Verify that a short-lived R2 presigned GET URL works before TTL and is rejected after TTL."""
    if ttl_s < 1 or ttl_s > 60:
        return ExpiryVerificationResult(
            status="FAIL",
            exit_code=1,
            summary="ttl_s must be between 1 and 60 seconds for isolated expiry verification",
            ttl_seconds=ttl_s,
        )

    if settings is None:
        target_env = env_path or (BACKEND_DIR / ".env")
        settings = Settings(_env_file=target_env if target_env.exists() else None)

    if adapter is None:
        if (
            settings.media_storage_provider != "r2"
            or not settings.r2_bucket_name
            or not settings.r2_access_key_id
            or not settings.r2_secret_access_key
            or not settings.effective_r2_endpoint_url
        ):
            return ExpiryVerificationResult(
                status="BLOCKED",
                exit_code=2,
                summary="Live R2 credentials/configuration not provisioned.",
                ttl_seconds=ttl_s,
            )
        adapter = create_storage_adapter(settings)
        if not isinstance(adapter, CloudflareR2StorageAdapter):
            return ExpiryVerificationResult(
                status="BLOCKED",
                exit_code=2,
                summary="Storage adapter is not CloudflareR2StorageAdapter.",
                ttl_seconds=ttl_s,
            )

    bucket_name = settings.r2_bucket_name or getattr(adapter, "bucket_name", "unknown")
    probe_key = f"users/{PROBE_USER_ID}/tryon/r2-expiry-probe-{uuid.uuid4()}/probe.webp"
    payload = _build_synthetic_webp_bytes()
    expected_sha256 = hashlib.sha256(payload).hexdigest()

    client: httpx.Client | None = None
    if http_get is None:
        client = httpx.Client(timeout=15.0, follow_redirects=False)
        http_get_fn = client.get
    else:
        http_get_fn = http_get

    uploaded = False
    pre_status: int | None = None
    post_status: int | None = None
    err_code: str | None = None
    err_msg: str | None = None
    elapsed = 0.0

    try:
        await adapter.put_object(
            probe_key,
            payload,
            content_type="image/webp",
            custom_metadata={"purpose": "r2_live_expiry_probe"},
        )
        uploaded = True

        signed_at = time.monotonic()
        signed_url = await adapter.generate_presigned_get_url(
            key=probe_key,
            expires_in_s=ttl_s,
            response_content_type="image/webp",
        )

        # 1. Confirm URL succeeds before expiration
        r_before = await asyncio.to_thread(http_get_fn, signed_url)
        pre_status = r_before.status_code
        if pre_status != 200:
            raise AssertionError(f"Expected HTTP 200 before expiry, got {pre_status}")
        if hashlib.sha256(r_before.content).hexdigest() != expected_sha256:
            raise AssertionError("Pre-expiry payload SHA-256 mismatch")

        # 2. Sleep until past TTL + margin, retrying briefly if edge clock skew permits
        initial_wait = max(0.5, ttl_s + wait_margin_s - (time.monotonic() - signed_at))
        await asyncio.to_thread(sleep_fn, initial_wait)

        while True:
            elapsed = round(time.monotonic() - signed_at, 2)
            r_after = await asyncio.to_thread(http_get_fn, signed_url)
            post_status = r_after.status_code
            if post_status in (401, 403):
                err_code, err_msg = _parse_s3_error(r_after.content)
                break
            if elapsed >= max_wait_s:
                raise AssertionError(
                    f"Signed URL still accepted (HTTP {post_status}) after {elapsed}s (TTL={ttl_s}s)"
                )
            await asyncio.to_thread(sleep_fn, 1.0)

        # 3. Clean up synthetic test object
        deleted = await adapter.delete_object(probe_key)
        uploaded = False
        exists_after = await adapter.object_exists(probe_key)
        cleanup_ok = bool(deleted and not exists_after)

        return ExpiryVerificationResult(
            status="PASS" if cleanup_ok else "FAIL",
            exit_code=0 if cleanup_ok else 1,
            summary=(
                f"Actual R2 signed URL expiration verified: HTTP {pre_status} before TTL={ttl_s}s, "
                f"HTTP {post_status} ({err_code or 'rejected'}) after {elapsed}s."
            ),
            bucket=bucket_name,
            ttl_seconds=ttl_s,
            elapsed_seconds=elapsed,
            pre_expiry_status_code=pre_status,
            post_expiry_status_code=post_status,
            rejection_error_code=err_code,
            rejection_message=err_msg,
            cleanup_verified=cleanup_ok,
        )
    except Exception as exc:
        return ExpiryVerificationResult(
            status="FAIL",
            exit_code=1,
            summary=f"Expiry verification failed: {type(exc).__name__}: {_sanitize_message(str(exc))}",
            bucket=bucket_name,
            ttl_seconds=ttl_s,
            elapsed_seconds=elapsed,
            pre_expiry_status_code=pre_status,
            post_expiry_status_code=post_status,
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
    res = asyncio.run(run_signed_url_expiry_verification())
    print(f"R2_EXPIRY_STATUS={res.status}")
    print(f"SUMMARY={res.summary}")
    if res.bucket:
        print(f"BUCKET={res.bucket}")
    print(
        f"TTL_S={res.ttl_seconds} ELAPSED_S={res.elapsed_seconds} "
        f"PRE_EXPIRY_HTTP={res.pre_expiry_status_code} POST_EXPIRY_HTTP={res.post_expiry_status_code}"
    )
    if res.rejection_error_code or res.rejection_message:
        print(f"REJECTION_CODE={res.rejection_error_code} REJECTION_MESSAGE={res.rejection_message}")
    print(f"CLEANUP_VERIFIED={res.cleanup_verified}")
    return res.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

