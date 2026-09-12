"""Looks API router — M9 Today's Look (#31 `GET /v1/looks/today`, #32
`POST /v1/looks/today`, #33 `POST /v1/looks/today/save`) plus endpoints
#23 (`POST /v1/looks/saved`), #24 (`GET /v1/looks/saved`), and #25
(`DELETE /v1/looks/saved/{saved_look_id}`, DEC-013).

The `/today` routes are registered BEFORE `/saved*` (DEC-017 §7 guard —
no generic route may shadow them; no `/{look_id}` route exists today).

Requires the contract's `Idempotency-Key` header (C-12/API-33). On replay
returns the original save; on a conflicting replay returns 409.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Path, Query
from sqlalchemy.orm import Session
from uuid import UUID

from app.api.deps import get_current_user_id
from app.api.errors import not_found, validation
from app.api.schemas.saved_looks import SaveLookRequest, SavedLook, SavedLookList
from app.api.schemas.today import (
    TodayLook,
    TodayLookAlternative,
    TodayLookComponent,
    TodayLookStyleDna,
    TodayLookWardrobeContext,
)
from app.application.saved_looks import (
    DeleteSavedLook,
    ListSavedLooks,
    SaveRecommendation,
)
from app.application.today import GetTodayLook, RegenerateTodayLook
from app.domain.ports.repositories import TodayLookRecommendation
from app.infrastructure.db.repositories import (
    ActivityDayRepositorySQL,
    EventTypeRepositorySQL,
    LearningSignalRepositorySQL,
    SavedLookRepositorySQL,
    UserEventRepositorySQL,
    UserStateRepositorySQL,
    WardrobeItemRepositorySQL,
)
from app.infrastructure.db.session import get_db
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

router = APIRouter(prefix="/v1/looks", tags=["looks"])


def _record_to_schema(record) -> SavedLook:
    return SavedLook(
        id=record.id,
        lookId=record.look_id,
        title=record.title,
        sourceContext=record.source_context,
        snapshot=record.snapshot,
        sourceRunId=record.source_run_id,
        createdAt=record.created_at,
    )


def _today_to_schema(record: TodayLookRecommendation) -> TodayLook:
    style_dna = None
    if record.style_dna:
        style_dna = TodayLookStyleDna(
            styleType=record.style_dna.get("styleType"),
            bodyType=record.style_dna.get("bodyType"),
            skinTone=record.style_dna.get("skinTone"),
            faceShape=record.style_dna.get("faceShape"),
        )
    return TodayLook(
        title=record.title,
        occasion=record.occasion,
        description=record.description,
        matchScore=record.match_score,
        styleScore=record.style_score,
        components=[
            TodayLookComponent(
                id=item.id,
                name=item.name,
                category=item.category,
                color=item.color,
                material=item.material,
            )
            for item in record.components
        ],
        reasons=list(record.reasons),
        styleDna=style_dna,
        wardrobeContext=TodayLookWardrobeContext(
            totalItems=record.total_items,
            matchingItems=record.matching_items,
        ),
        alternatives=[
            TodayLookAlternative(id=alt.id, matchScore=alt.match_score)
            for alt in record.alternatives
        ],
        selectedItemIds=list(record.selected_item_ids),
    )


@router.get(
    "/today",
    response_model=TodayLook,
    response_model_exclude_none=True,
    responses={401: {"model": dict}, 404: {"model": dict}, 422: {"model": dict}},
)
def get_today_look(
    variant: str | None = Query(default=None, min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> TodayLook:
    """Derive today's look (TRX-2 read/derive only, UC-17).

    Empty wardrobe or no legal candidate → 404 ("none found"). No side
    effects; repeated calls over unchanged inputs are deterministic.
    """
    use_case = GetTodayLook(
        events=UserEventRepositorySQL(db),
        event_types=EventTypeRepositorySQL(db),
        wardrobe_items=WardrobeItemRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
    )
    record = use_case(user_id=user_id, variant=variant)
    if record is None:
        raise not_found()
    return _today_to_schema(record)


@router.post(
    "/today",
    response_model=TodayLook,
    response_model_exclude_none=True,
    responses={
        401: {"model": dict},
        404: {"model": dict},
        422: {"model": dict},
        503: {"model": dict},
    },
)
def regenerate_today_look(
    seed: str | None = Query(default=None, min_length=1, max_length=200),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> TodayLook:
    """Derive a fresh today's look (UC-16).

    `seed` selects the ranked derivation variant (absent → the winner).
    Persists nothing, never keyed. No legal candidate → 404.
    """
    use_case = RegenerateTodayLook(
        events=UserEventRepositorySQL(db),
        event_types=EventTypeRepositorySQL(db),
        wardrobe_items=WardrobeItemRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
    )
    record = use_case(user_id=user_id, seed=seed)
    if record is None:
        raise not_found()
    return _today_to_schema(record)


@router.post(
    "/today/save",
    response_model=SavedLook,
    status_code=201,
    responses={404: {"model": dict}, 409: {"model": dict}, 422: {"model": dict}, 401: {"model": dict}},
)
def save_today_look(
    request: SaveLookRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SavedLook:
    """Save a derived TodayLook via M7 (endpoint #33, DEC-018 §8).

    Delegates verbatim to `SaveRecommendation`: one `saved_looks` row +
    one `look_saved` signal (TRX-3). `sourceContext` must be `"daily"`;
    `snapshot` is the TodayLook verbatim (incl. `selectedItemIds`, which
    M7 validates for outfit-family saves). No wear logging.
    """
    if not idempotency_key:
        raise validation(
            [{"field": "Idempotency-Key", "error": "required header"}]
        )
    if request.sourceContext != "daily":
        raise validation(
            [
                {
                    "field": "sourceContext",
                    "error": "must be daily for today's look saves",
                    "allowed": ["daily"],
                }
            ]
        )

    use_case = SaveRecommendation(
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
        source_context=request.sourceContext,
        idempotency_key=idempotency_key,
    )
    return _record_to_schema(record)


@router.post(
    "/saved",
    response_model=SavedLook,
    status_code=201,
    responses={404: {"model": dict}, 409: {"model": dict}, 422: {"model": dict}, 401: {"model": dict}},
)
def save_look(
    request: SaveLookRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SavedLook:
    """Save a recommendation (TRX-3: saved look + `look_saved` signal)."""
    if not idempotency_key:
        raise validation(
            [{"field": "Idempotency-Key", "error": "required header"}]
        )

    use_case = SaveRecommendation(
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
        source_context=request.sourceContext,
        idempotency_key=idempotency_key,
    )
    return _record_to_schema(record)


@router.get(
    "/saved",
    response_model=SavedLookList,
    responses={422: {"model": dict}, 401: {"model": dict}},
)
def list_saved_looks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SavedLookList:
    """Paged saved-look list for the owner (createdAt desc; OW-1)."""
    use_case = ListSavedLooks(saved_looks=SavedLookRepositorySQL(db))
    items, total = use_case(user_id=user_id, page=page, page_size=page_size)
    return SavedLookList(
        items=[_record_to_schema(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.delete(
    "/saved/{saved_look_id}",
    status_code=204,
    responses={401: {"model": dict}, 404: {"model": dict}, 422: {"model": dict}},
)
def delete_saved_look(
    saved_look_id: UUID = Path(..., description="UUID of the saved look to delete"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Delete one owned saved look (DEC-013).

    Owner-scoped delete. Foreign/non-existent id → 404 (OW-1, 404-not-403).
    Successful delete → 204 No Content. The row (snapshot included) is
    physically removed; learning signals are preserved.
    """
    use_case = DeleteSavedLook(saved_looks=SavedLookRepositorySQL(db))
    use_case(user_id=user_id, saved_look_id=saved_look_id)
    return None
