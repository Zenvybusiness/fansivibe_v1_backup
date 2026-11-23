"""Virtual Try-On Router (Phase 5C).

Authenticated endpoints for durable virtual try-on jobs:
- `POST   /v1/tryon/jobs` → Create try-on job (202)
- `GET    /v1/tryon/jobs/{job_id}` → Get job status (200)
- `GET    /v1/tryon/jobs/{job_id}/image` → Get generated try-on image (200)
- `POST   /v1/tryon/jobs/{job_id}/retry` → Retry failed job (202)
- `POST   /v1/tryon/jobs/{job_id}/cancel` → Cancel queued/processing job (200)
- `DELETE /v1/tryon/jobs/{job_id}` → Delete job and associated media (204)
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, Response, UploadFile, status

from app.api.deps import (
    get_current_user_id,
    get_storage_adapter,
    get_tryon_repository,
    get_tryon_wardrobe_repository,
)
from app.api.errors import conflict, not_found, validation
from app.api.schemas.tryon import TryOnJobStatus, TryOnJobSubmitted
from app.application import tryon as tryon_app
from app.application.media import read_image_bytes
from app.config.settings import get_settings
from app.domain.ports.storage import ObjectStoragePort

router = APIRouter(prefix="/v1/tryon", tags=["tryon"])


def _parse_garment_ids(raw: str) -> list[str]:
    try:
        decoded = json.loads(raw) if raw.strip() else []
    except Exception:
        raise validation([{"field": "garment_ids", "error": "must be a JSON list"}])
    if not isinstance(decoded, list) or any(
        not isinstance(item, str) for item in decoded
    ):
        raise validation([{"field": "garment_ids", "error": "must be a JSON list"}])
    return decoded


@router.post(
    "/jobs",
    response_model=TryOnJobSubmitted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": dict},
        409: {"model": dict},
        422: {"model": dict},
        429: {"model": dict},
        503: {"model": dict},
    },
)
def submit_tryon_job(
    background_tasks: BackgroundTasks,
    person_image: UploadFile = File(...),
    outfit_source: str = Form(...),
    garment_ids: str = Form(default="[]"),
    consent_version: str = Form(...),
    consent_accepted: bool = Form(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    job_repo: Any = Depends(get_tryon_repository),
    wardrobe_repo: Any = Depends(get_tryon_wardrobe_repository),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> TryOnJobSubmitted:
    """Submit a virtual try-on job with wardrobe validation and durable persistence."""
    ids = _parse_garment_ids(garment_ids)
    content = read_image_bytes(person_image)
    content_type = person_image.content_type or "image/jpeg"

    job, created = tryon_app.submit_job(
        user_id=str(user_id),
        outfit_source=outfit_source.strip(),
        garment_ids=ids,
        person_content_type=content_type,
        person_bytes=content,
        consent_version=consent_version.strip(),
        consent_accepted=consent_accepted,
        idempotency_key=(idempotency_key or "").strip(),
        wardrobe_repo=wardrobe_repo,
        job_repo=job_repo,
        storage=storage,
    )

    settings = tryon_app.get_settings()
    is_mock = (getattr(settings, "tryon_provider", "mock") != "catvton")

    if created:
        background_tasks.add_task(
            tryon_app.store_person_image_async,
            storage=storage,
            user_id=job.user_id,
            job_id=job.id,
            person_bytes=content,
            content_type=content_type,
        )
        if not is_mock:
            background_tasks.add_task(
                tryon_app.execute_tryon_inference,
                job_id=job.id,
                user_id=job.user_id,
                job_repo=job_repo,
                storage=storage,
                wardrobe_repo=wardrobe_repo,
            )

    return TryOnJobSubmitted(job_id=str(job.id), status=job.status, is_mock=is_mock)



@router.get(
    "/jobs/{job_id}",
    response_model=TryOnJobStatus,
    responses={401: {"model": dict}, 404: {"model": dict}},
)
def get_tryon_job(
    job_id: str,
    user_id: UUID = Depends(get_current_user_id),
    job_repo: Any = Depends(get_tryon_repository),
) -> TryOnJobStatus:
    """Poll job status (owner-only, 404-not-403)."""
    job = tryon_app.get_job(user_id=str(user_id), job_id=job_id, job_repo=job_repo)
    if job is None:
        raise not_found()

    # In mock mode, advance lifecycle deterministically
    settings = tryon_app.get_settings()
    is_mock = (getattr(settings, "tryon_provider", "mock") != "catvton")
    if is_mock and job.status != "completed":
        job = tryon_app.poll_job(job, job_repo=job_repo)

    progress = 100 if job.status == "completed" else (0 if job.status in ("failed", "cancelled") else 50)

    return TryOnJobStatus(
        job_id=str(job.id),
        status=job.status,
        progress=progress,
        is_mock=is_mock,
        outfit_source=job.outfit_source,
        error_code=job.error_code,
        error_message=job.error_message,
        retry_count=job.retry_count,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        garment_ids=list(job.garment_ids),
        result_media_ref=job.result_media_ref,
    )


@router.get(
    "/jobs/{job_id}/image",
    responses={
        401: {"model": dict},
        404: {"model": dict},
        409: {"model": dict},
    },
)
async def get_tryon_image(
    job_id: str,
    user_id: UUID = Depends(get_current_user_id),
    job_repo: Any = Depends(get_tryon_repository),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> Response:
    """Fetch the composite try-on image (completed jobs only)."""
    job = tryon_app.get_job(user_id=str(user_id), job_id=job_id, job_repo=job_repo)
    if job is None:
        raise not_found()

    if job.status != "completed":
        raise conflict(kind="not_completed")

    content: bytes | None = job.image_bytes
    if content is None:
        content = tryon_app.get_cached_result_image(job.id)
    if content is None and storage is not None and job.result_media_ref and "key" in job.result_media_ref:
        try:
            content = await storage.read_object(job.result_media_ref["key"])
        except Exception:
            content = None

    if content is None:
        raise not_found()

    media_type = "image/svg+xml" if content.startswith(b"<svg") else "image/jpeg"
    return Response(content=content, media_type=media_type)


@router.post(
    "/jobs/{job_id}/retry",
    response_model=TryOnJobSubmitted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": dict},
        404: {"model": dict},
        409: {"model": dict},
    },
)
def retry_tryon_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
    job_repo: Any = Depends(get_tryon_repository),
    wardrobe_repo: Any = Depends(get_tryon_wardrobe_repository),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> TryOnJobSubmitted:
    """Retry an eligible failed or cancelled try-on job."""
    job = tryon_app.retry_job(user_id=str(user_id), job_id=job_id, job_repo=job_repo)

    background_tasks.add_task(
        tryon_app.execute_tryon_inference,
        job_id=job.id,
        user_id=job.user_id,
        job_repo=job_repo,
        storage=storage,
        wardrobe_repo=wardrobe_repo,
    )

    is_mock = (get_settings().tryon_provider != "catvton")
    return TryOnJobSubmitted(job_id=str(job.id), status=job.status, is_mock=is_mock)


@router.post(
    "/jobs/{job_id}/cancel",
    response_model=TryOnJobStatus,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": dict},
        404: {"model": dict},
        409: {"model": dict},
    },
)
def cancel_tryon_job(
    job_id: str,
    user_id: UUID = Depends(get_current_user_id),
    job_repo: Any = Depends(get_tryon_repository),
) -> TryOnJobStatus:
    """Cancel an active queued or processing try-on job."""
    job = tryon_app.cancel_job(user_id=str(user_id), job_id=job_id, job_repo=job_repo)
    is_mock = (job.provider != "catvton")
    return TryOnJobStatus(
        job_id=str(job.id),
        status=job.status,
        progress=0,
        is_mock=is_mock,
        outfit_source=job.outfit_source,
        error_code=job.error_code,
        error_message=job.error_message,
        retry_count=job.retry_count,
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        garment_ids=list(job.garment_ids),
        result_media_ref=job.result_media_ref,
    )


@router.delete(
    "/jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        401: {"model": dict},
        404: {"model": dict},
    },
)
async def delete_tryon_job(
    job_id: str,
    user_id: UUID = Depends(get_current_user_id),
    job_repo: Any = Depends(get_tryon_repository),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> Response:
    """Delete a try-on job and its private media objects."""
    deleted = await tryon_app.delete_job_and_media(
        user_id=str(user_id),
        job_id=job_id,
        job_repo=job_repo,
        storage=storage,
    )
    if not deleted:
        raise not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
