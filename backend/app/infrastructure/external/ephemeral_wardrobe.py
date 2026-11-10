"""Ephemeral in-memory wardrobe repository adapter for guest outfit recommendations.

Preserves the canonical GenerateOutfit use case and WardrobeItemRepository
protocol for guest users without database access, without persisted identity,
and without fabricating garment attributes or user records (TRX-4, C-01, D10).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Sequence, Union
from uuid import UUID

from app.domain.ports.repositories import (
    WardrobeInsightSummary,
    WardrobeItemRecord,
    WardrobeItemRepository,
)

# Valid ensemble categories recognized by Fansivibe domain rules
_VALID_CATEGORIES = frozenset(
    {"tops", "bottoms", "outerwear", "footwear", "accessories"}
)


def _safe_float(value: Any) -> Optional[float]:
    """Parse float safely; returns None on failure or out-of-range value."""
    if value is None:
        return None
    try:
        f = float(value)
        if 0.0 <= f <= 1.0:
            return f
        return None
    except (ValueError, TypeError):
        return None


def _normalize_guest_item(
    item: Union[WardrobeItemRecord, dict[str, Any], Any],
    owner_id: Optional[UUID] = None,
) -> Optional[WardrobeItemRecord]:
    """Convert a raw guest item representation into a canonical WardrobeItemRecord.

    Preserves garment IDs verbatim where valid.
    Preserves category, color, material, fit, and fit_confidence.
    Rejects malformed or incomplete records without fabricating missing fields.
    Returns None if the record cannot be safely adapted.
    """
    if item is None:
        return None

    if isinstance(item, WardrobeItemRecord):
        # Already a domain record; verify essential fields
        if not item.id or not item.category or not item.color or not item.name:
            return None
        return item

    # Extract fields from dict or object
    if isinstance(item, dict):
        raw_id = item.get("id")
        raw_name = item.get("name")
        raw_cat = item.get("category")
        raw_col = item.get("color")
        raw_mat = item.get("material")
        raw_fav = item.get("isFavorite", item.get("is_favorite", False))
        raw_fit = item.get("fit")
        raw_conf = item.get("fit_confidence", item.get("fitConfidence"))
        raw_img = item.get("image_ref", item.get("imageRef"))
    else:
        raw_id = getattr(item, "id", None)
        raw_name = getattr(item, "name", None)
        raw_cat = getattr(item, "category", None)
        raw_col = getattr(item, "color", None)
        raw_mat = getattr(item, "material", None)
        raw_fav = getattr(item, "isFavorite", getattr(item, "is_favorite", False))
        raw_fit = getattr(item, "fit", None)
        raw_conf = getattr(
            item, "fit_confidence", getattr(item, "fitConfidence", None)
        )
        raw_img = getattr(item, "image_ref", getattr(item, "imageRef", None))

    # Essential validation: id, name, category, color must be valid non-empty values
    if raw_id is None or (isinstance(raw_id, str) and not raw_id.strip()):
        return None
    garment_id: Any = raw_id
    if isinstance(raw_id, str):
        try:
            garment_id = UUID(raw_id.strip())
        except (ValueError, AttributeError):
            garment_id = raw_id.strip()

    if not isinstance(raw_name, str) or not raw_name.strip():
        return None
    name = raw_name.strip()

    if not isinstance(raw_cat, str) or not raw_cat.strip():
        return None
    category = raw_cat.strip().lower()
    if category not in _VALID_CATEGORIES:
        return None

    if not isinstance(raw_col, str) or not raw_col.strip():
        return None
    color = raw_col.strip().lower()

    # Optional fields: safely handle malformed values without fabrication
    material: Optional[str] = None
    if isinstance(raw_mat, str) and raw_mat.strip():
        material = raw_mat.strip().lower()

    fit: Optional[str] = None
    if isinstance(raw_fit, str) and raw_fit.strip():
        fit = raw_fit.strip().lower()

    fit_confidence = _safe_float(raw_conf)
    is_favorite = bool(raw_fav)
    image_ref = dict(raw_img) if isinstance(raw_img, dict) else None
    now = datetime.now(timezone.utc)

    return WardrobeItemRecord(
        id=garment_id,
        user_id=owner_id,  # None for unauthenticated guests
        name=name,
        category=category,
        color=color,
        material=material,
        is_favorite=is_favorite,
        image_ref=image_ref,
        created_at=now,
        updated_at=now,
        fit=fit,
        fit_confidence=fit_confidence,
    )


class EphemeralWardrobeItemRepository:
    """In-memory WardrobeItemRepository adapter for guest recommendations.

    Satisfies the WardrobeItemRepository protocol for read operations
    over an in-memory guest wardrobe snapshot with zero database queries.
    """

    def __init__(
        self,
        items: Optional[Sequence[Union[WardrobeItemRecord, dict[str, Any], Any]]] = None,
        *,
        owner_id: Optional[UUID] = None,
    ) -> None:
        self._owner_id = owner_id
        self._items: list[WardrobeItemRecord] = []
        if items:
            for raw_item in items:
                adapted = _normalize_guest_item(raw_item, owner_id=owner_id)
                if adapted is not None:
                    self._items.append(adapted)

    @property
    def items(self) -> list[WardrobeItemRecord]:
        return list(self._items)

    def get_for_user(
        self,
        *,
        user_id: Optional[UUID] = None,
        page: int = 1,
        page_size: int = 100,
        category: Optional[str] = None,
        color: Optional[str] = None,
        sort: Optional[str] = None,
        order: str = "desc",
    ) -> tuple[list[WardrobeItemRecord], int]:
        """Fetch items matching optional category/color filters with pagination."""
        filtered = self._items
        if category is not None:
            norm_cat = category.strip().lower()
            filtered = [i for i in filtered if i.category == norm_cat]
        if color is not None:
            norm_col = color.strip().lower()
            filtered = [i for i in filtered if i.color == norm_col]

        reverse = order.lower() == "desc"
        if sort == "name":
            filtered = sorted(filtered, key=lambda i: i.name, reverse=reverse)
        elif sort == "created_at":
            filtered = sorted(filtered, key=lambda i: i.created_at, reverse=reverse)

        total = len(filtered)
        p = max(1, page)
        ps = max(1, page_size)
        start = (p - 1) * ps
        end = start + ps
        return filtered[start:end], total

    def get_by_id(
        self, *, user_id: Optional[UUID] = None, item_id: Union[UUID, str]
    ) -> Optional[WardrobeItemRecord]:
        target = str(item_id)
        for item in self._items:
            if item.id == item_id or str(item.id) == target:
                return item
        return None

    def get_by_ids(
        self, *, user_id: Optional[UUID] = None, item_ids: Sequence[Union[UUID, str]]
    ) -> list[WardrobeItemRecord]:
        targets = {str(iid) for iid in item_ids}
        return [item for item in self._items if str(item.id) in targets]


    def get_insight_summary(
        self, *, user_id: Optional[UUID] = None
    ) -> WardrobeInsightSummary:
        counts = {cat: 0 for cat in sorted(_VALID_CATEGORIES)}
        favorites = 0
        for item in self._items:
            counts[item.category] = counts.get(item.category, 0) + 1
            if item.is_favorite:
                favorites += 1
        return WardrobeInsightSummary(
            total=len(self._items),
            favorite_count=favorites,
            counts_by_category=counts,
        )

    def create(
        self,
        *,
        user_id: Optional[UUID] = None,
        name: str,
        category: str,
        color: str,
        material: Optional[str],
        isFavorite: bool,
        image_ref: Optional[dict[str, Any]] = None,
        fit: Optional[str] = None,
        fit_confidence: Optional[float] = None,
    ) -> WardrobeItemRecord:
        now = datetime.now(timezone.utc)
        record = WardrobeItemRecord(
            id=str(len(self._items) + 1),
            user_id=user_id or self._owner_id,
            name=name,
            category=category.strip().lower(),
            color=color.strip().lower(),
            material=material.strip().lower() if material else None,
            is_favorite=isFavorite,
            image_ref=image_ref,
            created_at=now,
            updated_at=now,
            fit=fit.strip().lower() if fit else None,
            fit_confidence=_safe_float(fit_confidence),
        )
        self._items.append(record)
        return record

    def update(
        self,
        *,
        user_id: Optional[UUID] = None,
        item_id: Union[UUID, str],
        name: Optional[str] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        material: Optional[str] = None,
        material_set: bool = False,
        isFavorite: Optional[bool] = None,
        image_ref: Optional[dict[str, Any]] = None,
        image_ref_set: bool = False,
        fit: Optional[str] = None,
        fit_set: bool = False,
        fit_confidence: Optional[float] = None,
        fit_confidence_set: bool = False,
    ) -> Optional[WardrobeItemRecord]:
        target = str(item_id)
        for idx, item in enumerate(self._items):
            if item.id == item_id or str(item.id) == target:
                now = datetime.now(timezone.utc)
                updated = WardrobeItemRecord(
                    id=item.id,
                    user_id=item.user_id,
                    name=name if name is not None else item.name,
                    category=category.strip().lower() if category is not None else item.category,
                    color=color.strip().lower() if color is not None else item.color,
                    material=material.strip().lower() if material_set and material else (None if material_set else item.material),
                    is_favorite=isFavorite if isFavorite is not None else item.is_favorite,
                    image_ref=image_ref if image_ref_set else item.image_ref,
                    created_at=item.created_at,
                    updated_at=now,
                    fit=fit.strip().lower() if fit_set and fit else (None if fit_set else item.fit),
                    fit_confidence=_safe_float(fit_confidence) if fit_confidence_set else item.fit_confidence,
                )
                self._items[idx] = updated
                return updated
        return None

    def delete(
        self, *, user_id: Optional[UUID] = None, item_id: Union[UUID, str]
    ) -> None:
        target = str(item_id)
        self._items = [i for i in self._items if i.id != item_id and str(i.id) != target]

    def commit(self) -> None:
        """In-memory no-op."""
        pass

    def rollback(self) -> None:
        """In-memory no-op."""
        pass
