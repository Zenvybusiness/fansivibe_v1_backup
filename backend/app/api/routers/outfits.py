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

from app.api.deps import get_current_user_id, get_storage_adapter
from app.api.errors import validation
from app.api.schemas.outfits import (
    OutfitGenerateRequest,
    OutfitRecommendation,
    OutfitComponent,
    OutfitSlotSwapRequest,
    OutfitSlotSwapResponse,
    OutfitCandidatesRequest,
    OutfitCandidatesResponse,
    OutfitCandidateItem,
)
from app.api.schemas.saved_looks import SaveLookRequest, SavedLook
from app.application.outfits import (
    EMPTY_OUTFIT_REASON_HEADER,
    NO_LEGAL_CANDIDATE,
    GenerateOutfit,
    SaveOutfit,
    SwapOutfitSlot,
    GetOutfitCandidates,
)
from app.domain.ports.repositories import OutfitRecommendation as OutfitRecord
from app.domain.ports.storage import ObjectStoragePort
from app.infrastructure.db.repositories import (
    ActivityDayRepositorySQL,
    FeedbackRepositorySQL,
    LearningSignalRepositorySQL,
    SavedLookRepositorySQL,
    UserStateRepositorySQL,
    WardrobeItemRepositorySQL,
    WearEventRepositorySQL,
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
    keyed. No legal candidate → 204 ("no matching wardrobe") with an
    empty body plus the M11 P4 `X-Outfit-Empty-Reason` header carrying
    the deterministic reason (`empty_wardrobe` /
    `missing_required_category` / `no_legal_candidate`). Older clients
    ignore the header: body and status are unchanged, so the existing
    204 path stays byte-compatible.
    """
    use_case = GenerateOutfit(
        wardrobe_items=WardrobeItemRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
        feedback=FeedbackRepositorySQL(db),
        saved_looks=SavedLookRepositorySQL(db),
        wears=WearEventRepositorySQL(db),
    )
    record, empty_reason = use_case.derive_with_reason(
        user_id=user_id,
        occasion=request.occasion,
        mood=request.mood,
        fit=request.fit,
        color_palette=request.colorPalette,
        seed=request.seed,
        preferred_item_ids=request.preferredItemIds,
    )
    if record is None:
        return Response(
            status_code=204,
            headers={EMPTY_OUTFIT_REASON_HEADER: empty_reason or NO_LEGAL_CANDIDATE},
        )
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


async def _candidate_to_wire(record, storage: ObjectStoragePort | None = None) -> OutfitCandidateItem:
    """Map a `WardrobeItemRecord` to `OutfitCandidateItem` enriched with presigned GET URL."""
    image_url: str | None = None
    image_ref = record.image_ref
    if image_ref and isinstance(image_ref, dict):
        key = (
            image_ref.get("objectKey")
            or image_ref.get("object_key")
            or image_ref.get("canonical_key")
            or image_ref.get("canonicalKey")
            or image_ref.get("key")
        )
        if key and storage is not None:
            try:
                image_url = await storage.generate_presigned_get_url(key=key, expires_in_s=900)
                image_ref = {**image_ref, "downloadUrl": image_url, "url": image_url}
            except Exception:
                pass
    return OutfitCandidateItem(
        id=str(record.id),
        name=record.name,
        category=record.category,
        color=record.color,
        material=record.material,
        isFavorite=record.is_favorite,
        fit=record.fit,
        fitConfidence=record.fit_confidence,
        imageRef=image_ref,
        imageUrl=image_url,
    )


@router.post(
    "/swap-slot",
    response_model=OutfitSlotSwapResponse,
    response_model_exclude_none=True,
    responses={
        401: {"model": dict},
        404: {"model": dict},
        409: {"model": dict},
        422: {"model": dict},
        429: {"model": dict},
        503: {"model": dict},
    },
)
def swap_outfit_slot(
    request: OutfitSlotSwapRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> OutfitSlotSwapResponse:
    """Swap one outfit component slot and recalculate complete compatibility (P1-1).

    Enforces:
    - User authentication (401).
    - Ownership validation: all current garments and replacement garment must belong to user (OW-1, 404).
    - Slot category match (422).
    - No duplicate garments across slots (422).
    - Pinned slot protection: cannot replace a pinned slot (409 PINNED_SLOT_CONFLICT).
    - Preservation of all other pinned garments (409).
    - Canonical compatibility recalculation via existing decision engine.
    """
    use_case = SwapOutfitSlot(
        wardrobe_items=WardrobeItemRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
        feedback=FeedbackRepositorySQL(db),
        saved_looks=SavedLookRepositorySQL(db),
        wears=WearEventRepositorySQL(db),
    )
    rec_record, prev_id, prev_score, warnings = use_case.execute(
        user_id=user_id,
        occasion=request.occasion,
        mood=request.mood,
        fit=request.fit,
        color_palette=request.colorPalette,
        current_garment_ids=request.currentGarmentIds,
        slot=request.slot,
        replacement_garment_id=request.replacementGarmentId,
        pinned_garment_ids=request.pinnedGarmentIds,
        seed=request.seed,
    )
    outfit_schema = _record_to_outfit_schema(rec_record)
    return OutfitSlotSwapResponse(
        outfit=outfit_schema,
        replacedSlot=request.slot,
        previousGarmentId=prev_id,
        replacementGarmentId=str(request.replacementGarmentId),
        compatibilityScore=outfit_schema.matchScore,
        previousCompatibilityScore=prev_score,
        reasons=outfit_schema.reasons,
        warnings=warnings,
    )


@router.post(
    "/candidates",
    response_model=OutfitCandidatesResponse,
    response_model_exclude_none=True,
    responses={
        401: {"model": dict},
        422: {"model": dict},
        429: {"model": dict},
    },
)
async def get_outfit_candidates(
    request: OutfitCandidatesRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    storage: ObjectStoragePort = Depends(get_storage_adapter),
) -> OutfitCandidatesResponse:
    """Retrieve eligible replacement wardrobe items for a slot (P1-1).

    Filters by slot category and excludes garments currently occupying slots in the outfit.
    Enriches with presigned GET image URLs when media references exist.
    """
    use_case = GetOutfitCandidates(wardrobe_items=WardrobeItemRepositorySQL(db))
    canonical_slot, items = use_case.execute(
        user_id=user_id,
        slot=request.slot,
        current_garment_ids=request.currentGarmentIds,
        limit=request.limit,
    )
    candidates = [await _candidate_to_wire(item, storage=storage) for item in items]
    return OutfitCandidatesResponse(
        slot=canonical_slot,
        candidates=candidates,
    )
