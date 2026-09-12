"""Repository ports — persistence seams the application layer depends on.

Implementations live in `app/infrastructure/db/repositories.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol
from uuid import UUID


@dataclass(frozen=True)
class AnalysisRunRecord:
    """A bare `analysis_runs` row (owner-scoped read).

    ``knowledge_version`` is the combined knowledge provenance (STEP 12.3,
    ``<catalog>+<OI>``); ``None`` marks a legacy row — unknown, never inferred.
    """

    id: UUID
    run_type: str
    status: str
    engine_version: str
    created_at: datetime
    completed_at: Optional[datetime]
    input_media: Optional[dict]
    result: Optional[dict]
    error: Optional[dict]
    knowledge_version: Optional[str] = None


@dataclass(frozen=True)
class AnalysisRunSummary:
    """A list-row summary (no `result`, no `error`)."""

    id: UUID
    run_type: str
    status: str
    engine_version: str
    created_at: datetime
    completed_at: Optional[datetime]
    input_media: Optional[dict]


@dataclass(frozen=True)
class SavedLookRecord:
    """A `saved_looks` row (owner-scoped read).

    ``source_context`` is the backend-owned domain discriminator (STEP 11.16:
    hairstyle/grooming/outfit). It defaults to ``None``, which marks a legacy
    row written before the contract — domain unknown, never inferred.
    """

    id: UUID
    look_id: Optional[str]
    title: str
    snapshot: dict
    source_run_id: Optional[UUID]
    created_at: datetime
    source_context: Optional[str] = None


@dataclass(frozen=True)
class WardrobeItemRecord:
    """A `wardrobe_items` row (owner-scoped read)."""

    id: UUID
    user_id: UUID
    name: str
    category: str
    color: str
    material: Optional[str]
    is_favorite: bool
    image_ref: Optional[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WardrobeInsightSummary:
    """Aggregate wardrobe facts for one owner (W-7/UC-14 input).

    `counts_by_category` covers every active `wardrobe_categories` code in
    code order (zero where the owner has no items); `total` and
    `favorite_count` are owner-scoped. Pure facts — prose is composed in
    the application layer.
    """

    total: int
    favorite_count: int
    counts_by_category: dict[str, int]


@dataclass(frozen=True)
class SavedLookCoverage:
    """Deterministic saved-outfit coverage facts for one owner (W-7/UC-14 input).

    `saved_outfit_count` is the owner's `source_context == "outfit"` save
    count — hairstyle/grooming/legacy rows never count, because only outfit
    saves can reference wardrobe items (`snapshot.selectedItemIds`).
    `represented_item_ids` are the distinct canonical wardrobe UUID strings
    from those saves that still resolve to the owner's current wardrobe
    items (stale/deleted IDs dropped). `represented_categories` maps each
    such category code to its distinct represented-item count. Pure facts —
    prose is composed in the application layer.
    """

    saved_outfit_count: int
    represented_item_ids: frozenset[str]
    represented_categories: dict[str, int]


@dataclass(frozen=True)
class WearEventRecord:
    """A `wardrobe_wear_events` row (owner-scoped read, STEP 15.3).

    One row = one wardrobe item worn. `wear_group_id` correlates the rows
    of one logging action (single-item wear = a group of one).
    `wardrobe_item_id` intentionally carries no FK (No-FK-to-trigger rule):
    rows survive item deletion and stale UUIDs resolve to nothing at read
    time — never fabricated, never inferred.
    """

    id: UUID
    user_id: UUID
    wardrobe_item_id: UUID
    worn_at: datetime
    wear_group_id: UUID
    idempotency_key: str
    created_at: datetime


@dataclass(frozen=True)
class WearGroupRecord:
    """A `wardrobe_wear_groups` ledger row (STEP 15.4B).

    The durable identity of one logical wear action: one user + one
    idempotency key = one group. `id` IS the `wear_group_id` shared by the
    action's `wardrobe_wear_events` rows. `item_ids` is the canonical
    request payload (sorted unique UUID strings) plus the worn instant —
    replay equivalence only, never intelligence input.
    """

    id: UUID
    user_id: UUID
    idempotency_key: str
    item_ids: list[str]
    worn_at: datetime
    created_at: datetime


@dataclass(frozen=True)
class WearSummary:
    """Read-only wear-intelligence facts for one owner (STEP 15.6).

    Grounded ONLY in flat `wardrobe_wear_events` rows (never the
    `wardrobe_wear_groups.item_ids` ledger payload, never favorites, saved
    looks, recommendations, or created/updated timestamps). Every field is
    attributed to the owner's CURRENT `wardrobe_items`: historical rows
    whose item no longer exists are ignored everywhere, so
    `total_wears == sum(wear_counts.values()) ==
    sum(wears_by_category.values())` always holds.

    Determinism (fixed by `GetWearSummary` / `get_wear_summary`):
    - `wear_counts` / `last_worn` cover every current item (zeros / None
      included), keyed by canonical UUID string in sorted-id order.
    - `most_worn_item_ids`: items tied at the maximum wear count (empty
      when nothing was ever worn); ordered by last-worn desc, item id asc.
    - `least_worn_item_ids`: items tied at the minimum wear count over ALL
      current items — never-worn items included when present (empty only
      when the wardrobe itself is empty); never-worn (None) sorts before
      any instant, then last-worn asc, then item id asc.
    - `unworn_item_ids`: the zero-count subset of the above, item id asc.
    - `recently_worn_item_ids`: distinct current items whose last wear is
      at/after the caller-supplied `recent_since` cutoff (inclusive);
      ordered by last-worn desc, item id asc.
    - `wears_by_category`: categories of the owner's current items only
      (code-sorted, zero-filled); categories with no current items never
      appear.
    """

    total_wears: int
    wear_counts: dict[str, int]
    last_worn: dict[str, Optional[datetime]]
    most_worn_item_ids: list[str]
    least_worn_item_ids: list[str]
    unworn_item_ids: list[str]
    recently_worn_item_ids: list[str]
    wears_by_category: dict[str, int]


@dataclass(frozen=True)
class UserProfileRecord:
    """The owner's current profile projection (UC-6 `GET /v1/users/me`).

    ``settings`` is the contract's sparse container; no `settings` column
    exists in `user_state` yet (controlled keys arrive with the M2 module),
    so the SQL adapter returns an empty dict — never fabricated data.
    """

    user_id: UUID
    display_name: str
    style_profile: dict
    preferences: dict
    settings: dict
    flags: dict
    version: int


class AnalysisRunRepository(Protocol):
    def create(
        self,
        *,
        user_id: UUID,
        run_type: str,
        engine_version: str,
        input_media: Optional[dict] = None,
        knowledge_version: Optional[str] = None,
    ) -> UUID: ...

    def get_for_user(self, *, user_id: UUID, run_id: UUID) -> Optional[AnalysisRunRecord]: ...

    def list_for_user(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[AnalysisRunSummary], int]: ...

    def complete(
        self, *, run_id: UUID, user_id: UUID, status: str, result: Optional[dict]
    ) -> bool: ...

    def fail(self, *, run_id: UUID, user_id: UUID, error: Optional[dict]) -> bool: ...


class UserStateRepository(Protocol):
    def get_style_profile(self, *, user_id: UUID) -> Optional[dict]: ...

    def get_profile(self, *, user_id: UUID) -> Optional[UserProfileRecord]: ...

    def update_preferences(self, *, user_id: UUID, preferences: dict) -> None: ...


class SavedLookRepository(Protocol):
    def insert(
        self,
        *,
        user_id: UUID,
        look_id: Optional[str],
        title: str,
        source_context: str,
        snapshot: dict,
        idempotency_key: str,
        source_run_id: Optional[UUID],
    ) -> SavedLookRecord: ...

    def get_for_user(self, *, user_id: UUID, saved_look_id: UUID) -> Optional[SavedLookRecord]: ...

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional[SavedLookRecord]: ...

    def list_for_user(
        self, *, user_id: UUID, page: int, page_size: int
    ) -> tuple[list[SavedLookRecord], int]: ...

    def get_outfit_coverage(self, *, user_id: UUID) -> "SavedLookCoverage": ...

    def delete(
        self, *, user_id: UUID, saved_look_id: UUID
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class WardrobeItemRepository(Protocol):
    """Wardrobe item repository protocol — OW-1 owner-scoping."""

    def get_for_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
        category: Optional[str] = None,
        color: Optional[str] = None,
        sort: Optional[str] = None,
        order: str = "desc",
    ) -> tuple[list["WardrobeItemRecord"], int]: ...

    def get_by_id(
        self, *, user_id: UUID, item_id: UUID
    ) -> Optional["WardrobeItemRecord"]: ...

    def create(
        self,
        *,
        user_id: UUID,
        name: str,
        category: str,
        color: str,
        material: Optional[str],
        isFavorite: bool,
    ) -> "WardrobeItemRecord": ...

    def update(
        self,
        *,
        user_id: UUID,
        item_id: UUID,
        name: Optional[str],
        category: Optional[str],
        color: Optional[str],
        material: Optional[str],
        material_set: bool = False,
        isFavorite: Optional[bool],
    ) -> Optional["WardrobeItemRecord"]: ...

    def delete(
        self, *, user_id: UUID, item_id: UUID
    ) -> None: ...

    def get_insight_summary(self, *, user_id: UUID) -> "WardrobeInsightSummary": ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class WearEventRepository(Protocol):
    """Wear-event repository protocol — OW-1 owner-scoping (STEP 15.3).

    Minimal contract for the 15.4 use-case layer (`LogWearEvents` /
    `ListWearEvents`); the SQL implementation lands with the API step.
    `wardrobe_item_id` values are validated against the owner's current
    wardrobe by the caller (unknown/foreign IDs → 404, never 403).
    """

    def log(
        self,
        *,
        user_id: UUID,
        wardrobe_item_id: UUID,
        worn_at: datetime,
        wear_group_id: UUID,
        idempotency_key: str,
    ) -> "WearEventRecord": ...

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> list["WearEventRecord"]: ...

    def list_for_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
        item_id: Optional[UUID] = None,
    ) -> tuple[list["WearEventRecord"], int]: ...

    def get_wear_summary(
        self, *, user_id: UUID, recent_since: datetime
    ) -> "WearSummary":
        """Read-only wear-intelligence facts for one owner (STEP 15.6).

        `recent_since` is an aware UTC cutoff owned by the caller
        (`GetWearSummary` derives it from its recent-wear window).
        """
        ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class WearGroupRepository(Protocol):
    """Wear-group ledger protocol — OW-1 owner-scoping (STEP 15.4B).

    Minimal contract for the logical wear action's durable identity
    (`LogWearEvents` writes the group first in the same transaction, then
    the action's `wardrobe_wear_events` rows). Not a generic idempotency
    framework: one table, two ops, worn only by the wear surface.
    """

    def create_group(
        self,
        *,
        user_id: UUID,
        idempotency_key: str,
        item_ids: list[str],
        worn_at: datetime,
    ) -> "WearGroupRecord": ...

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional["WearGroupRecord"]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class LearningSignalRepository(Protocol):
    def insert_look_saved(
        self,
        *,
        user_id: UUID,
        signal_type: str = "look_saved",
        label: str,
        context: Optional[dict],
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
