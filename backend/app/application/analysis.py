"""Application use cases — analysis surface (UC-25/26, run reads).

Each use case is a thin orchestration unit: it composes the repositories, the
decision engine, and the knowledge source, and raises typed `ApiError`s on
failure. Business rules live here, not in the routers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import replace
from typing import Callable, Optional
from uuid import UUID

from app.api.errors import ApiError, validation, not_found
from app.application.enrichment import enrich_hairstyle_result
from app.application.media import build_media_ref, read_image_bytes
from app.ai.vision_appearance_adapter import AppearanceAnalysisError
from app.domain.ports.appearance_analysis import AppearanceAnalysisPort
from app.domain.ports.external import KnowledgeSource
from app.domain.ports.repositories import (
    AnalysisRunRepository,
    LearningSignalRepository,
    SavedLookRepository,
    UserStateRepository,
)
from app.domain.services.analysis_rules import build_context, recommend_hairstyle, knowledge_provenance
from app.domain.services.grooming_rules import recommend_grooming
from app.domain.value_objects import (
    AppearanceProfile,
    GroomingResult,
    HairstylePreferences,
    HairstyleResult,
)
from app.ai.appearance_adapter import DevelopmentAppearanceAnalysisAdapter


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

    STEP 11.2 — the owner's existing `saved_looks` rows are read (PostgreSQL
    remains the source of truth) and valid saved hairstyle look IDs are mapped
    to ``HairstylePreferences.preferredLookIds`` (soft +0.03 scoring boost via
    the existing Scoring stage). ``excludedLookIds`` is intentionally left
    empty: a save is a positive signal, and the Filtering stage treats
    exclusion as a hard drop — excluding saved looks would hide exactly what
    the user saved. When no `saved_looks` repo is wired (e.g. older callers)
    or the user has no valid saved hairstyle looks, behavior is identical to
    before (empty preferences).
    """

    def __init__(
        self,
        *,
        runs: AnalysisRunRepository,
        user_state: UserStateRepository,
        knowledge: KnowledgeSource,
        enrich: Optional[Callable[[HairstyleResult], HairstyleResult]] = None,
        saved_looks: Optional[SavedLookRepository] = None,
    ) -> None:
        self._runs = runs
        self._user_state = user_state
        self._knowledge = knowledge
        self._enrich = enrich or enrich_hairstyle_result
        self._saved_looks = saved_looks

    def _saved_hairstyle_preferences(self, *, user_id: UUID) -> HairstylePreferences:
        """Build preferences from the owner's saved hairstyle look IDs.

        Uses only the existing `SavedLookRepository.list_for_user()` (owner
        scoping enforced by the repository, OW-1). A saved row contributes
        iff its `look_id` is non-empty AND resolves in the existing hairstyle
        catalog via `lookup_hairstyle_look` — outfit saves (`look_id=None`),
        grooming IDs, unknown codes, and arbitrary titles are ignored (no
        inference from text). Failures degrade to empty preferences so the
        recommendation never breaks.
        """
        if self._saved_looks is None:
            return HairstylePreferences()
        try:
            rows, _ = self._saved_looks.list_for_user(
                user_id=user_id, page=1, page_size=100
            )
        except Exception:
            return HairstylePreferences()
        preferred: set[str] = set()
        for row in rows or []:
            look_id = row.look_id
            if not look_id:
                continue
            try:
                if self._knowledge.lookup_hairstyle_look(look_id) is None:
                    continue
            except Exception:
                continue
            preferred.add(look_id)
        return HairstylePreferences(preferredLookIds=frozenset(preferred))

    def __call__(self, *, user_id: UUID, face_profile_ref: str) -> UUID:
        profile = self._user_state.get_style_profile(user_id=user_id)
        if not profile or not profile.get("face_shape"):
            raise insufficient_user_data("face")

        run_id = self._runs.create(
            user_id=user_id,
            run_type="hairstyle",
            input_media=None,  # profile-only pass; no image (MS10.3 sealed)
            knowledge_version=knowledge_provenance(),
        )

        appearance = AppearanceProfile(
            faceShape=str(profile["face_shape"]),
            skinTone=str(profile.get("skin_tone") or ""),
            bodyType=str(profile.get("body_type") or ""),
            styleType=str(profile.get("style_type") or ""),
            sourceRunId=str(run_id),
        )

        try:
            preferences = self._saved_hairstyle_preferences(user_id=user_id)
            result = recommend_hairstyle(self._knowledge, appearance, preferences)
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

        # Size validation uses the declared size so oversized payloads are
        # rejected before their bytes are read into memory.
        size_bytes = getattr(image, "size", None)
        if size_bytes is not None and size_bytes > 20 * 1024 * 1024:
            raise validation(
                [{"field": "image", "error": f"image too large ({size_bytes} bytes), max 20 MB"}]
            )

        # Construct MediaRef from the actual received bytes (real SHA-256).
        content = read_image_bytes(image)
        media_ref = build_media_ref(
            user_id=user_id, content_type=content_type, content=content
        )

        # Step 1: Create analysis run (pending)
        run_id = self._runs.create(
            user_id=user_id,
            run_type="outfit",
            engine_version="vision-v1",
            input_media=media_ref,
            knowledge_version=knowledge_provenance(),
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

        # Step 6+7 (STEP 11.13): the run's learning signals, typed verbatim.
        # `outfit_selected` keeps its existing meaning here — completed outfit
        # generation/run lifecycle, not an explicit UI selection. Both inserts
        # are committed together below: one commit covers the run's signals
        # (never one commit per insert). TRX-6 above is untouched.
        if self._learning_signal is not None:
            self._learning_signal.insert_look_saved(
                user_id=user_id,
                signal_type="analysis_updated",
                label="analysis_updated",
                context={"run_id": str(run_id), "run_type": "outfit"},
            )
            self._learning_signal.insert_look_saved(
                user_id=user_id,
                signal_type="outfit_selected",
                label="outfit_selected",
                context={"source_context": "outfit", "run_id": str(run_id), "run_type": "outfit"},
            )
            self._learning_signal.commit()

        return run_id


class CreateHairstyleImageRun:
    """UC-43/S-2 — submit a hairstyle analysis (image-based pass).

    Hairstyle-typed run → AppearanceAnalysisPort → AppearanceProfile → TRX-6
    ``user_state.style_profile`` persistence → completed/failed run with a
    hairstyle recommendation snapshot.

    ``appearance_port`` is REQUIRED (no default): the development/hash adapter
    must never silently back this path. Until STEP 10.4 wires a production
    analyzer, the endpoint refuses image uploads honestly and this use case
    is exercised only by tests with an explicit stub port.
    """

    def __init__(
        self,
        *,
        runs: AnalysisRunRepository,
        knowledge: KnowledgeSource,
        appearance_port: AppearanceAnalysisPort,
        user_state: Optional[UserStateRepository] = None,
        learning_signal: Optional[LearningSignalRepository] = None,
        enrich: Optional[Callable[[HairstyleResult], HairstyleResult]] = None,
    ) -> None:
        self._runs = runs
        self._knowledge = knowledge
        self._appearance_port = appearance_port
        self._user_state = user_state
        self._learning_signal = learning_signal
        self._enrich = enrich or enrich_hairstyle_result

    def __call__(self, *, user_id: UUID, image: any) -> UUID:
        # Validate image content-type
        content_type = getattr(image, "content_type", None)
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise validation(
                [{"field": "image", "error": "unsupported media type, must be JPEG, PNG or WebP"}]
            )

        # Size validation uses the declared size so oversized payloads are
        # rejected before their bytes are read into memory.
        size_bytes = getattr(image, "size", None)
        if size_bytes is not None and size_bytes > 20 * 1024 * 1024:
            raise validation(
                [{"field": "image", "error": f"image too large ({size_bytes} bytes), max 20 MB"}]
            )

        # Construct MediaRef from the actual received bytes (real SHA-256).
        # The analyzer identity is recorded as run provenance (STEP 10.4);
        # unknown ports report "unknown" rather than a fabricated identity.
        content = read_image_bytes(image)
        media_ref = build_media_ref(
            user_id=user_id,
            content_type=content_type,
            content=content,
            analyzer=getattr(self._appearance_port, "adapter_id", "unknown"),
        )

        # Step 1: Create hairstyle-typed analysis run (pending)
        run_id = self._runs.create(
            user_id=user_id,
            run_type="hairstyle",
            engine_version="vision-v1",
            input_media=media_ref,
            knowledge_version=knowledge_provenance(),
        )

        # Step 2: Run appearance analysis through the injected port.
        # The port receives the actual image bytes (STEP 10 boundary fix);
        # typed analyzer failures carry their contract reason into the run.
        try:
            appearance_profile = self._appearance_port.analyze(
                media_ref=media_ref, user_id=user_id, image_bytes=content
            )
        except AppearanceAnalysisError as exc:
            self._runs.fail(
                run_id=run_id,
                user_id=user_id,
                error={
                    "code": "PROCESSING_FAILURE",
                    "message": "We couldn't finish this request. Please try again.",
                    "details": {"run_id": str(run_id), "reason": exc.reason},
                },
            )
            return run_id
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

        # A measured faceShape is required — never fall back to a default
        # shape, which would present fabrication as analysis.
        if not appearance_profile.faceShape:
            self._runs.fail(
                run_id=run_id,
                user_id=user_id,
                error={
                    "code": "PROCESSING_FAILURE",
                    "message": "We couldn't finish this request. Please try again.",
                    "details": {"run_id": str(run_id), "reason": "no_face_detected"},
                },
            )
            return run_id

        # Anchor provenance to the producing run, as the profile-only pass does.
        appearance_profile = replace(appearance_profile, sourceRunId=str(run_id))

        # Step 3: Feed the measured profile into the hairstyle decision engine
        try:
            result = recommend_hairstyle(self._knowledge, appearance_profile)
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

        # Step 4: Complete the run with the structured result
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

        # Step 6 (STEP 11.13): the run's learning signal, typed verbatim and
        # committed with the run (TRX-6 above is untouched).
        if self._learning_signal is not None:
            self._learning_signal.insert_look_saved(
                user_id=user_id,
                signal_type="analysis_updated",
                label="analysis_updated",
                context={"run_id": str(run_id), "run_type": "hairstyle"},
            )
            self._learning_signal.commit()

        return run_id


class CreateGroomingRun:
    """UC-?? — submit a grooming analysis (profile-only pass).

    The stored `style_profile` is the grounding input (honest: nothing is
    fabricated). Without stored face attributes we return
    ``INSUFFICIENT_USER_DATA`` rather than inventing a profile.

    STEP 11.3 — mirrors STEP 11.2 (hairstyle): the owner's existing
    `saved_looks` rows are read (PostgreSQL remains the source of truth) and
    valid saved *grooming* look IDs are mapped to
    ``HairstylePreferences.preferredLookIds`` (the existing shared preference
    type the canonical grooming engine already consumes; soft +0.03 scoring
    boost via the existing Scoring stage). ``excludedLookIds`` is
    intentionally left empty: a save is a positive signal, and the Filtering
    stage treats exclusion as a hard drop. When no `saved_looks` repo is wired
    (e.g. older callers) or the user has no valid saved grooming looks,
    behavior is identical to before (empty preferences).
    """

    def __init__(
        self,
        *,
        runs: AnalysisRunRepository,
        user_state: UserStateRepository,
        knowledge: KnowledgeSource,
        enrich: Optional[Callable[[GroomingResult], GroomingResult]] = None,
        saved_looks: Optional[SavedLookRepository] = None,
    ) -> None:
        self._runs = runs
        self._user_state = user_state
        self._knowledge = knowledge
        self._enrich = enrich
        self._saved_looks = saved_looks

    def _saved_grooming_preferences(self, *, user_id: UUID) -> HairstylePreferences:
        """Build preferences from the owner's saved grooming look IDs.

        Uses only the existing `SavedLookRepository.list_for_user()` (owner
        scoping enforced by the repository, OW-1). A saved row contributes
        iff its `look_id` is non-empty AND resolves in the existing grooming
        catalog via `lookup_grooming_look` — outfit saves (`look_id=None`),
        hairstyle IDs, unknown codes, and arbitrary titles are ignored (no
        inference from text). Failures degrade to empty preferences so the
        recommendation never breaks.
        """
        if self._saved_looks is None:
            return HairstylePreferences()
        try:
            rows, _ = self._saved_looks.list_for_user(
                user_id=user_id, page=1, page_size=100
            )
        except Exception:
            return HairstylePreferences()
        preferred: set[str] = set()
        for row in rows or []:
            look_id = row.look_id
            if not look_id:
                continue
            try:
                if self._knowledge.lookup_grooming_look(look_id) is None:
                    continue
            except Exception:
                continue
            preferred.add(look_id)
        return HairstylePreferences(preferredLookIds=frozenset(preferred))

    def __call__(self, *, user_id: UUID, face_profile_ref: str) -> UUID:
        profile = self._user_state.get_style_profile(user_id=user_id)
        if not profile or not profile.get("face_shape"):
            raise insufficient_user_data("face")

        run_id = self._runs.create(
            user_id=user_id,
            run_type="grooming",
            engine_version="rules-v1",
            input_media=None,  # profile-only pass; no image (MS10.3 sealed)
            knowledge_version=knowledge_provenance(),
        )

        appearance = AppearanceProfile(
            faceShape=str(profile["face_shape"]),
            skinTone=str(profile.get("skin_tone") or ""),
            bodyType=str(profile.get("body_type") or ""),
            styleType=str(profile.get("style_type") or ""),
            sourceRunId=str(run_id),
        )

        try:
            preferences = self._saved_grooming_preferences(user_id=user_id)
            result = recommend_grooming(self._knowledge, appearance, preferences)
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
