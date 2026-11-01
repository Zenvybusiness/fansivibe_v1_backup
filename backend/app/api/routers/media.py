"""Media upload API router — endpoint `POST /v1/media/uploads` (Stage 2 P0-4 / M16).

Conforms to:
- OW-1 caller scoping: user_id derived exclusively from verified JWT token.
- Guest uploads rejected (401).
- Strict input validation and Pydantic request normalization.
- Required `Idempotency-Key` header with max 128 chars.
- Short-lived presigned PUT URL generation (15-min TTL).
- 201 Created wire response.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, get_storage_adapter
from app.api.errors import ApiError
from app.api.schemas.media import (
    MediaDownloadUrlResponse,
    PublishedMediaRefResponse,
    UploadAuthorizationRequest,
    UploadAuthorizationResponse,
    UploadCompleteRequest,
)
from app.application.media import AuthorizeMediaUpload, CompleteMediaUpload, GetMediaUrl
from app.config.settings import get_settings
from app.domain.ports.storage import ObjectStoragePort
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/v1/media", tags=["media"])



@router.post(
    "/uploads",
    response_model=UploadAuthorizationResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"description": "Unauthenticated or invalid token"},
        409: {"description": "Idempotency key conflict (different parameters)"},
        422: {"description": "Validation error (invalid size, MIME type, or headers)"},
        429: {"description": "Rate limit exceeded (max 30 authorizations/min)"},
        500: {"description": "Storage client signing failure"},
        503: {"description": "Database failure"},
    },
)
async def authorize_media_upload(
    request: UploadAuthorizationRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> UploadAuthorizationResponse:
    """Authorize a direct wardrobe photo upload to cloud object storage."""
    if not idempotency_key or not idempotency_key.strip():
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Idempotency-Key header is required.",
            details={"header": "Idempotency-Key"},
        )

    clean_key = idempotency_key.strip()
    if len(clean_key) > 128:
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message="Idempotency-Key must not exceed 128 characters.",
            details={"header": "Idempotency-Key"},
        )

    settings = get_settings()
    use_case = AuthorizeMediaUpload(
        storage=storage,
        db=db,
        active_key_id=settings.media_upload_active_key_id,
        key_ring=settings.effective_media_upload_key_ring,
    )

    result = await use_case.execute(
        user_id=user_id,
        purpose=request.purpose,
        content_type=request.contentType,
        size_bytes=request.sizeBytes,
        idempotency_key=clean_key,
        filename=request.filename,
        client_assertion_sha256=request.clientAssertionSha256,
    )

    return UploadAuthorizationResponse(**result)


@router.post(
    "/uploads/{upload_id}/complete",
    response_model=PublishedMediaRefResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Staging object not found or empty"},
        401: {"description": "Unauthenticated or invalid token"},
        404: {"description": "Upload not found (OW-1 caller scoping)"},
        409: {"description": "Upload currently processing conflict"},
        410: {"description": "Upload authorization expired"},
        422: {"description": "Validation error (corrupt, checksum mismatch, bombs)"},
        429: {"description": "Rate limited / lock contention"},
        500: {"description": "Transcoding failure"},
        503: {"description": "Storage or database failure"},
    },
)
async def complete_media_upload(
    upload_id: UUID,
    request: UploadCompleteRequest | None = None,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> PublishedMediaRefResponse:
    """Verify staging upload and publish canonical WebP media."""
    use_case = CompleteMediaUpload(
        storage=storage,
        db=db,
    )
    client_sha256 = request.clientSha256 if request is not None else None
    result = await use_case.execute(
        user_id=user_id,
        upload_id=upload_id,
        client_assertion_sha256=client_sha256,
    )
    return PublishedMediaRefResponse(**result)


@router.get(
    "/url",
    response_model=MediaDownloadUrlResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"description": "Unauthenticated or invalid token"},
        404: {"description": "Media not found (OW-1 caller scoping)"},
        422: {"description": "Validation error (missing uploadId/objectKey or invalid namespace)"},
        500: {"description": "Storage client signing failure"},
    },
)
async def get_media_url(
    upload_id: Annotated[UUID | None, Query(alias="uploadId")] = None,
    upload_id_snake: Annotated[UUID | None, Query(alias="upload_id", include_in_schema=False)] = None,
    object_key: Annotated[str | None, Query(alias="objectKey")] = None,
    object_key_snake: Annotated[str | None, Query(alias="object_key", include_in_schema=False)] = None,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> MediaDownloadUrlResponse:
    """Retrieve temporary presigned GET URL for verified published wardrobe media under OW-1."""
    effective_upload_id = upload_id or upload_id_snake
    effective_object_key = object_key or object_key_snake
    use_case = GetMediaUrl(storage=storage, db=db)
    result = await use_case.execute(
        user_id=user_id,
        upload_id=effective_upload_id,
        object_key=effective_object_key,
    )
    return MediaDownloadUrlResponse(**result)


