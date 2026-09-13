"""Application use cases — M13 outfit generation + save (UC-28/29/30).

`GenerateOutfit` (endpoint #41 `POST /v1/outfits/generate`) derives one
`OutfitRecommendation` per request from the owner's current UserState
(read-only preferences) + owned wardrobe. There is no outfit-records
table (TRX-4): derivation is READ/DERIVE only — no INSERT/UPDATE/DELETE
anywhere (no save, no signal, no wear row, no preference/event/wardrobe
mutation — and no commit call at all).

The canonical generate → score → rank → select pipeline is reused
verbatim (no second engine, no second scoring). Scoring occasions are
`[occasion] + persisted preferred_occasions`, deduped (M8-C/M9
precedent); the preferred-item set stays empty (M8-C/M9 precedent —
`resolve_preferred_item_ids` is never consulted here).

`seed` (UC-29) only selects among the ranked legal candidates: absent →
the winner (`select_best_outfit_candidate`); supplied → a stable hash
index into the ranked list (same key + same inputs → same pick;
different keys differ best-effort). Bounds (`1..200`, supplied-empty
rejected) are enforced here so direct callers see identical 422s; the
router declares the same bounds as the wire guard.

`SaveOutfit` (endpoint #42 `POST /v1/outfits/saved`, UC-30) freezes one
derived outfit via M7 `SaveRecommendation` (TRX-3) under
`sourceContext == "outfit"`. Before delegating, the outfit snapshot's
component IDs are fail-closed (DEC-010): malformed → 422, unknown or
foreign → 404, nothing stored. M7 itself is untouched.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from typing import Optional
from uuid import UUID

from app.api.errors import ApiError, ai_failure, not_found
from app.application.saved_looks import SaveRecommendation
from app.domain.ports.external import KnowledgeSource
from app.domain.ports.repositories import (
    ActivityDayRepository,
    LearningSignalRepository,
    OutfitComponent,
    OutfitRecommendation,
    SavedLookRepository,
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
# same order as the M8-C event outfit and M9 adapters).
_OUTFIT_SLOT_ORDER = ("tops", "bottoms", "outerwear", "footwear", "accessories")

_SLOT_ATTRS = {
    "tops": "top_ids",
    "bottoms": "bottom_ids",
    "outerwear": "outerwear_ids",
    "footwear": "footwear_ids",
    "accessories": "accessory_ids",
}

# Preference/seed bound (M9 `_SELECTOR_MAX_LENGTH` precedent: no
# authoritative maximum; BC-13 family ceiling, enforced as 422).
_VALUE_MAX_LENGTH = 200


def _field_error(field: str, error: str) -> ApiError:
    return ApiError(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Some of the provided values are not valid. Please check your input.",
        details={"field_errors": [{"field": field, "error": error}]},
    )


def _validate_preference(field: str, value: object) -> str:
    """Validate one preference selection (non-blank 1..200 string).

    Returns the stripped value for scoring/prose; the wire echoes stay
    verbatim. No backend vocab table exists for these selections, so
    validation is structural only (UC-28 "invalid preference values").
    """
    if not isinstance(value, str) or not value.strip():
        raise _field_error(field, "must be a non-empty string")
    if len(value) > _VALUE_MAX_LENGTH:
        raise _field_error(
            field, f"must be between 1 and {_VALUE_MAX_LENGTH} characters"
        )
    return value.strip()


def _validate_selector(field: str, value: object) -> Optional[str]:
    """Validate the opaque UC-29 seed selector (absent → winner pick)."""
    if value is None:
        return None
    if not isinstance(value, str) or not (1 <= len(value) <= _VALUE_MAX_LENGTH):
        raise _field_error(
            field,
            f"must be between 1 and {_VALUE_MAX_LENGTH} characters",
        )
    return value


def _select_index(count: int, key: Optional[str]) -> int:
    """Deterministic ranked-candidate pick (M9 `_select_index` precedent).

    Absent key → rank 0 (the winner). Supplied key → stable SHA-256
    index into the ranked list: identical inputs repeat byte-identically,
    different keys vary best-effort over the bounded candidate space.

    Empty candidate space (`count <= 0`) is a caller error: the derivation
    guards `if not ranked: return None` before selecting, so this raises
    `ValueError` instead of crashing with `ZeroDivisionError` (`% 0`) —
    the Python analog of Dart `Random.nextInt(0)` (`RangeError: max ... was 0`).
    """
    if count <= 0:
        raise ValueError("no candidates to select from")
    if key is None:
        return 0
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest, 16) % count


class _DerivationFailed(Exception):
    """Unexpected engine failure during candidate derivation."""


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


def _candidate_member_ids(candidate) -> list[str]:
    ids: list[str] = []
    for category in _OUTFIT_SLOT_ORDER:
        ids.extend(getattr(candidate, _SLOT_ATTRS[category], ()))
    return [str(item_id) for item_id in ids]


def _to_recommendation(
    *,
    occasion: str,
    mood: str,
    fit: str,
    color_palette: str,
    winner,
    by_record: dict,
) -> OutfitRecommendation:
    label = occasion.title()
    components: list[OutfitComponent] = []
    covered: list[str] = []
    for category in _OUTFIT_SLOT_ORDER:
        for item_id in getattr(winner, _SLOT_ATTRS[category], ()):
            record = by_record.get(str(item_id))
            if record is None:  # pragma: no cover — defensive; IDs are owned.
                continue
            components.append(
                OutfitComponent(
                    id=str(record.id),
                    name=record.name,
                    category=category,
                    color=record.color,
                    material=record.material,
                    reason=f"Chosen {category} piece for your {label} outfit",
                )
            )
        if getattr(winner, _SLOT_ATTRS[category], ()):
            covered.append(category)
    count = len(covered)
    member_ids = _candidate_member_ids(winner)
    colors: list[str] = []
    for component in components:
        if component.color not in colors:
            colors.append(component.color)
    favorites = [
        by_record[component.id].name
        for component in components
        if component.id in by_record and by_record[component.id].is_favorite
    ]

    reasons = [
        f"Picked for a {label} occasion",
        f"Covers {count} categor{'y' if count == 1 else 'ies'}: "
        + ", ".join(covered),
    ]
    reasons.extend(f"Includes your favorite {name}" for name in favorites)

    # Metric prose states only request/composition/score facts — never
    # engine-signal claims, comfort, flattery, or invented score points
    # (AI-0). Every value is verifiable against the request + winner.
    match_score = round(winner.score / 100, 4)
    percent = int(round(winner.score))
    missing = [
        category
        for category in _OUTFIT_SLOT_ORDER
        if not getattr(winner, _SLOT_ATTRS[category], ())
    ]
    if missing:
        improvement = (
            f"Consider adding {missing[0]} to complete the coverage."
        )
    else:
        improvement = "Full coverage across all five categories."
    return OutfitRecommendation(
        title=f"{label} Outfit",
        match_score=match_score,
        components=components,
        reasons=reasons,
        color_harmony=(
            f"{color_palette} palette across {len(member_ids)} "
            f"{'piece' if len(member_ids) == 1 else 'pieces'}: "
            + ", ".join(colors)
            + "."
        ),
        body_fit=f"Assembled for a {fit} fit across {len(member_ids)} pieces.",
        occasion_match=f"Matched for {label} across {count} categories.",
        style_score_impact=(
            f"{percent}% ensemble match from {len(member_ids)} owned pieces."
        ),
        improvement_suggestion=improvement,
        selected_occasion=occasion,
        selected_mood=mood,
        selected_color_palette=color_palette,
    )


class GenerateOutfit:
    """Derive one outfit (endpoint #41 `POST /v1/outfits/generate`,
    UC-28/UC-29).

    READ/DERIVE only (TRX-2): repeated calls over unchanged inputs are
    byte-identical. `seed` is an opaque ranked-candidate selector —
    no vocabulary is invented for it. No legal candidate → `None`
    (the router answers 204); an unexpected engine failure surfaces as
    503 (C-8, no internals).
    """

    def __init__(
        self,
        *,
        wardrobe_items: WardrobeItemRepository,
        user_state: UserStateRepository,
    ) -> None:
        self._wardrobe_items = wardrobe_items
        self._user_state = user_state

    def __call__(
        self,
        *,
        user_id: UUID,
        occasion: object,
        mood: object,
        fit: object,
        color_palette: object,
        seed: object = None,
    ) -> Optional[OutfitRecommendation]:
        clean_occasion = _validate_preference("occasion", occasion)
        clean_mood = _validate_preference("mood", mood)
        clean_fit = _validate_preference("fit", fit)
        clean_palette = _validate_preference("colorPalette", color_palette)
        key = _validate_selector("seed", seed)
        try:
            return _derive_outfit(
                wardrobe_items=self._wardrobe_items,
                user_state=self._user_state,
                user_id=user_id,
                occasion=clean_occasion,
                mood=clean_mood,
                fit=clean_fit,
                color_palette=clean_palette,
                key=key,
            )
        except _DerivationFailed:
            raise ai_failure()


def _derive_outfit(
    *,
    wardrobe_items: WardrobeItemRepository,
    user_state: UserStateRepository,
    user_id: UUID,
    occasion: str,
    mood: str,
    fit: str,
    color_palette: str,
    key: Optional[str],
) -> Optional[OutfitRecommendation]:
    """Shared derivation for UC-28 (no seed) and UC-29 (seeded).

    Returns the honest `OutfitRecommendation`, or `None` when the owner
    has no legal candidate (empty wardrobe / tops+bottoms missing) —
    the router maps `None` to 204 ("no matching wardrobe", #41).
    """
    wardrobe = _load_owner_wardrobe(wardrobe_items=wardrobe_items, user_id=user_id)
    if not wardrobe:
        return None

    occasions = [occasion]
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
        occasion=occasion,
        mood=mood,
        fit=fit,
        color_palette=color_palette,
        winner=winner,
        by_record=by_record,
    )


def _invalid_component(field: str, error: str) -> ApiError:
    """422 for a malformed outfit snapshot component (DEC-010)."""
    return ApiError(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Some of the provided values are not valid. Please check your input.",
        details={"field_errors": [{"field": field, "error": error}]},
    )


class SaveOutfit:
    """Freeze one derived outfit (endpoint #42 `POST /v1/outfits/saved`,
    UC-30) via M7 `SaveRecommendation` (TRX-3) under
    `sourceContext == "outfit"`.

    The snapshot's component IDs fail closed before anything is stored
    (DEC-010): malformed IDs → 422; unknown or foreign IDs → 404
    (OW-1, 404-not-403). M7 itself is untouched — the validated snapshot
    delegates verbatim, so idempotent replay (same key + payload) and
    409 (same key, different payload) keep M7 semantics byte-for-byte.
    """

    def __init__(
        self,
        *,
        saved_looks: SavedLookRepository,
        signals: LearningSignalRepository,
        knowledge: KnowledgeSource,
        wardrobe_items: WardrobeItemRepository,
        activity_days: Optional[ActivityDayRepository] = None,
    ) -> None:
        self._saved_looks = saved_looks
        self._signals = signals
        self._knowledge = knowledge
        self._wardrobe_items = wardrobe_items
        self._activity_days = activity_days

    def _validated_outfit_components(self, *, user_id: UUID, snapshot: object) -> dict:
        """Structural + ownership validation for an outfit snapshot.

        Requires a non-empty `components` list whose members carry
        non-empty string `id`/`name`/`category`/`color` (the component
        identity contract); every ID must parse as a UUID (else 422)
        and resolve to an owned wardrobe row (else 404). Returns the
        snapshot untouched — identity is never rewritten here.
        """
        if not isinstance(snapshot, dict):
            raise _invalid_component("snapshot", "must be an object")
        raw_components = snapshot.get("components")
        if not isinstance(raw_components, list) or not raw_components:
            raise _invalid_component(
                "snapshot.components", "must be a non-empty list"
            )
        for component in raw_components:
            if not isinstance(component, dict):
                raise _invalid_component(
                    "snapshot.components", "every component must be an object"
                )
            for field in ("id", "name", "category", "color"):
                value = component.get(field)
                if not isinstance(value, str) or not value:
                    raise _invalid_component(
                        f"snapshot.components.{field}",
                        "must be a non-empty string",
                    )
            try:
                item_id = UUID(component["id"])
            except (ValueError, TypeError):
                raise _invalid_component(
                    "snapshot.components.id",
                    f"not a valid UUID: {component['id']}",
                )
            if (
                self._wardrobe_items.get_by_id(user_id=user_id, item_id=item_id)
                is None
            ):
                # Owner-scoped lookup: nonexistent and foreign IDs are
                # indistinguishable by design (OW-1, 404-not-403). The save
                # is rejected outright — foreign IDs are never silently
                # dropped.
                raise not_found()
        return snapshot

    def __call__(
        self,
        *,
        user_id: UUID,
        look_id: Optional[str],
        title: str,
        snapshot: dict,
        idempotency_key: str,
    ):
        """Returns (saved_look, created). `created=False` on replay."""
        validated = self._validated_outfit_components(
            user_id=user_id, snapshot=snapshot
        )
        saver = SaveRecommendation(
            saved_looks=self._saved_looks,
            signals=self._signals,
            knowledge=self._knowledge,
            wardrobe_items=self._wardrobe_items,
            activity_days=self._activity_days,
        )
        return saver(
            user_id=user_id,
            look_id=look_id,
            title=title,
            snapshot=validated,
            source_context="outfit",
            idempotency_key=idempotency_key,
        )
