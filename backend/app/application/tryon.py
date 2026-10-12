"""Stage F0 mock try-on jobs — in-memory, zero DB rows, $0.

Design (approved free-first plan): no migration is created for the mock
stage. Jobs live in a process-local store (same single-process scope as
the existing ``rate_limit`` limiter) and hold only content digests plus
the rendered mock SVG — real person image bytes are hashed and
discarded like the ephemeral analysis passes, never persisted, logged,
or echoed. A durable ``tryon_jobs`` table rides with the paid-provider
stage, which reuses the idempotency/consent/quota shapes frozen here.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import date

from app.api.errors import conflict, rate_limited, validation
from app.application.media import sha256_hex
from app.config.settings import get_settings
from app.domain.ports.tryon_provider import MockTryOnProvider

_OUTFIT_SOURCES = frozenset({"today", "outfit", "saved", "wardrobe"})
_ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_PERSON_BYTES = 20 * 1024 * 1024
_MAX_GARMENT_IDS = 8

_POLLS_TO_COMPLETE = 1


@dataclass
class TryOnJob:
    """One mock try-on job. ``image_bytes`` is the rendered mock SVG only."""

    job_id: str
    user_id: str
    outfit_source: str
    garment_ids: tuple
    person_digest: str
    seed: str
    consent_version: str
    idempotency_key: str
    payload_digest: str
    status: str = "processing"
    polls: int = 0
    image_bytes: bytes | None = None


_lock = threading.Lock()
_JOBS: dict[str, TryOnJob] = {}
_IDEMPOTENCY: dict[tuple[str, str], str] = {}
_QUOTA: dict[tuple[str, str], int] = {}


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
) -> tuple[TryOnJob, bool]:
    """Validate, enforce idempotency/quota, and create (or replay) a job.

    Returns ``(job, created)`` — replay of the same key+payload returns
    the original with ``created=False``; same key with a different
    payload raises 409 CONFLICT (C-12 pattern).
    """
    settings = get_settings()
    if not settings.tryon_enabled or settings.tryon_provider == "off":
        from app.api.errors import ai_failure

        raise ai_failure()
    if not (idempotency_key or "").strip():
        raise validation(
            [{"field": "Idempotency-Key", "error": "is required"}]
        )
    if not consent_accepted:
        raise validation(
            [{"field": "consent_accepted", "error": "explicit consent is required"}]
        )
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
        raise validation(
            [{"field": "outfit_source", "error": "unknown outfit source"}]
        )
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
            raise validation(
                [{"field": "garment_ids", "error": "ids must be 1..200 chars"}]
            )
    if person_content_type not in _ALLOWED_IMAGE_TYPES:
        raise validation(
            [{"field": "person_image", "error": "must be jpeg, png, or webp"}]
        )
    if not person_bytes or len(person_bytes) > _MAX_PERSON_BYTES:
        raise validation(
            [{"field": "person_image", "error": "must be non-empty, at most 20 MB"}]
        )

    person_digest = sha256_hex(person_bytes)
    digest = _payload_digest(
        outfit_source=outfit_source,
        garment_ids=garment_ids,
        person_digest=person_digest,
        consent_version=consent_version,
    )
    day = (today or date.today()).isoformat()
    with _lock:
        existing_id = _IDEMPOTENCY.get((user_id, idempotency_key))
        if existing_id is not None:
            existing = _JOBS[existing_id]
            if existing.payload_digest != digest:
                raise conflict(kind="idempotency_key_reuse")
            return existing, False
        used = _QUOTA.get((user_id, day), 0)
        if used >= settings.tryon_daily_quota_per_user:
            raise rate_limited()
        job = TryOnJob(
            job_id=uuid.uuid4().hex,
            user_id=user_id,
            outfit_source=outfit_source,
            garment_ids=tuple(garment_ids),
            person_digest=person_digest,
            seed=seed,
            consent_version=consent_version,
            idempotency_key=idempotency_key,
            payload_digest=digest,
        )
        _JOBS[job.job_id] = job
        _IDEMPOTENCY[(user_id, idempotency_key)] = job.job_id
        _QUOTA[(user_id, day)] = used + 1
        return job, True


def get_job(*, user_id: str, job_id: str) -> TryOnJob | None:
    """Owner-scoped lookup — unknown or foreign ids return None (404)."""
    job = _JOBS.get(job_id)
    if job is None or job.user_id != user_id:
        return None
    return job


def poll_job(job: TryOnJob) -> TryOnJob:
    """Advance the mock lifecycle: processing → completed (deterministic).

    First poll stays ``processing`` so clients exercise polling; the next
    renders the mock SVG once. No provider call, no cost, no PII stored.
    """
    with _lock:
        job.polls += 1
        if job.polls > _POLLS_TO_COMPLETE and job.status != "completed":
            provider = MockTryOnProvider()
            job.image_bytes = provider.render(
                person_digest=job.person_digest,
                garment_labels=list(job.garment_ids),
                seed=job.seed,
                outfit_source=job.outfit_source,
            )
            job.status = "completed"
        return job


def reset_for_tests() -> None:
    """Clear process-local mock state (tests only)."""
    with _lock:
        _JOBS.clear()
        _IDEMPOTENCY.clear()
        _QUOTA.clear()
