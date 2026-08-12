"""Application use cases — analysis surface (UC-25/26, run reads).

Each use case is a thin orchestration unit: it composes the repositories, the
decision engine, and the knowledge source, and raises typed `ApiError`s on
failure. Business rules live here, not in the routers.
"""

from __future__ import annotations

from typing import Callable, Optional
from uuid import UUID

from app.api.errors import ApiError, not_found
from app.application.enrichment import enrich_hairstyle_result
from app.domain.ports.external import KnowledgeSource
from app.domain.ports.repositories import (
    AnalysisRunRecord,
    AnalysisRunRepository,
    UserStateRepository,
)
from app.domain.services.analysis_rules import recommend_hairstyle
from app.domain.value_objects import AppearanceProfile, HairstyleResult


def insufficient_user_data(missing: str) -> ApiError:
    return ApiError(
        status_code=422,
        code="INSUFFICIENT_USER_DATA",
        message="We need a bit more from your profile to do this. Add a few items and try again.",
        details={"missing": missing},
    )


class CreateHairstyleRun:
    """UC-25/26 — submit a hairstyle analysis (profile-only pass, D2).

    The stored `style_profile` is the grounding input (honest: nothing is
    fabricated). Without stored face attributes we return
    ``INSUFFICIENT_USER_DATA`` rather than inventing a profile.
    """

    def __init__(
        self,
        *,
        runs: AnalysisRunRepository,
        user_state: UserStateRepository,
        knowledge: KnowledgeSource,
        enrich: Optional[Callable[[HairstyleResult], HairstyleResult]] = None,
    ) -> None:
        self._runs = runs
        self._user_state = user_state
        self._knowledge = knowledge
        self._enrich = enrich or enrich_hairstyle_result

    def __call__(self, *, user_id: UUID, face_profile_ref: str) -> UUID:
        profile = self._user_state.get_style_profile(user_id=user_id)
        if not profile or not profile.get("face_shape"):
            raise insufficient_user_data("face")

        run_id = self._runs.create(
            user_id=user_id,
            run_type="hairstyle",
            input_media=None,  # profile-only pass; no image (MS10.3 sealed)
        )

        appearance = AppearanceProfile(
            faceShape=str(profile["face_shape"]),
            skinTone=str(profile.get("skin_tone") or ""),
            bodyType=str(profile.get("body_type") or ""),
            styleType=str(profile.get("style_type") or ""),
            sourceRunId=str(run_id),
        )

        try:
            result = recommend_hairstyle(self._knowledge, appearance)
            result = self._enrich(result)
        except Exception:
            # Pipeline failure → honest `failed` run (PROCESSING_FAILURE,
            # details.run_id) per §5.1/§7 — never a stuck pending run.
            self._runs.fail(
                run_id=run_id,
                user_id=user_id,
                error={
                    "code": "PROCESSING_FAILURE",
                    "message": "We couldn't finish this request. Please try again.",
                    "details": {"run_id": str(run_id)},
                },
            )
            return run_id

        completed = self._runs.complete(
            run_id=run_id,
            user_id=user_id,
            status="completed",
            result=result.to_snapshot(),
        )
        if not completed:
            raise ApiError(
                status_code=500,
                code="DATABASE_FAILURE",
                message="Something went wrong while saving your data. Please try again.",
            )
        return run_id


class GetAnalysisRun:
    """Read one run (owner-only; foreign/missing → 404, OW-1)."""

    def __init__(self, *, runs: AnalysisRunRepository) -> None:
        self._runs = runs

    def __call__(self, *, user_id: UUID, run_id: UUID) -> AnalysisRunRecord:
        record = self._runs.get_for_user(user_id=user_id, run_id=run_id)
        if record is None:
            raise not_found()
        return record


class ListAnalysisRuns:
    """Paged run-history summaries (no `result`/`error`)."""

    def __init__(self, *, runs: AnalysisRunRepository) -> None:
        self._runs = runs

    def __call__(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[object], int]:
        return self._runs.list_for_user(user_id=user_id, page=page, page_size=page_size)
