"""Application use cases — M9 Today's Look derivation (UC-16/UC-17).

`GetTodayLook` (endpoint #31 `GET /v1/looks/today`) and
`RegenerateTodayLook` (endpoint #32 `POST /v1/looks/today`) derive one
`TodayLook` per request from the owner's current UserState + owned
wardrobe + optional nearest event. There is no `today_look_records`
table (DEC-017-A): derivation is READ/DERIVE only — no INSERT/UPDATE/
DELETE anywhere (no save, no signal, no wear row, no preference write,
no event/wardrobe mutation — and no commit call at all).

The canonical generate → score → rank → select pipeline is reused
verbatim (no second engine, no second scoring). The optional nearest
event seeds the scoring occasions as highest priority: candidate set =
owner events with `event_date` >= server-UTC today (today qualifies),
ordered `event_date ASC, event_time ASC NULLS LAST, id ASC` via the
frozen M8 list ordering (DEC-018 §2); the first row or none. Only the
event TYPE CODE is consumed. No event → derive normally (never 404 for
the missing event alone). Scoring occasions are `[event code] +
persisted preferred_occasions`, deduped (DEC-018/M8-C precedent).

Variant/seed only select among the ranked legal candidates (DEC-018
C12): absent → the winner (`select_best_outfit_candidate`); supplied →
a stable hash index into the ranked list (same key + same inputs →
same pick; different keys differ best-effort — a bounded candidate
space can collide, DEC-017-C). Bounds (`1..200`, supplied-empty
rejected) are enforced here so direct callers see identical 422s; the
router declares the same bounds as the wire guard.

Weather has no provider in v1: the derivation carries no weather hint
and never fails for weather (DEC-017-G).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional
from uuid import UUID

from app.api.errors import ApiError, ai_failure, internal_error
from app.domain.ports.repositories import (
    EventTypeRepository,
    TodayLookAlternative,
    TodayLookComponent,
    TodayLookRecommendation,
    UserEventRepository,
    UserStateRepository,
    WardrobeItemRepository,
)
from app.domain.services.analysis_rules import (
    generate_outfit_candidates,
    rank_outfit_candidates,
    score_outfit_candidate,
    select_best_outfit_candidate,
)

# Canonical ensemble slot order for component rendering (tops first —
# same order as the M8-C event outfit adapter).
_OUTFIT_SLOT_ORDER = ("tops", "bottoms", "outerwear", "footwear", "accessories")

_SLOT_ATTRS = {
    "tops": "top_ids",
    "bottoms": "bottom_ids",
    "outerwear": "outerwear_ids",
    "footwear": "footwear_ids",
    "accessories": "accessory_ids",
}

# Selector bound (DEC-018 §3/4: no authoritative maximum; BC-13 family
# ceiling, enforced as 422 — variant/seed never affect determinism
# guarantees, only which ranked candidate is picked).
_SELECTOR_MAX_LENGTH = 200

# Projection of the snake_case `style_profile` store to the camelCase
# `styleDna` wire object (DEC-018 C12: 4-field StyleProfile projection,
# absent subfields omitted — never 404 for profile gaps).
_STYLE_DNA_FIELDS = (
    ("style_type", "styleType"),
    ("body_type", "bodyType"),
    ("skin_tone", "skinTone"),
    ("face_shape", "faceShape"),
)


def _utc_today():
    """Server-UTC calendar date (nearest-event datum, DEC-018 §2)."""
    return datetime.now(timezone.utc).date()


def _field_error(field: str, error: str) -> ApiError:
    return ApiError(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Some of the provided values are not valid. Please check your input.",
        details={"field_errors": [{"field": field, "error": error}]},
    )


def _validate_selector(field: str, value: object) -> Optional[str]:
    """Validate an opaque variant/seed selector (absent → default pick)."""
    if value is None:
        return None
    if not isinstance(value, str) or not (1 <= len(value) <= _SELECTOR_MAX_LENGTH):
        raise _field_error(
            field,
            f"must be between 1 and {_SELECTOR_MAX_LENGTH} characters",
        )
    return value


def _select_index(count: int, key: Optional[str]) -> int:
    """Deterministic ranked-candidate pick (DEC-018 C12).

    Absent key → rank 0 (the winner). Supplied key → stable SHA-256
    index into the ranked list: identical inputs repeat byte-identically,
    different keys vary best-effort over the bounded candidate space.
    """
    if key is None:
        return 0
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % count


def _clamp_score(value: float) -> int:
    """Winner's native 0–100 budget score → wire int (DEC-018 C12)."""
    return max(0, min(100, int(round(value))))


class _DerivationFailed(Exception):
    """Unexpected engine failure during candidate derivation."""


def _derive_today_look(
    *,
    events: UserEventRepository,
    event_types: EventTypeRepository,
    wardrobe_items: WardrobeItemRepository,
    user_state: UserStateRepository,
    user_id: UUID,
    key: Optional[str],
) -> Optional[TodayLookRecommendation]:
    """Shared derivation for GET (variant) and POST (seed).

    Returns the honest `TodayLookRecommendation`, or `None` when the
    owner has no legal candidate (empty wardrobe / tops+bottoms missing)
    — the router maps `None` to 404 ("none found", DEC-017-B).
    """
    wardrobe = _load_owner_wardrobe(wardrobe_items=wardrobe_items, user_id=user_id)
    if not wardrobe:
        return None

    event_code: Optional[str] = None
    nearest = events.list_for_user(
        user_id=user_id, from_date=_utc_today(), order="asc", page=1, page_size=1
    )[0]
    if nearest:
        event_code = nearest[0].event_type

    occasions = [event_code] if event_code is not None else []
    occasions.extend(
        item
        for item in _preferred_occasions(user_state=user_state, user_id=user_id)
        if isinstance(item, str) and item not in occasions
    )

    adapted = [
        SimpleNamespace(
            id=str(record.id),
            category=record.category,
            color=record.color,
            material=record.material,
            is_favorite=record.is_favorite,
        )
        for record in wardrobe
    ]
    items_by_id = {item.id: item for item in adapted}
    try:
        ranked = rank_outfit_candidates(
            [
                score_outfit_candidate(candidate, items_by_id, frozenset(), occasions)
                for candidate in generate_outfit_candidates(adapted)
            ]
        )
    except Exception as exc:
        raise _DerivationFailed from exc
    if not ranked:
        return None
    if key is None:
        winner = select_best_outfit_candidate(ranked)
    else:
        winner = ranked[_select_index(len(ranked), key)]
    if winner is None:  # pragma: no cover — defensive; ranked non-empty.
        return None
    by_record = {str(record.id): record for record in wardrobe}
    return _to_recommendation(
        event_types=event_types,
        event_code=event_code,
        occasions=occasions,
        user_state=user_state,
        user_id=user_id,
        winner=winner,
        ranked=ranked,
        by_record=by_record,
        total_items=len(wardrobe),
    )


def _load_owner_wardrobe(
    *, wardrobe_items: WardrobeItemRepository, user_id: UUID
) -> list:
    """All of the owner's wardrobe items (owner-scoped pages of 100)."""
    items: list = []
    page = 1
    while True:
        batch, total = wardrobe_items.get_for_user(
            user_id=user_id, page=page, page_size=100
        )
        items.extend(batch)
        if len(items) >= total or not batch:
            return items
        page += 1


def _preferred_occasions(*, user_state: UserStateRepository, user_id: UUID) -> list:
    """Persisted occasion codes for scoring context (read-only)."""
    try:
        profile = user_state.get_profile(user_id=user_id)
    except Exception:
        return []
    if profile is None:
        return []
    raw = profile.preferences.get("preferred_occasions")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _style_dna(*, user_state: UserStateRepository, user_id: UUID) -> Optional[dict]:
    """Present-only StyleProfile projection (read-only, gaps tolerated)."""
    try:
        profile = user_state.get_profile(user_id=user_id)
    except Exception:
        return None
    if profile is None:
        return None
    stored = profile.style_profile
    if not isinstance(stored, dict):
        return None
    projected = {
        wire: stored[store]
        for store, wire in _STYLE_DNA_FIELDS
        if isinstance(stored.get(store), str) and stored[store] != ""
    }
    return projected or None


def _candidate_member_ids(candidate) -> list[str]:
    ids: list[str] = []
    for category in _OUTFIT_SLOT_ORDER:
        ids.extend(getattr(candidate, _SLOT_ATTRS[category], ()))
    return [str(item_id) for item_id in ids]


def _to_recommendation(
    *,
    event_types: EventTypeRepository,
    event_code: Optional[str],
    occasions: list,
    user_state: UserStateRepository,
    user_id: UUID,
    winner,
    ranked: list,
    by_record: dict,
    total_items: int,
) -> TodayLookRecommendation:
    if event_code is not None:
        type_row = event_types.get_by_code(code=event_code)
        label: Optional[str] = type_row.label if type_row is not None else event_code
        occasion: Optional[str] = event_code
    else:
        label = occasions[0] if occasions else None
        occasion = occasions[0] if occasions else None
    title = f"{label} Look" if label else "Today's Look"

    selected_item_ids = sorted(set(_candidate_member_ids(winner)))
    components: list[TodayLookComponent] = []
    covered: list[str] = []
    for category in _OUTFIT_SLOT_ORDER:
        for item_id in getattr(winner, _SLOT_ATTRS[category], ()):
            record = by_record.get(str(item_id))
            if record is None:  # pragma: no cover — defensive; IDs are owned.
                continue
            components.append(
                TodayLookComponent(
                    id=str(record.id),
                    name=record.name,
                    category=category,
                    color=record.color,
                    material=record.material,
                )
            )
        if getattr(winner, _SLOT_ATTRS[category], ()):
            covered.append(category)
    count = len(covered)
    description = (
        f"{title} with {len(selected_item_ids)} "
        f"{'piece' if len(selected_item_ids) == 1 else 'pieces'} "
        f"covering {', '.join(covered)}."
    )
    reasons = []
    if label is not None:
        reasons.append(f"Picked for a {label} occasion")
    reasons.append(
        f"Covers {count} categor{'y' if count == 1 else 'ies'}: " + ", ".join(covered)
    )
    for component in components:
        record = by_record.get(component.id)
        if record is not None and record.is_favorite:
            reasons.append(f"Includes your favorite {record.name}")

    score = _clamp_score(winner.score)
    alternatives = [
        TodayLookAlternative(
            id="-".join(sorted(set(_candidate_member_ids(candidate)))),
            match_score=_clamp_score(candidate.score),
        )
        for candidate in ranked[1:3]
    ]
    return TodayLookRecommendation(
        title=title,
        occasion=occasion,
        description=description,
        match_score=score,
        style_score=score,
        components=components,
        reasons=reasons,
        style_dna=_style_dna(user_state=user_state, user_id=user_id),
        total_items=total_items,
        matching_items=len(selected_item_ids),
        alternatives=alternatives,
        selected_item_ids=selected_item_ids,
    )


class GetTodayLook:
    """Derive today's look (endpoint #31 `GET /v1/looks/today`, UC-17).

    READ/DERIVE only (TRX-2): repeated calls over unchanged inputs are
    byte-identical. `variant` is an opaque ranked-candidate selector —
    no vocabulary is invented for it. No legal candidate → `None`
    (the router answers 404); weather is absent by design (never 503).
    """

    def __init__(
        self,
        *,
        events: UserEventRepository,
        event_types: EventTypeRepository,
        wardrobe_items: WardrobeItemRepository,
        user_state: UserStateRepository,
    ) -> None:
        self._events = events
        self._event_types = event_types
        self._wardrobe_items = wardrobe_items
        self._user_state = user_state

    def __call__(
        self, *, user_id: UUID, variant: object = None
    ) -> Optional[TodayLookRecommendation]:
        key = _validate_selector("variant", variant)
        try:
            return _derive_today_look(
                events=self._events,
                event_types=self._event_types,
                wardrobe_items=self._wardrobe_items,
                user_state=self._user_state,
                user_id=user_id,
                key=key,
            )
        except _DerivationFailed:
            raise internal_error()


class RegenerateTodayLook:
    """Derive a fresh today's look (endpoint #32 `POST /v1/looks/today`, UC-16).

    Same derivation as GET with an independent `seed` selector (no
    variant↔seed equivalence claimed): absent seed → the winner, supplied
    seed → the stable ranked pick. Persists nothing, never keyed. An
    unexpected generation failure surfaces as 503 (C-8, no internals);
    no legal candidate → `None` (the router answers 404).
    """

    def __init__(
        self,
        *,
        events: UserEventRepository,
        event_types: EventTypeRepository,
        wardrobe_items: WardrobeItemRepository,
        user_state: UserStateRepository,
    ) -> None:
        self._events = events
        self._event_types = event_types
        self._wardrobe_items = wardrobe_items
        self._user_state = user_state

    def __call__(
        self, *, user_id: UUID, seed: object = None
    ) -> Optional[TodayLookRecommendation]:
        key = _validate_selector("seed", seed)
        try:
            return _derive_today_look(
                events=self._events,
                event_types=self._event_types,
                wardrobe_items=self._wardrobe_items,
                user_state=self._user_state,
                user_id=user_id,
                key=key,
            )
        except _DerivationFailed:
            raise ai_failure()
