"""Repository ports — persistence seams the application layer depends on.

Implementations live in `app/infrastructure/db/repositories.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any, Optional, Protocol, Sequence, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from app.domain.services.media_attention import (
        ContributingRecordAssignment,
        MediaAttentionEvidence,
        MediaAttentionObservation,
    )
    from app.domain.services.normalization import NormalizedProduct
    from app.domain.services.product_identity import IdentityDecision
    from app.domain.services.search_interest import SearchInterestObservation
    from app.domain.services.trends import ObservationEvidence


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
    idempotency_key: Optional[str] = None


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
    knowledge_version: Optional[str] = None


@dataclass(frozen=True)
class SavedLookRecord:
    """A `saved_looks` row (owner-scoped read).

    ``source_context`` is the backend-owned domain discriminator (STEP 11.16:
    hairstyle/grooming/outfit, plus M9 "daily" via 0018). It defaults to
    ``None``, which marks a legacy row written before the contract — domain
    unknown, never inferred.
    """

    id: UUID
    look_id: Optional[str]
    title: str
    snapshot: dict
    source_run_id: Optional[UUID]
    created_at: datetime
    source_context: Optional[str] = None


@dataclass(frozen=True)
class UserEventRecord:
    """A `user_events` row (owner-scoped read, M8-A).

    `event_type` is the stable `event_types` code (K9.1, never a label).
    `event_time` is wall-clock `HH:mm` with no timezone (DEC-016);
    `None` means no time was supplied. `location`/`notes` are verbatim
    stored text (`None` = absent); no trimming or normalization is ever
    applied at this layer.
    """

    id: UUID
    user_id: UUID
    title: str
    event_type: str
    event_date: date
    event_time: Optional[time]
    location: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class EventOutfitComponent:
    """One owned wardrobe item inside an event outfit (M8-C).

    Honest subset of the ensemble `OutfitComponent`: `id` is the real
    backend wardrobe UUID string; `category`/`color`/`material` are the
    stored vocab codes (K9.1, labels never on wire — M9 C12 precedent).
    `colorHex` has no server source and is absent by construction
    (DEC-015, AI-0). `reason` states only the grounded selection fact
    (the item's slot pick for the derivation occasion) — never comfort,
    fit, mood, or AI claims.
    """

    id: str
    name: str
    category: str
    color: str
    material: Optional[str]
    reason: str


@dataclass(frozen=True)
class EventOutfitRecommendation:
    """A derived event outfit (M8-C, UC-21) — read/derive only.

    Honest subset of the ensemble `OutfitRecommendation`: `match_score`
    is the winner's 0–100 budget score rescaled to the family 0..1
    wire scale; `selected_occasion` is the event TYPE CODE. Fields with
    no engine source (`colorHarmony`, `bodyFit`, `occasionMatch`,
    `styleScoreImpact`, `improvementSuggestion`, `selectedMood`,
    `selectedColorPalette`, per-component `colorHex`) are absent by
    construction (AI-0 honesty outranks DTO-completeness — DEC-015,
    M5 P-3 precedent). The canonical DTO carries no alternatives
    (verified: DAILY §4.4, V1, builder mock), so runners-up are never
    exposed here.
    """

    title: str
    match_score: float
    components: list["EventOutfitComponent"]
    reasons: list[str]
    selected_occasion: str


@dataclass(frozen=True)
class TodayLookComponent:
    """One owned wardrobe item inside a derived TodayLook (M9, UC-16/UC-17).

    Honest subset of the derived-look `DailyOutfitComponent`:
    `id`/`name` come from the owned row; `category`/`color`/`material`
    are the stored vocab codes (K9.1, labels never on wire — DEC-018
    C12). `colorHex` has no server source and is absent by construction
    (AI-0, same verified fact as DEC-015).
    """

    id: str
    name: str
    category: str
    color: str
    material: Optional[str]


@dataclass(frozen=True)
class TodayLookAlternative:
    """One ranked runner-up surfaced with a TodayLook (M9, DEC-018 C12).

    Minimal mapping only: a stable id derived from the alternative's own
    member wardrobe UUIDs (never mock ids) plus the candidate's native
    0–100 score. Names and style labels have no grounded source and are
    absent by construction (AI-0).
    """

    id: str
    match_score: int


@dataclass(frozen=True)
class TodayLookRecommendation:
    """A derived TodayLook (M9, UC-16/UC-17) — read/derive only.

    The derived-look family DTO (DAILY §4.4): `match_score`/`style_score`
    are the winner's native 0–100 int scale (STEP-13 budget, no rescale —
    DEC-018 C12); `occasion` is the seeding event TYPE CODE when
    event-seeded, else the preferred-occasion derivation (`None` when
    neither exists — omitted, never fabricated); `selected_item_ids` is
    the canonical sorted-unique winner UUID list (the additive top-level
    field that reuses M7 validation verbatim); `alternatives` are
    `ranked[1:3]`; `style_dna` carries only present profile subfields;
    `total_items`/`matching_items` are grounded wardrobe counts.
    `weather` has no provider in v1 and stays `None` (absent hint,
    never an error — DEC-017-G). Sourceless optionals (`aiInsights`,
    `dailyStyleTip`, `aiSelectionReason`, `confidenceBoost`,
    `wardrobeContext.insight`) are absent by construction (AI-0).
    """

    title: str
    occasion: Optional[str]
    description: str
    match_score: int
    style_score: int
    components: list["TodayLookComponent"]
    reasons: list[str]
    style_dna: Optional[dict]
    total_items: int
    matching_items: int
    alternatives: list["TodayLookAlternative"]
    selected_item_ids: list[str]


@dataclass(frozen=True)
class OutfitComponent:
    """One owned wardrobe item inside a derived outfit (M13, UC-28/UC-29).

    Ensemble-family `OutfitComponent`: `id`/`name` come from the owned
    row; `category`/`color`/`material` are the stored vocab codes;
    `reason` states only the grounded slot-pick fact (M8-C precedent).
    `colorHex` has no server source and is absent by construction
    (AI-0, same verified fact as DEC-015/M9).
    """

    id: str
    name: str
    category: str
    color: str
    material: Optional[str]
    reason: str


@dataclass(frozen=True)
class OutfitRecommendation:
    """A derived outfit (M13, UC-28/UC-29) — read/derive only.

    The ensemble-family DTO (REC_API §4.3, V1 §6.7): `match_score` is
    the winner's 0–100 budget score rescaled to the family 0..1 wire
    scale (M8-C precedent, no second scoring); `selected_occasion`/
    `selected_mood`/`selected_color_palette` echo the validated request
    prefs (stripped, else verbatim). Metric prose (`color_harmony`, `body_fit`,
    `occasion_match`, `style_score_impact`, `improvement_suggestion`)
    states only request/composition/score facts (palette + member
    colors + counts, requested fit, occasion + coverage, ensemble
    match percent, coverage gaps) — never engine-signal claims, comfort
    or flattery prose (AI-0). No alternatives: the canonical DTO
    carries none, so runners-up are never exposed here.
    """

    title: str
    match_score: float
    components: list["OutfitComponent"]
    reasons: list[str]
    color_harmony: str
    body_fit: str
    occasion_match: str
    style_score_impact: str
    improvement_suggestion: str
    selected_occasion: str
    selected_mood: str
    selected_color_palette: str


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
    # STEP 2.9 (C-02-F Option B): persisted fit evidence; trailing defaults
    # keep every existing construction valid (absent = None = neutral).
    fit: Optional[str] = None
    fit_confidence: Optional[float] = None


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
        idempotency_key: Optional[str] = None,
    ) -> UUID: ...

    def get_for_user(self, *, user_id: UUID, run_id: UUID) -> Optional[AnalysisRunRecord]: ...

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional[AnalysisRunRecord]: ...

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

    def update_style_profile(
        self,
        *,
        user_id: UUID,
        face_shape: Optional[str] = None,
        skin_tone: Optional[str] = None,
        body_type: Optional[str] = None,
        style_type: Optional[str] = None,
        source_run_id: Optional[str] = None,
    ) -> None: ...


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

    def count_for_user(self, *, user_id: UUID) -> int: ...

    def delete(
        self, *, user_id: UUID, saved_look_id: UUID
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass(frozen=True)
class FeedbackEventRecord:
    """One append-only `feedback_events` row (M11, UC-32).

    Raw user reaction: `rating` is the submitted tag string (vocabulary
    pending the feedback design — stored verbatim, never normalized);
    at most one of `target_look_id` (catalog `looks.code`) /
    `target_saved_look_id` (owned `saved_looks.id`) is set.
    """

    id: UUID
    user_id: UUID
    target_look_id: Optional[str]
    target_saved_look_id: Optional[UUID]
    rating: str
    reason: Optional[str]
    idempotency_key: str
    occurred_at: datetime


class FeedbackRepository(Protocol):
    """Append-only reaction-history protocol — M11 (UC-32).

    Single INSERT per submit (tier 1, TRX-2 non-transactional value
    write — no signal, no activity, no second unit). Idempotent replay
    is keyed by `(user_id, idempotency_key)` (M7 precedent): the use
    case compares the canonical payload and returns the original row or
    raises conflict. No commit inside row methods — the owning use case
    commits (SavedLook precedent).
    """

    def insert(
        self,
        *,
        user_id: UUID,
        target_look_id: Optional[str],
        target_saved_look_id: Optional[UUID],
        rating: str,
        reason: Optional[str],
        idempotency_key: str,
    ) -> FeedbackEventRecord: ...

    def get_by_idempotency(
        self, *, user_id: UUID, idempotency_key: str
    ) -> Optional[FeedbackEventRecord]: ...

    def list_for_user(
        self, *, user_id: UUID, limit: int = 100
    ) -> list[FeedbackEventRecord]: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class LookRepository(Protocol):
    """Minimal catalog-look existence read — M11 target validation.

    Only what UC-32 needs: resolving a submitted `targetLookId`
    (catalog `looks.code`) to its canonical code. System-owned, never
    user-scoped (KN catalog). Read-only — no commit, no write.
    """

    def get_by_code(self, *, code: str) -> Optional[str]: ...


class UserEventRepository(Protocol):
    """Event-calendar repository protocol — OW-1 owner-scoping (M8-A).

    Minimal foundation contract for the upcoming M8 CRUD use cases
    (UC-18/UC-19/UC-20): every row op is scoped to the caller's
    `user_id` (unknown/foreign ids resolve to `None`/no-op at this
    layer; the use case maps that to 404, never 403). No signal writes,
    no preference writes (R36 lives in the use case as a sequential
    second unit, DEC-015). No commit inside row methods — the owning
    use case commits (SavedLook precedent).
    """

    def create(
        self,
        *,
        user_id: UUID,
        title: str,
        event_type: str,
        event_date: date,
        event_time: Optional[time] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> "UserEventRecord": ...

    def get_for_user(self, *, user_id: UUID, event_id: UUID) -> Optional["UserEventRecord"]: ...

    def list_for_user(
        self,
        *,
        user_id: UUID,
        from_date: Optional[date] = None,
        order: str = "asc",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list["UserEventRecord"], int]: ...

    def update(
        self,
        *,
        user_id: UUID,
        event_id: UUID,
        title: str,
        event_type: str,
        event_date: date,
        event_time: Optional[time] = None,
        location: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Optional["UserEventRecord"]: ...

    def delete(
        self, *, user_id: UUID, event_id: UUID
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class EventTypeRepository(Protocol):
    """Read-only M8 event-type vocabulary protocol (M8-A).

    System-owned, never user-scoped (K9.1): only `active` rows, in
    deterministic `(sort_order, code)` order (DEC-015, 0005 precedent).
    Read-only — no commit, no write, no user data. Upcoming create/update
    validation resolves codes through here (unknown/inactive → 422).
    """

    def list_active(self) -> list["VocabularyRecord"]: ...

    def get_by_code(self, *, code: str) -> Optional["VocabularyRecord"]:
        """Return the active row for `code`, else `None`.

        Unknown AND inactive codes resolve to `None` so callers reject
        both with the same 422 (no existence oracle on deprecated codes).
        """
        ...


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
        image_ref: Optional[dict[str, Any]] = None,
        fit: Optional[str] = None,
        fit_confidence: Optional[float] = None,
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
        image_ref: Optional[dict[str, Any]] = None,
        image_ref_set: bool = False,
        fit: Optional[str] = None,
        fit_set: bool = False,
        fit_confidence: Optional[float] = None,
        fit_confidence_set: bool = False,
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

    def list_recent_labels(self, *, user_id: UUID, limit: int) -> list[str]:
        """Return the user's newest signal labels first (owner-scoped).

        Read surface for `GET /v1/learning/summary` recents (M10-B,
        DEC-020 §E): server-owned `label` strings only — never type,
        context, or timestamps.
        """
        ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class ActivityDayRepository(Protocol):
    """Streak-history seam (E9, P1, M10-A).

    Minimal on purpose: the per-signal upsert plus the styled-day read
    the streak derivation needs. No speculative CRUD — history rows are
    never edited or deleted while the account lives (PR-5).
    """

    def upsert_styled_day(self, *, user_id: UUID, day: date) -> None:
        """Mark the user's calendar day styled (idempotent per day)."""
        ...

    def list_styled_days(self, *, user_id: UUID) -> list[date]:
        """Return the user's styled days (owner-scoped)."""
        ...


@dataclass(frozen=True)
class VocabularyRecord:
    """One active system-owned vocabulary row (M5 knowledge reads, STEP 19.5).

    Knowledge-only facts (`code`/`label`/`sort_order` from
    `wardrobe_categories` or `colors`); never user-scoped, never user data.
    """

    code: str
    label: str
    sort_order: int


class VocabularyRepository(Protocol):
    """Read-only system vocabulary protocol — M5 `#19`/`#20` (STEP 19.5).

    Lists active rows in deterministic `(sort_order, code)` order.
    Implementations never expose user rows through this port (KN-9).
    """

    def list_active(self) -> list["VocabularyRecord"]: ...


@dataclass(frozen=True)
class AuthAccountRecord:
    """An auth identity row (D-AUTH-1, M1).

    The (provider, subject) pair IS the account identity (BC-1);
    `password_hash` is the provider-side credential (bcrypt, never the
    password). `register_idempotency_key` is the C-12 replay key of the
    register call that created the account (None for legacy rows).
    """

    user_id: UUID
    auth_provider: str
    auth_subject: str
    display_name: str
    password_hash: Optional[str]
    register_idempotency_key: Optional[str]


@dataclass(frozen=True)
class AuthSessionRecord:
    """One R51 device/session row (D-AUTH-1, M1).

    `token_digest` identifies the row without persisting the bearer
    token; `revoked_at` stamps logout; `expires_at` bounds lifetime.
    """

    id: UUID
    user_id: UUID
    token_digest: str
    expires_at: datetime
    revoked_at: Optional[datetime]


class AuthRepository(Protocol):
    """Account + session seam for the auth module (D-AUTH-1, M1).

    Minimal on purpose: account lookup/creation by the opaque
    (provider, subject) identity plus session issue/lookup/revoke.
    Password hashing and token minting live in the infrastructure auth
    adapter (`app/infrastructure/auth.py`) — never here, never in
    domain logic (F-3/DR-1: domain sees `user_id` only).
    """

    def find_account(
        self, *, auth_provider: str, auth_subject: str
    ) -> Optional[AuthAccountRecord]: ...

    def create_account(
        self,
        *,
        auth_provider: str,
        auth_subject: str,
        display_name: str,
        password_hash: Optional[str],
        idempotency_key: Optional[str],
    ) -> AuthAccountRecord: ...

    def create_session(
        self,
        *,
        session_id: UUID,
        user_id: UUID,
        token_digest: str,
        expires_at: datetime,
    ) -> AuthSessionRecord: ...

    def find_session(
        self, *, token_digest: str
    ) -> Optional[AuthSessionRecord]: ...

    def revoke_session(self, *, session_id: UUID) -> None: ...

    def delete_account(self, *, user_id: UUID) -> bool: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class DiscoveryRepository(Protocol):
    """Persistence boundary for one Discovery collection run (D3).

    Kept deliberately narrow: the collection service orchestrates the
    workflow, this port only persists. The SQL adapter lives in
    ``app.infrastructure.db.repositories``; tests substitute an in-memory
    fake to exercise adapter/failure paths without a database.
    """

    def start_run(self, *, source: str) -> UUID: ...

    def insert_raw_if_absent(
        self,
        *,
        run_id: UUID,
        source: str,
        source_record_id: Optional[str],
        payload: object,
        payload_hash: str,
        source_timestamp: Optional[datetime],
    ) -> tuple[UUID, bool]:
        """Insert one verbatim raw record; return ``(id, created)``.

        ``created`` is ``False`` when an identical ``(source, payload_hash)``
        already exists — the existing id is returned and no row is added.
        """
        ...

    def mark_raw(self, *, raw_id: UUID, status: str, error: Optional[str]) -> None: ...

    def upsert_product(
        self,
        *,
        product: "NormalizedProduct",
        run_id: UUID,
        source: str,
        source_product_id: str,
        raw_id: UUID,
        payload_hash: str,
    ) -> "IdentityDecision":
        """Persist a listing and return its resolved canonical identity.

        Applies the conservative policy in
        ``app.domain.services.product_identity``: exact source identity
        updates the existing product; a verified GTIN match attaches the
        listing to that product without overwriting its canonical fields; a
        possible match creates a separate product and reports the candidates.

        Also appends one ``product_observations`` row for the listing, in the
        same transaction as the product/mapping write, so a failed write never
        leaves a product without its observation (or vice versa). The source
        timestamp is taken from ``product.observed_at``; the observation's own
        ``observed_at`` is the collection time.
        """
        ...

    def finish_run(
        self,
        *,
        run_id: UUID,
        status: str,
        fetched: int,
        inserted: int,
        updated: int,
        skipped: int,
        failed: int,
        error_summary: Optional[str],
    ) -> None: ...

    def rollback(self) -> None:
        """Drop a failed unit of work so a poisoned session can finish the run."""
        ...


@dataclass(frozen=True)
class ProductVariantRecord:
    """Variant metadata (size, color, SKU, GTIN) for a product (DISCOVERY-10B-3)."""

    id: UUID
    sku: Optional[str] = None
    gtin: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductOfferRecord:
    """One retailer's commercial offer for a canonical product (DISCOVERY-10B-2)."""

    id: UUID
    retailer_id: UUID
    retailer_name: str
    retailer_slug: str
    price: float
    product_url: str
    currency: str = "INR"
    availability: bool = True
    in_stock: bool = True
    original_price: Optional[float] = None
    affiliate_url: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    retailer_domain: str = ""
    variant: Optional[ProductVariantRecord] = None
    product_id: Optional[UUID] = None
    is_active: bool = True


@dataclass(frozen=True)
class CatalogProductRecord:
    """One normalized catalog product shaped for domain use cases (DISCOVERY-03).

    Derived from the canonical ``products`` table. Unprovided fields stay
    ``None`` (or empty) — never fabricated. ``price`` is exact numeric INR.
    ``image_urls`` holds provider CDN URLs only (never binaries).
    ``is_synthetic`` / ``is_fixture`` explicitly flag test fixtures.
    ``offers`` contains all active multi-retailer commercial offers.
    """

    id: UUID
    title: str
    brand: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    attributes: dict[str, Any] = field(default_factory=dict)
    price: Optional[float] = None
    currency: Optional[str] = None
    availability: Optional[bool] = None
    product_url: Optional[str] = None
    image_urls: tuple[str, ...] = ()
    offers: tuple[ProductOfferRecord, ...] = ()
    first_seen_at: Optional[datetime] = None
    last_verified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def is_synthetic(self) -> bool:
        return bool(self.attributes.get("synthetic", False))

    @property
    def is_fixture(self) -> bool:
        return bool(self.attributes.get("fixture", False))

    @property
    def material(self) -> Optional[str]:
        val = self.attributes.get("material")
        return str(val) if val is not None else None

    @property
    def color(self) -> Optional[str]:
        val = self.attributes.get("color")
        return str(val) if val is not None else None

    @property
    def fit(self) -> Optional[str]:
        val = self.attributes.get("fit")
        return str(val) if val is not None else None

    @property
    def silhouette(self) -> Optional[str]:
        val = self.attributes.get("silhouette")
        return str(val) if val is not None else None

    @property
    def season(self) -> Optional[str]:
        val = self.attributes.get("season")
        return str(val) if val is not None else None

    @property
    def style_tags(self) -> tuple[str, ...]:
        val = self.attributes.get("style_tags")
        if isinstance(val, (list, tuple)):
            return tuple(str(x) for x in val)
        return ()

    @property
    def gtin(self) -> Optional[str]:
        identifiers = self.attributes.get("identifiers")
        if isinstance(identifiers, dict):
            val = identifiers.get("gtin")
            return str(val) if val is not None else None
        return None


CatalogProduct = CatalogProductRecord


@dataclass(frozen=True)
class ProductFilterCriteria:
    """Hard filter specifications for catalog product candidate retrieval (DISCOVERY-03)."""

    categories: Optional[tuple[str, ...]] = None
    exclude_categories: Optional[tuple[str, ...]] = None
    subcategories: Optional[tuple[str, ...]] = None
    exclude_subcategories: Optional[tuple[str, ...]] = None
    brands: Optional[tuple[str, ...]] = None
    exclude_brands: Optional[tuple[str, ...]] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    currency: Optional[str] = None
    materials: Optional[tuple[str, ...]] = None
    colors: Optional[tuple[str, ...]] = None
    fits: Optional[tuple[str, ...]] = None
    silhouettes: Optional[tuple[str, ...]] = None
    in_stock_only: Optional[bool] = None
    include_synthetic: bool = True
    has_price: Optional[bool] = None
    has_images: Optional[bool] = None
    ffo_concepts: Optional[tuple[str, ...]] = None
    q: Optional[str] = None


class ProductCandidateRepository(Protocol):
    """Persistence read boundary for catalog candidate retrieval (DISCOVERY-03)."""

    def get_by_id(self, product_id: UUID) -> Optional[CatalogProductRecord]: ...

    def count_candidates(self, criteria: ProductFilterCriteria) -> int: ...

    def get_candidates(
        self,
        criteria: ProductFilterCriteria,
        *,
        sort_order: str = "newest",
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[CatalogProductRecord, ...]: ...

    def get_product_offers(
        self, product_id: UUID
    ) -> tuple[ProductOfferRecord, ...]: ...

    def get_offer_by_id(
        self, offer_id: UUID
    ) -> Optional[ProductOfferRecord]: ...




class TrendRepository(Protocol):
    """Read boundary for the D6 trend engine.

    Reads historical observations for a half-open window ``[start, end)`` and
    shapes them for the pure engine in ``app.domain.services.trends``. Strictly
    read-only: no writes, no migration, no clock. The SQL adapter lives in
    ``app.infrastructure.db.repositories``.
    """

    def observations_in_window(
        self, *, window_start: datetime, window_end: datetime
    ) -> "tuple[ObservationEvidence, ...]":
        """Observation evidence with ``observed_at`` in ``[start, end)``."""
        ...


@dataclass(frozen=True)
class SearchInterestEvidence:
    """One stored search-interest observation shaped for a read boundary (D9B).

    A concept-level **relative** signal — no product, no price. ``value`` is
    ``None`` whenever ``value_status`` is not ``present`` (never zero).
    ``observed_at`` is collection time; ``source_timestamp`` is provider time.
    ``synthetic`` marks fixture/test evidence.
    """

    source: str
    metric: str
    query_kind: str
    query_key: str
    query_display: str
    geo_scope: str
    geo_scope_type: str
    aggregation_interval: str
    period_start: datetime
    period_end: datetime
    value: Optional[float]
    value_scale: str
    value_status: str
    is_relative: bool
    source_timestamp: Optional[datetime]
    observed_at: datetime
    query_config_version: str
    synthetic: bool


class SearchInterestRepository(Protocol):
    """Persistence boundary for search-interest observations (D9B).

    Deliberately separate from ``DiscoveryRepository``: a search-interest
    observation is a concept-level signal, not a product listing, and must not
    reuse the product path. The collection workflow still uses the existing
    ``DiscoveryRepository`` for its run + verbatim raw-record bookkeeping.
    """

    def insert_observation(
        self,
        *,
        observation: "SearchInterestObservation",
        run_id: UUID,
        raw_id: UUID,
        payload_hash: str,
    ) -> tuple[UUID, bool]:
        """Append one observation; return ``(id, created)``.

        ``created`` is ``False`` when the observation already exists (same raw
        record, or the same natural key from a differently-hashed payload), so
        repeated collection never inflates a series.
        """
        ...

    def observations_in_window(
        self, *, window_start: datetime, window_end: datetime
    ) -> "tuple[SearchInterestEvidence, ...]":
        """Observations whose period is fully contained in ``[start, end)``.

        Read-only; ordered by ``(query_key, geo_scope, period_start)``.
        """
        ...


@runtime_checkable
class MediaAttentionRepository(Protocol):
    """Persistence boundary for media-attention observations (D9B).

    Deliberately separate from ``DiscoveryRepository`` and ``SearchInterestRepository``:
    a media-attention observation is an aggregated concept-level editorial press signal
    derived from clustered news articles, not a search query index or product listing.
    """

    def insert_observation_with_contributing_records(
        self,
        *,
        observation: "MediaAttentionObservation",
        run_id: Optional[UUID],
        contributing_records: Sequence["ContributingRecordAssignment"] = (),
    ) -> tuple[UUID, bool]:
        """Atomically persist one observation and its contributing records.

        Returns ``(observation_id, created)``.
        - If an observation with the same natural key already exists, returns
          ``(existing_id, False)`` without overwriting the existing observation.
        - Idempotently ensures all provided contributing records are linked
          (relinking any missing/pruned records) while maintaining atomicity.
        """
        ...

    def relink_contributing_records(
        self,
        *,
        observation_id: UUID,
        contributing_records: Sequence["ContributingRecordAssignment"],
    ) -> int:
        """Insert missing join records for an existing observation.

        Returns count of newly linked records. Resets ``provenance_pruned = False``.
        """
        ...

    def observations_in_window(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        query_key: Optional[str] = None,
        geo_scope: Optional[str] = None,
    ) -> tuple["MediaAttentionEvidence", ...]:
        """Observations whose period is fully contained in ``[window_start, window_end)``.

        Read-only; ordered by ``(query_key, geo_scope, period_start)``.
        """
        ...

    def get_contributing_records(
        self,
        *,
        observation_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple["ContributingRecordAssignment", ...]:
        """Read drill-down contributing record assignments for an observation."""
        ...

    def prune_expired_raw_records(
        self,
        *,
        older_than: datetime,
    ) -> int:
        """Prune raw source records older than a cutoff date.

        Cascades link removal, marks parent observations as ``provenance_pruned = True``,
        and returns the number of pruned raw records.
        """
        ...


@dataclass(frozen=True)
class DiscoveryEventRecord:
    """Canonical domain representation of a persisted discovery interaction event."""

    id: UUID
    user_id: Optional[UUID]
    guest_session_id: Optional[UUID]
    event_type: str
    target_type: str
    target_id: str
    product_id: Optional[UUID]
    surface: str
    position: Optional[int]
    client_event_id: UUID
    payload_hash: str
    metadata: dict[str, Any]
    client_occurred_at: datetime
    received_at: datetime


@runtime_checkable
class DiscoveryEventRepository(Protocol):
    """Discovery interaction events persistence seam (DISCOVERY-10A)."""

    def persist_events_batch(
        self,
        *,
        events: Sequence[dict[str, Any]],
        user_id: Optional[UUID],
        guest_session_id: Optional[UUID],
    ) -> list[tuple[UUID, str, bool]]:
        """Persist a batch of events atomically in a single database transaction.

        Returns a list of (client_event_id, status, replayed).
        - status: 'accepted' or 'acknowledged'
        - replayed: True if already persisted with identical payload_hash
        - If client_event_id already exists with conflicting payload_hash, raises ApiError(409)
        """
        ...

    def get_existing_product_ids(self, product_ids: set[UUID]) -> set[UUID]:
        """Validate which product UUIDs exist in the products table."""
        ...


