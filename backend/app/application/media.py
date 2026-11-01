"""Media upload authorization, durable idempotency, and atomic rate limiting.

Implements P0-4 Phase 2 use cases:
- Authenticated wardrobe photo upload authorization.
- Durable PostgreSQL-backed idempotency (RFC 9440).
- Atomic distributed rate limiting via PostgreSQL transaction-scoped advisory locks.
- Versioned HMAC key-ring request fingerprinting.
- Staging key scoping: `staging/users/{user_id}/wardrobe/{upload_id}.{ext}`.
- Bounded retention pruning.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import asyncio
import hashlib
import hmac
import logging
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, not_, or_, select, text, update
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session

from app.api.errors import ApiError, database_failure, not_found, rate_limited, validation
from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageError,
    StorageNotFoundError,
    StoragePayloadError,
)
from app.infrastructure.db.models import MediaUploadAuthorization
from app.workers.transcoder import (
    ImageValidationError,
    MemoryLimitExceededError,
    TranscoderProcessManager,
    TranscodingError,
    TranscodingTimeoutError,
)

logger = logging.getLogger(__name__)

# --- Legacy Analysis MediaRef Helpers (Preserved) ---

_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def sha256_hex(data: bytes) -> str:
    """Hex SHA-256 digest of the exact bytes received."""
    return hashlib.sha256(data).hexdigest()


def read_image_bytes(image: object) -> bytes:
    """Read the actual received bytes from an uploaded image."""
    file_obj = getattr(image, "file", None)
    read = getattr(file_obj, "read", None)
    if read is None:
        raise validation(
            [{"field": "image", "error": "could not read image data"}]
        )
    try:
        file_obj.seek(0)
    except Exception:
        pass
    try:
        content = read()
    except Exception:
        raise validation(
            [{"field": "image", "error": "could not read image data"}]
        )
    if not isinstance(content, (bytes, bytearray)) or len(content) == 0:
        raise validation(
            [{"field": "image", "error": "could not read image data"}]
        )
    return bytes(content)


def build_media_ref(
    *,
    user_id: UUID,
    content_type: str,
    content: bytes,
    analyzer: str | None = None,
) -> dict:
    """Build the persisted MediaRef metadata dict from received bytes."""
    ext = _EXTENSION_BY_CONTENT_TYPE.get(content_type, "jpg")
    key = f"users/{user_id}/scans/{uuid4()}/input.{ext}"
    media_ref = {
        "key": key,
        "mediaType": content_type,
        "sizeBytes": len(content),
        "contentHash": sha256_hex(content),
        "isGenerated": False,
        "uploadedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if analyzer is not None:
        media_ref["analyzer"] = analyzer
    return media_ref


# --- Stage 2 P0-4 / M16 Upload Authorization Constants & Helpers ---

# Upload authorization validity window
PRESIGNED_PUT_EXPIRY_SECONDS = 900  # 15 minutes
IDEMPOTENCY_RETENTION_HOURS = 24    # 24 hours durable retention
MAX_UPLOADS_PER_MINUTE = 30         # 30 new authorizations per rolling 60s


class IdempotencyConflictError(ApiError):
    """Raised when an Idempotency-Key is reused with differing request parameters (RFC 9440)."""

    def __init__(self, key: str) -> None:
        super().__init__(
            status_code=409,
            code="IDEMPOTENCY_CONFLICT",
            message="The Idempotency-Key has already been used with different request parameters.",
            details={"idempotency_key": key},
        )


def compute_canonical_request_fingerprint(
    *,
    secret_key: str,
    user_id: UUID,
    purpose: str,
    content_type: str,
    size_bytes: int,
    client_assertion_sha256: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    """Compute deterministic canonical HMAC-SHA256 request fingerprint.

    Binds strictly to normalized, non-volatile semantic request fields. Volatile
    fields like timestamps or generated URLs are strictly excluded.
    """
    canonical_payload = (
        f"client_sha256:{client_assertion_sha256 or ''}\n"
        f"content_type:{content_type.strip().lower()}\n"
        f"filename:{filename or ''}\n"
        f"purpose:{purpose.strip().lower()}\n"
        f"size_bytes:{size_bytes}\n"
        f"user_id:{str(user_id).lower().strip()}"
    )
    return hmac.new(
        secret_key.encode("utf-8"),
        f"fansivibe:v1:req_fingerprint:\n{canonical_payload}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


MEDIA_UPLOAD_LOCK_NAMESPACE = "media_upload_rate_limit"
DEFAULT_PRUNE_BATCH_SIZE = 1000


def get_media_upload_lock_key(user_id: UUID) -> int:
    """Derive a stable, namespaced signed 64-bit integer for user-scoped advisory locking.

    Stable namespace: ``media_upload_rate_limit:{user_id}``.
    Preserved across deployed instances to ensure consistent serialization.
    """
    digest = hashlib.sha256(f"{MEDIA_UPLOAD_LOCK_NAMESPACE}:{user_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def prune_expired_authorizations(
    db: Session,
    *,
    now: Optional[datetime] = None,
    batch_size: int = DEFAULT_PRUNE_BATCH_SIZE,
    max_batches: Optional[int] = None,
) -> int:
    """Prune expired non-published authorization records in bounded batches (Stage 2 P0-4 Phase 3.1).

    Guarantees:
    - Published media authorization records (`status = 'published'`) are strictly
      preserved regardless of age, retaining canonical metadata for Phase 4 wardrobe association.
    - Active processing records (`status = 'processing'` with active lease) are preserved.
    - Stale/expired authorizations (`status in ('authorized', 'failed', 'expired')` or
      processing records whose lease expired) older than `cutoff` are pruned in bounded batches.
    - Deletes at most ``batch_size`` records per transaction commit to prevent
      lock contention and large WAL spikes. Returns total records deleted.
    - Never deletes canonical storage objects as part of authorization pruning.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    if max_batches is not None and max_batches < 1:
        raise ValueError("max_batches must be >= 1")

    cutoff = now or datetime.now(timezone.utc)
    total_deleted = 0
    batches_run = 0

    is_active_processing = and_(
        MediaUploadAuthorization.status == "processing",
        MediaUploadAuthorization.processing_lease_expires_at.is_not(None),
        MediaUploadAuthorization.processing_lease_expires_at >= cutoff,
    )

    while True:
        stmt = (
            select(MediaUploadAuthorization.upload_id)
            .where(
                MediaUploadAuthorization.expires_at < cutoff,
                MediaUploadAuthorization.status != "published",
                not_(is_active_processing),
            )
            .limit(batch_size)
        )
        batch_ids = list(db.execute(stmt).scalars().all())
        if not batch_ids:
            break

        del_stmt = delete(MediaUploadAuthorization).where(
            MediaUploadAuthorization.upload_id.in_(batch_ids)
        )
        res = db.execute(del_stmt)
        db.commit()

        count = res.rowcount or len(batch_ids)
        total_deleted += count
        batches_run += 1

        if len(batch_ids) < batch_size:
            break
        if max_batches is not None and batches_run >= max_batches:
            break

    return total_deleted


class AuthorizeMediaUpload:
    """Use case implementing the 14-step upload authorization lifecycle."""

    def __init__(
        self,
        *,
        storage: ObjectStoragePort,
        db: Session,
        active_key_id: str,
        key_ring: Dict[str, str],
    ) -> None:
        self._storage = storage
        self._db = db
        self._active_key_id = active_key_id
        self._key_ring = key_ring
        self._active_secret = key_ring.get(active_key_id) or "fansivibe-dev-upload-secret"

    def _verify_existing_fingerprint(
        self,
        existing: MediaUploadAuthorization,
        *,
        user_id: UUID,
        purpose: str,
        content_type: str,
        size_bytes: int,
        client_assertion_sha256: Optional[str],
        filename: Optional[str],
    ) -> bool:
        """Verify if incoming request matches existing record's fingerprint under its key version."""
        secret = self._key_ring.get(existing.key_version)
        if not secret:
            logger.warning(
                "Authorization %s has unknown key_version %s",
                existing.upload_id,
                existing.key_version,
            )
            return False
        expected_fp = compute_canonical_request_fingerprint(
            secret_key=secret,
            user_id=user_id,
            purpose=purpose,
            content_type=content_type,
            size_bytes=size_bytes,
            client_assertion_sha256=client_assertion_sha256,
            filename=filename,
        )
        return hmac.compare_digest(existing.request_fingerprint, expected_fp)

    async def _generate_upload_response(
        self,
        *,
        upload_id: UUID,
        staging_key: str,
        content_type: str,
        size_bytes: int,
        expires_at: datetime,
    ) -> Dict[str, Any]:
        """Generate presigned PUT URL and construct standardized upload response."""
        try:
            upload_url = await self._storage.generate_presigned_put_url(
                key=staging_key,
                content_type=content_type,
                size_bytes=size_bytes,
                expires_in_s=PRESIGNED_PUT_EXPIRY_SECONDS,
            )
        except Exception as exc:
            logger.error("Presigned URL generation failed: %s", exc)
            raise ApiError(
                status_code=500,
                code="STORAGE_SIGNING_ERROR",
                message="Failed to generate presigned upload URL. Please retry with the same Idempotency-Key.",
                details={"upload_id": str(upload_id)},
            )

        return {
            "uploadId": upload_id,
            "uploadUrl": upload_url,
            "stagingKey": staging_key,
            "expiresAt": expires_at,
            "expiresInSeconds": PRESIGNED_PUT_EXPIRY_SECONDS,
            "requiredHeaders": {"Content-Type": content_type},
        }

    async def execute(
        self,
        *,
        user_id: UUID,
        purpose: str,
        content_type: str,
        size_bytes: int,
        idempotency_key: str,
        filename: Optional[str] = None,
        client_assertion_sha256: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Authorize a media upload following the strict 14-step transaction lifecycle."""
        clean_key = idempotency_key.strip()
        if not clean_key or len(clean_key) > 128:
            raise ApiError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="Idempotency-Key must be between 1 and 128 characters.",
                details={"header": "Idempotency-Key"},
            )

        # 3. Compute canonical request fingerprint
        fingerprint = compute_canonical_request_fingerprint(
            secret_key=self._active_secret,
            user_id=user_id,
            purpose=purpose,
            content_type=content_type,
            size_bytes=size_bytes,
            client_assertion_sha256=client_assertion_sha256,
            filename=filename,
        )

        ext = "webp" if content_type == "image/webp" else "jpeg"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=PRESIGNED_PUT_EXPIRY_SECONDS)

        # 4. Fast check for existing (user_id, idempotency_key) record
        try:
            existing = self._db.execute(
                select(MediaUploadAuthorization).where(
                    MediaUploadAuthorization.user_id == user_id,
                    MediaUploadAuthorization.idempotency_key == clean_key,
                )
            ).scalar_one_or_none()
        except OperationalError as exc:
            self._db.rollback()
            pgcode = getattr(exc.orig, "pgcode", None) or getattr(exc.orig, "sqlstate", None)
            is_lock_timeout = False
            if pgcode == "55P03":
                is_lock_timeout = True
            else:
                error_str = str(exc).lower()
                if "lock_timeout" in error_str or "canceling statement due to lock timeout" in error_str:
                    is_lock_timeout = True
            if is_lock_timeout:
                logger.warning("Advisory lock acquisition timed out for user %s", user_id)
                raise rate_limited(retry_after_s=5)
            logger.error("Database operational error during fast check: %s", exc)
            raise database_failure()
        except DBAPIError as exc:
            self._db.rollback()
            logger.error("Database error during fast check: %s", exc)
            raise database_failure()

        if existing is not None:
            # 5. Check semantic conflict (RFC 9440) using the record's persisted key_version
            if not self._verify_existing_fingerprint(
                existing,
                user_id=user_id,
                purpose=purpose,
                content_type=content_type,
                size_bytes=size_bytes,
                client_assertion_sha256=client_assertion_sha256,
                filename=filename,
            ):
                raise IdempotencyConflictError(clean_key)

            # 6. Identical retry: reuse existing authorization and mint fresh URL
            existing_upload_id = existing.upload_id
            existing_staging_key = existing.staging_key
            self._db.rollback()
            return await self._generate_upload_response(
                upload_id=existing_upload_id,
                staging_key=existing_staging_key,
                content_type=content_type,
                size_bytes=size_bytes,
                expires_at=expires_at,
            )

        # 7-13. New request: Enforce rate limit & persist under atomic transaction lock
        is_postgres = False
        try:
            bind = self._db.get_bind()
            if bind is not None and bind.dialect.name == "postgresql":
                is_postgres = True
        except Exception:
            is_postgres = False

        lock_key = get_media_upload_lock_key(user_id)

        try:
            # 8. Acquire transaction-scoped PostgreSQL advisory lock
            if is_postgres:
                self._db.execute(text("SET LOCAL lock_timeout = '3s'"))
                self._db.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": lock_key},
                )

            # 9. Double-check idempotency record while holding the lock
            locked_existing = self._db.execute(
                select(MediaUploadAuthorization).where(
                    MediaUploadAuthorization.user_id == user_id,
                    MediaUploadAuthorization.idempotency_key == clean_key,
                )
            ).scalar_one_or_none()

            if locked_existing is not None:
                if not self._verify_existing_fingerprint(
                    locked_existing,
                    user_id=user_id,
                    purpose=purpose,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    client_assertion_sha256=client_assertion_sha256,
                    filename=filename,
                ):
                    raise IdempotencyConflictError(clean_key)

                existing_upload_id = locked_existing.upload_id
                existing_staging_key = locked_existing.staging_key
                # Release database transaction and advisory lock before awaiting external storage signing!
                self._db.rollback()
                return await self._generate_upload_response(
                    upload_id=existing_upload_id,
                    staging_key=existing_staging_key,
                    content_type=content_type,
                    size_bytes=size_bytes,
                    expires_at=expires_at,
                )

            # 10. Count authorizations in rolling 60-second window
            if is_postgres:
                window_filter = MediaUploadAuthorization.created_at >= (
                    func.now() - text("INTERVAL '60 seconds'")
                )
            else:
                one_min_ago = now - timedelta(seconds=60)
                window_filter = MediaUploadAuthorization.created_at >= one_min_ago

            recent_count = self._db.execute(
                select(func.count()).select_from(MediaUploadAuthorization).where(
                    MediaUploadAuthorization.user_id == user_id,
                    window_filter,
                )
            ).scalar() or 0

            # 11. Enforce rate limit ceiling (30 req/min)
            if recent_count >= MAX_UPLOADS_PER_MINUTE:
                raise rate_limited(retry_after_s=60)

            # 12. Persist the new authorization record
            upload_id = uuid4()
            staging_key = f"staging/users/{str(user_id)}/wardrobe/{str(upload_id)}.{ext}"

            new_auth = MediaUploadAuthorization(
                user_id=user_id,
                idempotency_key=clean_key,
                upload_id=upload_id,
                key_version=self._active_key_id,
                request_fingerprint=fingerprint,
                staging_key=staging_key,
                content_type=content_type,
                size_bytes=size_bytes,
                created_at=now,
                expires_at=now + timedelta(hours=IDEMPOTENCY_RETENTION_HOURS),
            )
            self._db.add(new_auth)

            # 13. Commit the transaction (releases advisory lock)
            self._db.commit()

        except OperationalError as exc:
            self._db.rollback()
            # Map PostgreSQL lock timeout (SQLSTATE 55P03) to 429 Retry-After: 5
            pgcode = getattr(exc.orig, "pgcode", None) or getattr(exc.orig, "sqlstate", None)
            is_lock_timeout = False
            if pgcode == "55P03":
                is_lock_timeout = True
            else:
                error_str = str(exc).lower()
                if "lock_timeout" in error_str or "canceling statement due to lock timeout" in error_str:
                    is_lock_timeout = True

            if is_lock_timeout:
                logger.warning("Advisory lock acquisition timed out for user %s", user_id)
                raise rate_limited(retry_after_s=5)
            logger.error("Database operational error during upload authorization: %s", exc)
            raise database_failure()
        except DBAPIError as exc:
            self._db.rollback()
            logger.error("Database error during upload authorization: %s", exc)
            raise database_failure()
        except ApiError:
            self._db.rollback()
            raise
        except Exception as exc:
            self._db.rollback()
            logger.exception("Unexpected error during upload authorization: %s", exc)
            raise database_failure()

        # 14. Generate presigned PUT URL using persisted authorization
        return await self._generate_upload_response(
            upload_id=upload_id,
            staging_key=staging_key,
            content_type=content_type,
            size_bytes=size_bytes,
            expires_at=expires_at,
        )


MEDIA_UPLOAD_COMPLETE_LOCK_NAMESPACE = "media_upload_complete"
DEFAULT_PROCESSING_LEASE_SECONDS = 30
PROCESSING_LEASE_SECONDS = DEFAULT_PROCESSING_LEASE_SECONDS
MAX_PROCESSING_ATTEMPTS = 5
PROCESSING_RECOVERY_COOLDOWN_SECONDS = 60.0
DEFAULT_PIPELINE_TIMEOUT_SECONDS = 25.0
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5.0


def _get_db_wallclock(db: Session, is_postgres: bool) -> datetime:
    """Return actual database wall-clock time using clock_timestamp() on PostgreSQL.

    Prevents transaction-start freezing where SELECT now() returns the timestamp
    at the start of the transaction before advisory-lock acquisition.
    """
    if is_postgres:
        try:
            val = db.execute(text("SELECT clock_timestamp()")).scalar()
            if val is not None:
                return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return datetime.now(timezone.utc)


def get_attempt_object_key(user_id: UUID, upload_id: UUID, lease_token: UUID) -> str:
    """Derive immutable attempt-specific WebP storage key from user ID, upload ID, and lease token (Stage 2 P0-4 Phase 3.4).

    Format: users/{user_id}/wardrobe/{upload_id}/attempts/{lease_token}.webp

    Guarantees:
    - Derived strictly from authenticated owner, upload ID, and lease token.
    - Never derived from arbitrary client input.
    - Path components validated and normalized as UUID strings (preventing traversal).
    - Immutable across processing attempts: different attempts write to distinct non-overlapping keys.
    """
    u_str = str(UUID(str(user_id)))
    up_str = str(UUID(str(upload_id)))
    tok_str = str(UUID(str(lease_token)))
    return f"users/{u_str}/wardrobe/{up_str}/attempts/{tok_str}.webp"


def get_canonical_object_key(
    user_id: UUID, upload_id: UUID, lease_token: Optional[UUID] = None
) -> str:
    """Derive canonical WebP storage key.

    If lease_token is provided, delegates to get_attempt_object_key (Stage 2 P0-4 Phase 3.4):
    users/{user_id}/wardrobe/{upload_id}/attempts/{lease_token}.webp

    If lease_token is None, returns the legacy deterministic key (Stage 2 P0-4 Phase 3.1):
    users/{user_id}/wardrobe/{upload_id}/canonical.webp
    """
    if lease_token is not None:
        return get_attempt_object_key(user_id, upload_id, lease_token)
    u_str = str(UUID(str(user_id)))
    up_str = str(UUID(str(upload_id)))
    return f"users/{u_str}/wardrobe/{up_str}/canonical.webp"


def get_media_upload_complete_lock_key(upload_id: UUID) -> int:
    """Derive stable signed 64-bit integer for upload-completion advisory locking."""
    raw = hashlib.sha256(f"fansivibe:{MEDIA_UPLOAD_COMPLETE_LOCK_NAMESPACE}:{upload_id}".encode()).digest()[:8]
    return int.from_bytes(raw, "big", signed=True)


class CompleteMediaUpload:
    """Stage 2 P0-4 Phase 3.2: Verify staging media upload and publish canonical WebP with fenced lease coordination."""

    def __init__(
        self,
        storage: ObjectStoragePort,
        db: Session,
        transcoder: Optional[TranscoderProcessManager] = None,
        lease_seconds: int = PROCESSING_LEASE_SECONDS,
        pipeline_timeout_seconds: float = DEFAULT_PIPELINE_TIMEOUT_SECONDS,
        heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._storage = storage
        self._db = db
        self._transcoder = transcoder or TranscoderProcessManager()
        self._lease_seconds = lease_seconds
        self._pipeline_timeout_seconds = pipeline_timeout_seconds
        self._heartbeat_interval_seconds = heartbeat_interval_seconds

    def renew_lease(
        self,
        upload_id: UUID,
        lease_token: UUID,
        extend_seconds: Optional[int] = None,
    ) -> bool:
        """Renew processing lease if and only if the current worker still holds ownership.

        Returns True if lease was extended, False if ownership was lost (affected 0 rows).
        Uses independent database connection to avoid interfering with any ongoing transaction on self._db.
        """
        sec = extend_seconds or self._lease_seconds
        try:
            engine = self._db.get_bind()
            if engine is None:
                return False
            is_postgres = getattr(engine.dialect, "name", "") == "postgresql"
            with engine.connect() as conn:
                if is_postgres:
                    res = conn.execute(
                        text("""
                            UPDATE media_upload_authorizations
                            SET processing_lease_expires_at = clock_timestamp() + make_interval(secs => :extend_seconds)
                            WHERE upload_id = :upload_id
                              AND processing_lease_token = :lease_token
                              AND status = 'processing'
                        """),
                        {"upload_id": upload_id, "lease_token": lease_token, "extend_seconds": sec},
                    )
                else:
                    new_exp = datetime.now(timezone.utc) + timedelta(seconds=sec)
                    stmt = (
                        update(MediaUploadAuthorization)
                        .where(
                            MediaUploadAuthorization.upload_id == upload_id,
                            MediaUploadAuthorization.processing_lease_token == lease_token,
                            MediaUploadAuthorization.status == "processing",
                        )
                        .values(processing_lease_expires_at=new_exp)
                    )
                    res = conn.execute(stmt)
                conn.commit()
                return (res.rowcount or 0) > 0
        except Exception as exc:
            logger.warning("Error renewing lease for upload %s: %s", upload_id, exc)
            return False

    def _record_failure(
        self,
        upload_id: UUID,
        lease_token: Optional[UUID],
        failure_reason: str,
    ) -> bool:
        """Record terminal failure conditional on holding the active lease token."""
        try:
            stmt = (
                update(MediaUploadAuthorization)
                .where(
                    MediaUploadAuthorization.upload_id == upload_id,
                    MediaUploadAuthorization.processing_lease_token == lease_token,
                )
                .values(
                    status="failed",
                    failure_reason=failure_reason[:64],
                    processing_lease_expires_at=None,
                    processing_lease_token=None,
                )
            )
            res = self._db.execute(stmt)
            self._db.commit()
            return (res.rowcount or 0) > 0
        except Exception:
            self._db.rollback()
            return False

    def _record_retryable_status(
        self,
        upload_id: UUID,
        lease_token: Optional[UUID],
    ) -> bool:
        """Clear active lease and revert status to authorized conditional on holding active lease token."""
        try:
            stmt = (
                update(MediaUploadAuthorization)
                .where(
                    MediaUploadAuthorization.upload_id == upload_id,
                    MediaUploadAuthorization.processing_lease_token == lease_token,
                    MediaUploadAuthorization.status == "processing",
                )
                .values(
                    status="authorized",
                    processing_lease_expires_at=None,
                    processing_lease_token=None,
                )
            )
            res = self._db.execute(stmt)
            self._db.commit()
            return (res.rowcount or 0) > 0
        except Exception:
            self._db.rollback()
            return False

    async def execute(
        self,
        *,
        user_id: UUID,
        upload_id: UUID,
        client_assertion_sha256: Optional[str] = None,
    ) -> dict[str, Any]:
        """Verify staging object and publish canonical WebP with fenced lease coordination.

        Enforces:
        - OW-1 ownership boundary (safe 404 on nonexistent or cross-user upload_id).
        - Idempotent replay of previously published uploads (200 OK with published ref, regardless of 24h upload authorization expiry).
        - Terminal failure status protection (HTTP 409 UPLOAD_FAILED).
        - 24-hour authorization expiration check for uncompleted uploads (410 Gone).
        - Atomic serialization of concurrent requests via advisory locking and durable fenced DB lease.
        - True PostgreSQL wall-clock time evaluation via clock_timestamp().
        - Attempt counter bounding across all non-published requests (max 5 attempts, with 60s cooldown recovery).
        - Unique fencing token generated and persisted with every successful lease claim.
        - Safe cancellation, timeouts, and heartbeat renewal.
        - Fail-closed crash recovery requiring trusted server-side integrity evidence and decoded WebP dimensions.
        """
        # 1. Acquire transaction-scoped advisory lock if running on PostgreSQL
        is_postgres = False
        try:
            bind = self._db.get_bind()
            if bind is not None and getattr(bind.dialect, "name", "") == "postgresql":
                is_postgres = True
        except Exception:
            pass

        lock_key = get_media_upload_complete_lock_key(upload_id)
        if is_postgres:
            try:
                self._db.execute(text("SET LOCAL lock_timeout = '3s'"))
                self._db.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_key)"),
                    {"lock_key": lock_key},
                )
            except OperationalError as exc:
                self._db.rollback()
                pgcode = getattr(exc.orig, "pgcode", None) or getattr(exc.orig, "sqlstate", None)
                if pgcode == "55P03" or "lock_timeout" in str(exc).lower():
                    logger.warning("Advisory lock acquisition timed out for completion of upload %s", upload_id)
                    raise rate_limited(retry_after_s=5)
                logger.error("Database operational error during completion locking: %s", exc)
                raise database_failure()
            except Exception as exc:
                self._db.rollback()
                logger.error("Unexpected error during advisory locking: %s", exc)
                raise database_failure()

        # Determine current database wall-clock time (clock_timestamp on PostgreSQL)
        db_now = _get_db_wallclock(self._db, is_postgres)

        # 2. Load the authorization record under OW-1 scoping
        auth = self._db.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.user_id == user_id,
                MediaUploadAuthorization.upload_id == upload_id,
            )
        ).scalar_one_or_none()

        if auth is None:
            self._db.rollback()
            raise not_found()

        # 3. Check if already PUBLISHED (Idempotent replay takes precedence over 24h upload authorization expiry)
        if auth.status == "published":
            # Deterministic cleanup of staging object if previous crash occurred after DB commit
            if auth.staging_key:
                try:
                    await self._storage.delete_object(auth.staging_key)
                except Exception:
                    pass

            published_res = {
                "uploadId": auth.upload_id,
                "objectKey": auth.canonical_key,
                "mediaType": "image/webp",
                "width": auth.canonical_width,
                "height": auth.canonical_height,
                "sizeBytes": auth.canonical_size_bytes,
                "contentHash": auth.canonical_sha256,
                "uploadedAt": auth.completed_at or db_now,
                "status": "ready",
            }
            self._db.rollback()
            return published_res

        # 4. Check if previously FAILED terminally
        if auth.status == "failed":
            self._db.rollback()
            raise ApiError(
                status_code=409,
                code="UPLOAD_FAILED",
                message=f"Upload previously failed terminally ({auth.failure_reason or 'unknown reason'}). Re-upload is required.",
            )

        # 5. Check 24-hour expiration for uncompleted authorizations
        expires_at = auth.expires_at if auth.expires_at.tzinfo else auth.expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= db_now:
            self._db.rollback()
            raise ApiError(
                status_code=410,
                code="UPLOAD_EXPIRED",
                message="The upload authorization has expired.",
            )

        # 6. Check if another concurrent request is actively processing under valid lease
        if auth.status == "processing":
            lease_active = False
            if auth.processing_lease_expires_at is not None:
                lease_exp = (
                    auth.processing_lease_expires_at
                    if auth.processing_lease_expires_at.tzinfo
                    else auth.processing_lease_expires_at.replace(tzinfo=timezone.utc)
                )
                if lease_exp > db_now:
                    lease_active = True

            if lease_active:
                self._db.rollback()
                raise ApiError(
                    status_code=409,
                    code="CONFLICT",
                    message="Upload is currently being processed by another worker. Please retry shortly.",
                    headers={"Retry-After": "5"},
                )

        # 7. Check Attempt-Limit and Cooldown across all non-published, non-active requests
        if auth.processing_attempts >= MAX_PROCESSING_ATTEMPTS:
            started_at = auth.processing_started_at
            if started_at is not None:
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                elapsed_s = (db_now - started_at).total_seconds()
            else:
                elapsed_s = 999.0

            if elapsed_s >= PROCESSING_RECOVERY_COOLDOWN_SECONDS:
                logger.warning(
                    "Upload %s reached %d attempts but cooldown elapsed (%.1fs); resetting attempt counter to 1 for recovery",
                    upload_id,
                    MAX_PROCESSING_ATTEMPTS,
                    elapsed_s,
                )
                auth.processing_attempts = 1
            else:
                self._db.rollback()
                raise ApiError(
                    status_code=409,
                    code="PROCESSING_LIMIT_EXCEEDED",
                    message=f"Upload exceeded maximum processing attempts ({MAX_PROCESSING_ATTEMPTS}). Please wait before retrying.",
                    headers={"Retry-After": "60"},
                )
        else:
            auth.processing_attempts += 1

        # 8. Persist unique fencing lease token & claim processing lease atomically
        previous_lease_token = auth.processing_lease_token
        lease_token = uuid4()
        staging_key = auth.staging_key
        expected_content_type = auth.content_type
        existing_canonical_key = auth.canonical_key
        existing_canonical_sha256 = auth.canonical_sha256

        auth.status = "processing"
        auth.processing_lease_token = lease_token
        auth.processing_started_at = db_now
        auth.processing_lease_expires_at = db_now + timedelta(seconds=self._lease_seconds)
        self._db.commit()

        # 9. Setup background heartbeat task for ongoing renewal
        stop_heartbeat = asyncio.Event()
        heartbeat_task = None
        if self._heartbeat_interval_seconds > 0:
            async def _heartbeat_worker():
                while not stop_heartbeat.is_set():
                    try:
                        await asyncio.wait_for(stop_heartbeat.wait(), timeout=self._heartbeat_interval_seconds)
                        break
                    except asyncio.TimeoutError:
                        pass
                    still_owner = self.renew_lease(upload_id, lease_token, extend_seconds=self._lease_seconds)
                    if not still_owner:
                        logger.warning(
                            "Heartbeat: lease ownership lost for upload %s (token %s)",
                            upload_id,
                            lease_token,
                        )
                        break

            heartbeat_task = asyncio.create_task(_heartbeat_worker())

        try:
            if self._pipeline_timeout_seconds > 0:
                return await asyncio.wait_for(
                    self._execute_pipeline(
                        user_id=user_id,
                        upload_id=upload_id,
                        lease_token=lease_token,
                        staging_key=staging_key,
                        expected_content_type=expected_content_type,
                        existing_canonical_key=existing_canonical_key,
                        existing_canonical_sha256=existing_canonical_sha256,
                        previous_lease_token=previous_lease_token,
                        client_assertion_sha256=client_assertion_sha256,
                    ),
                    timeout=self._pipeline_timeout_seconds,
                )
            else:
                return await self._execute_pipeline(
                    user_id=user_id,
                    upload_id=upload_id,
                    lease_token=lease_token,
                    staging_key=staging_key,
                    expected_content_type=expected_content_type,
                    existing_canonical_key=existing_canonical_key,
                    existing_canonical_sha256=existing_canonical_sha256,
                    previous_lease_token=previous_lease_token,
                    client_assertion_sha256=client_assertion_sha256,
                )
        except asyncio.TimeoutError:
            logger.warning(
                "Pipeline execution timed out after %.1fs for upload %s",
                self._pipeline_timeout_seconds,
                upload_id,
            )
            self._record_retryable_status(upload_id, lease_token)
            raise ApiError(
                status_code=504,
                code="PROCESSING_TIMEOUT",
                message=f"Upload processing exceeded timeout deadline ({self._pipeline_timeout_seconds}s).",
            )
        except asyncio.CancelledError:
            logger.warning("Pipeline execution cancelled for upload %s", upload_id)
            self._record_retryable_status(upload_id, lease_token)
            raise
        finally:
            stop_heartbeat.set()
            if heartbeat_task and not heartbeat_task.done():
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _execute_pipeline(
        self,
        *,
        user_id: UUID,
        upload_id: UUID,
        lease_token: UUID,
        staging_key: str,
        expected_content_type: str,
        existing_canonical_key: Optional[str],
        existing_canonical_sha256: Optional[str],
        previous_lease_token: Optional[UUID] = None,
        client_assertion_sha256: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute the external I/O, transcoding, and finalization stages under fencing ownership."""
        pipeline_completed = False
        try:
            # Step 7: Crash Recovery Check: did previous attempt publish canonical or attempt object to storage?
            candidate_keys: list[str] = []
            if existing_canonical_key and existing_canonical_key not in candidate_keys:
                candidate_keys.append(existing_canonical_key)
            if previous_lease_token is not None:
                prev_attempt_key = get_attempt_object_key(user_id, upload_id, previous_lease_token)
                if prev_attempt_key not in candidate_keys:
                    candidate_keys.append(prev_attempt_key)
            legacy_canonical_key = get_canonical_object_key(user_id, upload_id)
            if legacy_canonical_key not in candidate_keys:
                candidate_keys.append(legacy_canonical_key)
            cur_attempt_key = get_attempt_object_key(user_id, upload_id, lease_token)
            if cur_attempt_key not in candidate_keys:
                candidate_keys.append(cur_attempt_key)

            for expected_canonical_key in candidate_keys:
                try:
                    canonical_meta = await self._storage.get_object_metadata(expected_canonical_key)
                except StorageError as exc:
                    logger.warning("Crash recovery check storage error for %s: %s", expected_canonical_key, exc)
                    canonical_meta = None

                if canonical_meta is None:
                    continue

                expected_prefix = f"users/{str(user_id)}/wardrobe/{str(upload_id)}/"
                if not expected_canonical_key.startswith(expected_prefix) or not expected_canonical_key.endswith(".webp"):
                    logger.warning("Crash recovery: candidate key %s does not match expected prefix", expected_canonical_key)
                    continue

                is_owner_match = True
                meta_user = canonical_meta.custom_metadata.get("user_id") if canonical_meta.custom_metadata else None
                meta_upload = canonical_meta.custom_metadata.get("upload_id") if canonical_meta.custom_metadata else None
                meta_sha256 = canonical_meta.custom_metadata.get("sha256") if canonical_meta.custom_metadata else None

                if meta_user is not None and meta_user != str(user_id):
                    is_owner_match = False
                if meta_upload is not None and meta_upload != str(upload_id):
                    is_owner_match = False

                if "/attempts/" in expected_canonical_key:
                    token_in_key = expected_canonical_key.split("/attempts/")[1].replace(".webp", "")
                    meta_token = canonical_meta.custom_metadata.get("lease_token") if canonical_meta.custom_metadata else None
                    if meta_token is not None and meta_token != token_in_key:
                        is_owner_match = False

                is_type_valid = (canonical_meta.content_type == "image/webp")
                is_size_valid = (0 < canonical_meta.size_bytes <= 2 * 1024 * 1024)

                trusted_sha = existing_canonical_sha256 or meta_sha256

                if not (is_owner_match and is_type_valid and is_size_valid and trusted_sha):
                    logger.warning(
                        "Crash recovery: candidate %s metadata or trusted sha missing/invalid; checking next candidate",
                        expected_canonical_key,
                    )
                    continue

                canonical_bytes = await self._storage.read_object(
                    expected_canonical_key, max_bytes=2 * 1024 * 1024
                )
                actual_canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
                is_valid_webp = (
                    len(canonical_bytes) >= 12
                    and canonical_bytes[:4] == b"RIFF"
                    and canonical_bytes[8:12] == b"WEBP"
                )
                sha_matches = hmac.compare_digest(
                    actual_canonical_sha256.lower(), trusted_sha.strip().lower()
                )

                if not (is_valid_webp and sha_matches):
                    logger.warning(
                        "Crash recovery: canonical %s failed header/sha validation; checking next candidate",
                        expected_canonical_key,
                    )
                    continue

                # Verify dimensions by successful image decoding (never fabricate!)
                width, height = 0, 0
                try:
                    import io
                    from PIL import Image
                    with Image.open(io.BytesIO(canonical_bytes)) as img:
                        if img.format == "WEBP" and img.size[0] > 0 and img.size[1] > 0:
                            width, height = img.size
                        else:
                            logger.warning(
                                "Crash recovery: canonical %s format=%s size=%s",
                                expected_canonical_key,
                                img.format,
                                img.size,
                            )
                except Exception as exc:
                    logger.warning(
                        "Crash recovery: canonical %s failed PIL decoding: %s; rejecting adoption",
                        expected_canonical_key,
                        exc,
                    )

                if width <= 0 or height <= 0:
                    continue

                # Verify staging and client assertion consistency where staging remains available
                staging_consistent = True
                try:
                    staging_meta = await self._storage.get_object_metadata(staging_key)
                except Exception:
                    staging_meta = None

                if staging_meta is not None:
                    try:
                        staging_bytes = await self._storage.read_object(
                            staging_key, max_bytes=2 * 1024 * 1024
                        )
                        staging_sha256 = hashlib.sha256(staging_bytes).hexdigest()
                        if client_assertion_sha256:
                            if not hmac.compare_digest(
                                staging_sha256.lower(), client_assertion_sha256.strip().lower()
                            ):
                                still_owner = self._record_failure(upload_id, lease_token, "CHECKSUM_MISMATCH")
                                if still_owner:
                                    try:
                                        await self._storage.delete_object(staging_key)
                                    except Exception:
                                        pass
                                raise ApiError(
                                    status_code=422,
                                    code="CHECKSUM_MISMATCH",
                                    message="Actual object SHA-256 does not match client assertion.",
                                )

                        meta_source_sha = (
                            canonical_meta.custom_metadata.get("source_sha256")
                            if canonical_meta.custom_metadata
                            else None
                        )
                        if meta_source_sha and not hmac.compare_digest(
                            meta_source_sha.lower(), staging_sha256.lower()
                        ):
                            logger.warning(
                                "Crash recovery: candidate %s source_sha256 mismatch with staging",
                                expected_canonical_key,
                            )
                            staging_consistent = False
                    except ApiError:
                        raise
                    except Exception as exc:
                        logger.warning("Staging inspection during recovery error: %s", exc)
                        staging_consistent = False
                elif client_assertion_sha256:
                    meta_source_sha = (
                        canonical_meta.custom_metadata.get("source_sha256")
                        if canonical_meta.custom_metadata
                        else None
                    )
                    if not meta_source_sha or not hmac.compare_digest(
                        meta_source_sha.lower(), client_assertion_sha256.strip().lower()
                    ):
                        staging_consistent = False

                if not staging_consistent:
                    logger.warning(
                        "Crash recovery: staging consistency check failed for %s",
                        expected_canonical_key,
                    )
                    continue

                logger.info(
                    "Crash recovery: adopted verified canonical object %s for upload %s",
                    expected_canonical_key,
                    upload_id,
                )
                result = await self._finalize_published_record(
                    user_id=user_id,
                    upload_id=upload_id,
                    lease_token=lease_token,
                    canonical_key=expected_canonical_key,
                    canonical_sha256=actual_canonical_sha256,
                    size_bytes=len(canonical_bytes),
                    width=width,
                    height=height,
                    staging_key=staging_key,
                )
                pipeline_completed = True
                return result

            # Step 8: Zero-trust staging object inspection
            try:
                staging_meta = await self._storage.get_object_metadata(staging_key)
            except StorageError as exc:
                self._record_retryable_status(upload_id, lease_token)
                raise ApiError(
                    status_code=503,
                    code="STORAGE_ERROR",
                    message=f"Storage error inspecting staging object: {exc.message}",
                )

            if staging_meta is None:
                self._record_retryable_status(upload_id, lease_token)
                raise ApiError(
                    status_code=400,
                    code="STAGING_OBJECT_NOT_FOUND",
                    message="Uploaded bytes not found in storage. Ensure direct PUT completed before calling complete.",
                )

            if staging_meta.size_bytes <= 0:
                still_owner = self._record_failure(upload_id, lease_token, "EMPTY_OBJECT")
                if still_owner:
                    try:
                        await self._storage.delete_object(staging_key)
                    except Exception:
                        pass
                raise ApiError(
                    status_code=422,
                    code="EMPTY_OBJECT",
                    message="Uploaded image object is empty (0 bytes).",
                )

            if staging_meta.size_bytes > 2 * 1024 * 1024:
                still_owner = self._record_failure(upload_id, lease_token, "OBJECT_TOO_LARGE")
                if still_owner:
                    try:
                        await self._storage.delete_object(staging_key)
                    except Exception:
                        pass
                raise ApiError(
                    status_code=422,
                    code="OBJECT_TOO_LARGE",
                    message=f"Uploaded image object exceeds 2MB limit (actual: {staging_meta.size_bytes} bytes).",
                )

            # Step 9: Bounded byte stream read
            try:
                raw_bytes = await self._storage.read_object(staging_key, max_bytes=2 * 1024 * 1024)
            except StoragePayloadError as exc:
                still_owner = self._record_failure(upload_id, lease_token, "OBJECT_TOO_LARGE")
                if still_owner:
                    try:
                        await self._storage.delete_object(staging_key)
                    except Exception:
                        pass
                raise ApiError(status_code=422, code="OBJECT_TOO_LARGE", message=str(exc))
            except StorageError as exc:
                self._record_retryable_status(upload_id, lease_token)
                raise ApiError(
                    status_code=503,
                    code="STORAGE_ERROR",
                    message=f"Storage error reading staging object: {exc.message}",
                )

            # Step 10: Check client-asserted SHA-256 checksum if provided
            actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()
            if client_assertion_sha256:
                if not hmac.compare_digest(actual_sha256.lower(), client_assertion_sha256.strip().lower()):
                    still_owner = self._record_failure(upload_id, lease_token, "CHECKSUM_MISMATCH")
                    if still_owner:
                        try:
                            await self._storage.delete_object(staging_key)
                        except Exception:
                            pass
                    raise ApiError(
                        status_code=422,
                        code="CHECKSUM_MISMATCH",
                        message="Actual object SHA-256 does not match client assertion.",
                    )

            # Step 11: Validate magic bytes & cross-check declared MIME
            if len(raw_bytes) < 12:
                still_owner = self._record_failure(upload_id, lease_token, "INVALID_FILE_SIGNATURE")
                if still_owner:
                    try:
                        await self._storage.delete_object(staging_key)
                    except Exception:
                        pass
                raise ApiError(
                    status_code=422,
                    code="INVALID_FILE_SIGNATURE",
                    message="File signature is invalid.",
                )

            is_jpeg = raw_bytes[:3] == b"\xff\xd8\xff"
            is_webp = raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP"
            if not (is_jpeg or is_webp):
                still_owner = self._record_failure(upload_id, lease_token, "INVALID_FILE_SIGNATURE")
                if still_owner:
                    try:
                        await self._storage.delete_object(staging_key)
                    except Exception:
                        pass
                raise ApiError(
                    status_code=422,
                    code="INVALID_FILE_SIGNATURE",
                    message="File signature matches neither JPEG nor WebP magic bytes.",
                )

            if expected_content_type == "image/webp" and not is_webp:
                still_owner = self._record_failure(upload_id, lease_token, "CONTENT_TYPE_MISMATCH")
                if still_owner:
                    try:
                        await self._storage.delete_object(staging_key)
                    except Exception:
                        pass
                raise ApiError(
                    status_code=422,
                    code="CONTENT_TYPE_MISMATCH",
                    message=f"Payload signature does not match authorized content type '{expected_content_type}'.",
                )
            if expected_content_type == "image/jpeg" and not is_jpeg:
                still_owner = self._record_failure(upload_id, lease_token, "CONTENT_TYPE_MISMATCH")
                if still_owner:
                    try:
                        await self._storage.delete_object(staging_key)
                    except Exception:
                        pass
                raise ApiError(
                    status_code=422,
                    code="CONTENT_TYPE_MISMATCH",
                    message=f"Payload signature does not match authorized content type '{expected_content_type}'.",
                )

            # Step 12: Isolated image transcoding
            try:
                transcode_result = await self._transcoder.transcode(raw_bytes)
            except ImageValidationError as exc:
                still_owner = self._record_failure(upload_id, lease_token, exc.code)
                if still_owner:
                    try:
                        await self._storage.delete_object(staging_key)
                    except Exception:
                        pass
                raise ApiError(status_code=422, code=exc.code, message=exc.message)
            except TranscodingTimeoutError as exc:
                self._record_retryable_status(upload_id, lease_token)
                raise ApiError(status_code=500, code="TRANSCODING_TIMEOUT", message=exc.message)
            except MemoryLimitExceededError as exc:
                still_owner = self._record_failure(upload_id, lease_token, exc.code)
                if still_owner:
                    try:
                        await self._storage.delete_object(staging_key)
                    except Exception:
                        pass
                raise ApiError(status_code=422, code="DECOMPRESSION_BOMB", message=exc.message)
            except TranscodingError as exc:
                self._record_failure(upload_id, lease_token, exc.code)
                raise ApiError(status_code=500, code=exc.code, message=exc.message)

            # Step 13: Publish immutable attempt WebP object to private storage
            # Pre-PUT Fencing Gate: verify we still hold the valid lease before initiating network I/O
            still_holding_lease = self.renew_lease(upload_id, lease_token, extend_seconds=self._lease_seconds)
            if not still_holding_lease:
                logger.warning(
                    "Upload %s: pre-PUT fencing check failed; lease ownership lost for token %s. Aborting before storage write.",
                    upload_id,
                    lease_token,
                )
                raise ApiError(
                    status_code=409,
                    code="LEASE_LOST",
                    message="Processing lease ownership was lost before storage write could begin.",
                )

            attempt_key = get_attempt_object_key(user_id, upload_id, lease_token)
            try:
                await self._storage.put_object(
                    key=attempt_key,
                    data=transcode_result.canonical_bytes,
                    content_type="image/webp",
                    custom_metadata={
                        "user_id": str(user_id),
                        "upload_id": str(upload_id),
                        "lease_token": str(lease_token),
                        "sha256": transcode_result.canonical_sha256,
                        "width": str(transcode_result.width),
                        "height": str(transcode_result.height),
                        "source_sha256": actual_sha256,
                    },
                )
            except StorageError as exc:
                self._record_retryable_status(upload_id, lease_token)
                raise ApiError(
                    status_code=503,
                    code="STORAGE_ERROR",
                    message=f"Storage error writing canonical object: {exc.message}",
                )

            # Step 14: Persist published status in database and clear lease
            result = await self._finalize_published_record(
                user_id=user_id,
                upload_id=upload_id,
                lease_token=lease_token,
                canonical_key=attempt_key,
                canonical_sha256=transcode_result.canonical_sha256,
                size_bytes=transcode_result.canonical_size_bytes,
                width=transcode_result.width,
                height=transcode_result.height,
                staging_key=staging_key,
            )
            pipeline_completed = True
            return result
        finally:
            if not pipeline_completed:
                self._record_retryable_status(upload_id, lease_token)

    async def _finalize_published_record(
        self,
        *,
        user_id: UUID,
        upload_id: UUID,
        lease_token: UUID,
        canonical_key: str,
        canonical_sha256: str,
        size_bytes: int,
        width: int,
        height: int,
        staging_key: str,
    ) -> dict[str, Any]:
        """Finalize publication in DB conditional on holding active lease token."""
        is_postgres = False
        try:
            bind = self._db.get_bind()
            if bind is not None and getattr(bind.dialect, "name", "") == "postgresql":
                is_postgres = True
        except Exception:
            pass
        completed_at = _get_db_wallclock(self._db, is_postgres)

        try:
            stmt = (
                update(MediaUploadAuthorization)
                .where(
                    MediaUploadAuthorization.user_id == user_id,
                    MediaUploadAuthorization.upload_id == upload_id,
                    MediaUploadAuthorization.processing_lease_token == lease_token,
                    MediaUploadAuthorization.status == "processing",
                )
                .values(
                    status="published",
                    canonical_key=canonical_key,
                    canonical_sha256=canonical_sha256,
                    canonical_size_bytes=size_bytes,
                    canonical_width=width,
                    canonical_height=height,
                    completed_at=completed_at,
                    processing_lease_expires_at=None,
                    processing_lease_token=None,
                )
            )
            res = self._db.execute(stmt)
            if (res.rowcount or 0) == 0:
                self._db.rollback()
                logger.warning(
                    "Upload %s finalization aborted: lease token %s lost ownership",
                    upload_id,
                    lease_token,
                )
                raise ApiError(
                    status_code=409,
                    code="LEASE_LOST",
                    message="Processing lease ownership was lost before publication could be finalized.",
                )
            self._db.commit()
        except ApiError:
            raise
        except Exception as exc:
            self._db.rollback()
            logger.error("Database failure persisting published record for upload %s: %s", upload_id, exc)
            raise database_failure()

        # Deterministic deletion of staging object (non-blocking on failure, only after ownership verified)
        try:
            await self._storage.delete_object(staging_key)
        except Exception as exc:
            logger.warning("Failed to delete staging object %s: %s", staging_key, exc)

        return {
            "uploadId": upload_id,
            "objectKey": canonical_key,
            "mediaType": "image/webp",
            "width": width,
            "height": height,
            "sizeBytes": size_bytes,
            "contentHash": canonical_sha256,
            "uploadedAt": completed_at,
            "status": "ready",
        }


def validate_media_association(
    *,
    db: Session,
    user_id: UUID,
    image_ref: Any,
) -> dict[str, Any] | None:
    """Validate client-supplied media reference and return trusted canonical MediaRef dict (Stage 2 P0-4 Gate 1 / F-04).

    Enforces:
    1. Authenticated OW-1 ownership scoping.
    2. Resolves MediaUploadAuthorization from PostgreSQL.
    3. Rejects nonexistent uploads and foreign-user uploads with identical 404 MEDIA_NOT_FOUND (non-revealing).
    4. Rejects unpublished uploads:
       - Status 'authorized' or 'processing' -> 409 UNPUBLISHED_MEDIA
       - Status 'failed' -> 422 FAILED_MEDIA
       - Other non-published -> 422 UNPUBLISHED_MEDIA
    5. Confirms canonical key presence and validates user-specific namespace:
       `users/{user_id}/wardrobe/{upload_id}/` prefix and `.webp` suffix.
       Rejects staging keys (`staging/...`) and arbitrary bucket keys with 422.
    6. Confirms canonical metadata consistency:
       - canonical_sha256 is present and 64 lowercase hex characters
       - canonical_width and canonical_height are positive integers
       - canonical_size_bytes is positive integer
       Rejects corrupt or incomplete publication records with 422 CORRUPT_MEDIA_METADATA.
    7. If client provided an objectKey assertion, verifies it matches canonical_key.
       Rejects mismatch with 422 INVALID_MEDIA_REFERENCE.
    8. Derives the trusted canonical MediaRef dict strictly from PostgreSQL records.
       Client-supplied contents are never trusted as proof of publication or ownership.
    """
    if image_ref is None:
        return None

    client_key: Optional[str] = None
    upload_id_raw: Any = None

    if hasattr(image_ref, "uploadId"):
        upload_id_raw = getattr(image_ref, "uploadId")
        client_key = getattr(image_ref, "objectKey", None)
    elif isinstance(image_ref, dict):
        upload_id_raw = image_ref.get("uploadId") or image_ref.get("upload_id")
        client_key = image_ref.get("objectKey") or image_ref.get("object_key")
    else:
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="imageRef must be a valid media reference object with uploadId.",
            details={"field": "imageRef"},
        )

    if not upload_id_raw:
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="imageRef must contain a valid uploadId.",
            details={"field": "imageRef.uploadId"},
        )

    try:
        if isinstance(upload_id_raw, UUID):
            upload_id = upload_id_raw
        else:
            upload_id = UUID(str(upload_id_raw).strip())
    except (ValueError, TypeError, AttributeError):
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="uploadId must be a valid UUID.",
            details={"field": "imageRef.uploadId"},
        )

    stmt = select(MediaUploadAuthorization).where(
        MediaUploadAuthorization.upload_id == upload_id,
        MediaUploadAuthorization.user_id == user_id,
    )
    auth = db.execute(stmt).scalar_one_or_none()

    if auth is None:
        raise ApiError(
            status_code=404,
            code="MEDIA_NOT_FOUND",
            message="Referenced media upload not found.",
            details={"uploadId": str(upload_id)},
        )

    if auth.status in ("authorized", "processing"):
        raise ApiError(
            status_code=409,
            code="UNPUBLISHED_MEDIA",
            message="Media upload has not been published yet.",
            details={"uploadId": str(upload_id), "status": auth.status},
        )
    if auth.status == "failed":
        raise ApiError(
            status_code=422,
            code="FAILED_MEDIA",
            message="Media upload failed verification and cannot be associated.",
            details={"uploadId": str(upload_id), "failureReason": auth.failure_reason},
        )
    if auth.status != "published":
        raise ApiError(
            status_code=422,
            code="UNPUBLISHED_MEDIA",
            message=f"Media upload status is '{auth.status}'. Only published media can be associated.",
            details={"uploadId": str(upload_id), "status": auth.status},
        )

    canonical_key = auth.canonical_key
    if not canonical_key:
        raise ApiError(
            status_code=422,
            code="CORRUPT_MEDIA_METADATA",
            message="Published media record is missing canonical object key.",
            details={"uploadId": str(upload_id)},
        )

    if "staging/" in canonical_key:
        raise ApiError(
            status_code=422,
            code="CORRUPT_MEDIA_METADATA",
            message="Canonical key cannot point to staging namespace.",
            details={"uploadId": str(upload_id)},
        )

    expected_prefix = f"users/{str(user_id)}/wardrobe/{str(upload_id)}/"
    if not canonical_key.startswith(expected_prefix) or not canonical_key.endswith(".webp"):
        raise ApiError(
            status_code=422,
            code="CORRUPT_MEDIA_METADATA",
            message="Canonical key does not conform to authorized wardrobe namespace.",
            details={"uploadId": str(upload_id), "key": canonical_key},
        )

    sha = auth.canonical_sha256
    if not sha or len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha.lower()):
        raise ApiError(
            status_code=422,
            code="CORRUPT_MEDIA_METADATA",
            message="Published media record has invalid canonical SHA-256 digest.",
            details={"uploadId": str(upload_id)},
        )

    width = auth.canonical_width
    height = auth.canonical_height
    if not width or width <= 0 or not height or height <= 0:
        raise ApiError(
            status_code=422,
            code="CORRUPT_MEDIA_METADATA",
            message="Published media record has invalid image dimensions.",
            details={"uploadId": str(upload_id)},
        )

    size_bytes = auth.canonical_size_bytes
    if not size_bytes or size_bytes <= 0 or size_bytes > 2 * 1024 * 1024:
        raise ApiError(
            status_code=422,
            code="CORRUPT_MEDIA_METADATA",
            message="Published media record has invalid image size.",
            details={"uploadId": str(upload_id)},
        )

    if client_key and client_key.strip() != canonical_key:
        raise ApiError(
            status_code=422,
            code="INVALID_MEDIA_REFERENCE",
            message="Client-asserted objectKey does not match published canonical key.",
            details={"uploadId": str(upload_id), "clientKey": client_key, "canonicalKey": canonical_key},
        )

    return {
        "uploadId": str(auth.upload_id),
        "objectKey": canonical_key,
        "mediaType": "image/webp",
        "width": width,
        "height": height,
        "sizeBytes": size_bytes,
        "contentHash": sha.lower(),
        "uploadedAt": auth.completed_at.isoformat() if auth.completed_at else None,
        "status": "ready",
    }


class GetMediaUrl:
    """Stage 2 P0-4 Phase 4: Media retrieval service for authenticated published media."""

    def __init__(self, storage: ObjectStoragePort, db: Session) -> None:
        self._storage = storage
        self._db = db

    async def execute(
        self,
        *,
        user_id: UUID,
        upload_id: Optional[UUID] = None,
        object_key: Optional[str] = None,
        expires_in_s: int = 900,
    ) -> dict[str, Any]:
        """Mint a short-lived presigned GET URL for verified published media under OW-1."""
        if upload_id is None and not object_key:
            raise ApiError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="Either uploadId or objectKey must be specified.",
            )

        if object_key and "staging/" in object_key:
            raise ApiError(
                status_code=404,
                code="MEDIA_NOT_FOUND",
                message="Referenced media not found.",
            )

        query = select(MediaUploadAuthorization).where(
            MediaUploadAuthorization.user_id == user_id,
            MediaUploadAuthorization.status == "published",
        )
        if upload_id is not None:
            query = query.where(MediaUploadAuthorization.upload_id == upload_id)
        if object_key:
            clean_key = object_key.strip()
            query = query.where(MediaUploadAuthorization.canonical_key == clean_key)

        auth = self._db.execute(query).scalar_one_or_none()
        if auth is None or not auth.canonical_key:
            raise ApiError(
                status_code=404,
                code="MEDIA_NOT_FOUND",
                message="Referenced media not found.",
            )

        expected_prefix = f"users/{str(user_id)}/wardrobe/{str(auth.upload_id)}/"
        if not auth.canonical_key.startswith(expected_prefix) or not auth.canonical_key.endswith(".webp"):
            raise ApiError(
                status_code=404,
                code="MEDIA_NOT_FOUND",
                message="Referenced media not found.",
            )

        try:
            download_url = await self._storage.generate_presigned_get_url(
                key=auth.canonical_key,
                expires_in_s=expires_in_s,
            )
        except Exception as exc:
            logger.error("Presigned GET URL generation failed: %s", exc)
            raise ApiError(
                status_code=500,
                code="STORAGE_SIGNING_ERROR",
                message="Failed to generate presigned download URL.",
            )

        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=expires_in_s)

        return {
            "uploadId": auth.upload_id,
            "objectKey": auth.canonical_key,
            "downloadUrl": download_url,
            "mediaType": "image/webp",
            "width": auth.canonical_width,
            "height": auth.canonical_height,
            "sizeBytes": auth.canonical_size_bytes,
            "contentHash": auth.canonical_sha256,
            "expiresAt": expires_at,
            "expiresInSeconds": expires_in_s,
        }
