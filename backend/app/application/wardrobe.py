"""Application use cases for the wardrobe surface (Step 4D).

Each use case is a thin orchestration unit that composes the repository ports
and raises typed `ApiError`s on failure. Business rules live here, not in the
routers (BA-7).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.api.errors import ApiError, conflict, database_failure, not_found, validation
from app.api.schemas.wardrobe import WardrobeInsight
from app.domain.ports.repositories import (
    SavedLookRepository,
    WardrobeItemRepository,
    WearEventRecord,
    WearEventRepository,
    WearGroupRecord,
    WearGroupRepository,
    WearSummary,
)


# `wardrobe_items` FK constraint name → wire field, for mapping vocabulary
# violations (PG error 23503) to the 422 contract. Unknown 23503s fall back
# to flagging every supplied vocab field (see `_vocab_validation_error`).
_VOCAB_FK_CONSTRAINT_FIELDS = {
    "wardrobe_items_category_id_fkey": "category",
    "wardrobe_items_color_id_fkey": "color",
    "wardrobe_items_material_id_fkey": "material",
}


def _vocab_validation_error(
    exc: IntegrityError, supplied: dict[str, str | None]
) -> ApiError | None:
    """Map a vocab FK violation to a 422 `ApiError`, else None.

    Only PostgreSQL foreign-key violations (23503) are mapped; every other
    database error returns None so callers re-raise it unchanged.
    """
    orig = getattr(exc, "orig", None)
    pgcode = getattr(orig, "pgcode", None)
    if pgcode is not None and pgcode != "23503":
        return None
    haystack = str(orig) if orig is not None else str(exc)
    if pgcode is None and "foreign key" not in haystack.lower():
        return None
    fields = [
        field
        for constraint, field in _VOCAB_FK_CONSTRAINT_FIELDS.items()
        if constraint in haystack
    ]
    if not fields:
        # Constraint name unrecognized — the violation must still come from
        # one of the caller-supplied vocab codes (user_id is server-set).
        fields = [field for field, value in supplied.items() if value is not None]
    if not fields:
        return None
    return validation(
        [
            {"field": field, "error": f"unknown {field} code"}
            for field in fields
        ]
    )


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
            category=category,
            color=color,
            sort=sort,
            order=order or "desc",
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

        try:
            record = self._wardrobe.create(
                user_id=user_id,
                name=name,
                category=category,
                color=color,
                material=material,
                isFavorite=isFavorite,
            )
            self._wardrobe.commit()
            return record
        except IntegrityError as exc:
            self._wardrobe.rollback()
            mapped = _vocab_validation_error(
                exc, {"category": category, "color": color, "material": material}
            )
            if mapped is None:
                raise
            raise mapped from exc


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
        material_set: bool = False,
        isFavorite: bool | None,
    ) -> WardrobeItemRecord:
        record = self._wardrobe.get_by_id(user_id=user_id, item_id=item_id)
        if record is None:
            raise not_found()

        if name is not None and (len(name) < 1 or len(name) > 100):
            raise validation(
                [{"field": "name", "error": "name must be between 1 and 100 characters"}]
            )

        try:
            updated = self._wardrobe.update(
                user_id=user_id,
                item_id=item_id,
                name=name,
                category=category,
                color=color,
                material=material,
                material_set=material_set,
                isFavorite=isFavorite,
            )
            self._wardrobe.commit()
        except IntegrityError as exc:
            self._wardrobe.rollback()
            mapped = _vocab_validation_error(
                exc, {"category": category, "color": color, "material": material}
            )
            if mapped is None:
                raise
            raise mapped from exc
        if updated is None:
            # Lost a race with a concurrent delete after the owner check.
            raise not_found()
        return updated


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
        record = self._wardrobe.get_by_id(user_id=user_id, item_id=item_id)
        if record is None:
            raise not_found()
        self._wardrobe.delete(user_id=user_id, item_id=item_id)
        self._wardrobe.commit()


class GetWardrobeInsight:
    """UC-14 — `GET /v1/wardrobe/insight` (W-7).

    Read-only derived insight. Wardrobe coverage (the owner's
    `wardrobe_items` counts) is authoritative: the title and the base
    sentence come from it exactly as before. Saved outfits
    (`saved_looks.source_context == "outfit"`, `snapshot.selectedItemIds`
    resolved against the owner's current items) add one grounded,
    deterministic follow-up when — and only when — at least one saved
    reference resolves: which covered categories are represented in saved
    looks, and which covered categories are not. A saved look means
    presence in a saved look only — never wear, need-to-buy, popularity,
    compatibility, color, season, or duplicate claims. Returns None when
    the wardrobe is empty so the router can answer 204 with no fabricated
    insight (saved looks never fabricate one either).
    """

    def __init__(
        self,
        *,
        wardrobe: WardrobeItemRepository,
        saved_looks: SavedLookRepository,
    ) -> None:
        self._wardrobe = wardrobe
        self._saved_looks = saved_looks

    def __call__(self, *, user_id: UUID) -> WardrobeInsight | None:
        summary = self._wardrobe.get_insight_summary(user_id=user_id)
        if summary.total == 0:
            return None
        counts = summary.counts_by_category
        covered = sorted(code for code, n in counts.items() if n > 0)
        missing = sorted(code for code, n in counts.items() if n == 0)
        item_word = "item" if summary.total == 1 else "items"
        fav_word = "favorite" if summary.favorite_count == 1 else "favorites"
        suffix = self._saved_look_suffix(user_id=user_id, covered=covered)
        if not missing:
            return WardrobeInsight(
                title="Wardrobe Health",
                insight=(
                    f"You have {summary.total} {item_word} covering all "
                    f"{len(counts)} wardrobe categories "
                    f"({', '.join(covered)}), with {summary.favorite_count} "
                    f"marked as {fav_word}.{suffix}"
                ),
            )
        return WardrobeInsight(
            title="Wardrobe Gaps",
            insight=(
                f"You have {summary.total} {item_word} across {len(covered)} "
                f"of {len(counts)} categories ({', '.join(covered)}), with "
                f"{summary.favorite_count} marked as {fav_word}. "
                f"Missing: {', '.join(missing)}.{suffix}"
            ),
        )

    def _saved_look_suffix(self, *, user_id: UUID, covered: list[str]) -> str:
        """Grounded saved-outfit follow-up, or "" when nothing resolves.

        Only categories that resolve to the owner's current wardrobe items
        count, intersected with the covered set so the fraction always
        refers to the same universe the base sentence reports. Empty when
        there are no outfit saves, when saves reference nothing current
        (stale/deleted IDs, item-less snapshots, hairstyle/grooming/legacy
        rows) — no claim is better than an ungrounded one.
        """
        coverage = self._saved_looks.get_outfit_coverage(user_id=user_id)
        covered_set = set(covered)
        represented = sorted(
            code
            for code in coverage.represented_categories
            if code in covered_set
        )
        if not represented:
            return ""
        suffix = (
            f" Saved looks include items from {len(represented)} of your "
            f"{len(covered)} covered categories ({', '.join(represented)})."
        )
        unrepresented = [code for code in covered if code not in set(represented)]
        if unrepresented:
            suffix += (
                f" Not represented in saved looks: "
                f"{', '.join(unrepresented)}."
            )
        return suffix


# Maximum canonical item IDs per wear-logging action (STEP 15.2: an outfit
# spans at most the 5 generator categories, plus margin; bounds mass-inserts).
_MAX_WEAR_ITEMS = 10

# Clock-skew leeway for the future-`worn_at` guard below.
_WORN_AT_FUTURE_LEEWAY = timedelta(seconds=60)


def _normalize_worn_at(worn_at: datetime | None) -> datetime:
    """Resolve the effective `worn_at`: omitted → server now; naive → UTC."""
    if worn_at is None:
        return datetime.now(timezone.utc)
    if worn_at.tzinfo is None:
        return worn_at.replace(tzinfo=timezone.utc)
    return worn_at


class LogWearEvents:
    """Log a wear event — `POST /v1/wardrobe/wears` (STEP 15.4B).

    One logging action writes ONE durable ledger row
    (`wardrobe_wear_groups`) plus one flat event row per canonical wardrobe
    item ID; all rows share the ledger row's `id` as `wear_group_id` and one
    `worn_at`, committed once. The ledger's `UNIQUE(user_id,
    idempotency_key)` is the authoritative whole-request arbiter (15.4A):
    same key + same canonical payload replays the group's rows
    (`created=False`); same key + changed payload is a 409 — and concurrent
    same-key writers serialize on the ledger index instead of fusing groups.
    The per-row UNIQUE (migration 0013) remains as defense-in-depth.
    Ownership of every item is validated owner-scoped BEFORE the ledger
    write (unknown/foreign IDs → 404, never 403); already-persisted history
    is never mutated. Append-only: no update/delete surface.
    """

    def __init__(
        self,
        *,
        wardrobe: WardrobeItemRepository,
        wears: WearEventRepository,
        groups: WearGroupRepository,
    ) -> None:
        self._wardrobe = wardrobe
        self._wears = wears
        self._groups = groups

    def __call__(
        self,
        *,
        user_id: UUID,
        item_ids: list[UUID],
        worn_at: datetime | None,
        idempotency_key: str,
    ) -> tuple[list[WearEventRecord], bool]:
        """Returns (wear records in canonical order, created)."""
        canonical_ids = sorted(set(item_ids))
        if not canonical_ids:
            raise validation(
                [{"field": "itemIds", "error": "at least one item ID is required"}]
            )
        if len(canonical_ids) > _MAX_WEAR_ITEMS:
            raise validation(
                [
                    {
                        "field": "itemIds",
                        "error": f"at most {_MAX_WEAR_ITEMS} items per wear event",
                    }
                ]
            )
        effective_worn_at = _normalize_worn_at(worn_at)
        if effective_worn_at > datetime.now(timezone.utc) + _WORN_AT_FUTURE_LEEWAY:
            raise validation(
                [{"field": "wornAt", "error": "worn time cannot be in the future"}]
            )
        for item_id in canonical_ids:
            if self._wardrobe.get_by_id(user_id=user_id, item_id=item_id) is None:
                # Owner-scoped lookup: nonexistent and foreign IDs are
                # indistinguishable by design (OW-1, 404-not-403). A deleted
                # item therefore cannot be newly logged — while rows written
                # before its deletion remain readable history.
                raise not_found()

        canonical_strs = [str(item_id) for item_id in canonical_ids]
        # Only a client-supplied instant joins the canonical payload (see
        # `_same_wear_payload`): retries that omit `wornAt` must replay.
        compare_worn_at = effective_worn_at if worn_at is not None else None
        try:
            group = self._groups.create_group(
                user_id=user_id,
                idempotency_key=idempotency_key,
                item_ids=canonical_strs,
                worn_at=effective_worn_at,
            )
        except IntegrityError:
            # Another action owns this key: either a committed group (plain
            # replay/409) or a concurrent writer whose transaction PostgreSQL
            # held ours behind — by the time we observe the violation their
            # outcome is durable, so the re-read below always decides on
            # committed state. Roll back first: the session is unusable
            # until the failed transaction is cleared.
            self._groups.rollback()
            group = self._groups.get_by_idempotency(
                user_id=user_id, idempotency_key=idempotency_key
            )
            if group is None:
                raise database_failure()
            return self._replay_or_conflict(
                group,
                canonical_ids=canonical_ids,
                compare_worn_at=compare_worn_at,
            )

        try:
            records = [
                self._wears.log(
                    user_id=user_id,
                    wardrobe_item_id=item_id,
                    worn_at=effective_worn_at,
                    wear_group_id=group.id,
                    idempotency_key=idempotency_key,
                )
                for item_id in canonical_ids
            ]
            # One commit covers the ledger row AND every event row: a
            # mid-batch failure rolls back both, never a group without rows.
            self._groups.commit()
        except Exception:
            self._groups.rollback()
            raise database_failure()
        return records, True

    def _replay_or_conflict(
        self,
        group: WearGroupRecord,
        *,
        canonical_ids: list[UUID],
        compare_worn_at: datetime | None,
    ) -> tuple[list[WearEventRecord], bool]:
        """Replay the durable group's rows, or 409 on payload mismatch."""
        if group.item_ids != [str(item_id) for item_id in canonical_ids]:
            raise conflict("duplicate")
        if compare_worn_at is not None and group.worn_at != compare_worn_at:
            raise conflict("duplicate")
        rows = self._wears.get_by_idempotency(
            user_id=group.user_id, idempotency_key=group.idempotency_key
        )
        member_rows = [row for row in rows if row.wear_group_id == group.id]
        return member_rows, False


class ListWearEvents:
    """List the owner's wear events — `GET /v1/wardrobe/wears` (STEP 15.4).

    Individual rows (never grouped objects), `worn_at` desc with `id` asc
    tiebreak, optional `item_id` filter, offset envelope. Empty history is
    an empty page — never fabricated, never 204.
    """

    def __init__(self, *, wears: WearEventRepository) -> None:
        self._wears = wears

    def __call__(
        self,
        *,
        user_id: UUID,
        item_id: UUID | None,
        page: int,
        page_size: int,
    ) -> tuple[list[WearEventRecord], int]:
        if page_size < 1 or page_size > 100:
            raise validation(
                [{"field": "page_size", "error": "page_size must be between 1 and 100"}]
            )
        return self._wears.list_for_user(
            user_id=user_id,
            page=page,
            page_size=page_size,
            item_id=item_id,
        )


class GetWearSummary:
    """Read-only wear intelligence — W-9 (`GET /v1/wardrobe/wear-summary`,
    STEP 17.3, DEC-012).

    Computes grounded wear statistics from flat `wardrobe_wear_events`
    only (see `WearSummary`): total/per-item counts, last-worn instants,
    most/least-worn groups, unworn items, recently-worn items, and
    per-category frequency. Favorites, saved looks, recommendations, and
    created/updated timestamps are NEVER read. SELECT-only: no commit,
    no rollback, no mutation.

    Definitions owned here (the repository only executes them):
    - Recent-wear window: `RECENT_WEAR_WINDOW` (30 days); an item is
      recent when its last wear is at/after `now - window` (inclusive).
    - `now` defaults to server time; naive values are read as UTC (the
      `_normalize_worn_at` convention), so tests can pin time.
    """

    RECENT_WEAR_WINDOW = timedelta(days=30)

    def __init__(self, *, wears: WearEventRepository) -> None:
        self._wears = wears

    def __call__(self, *, user_id: UUID, now: datetime | None = None) -> WearSummary:
        effective_now = _normalize_worn_at(now)
        return self._wears.get_wear_summary(
            user_id=user_id,
            recent_since=effective_now - self.RECENT_WEAR_WINDOW,
        )