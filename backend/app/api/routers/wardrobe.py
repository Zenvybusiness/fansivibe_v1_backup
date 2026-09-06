"""Wardrobe API router — endpoints W-1 (`GET /v1/wardrobe/items`) and W-3
(`POST /v1/wardrobe/items`).

Owner-scoped by authenticated user (OW-1). Follows the existing router patterns
from `users.py` and `looks.py`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.api.errors import not_found, validation
from app.api.schemas.wardrobe import (
    WardrobeItem,
    WardrobeItemCreate,
    WardrobeItemPatch,
    ListEnvelope,
)
from app.application.wardrobe import (
    ListWardrobeItems,
    AddWardrobeItem,
    GetWardrobeItem,
    UpdateWardrobeItem,
)
from app.infrastructure.db.repositories import WardrobeItemRepositorySQL
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/v1/wardrobe", tags=["wardrobe"])


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
    return ListEnvelope(items=items, page=page, page_size=page_size, total=total)


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
    return WardrobeItem(
        id=record.id,
        name=record.name,
        category=record.category,
        color=record.color,
        material=record.material,
        isFavorite=record.isFavorite,
        imageRef=record.image_ref,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


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
    return WardrobeItem(
        id=record.id,
        name=record.name,
        category=record.category,
        color=record.color,
        material=record.material,
        isFavorite=record.isFavorite,
        imageRef=record.image_ref,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


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
        isFavorite=request.isFavorite,
    )
    return WardrobeItem(
        id=record.id,
        name=record.name,
        category=record.category,
        color=record.color,
        material=record.material,
        isFavorite=record.isFavorite,
        imageRef=record.image_ref,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


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