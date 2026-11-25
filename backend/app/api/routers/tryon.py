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

import asyncio
from dataclasses import asdict
import json
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, Request, Response, UploadFile, status

from app.api.deps import (
    get_current_user_id,
    get_storage_adapter,
    get_tryon_repository,
    get_tryon_wardrobe_repository,
    get_wardrobe_repository,
    require_operator_auth,
)
from app.api.errors import ApiError, conflict, not_found, validation
from app.api.schemas.tryon import TryOnJobStatus, TryOnJobSubmitted
from app.application import tryon as tryon_app
from app.application.media import read_image_bytes
from app.config.settings import get_settings
from app.domain.ports.storage import ObjectStoragePort
from app.domain.ports.tryon_provider import ProviderPayloadError
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/v1/tryon", tags=["tryon"])


async def _execute_inference_with_fresh_session(
    *,
    job_id: UUID,
    user_id: UUID,
    storage: ObjectStoragePort,
    db_override: Any = None,
    wardrobe_override: Any = None,
) -> None:
    """Run try-on inference in background with an independently managed DB session."""
    from app.infrastructure.db.repositories import TryOnJobRepositorySQL, WardrobeItemRepositorySQL
    from app.infrastructure.db.session import SessionLocal

    db = None
    gen = None
    w_gen = None
    try:
        if db_override is not None:
            res = db_override()
            if hasattr(res, "__next__"):
                gen = res
                db = next(res)
            else:
                db = res
        else:
            db = SessionLocal()

        bg_job_repo = TryOnJobRepositorySQL(db)
        if wardrobe_override is not None:
            w_res = wardrobe_override()
            if hasattr(w_res, "__next__"):
                w_gen = w_res
                bg_wardrobe_repo = next(w_res)
            else:
                bg_wardrobe_repo = w_res
        else:
            bg_wardrobe_repo = WardrobeItemRepositorySQL(db)

        await tryon_app.execute_tryon_inference(
            job_id=job_id,
            user_id=user_id,
            job_repo=bg_job_repo,
            storage=storage,
            wardrobe_repo=bg_wardrobe_repo,
        )
    finally:
        if w_gen is not None:
            try:
                w_gen.close()
            except Exception:
                pass
        if gen is not None:
            try:
                gen.close()
            except Exception:
                pass
        elif db is not None:
            try:
                db.close()
            except Exception:
                pass


def _schedule_inference(
    *,
    background_tasks: BackgroundTasks,
    request: Request,
    job_id: UUID,
    user_id: UUID,
    job_repo: Any,
    wardrobe_repo: Any,
    storage: ObjectStoragePort,
) -> None:
    """Schedule background inference without reusing closed request DB sessions."""
    overrides = request.app.dependency_overrides
    if overrides.get(get_tryon_repository) is not None or isinstance(
        job_repo, tryon_app.InMemoryTryOnJobRepository
    ):
        background_tasks.add_task(
            tryon_app.execute_tryon_inference,
            job_id=job_id,
            user_id=user_id,
            job_repo=job_repo,
            storage=storage,
            wardrobe_repo=wardrobe_repo,
        )
    else:
        background_tasks.add_task(
            _execute_inference_with_fresh_session,
            job_id=job_id,
            user_id=user_id,
            storage=storage,
            db_override=overrides.get(get_db),
            wardrobe_override=overrides.get(get_wardrobe_repository),
        )


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
async def submit_tryon_job(
    request: Request,
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
    is_mock = (getattr(settings, "tryon_provider", "mock") == "mock")

    if created:
        # Hard prerequisite: persist person image durably BEFORE scheduling inference
        try:
            await tryon_app.store_person_image_async(
                storage=storage,
                user_id=job.user_id,
                job_id=job.id,
                person_bytes=None,
                content_type=content_type,
                job_repo=job_repo,
            )
        except Exception:
            raise ApiError(
                status_code=503,
                code="STORAGE_FAILURE",
                message="Failed to securely store input person image. Please try again.",
            )

        if not is_mock:
            _schedule_inference(
                background_tasks=background_tasks,
                request=request,
                job_id=job.id,
                user_id=job.user_id,
                job_repo=job_repo,
                wardrobe_repo=wardrobe_repo,
                storage=storage,
            )

    return TryOnJobSubmitted(job_id=str(job.id), status=job.status, is_mock=is_mock)



def _cancelled_notice_for_job(job: tryon_app.TryOnJobRecord) -> str | None:
    if job.status != "cancelled":
        return job.error_message
    if job.error_message:
        return job.error_message
    if job.provider not in ("mock", "catvton"):
        return (
            "Cancelled locally. If the request was already submitted to the "
            "try-on provider, it may still consume a credit."
        )
    return None


@router.get(
    "/jobs/{job_id}",
    response_model=TryOnJobStatus,
    responses={401: {"model": dict}, 404: {"model": dict}},
)
async def get_tryon_job(
    job_id: str,
    user_id: UUID = Depends(get_current_user_id),
    job_repo: Any = Depends(get_tryon_repository),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> TryOnJobStatus:
    """Poll job status (owner-only, 404-not-403)."""
    job = tryon_app.get_job(user_id=str(user_id), job_id=job_id, job_repo=job_repo)
    if job is None:
        raise not_found()

    # In mock mode, advance lifecycle deterministically for mock jobs only
    settings = tryon_app.get_settings()
    is_mock = (getattr(settings, "tryon_provider", "mock") == "mock")
    if is_mock and job.provider == "mock" and job.status in ("queued", "processing"):
        prev_status = job.status
        job = tryon_app.poll_job(job, job_repo=job_repo)
        if (
            prev_status != "completed"
            and job.status == "completed"
            and storage is not None
            and job.result_media_ref
            and "key" in job.result_media_ref
            and job.image_bytes
        ):
            try:
                await storage.put_object(
                    job.result_media_ref["key"],
                    job.image_bytes,
                    content_type=job.result_media_ref.get("mediaType", "image/svg+xml"),
                )
            except Exception:
                pass

    progress = 100 if job.status == "completed" else (0 if job.status in ("failed", "cancelled") else 50)

    return TryOnJobStatus(
        job_id=str(job.id),
        status=job.status,
        progress=progress,
        is_mock=is_mock,
        outfit_source=job.outfit_source,
        error_code=job.error_code,
        error_message=_cancelled_notice_for_job(job),
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
            content = await storage.read_object(
                job.result_media_ref["key"],
                max_bytes=tryon_app._MAX_RESULT_BYTES,
            )
        except Exception:
            content = None

    if content is None:
        raise not_found()

    allow_svg = (job.provider == "mock") or bool((job.result_media_ref or {}).get("isMock"))
    try:
        media_type, _ = tryon_app.validate_and_inspect_output_image(
            content,
            allow_svg=allow_svg,
            provider_id=job.provider,
        )
    except ProviderPayloadError:
        raise not_found()

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
    request: Request,
    job_id: str,
    background_tasks: BackgroundTasks,
    user_id: UUID = Depends(get_current_user_id),
    job_repo: Any = Depends(get_tryon_repository),
    wardrobe_repo: Any = Depends(get_tryon_wardrobe_repository),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> TryOnJobSubmitted:
    """Retry an eligible failed or cancelled try-on job."""
    job = tryon_app.retry_job(user_id=str(user_id), job_id=job_id, job_repo=job_repo)

    _schedule_inference(
        background_tasks=background_tasks,
        request=request,
        job_id=job.id,
        user_id=job.user_id,
        job_repo=job_repo,
        wardrobe_repo=wardrobe_repo,
        storage=storage,
    )

    is_mock = (get_settings().tryon_provider == "mock")
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
    is_mock = (job.provider == "mock")
    return TryOnJobStatus(
        job_id=str(job.id),
        status=job.status,
        progress=0,
        is_mock=is_mock,
        outfit_source=job.outfit_source,
        error_code=job.error_code,
        error_message=_cancelled_notice_for_job(job),
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


@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_operator_auth)],
    include_in_schema=False,
    responses={
        200: {"model": dict},
        401: {"model": dict},
        403: {"model": dict},
        503: {"model": dict},
    },
)
async def get_tryon_health(
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> dict[str, Any]:
    """Operator-only health status separating local backend, storage, and provider config.

    Never queries external provider account/credit endpoints.
    Use ``GET /v1/tryon/health/credits`` for explicit external credit/account checks.
    """
    settings = get_settings()
    provider_name = settings.tryon_provider
    env = settings.environment

    local_backend_status: dict[str, Any] = {
        "status": "healthy" if (settings.tryon_enabled and provider_name != "off") else "disabled",
        "tryon_enabled": bool(settings.tryon_enabled),
        "environment": env,
    }

    provider_config_status: dict[str, Any]
    if provider_name == "commercial":
        try:
            config = tryon_app.CommercialTryOnProviderConfig(
                provider_name=settings.tryon_commercial_provider_name,
                api_key=settings.tryon_commercial_api_key or "",
                endpoint_url=settings.tryon_commercial_endpoint_url or "",
                connect_timeout_s=settings.tryon_commercial_connect_timeout_s,
                inference_timeout_s=settings.tryon_commercial_inference_timeout_s,
                max_retries=settings.tryon_commercial_max_retries,
            )
            tryon_app.CommercialTryOnProvider(config)
            provider_config_status = {
                "provider": provider_name,
                "configured": True,
                "status": "healthy",
            }
        except Exception as exc:
            provider_config_status = {
                "provider": provider_name,
                "configured": False,
                "status": "unavailable",
                "error": type(exc).__name__,
            }
    elif provider_name == "genlook":
        from app.infrastructure.external.genlook_tryon import (
            GENLOOK_DEFAULT_BASE_URL,
            GenlookTryOnConfig,
            GenlookTryOnProvider,
        )

        try:
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
            GenlookTryOnProvider(g_config)
            provider_config_status = {
                "provider": "genlook",
                "configured": True,
                "status": "healthy",
                "keep_for_days": g_config.keep_for_days,
                "ai_label": g_config.ai_label,
                "poll_timeout_s": g_config.poll_timeout_s,
            }
        except Exception as exc:
            provider_config_status = {
                "provider": provider_name,
                "configured": False,
                "status": "unavailable",
                "error": type(exc).__name__,
            }
    elif provider_name == "catvton":
        provider_config_status = {
            "provider": "catvton",
            "configured": True,
            "status": "healthy" if env != "production" else "blocked_in_production",
            "environment": env,
            "mode": "local_research",
        }
    elif provider_name == "mock":
        provider_config_status = {
            "provider": "mock",
            "configured": True,
            "status": "healthy" if env != "production" else "unsupported_in_production",
            "mode": "test_data",
        }
    else:
        provider_config_status = {
            "provider": provider_name,
            "configured": False,
            "status": "disabled",
        }

    storage_status: dict[str, Any]
    check_fn = getattr(storage, "check_health", None)
    if callable(check_fn):
        try:
            if asyncio.iscoroutinefunction(check_fn):
                storage_status = await check_fn()
            else:
                storage_status = await asyncio.to_thread(check_fn)
        except Exception as exc:
            storage_status = {
                "provider": settings.media_storage_provider,
                "status": "unavailable",
                "error": type(exc).__name__,
            }
    else:
        storage_status = {
            "provider": settings.media_storage_provider,
            "status": "healthy",
        }

    overall = "healthy"
    if local_backend_status.get("status") != "healthy":
        overall = "degraded"
    if provider_config_status.get("status") in (
        "unavailable",
        "blocked_in_production",
        "unsupported_in_production",
        "degraded",
    ):
        overall = "degraded"
    if storage_status.get("status") in ("unhealthy", "unavailable"):
        overall = "degraded"

    return {
        "status": overall,
        "environment": env,
        "local_backend": local_backend_status,
        "provider_config": provider_config_status,
        "provider": provider_config_status,
        "storage": storage_status,
        "credits": {
            "checked": False,
            "endpoint": "/v1/tryon/health/credits",
        },
        "retention_enabled": settings.tryon_retention_enabled,
        "retention_policies": {
            "person_photo_hours": settings.tryon_retention_person_photo_hours,
            "result_hours": settings.tryon_retention_result_hours,
            "failed_jobs_hours": settings.tryon_retention_failed_jobs_hours,
            "cancelled_jobs_hours": settings.tryon_retention_cancelled_jobs_hours,
        },
        "quotas": {
            "daily_per_user": settings.tryon_daily_quota_per_user,
            "max_concurrent_per_user": settings.tryon_max_concurrent_jobs_per_user,
        },
    }


@router.get(
    "/health/credits",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_operator_auth)],
    include_in_schema=False,
    responses={
        200: {"model": dict},
        401: {"model": dict},
        403: {"model": dict},
        503: {"model": dict},
    },
)
async def get_tryon_provider_credits() -> dict[str, Any]:
    """Operator-only external provider account/credit check (separated from ordinary health)."""
    settings = get_settings()
    provider_name = settings.tryon_provider

    if provider_name == "genlook":
        from app.infrastructure.external.genlook_tryon import (
            GENLOOK_DEFAULT_BASE_URL,
            GenlookTryOnConfig,
            GenlookTryOnProvider,
        )

        try:
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
            return await asyncio.to_thread(g_provider.check_health)
        except Exception as exc:
            return {
                "provider": provider_name,
                "status": "unavailable",
                "error": type(exc).__name__,
            }

    if provider_name == "commercial":
        try:
            config = tryon_app.CommercialTryOnProviderConfig(
                provider_name=settings.tryon_commercial_provider_name,
                api_key=settings.tryon_commercial_api_key or "",
                endpoint_url=settings.tryon_commercial_endpoint_url or "",
                connect_timeout_s=settings.tryon_commercial_connect_timeout_s,
                inference_timeout_s=settings.tryon_commercial_inference_timeout_s,
                max_retries=settings.tryon_commercial_max_retries,
            )
            provider = tryon_app.CommercialTryOnProvider(config)
            return await asyncio.to_thread(provider.check_health)
        except Exception as exc:
            return {
                "provider": provider_name,
                "status": "unavailable",
                "error": type(exc).__name__,
            }

    return {
        "provider": provider_name,
        "status": "not_applicable",
        "credit_balance": None,
    }


@router.post(
    "/maintenance/retention-cleanup",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_operator_auth)],
    include_in_schema=False,
    responses={
        200: {"model": dict},
        401: {"model": dict},
        403: {"model": dict},
        503: {"model": dict},
    },
)
async def run_retention_cleanup(
    job_repo: Any = Depends(get_tryon_repository),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> dict[str, Any]:
    """Execute retention policy cleanup across storage and database."""
    summary = await tryon_app.cleanup_retention_data(
        job_repo=job_repo,
        storage=storage,
    )
    return asdict(summary)
