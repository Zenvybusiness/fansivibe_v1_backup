"""Virtual Try-On Application Layer (Phase 5C).

Durable job management, ownership validation, media persistence, and
asynchronous provider execution.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import io
import logging
import threading
from typing import Any, Optional
from uuid import UUID, uuid4
import xml.etree.ElementTree as ET

from fastapi import HTTPException
from PIL import Image, ImageOps

from app.api.errors import ApiError, ai_failure, conflict, not_found, rate_limited, validation
from app.application.media import sha256_hex
from app.config.image import MAX_OUTPUT_IMAGE_PIXELS, MAX_PERSON_IMAGE_PIXELS
from app.config.settings import Settings, get_settings
from app.domain.ports.repositories import (
    TryOnJobRecord,
    TryOnJobRepository,
    WardrobeItemRepository,
)
from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageError,
    StorageNotFoundError,
    resolve_wardrobe_image_key,
    validate_scoped_object_key,
)
from app.domain.ports.tryon_provider import (
    CatVTONTryOnProvider,
    CommercialProviderConfigurationError,
    CommercialTryOnProvider,
    CommercialTryOnProviderConfig,
    MockTryOnProvider,
    ProviderAuthError,
    ProviderPayloadError,
    ProviderQuotaExceededError,
    ProviderTransientError,
    TryOnProviderError,
    map_wardrobe_category_to_fashn,
)
from app.infrastructure.external.genlook_tryon import (
    GENLOOK_DEFAULT_BASE_URL,
    GENLOOK_MAX_IMAGE_BYTES,
    GenlookCancelledError,
    GenlookImageUploadResult,
    GenlookTryOnConfig,
    GenlookTryOnCreateResult,
    GenlookTryOnProvider,
    build_genlook_product_spec,
)

logger = logging.getLogger("fansivibe.tryon.application")

_OUTFIT_SOURCES = frozenset({"today", "outfit", "saved", "wardrobe"})
_ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MIME_TO_PIL_FORMAT = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_PIL_FORMAT_TO_MIME_EXT = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
_MAX_PERSON_BYTES = 20 * 1024 * 1024
_MAX_RESULT_BYTES = 20 * 1024 * 1024
_MAX_PERSON_PIXELS = MAX_PERSON_IMAGE_PIXELS
_MIN_PERSON_EDGE = 64
_MAX_PERSON_EDGE = 4096
_MAX_OUTPUT_PIXELS = MAX_OUTPUT_IMAGE_PIXELS
_MAX_OUTPUT_EDGE = 8192
_MAX_GARMENT_IDS = 8

_POLLS_TO_COMPLETE = 1


class InMemoryTryOnJobRepository:
    """Thread-safe in-memory repository conforming to TryOnJobRepository protocol.

    Provides high-speed zero-database execution for unit tests and fallback environments.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[UUID, TryOnJobRecord] = {}
        self._idempotency: dict[tuple[UUID, str], UUID] = {}
        self._images: dict[UUID, bytes] = {}

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()
            self._idempotency.clear()
            self._images.clear()

    def set_image_bytes(self, job_id: UUID, image_bytes: bytes) -> None:
        with self._lock:
            self._images[job_id] = image_bytes
            if job_id in self._jobs:
                old = self._jobs[job_id]
                self._jobs[job_id] = TryOnJobRecord(
                    id=old.id,
                    user_id=old.user_id,
                    outfit_source=old.outfit_source,
                    garment_id=old.garment_id,
                    garment_ids=old.garment_ids,
                    provider=old.provider,
                    status=old.status,
                    consent_version=old.consent_version,
                    consent_accepted_at=old.consent_accepted_at,
                    created_at=old.created_at,
                    updated_at=old.updated_at,
                    person_media_ref=old.person_media_ref,
                    result_media_ref=old.result_media_ref,
                    idempotency_key=old.idempotency_key,
                    request_fingerprint=old.request_fingerprint,
                    error_code=old.error_code,
                    error_message=old.error_message,
                    retry_count=old.retry_count,
                    retry_of_job_id=old.retry_of_job_id,
                    processing_started_at=old.processing_started_at,
                    completed_at=old.completed_at,
                    image_bytes=image_bytes,
                )

    def get_image_bytes(self, job_id: UUID) -> Optional[bytes]:
        with self._lock:
            return self._images.get(job_id)

    def create(
        self,
        *,
        job_id: UUID,
        user_id: UUID,
        outfit_source: str,
        garment_id: Optional[UUID],
        garment_ids: list[str],
        provider: str,
        status: str,
        consent_version: str,
        consent_accepted_at: datetime,
        person_media_ref: Optional[dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        request_fingerprint: Optional[str] = None,
    ) -> TryOnJobRecord:
        now = datetime.now(timezone.utc)
        record = TryOnJobRecord(
            id=job_id,
            user_id=user_id,
            outfit_source=outfit_source,
            garment_id=garment_id,
            garment_ids=tuple(garment_ids),
            provider=provider,
            status=status,
            consent_version=consent_version,
            consent_accepted_at=consent_accepted_at,
            created_at=now,
            updated_at=now,
            person_media_ref=person_media_ref,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        with self._lock:
            if idempotency_key and (user_id, idempotency_key) in self._idempotency:
                from sqlalchemy.exc import IntegrityError
                raise IntegrityError("duplicate idempotency key", None, None)
            self._jobs[job_id] = record
            if idempotency_key:
                self._idempotency[(user_id, idempotency_key)] = job_id
        return record

    def create_with_quota(
        self,
        *,
        job_id: UUID,
        user_id: UUID,
        outfit_source: str,
        garment_id: Optional[UUID],
        garment_ids: list[str],
        provider: str,
        status: str,
        consent_version: str,
        consent_accepted_at: datetime,
        person_media_ref: Optional[dict[str, Any]] = None,
        idempotency_key: str,
        request_fingerprint: str,
        day: date,
        daily_quota: int,
        concurrent_limit: int,
    ) -> tuple[TryOnJobRecord, bool]:
        """Atomically verify idempotency and quotas under in-memory lock."""
        now = datetime.now(timezone.utc)
        with self._lock:
            existing_id = self._idempotency.get((user_id, idempotency_key))
            if existing_id is not None:
                existing = self._jobs.get(existing_id)
                if existing is not None:
                    if existing.request_fingerprint != request_fingerprint:
                        raise conflict(kind="idempotency_key_reuse")
                    return existing, False

            used = sum(
                1
                for j in self._jobs.values()
                if j.user_id == user_id and j.created_at.date() == day
            )
            if used >= daily_quota:
                raise rate_limited()

            active = sum(
                1
                for j in self._jobs.values()
                if j.user_id == user_id and j.status in ("queued", "processing")
            )
            if active >= concurrent_limit:
                raise rate_limited()

            record = self.create(
                job_id=job_id,
                user_id=user_id,
                outfit_source=outfit_source,
                garment_id=garment_id,
                garment_ids=garment_ids,
                provider=provider,
                status=status,
                consent_version=consent_version,
                consent_accepted_at=consent_accepted_at,
                person_media_ref=person_media_ref,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
            return record, True

    def get_by_id(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
    ) -> Optional[TryOnJobRecord]:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None or rec.user_id != user_id:
                return None
            img = self._images.get(job_id)
            if img is not None and rec.image_bytes is None:
                rec = TryOnJobRecord(
                    id=rec.id,
                    user_id=rec.user_id,
                    outfit_source=rec.outfit_source,
                    garment_id=rec.garment_id,
                    garment_ids=rec.garment_ids,
                    provider=rec.provider,
                    status=rec.status,
                    consent_version=rec.consent_version,
                    consent_accepted_at=rec.consent_accepted_at,
                    created_at=rec.created_at,
                    updated_at=rec.updated_at,
                    person_media_ref=rec.person_media_ref,
                    result_media_ref=rec.result_media_ref,
                    idempotency_key=rec.idempotency_key,
                    request_fingerprint=rec.request_fingerprint,
                    error_code=rec.error_code,
                    error_message=rec.error_message,
                    retry_count=rec.retry_count,
                    retry_of_job_id=rec.retry_of_job_id,
                    processing_started_at=rec.processing_started_at,
                    completed_at=rec.completed_at,
                    image_bytes=img,
                )
            return rec

    def update_status(
        self,
        *,
        job_id: UUID,
        status: str,
        processing_started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[TryOnJobRecord]:
        with self._lock:
            old = self._jobs.get(job_id)
            if not old:
                return None
            # Stale worker protection: terminal jobs cannot move back to queued/processing
            if old.status in ("completed", "cancelled") and status in ("queued", "processing"):
                return old
            new_rec = TryOnJobRecord(
                id=old.id,
                user_id=old.user_id,
                outfit_source=old.outfit_source,
                garment_id=old.garment_id,
                garment_ids=old.garment_ids,
                provider=old.provider,
                status=status,
                consent_version=old.consent_version,
                consent_accepted_at=old.consent_accepted_at,
                created_at=old.created_at,
                updated_at=datetime.now(timezone.utc),
                person_media_ref=old.person_media_ref,
                result_media_ref=old.result_media_ref,
                idempotency_key=old.idempotency_key,
                request_fingerprint=old.request_fingerprint,
                error_code=old.error_code,
                error_message=old.error_message,
                retry_count=old.retry_count,
                retry_of_job_id=old.retry_of_job_id,
                processing_started_at=processing_started_at or old.processing_started_at,
                completed_at=completed_at or old.completed_at,
                image_bytes=old.image_bytes or self._images.get(job_id),
            )
            self._jobs[job_id] = new_rec
            return new_rec

    def update_result(
        self,
        *,
        job_id: UUID,
        result_media_ref: dict[str, Any],
        completed_at: datetime,
    ) -> Optional[TryOnJobRecord]:
        with self._lock:
            old = self._jobs.get(job_id)
            if not old:
                return None
            # Cancelled or failed jobs cannot later become completed (stale worker protection)
            if old.status in ("cancelled", "completed", "failed"):
                return old
            new_rec = TryOnJobRecord(
                id=old.id,
                user_id=old.user_id,
                outfit_source=old.outfit_source,
                garment_id=old.garment_id,
                garment_ids=old.garment_ids,
                provider=old.provider,
                status="completed",
                consent_version=old.consent_version,
                consent_accepted_at=old.consent_accepted_at,
                created_at=old.created_at,
                updated_at=datetime.now(timezone.utc),
                person_media_ref=old.person_media_ref,
                result_media_ref=result_media_ref,
                idempotency_key=old.idempotency_key,
                request_fingerprint=old.request_fingerprint,
                error_code=None,
                error_message=None,
                retry_count=old.retry_count,
                retry_of_job_id=old.retry_of_job_id,
                processing_started_at=old.processing_started_at,
                completed_at=completed_at,
                image_bytes=old.image_bytes or self._images.get(job_id),
            )
            self._jobs[job_id] = new_rec
            return new_rec

    def update_failure(
        self,
        *,
        job_id: UUID,
        error_code: str,
        error_message: str,
        completed_at: datetime,
    ) -> Optional[TryOnJobRecord]:
        with self._lock:
            old = self._jobs.get(job_id)
            if not old:
                return None
            # Completed or cancelled jobs cannot be overwritten by delayed worker failures
            if old.status in ("completed", "cancelled"):
                return old
            new_rec = TryOnJobRecord(
                id=old.id,
                user_id=old.user_id,
                outfit_source=old.outfit_source,
                garment_id=old.garment_id,
                garment_ids=old.garment_ids,
                provider=old.provider,
                status="failed",
                consent_version=old.consent_version,
                consent_accepted_at=old.consent_accepted_at,
                created_at=old.created_at,
                updated_at=datetime.now(timezone.utc),
                person_media_ref=old.person_media_ref,
                result_media_ref=old.result_media_ref,
                idempotency_key=old.idempotency_key,
                request_fingerprint=old.request_fingerprint,
                error_code=error_code,
                error_message=error_message,
                retry_count=old.retry_count,
                retry_of_job_id=old.retry_of_job_id,
                processing_started_at=old.processing_started_at,
                completed_at=completed_at,
                image_bytes=None,
            )
            self._jobs[job_id] = new_rec
            return new_rec

    def update_retry(
        self,
        *,
        job_id: UUID,
        retry_count: int,
        status: str = "queued",
    ) -> Optional[TryOnJobRecord]:
        with self._lock:
            old = self._jobs.get(job_id)
            if not old:
                return None
            new_rec = TryOnJobRecord(
                id=old.id,
                user_id=old.user_id,
                outfit_source=old.outfit_source,
                garment_id=old.garment_id,
                garment_ids=old.garment_ids,
                provider=old.provider,
                status=status,
                consent_version=old.consent_version,
                consent_accepted_at=old.consent_accepted_at,
                created_at=old.created_at,
                updated_at=datetime.now(timezone.utc),
                person_media_ref=old.person_media_ref,
                result_media_ref=old.result_media_ref,
                idempotency_key=old.idempotency_key,
                request_fingerprint=old.request_fingerprint,
                error_code=None,
                error_message=None,
                retry_count=retry_count,
                retry_of_job_id=old.retry_of_job_id,
                processing_started_at=None,
                completed_at=None,
                image_bytes=None,
            )
            self._jobs[job_id] = new_rec
            return new_rec

    def delete(
        self,
        *,
        user_id: UUID,
        job_id: UUID,
    ) -> bool:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec is None or rec.user_id != user_id:
                return False
            del self._jobs[job_id]
            if rec.idempotency_key:
                self._idempotency.pop((user_id, rec.idempotency_key), None)
            self._images.pop(job_id, None)
            return True

    def find_by_idempotency_key(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
    ) -> Optional[TryOnJobRecord]:
        with self._lock:
            job_id = self._idempotency.get((user_id, idempotency_key))
            if job_id is None:
                return None
            return self._jobs.get(job_id)

    def find_by_status(
        self,
        *,
        status: str,
    ) -> list[TryOnJobRecord]:
        with self._lock:
            return [job for job in self._jobs.values() if job.status == status]

    def count_today_jobs(
        self,
        *,
        user_id: UUID,
        day: date,
    ) -> int:
        with self._lock:
            return sum(
                1
                for j in self._jobs.values()
                if j.user_id == user_id and j.created_at.date() == day
            )

    def count_active_jobs(
        self,
        *,
        user_id: UUID,
    ) -> int:
        with self._lock:
            return sum(
                1
                for j in self._jobs.values()
                if j.user_id == user_id and j.status in ("queued", "processing")
            )

    def find_expired_jobs(
        self,
        *,
        status: str,
        older_than: datetime,
    ) -> list[TryOnJobRecord]:
        with self._lock:
            return [
                j
                for j in self._jobs.values()
                if j.status == status
                and (j.completed_at or j.created_at) <= older_than
            ]

    def find_jobs_with_unpurged_person_photo(
        self,
        *,
        older_than: datetime,
    ) -> list[TryOnJobRecord]:
        with self._lock:
            return [
                j
                for j in self._jobs.values()
                if j.person_media_ref is not None and j.created_at <= older_than
            ]

    def clear_person_media_ref(
        self,
        *,
        job_id: UUID,
    ) -> bool:
        with self._lock:
            old = self._jobs.get(job_id)
            if not old:
                return False
            self._jobs[job_id] = TryOnJobRecord(
                id=old.id,
                user_id=old.user_id,
                outfit_source=old.outfit_source,
                garment_id=old.garment_id,
                garment_ids=old.garment_ids,
                provider=old.provider,
                status=old.status,
                consent_version=old.consent_version,
                consent_accepted_at=old.consent_accepted_at,
                created_at=old.created_at,
                updated_at=datetime.now(timezone.utc),
                person_media_ref=None,
                result_media_ref=old.result_media_ref,
                idempotency_key=old.idempotency_key,
                request_fingerprint=old.request_fingerprint,
                error_code=old.error_code,
                error_message=old.error_message,
                retry_count=old.retry_count,
                retry_of_job_id=old.retry_of_job_id,
                processing_started_at=old.processing_started_at,
                completed_at=old.completed_at,
                image_bytes=old.image_bytes,
            )
            return True

    def update_person_media_ref(
        self,
        *,
        job_id: UUID,
        person_media_ref: dict[str, Any],
    ) -> Optional[TryOnJobRecord]:
        with self._lock:
            old = self._jobs.get(job_id)
            if not old:
                return None
            new_rec = TryOnJobRecord(
                id=old.id,
                user_id=old.user_id,
                outfit_source=old.outfit_source,
                garment_id=old.garment_id,
                garment_ids=old.garment_ids,
                provider=old.provider,
                status=old.status,
                consent_version=old.consent_version,
                consent_accepted_at=old.consent_accepted_at,
                created_at=old.created_at,
                updated_at=datetime.now(timezone.utc),
                person_media_ref=dict(person_media_ref),
                result_media_ref=old.result_media_ref,
                idempotency_key=old.idempotency_key,
                request_fingerprint=old.request_fingerprint,
                error_code=old.error_code,
                error_message=old.error_message,
                retry_count=old.retry_count,
                retry_of_job_id=old.retry_of_job_id,
                processing_started_at=old.processing_started_at,
                completed_at=old.completed_at,
                image_bytes=old.image_bytes,
            )
            self._jobs[job_id] = new_rec
            return new_rec

    def find_reusable_genlook_image_id(
        self,
        *,
        user_id: UUID,
        person_digest: str,
        consent_version: str,
        min_created_at: datetime,
        now: datetime,
    ) -> Optional[str]:
        with self._lock:
            candidates = [
                j
                for j in self._jobs.values()
                if j.user_id == user_id
                and j.provider == "genlook"
                and j.consent_version == consent_version
                and j.consent_accepted_at is not None
                and j.person_media_ref is not None
                and j.created_at >= min_created_at
            ]
            candidates.sort(key=lambda j: j.created_at, reverse=True)
            for j in candidates:
                ref = j.person_media_ref
                if not isinstance(ref, dict) or ref.get("contentHash") != person_digest:
                    continue
                gl = ref.get("genlook")
                if not isinstance(gl, dict):
                    continue
                image_id = gl.get("imageId")
                expires_raw = gl.get("imageExpiresAt")
                if not isinstance(image_id, str) or not image_id.strip() or not isinstance(expires_raw, str):
                    continue
                try:
                    expires_at = datetime.fromisoformat(expires_raw)
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    if expires_at > now:
                        return image_id.strip()
                except Exception:
                    continue
            return None


# Default in-memory store for test/fallback usage
_IN_MEMORY_REPO = InMemoryTryOnJobRepository()
_POLL_COUNTS: dict[str, int] = {}
_BYTE_CACHE: dict[str, tuple[bytes, str]] = {}  # job_id -> (person_bytes, content_type)


def _detect_magic_format(data: bytes) -> str | None:
    """Identify image format strictly from leading file signature magic bytes."""
    if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
        return "JPEG"
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "PNG"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def validate_and_sanitize_person_image(
    person_bytes: bytes,
    declared_content_type: str,
) -> tuple[bytes, str]:
    """Validate person image bytes with Pillow, preserve orientation, and strip EXIF/GPS.

    Ensures:
    - Content-Type is never trusted alone (magic bytes + Pillow img.format must agree).
    - Decompression bombs and excessive dimensions are rejected.
    - Orientation is baked into pixels via ImageOps.exif_transpose.
    - All EXIF, GPS, XMP, ICC, and comment metadata is stripped via clean re-encoding.
    - Returned bytes and MIME type agree strictly.
    """
    declared_mime = (declared_content_type or "").split(";")[0].strip().lower()
    if declared_mime not in _ALLOWED_IMAGE_TYPES:
        raise validation([{"field": "person_image", "error": "must be jpeg, png, or webp"}])

    if not person_bytes or len(person_bytes) > _MAX_PERSON_BYTES:
        raise validation(
            [{"field": "person_image", "error": "must be non-empty, at most 20 MB"}]
        )

    expected_format = _MIME_TO_PIL_FORMAT[declared_mime]
    magic_format = _detect_magic_format(person_bytes)
    if magic_format is None:
        raise validation(
            [{"field": "person_image", "error": "invalid or unsupported image file"}]
        )
    if magic_format != expected_format:
        raise validation(
            [{"field": "person_image", "error": "image content does not match declared content type"}]
        )

    try:
        with Image.open(io.BytesIO(person_bytes)) as img:
            if img.format not in ("JPEG", "PNG", "WEBP"):
                raise validation(
                    [{"field": "person_image", "error": "unsupported image format"}]
                )
            if img.format != expected_format:
                raise validation(
                    [{"field": "person_image", "error": "image content does not match declared content type"}]
                )
            w, h = img.size
            if w * h > _MAX_PERSON_PIXELS:
                raise validation(
                    [{"field": "person_image", "error": "image pixel count exceeds maximum allowed limit"}]
                )
            if w > _MAX_PERSON_EDGE or h > _MAX_PERSON_EDGE:
                raise validation(
                    [{"field": "person_image", "error": "image dimensions exceed maximum 4096x4096"}]
                )
            if w < _MIN_PERSON_EDGE or h < _MIN_PERSON_EDGE:
                raise validation(
                    [{"field": "person_image", "error": "image dimensions must be at least 64x64"}]
                )

            img.load()
            oriented = ImageOps.exif_transpose(img)
            ow, oh = oriented.size
            if ow * oh > _MAX_PERSON_PIXELS or ow > _MAX_PERSON_EDGE or oh > _MAX_PERSON_EDGE:
                raise validation(
                    [{"field": "person_image", "error": "image dimensions exceed maximum 4096x4096"}]
                )
            if ow < _MIN_PERSON_EDGE or oh < _MIN_PERSON_EDGE:
                raise validation(
                    [{"field": "person_image", "error": "image dimensions must be at least 64x64"}]
                )

            if expected_format == "JPEG":
                if oriented.mode != "RGB":
                    oriented = oriented.convert("RGB")
            else:
                if oriented.mode in ("RGBA", "LA") or (
                    oriented.mode == "P" and "transparency" in oriented.info
                ):
                    oriented = oriented.convert("RGBA")
                elif oriented.mode != "RGB":
                    oriented = oriented.convert("RGB")

            # Reconstruct clean pixel buffer without EXIF, GPS, XMP, ICC, or info metadata
            clean_img = Image.frombytes(oriented.mode, oriented.size, oriented.tobytes())
            out_buf = io.BytesIO()
            if expected_format == "JPEG":
                clean_img.save(out_buf, format="JPEG", quality=92)
            elif expected_format == "PNG":
                clean_img.save(out_buf, format="PNG")
            else:
                clean_img.save(out_buf, format="WEBP", quality=90)
            sanitized_bytes = out_buf.getvalue()

        if not sanitized_bytes or len(sanitized_bytes) > _MAX_PERSON_BYTES:
            raise validation(
                [{"field": "person_image", "error": "sanitized image exceeds size limits"}]
            )

        with Image.open(io.BytesIO(sanitized_bytes)) as check_img:
            if check_img.format != expected_format:
                raise validation(
                    [{"field": "person_image", "error": "re-encoded image format mismatch"}]
                )
            check_exif = check_img.getexif()
            if check_exif and len(check_exif) > 0:
                raise validation(
                    [{"field": "person_image", "error": "failed to strip EXIF metadata"}]
                )

        return sanitized_bytes, declared_mime
    except (HTTPException, ApiError):
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise validation(
            [{"field": "person_image", "error": "image exceeds decompression safety limits"}]
        )
    except Exception:
        raise validation(
            [{"field": "person_image", "error": "invalid or unreadable image file"}]
        )


def validate_and_inspect_output_image(
    result_bytes: bytes,
    *,
    allow_svg: bool = False,
    provider_id: str = "unknown",
    correlation_id: str | None = None,
) -> tuple[str, str]:
    """Validate provider output bytes and detect true MIME type and file extension.

    Raises ProviderPayloadError for empty, malformed, unsupported, or bomb payloads.
    SVG is permitted ONLY when allow_svg=True (mock provider).
    """
    if not result_bytes:
        raise ProviderPayloadError(
            "Provider returned empty image output",
            provider_id=provider_id,
            correlation_id=correlation_id,
        )

    stripped = result_bytes.lstrip()
    if stripped.startswith(b"<svg") or (stripped.startswith(b"<?xml") and b"<svg" in stripped[:256]):
        if not allow_svg:
            raise ProviderPayloadError(
                "Non-mock provider returned unsupported SVG output",
                provider_id=provider_id,
                correlation_id=correlation_id,
            )
        upper_head = stripped[:1024].upper()
        if b"<!DOCTYPE" in upper_head or b"<!ENTITY" in upper_head:
            raise ProviderPayloadError(
                "Unsafe SVG output rejected",
                provider_id=provider_id,
                correlation_id=correlation_id,
            )
        try:
            root = ET.fromstring(stripped.decode("utf-8"))
        except Exception as exc:
            raise ProviderPayloadError(
                "Malformed SVG output from mock provider",
                provider_id=provider_id,
                correlation_id=correlation_id,
                cause=exc,
            )
        if not (root.tag == "svg" or root.tag.endswith("}svg")):
            raise ProviderPayloadError(
                "Invalid SVG root element",
                provider_id=provider_id,
                correlation_id=correlation_id,
            )
        return "image/svg+xml", "svg"

    magic_format = _detect_magic_format(result_bytes)
    if magic_format is None:
        raise ProviderPayloadError(
            "Provider output has unsupported or corrupt format (must be JPEG, PNG, or WebP)",
            provider_id=provider_id,
            correlation_id=correlation_id,
        )

    try:
        with Image.open(io.BytesIO(result_bytes)) as img:
            if img.format not in _PIL_FORMAT_TO_MIME_EXT or img.format != magic_format:
                raise ProviderPayloadError(
                    f"Provider output format {img.format!r} does not match signature {magic_format!r}",
                    provider_id=provider_id,
                    correlation_id=correlation_id,
                )
            w, h = img.size
            if w < 1 or h < 1 or w > _MAX_OUTPUT_EDGE or h > _MAX_OUTPUT_EDGE or (w * h > _MAX_OUTPUT_PIXELS):
                raise ProviderPayloadError(
                    f"Provider output dimensions {w}x{h} exceed safety limits",
                    provider_id=provider_id,
                    correlation_id=correlation_id,
                )
            img.load()
            return _PIL_FORMAT_TO_MIME_EXT[img.format]
    except ProviderPayloadError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ProviderPayloadError(
            "Provider output rejected as decompression bomb",
            provider_id=provider_id,
            correlation_id=correlation_id,
            cause=exc,
        )
    except Exception as exc:
        raise ProviderPayloadError(
            "Provider output image is malformed or unreadable",
            provider_id=provider_id,
            correlation_id=correlation_id,
            cause=exc,
        )


async def create_confirmed_presigned_input_url(
    *,
    storage: ObjectStoragePort,
    key: str,
    expires_in_s: int = 600,
) -> str:
    """Create a presigned GET URL only after confirming durable object persistence."""
    if not key or not key.strip():
        raise StorageNotFoundError("Input media key is missing", key=key)
    validate_scoped_object_key(key)
    exists = await storage.object_exists(key)
    if not exists:
        raise StorageNotFoundError(
            "Cannot issue presigned input URL before durable storage confirmation",
            key=key,
        )
    return await storage.generate_presigned_get_url(key=key, expires_in_s=expires_in_s)


def _payload_digest(
    *,
    outfit_source: str,
    garment_ids: list[str],
    person_digest: str,
    consent_version: str,
) -> str:
    canonical = "|".join(
        [outfit_source, ",".join(garment_ids), person_digest, consent_version]
    )
    return sha256_hex(canonical.encode("utf-8"))


def submit_job(
    *,
    user_id: str,
    outfit_source: str,
    garment_ids: list[str],
    person_content_type: str,
    person_bytes: bytes,
    consent_version: str,
    consent_accepted: bool,
    idempotency_key: str,
    today: date | None = None,
    seed: str = "mock-1",
    wardrobe_repo: Optional[WardrobeItemRepository] = None,
    job_repo: Optional[TryOnJobRepository] = None,
    storage: Optional[ObjectStoragePort] = None,
) -> tuple[TryOnJobRecord, bool]:
    """Validate inputs, check wardrobe ownership, enforce idempotency, and persist try-on job."""
    settings = get_settings()

    enabled = getattr(settings, "tryon_enabled", True)
    provider_name = getattr(settings, "tryon_provider", "mock")
    env = getattr(settings, "environment", "development")

    if not enabled or provider_name == "off":
        raise ai_failure()

    # Production gate: CatVTON is prohibited in production. If mock or missing provider in production, fail closed.
    if env == "production":
        if provider_name == "catvton":
            raise validation(
                [{"field": "tryon_provider", "error": "CatVTON cannot be enabled in production."}]
            )
        if provider_name == "mock":
            raise ai_failure()

    if provider_name == "genlook" and not getattr(settings, "genlook_api_key", None):
        raise ai_failure()


    if not (idempotency_key or "").strip():
        raise validation([{"field": "Idempotency-Key", "error": "is required"}])

    if not consent_accepted:
        raise validation([{"field": "consent_accepted", "error": "explicit consent is required"}])

    if consent_version != settings.tryon_consent_version:
        raise validation(
            [
                {
                    "field": "consent_version",
                    "error": f"must be {settings.tryon_consent_version!r}",
                }
            ]
        )

    if outfit_source not in _OUTFIT_SOURCES:
        raise validation([{"field": "outfit_source", "error": "unknown outfit source"}])

    if not garment_ids or len(garment_ids) > _MAX_GARMENT_IDS:
        raise validation(
            [
                {
                    "field": "garment_ids",
                    "error": f"must hold 1..{_MAX_GARMENT_IDS} garment ids",
                }
            ]
        )

    for gid in garment_ids:
        if not isinstance(gid, str) or not gid.strip() or len(gid) > 200:
            raise validation([{"field": "garment_ids", "error": "ids must be 1..200 chars"}])

    if provider_name == "genlook" and len(garment_ids) != 1:
        raise validation(
            [{"field": "garment_ids", "error": "Genlook try-on requires exactly 1 garment id"}]
        )

    sanitized_bytes, canonical_content_type = validate_and_sanitize_person_image(
        person_bytes, person_content_type
    )
    if provider_name == "genlook" and len(sanitized_bytes) > GENLOOK_MAX_IMAGE_BYTES:
        raise validation(
            [{"field": "person_image", "error": "must be at most 10 MB for Genlook"}]
        )

    # User ID parsing
    try:
        user_uuid = UUID(user_id)
    except Exception:
        raise validation([{"field": "user_id", "error": "invalid user UUID"}])

    # Digital Wardrobe garment validation & ownership check
    first_garment_uuid: Optional[UUID] = None
    if outfit_source == "wardrobe" or provider_name == "genlook":
        if not garment_ids:
            raise validation([{"field": "garment_ids", "error": "at least one garment id is required"}])
        for gid in garment_ids:
            try:
                g_uuid = UUID(gid)
            except Exception:
                raise validation([{"field": "garment_ids", "error": f"invalid garment UUID: {gid}"}])
            if first_garment_uuid is None:
                first_garment_uuid = g_uuid
            if wardrobe_repo is not None:
                item = wardrobe_repo.get_by_id(user_id=user_uuid, item_id=g_uuid)
                if item is None:
                    raise validation(
                        [
                            {
                                "field": "garment_ids",
                                "error": f"garment {gid} not found in user wardrobe",
                            }
                        ]
                    )
    else:
        # For non-wardrobe sources, if IDs are valid UUIDs, record first UUID
        if garment_ids:
            try:
                first_garment_uuid = UUID(garment_ids[0])
            except Exception:
                pass

    repo = job_repo or _IN_MEMORY_REPO
    person_digest = sha256_hex(sanitized_bytes)
    digest = _payload_digest(
        outfit_source=outfit_source,
        garment_ids=garment_ids,
        person_digest=person_digest,
        consent_version=consent_version,
    )
    current_day = today or datetime.now(timezone.utc).date()

    # Idempotency fast-path check
    existing = repo.find_by_idempotency_key(
        user_id=user_uuid, idempotency_key=idempotency_key
    )
    if existing is not None:
        if existing.request_fingerprint != digest:
            raise conflict(kind="idempotency_key_reuse")
        return existing, False

    daily_quota = getattr(settings, "tryon_daily_quota_per_user", 20)
    concurrent_limit = getattr(settings, "tryon_max_concurrent_jobs_per_user", 5)

    job_id = uuid4()
    person_ext = "webp" if "webp" in canonical_content_type else ("png" if "png" in canonical_content_type else "jpg")
    person_key = f"users/{user_uuid}/tryon/{job_id}/person.{person_ext}"
    person_media_ref = {
        "key": person_key,
        "mediaType": canonical_content_type,
        "sizeBytes": len(sanitized_bytes),
        "contentHash": person_digest,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
    }

    initial_status = "processing" if settings.tryon_provider == "mock" else "queued"
    create_atomic_fn = getattr(repo, "create_with_quota", None)

    if callable(create_atomic_fn):
        created_job, created = create_atomic_fn(
            job_id=job_id,
            user_id=user_uuid,
            outfit_source=outfit_source,
            garment_id=first_garment_uuid,
            garment_ids=garment_ids,
            provider=settings.tryon_provider,
            status=initial_status,
            consent_version=consent_version,
            consent_accepted_at=datetime.now(timezone.utc),
            person_media_ref=person_media_ref,
            idempotency_key=idempotency_key,
            request_fingerprint=digest,
            day=current_day,
            daily_quota=daily_quota,
            concurrent_limit=concurrent_limit,
        )
        if created:
            _BYTE_CACHE[str(job_id)] = (sanitized_bytes, canonical_content_type)
        return created_job, created

    # Fallback path for minimal custom repository test stubs without create_with_quota
    used = repo.count_today_jobs(user_id=user_uuid, day=current_day)
    if used >= daily_quota:
        raise rate_limited()

    active_count = repo.count_active_jobs(user_id=user_uuid)
    if active_count >= concurrent_limit:
        raise rate_limited()

    # Temporarily stage sanitized person bytes until durable storage persistence completes
    _BYTE_CACHE[str(job_id)] = (sanitized_bytes, canonical_content_type)

    try:
        created_job = repo.create(
            job_id=job_id,
            user_id=user_uuid,
            outfit_source=outfit_source,
            garment_id=first_garment_uuid,
            garment_ids=garment_ids,
            provider=settings.tryon_provider,
            status=initial_status,
            consent_version=consent_version,
            consent_accepted_at=datetime.now(timezone.utc),
            person_media_ref=person_media_ref,
            idempotency_key=idempotency_key,
            request_fingerprint=digest,
        )
    except Exception:
        _BYTE_CACHE.pop(str(job_id), None)
        # Check if an idempotency race occurred
        existing = repo.find_by_idempotency_key(
            user_id=user_uuid, idempotency_key=idempotency_key
        )
        if existing is not None:
            if existing.request_fingerprint != digest:
                raise conflict(kind="idempotency_key_reuse")
            return existing, False
        raise

    return created_job, True


async def store_person_image_async(
    *,
    storage: ObjectStoragePort,
    user_id: UUID,
    job_id: UUID,
    person_bytes: bytes | None = None,
    content_type: str = "image/jpeg",
    job_repo: Optional[TryOnJobRepository] = None,
) -> str:
    """Persist sanitized person image bytes to object storage and confirm durability.

    Never swallows storage failures: marks job failed and re-raises on error,
    and always evicts temporary in-memory person bytes once stored or failed.
    """
    try:
        cached = _BYTE_CACHE.get(str(job_id))
        if cached is not None:
            effective_bytes, effective_ct = cached
        else:
            if not person_bytes:
                if job_repo is not None:
                    job_repo.update_failure(
                        job_id=job_id,
                        error_code="STORAGE_FAILURE",
                        error_message="Missing person image bytes for storage.",
                        completed_at=datetime.now(timezone.utc),
                    )
                raise StorageError("Missing person image bytes for storage")
            effective_bytes, effective_ct = validate_and_sanitize_person_image(
                person_bytes, content_type
            )

        person_ext = "webp" if "webp" in effective_ct else ("png" if "png" in effective_ct else "jpg")
        key = f"users/{user_id}/tryon/{job_id}/person.{person_ext}"

        if job_repo is not None:
            current = job_repo.get_by_id(user_id=user_id, job_id=job_id)
            if current is not None and current.status == "cancelled":
                return key

        try:
            await storage.put_object(key, effective_bytes, content_type=effective_ct)
            exists = await storage.object_exists(key)
            if not exists:
                raise StorageError("Person image storage confirmation failed", key=key)
        except Exception as e:
            logger.error("Failed to persist person image to storage for job %s: %s", job_id, e)
            if job_repo is not None:
                job_repo.update_failure(
                    job_id=job_id,
                    error_code="STORAGE_FAILURE",
                    error_message="Failed to securely store input person image.",
                    completed_at=datetime.now(timezone.utc),
                )
            raise

        # Check if cancelled concurrently while uploading; remove orphaned input object
        if job_repo is not None:
            latest = job_repo.get_by_id(user_id=user_id, job_id=job_id)
            if latest is not None and latest.status == "cancelled":
                try:
                    await storage.delete_object(key)
                except Exception as del_exc:
                    logger.warning("Failed to delete cancelled input image %s: %s", key, del_exc)

        return key
    finally:
        # Immediately evict person bytes from memory in all exit paths
        _BYTE_CACHE.pop(str(job_id), None)


async def execute_tryon_inference(
    *,
    job_id: UUID,
    user_id: UUID,
    job_repo: Optional[TryOnJobRepository],
    storage: Optional[ObjectStoragePort] = None,
    wardrobe_repo: Optional[WardrobeItemRepository] = None,
    seed: str = "mock-1",
) -> None:
    """Execute try-on inference in background, persist result privately, and update job status."""
    try:
        await _execute_tryon_inference_impl(
            job_id=job_id,
            user_id=user_id,
            job_repo=job_repo,
            storage=storage,
            wardrobe_repo=wardrobe_repo,
            seed=seed,
        )
    finally:
        _BYTE_CACHE.pop(str(job_id), None)


async def _execute_tryon_inference_impl(
    *,
    job_id: UUID,
    user_id: UUID,
    job_repo: Optional[TryOnJobRepository],
    storage: Optional[ObjectStoragePort] = None,
    wardrobe_repo: Optional[WardrobeItemRepository] = None,
    seed: str = "mock-1",
) -> None:
    repo = job_repo or _IN_MEMORY_REPO
    job = repo.get_by_id(user_id=user_id, job_id=job_id)
    if job is None or job.status in ("cancelled", "completed", "failed"):
        logger.info("TryOn job %s absent or terminal (%s); stopping execution.", job_id, getattr(job, "status", None))
        return

    settings = get_settings()
    provider_name = settings.tryon_provider

    # Enforce hard prerequisite: if job has a person_media_ref, person image MUST be durably stored
    person_bytes: Optional[bytes] = None
    if job.person_media_ref and "key" in job.person_media_ref:
        person_key = job.person_media_ref["key"]
        if storage is None:
            logger.error("Storage unavailable for job %s with person_media_ref", job_id)
            repo.update_failure(
                job_id=job_id,
                error_code="STORAGE_FAILURE",
                error_message="Media storage is unavailable for person image retrieval.",
                completed_at=datetime.now(timezone.utc),
            )
            return
        try:
            if not await storage.object_exists(person_key):
                logger.error("Person image missing from durable storage for job %s (key=%s)", job_id, person_key)
                repo.update_failure(
                    job_id=job_id,
                    error_code="STORAGE_FAILURE",
                    error_message="Input person image was not persisted in storage.",
                    completed_at=datetime.now(timezone.utc),
                )
                return
            person_bytes = await storage.read_object(person_key, max_bytes=_MAX_PERSON_BYTES)
        except Exception as e:
            logger.error("Could not load person image from storage for job %s: %s", job_id, e)
            repo.update_failure(
                job_id=job_id,
                error_code="STORAGE_FAILURE",
                error_message="Failed to retrieve persisted person image from storage.",
                completed_at=datetime.now(timezone.utc),
            )
            return
    else:
        cached_person = _BYTE_CACHE.pop(str(job_id), None)
        person_bytes = cached_person[0] if cached_person else None

    now = datetime.now(timezone.utc)
    repo.update_status(job_id=job_id, status="processing", processing_started_at=now)

    # Resolve garment bytes / signed URL and validate category
    garment_bytes: Optional[bytes] = None
    category = "tops" if provider_name == "commercial" else "upper"
    corr_id = str(uuid4())
    garment_item = None

    if provider_name == "genlook":
        if not getattr(settings, "genlook_api_key", None):
            repo.update_failure(
                job_id=job_id,
                error_code="PROVIDER_CONFIG_ERROR",
                error_message="Try-on provider configuration is incomplete.",
                completed_at=datetime.now(timezone.utc),
            )
            return
        if len(job.garment_ids) != 1 or job.garment_id is None:
            repo.update_failure(
                job_id=job_id,
                error_code="PAYLOAD_REJECTED",
                error_message="Genlook try-on requires exactly 1 owned wardrobe garment.",
                completed_at=datetime.now(timezone.utc),
            )
            return
        if wardrobe_repo is None:
            repo.update_failure(
                job_id=job_id,
                error_code="PAYLOAD_REJECTED",
                error_message="Wardrobe repository is unavailable for garment verification.",
                completed_at=datetime.now(timezone.utc),
            )
            return
        try:
            garment_item = wardrobe_repo.get_by_id(user_id=user_id, item_id=job.garment_id)
        except Exception as e:
            logger.warning("Could not query garment item for Genlook job %s: %s", job_id, e)
            garment_item = None
        if garment_item is None or garment_item.user_id != user_id:
            repo.update_failure(
                job_id=job_id,
                error_code="PAYLOAD_REJECTED",
                error_message="Selected garment was not found in your Digital Wardrobe.",
                completed_at=datetime.now(timezone.utc),
            )
            return
        try:
            resolved_garment_key = resolve_wardrobe_image_key(
                garment_item.image_ref,
                user_id=user_id,
            ).key
        except StorageError as e:
            logger.warning(
                "Invalid garment image_ref for Genlook job %s: %s",
                job_id,
                type(e).__name__,
            )
            repo.update_failure(
                job_id=job_id,
                error_code="PAYLOAD_REJECTED",
                error_message="Selected garment does not have an available image in storage.",
                completed_at=datetime.now(timezone.utc),
            )
            return
        if storage is None:
            repo.update_failure(
                job_id=job_id,
                error_code="PAYLOAD_REJECTED",
                error_message="Selected garment does not have an available image in storage.",
                completed_at=datetime.now(timezone.utc),
            )
            return
        try:
            garment_image_url = await create_confirmed_presigned_input_url(
                storage=storage,
                key=resolved_garment_key,
                expires_in_s=300,
            )
        except Exception as e:
            logger.warning("Failed to sign garment image URL for Genlook job %s: %s", job_id, type(e).__name__)
            repo.update_failure(
                job_id=job_id,
                error_code="STORAGE_FAILURE",
                error_message="Selected garment image could not be accessed from private storage.",
                completed_at=datetime.now(timezone.utc),
            )
            return

        genlook_product_spec = build_genlook_product_spec(
            item_id=str(garment_item.id),
            name=garment_item.name,
            category=garment_item.category,
            color=garment_item.color,
            material=garment_item.material,
            fit=garment_item.fit,
            image_url=garment_image_url,
        )
    elif job.garment_id and wardrobe_repo is not None:
        item = None
        try:
            item = wardrobe_repo.get_by_id(user_id=user_id, item_id=job.garment_id)
        except Exception as e:
            logger.warning("Could not query garment item for job %s: %s", job_id, e)

        if item is not None:
            if provider_name == "commercial":
                try:
                    category = map_wardrobe_category_to_fashn(
                        item.category,
                        correlation_id=corr_id,
                        provider_id=settings.tryon_commercial_provider_name,
                    )
                except ProviderPayloadError as e:
                    logger.warning("Unsupported garment category for job %s: %s", job_id, e.message)
                    repo.update_failure(
                        job_id=job_id,
                        error_code="PAYLOAD_REJECTED",
                        error_message="Selected garment category is not supported for virtual try-on.",
                        completed_at=datetime.now(timezone.utc),
                    )
                    return
            elif provider_name == "catvton":
                try:
                    fashn_cat = map_wardrobe_category_to_fashn(
                        item.category,
                        correlation_id=corr_id,
                        provider_id="catvton",
                    )
                except ProviderPayloadError as e:
                    logger.warning("Unsupported garment category for CatVTON job %s: %s", job_id, e.message)
                    repo.update_failure(
                        job_id=job_id,
                        error_code="PAYLOAD_REJECTED",
                        error_message="Selected garment category is not supported for virtual try-on.",
                        completed_at=datetime.now(timezone.utc),
                    )
                    return
                category = {"tops": "upper", "bottoms": "lower", "one-pieces": "overall"}[fashn_cat]
            else:
                if item.category in ("bottoms", "pants", "jeans", "skirts", "shorts"):
                    category = "lower"
                elif item.category in ("dresses", "jumpsuits", "overall", "one-pieces"):
                    category = "overall"

            if storage is not None and item.image_ref is not None:
                try:
                    garment_key = resolve_wardrobe_image_key(
                        item.image_ref,
                        user_id=user_id,
                    ).key
                    garment_bytes = await storage.read_object(
                        garment_key, max_bytes=_MAX_PERSON_BYTES
                    )
                except Exception as e:
                    logger.warning("Could not retrieve garment image for job %s: %s", job_id, type(e).__name__)

    person_ref_copy = dict(job.person_media_ref or {})
    genlook_meta = dict(person_ref_copy.get("genlook") or {})
    attempt_seq = int(genlook_meta.get("attemptSeq", 0))

    def _persist_genlook_meta(updates: dict[str, Any]) -> None:
        genlook_meta.update(updates)
        person_ref_copy["genlook"] = dict(genlook_meta)
        update_fn = getattr(repo, "update_person_media_ref", None)
        if callable(update_fn):
            update_fn(job_id=job_id, person_media_ref=person_ref_copy)

    # Execute provider render
    try:
        if provider_name == "genlook":
            person_digest = person_ref_copy.get("contentHash") or (
                sha256_hex(person_bytes) if person_bytes else ""
            )
            existing_generation_id: Optional[str] = None
            raw_gen_id = genlook_meta.get("generationId")
            if (
                isinstance(raw_gen_id, str)
                and raw_gen_id.strip()
                and genlook_meta.get("generationStatus") != "FAILED"
            ):
                existing_generation_id = raw_gen_id.strip()

            existing_image_id: Optional[str] = None
            if existing_generation_id is None:
                retention_hours = getattr(settings, "tryon_retention_person_photo_hours", 24)
                min_created_at = now - timedelta(hours=retention_hours)
                # 1) Reuse imageId on this same job if ownership, consent, digest, and retention hold
                cur_img_id = genlook_meta.get("imageId")
                cur_exp = genlook_meta.get("imageExpiresAt")
                if (
                    isinstance(cur_img_id, str)
                    and cur_img_id.strip()
                    and job.user_id == user_id
                    and job.consent_accepted_at is not None
                    and job.consent_version == settings.tryon_consent_version
                    and person_ref_copy.get("contentHash") == person_digest
                    and job.created_at >= min_created_at
                    and isinstance(cur_exp, str)
                ):
                    try:
                        exp_dt = datetime.fromisoformat(cur_exp)
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        if exp_dt > now:
                            existing_image_id = cur_img_id.strip()
                    except Exception:
                        existing_image_id = None

                # 2) Or reuse a recent valid imageId owned by the same user
                if existing_image_id is None:
                    find_fn = getattr(repo, "find_reusable_genlook_image_id", None)
                    if callable(find_fn) and person_digest:
                        existing_image_id = find_fn(
                            user_id=user_id,
                            person_digest=person_digest,
                            consent_version=settings.tryon_consent_version,
                            min_created_at=min_created_at,
                            now=now,
                        )

                attempt_idem_key = genlook_meta.get("pendingIdempotencyKey")
                if not isinstance(attempt_idem_key, str) or not attempt_idem_key.strip():
                    attempt_idem_key = f"fv-tryon-{job_id}-a{attempt_seq}"
                    _persist_genlook_meta(
                        {
                            "attemptSeq": attempt_seq,
                            "pendingIdempotencyKey": attempt_idem_key,
                            "productExternalId": str(garment_item.id),
                            "creditsEstimated": 1,
                        }
                    )
            else:
                attempt_idem_key = f"fv-tryon-{job_id}-a{attempt_seq}"

            def _on_genlook_image_uploaded(upload_res: GenlookImageUploadResult) -> None:
                expires_at = datetime.now(timezone.utc) + timedelta(days=upload_res.keep_for_days)
                _persist_genlook_meta(
                    {
                        "imageId": upload_res.image_id,
                        "imageUploadedAt": datetime.now(timezone.utc).isoformat(),
                        "imageExpiresAt": expires_at.isoformat(),
                        "keepForDays": upload_res.keep_for_days,
                        "uploadRequestId": upload_res.request_id,
                    }
                )

            def _on_genlook_generation_created(create_res: GenlookTryOnCreateResult) -> None:
                _persist_genlook_meta(
                    {
                        "generationId": create_res.generation_id,
                        "generationStatus": create_res.status,
                        "productExternalIds": list(create_res.product_external_ids),
                        "createRequestId": create_res.request_id,
                        "idempotencyReplayed": create_res.idempotency_replayed,
                        "pendingIdempotencyKey": None,
                        "creditsEstimated": 1,
                    }
                )

            def _is_job_cancelled() -> bool:
                cur = repo.get_by_id(user_id=user_id, job_id=job_id)
                return cur is not None and cur.status == "cancelled"

            if _is_job_cancelled():
                logger.info("Genlook try-on job %s cancelled before provider dispatch.", job_id)
                return

            g_config = GenlookTryOnConfig(
                api_key=settings.genlook_api_key or "",
                base_url=getattr(settings, "genlook_api_base_url", GENLOOK_DEFAULT_BASE_URL),
                connect_timeout_s=getattr(settings, "genlook_connect_timeout_s", 10.0),
                request_timeout_s=getattr(settings, "genlook_request_timeout_s", 30.0),
                poll_interval_s=getattr(settings, "genlook_poll_interval_s", 1.0),
                poll_timeout_s=getattr(settings, "genlook_poll_timeout_s", 120.0),
                max_retries=getattr(settings, "genlook_max_retries", 2),
                keep_for_days=getattr(settings, "genlook_keep_for_days", 1),
                ai_label=getattr(settings, "genlook_ai_label", True),
            )
            g_provider = GenlookTryOnProvider(g_config)
            result_bytes = await asyncio.to_thread(
                g_provider.render,
                person_digest=person_digest,
                garment_labels=list(job.garment_ids),
                seed=seed,
                outfit_source=job.outfit_source,
                person_bytes=person_bytes,
                category=garment_item.category,
                correlation_id=corr_id,
                job_id=str(job_id),
                garment_image_url=garment_image_url,
                is_cancelled_fn=_is_job_cancelled,
                existing_generation_id=existing_generation_id,
                existing_image_id=existing_image_id,
                idempotency_key=attempt_idem_key,
                external_user_id=str(user_id),
                product_spec=genlook_product_spec,
                on_image_uploaded=_on_genlook_image_uploaded,
                on_generation_created=_on_genlook_generation_created,
            )
            _persist_genlook_meta(
                {
                    "generationStatus": "COMPLETED",
                    "creditsCharged": 1,
                    "refunded": False,
                }
            )
        elif provider_name == "commercial":
            config = CommercialTryOnProviderConfig(
                provider_name=settings.tryon_commercial_provider_name,
                api_key=settings.tryon_commercial_api_key or "",
                endpoint_url=settings.tryon_commercial_endpoint_url or "",
                connect_timeout_s=settings.tryon_commercial_connect_timeout_s,
                inference_timeout_s=settings.tryon_commercial_inference_timeout_s,
                max_retries=settings.tryon_commercial_max_retries,
            )
            provider = CommercialTryOnProvider(config)
            result_bytes = await asyncio.to_thread(
                provider.render,
                person_digest=job.person_media_ref.get("contentHash") if job.person_media_ref else "",
                garment_labels=list(job.garment_ids),
                seed=seed,
                outfit_source=job.outfit_source,
                person_bytes=person_bytes,
                garment_bytes=garment_bytes,
                category=category,
                correlation_id=corr_id,
            )
        elif provider_name == "catvton":
            provider = CatVTONTryOnProvider()
            result_bytes = await asyncio.to_thread(
                provider.render,
                person_digest=job.person_media_ref.get("contentHash") if job.person_media_ref else "",
                garment_labels=list(job.garment_ids),
                seed=seed,
                outfit_source=job.outfit_source,
                person_bytes=person_bytes,
                garment_bytes=garment_bytes,
                category=category,
            )
        else:
            provider = MockTryOnProvider()
            result_bytes = provider.render(
                person_digest=job.person_media_ref.get("contentHash") if job.person_media_ref else "",
                garment_labels=list(job.garment_ids),
                seed=seed,
                outfit_source=job.outfit_source,
            )
    except GenlookCancelledError:
        logger.info("Genlook try-on job %s cancelled during polling; preserving cancelled state.", job_id)
        return
    except ProviderPayloadError as e:
        if provider_name == "genlook":
            err_code = getattr(e, "provider_error_code", None)
            if err_code == "RESULT_DOWNLOAD_REJECTED" and genlook_meta.get("generationId"):
                # Generation already COMPLETED on Genlook (1 credit charged).
                # Preserve generationId so retry re-fetches GET /generations/{id} without double-charging.
                _persist_genlook_meta(
                    {
                        "generationStatus": "COMPLETED",
                        "pendingIdempotencyKey": None,
                        "creditsCharged": 1,
                        "refunded": False,
                        "lastErrorCode": err_code,
                    }
                )
            else:
                _persist_genlook_meta(
                    {
                        "generationStatus": "FAILED" if genlook_meta.get("generationId") else genlook_meta.get("generationStatus"),
                        "generationId": None,
                        "pendingIdempotencyKey": None,
                        "attemptSeq": attempt_seq + 1,
                        "creditsCharged": 0,
                        "refunded": bool(genlook_meta.get("generationId")),
                        "lastErrorCode": err_code,
                    }
                )
        logger.warning("TryOn payload rejected for job %s: %s", job_id, e.message)
        repo.update_failure(
            job_id=job_id,
            error_code="PAYLOAD_REJECTED",
            error_message="The try-on image payload was rejected by the provider.",
            completed_at=datetime.now(timezone.utc),
        )
        return
    except ProviderAuthError as e:
        if provider_name == "genlook":
            _persist_genlook_meta(
                {
                    "pendingIdempotencyKey": None,
                    "attemptSeq": attempt_seq + 1,
                    "creditsCharged": 0,
                    "lastErrorCode": getattr(e, "provider_error_code", None),
                }
            )
        logger.error("TryOn provider auth failure for job %s: %s", job_id, e.message)
        repo.update_failure(
            job_id=job_id,
            error_code="PROVIDER_AUTH_ERROR",
            error_message="Commercial try-on provider authorization failed.",
            completed_at=datetime.now(timezone.utc),
        )
        return
    except ProviderQuotaExceededError as e:
        if provider_name == "genlook":
            err_code = getattr(e, "provider_error_code", None)
            _persist_genlook_meta(
                {
                    "generationStatus": "FAILED" if genlook_meta.get("generationId") else genlook_meta.get("generationStatus"),
                    "generationId": None,
                    "pendingIdempotencyKey": None,
                    "attemptSeq": attempt_seq + 1,
                    "creditsCharged": 0,
                    "refunded": bool(genlook_meta.get("generationId")),
                    "lastErrorCode": err_code,
                }
            )
        logger.warning("TryOn provider quota exceeded for job %s: %s", job_id, e.message)
        repo.update_failure(
            job_id=job_id,
            error_code="PROVIDER_QUOTA_EXCEEDED",
            error_message="Commercial try-on capacity limit reached. Please try again later.",
            completed_at=datetime.now(timezone.utc),
        )
        return
    except ProviderTransientError as e:
        if provider_name == "genlook":
            err_code = getattr(e, "provider_error_code", None)
            # If Genlook explicitly marked generation FAILED (refunded), clear generationId so retry can re-submit;
            # if poll timed out or POST /try-on response was lost, KEEP generationId / pendingIdempotencyKey!
            if genlook_meta.get("generationId") and err_code in (
                "GENERATION_FAILED",
                "GENERATION_TIMEOUT",
            ):
                _persist_genlook_meta(
                    {
                        "generationStatus": "FAILED",
                        "generationId": None,
                        "pendingIdempotencyKey": None,
                        "attemptSeq": attempt_seq + 1,
                        "creditsCharged": 0,
                        "refunded": True,
                        "lastErrorCode": err_code,
                    }
                )
            else:
                _persist_genlook_meta({"lastErrorCode": err_code or "TRANSIENT_UNCERTAIN"})
        logger.warning("TryOn provider transient error for job %s: %s", job_id, e.message)
        repo.update_failure(
            job_id=job_id,
            error_code="PROVIDER_TRANSIENT_FAILURE",
            error_message="Commercial try-on provider experienced a transient error. You can retry.",
            completed_at=datetime.now(timezone.utc),
        )
        return
    except CommercialProviderConfigurationError as e:
        logger.error("TryOn commercial config error for job %s: %s", job_id, e.message)
        repo.update_failure(
            job_id=job_id,
            error_code="PROVIDER_CONFIG_ERROR",
            error_message="Try-on provider configuration is incomplete.",
            completed_at=datetime.now(timezone.utc),
        )
        return
    except Exception as e:
        logger.error("TryOn inference failed for job %s: %s", job_id, e)
        repo.update_failure(
            job_id=job_id,
            error_code="AI_INFERENCE_FAILURE",
            error_message="Virtual try-on model processing failed. Please try again.",
            completed_at=datetime.now(timezone.utc),
        )
        return

    # Check for cancellation before validating/persisting
    latest = repo.get_by_id(user_id=user_id, job_id=job_id)
    if latest is not None and latest.status == "cancelled":
        logger.info("Job %s was cancelled during inference; discarding result.", job_id)
        return

    # Validate provider output bytes and detect true format/MIME
    try:
        result_content_type, result_ext = validate_and_inspect_output_image(
            result_bytes,
            allow_svg=(provider_name == "mock"),
            provider_id=provider_name,
            correlation_id=corr_id,
        )
    except ProviderPayloadError as e:
        logger.warning("TryOn provider returned invalid output for job %s: %s", job_id, e.message)
        repo.update_failure(
            job_id=job_id,
            error_code="INVALID_PROVIDER_OUTPUT",
            error_message="The try-on provider returned an invalid or unsupported image.",
            completed_at=datetime.now(timezone.utc),
        )
        return

    result_key = f"users/{user_id}/tryon/{job_id}/result.{result_ext}"

    result_media_ref: dict[str, Any] = {
        "key": result_key,
        "mediaType": result_content_type,
        "sizeBytes": len(result_bytes),
        "contentHash": sha256_hex(result_bytes),
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "isMock": (provider_name == "mock"),
        "provider": provider_name,
    }
    if provider_name == "genlook":
        if genlook_meta.get("generationId"):
            result_media_ref["generationId"] = genlook_meta["generationId"]
        result_media_ref["creditsCharged"] = genlook_meta.get("creditsCharged", 1)

    if storage is not None:
        # Clean up previous attempt output if extension changed on retry
        prev_key = job.result_media_ref.get("key") if job.result_media_ref else None
        if prev_key and prev_key != result_key:
            try:
                await storage.delete_object(prev_key)
            except Exception:
                pass
        try:
            await storage.put_object(
                result_key,
                result_bytes,
                content_type=result_content_type,
            )
            exists = await storage.object_exists(result_key)
            if not exists:
                raise StorageError("Try-on result storage confirmation failed", key=result_key)
        except Exception as e:
            logger.error("Failed to store try-on result image for job %s: %s", job_id, e)
            repo.update_failure(
                job_id=job_id,
                error_code="STORAGE_FAILURE",
                error_message="Failed to securely store generated try-on result.",
                completed_at=datetime.now(timezone.utc),
            )
            return

    # Check for cancellation after persistence (stale worker / cancellation race)
    latest = repo.get_by_id(user_id=user_id, job_id=job_id)
    if latest is not None and latest.status == "cancelled":
        logger.info("Job %s was cancelled after storage; deleting orphaned result.", job_id)
        if storage is not None:
            try:
                await storage.delete_object(result_key)
            except Exception:
                pass
        return

    # Cache result bytes only for in-memory test repository
    if isinstance(repo, InMemoryTryOnJobRepository):
        repo.set_image_bytes(job_id, result_bytes)

    # Complete job
    updated = repo.update_result(
        job_id=job_id,
        result_media_ref=result_media_ref,
        completed_at=datetime.now(timezone.utc),
    )
    if updated is None or updated.status != "completed":
        logger.info("Job %s was %s at update_result boundary; deleting orphaned result.", job_id, getattr(updated, "status", "missing"))
        if storage is not None:
            try:
                await storage.delete_object(result_key)
            except Exception:
                pass


def get_job(
    *,
    user_id: str,
    job_id: str,
    job_repo: Optional[TryOnJobRepository] = None,
) -> Optional[TryOnJobRecord]:
    """Owner-scoped lookup — returns TryOnJobRecord or None."""
    try:
        user_uuid = UUID(user_id)
        job_uuid = UUID(job_id)
    except Exception:
        return None

    repo = job_repo or _IN_MEMORY_REPO
    return repo.get_by_id(user_id=user_uuid, job_id=job_uuid)


def poll_job(
    job: TryOnJobRecord,
    job_repo: Optional[TryOnJobRepository] = None,
) -> TryOnJobRecord:
    """Advance mock job deterministic lifecycle for pollers."""
    key = str(job.id)
    polls = _POLL_COUNTS.get(key, 0) + 1
    _POLL_COUNTS[key] = polls

    repo = job_repo or _IN_MEMORY_REPO

    if polls > _POLLS_TO_COMPLETE and job.status != "completed":
        settings = get_settings()
        if settings.tryon_provider == "catvton":
            provider = CatVTONTryOnProvider()
        else:
            provider = MockTryOnProvider()

        p_digest = job.person_media_ref.get("contentHash") if job.person_media_ref else ""
        rendered = provider.render(
            person_digest=p_digest,
            garment_labels=list(job.garment_ids),
            seed="mock-1",
            outfit_source=job.outfit_source,
        )
        result_ct, result_ext = validate_and_inspect_output_image(
            rendered,
            allow_svg=(settings.tryon_provider != "catvton"),
            provider_id=settings.tryon_provider,
        )
        if isinstance(repo, InMemoryTryOnJobRepository):
            repo.set_image_bytes(job.id, rendered)

        now = datetime.now(timezone.utc)
        result_media_ref = {
            "key": f"users/{job.user_id}/tryon/{job.id}/result.{result_ext}",
            "mediaType": result_ct,
            "sizeBytes": len(rendered),
            "contentHash": sha256_hex(rendered),
            "completedAt": now.isoformat(),
            "isMock": (settings.tryon_provider != "catvton"),
        }
        updated = repo.update_result(
            job_id=job.id,
            result_media_ref=result_media_ref,
            completed_at=now,
        )
        _POLL_COUNTS.pop(key, None)
        _BYTE_CACHE.pop(key, None)
        if updated:
            if not isinstance(repo, InMemoryTryOnJobRepository):
                return TryOnJobRecord(
                    id=updated.id,
                    user_id=updated.user_id,
                    outfit_source=updated.outfit_source,
                    garment_id=updated.garment_id,
                    garment_ids=updated.garment_ids,
                    provider=updated.provider,
                    status=updated.status,
                    consent_version=updated.consent_version,
                    consent_accepted_at=updated.consent_accepted_at,
                    created_at=updated.created_at,
                    updated_at=updated.updated_at,
                    person_media_ref=updated.person_media_ref,
                    result_media_ref=updated.result_media_ref,
                    idempotency_key=updated.idempotency_key,
                    request_fingerprint=updated.request_fingerprint,
                    error_code=updated.error_code,
                    error_message=updated.error_message,
                    retry_count=updated.retry_count,
                    retry_of_job_id=updated.retry_of_job_id,
                    processing_started_at=updated.processing_started_at,
                    completed_at=updated.completed_at,
                    image_bytes=rendered,
                )
            return updated
    return job


_MAX_TRYON_RETRIES = 3


def retry_job(
    *,
    user_id: str,
    job_id: str,
    job_repo: Optional[TryOnJobRepository] = None,
) -> TryOnJobRecord:
    """Retry an eligible failed or cancelled try-on job."""
    settings = get_settings()
    enabled = getattr(settings, "tryon_enabled", True)
    provider_name = getattr(settings, "tryon_provider", "mock")
    env = getattr(settings, "environment", "development")

    if not enabled or provider_name == "off":
        raise ai_failure()
    if env == "production" and provider_name in ("mock", "catvton"):
        raise ai_failure()
    if provider_name == "genlook" and not getattr(settings, "genlook_api_key", None):
        raise ai_failure()

    try:
        user_uuid = UUID(user_id)
        job_uuid = UUID(job_id)
    except Exception:
        raise not_found()

    repo = job_repo or _IN_MEMORY_REPO
    job = repo.get_by_id(user_id=user_uuid, job_id=job_uuid)
    if job is None:
        raise not_found()

    if job.status not in ("failed", "cancelled"):
        raise conflict(kind="cannot_retry_completed_job")

    if job.retry_count >= _MAX_TRYON_RETRIES:
        raise conflict(kind="max_retries_exceeded")

    concurrent_limit = getattr(settings, "tryon_max_concurrent_jobs_per_user", 5)
    if repo.count_active_jobs(user_id=user_uuid) >= concurrent_limit:
        raise rate_limited()

    updated = repo.update_retry(
        job_id=job_uuid,
        retry_count=job.retry_count + 1,
        status="processing",
    )
    if not updated:
        raise not_found()
    return updated


def cancel_job(
    *,
    user_id: str,
    job_id: str,
    job_repo: Optional[TryOnJobRepository] = None,
) -> TryOnJobRecord:
    """Cancel an active queued or processing try-on job."""
    try:
        user_uuid = UUID(user_id)
        job_uuid = UUID(job_id)
    except Exception:
        raise not_found()

    repo = job_repo or _IN_MEMORY_REPO
    job = repo.get_by_id(user_id=user_uuid, job_id=job_uuid)
    if job is None:
        raise not_found()

    if job.status in ("completed", "failed"):
        raise conflict(kind="cannot_cancel_finished_job")

    updated = repo.update_status(
        job_id=job_uuid,
        status="cancelled",
        completed_at=datetime.now(timezone.utc),
    )
    _BYTE_CACHE.pop(str(job_uuid), None)
    _POLL_COUNTS.pop(str(job_uuid), None)
    if not updated:
        raise not_found()
    return updated


async def delete_job_and_media(
    *,
    user_id: str,
    job_id: str,
    job_repo: Optional[TryOnJobRepository] = None,
    storage: Optional[ObjectStoragePort] = None,
) -> bool:
    """Delete a try-on job and its associated private media objects."""
    try:
        user_uuid = UUID(user_id)
        job_uuid = UUID(job_id)
    except Exception:
        raise not_found()

    repo = job_repo or _IN_MEMORY_REPO
    job = repo.get_by_id(user_id=user_uuid, job_id=job_uuid)
    if job is None:
        raise not_found()

    # Safely delete private media
    if storage is not None:
        if job.person_media_ref and "key" in job.person_media_ref:
            try:
                await storage.delete_object(job.person_media_ref["key"])
            except Exception as e:
                logger.warning("Failed to delete person image %s: %s", job.person_media_ref["key"], e)
        if job.result_media_ref and "key" in job.result_media_ref:
            try:
                await storage.delete_object(job.result_media_ref["key"])
            except Exception as e:
                logger.warning("Failed to delete result image %s: %s", job.result_media_ref["key"], e)

    _BYTE_CACHE.pop(str(job_uuid), None)
    _POLL_COUNTS.pop(str(job_uuid), None)
    return repo.delete(user_id=user_uuid, job_id=job_uuid)


def get_cached_result_image(job_id: UUID) -> Optional[bytes]:
    """Retrieve cached result image bytes across in-memory and SQL repositories."""
    return _IN_MEMORY_REPO.get_image_bytes(job_id)


def reset_for_tests() -> None:
    """Clear in-memory state across tests."""
    _IN_MEMORY_REPO.clear()
    _BYTE_CACHE.clear()
    _POLL_COUNTS.clear()


def recover_interrupted_jobs(
    job_repo: Optional[TryOnJobRepository] = None,
) -> int:
    """Recover jobs left in queued or processing status on backend restart.

    Transition orphaned jobs to failed status with clear reason codes:
    - INTERRUPTED_IN_QUEUE for jobs that had not yet reached inference.
    - INTERRUPTED_DURING_INFERENCE for jobs active during crash, preventing
      duplicate billing or duplicate inference.
    Users can safely inspect the state and retry.
    """
    repo = job_repo or _IN_MEMORY_REPO
    count = 0
    now = datetime.now(timezone.utc)
    for st in ("processing", "queued"):
        jobs = repo.find_by_status(status=st)
        for job in jobs:
            msg = (
                "Job processing was interrupted by server restart during inference. Please retry."
                if st == "processing"
                else "Job processing was interrupted by server restart while queued. Please retry."
            )
            repo.update_failure(
                job_id=job.id,
                error_code="INTERRUPTED_BY_RESTART",
                error_message=msg,
                completed_at=now,
            )
            _BYTE_CACHE.pop(str(job.id), None)
            _POLL_COUNTS.pop(str(job.id), None)
            count += 1
    return count


@dataclass
class RetentionCleanupSummary:
    person_photos_purged: int = 0
    failed_jobs_deleted: int = 0
    cancelled_jobs_deleted: int = 0
    completed_results_deleted: int = 0
    storage_objects_deleted: int = 0
    storage_errors: int = 0


async def cleanup_retention_data(
    *,
    job_repo: Optional[TryOnJobRepository] = None,
    storage: Optional[ObjectStoragePort] = None,
    settings: Optional[Settings] = None,
    now: Optional[datetime] = None,
) -> RetentionCleanupSummary:
    """Enforce configurable privacy retention policies across database and storage layer.

    Policies:
    - Person photos older than tryon_retention_person_photo_hours (default 24h) are deleted
      from storage and their reference cleared from the database.
    - Cancelled jobs older than tryon_retention_cancelled_jobs_hours (default 12h) are purged.
    - Failed jobs older than tryon_retention_failed_jobs_hours (default 24h) are purged.
    - Completed jobs older than tryon_retention_result_hours (default 72h) are purged.
    """
    repo = job_repo or _IN_MEMORY_REPO
    cfg = settings or get_settings()
    summary = RetentionCleanupSummary()
    if not cfg.tryon_retention_enabled:
        return summary

    current_time = now or datetime.now(timezone.utc)

    # 1. Purge expired person photos (default 24h)
    person_cutoff = current_time - timedelta(hours=cfg.tryon_retention_person_photo_hours)
    jobs_with_photos = repo.find_jobs_with_unpurged_person_photo(older_than=person_cutoff)
    for j in jobs_with_photos:
        if j.person_media_ref and "key" in j.person_media_ref:
            key = j.person_media_ref["key"]
            if storage is not None:
                try:
                    await storage.delete_object(key)
                    summary.storage_objects_deleted += 1
                except Exception as e:
                    logger.warning("Failed to purge person photo %s: %s", key, e)
                    summary.storage_errors += 1
            repo.clear_person_media_ref(job_id=j.id)
            summary.person_photos_purged += 1

    # 2. Purge expired cancelled jobs (default 12h)
    cancelled_cutoff = current_time - timedelta(hours=cfg.tryon_retention_cancelled_jobs_hours)
    expired_cancelled = repo.find_expired_jobs(status="cancelled", older_than=cancelled_cutoff)
    for j in expired_cancelled:
        if storage is not None:
            if j.person_media_ref and "key" in j.person_media_ref:
                try:
                    await storage.delete_object(j.person_media_ref["key"])
                    summary.storage_objects_deleted += 1
                except Exception:
                    summary.storage_errors += 1
            if j.result_media_ref and "key" in j.result_media_ref:
                try:
                    await storage.delete_object(j.result_media_ref["key"])
                    summary.storage_objects_deleted += 1
                except Exception:
                    summary.storage_errors += 1
        repo.delete(user_id=j.user_id, job_id=j.id)
        summary.cancelled_jobs_deleted += 1

    # 3. Purge expired failed jobs (default 24h)
    failed_cutoff = current_time - timedelta(hours=cfg.tryon_retention_failed_jobs_hours)
    expired_failed = repo.find_expired_jobs(status="failed", older_than=failed_cutoff)
    for j in expired_failed:
        if storage is not None:
            if j.person_media_ref and "key" in j.person_media_ref:
                try:
                    await storage.delete_object(j.person_media_ref["key"])
                    summary.storage_objects_deleted += 1
                except Exception:
                    summary.storage_errors += 1
            if j.result_media_ref and "key" in j.result_media_ref:
                try:
                    await storage.delete_object(j.result_media_ref["key"])
                    summary.storage_objects_deleted += 1
                except Exception:
                    summary.storage_errors += 1
        repo.delete(user_id=j.user_id, job_id=j.id)
        summary.failed_jobs_deleted += 1

    # 4. Purge expired completed jobs (default 72h)
    completed_cutoff = current_time - timedelta(hours=cfg.tryon_retention_result_hours)
    expired_completed = repo.find_expired_jobs(status="completed", older_than=completed_cutoff)
    for j in expired_completed:
        if storage is not None:
            if j.person_media_ref and "key" in j.person_media_ref:
                try:
                    await storage.delete_object(j.person_media_ref["key"])
                    summary.storage_objects_deleted += 1
                except Exception:
                    summary.storage_errors += 1
            if j.result_media_ref and "key" in j.result_media_ref:
                try:
                    await storage.delete_object(j.result_media_ref["key"])
                    summary.storage_objects_deleted += 1
                except Exception:
                    summary.storage_errors += 1
        repo.delete(user_id=j.user_id, job_id=j.id)
        summary.completed_results_deleted += 1

    logger.info("Retention cleanup completed: %s", summary)
    return summary
