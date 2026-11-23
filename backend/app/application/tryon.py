"""Virtual Try-On Application Layer (Phase 5C).

Durable job management, ownership validation, media persistence, and
asynchronous provider execution.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
import logging
import threading
from typing import Any, Optional
from uuid import UUID, uuid4

from app.api.errors import ai_failure, conflict, not_found, rate_limited, validation
from app.application.media import sha256_hex
from app.config.settings import get_settings
from app.domain.ports.repositories import (
    TryOnJobRecord,
    TryOnJobRepository,
    WardrobeItemRepository,
)
from app.domain.ports.storage import ObjectStoragePort
from app.domain.ports.tryon_provider import CatVTONTryOnProvider, MockTryOnProvider

logger = logging.getLogger("fansivibe.tryon.application")

_OUTFIT_SOURCES = frozenset({"today", "outfit", "saved", "wardrobe"})
_ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_PERSON_BYTES = 20 * 1024 * 1024
_MAX_GARMENT_IDS = 8

_POLLS_TO_COMPLETE = 1


class InMemoryTryOnJobRepository:
    """Thread-safe in-memory repository conforming to TryOnJobRepository protocol.

    Provides high-speed zero-database execution for unit tests and fallback environments.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
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
            self._jobs[job_id] = record
            if idempotency_key:
                self._idempotency[(user_id, idempotency_key)] = job_id
        return record

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


# Default in-memory store for test/fallback usage
_IN_MEMORY_REPO = InMemoryTryOnJobRepository()
_POLL_COUNTS: dict[str, int] = {}
_BYTE_CACHE: dict[str, tuple[bytes, str]] = {}  # job_id -> (person_bytes, content_type)


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

    if person_content_type not in _ALLOWED_IMAGE_TYPES:
        raise validation([{"field": "person_image", "error": "must be jpeg, png, or webp"}])

    if not person_bytes or len(person_bytes) > _MAX_PERSON_BYTES:
        raise validation(
            [{"field": "person_image", "error": "must be non-empty, at most 20 MB"}]
        )

    # User ID parsing
    try:
        user_uuid = UUID(user_id)
    except Exception:
        raise validation([{"field": "user_id", "error": "invalid user UUID"}])

    # Digital Wardrobe garment validation & ownership check
    first_garment_uuid: Optional[UUID] = None
    if outfit_source == "wardrobe":
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
    person_digest = sha256_hex(person_bytes)
    digest = _payload_digest(
        outfit_source=outfit_source,
        garment_ids=garment_ids,
        person_digest=person_digest,
        consent_version=consent_version,
    )
    current_day = today or date.today()

    # Idempotency check
    existing = repo.find_by_idempotency_key(
        user_id=user_uuid, idempotency_key=idempotency_key
    )
    if existing is not None:
        if existing.request_fingerprint != digest:
            raise conflict(kind="idempotency_key_reuse")
        return existing, False

    # Quota check
    used = repo.count_today_jobs(user_id=user_uuid, day=current_day)
    if used >= settings.tryon_daily_quota_per_user:
        raise rate_limited()

    job_id = uuid4()
    person_ext = "webp" if "webp" in person_content_type else ("png" if "png" in person_content_type else "jpg")
    person_key = f"users/{user_uuid}/tryon/{job_id}/person.{person_ext}"
    person_media_ref = {
        "key": person_key,
        "mediaType": person_content_type,
        "sizeBytes": len(person_bytes),
        "contentHash": person_digest,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
    }

    # Store person bytes cache for fast retrieval in memory/background worker
    _BYTE_CACHE[str(job_id)] = (person_bytes, person_content_type)

    initial_status = "processing" if settings.tryon_provider == "mock" else "queued"

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

    return created_job, True


async def store_person_image_async(
    *,
    storage: ObjectStoragePort,
    user_id: UUID,
    job_id: UUID,
    person_bytes: bytes,
    content_type: str,
) -> None:
    """Safely and privately persists person image bytes to object storage."""
    person_ext = "webp" if "webp" in content_type else ("png" if "png" in content_type else "jpg")
    key = f"users/{user_id}/tryon/{job_id}/person.{person_ext}"
    try:
        await storage.put_object(key, person_bytes, content_type=content_type)
    except Exception as e:
        logger.warning("Failed to persist person image to storage for job %s: %s", job_id, e)


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
    repo = job_repo or _IN_MEMORY_REPO
    job = repo.get_by_id(user_id=user_id, job_id=job_id)
    if job is None or job.status == "cancelled":
        logger.info("TryOn job %s cancelled or absent; stopping execution.", job_id)
        return

    now = datetime.now(timezone.utc)
    repo.update_status(job_id=job_id, status="processing", processing_started_at=now)

    settings = get_settings()
    provider_name = settings.tryon_provider

    # Resolve person bytes
    cached_person = _BYTE_CACHE.get(str(job_id))
    person_bytes = cached_person[0] if cached_person else None
    if person_bytes is None and storage is not None and job.person_media_ref:
        try:
            person_bytes = await storage.read_object(job.person_media_ref["key"])
        except Exception as e:
            logger.warning("Could not read person image from storage for job %s: %s", job_id, e)

    # Resolve garment bytes if available
    garment_bytes: Optional[bytes] = None
    category = "upper"
    if job.garment_id and wardrobe_repo is not None:
        try:
            item = wardrobe_repo.get_by_id(user_id=user_id, item_id=job.garment_id)
            if item:
                if item.category in ("bottoms", "pants", "jeans", "skirts", "shorts"):
                    category = "lower"
                elif item.category in ("dresses", "jumpsuits", "overall"):
                    category = "overall"
                if storage is not None and item.image_ref and "key" in item.image_ref:
                    garment_bytes = await storage.read_object(item.image_ref["key"])
        except Exception as e:
            logger.warning("Could not retrieve garment image for job %s: %s", job_id, e)

    # Execute provider render
    try:
        if provider_name == "catvton":
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
    except Exception as e:
        logger.error("TryOn inference failed for job %s: %s", job_id, e)
        repo.update_failure(
            job_id=job_id,
            error_code="AI_INFERENCE_FAILURE",
            error_message="Virtual try-on model processing failed. Please try again.",
            completed_at=datetime.now(timezone.utc),
        )
        return

    # Check for cancellation before persisting
    latest = repo.get_by_id(user_id=user_id, job_id=job_id)
    if latest is not None and latest.status == "cancelled":
        logger.info("Job %s was cancelled during inference; discarding result.", job_id)
        return

    # Persist generated result privately
    is_svg = result_bytes.startswith(b"<svg")
    result_ext = "svg" if is_svg else "jpg"
    result_content_type = "image/svg+xml" if is_svg else "image/jpeg"
    result_key = f"users/{user_id}/tryon/{job_id}/result.{result_ext}"

    result_media_ref = {
        "key": result_key,
        "mediaType": result_content_type,
        "sizeBytes": len(result_bytes),
        "contentHash": sha256_hex(result_bytes),
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "isMock": (provider_name != "catvton"),
    }

    if storage is not None:
        try:
            await storage.put_object(
                result_key,
                result_bytes,
                content_type=result_content_type,
            )
        except Exception as e:
            logger.error("Failed to store try-on result image for job %s: %s", job_id, e)
            repo.update_failure(
                job_id=job_id,
                error_code="STORAGE_FAILURE",
                error_message="Failed to securely store generated try-on result.",
                completed_at=datetime.now(timezone.utc),
            )
            return

    # Cache result bytes for in-memory / fast responses
    if isinstance(repo, InMemoryTryOnJobRepository):
        repo.set_image_bytes(job_id, result_bytes)
    _IN_MEMORY_REPO.set_image_bytes(job_id, result_bytes)

    # Complete job
    repo.update_result(
        job_id=job_id,
        result_media_ref=result_media_ref,
        completed_at=datetime.now(timezone.utc),
    )


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
        if isinstance(repo, InMemoryTryOnJobRepository):
            repo.set_image_bytes(job.id, rendered)
        _IN_MEMORY_REPO.set_image_bytes(job.id, rendered)

        now = datetime.now(timezone.utc)
        result_media_ref = {
            "key": f"users/{job.user_id}/tryon/{job.id}/result.svg",
            "mediaType": "image/svg+xml",
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
        if updated:
            return updated
    return job


def retry_job(
    *,
    user_id: str,
    job_id: str,
    job_repo: Optional[TryOnJobRepository] = None,
) -> TryOnJobRecord:
    """Retry an eligible failed or cancelled try-on job."""
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

    Transition orphaned jobs to failed status with clear INTERRUPTED_BY_RESTART
    error code so they never become falsely completed and users can retry.
    """
    repo = job_repo or _IN_MEMORY_REPO
    count = 0
    now = datetime.now(timezone.utc)
    for st in ("processing", "queued"):
        jobs = repo.find_by_status(status=st)
        for job in jobs:
            repo.update_failure(
                job_id=job.id,
                error_code="INTERRUPTED_BY_RESTART",
                error_message="Processing was interrupted by server restart. Please retry.",
                completed_at=now,
            )
            count += 1
    return count

    _POLL_COUNTS.clear()
    _BYTE_CACHE.clear()
