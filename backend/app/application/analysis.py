"""Application use cases — analysis surface (UC-25/26, run reads).

Each use case is a thin orchestration unit: it composes the repositories, the
decision engine, and the knowledge source, and raises typed `ApiError`s on
failure. Business rules live here, not in the routers.
"""

from __future__ import annotations

import uuid as _uuid
import time as _time

from abc import ABC, abstractmethod
from typing import Callable, Optional
from uuid import UUID

from app.api.errors import ApiError, validation, not_found
from app.application.enrichment import enrich_hairstyle_result
from app.domain.ports.appearance_analysis import AppearanceAnalysisPort
from app.domain.ports.external import KnowledgeSource
from app.domain.ports.repositories import (
    AnalysisRunRepository,
    LearningSignalRepository,
    UserStateRepository,
)
from app.domain.services.analysis_rules import build_context, recommend_hairstyle
from app.domain.services.grooming_rules import recommend_grooming
from app.domain.value_objects import AppearanceProfile, HairstyleResult, GroomingResult


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


class CreateOutfitRun:
    """UC-44 — submit an outfit/appearance analysis (image-based pass, S-1).

    Validates the uploaded image, constructs a MediaRef, creates the analysis
    run with `status=pending`, runs the appearance analysis adapter, feeds the
    result into the decision engine, completes the run with a structured result,
    and returns the run_id.

    The adapter is injected via the constructor (defaults to
    `DevelopmentAppearanceAnalysisAdapter` for development/testing). Production
    deployment should provide a production-model adapter implementing
    `AppearanceAnalysisPort`.

    After run completion, TRX-6 updates `user_state.style_profile` with the
    image-derived appearance attributes, making the profile reusable context
    for future hairstyle/grooming runs. A learning signal `analysis_updated`
    is also emitted.
    """

    def __init__(
        self,
        *,
        runs: AnalysisRunRepository,
        knowledge: KnowledgeSource,
        appearance_port: Optional[AppearanceAnalysisPort] = None,
        user_state: Optional[UserStateRepository] = None,
        learning_signal: Optional[LearningSignalRepository] = None,
    ) -> None:
        self._runs = runs
        self._knowledge = knowledge
        self._appearance_port = appearance_port or DevelopmentAppearanceAnalysisAdapter()
        self._user_state = user_state
        self._learning_signal = learning_signal

    def __call__(self, *, user_id: UUID, image: any) -> UUID:
        # Validate image content-type
        content_type = getattr(image, "content_type", None)
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise validation(
                [{"field": "image", "error": "unsupported media type, must be JPEG, PNG or WebP"}]
            )

        # Validate image size (max 20 MB)
        size_bytes = getattr(image, "size", None)
        if size_bytes is not None and size_bytes > 20 * 1024 * 1024:
            raise validation(
                [{"field": "image", "error": f"image too large ({size_bytes} bytes), max 20 MB"}]
            )

        # Construct MediaRef
        ext = "jpg"  # default extension; Flutter may determine from content_type
        key = f"users/{user_id}/scans/{_uuid.uuid4()}/input.{ext}"
        media_ref = {
            "key": key,
            "mediaType": content_type,
            "sizeBytes": size_bytes,
            "contentHash": _uuid.uuid4().hex[:64],  # placeholder SHA-256 hash
            "isGenerated": False,
            "uploadedAt": _time.time.strftime(_time.gmtime(), "%Y-%m-%dT%H:%M:%SZ"),
        }

        # Step 1: Create analysis run (pending)
        run_id = self._runs.create(
            user_id=user_id,
            run_type="outfit",
            engine_version="vision-v1",
            input_media=media_ref,
        )

        # Step 2: Run appearance analysis adapter
        try:
            appearance_profile = self._appearance_port.analyze(
                media_ref=media_ref, user_id=user_id
            )
        except Exception:
            # Adapter failure → honest `failed` run (PROCESSING_FAILURE,
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

        # Step 3: Feed appearance profile into decision engine
        try:
            context = build_context(
                appearance=appearance_profile,
                knowledge_version=getattr(self._knowledge, "knowledge_version", ""),
            )
            hairstyle_result = recommend_hairstyle(self._knowledge, appearance_profile)
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

        # Step 4: Complete the run with the structured result
        completed = self._runs.complete(
            run_id=run_id,
            user_id=user_id,
            status="completed",
            result=hairstyle_result.to_snapshot(),
        )
        if not completed:
            raise ApiError(
                status_code=500,
                code="DATABASE_FAILURE",
                message="Something went wrong while saving your data. Please try again.",
            )

        # Step 5: TRX-6 — Update user_state.style_profile with image-derived attributes
        # This makes the appearance profile reusable context for future runs
        # (hairstyle, grooming) without needing re-capture.
        if self._user_state is not None:
            self._user_state.update_style_profile(
                user_id=user_id,
                face_shape=appearance_profile.faceShape,
                skin_tone=appearance_profile.skinTone,
                body_type=appearance_profile.bodyType,
                style_type=appearance_profile.styleType,
                source_run_id=str(run_id),
            )

        # Step 6: Emit learning signal that the profile was updated from an analysis run
        if self._learning_signal is not None:
            self._learning_signal.insert_look_saved(
                user_id=user_id,
                label="analysis_updated",
                context={"run_id": str(run_id), "run_type": "outfit"},
            )

        return run_id


class CreateGroomingRun:
    """UC-?? — submit a grooming analysis (profile-only pass).

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
        enrich: Optional[Callable[[GroomingResult], GroomingResult]] = None,
    ) -> None:
        self._runs = runs
        self._user_state = user_state
        self._knowledge = knowledge
        self._enrich = enrich

    def __call__(self, *, user_id: UUID, face_profile_ref: str) -> UUID:
        profile = self._user_state.get_style_profile(user_id=user_id)
        if not profile or not profile.get("face_shape"):
            raise insufficient_user_data("face")

        run_id = self._runs.create(
            user_id=user_id,
            run_type="grooming",
            engine_version="rules-v1",
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
            result = recommend_grooming(self._knowledge, appearance)
            enrich = self._enrich or (lambda r: r)
            result = enrich(result)
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
