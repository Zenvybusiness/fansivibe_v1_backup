"""Mock virtual try-on router — Stage F0 endpoints (mock only, $0).

- `POST /v1/tryon/jobs` (multipart person photo + outfit refs) → 202
- `GET  /v1/tryon/jobs/{job_id}` (owner-only poll) → bare status
- `GET  /v1/tryon/jobs/{job_id}/image` (owner-only mock SVG) → image

Authenticated like the analysis passes (guests get 401 server-side, in
addition to the Flutter button gate). Bytes are hashed and discarded —
garment pixels travel as caller-supplied IDs only (the audit proves the
backend cannot retrieve wardrobe image bytes), and the result is mock
SVG labelled TEST DATA (`is_mock: true` on every response). Zero DB
rows; no paid provider exists in this stage.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from fastapi.responses import Response

from app.api.deps import get_current_user_id
from app.api.errors import conflict, not_found, validation
from app.api.schemas.tryon import TryOnJobStatus, TryOnJobSubmitted
from app.application.media import read_image_bytes
from app.application import tryon as tryon_app

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
    status_code=202,
    responses={
        401: {"model": dict},
        409: {"model": dict},
        422: {"model": dict},
        429: {"model": dict},
        503: {"model": dict},
    },
)
def submit_tryon_job(
    person_image: UploadFile = File(...),
    outfit_source: str = Form(...),
    garment_ids: str = Form(default="[]"),
    consent_version: str = Form(...),
    consent_accepted: bool = Form(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
) -> TryOnJobSubmitted:
    """Submit one mock try-on job (both outfit paths share this endpoint).

    Path A sends the TodayLook `selectedItemIds`; Path B sends the
    outfit/saved/wardrobe ids — both as labels only, never as pixels.
    """
    ids = _parse_garment_ids(garment_ids)
    content = read_image_bytes(person_image)
    job, _ = tryon_app.submit_job(
        user_id=str(user_id),
        outfit_source=outfit_source.strip(),
        garment_ids=ids,
        person_content_type=person_image.content_type or "",
        person_bytes=content,
        consent_version=consent_version.strip(),
        consent_accepted=consent_accepted,
        idempotency_key=(idempotency_key or "").strip(),
    )
    return TryOnJobSubmitted(job_id=job.job_id, status=job.status, is_mock=True)


@router.get(
    "/jobs/{job_id}",
    response_model=TryOnJobStatus,
    responses={401: {"model": dict}, 404: {"model": dict}},
)
def get_tryon_job(
    job_id: str,
    user_id: UUID = Depends(get_current_user_id),
) -> TryOnJobStatus:
    """Poll one mock job (owner-only, 404-not-403)."""
    job = tryon_app.get_job(user_id=str(user_id), job_id=job_id)
    if job is None:
        raise not_found()
    job = tryon_app.poll_job(job)
    progress = 100 if job.status == "completed" else 50
    return TryOnJobStatus(
        job_id=job.job_id,
        status=job.status,
        progress=progress,
        is_mock=True,
        outfit_source=job.outfit_source,
    )


@router.get(
    "/jobs/{job_id}/image",
    responses={
        401: {"model": dict},
        404: {"model": dict},
        409: {"model": dict},
    },
)
def get_tryon_image(
    job_id: str,
    user_id: UUID = Depends(get_current_user_id),
) -> Response:
    """Fetch the mock composite SVG (completed jobs only)."""
    job = tryon_app.get_job(user_id=str(user_id), job_id=job_id)
    if job is None or job.image_bytes is None:
        if job is not None and job.status != "completed":
            raise conflict(kind="not_completed")
        raise not_found()
    return Response(content=job.image_bytes, media_type="image/svg+xml")
