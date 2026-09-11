"""Wardrobe API router — endpoints W-1 (`GET /v1/wardrobe/items`), W-3
(`POST /v1/wardrobe/items`), the wear-event surface
(`POST`/`GET /v1/wardrobe/wears`, STEP 15.4), and the read-only wear
summary (`GET /v1/wardrobe/wear-summary`, W-9, STEP 17.3).

Owner-scoped by authenticated user (OW-1). Follows the existing router patterns
from `users.py` and `looks.py`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.api.errors import validation
from app.api.schemas.wardrobe import (
    WardrobeItem,
    WardrobeInsight,
    WardrobeItemCreate,
    WardrobeItemPatch,
    WearEvent,
    WearEventList,
    WearEventLogRequest,
    WearEventLogResponse,
    WearSummary,
    ListEnvelope,
)
from app.application.wardrobe import (
    ListWardrobeItems,
    AddWardrobeItem,
    GetWardrobeItem,
    GetWardrobeInsight,
    GetWearSummary,
    ListWearEvents,
    LogWearEvents,
    UpdateWardrobeItem,
    DeleteWardrobeItem,
)
from app.infrastructure.db.repositories import (
    SavedLookRepositorySQL,
    WardrobeItemRepositorySQL,
    WearEventRepositorySQL,
    WearGroupRepositorySQL,
)
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/v1/wardrobe", tags=["wardrobe"])


def _to_wire(record) -> WardrobeItem:
    """Map a `WardrobeItemRecord` (domain `snake_case`) to the wire schema."""
    return WardrobeItem(
        id=record.id,
        name=record.name,
        category=record.category,
        color=record.color,
        material=record.material,
        isFavorite=record.is_favorite,
        imageRef=record.image_ref,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


def _wear_to_wire(record) -> WearEvent:
    """Map a `WearEventRecord` (domain `snake_case`) to the wire schema."""
    return WearEvent(
        id=record.id,
        wardrobeItemId=record.wardrobe_item_id,
        wornAt=record.worn_at,
        wearGroupId=record.wear_group_id,
        createdAt=record.created_at,
    )


def _wear_summary_to_wire(summary) -> WearSummary:
    """Map a domain `WearSummary` to the wire schema (W-9, STEP 17.3).

    Pure field rename at the API boundary — no recomputation, no
    filtering, no judgment. Domain keys are already canonical backend
    UUID strings; category keys are already canonical vocab codes.
    """
    return WearSummary(
        totalWears=summary.total_wears,
        wearCounts=dict(summary.wear_counts),
        lastWorn=dict(summary.last_worn),
        mostWornItemIds=list(summary.most_worn_item_ids),
        leastWornItemIds=list(summary.least_worn_item_ids),
        unwornItemIds=list(summary.unworn_item_ids),
        recentlyWornItemIds=list(summary.recently_worn_item_ids),
        wearsByCategory=dict(summary.wears_by_category),
    )


@router.get(
    "/items",
    response_model=ListEnvelope,
    responses={
        401: {"model": dict},
        422: {"model": dict},
        429: {"model": dict},
    },
)
def list_wardrobe_items(
    category: str | None = Query(
        default=None,
        description="Vocab code filter (wardrobe_categories.code). Validated server-side.",
    ),
    color: str | None = Query(
        default=None,
        description="Vocab code filter (colors.code). Validated server-side.",
    ),
    sort: str | None = Query(
        default=None,
        description="Sort key: created_at | updated_at | name",
    ),
    order: str | None = Query(
        default="desc",
        description="Sort order: asc | desc (default desc for time keys, asc for name)",
    ),
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page, max 100"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ListEnvelope:
    """List the authenticated user's wardrobe items with filtering, sorting, and pagination."""
    use_case = ListWardrobeItems(wardrobe=WardrobeItemRepositorySQL(db))
    items, total = use_case(
        user_id=user_id,
        category=category,
        color=color,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    return ListEnvelope(
        items=[_to_wire(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/items",
    response_model=WardrobeItem,
    status_code=201,
    responses={
        401: {"model": dict},
        409: {"model": dict},
        422: {"model": dict},
        413: {"model": dict},
        429: {"model": dict},
    },
)
def add_wardrobe_item(
    request: WardrobeItemCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WardrobeItem:
    """Create a new wardrobe item.

    Category and color are validated against the controlled vocabulary server-side.
    Material is optional and validated if provided. Image handling is sealed until
    MS10.3 — imageRef is accepted but media flow is not mounted.
    """
    use_case = AddWardrobeItem(wardrobe=WardrobeItemRepositorySQL(db))
    record = use_case(
        user_id=user_id,
        name=request.name,
        category=request.category,
        color=request.color,
        material=request.material,
        isFavorite=request.isFavorite,
    )
    return _to_wire(record)


@router.get(
    "/items/{item_id}",
    response_model=WardrobeItem,
    responses={
        401: {"model": dict},
        404: {"model": dict},
        422: {"model": dict},
    },
)
def get_wardrobe_item(
    item_id: UUID = Path(..., description="UUID of the wardrobe item to retrieve"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WardrobeItem:
    """Retrieve a single wardrobe item.

    Owner-scoped lookup; foreign/non-existent item → 404 NOT_FOUND.
    """
    use_case = GetWardrobeItem(wardrobe=WardrobeItemRepositorySQL(db))
    record = use_case(user_id=user_id, item_id=item_id)
    return _to_wire(record)


@router.patch(
    "/items/{item_id}",
    response_model=WardrobeItem,
    responses={
        401: {"model": dict},
        404: {"model": dict},
        422: {"model": dict},
    },
)
def update_wardrobe_item(
    request: WardrobeItemPatch,
    item_id: UUID = Path(..., description="UUID of the wardrobe item to update"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WardrobeItem:
    """Update a wardrobe item (partial merge).

    name optional (1–100 chars when supplied),
    category/color must be valid vocabulary codes,
    material optional; null clears material,
    isFavorite optional,
    imageRef remains sealed until MS10.3,
    server updates updatedAt.
    Foreign/non-existent item → 404.
    """
    use_case = UpdateWardrobeItem(wardrobe=WardrobeItemRepositorySQL(db))
    record = use_case(
        user_id=user_id,
        item_id=item_id,
        name=request.name,
        category=request.category,
        color=request.color,
        material=request.material,
        material_set="material" in request.model_fields_set,
        isFavorite=request.isFavorite,
    )
    return _to_wire(record)


@router.delete(
    "/items/{item_id}",
    status_code=204,
    responses={
        401: {"model": dict},
        404: {"model": dict},
    },
)
def delete_wardrobe_item(
    item_id: UUID = Path(..., description="UUID of the wardrobe item to delete"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Delete a wardrobe item.

    Owner-scoped delete.
    Foreign/non-existent item → 404.
    Successful delete → 204 No Content.
    """
    use_case = DeleteWardrobeItem(wardrobe=WardrobeItemRepositorySQL(db))
    use_case(user_id=user_id, item_id=item_id)
    return None


@router.get(
    "/insight",
    response_model=WardrobeInsight,
    responses={
        401: {"model": dict},
        204: {"description": "Empty wardrobe — no insight fabricated"},
        429: {"model": dict},
    },
)
def get_wardrobe_insight(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WardrobeInsight | Response:
    """Derived wardrobe insight (W-7/UC-14).

    Read-only aggregate over the owner's `wardrobe_items` (counts by
    canonical category, favorites) plus saved-outfit representation
    (owner-scoped `saved_looks` with `source_context == "outfit"`,
    resolved against the owner's current items). Wardrobe coverage stays
    authoritative; saved looks only add which covered categories appear
    in saved looks. Empty wardrobe → 204, never a fabricated insight.
    No side effects.
    """
    use_case = GetWardrobeInsight(
        wardrobe=WardrobeItemRepositorySQL(db),
        saved_looks=SavedLookRepositorySQL(db),
    )
    result = use_case(user_id=user_id)
    if result is None:
        return Response(status_code=204)
    return result


@router.post(
    "/wears",
    response_model=WearEventLogResponse,
    status_code=201,
    responses={
        401: {"model": dict},
        404: {"model": dict},
        409: {"model": dict},
        422: {"model": dict},
    },
)
def log_wear_events(
    request: WearEventLogRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WearEventLogResponse:
    """Log a wear event (STEP 15.4B: one durable group + rows per item).

    Requires the contract's `Idempotency-Key` header (C-12/API-33, save
    precedent). Same key + same canonical payload replays the original
    group (`created=false`, still 201); same key + changed payload → 409.
    Unknown/foreign item IDs → 404 (OW-1). Append-only: no update/delete.
    """
    if not idempotency_key:
        raise validation(
            [{"field": "Idempotency-Key", "error": "required header"}]
        )
    use_case = LogWearEvents(
        wardrobe=WardrobeItemRepositorySQL(db),
        wears=WearEventRepositorySQL(db),
        groups=WearGroupRepositorySQL(db),
    )
    records, created = use_case(
        user_id=user_id,
        item_ids=request.itemIds,
        worn_at=request.wornAt,
        idempotency_key=idempotency_key,
    )
    return WearEventLogResponse(
        wears=[_wear_to_wire(record) for record in records],
        wearGroupId=records[0].wear_group_id,
        wornAt=records[0].worn_at,
        created=created,
    )


@router.get(
    "/wears",
    response_model=WearEventList,
    responses={
        401: {"model": dict},
        422: {"model": dict},
    },
)
def list_wear_events(
    item_id: UUID | None = Query(
        default=None,
        description="Filter to one wardrobe item UUID.",
    ),
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page, max 100"),
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WearEventList:
    """Paged wear-event history for the owner (worn_at desc, id asc).

    Individual rows, never grouped objects. Empty history is an empty
    envelope — never 204, never fabricated.
    """
    use_case = ListWearEvents(wears=WearEventRepositorySQL(db))
    items, total = use_case(
        user_id=user_id,
        item_id=item_id,
        page=page,
        page_size=page_size,
    )
    return WearEventList(
        items=[_wear_to_wire(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get(
    "/wear-summary",
    response_model=WearSummary,
    responses={
        401: {"model": dict},
        429: {"model": dict},
    },
)
def get_wear_summary(
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WearSummary:
    """Read-only wear summary for the owner (W-9, STEP 17.3, DEC-012).

    SELECT-only aggregate over the owner's flat `wardrobe_wear_events`
    via `GetWearSummary` — total/per-item counts, last-worn instants,
    most/least-worn ties, unworn items, last-30-days recency, and
    per-category frequency. Favorites, saved looks, recommendations,
    and timestamps are never read; stale deleted-item rows are ignored.
    Empty wardrobe → 200 zero object, never 204, never 404.
    No side effects: no commit, no mutation.
    """
    use_case = GetWearSummary(wears=WearEventRepositorySQL(db))
    return _wear_summary_to_wire(use_case(user_id=user_id))