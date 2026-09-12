"""Events API router — endpoints #26–29 (M8-B, UC-18/UC-19/UC-20).

`POST /v1/events` creates one owned event (201, no idempotency key —
retries append); `GET /v1/events` lists the owner's upcoming window
(`sort=event_date` only, default `from` is server-UTC today);
`PUT /v1/events/{event_id}` fully replaces one owned event;
`DELETE /v1/events/{event_id}` physically removes it (204).

Thin layer only: auth dependency → schema parsing → use case →
response mapping (BA-7). No E-3 single-GET here (deferred, additive).
"""

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.api.schemas.events import (
    EventCreate,
    EventSummary,
    EventUpdate,
    OutfitComponent,
    OutfitRecommendation,
    UserEvent,
    UserEventList,
)
from app.application.events import (
    CreateEvent,
    DeleteEvent,
    GenerateEventOutfit,
    ListEvents,
    UpdateEvent,
)
from app.domain.ports.repositories import EventOutfitRecommendation, UserEventRecord
from app.infrastructure.db.repositories import (
    EventTypeRepositorySQL,
    UserEventRepositorySQL,
    UserStateRepositorySQL,
    WardrobeItemRepositorySQL,
)
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/v1/events", tags=["events"])


def _format_time(record: UserEventRecord) -> Optional[str]:
    if record.event_time is None:
        return None
    return record.event_time.strftime("%H:%M")


def _to_user_event(record: UserEventRecord) -> UserEvent:
    return UserEvent(
        id=record.id,
        title=record.title,
        eventType=record.event_type,
        eventDate=record.event_date,
        time=_format_time(record),
        location=record.location,
        notes=record.notes,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


def _to_summary(record: UserEventRecord) -> EventSummary:
    return EventSummary(
        id=record.id,
        title=record.title,
        eventType=record.event_type,
        eventDate=record.event_date,
        time=_format_time(record),
    )


def _to_outfit_recommendation(record: EventOutfitRecommendation) -> OutfitRecommendation:
    return OutfitRecommendation(
        title=record.title,
        matchScore=record.match_score,
        components=[
            OutfitComponent(
                id=item.id,
                name=item.name,
                category=item.category,
                color=item.color,
                colorHex=None,
                material=item.material,
                reason=item.reason,
            )
            for item in record.components
        ],
        reasons=list(record.reasons),
        selectedOccasion=record.selected_occasion,
    )


@router.post(
    "",
    response_model=UserEvent,
    status_code=201,
    responses={401: {"model": dict}, 422: {"model": dict}},
)
def create_event(
    request: EventCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> UserEvent:
    """Create one owned event (TRX-7 single INSERT + sequential R36 feed)."""
    use_case = CreateEvent(
        events=UserEventRepositorySQL(db),
        event_types=EventTypeRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
    )
    record = use_case(
        user_id=user_id,
        title=request.title,
        event_type=request.eventType,
        event_date=request.eventDate,
        event_time=request.time,
        location=request.location,
        notes=request.notes,
    )
    return _to_user_event(record)


@router.get(
    "",
    response_model=UserEventList,
    responses={401: {"model": dict}, 422: {"model": dict}},
)
def list_events(
    from_date: Optional[date] = Query(default=None, alias="from"),
    sort: str = Query(default="event_date"),
    order: str = Query(default="asc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> UserEventList:
    """List the owner's events (upcoming window, soonest-first; OW-1)."""
    use_case = ListEvents(events=UserEventRepositorySQL(db))
    items, total = use_case(
        user_id=user_id,
        from_date=from_date,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    return UserEventList(
        items=[_to_summary(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.put(
    "/{event_id}",
    response_model=UserEvent,
    responses={401: {"model": dict}, 404: {"model": dict}, 422: {"model": dict}},
)
def update_event(
    request: EventUpdate,
    event_id: UUID = Path(..., description="UUID of the event to replace"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> UserEvent:
    """Fully replace one owned event (404-not-403; single UPDATE unit)."""
    use_case = UpdateEvent(
        events=UserEventRepositorySQL(db),
        event_types=EventTypeRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
    )
    record = use_case(
        user_id=user_id,
        event_id=event_id,
        title=request.title,
        event_type=request.eventType,
        event_date=request.eventDate,
        event_time=request.time,
        location=request.location,
        notes=request.notes,
    )
    return _to_user_event(record)


@router.delete(
    "/{event_id}",
    status_code=204,
    responses={401: {"model": dict}, 404: {"model": dict}, 422: {"model": dict}},
)
def delete_event(
    event_id: UUID = Path(..., description="UUID of the event to delete"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Delete one owned event (204 empty; preferences/history untouched)."""
    use_case = DeleteEvent(events=UserEventRepositorySQL(db))
    use_case(user_id=user_id, event_id=event_id)
    return None


@router.post(
    "/{event_id}/outfit",
    response_model=OutfitRecommendation,
    response_model_exclude_none=True,
    responses={
        401: {"model": dict},
        404: {"model": dict},
        422: {"model": dict},
        503: {"model": dict},
    },
)
def generate_event_outfit(
    event_id: UUID = Path(..., description="UUID of the event to style"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Derive one outfit for an owned event (read/derive only, UC-21).

    Owner-scoped event (404-not-403). No legal candidate (empty/sparse
    wardrobe) → 204 empty (sibling #41 precedent — empty derived
    results are not errors). Nothing is persisted, signaled, or worn.
    """
    use_case = GenerateEventOutfit(
        events=UserEventRepositorySQL(db),
        event_types=EventTypeRepositorySQL(db),
        wardrobe_items=WardrobeItemRepositorySQL(db),
        user_state=UserStateRepositorySQL(db),
    )
    record = use_case(user_id=user_id, event_id=event_id)
    if record is None:
        return Response(status_code=204)
    return _to_outfit_recommendation(record)
