"""Analysis API router — endpoints #37/#39/#40.

Mounts the hairstyle analysis surface per `HAIRSTYLE_RECOMMENDATION_API.md`:
- `POST /v1/analysis/hairstyle` (async, profile-only pass, D2) → 202 {run_id}
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
)
from app.application.analysis import (
    CreateHairstyleRun,
    GetAnalysisRun,
    ListAnalysisRuns,
)
from app.domain.ports.repositories import AnalysisRunRecord
from app.infrastructure.db.repositories import (
    AnalysisRunRepositorySQL,
    UserStateRepositorySQL,
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
    """Submit a hairstyle analysis (profile-only pass). Returns `run_id`."""
    if image is not None:
        # Media pipeline is sealed (MS10.3) — refuse honestly, never fake a scan.
        raise validation(
            [{"field": "image", "error": "image upload is not available in this version"}]
        )
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
