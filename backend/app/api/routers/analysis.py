"""Analysis API router — endpoints #37/#39/#40/#43/#44.

Mounts the hairstyle analysis surface per `HAIRSTYLE_RECOMMENDATION_API.md`:
- `POST /v1/analysis/hairstyle` (async, accepts image or profile-only pass) → 202 {run_id}
- `POST /v1/analysis/outfit` (async, image-based pass, S-1) → 202 {run_id}
- `GET  /v1/analysis/runs/{run_id}` (owner-only, 404-not-403) → bare `AnalysisRun`
- `GET  /v1/analysis/runs` → paged summaries (no `result`)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.api.errors import validation
from app.api.schemas.analysis import (
    AnalysisRun,
    AnalysisRunList,
    AnalysisRunSummary,
    AsyncAccepted,
    CreateGroomingRunRequest,
    CreateOutfitScanRequest,
    CreateHairstyleScanRequest,
)
from app.application.analysis import (
    CreateGroomingRun,
    CreateHairstyleImageRun,
    CreateHairstyleRun,
    CreateOutfitRun,
    GetAnalysisRun,
    ListAnalysisRuns,
)
from app.ai.vision_appearance_adapter import OllamaVisionAppearanceAdapter
from app.domain.ports.appearance_analysis import AppearanceAnalysisPort
from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter
from app.domain.ports.repositories import AnalysisRunRecord, LearningSignalRepository
from app.infrastructure.db.repositories import (
    ActivityDayRepositorySQL,
    AnalysisRunRepositorySQL,
    UserStateRepositorySQL,
    SavedLookRepositorySQL,
    LearningSignalRepositorySQL,
)
from app.infrastructure.db.session import get_db
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

router = APIRouter(prefix="/v1/analysis", tags=["analysis"])


def _run_record_to_schema(record: AnalysisRunRecord) -> AnalysisRun:
    return AnalysisRun(
        run_id=record.id,
        run_type=record.run_type,
        status=record.status,
        created_at=record.created_at,
        completed_at=record.completed_at,
        engine_version=record.engine_version,
        input_media=record.input_media,
        result=record.result,
        error=record.error,
    )


def _run_summary_to_schema(record) -> AnalysisRunSummary:
    return AnalysisRunSummary(
        run_id=record.id,
        run_type=record.run_type,
        status=record.status,
        created_at=record.created_at,
        completed_at=record.completed_at,
        engine_version=record.engine_version,
        input_media=record.input_media,
    )


@router.post(
    "/hairstyle",
    response_model=AsyncAccepted,
    status_code=202,
    responses={422: {"model": dict}, 401: {"model": dict}},
)
def create_hairstyle_run(
    faceProfileRef: str | None = Form(default=None),
    image: UploadFile | None = File(default=None),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncAccepted:
    """Submit a hairstyle analysis (image-based or profile-only pass). Returns `run_id`."""
    if image is not None and faceProfileRef:
        raise validation(
            [{"field": "faceProfileRef", "error": "image and faceProfileRef are mutually exclusive"}]
        )
    if image is not None:
        if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise validation(
                [{"field": "image", "error": "unsupported media type, must be JPEG, PNG or WebP"}]
            )
        if image.size is not None and image.size > 20 * 1024 * 1024:
            raise validation(
                [{"field": "image", "error": f"image too large ({image.size} bytes), max 20 MB"}]
            )
        # STEP 10.5: production wiring. The image branch runs the
        # hairstyle-typed `CreateHairstyleImageRun` with the production
        # `OllamaVisionAppearanceAdapter` (settings-driven, never the
        # development/hash adapter). Analyzer failures surface as honest
        # terminal `failed` runs via the use case — no fallback, no
        # fabrication. Adapter construction is inline, matching the
        # established outfit-branch seam (no new DI framework).
        use_case = CreateHairstyleImageRun(
            runs=AnalysisRunRepositorySQL(db),
            knowledge=CatalogKnowledgeSource(),
            appearance_port=OllamaVisionAppearanceAdapter(),
            user_state=UserStateRepositorySQL(db),
            learning_signal=LearningSignalRepositorySQL(db),
            activity_days=ActivityDayRepositorySQL(db),
        )
        run_id = use_case(user_id=user_id, image=image)
        return AsyncAccepted(run_id=run_id)
    if not faceProfileRef:
        raise validation(
            [{"field": "faceProfileRef", "error": "required when no image is submitted"}]
        )
    try:
        UUID(faceProfileRef)
    except (ValueError, AttributeError):
        raise validation(
            [{"field": "faceProfileRef", "error": "must be a valid uuid"}]
        )

    use_case = CreateHairstyleRun(
        runs=AnalysisRunRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
        knowledge=CatalogKnowledgeSource(),
        saved_looks=SavedLookRepositorySQL(db),
    )
    run_id = use_case(user_id=user_id, face_profile_ref=faceProfileRef)
    return AsyncAccepted(run_id=run_id)


@router.get(
    "/runs/{run_id}",
    response_model=AnalysisRun,
    responses={404: {"model": dict}, 422: {"model": dict}, 401: {"model": dict}},
)
def get_analysis_run(
    run_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AnalysisRun:
    """Read one run (owner-only; foreign/missing run → 404, OW-1)."""
    use_case = GetAnalysisRun(runs=AnalysisRunRepositorySQL(db))
    record = use_case(user_id=user_id, run_id=run_id)
    return _run_record_to_schema(record)


@router.get(
    "/runs",
    response_model=AnalysisRunList,
    responses={422: {"model": dict}, 401: {"model": dict}},
)
def list_analysis_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AnalysisRunList:
    """Paged run-history summaries (no `result`, PR-5)."""
    use_case = ListAnalysisRuns(runs=AnalysisRunRepositorySQL(db))
    items, total = use_case(user_id=user_id, page=page, page_size=page_size)
    return AnalysisRunList(
        items=[_run_summary_to_schema(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/grooming",
    response_model=AsyncAccepted,
    status_code=202,
    responses={422: {"model": dict}, 401: {"model": dict}},
)
def create_grooming_run(
    request: CreateGroomingRunRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncAccepted:
    """Submit a grooming analysis (profile-only pass). Returns `run_id`."""
    face_profile_ref = request.face_profile_ref
    if not face_profile_ref:
        raise validation(
            [{"field": "face_profile_ref", "error": "required"}]
        )
    try:
        UUID(face_profile_ref)
    except (ValueError, AttributeError):
        raise validation(
            [{"field": "face_profile_ref", "error": "must be a valid uuid"}]
        )
    use_case = CreateGroomingRun(
        runs=AnalysisRunRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
        knowledge=CatalogKnowledgeSource(),
        saved_looks=SavedLookRepositorySQL(db),
    )
    run_id = use_case(user_id=user_id, face_profile_ref=face_profile_ref)
    return AsyncAccepted(run_id=run_id)


@router.post(
    "/outfit",
    response_model=AsyncAccepted,
    status_code=202,
    responses={
        401: {"model": dict},
        413: {"model": dict},
        422: {"model": dict},
        503: {"model": dict},
    },
)
def create_outfit_run(
    image: UploadFile = File(...),
    faceProfileRef: str | None = Form(default=None),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncAccepted:
    """Submit an outfit/appearance analysis (image-based pass, S-1). Returns `run_id`."""
    if faceProfileRef:
        raise validation(
            [{"field": "faceProfileRef", "error": "faceProfileRef not supported for outfit scan; use image only"}]
        )
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise validation(
            [{"field": "image", "error": "unsupported media type, must be JPEG, PNG or WebP"}]
        )
    if image.size is not None and image.size > 20 * 1024 * 1024:
        raise validation(
            [{"field": "image", "error": f"image too large ({image.size} bytes), max 20 MB"}]
        )
    use_case = CreateOutfitRun(
        runs=AnalysisRunRepositorySQL(db),
        knowledge=CatalogKnowledgeSource(),
        appearance_port=OllamaVisionAppearanceAdapter(),
        user_state=UserStateRepositorySQL(db),
        learning_signal=LearningSignalRepositorySQL(db),
        activity_days=ActivityDayRepositorySQL(db),
    )
    run_id = use_case(user_id=user_id, image=image)
    return AsyncAccepted(run_id=run_id)

