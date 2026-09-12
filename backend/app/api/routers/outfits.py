"""Outfits API router — M13 outfit builder (#41 `POST /v1/outfits/generate`,
#42 `POST /v1/outfits/saved`, UC-28/29/30).

Generation (#41) derives one ensemble `OutfitRecommendation` per request
(TRX-2, never persisted); no legal candidate → 204 honest empty.
Saving (#42) freezes one derived outfit via M7 `SaveRecommendation`
(TRX-3) under `sourceContext == "outfit"`, with the contract's
`Idempotency-Key` header (C-12/API-33). On replay returns the original
save; on a conflicting replay returns 409.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.deps import get_current_user_id
from app.api.errors import validation
from app.api.schemas.outfits import (
    OutfitGenerateRequest,
    OutfitRecommendation,
    OutfitComponent,
)
from app.api.schemas.saved_looks import SaveLookRequest, SavedLook
from app.application.outfits import GenerateOutfit, SaveOutfit
from app.domain.ports.repositories import OutfitRecommendation as OutfitRecord
from app.infrastructure.db.repositories import (
    ActivityDayRepositorySQL,
    LearningSignalRepositorySQL,
    SavedLookRepositorySQL,
    UserStateRepositorySQL,
    WardrobeItemRepositorySQL,
)
from app.infrastructure.db.session import get_db
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

router = APIRouter(prefix="/v1/outfits", tags=["outfits"])


def _record_to_outfit_schema(record: OutfitRecord) -> OutfitRecommendation:
    return OutfitRecommendation(
        title=record.title,
        matchScore=record.match_score,
        components=[
            OutfitComponent(
                id=item.id,
                name=item.name,
                category=item.category,
                color=item.color,
                material=item.material,
                reason=item.reason,
            )
            for item in record.components
        ],
        reasons=list(record.reasons),
        colorHarmony=record.color_harmony,
        bodyFit=record.body_fit,
        occasionMatch=record.occasion_match,
        styleScoreImpact=record.style_score_impact,
        improvementSuggestion=record.improvement_suggestion,
        selectedOccasion=record.selected_occasion,
        selectedMood=record.selected_mood,
        selectedColorPalette=record.selected_color_palette,
    )


def _record_to_saved_schema(record) -> SavedLook:
    return SavedLook(
        id=record.id,
        lookId=record.look_id,
        title=record.title,
        sourceContext=record.source_context,
        snapshot=record.snapshot,
        sourceRunId=record.source_run_id,
        createdAt=record.created_at,
    )


@router.post(
    "/generate",
    response_model=OutfitRecommendation,
    response_model_exclude_none=True,
    responses={
        401: {"model": dict},
        422: {"model": dict},
        429: {"model": dict},
        503: {"model": dict},
    },
)
def generate_outfit(
    request: OutfitGenerateRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Derive one outfit (TRX-2 read/derive only, UC-28/UC-29).

    `seed` selects the ranked derivation variant (absent → the winner;
    same seed repeats the backend result). Persists nothing, never
    keyed. No legal candidate → 204 ("no matching wardrobe").
    """
    use_case = GenerateOutfit(
        wardrobe_items=WardrobeItemRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
    )
    record = use_case(
        user_id=user_id,
        occasion=request.occasion,
        mood=request.mood,
        fit=request.fit,
        color_palette=request.colorPalette,
        seed=request.seed,
    )
    if record is None:
        return Response(status_code=204)
    return _record_to_outfit_schema(record)


@router.post(
    "/saved",
    response_model=SavedLook,
    status_code=201,
    responses={
        401: {"model": dict},
        404: {"model": dict},
        409: {"model": dict},
        422: {"model": dict},
        429: {"model": dict},
    },
)
def save_outfit(
    request: SaveLookRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SavedLook:
    """Freeze one derived outfit via M7 (endpoint #42, UC-30, DEC-010).

    Delegates verbatim to `SaveRecommendation` under
    `sourceContext == "outfit"` (TRX-3: one `saved_looks` row + one
    `look_saved` signal): the snapshot's component IDs fail closed
    first (malformed → 422, unknown/foreign → 404, nothing stored).
    `Idempotency-Key` is required. No wear logging.
    """
    if not idempotency_key:
        raise validation(
            [{"field": "Idempotency-Key", "error": "required header"}]
        )
    if request.sourceContext != "outfit":
        raise validation(
            [
                {
                    "field": "sourceContext",
                    "error": "must be outfit for outfit saves",
                    "allowed": ["outfit"],
                }
            ]
        )

    use_case = SaveOutfit(
        saved_looks=SavedLookRepositorySQL(db),
        signals=LearningSignalRepositorySQL(db),
        knowledge=CatalogKnowledgeSource(),
        wardrobe_items=WardrobeItemRepositorySQL(db),
        activity_days=ActivityDayRepositorySQL(db),
    )
    record, created = use_case(
        user_id=user_id,
        look_id=request.lookId,
        title=request.title,
        snapshot=request.snapshot,
        idempotency_key=idempotency_key,
    )
    return _record_to_saved_schema(record)
