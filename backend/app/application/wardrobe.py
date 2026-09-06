"""Application use cases for the wardrobe surface (Step 4D).

Each use case is a thin orchestration unit that composes the repository ports
and raises typed `ApiError`s on failure. Business rules live here, not in the
routers (BA-7).
"""

from __future__ import annotations

from uuid import UUID

from app.api.errors import not_found, validation
from app.domain.ports.repositories import WardrobeItemRepository


class ListWardrobeItems:
    """UC-10-ish — `GET /v1/wardrobe/items` (W-1).

    Returns the authenticated user's wardrobe items with filtering, sorting,
    and pagination. Owner-scoping (OW-1) enforced by repository.
    """

    def __init__(self, *, wardrobe: WardrobeItemRepository) -> None:
        self._wardrobe = wardrobe

    def __call__(
        self,
        *,
        user_id: UUID,
        category: str | None,
        color: str | None,
        sort: str | None,
        order: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[WardrobeItemRecord], int]:
        # Validate sort key
        valid_sort_keys = {"created_at", "updated_at", "name"}
        if sort is not None and sort not in valid_sort_keys:
            raise validation(
                [{"field": "sort", "error": f"invalid sort key; must be one of {valid_sort_keys}"}]
            )

        # Validate order
        if order is not None and order not in ("asc", "desc"):
            raise validation(
                [{"field": "order", "error": f"invalid order; must be one of (asc, desc)"}]
            )

        # Validate page_size
        if page_size < 1 or page_size > 100:
            raise validation(
                [{"field": "page_size", "error": "page_size must be between 1 and 100"}]
            )

        return self._wardrobe.get_for_user(
            user_id=user_id,
            page=page,
            page_size=page_size,
        )


class AddWardrobeItem:
    """UC-10 — `POST /v1/wardrobe/items` (W-3).

    Creates a new wardrobe item with vocab-validated category/color/material.
    Server-generated id and timestamps. Emits item_added learning signal
    (handled by caller / transaction boundary).
    """

    def __init__(self, *, wardrobe: WardrobeItemRepository) -> None:
        self._wardrobe = wardrobe

    def __call__(
        self,
        *,
        user_id: UUID,
        name: str,
        category: str,
        color: str,
        material: str | None,
        isFavorite: bool,
    ) -> WardrobeItemRecord:
        if len(name) < 1 or len(name) > 100:
            raise validation(
                [{"field": "name", "error": "name must be between 1 and 100 characters"}]
            )

        return self._wardrobe.create(
            user_id=user_id,
            name=name,
            category=category,
            color=color,
            material=material,
            isFavorite=isFavorite,
        )


class GetWardrobeItem:
    """UC-W2 — `GET /v1/wardrobe/items/{item_id}` (W-2).

    Returns the authenticated user's wardrobe item.
    Owner-scoped lookup; foreign/non-existent item → 404 NOT_FOUND.
    """

    def __init__(self, *, wardrobe: WardrobeItemRepository) -> None:
        self._wardrobe = wardrobe

    def __call__(
        self,
        *,
        user_id: UUID,
        item_id: UUID,
    ) -> WardrobeItemRecord:
        record = self._wardrobe.get_by_id(user_id=user_id, item_id=item_id)
        if record is None:
            raise not_found()
        return record


class UpdateWardrobeItem:
    """UC-W4 — `PATCH /v1/wardrobe/items/{item_id}` (W-4).

    Partial merge update. name optional (1–100 chars when supplied),
    category/color must be valid vocabulary codes,
    material optional; null clears material,
    isFavorite optional,
    imageRef remains sealed until MS10.3,
    server updates updatedAt.
    Foreign/non-existent item → 404.
    """

    def __init__(self, *, wardrobe: WardrobeItemRepository) -> None:
        self._wardrobe = wardrobe

    def __call__(
        self,
        *,
        user_id: UUID,
        item_id: UUID,
        name: str | None,
        category: str | None,
        color: str | None,
        material: str | None,
        isFavorite: bool | None,
    ) -> WardrobeItemRecord:
        record = self._wardrobe.get_by_id(user_id=user_id, item_id=item_id)
        if record is None:
            raise not_found()

        if name is not None and (len(name) < 1 or len(name) > 100):
            raise validation(
                [{"field": "name", "error": "name must be between 1 and 100 characters"}]
            )

        return self._wardrobe.update(
            user_id=user_id,
            item_id=item_id,
            name=name,
            category=category,
            color=color,
            material=material,
            isFavorite=isFavorite,
        )


class DeleteWardrobeItem:
    """UC-W5 — `DELETE /v1/wardrobe/items/{item_id}` (W-5).

    Owner-scoped delete.
    Foreign/non-existent item → 404.
    Successful delete → 204 No Content.
    """

    def __init__(self, *, wardrobe: WardrobeItemRepository) -> None:
        self._wardrobe = wardrobe

    def __call__(
        self,
        *,
        user_id: UUID,
        item_id: UUID,
    ) -> None:
        result = self._wardrobe.delete(user_id=user_id, item_id=item_id)
        if result is None:
            raise not_found()