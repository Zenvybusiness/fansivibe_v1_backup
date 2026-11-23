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
precedent); the preferred-item set carries the request's explicit
C-03 `preferredItemIds` (absent/empty ≡ empty baseline;
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
from typing import Optional, Sequence
from uuid import UUID

from app.api.errors import ApiError, ai_failure, not_found
from app.ai import intent, llm_backend
from app.api.schemas.outfits import (
    MissingPieceSuggestion,
    OutfitCandidateResponse,
    OutfitComponent as OutfitComponentSchema,
    OutfitCompositionResponse,
    ScoreBreakdown,
)
from app.application.saved_looks import SaveRecommendation
from app.domain.ports.external import KnowledgeSource
from app.domain.ports.repositories import (
    ActivityDayRepository,
    FeedbackRepository,
    LearningSignalRepository,
    OutfitComponent,

    OutfitRecommendation,
    SavedLookRepository,
    UserStateRepository,
    WardrobeItemRepository,
    WearEventRepository,
)
from app.domain.services.analysis_rules import (
    _candidate_members,
    _fit_points,
    _occasion_points,
    _palette_points,
    build_feedback_context,
    generate_outfit_candidates,
    rank_outfit_candidates,
    score_outfit_candidate,
    select_best_outfit_candidate,
)
from app.domain.value_objects import OutfitCandidate


# Canonical ensemble slot order for component rendering (tops first —
# same order as the M8-C event outfit and M9 adapters).
_OUTFIT_SLOT_ORDER = ("tops", "bottoms", "outerwear", "footwear", "accessories")

# M11 P4 typed empty reasons (endpoint #41 204 `X-Outfit-Empty-Reason`).
# Stable machine-readable codes proven by backend state only — never
# inferred from text, never ranked by an LLM. `no_legal_candidate` is
# defensive: tops+bottoms always pair today, so it is currently
# unreachable (pragma-marked at the return site).
EMPTY_WARDROBE = "empty_wardrobe"
MISSING_REQUIRED_CATEGORY = "missing_required_category"
NO_LEGAL_CANDIDATE = "no_legal_candidate"
EMPTY_OUTFIT_REASON_HEADER = "X-Outfit-Empty-Reason"

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


def _normalize_preferred_item_ids(value: object) -> frozenset:
    """Normalize request preferred IDs to a deduped frozenset of strings.

    C-03 explicit picks: absent/None/empty ≡ empty (baseline). UUID
    objects → canonical strings; strings pass through (scoring
    canonicalizes; malformed never match → 0). Duplicates collapse by
    set semantics. No DB lookup here — owner-scoped candidates stay the
    security boundary (foreign/unknown IDs contribute 0, never 404).
    """
    if value is None:
        return frozenset()
    if isinstance(value, (str, bytes)):
        return frozenset()
    try:
        items = list(value)  # type: ignore[arg-type]
    except TypeError:
        return frozenset()
    return frozenset(str(item) for item in items if item is not None)


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


# Phase 2 Step 2 — deterministic explanation reasons. Each string is
# emitted ONLY when its score term actually contributed (> 0) to the
# winning candidate; scoring itself is untouched (this function only
# reads winner sub-scores and recomputes the same palette/fit/occasion
# point helpers over the winner's own members).
PALETTE_REASON = "Matches your preferred palette"
FIT_REASON = "Matches your preferred fit"
PREFERRED_ITEM_REASON = "Uses an item you selected"
OCCASION_MATCH_REASON = "Matches the selected occasion"


def _to_recommendation(
    *,
    occasion: str,
    mood: str,
    fit: str,
    color_palette: str,
    winner,
    by_record: dict,
    occasions: object = None,
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

    # Grounded evidence checks: palette/fit/occasion recompute the exact
    # scoring helpers over the winner's members (same inputs the ranker
    # used); preference/favorite read the winner's own sub-scores.
    # Anything uncomputable degrades to "no reason" — never fabricated.
    try:
        _members = _candidate_members(winner, by_record)
    except Exception:
        _members = []
    if isinstance(occasions, (list, tuple)):
        _occasions = [o for o in occasions if isinstance(o, str) and o]
    else:
        _occasions = []
    if not _occasions:
        # ponytail: fallback [occasion] may under-report persisted-pref
        # occasion hits; pass occasions (as _derive_outfit does) to upgrade.
        _occasions = [occasion]
    try:
        _palette_hit = _palette_points(_members, color_palette) > 0
    except Exception:
        _palette_hit = False
    try:
        _fit_hit = _fit_points(_members, fit) > 0
    except Exception:
        _fit_hit = False
    try:
        _occasion_hit = _occasion_points(_members, _occasions) > 0
    except Exception:
        _occasion_hit = False
    try:
        _preferred_hit = float(getattr(winner, "preference", 0.0) or 0.0) > 0.0
    except (TypeError, ValueError):
        _preferred_hit = False
    try:
        _favorite_hit = float(getattr(winner, "favorite", 0.0) or 0.0) > 0.0
    except (TypeError, ValueError):
        _favorite_hit = False

    reasons = [
        f"Picked for a {label} occasion",
        f"Covers {count} categor{'y' if count == 1 else 'ies'}: "
        + ", ".join(covered),
    ]
    if _palette_hit:
        reasons.append(PALETTE_REASON)
    if _fit_hit:
        reasons.append(FIT_REASON)
    if _preferred_hit:
        reasons.append(PREFERRED_ITEM_REASON)
    if _favorite_hit:
        reasons.extend(f"Includes your favorite {name}" for name in favorites)
    if _occasion_hit:
        reasons.append(OCCASION_MATCH_REASON)
    if getattr(winner, "feedback", 0.0) > 0.0:
        reasons.append("Similar to outfits you've liked")
    elif getattr(winner, "feedback", 0.0) < 0.0:
        reasons.append("Reduced because of previous negative feedback")
    if getattr(winner, "wear", 0.0) > 0.0:
        reasons.append("Previously worn combination")
    # Deterministic order is construction order; drop exact duplicates.
    reasons = list(dict.fromkeys(reasons))

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
        feedback: Optional[FeedbackRepository] = None,
        saved_looks: Optional[SavedLookRepository] = None,
        wears: Optional[WearEventRepository] = None,
    ) -> None:
        self._wardrobe_items = wardrobe_items
        self._user_state = user_state
        self._feedback = feedback
        self._saved_looks = saved_looks
        self._wears = wears

    def __call__(
        self,
        *,
        user_id: UUID,
        occasion: object,
        mood: object,
        fit: object,
        color_palette: object,
        seed: object = None,
        preferred_item_ids: object = None,
    ) -> Optional[OutfitRecommendation]:
        record, _ = self.derive_with_reason(
            user_id=user_id,
            occasion=occasion,
            mood=mood,
            fit=fit,
            color_palette=color_palette,
            seed=seed,
            preferred_item_ids=preferred_item_ids,
        )
        return record

    def derive_with_reason(
        self,
        *,
        user_id: UUID,
        occasion: object,
        mood: object,
        fit: object,
        color_palette: object,
        seed: object = None,
        preferred_item_ids: object = None,
    ) -> tuple[Optional[OutfitRecommendation], Optional[str]]:
        """Derive one outfit plus the M11 P4 typed empty reason.

        Returns `(record, None)` on success; `(None, reason)` when no
        legal candidate exists (the router maps this to 204 with
        `X-Outfit-Empty-Reason`). `__call__` stays record-only so
        existing callers are byte-identical.
        """
        clean_occasion = _validate_preference("occasion", occasion)
        clean_mood = _validate_preference("mood", mood)
        clean_fit = _validate_preference("fit", fit)
        clean_palette = _validate_preference("colorPalette", color_palette)
        key = _validate_selector("seed", seed)
        preferred = _normalize_preferred_item_ids(preferred_item_ids)
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
                preferred_item_ids=preferred,
                feedback=self._feedback,
                saved_looks=self._saved_looks,
                wears=self._wears,
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
    preferred_item_ids: frozenset = frozenset(),
    feedback: Optional[FeedbackRepository] = None,
    saved_looks: Optional[SavedLookRepository] = None,
    wears: Optional[WearEventRepository] = None,
) -> Optional[OutfitRecommendation]:
    """Shared derivation for UC-28 (no seed) and UC-29 (seeded).

    Returns `(record, None)` on success, or `(None, reason)` when the
    owner has no legal candidate — the router maps `None` to 204
    ("no matching wardrobe", #41) with the reason as
    `X-Outfit-Empty-Reason`. Reasons come from the same deterministic
    backend state that produced zero candidates (no LLM, no text
    parsing): empty owner wardrobe → `empty_wardrobe`; tops or bottoms
    absent → `missing_required_category`; ranked empty despite both
    present → `no_legal_candidate`.
    """
    wardrobe = _load_owner_wardrobe(wardrobe_items=wardrobe_items, user_id=user_id)
    if not wardrobe:
        return None, EMPTY_WARDROBE

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
            fit=record.fit,
            fit_confidence=record.fit_confidence,
        )
        for record in wardrobe
    ]
    items_by_id = {item.id: item for item in adapted}
    feedback_context = build_feedback_context(
        user_id=user_id,
        feedback=feedback,
        saved_looks=saved_looks,
        wears=wears,
    )
    try:
        ranked = rank_outfit_candidates(
            [
                score_outfit_candidate(
                    candidate, items_by_id, preferred_item_ids, occasions,
                    preferred_palette=color_palette,
                    preferred_fit=fit,
                    feedback_context=feedback_context,
                )
                for candidate in generate_outfit_candidates(adapted)
            ]
        )
    except Exception as exc:
        raise _DerivationFailed from exc
    if not ranked:
        categories = {item.category for item in adapted}
        if "tops" not in categories or "bottoms" not in categories:
            return None, MISSING_REQUIRED_CATEGORY
        return None, NO_LEGAL_CANDIDATE  # pragma: no cover — defensive; tops+bottoms always pair today.
    if key is None:
        winner = select_best_outfit_candidate(ranked)
    else:
        winner = ranked[_select_index(len(ranked), key)]
    if winner is None:  # pragma: no cover — defensive; ranked non-empty.
        return None, NO_LEGAL_CANDIDATE
    by_record = {str(record.id): record for record in wardrobe}
    return (
        _to_recommendation(
            occasion=occasion,
            mood=mood,
            fit=fit,
            color_palette=color_palette,
            winner=winner,
            by_record=by_record,
            occasions=occasions,
        ),
        None,
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


def normalize_slot_name(slot: str) -> str:
    """Normalize user/client-provided slot name to canonical category (P1-1).

    Supported:
    - 'top', 'tops' -> 'tops'
    - 'bottom', 'bottoms' -> 'bottoms'
    - 'footwear', 'shoe', 'shoes' -> 'footwear'
    - 'outerwear' -> 'outerwear'
    - 'accessory', 'accessories' -> 'accessories'
    """
    clean = (slot or "").strip().lower()
    mapping = {
        "top": "tops",
        "tops": "tops",
        "bottom": "bottoms",
        "bottoms": "bottoms",
        "footwear": "footwear",
        "shoe": "footwear",
        "shoes": "footwear",
        "outerwear": "outerwear",
        "accessory": "accessories",
        "accessories": "accessories",
    }
    if clean not in mapping:
        raise ApiError(
            status_code=422,
            code="VALIDATION_ERROR",
            message=f"Unsupported slot '{slot}'. Supported slots: tops, bottoms, footwear, outerwear, accessories.",
            details={"field_errors": [{"field": "slot", "error": f"unsupported slot '{slot}'"}]},
        )
    return mapping[clean]


class SwapOutfitSlot:
    """Swap one outfit component slot and recalculate complete compatibility (P1-1).

    Enforces:
    - User ownership of all current garments and replacement garment (OW-1, 404).
    - Slot category match for replacement garment (422).
    - No duplicate garments across slots (422).
    - Pinned slot protection: cannot swap if the requested slot is pinned (409 PINNED_SLOT_CONFLICT).
    - Preservation of all other pinned garments (invariants verified).
    - Canonical compatibility recalculation using `score_outfit_candidate` and `_to_recommendation`.
    """

    def __init__(
        self,
        *,
        wardrobe_items: WardrobeItemRepository,
        user_state: UserStateRepository,
        feedback: Optional[FeedbackRepository] = None,
        saved_looks: Optional[SavedLookRepository] = None,
        wears: Optional[WearEventRepository] = None,
    ) -> None:
        self._wardrobe_items = wardrobe_items
        self._user_state = user_state
        self._feedback = feedback
        self._saved_looks = saved_looks
        self._wears = wears

    def execute(
        self,
        *,
        user_id: UUID,
        occasion: object,
        mood: object,
        fit: object,
        color_palette: object,
        current_garment_ids: Sequence[UUID],
        slot: str,
        replacement_garment_id: UUID,
        pinned_garment_ids: Optional[Sequence[UUID]] = None,
        seed: object = None,
    ) -> tuple[OutfitRecommendation, Optional[str], Optional[float], list[str]]:
        clean_occasion = _validate_preference("occasion", occasion)
        clean_mood = _validate_preference("mood", mood)
        clean_fit = _validate_preference("fit", fit)
        clean_palette = _validate_preference("colorPalette", color_palette)
        canonical_slot = normalize_slot_name(slot)

        if not current_garment_ids:
            raise _field_error("currentGarmentIds", "must not be empty")

        # Load and verify replacement garment ownership
        replacement_item = self._wardrobe_items.get_by_id(
            user_id=user_id, item_id=replacement_garment_id
        )
        if replacement_item is None:
            raise not_found()

        if replacement_item.category != canonical_slot:
            raise _field_error(
                "replacementGarmentId",
                f"replacement garment category '{replacement_item.category}' does not match requested slot '{canonical_slot}'",
            )

        # Load and verify ownership of every current garment
        current_items: dict[UUID, object] = {}
        for gid in current_garment_ids:
            item = self._wardrobe_items.get_by_id(user_id=user_id, item_id=gid)
            if item is None:
                raise not_found()
            current_items[gid] = item

        pinned_set = set(pinned_garment_ids or ())
        for pid in pinned_set:
            if pid not in current_items:
                raise _field_error(
                    "pinnedGarmentIds",
                    f"pinned garment ID '{pid}' is not part of the current outfit",
                )

        # Find the garment currently in the requested slot
        current_slot_items = [
            item for item in current_items.values() if item.category == canonical_slot
        ]
        previous_item_id = str(current_slot_items[0].id) if current_slot_items else None

        # Pinned slot rejection
        if current_slot_items and current_slot_items[0].id in pinned_set:
            raise ApiError(
                status_code=409,
                code="PINNED_SLOT_CONFLICT",
                message=f"Cannot replace slot '{canonical_slot}' because it is pinned. Unpin it first.",
                details={"slot": canonical_slot, "pinned_garment_id": str(current_slot_items[0].id)},
            )

        # Reject duplicate garment across different slots
        if replacement_garment_id in current_items:
            existing = current_items[replacement_garment_id]
            if existing.category != canonical_slot:
                raise _field_error(
                    "replacementGarmentId",
                    f"garment '{replacement_garment_id}' is already used in slot '{existing.category}'",
                )

        # Calculate previous compatibility score if possible
        prev_score: Optional[float] = None
        prev_buckets = {
            "top_ids": tuple(str(item.id) for item in current_items.values() if item.category == "tops"),
            "bottom_ids": tuple(str(item.id) for item in current_items.values() if item.category == "bottoms"),
            "outerwear_ids": tuple(str(item.id) for item in current_items.values() if item.category == "outerwear"),
            "footwear_ids": tuple(str(item.id) for item in current_items.values() if item.category == "footwear"),
            "accessory_ids": tuple(str(item.id) for item in current_items.values() if item.category == "accessories"),
        }
        if prev_buckets["top_ids"] and prev_buckets["bottom_ids"]:
            try:
                prev_cand = OutfitCandidate(**prev_buckets)
                prev_items_by_id = {
                    str(item.id): SimpleNamespace(
                        id=str(item.id),
                        category=item.category,
                        color=item.color,
                        material=item.material,
                        is_favorite=item.is_favorite,
                        fit=item.fit,
                        fit_confidence=item.fit_confidence,
                    )
                    for item in current_items.values()
                }
                prev_scored = score_outfit_candidate(
                    prev_cand,
                    prev_items_by_id,
                    frozenset(),
                    [clean_occasion],
                    preferred_palette=clean_palette,
                    preferred_fit=clean_fit,
                )
                prev_score = round(prev_scored.score / 100, 4)
            except Exception:
                prev_score = None

        # Build resulting items list
        resulting_items = [
            item for item in current_items.values() if item.category != canonical_slot
        ] + [replacement_item]

        # Verify all other pinned garments are preserved
        resulting_ids = {item.id for item in resulting_items}
        for pid in pinned_set:
            if pid not in resulting_ids:
                raise ApiError(
                    status_code=409,
                    code="PINNED_PRESERVATION_VIOLATION",
                    message=f"Pinned garment '{pid}' must be preserved.",
                    details={"pinned_garment_id": str(pid)},
                )

        buckets = {
            "top_ids": tuple(str(item.id) for item in resulting_items if item.category == "tops"),
            "bottom_ids": tuple(str(item.id) for item in resulting_items if item.category == "bottoms"),
            "outerwear_ids": tuple(str(item.id) for item in resulting_items if item.category == "outerwear"),
            "footwear_ids": tuple(str(item.id) for item in resulting_items if item.category == "footwear"),
            "accessory_ids": tuple(str(item.id) for item in resulting_items if item.category == "accessories"),
        }
        candidate = OutfitCandidate(**buckets)

        if not candidate.top_ids or not candidate.bottom_ids:
            raise _field_error(
                "slot",
                "Resulting outfit must contain at least tops and bottoms.",
            )

        occasions = [clean_occasion]
        occasions.extend(
            item
            for item in _preferred_occasions(user_state=self._user_state, user_id=user_id)
            if isinstance(item, str) and item not in occasions
        )
        feedback_context = build_feedback_context(
            user_id=user_id,
            feedback=self._feedback,
            saved_looks=self._saved_looks,
            wears=self._wears,
        )
        items_by_id = {
            str(item.id): SimpleNamespace(
                id=str(item.id),
                category=item.category,
                color=item.color,
                material=item.material,
                is_favorite=item.is_favorite,
                fit=item.fit,
                fit_confidence=item.fit_confidence,
            )
            for item in resulting_items
        }
        scored = score_outfit_candidate(
            candidate,
            items_by_id,
            frozenset(),
            occasions,
            preferred_palette=clean_palette,
            preferred_fit=clean_fit,
            feedback_context=feedback_context,
        )

        by_record = {str(item.id): item for item in resulting_items}
        recommendation = _to_recommendation(
            occasion=clean_occasion,
            mood=clean_mood,
            fit=clean_fit,
            color_palette=clean_palette,
            winner=scored,
            by_record=by_record,
            occasions=occasions,
        )

        warnings: list[str] = []
        if scored.score < 50.0:
            warnings.append("Resulting outfit compatibility is below recommended threshold.")

        return recommendation, previous_item_id, prev_score, warnings


class GetOutfitCandidates:
    """Retrieve eligible replacement wardrobe items for a slot (P1-1)."""

    def __init__(self, *, wardrobe_items: WardrobeItemRepository) -> None:
        self._wardrobe_items = wardrobe_items

    def execute(
        self,
        *,
        user_id: UUID,
        slot: str,
        current_garment_ids: Optional[Sequence[UUID]] = None,
        limit: int = 20,
    ) -> tuple[str, list]:
        canonical_slot = normalize_slot_name(slot)
        exclude_ids = {gid for gid in (current_garment_ids or ())}
        items, _ = self._wardrobe_items.get_for_user(
            user_id=user_id,
            page=1,
            page_size=max(limit * 2, 50),
            category=canonical_slot,
        )
        candidates = [item for item in items if item.id not in exclude_ids]
        return canonical_slot, candidates[:limit]


class ComposeOutfits:
    """Phase 3: Multi-candidate outfit composition engine with natural language parsing,
    wardrobe authority, canonical scoring, diverse candidate generation, and AI reasoning.
    """

    def __init__(
        self,
        *,
        wardrobe_items: WardrobeItemRepository,
        user_state: UserStateRepository,
        feedback: Optional[FeedbackRepository] = None,
        saved_looks: Optional[SavedLookRepository] = None,
        wears: Optional[WearEventRepository] = None,
        storage: Optional[ObjectStoragePort] = None,
    ) -> None:
        self._wardrobe_items = wardrobe_items
        self._user_state = user_state
        self._feedback = feedback
        self._saved_looks = saved_looks
        self._wears = wears
        self._storage = storage

    async def execute(
        self,
        *,
        user_id: UUID,
        occasion: Optional[str] = None,
        mood: Optional[str] = None,
        fit: Optional[str] = None,
        color_palette: Optional[str] = None,
        query: Optional[str] = None,
        preferred_item_ids: Optional[Sequence[UUID]] = None,
        limit: int = 3,
        seed: Optional[str] = None,
        weather_context: Optional[str] = None,
    ) -> tuple[Optional[OutfitCompositionResponse], Optional[str]]:
        # 1. Natural language query normalization & detection
        clean_query = query.strip() if isinstance(query, str) and query.strip() else None
        effective_occasion = occasion.strip() if isinstance(occasion, str) and occasion.strip() else None
        effective_mood = mood.strip() if isinstance(mood, str) and mood.strip() else None
        effective_fit = fit.strip() if isinstance(fit, str) and fit.strip() else None
        effective_palette = color_palette.strip() if isinstance(color_palette, str) and color_palette.strip() else None
        effective_weather = weather_context.strip() if isinstance(weather_context, str) and weather_context.strip() else None

        preferred_ids_set = set(preferred_item_ids or ())

        if clean_query:
            low_query = clean_query.lower()
            # Detect occasion from natural language
            detected_occ = intent.detect_occasion(clean_query)
            if detected_occ and not effective_occasion:
                effective_occasion = detected_occ

            # Detect formality / mood
            formality = intent.detect_formality_change(clean_query)
            if formality == "more_formal":
                effective_mood = effective_mood or "sharp"
                effective_occasion = effective_occasion or "formal"
            elif formality == "more_casual":
                effective_mood = effective_mood or "relaxed"
                effective_occasion = effective_occasion or "casual"

            # Detect weather cues
            if not effective_weather:
                if any(w in low_query for w in ("cold", "chilly", "winter", "freezing")):
                    effective_weather = "Chilly weather"
                elif any(w in low_query for w in ("rain", "rainy", "storm", "wet")):
                    effective_weather = "Rainy weather"
                elif any(w in low_query for w in ("warm", "hot", "summer", "sunny")):
                    effective_weather = "Warm weather"

            # Detect palette cues
            if not effective_palette:
                if "monochrome" in low_query or "black and white" in low_query:
                    effective_palette = "monochrome"
                elif any(w in low_query for w in ("earth", "brown", "olive", "tan")):
                    effective_palette = "earth tones"
                elif "pastel" in low_query:
                    effective_palette = "pastel"
                elif "contrast" in low_query:
                    effective_palette = "high contrast"

        # Defaults if still unspecified
        effective_occasion = effective_occasion or "casual"
        effective_mood = effective_mood or "confident"
        effective_fit = effective_fit or "regular"
        effective_palette = effective_palette or "monochrome"

        # 2. Load authenticated user's PostgreSQL wardrobe (OW-1 authority)
        wardrobe = _load_owner_wardrobe(wardrobe_items=self._wardrobe_items, user_id=user_id)
        if not wardrobe:
            return None, EMPTY_WARDROBE

        # Match garment query from natural language against owned items
        if clean_query:
            target_garment_query = intent.extract_target_garment_query(clean_query)
            if target_garment_query:
                matched_item, _ = intent.match_wardrobe_item(target_garment_query, wardrobe)
                if matched_item and hasattr(matched_item, "id"):
                    preferred_ids_set.add(matched_item.id)

        # 3. Category requirements validation
        categories = {item.category for item in wardrobe}
        if "tops" not in categories or "bottoms" not in categories:
            return None, MISSING_REQUIRED_CATEGORY

        adapted = [
            SimpleNamespace(
                id=str(record.id),
                category=record.category,
                color=record.color,
                material=record.material,
                is_favorite=record.is_favorite,
                fit=record.fit,
                fit_confidence=record.fit_confidence,
            )
            for record in wardrobe
        ]
        items_by_id = {item.id: item for item in adapted}
        by_record = {str(record.id): record for record in wardrobe}

        occasions = [effective_occasion]
        occasions.extend(
            item
            for item in _preferred_occasions(user_state=self._user_state, user_id=user_id)
            if isinstance(item, str) and item not in occasions
        )

        feedback_context = build_feedback_context(
            user_id=user_id,
            feedback=self._feedback,
            saved_looks=self._saved_looks,
            wears=self._wears,
        )

        preferred_norm = frozenset(str(pid) for pid in preferred_ids_set)

        # 4. Generate candidate combinations
        raw_candidates = generate_outfit_candidates(adapted)
        if not raw_candidates:
            return None, NO_LEGAL_CANDIDATE

        # 5. Canonical scoring
        scored_candidates = [
            score_outfit_candidate(
                candidate,
                items_by_id,
                preferred_norm,
                occasions,
                preferred_palette=effective_palette,
                preferred_fit=effective_fit,
                feedback_context=feedback_context,
            )
            for candidate in raw_candidates
        ]
        ranked = rank_outfit_candidates(scored_candidates)
        if not ranked:
            return None, NO_LEGAL_CANDIDATE

        # 6. Diverse candidate selection: guarantee genuinely different combinations
        selected_scored = []
        seen_pairs = set()

        start_idx = _select_index(len(ranked), seed) if seed else 0
        ordered_ranked = ranked[start_idx:] + ranked[:start_idx] if start_idx > 0 else ranked

        # Prioritize candidates that contain user-preferred / requested target pieces
        if preferred_norm:
            preferred_ranked = [
                c for c in ordered_ranked
                if preferred_norm.intersection(set(c.top_ids + c.bottom_ids + c.outerwear_ids + c.footwear_ids + c.accessory_ids))
            ]
            other_ranked = [
                c for c in ordered_ranked
                if not preferred_norm.intersection(set(c.top_ids + c.bottom_ids + c.outerwear_ids + c.footwear_ids + c.accessory_ids))
            ]
            ordered_ranked = preferred_ranked + other_ranked

        for c in ordered_ranked:
            pair = (tuple(sorted(c.top_ids)), tuple(sorted(c.bottom_ids)))
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                selected_scored.append(c)
                if len(selected_scored) >= limit:
                    break

        if len(selected_scored) < limit:
            full_seen = {
                (
                    tuple(sorted(c.top_ids)),
                    tuple(sorted(c.bottom_ids)),
                    tuple(sorted(c.outerwear_ids)),
                    tuple(sorted(c.footwear_ids)),
                    tuple(sorted(c.accessory_ids)),
                )
                for c in selected_scored
            }
            for c in ordered_ranked:
                fsig = (
                    tuple(sorted(c.top_ids)),
                    tuple(sorted(c.bottom_ids)),
                    tuple(sorted(c.outerwear_ids)),
                    tuple(sorted(c.footwear_ids)),
                    tuple(sorted(c.accessory_ids)),
                )
                if fsig not in full_seen:
                    full_seen.add(fsig)
                    selected_scored.append(c)
                    if len(selected_scored) >= limit:
                        break

        # 7. Build rich response candidates
        role_map = {
            "tops": "top",
            "bottoms": "bottom",
            "outerwear": "outerwear",
            "footwear": "footwear",
            "accessories": "accessory",
        }

        candidate_responses: list[OutfitCandidateResponse] = []
        titles_pool = [
            f"{effective_occasion.title()} Essential Look",
            f"Elevated {effective_occasion.title()} Ensemble",
            f"Relaxed {effective_occasion.title()} Coordination",
            f"Refined {effective_occasion.title()} Style",
            f"Modern {effective_occasion.title()} Ensemble",
        ]

        for idx, candidate in enumerate(selected_scored):
            cand_id = f"outfit-cand-{idx + 1}-{hashlib.md5(f'{candidate.top_ids}_{candidate.bottom_ids}_{seed}'.encode()).hexdigest()[:8]}"
            title = titles_pool[idx % len(titles_pool)]

            components: list[OutfitComponentSchema] = []
            component_dicts: list[dict] = []
            covered_categories: list[str] = []

            for cat in _OUTFIT_SLOT_ORDER:
                cat_ids = getattr(candidate, _SLOT_ATTRS[cat], ())
                if cat_ids:
                    covered_categories.append(cat)
                for item_id in cat_ids:
                    record = by_record.get(str(item_id))
                    if record is None:
                        continue

                    # Presigned image URL resolution
                    image_url: Optional[str] = None
                    image_ref = record.image_ref
                    if image_ref and isinstance(image_ref, dict):
                        key = (
                            image_ref.get("objectKey")
                            or image_ref.get("object_key")
                            or image_ref.get("canonical_key")
                            or image_ref.get("key")
                        )
                        if key and self._storage is not None:
                            try:
                                image_url = await self._storage.generate_presigned_get_url(key=key, expires_in_s=900)
                                image_ref = {**image_ref, "downloadUrl": image_url, "url": image_url}
                            except Exception:
                                pass

                    comp = OutfitComponentSchema(
                        id=str(record.id),
                        name=record.name,
                        category=cat,
                        role=role_map.get(cat, cat),
                        color=record.color,
                        material=record.material,
                        reason=f"Selected {role_map.get(cat, cat)} piece for {effective_occasion} styling",
                        imageUrl=image_url,
                        imageRef=image_ref,
                    )
                    components.append(comp)
                    component_dicts.append({
                        "id": str(record.id),
                        "name": record.name,
                        "category": cat,
                        "role": role_map.get(cat, cat),
                        "color": record.color,
                        "material": record.material,
                    })

            # Sub-score calculations
            try:
                _members = _candidate_members(candidate, by_record)
            except Exception:
                _members = []
            palette_pts = _palette_points(_members, effective_palette)
            fit_pts = _fit_points(_members, effective_fit)
            occasion_pts = _occasion_points(_members, occasions)
            pref_pts = float(getattr(candidate, "preference", 0.0) or 0.0)
            fb_pts = float(getattr(candidate, "feedback", 0.0) or 0.0)
            wear_pts = float(getattr(candidate, "wear", 0.0) or 0.0)

            match_score = round(candidate.score / 100, 4)

            score_breakdown = ScoreBreakdown(
                totalScore=match_score,
                occasionMatch=round(occasion_pts, 2),
                paletteMatch=round(palette_pts, 2),
                fitMatch=round(fit_pts, 2),
                preferenceBonus=round(pref_pts, 2),
                feedbackBonus=round(fb_pts, 2),
                wearAdjustment=round(wear_pts, 2),
                calculation=f"Overall compatibility {int(round(candidate.score))}% based on occasion alignment ({int(occasion_pts*100)}%), palette harmony ({int(palette_pts*100)}%), silhouette fit ({int(fit_pts*100)}%), and preference weights.",
            )

            # Grounded styling rationale & tips
            color_names = list(dict.fromkeys(c.color for c in components if c.color))
            color_harmony = f"{effective_palette.title()} harmony with {', '.join(color_names)} tones providing clean visual balance."
            style_desc = f"Complete {effective_occasion} outfit tailored for a {effective_fit} silhouette in {effective_palette} tones."

            reasons = [
                f"Curated for {effective_occasion.title()} settings",
                f"Harmonious {effective_palette} color balance across {len(components)} items",
            ]
            if palette_pts > 0:
                reasons.append("Matches your chosen palette")
            if fit_pts > 0:
                reasons.append(f"Structured for a {effective_fit} profile")
            if pref_pts > 0:
                reasons.append("Incorporates your selected wardrobe preferences")

            styling_tips = [
                f"Color balance: The {', '.join(color_names)} combination maintains a clean focal point.",
                f"Proportions: Balanced for a {effective_fit} silhouette; consider tucking or rolling the cuffs to emphasize waist or ankle lines.",
            ]
            if candidate.outerwear_ids:
                styling_tips.append("Outerwear: Wear the layer open to create an elongating vertical line.")
            elif effective_weather and "cold" in effective_weather.lower():
                styling_tips.append("Temperature tip: Bring a structured layer for cooler indoor temperatures.")

            # Missing pieces suggestions
            missing_pieces: list[MissingPieceSuggestion] = []
            if not candidate.footwear_ids:
                missing_pieces.append(
                    MissingPieceSuggestion(
                        category="footwear",
                        role="footwear",
                        suggestion="Clean leather sneakers or dress loafers would ground this ensemble",
                        isOwned=False,
                    )
                )
            if not candidate.outerwear_ids:
                missing_pieces.append(
                    MissingPieceSuggestion(
                        category="outerwear",
                        role="outerwear",
                        suggestion="A structured blazer, field jacket, or overcoat would add layered depth",
                        isOwned=False,
                    )
                )
            if not candidate.accessory_ids:
                missing_pieces.append(
                    MissingPieceSuggestion(
                        category="accessories",
                        role="accessory",
                        suggestion="A minimal leather belt or understated watch would provide finishing polish",
                        isOwned=False,
                    )
                )

            styling_rationale = (
                f"This {effective_occasion} ensemble brings together your {', '.join(c.name for c in components)}. "
                f"The {effective_palette} tones complement each other without competing, while the {effective_fit} cut creates a deliberate, well-proportioned silhouette."
            )

            # AI reasoning enrichment for top candidate if model available
            if idx == 0 and llm_backend.is_available():
                try:
                    missing_cat_names = [mp.category for mp in missing_pieces]
                    enriched = llm_backend.enrich_stylist_recommendation(
                        user_query=clean_query or f"{effective_occasion} outfit",
                        occasion=effective_occasion,
                        selected_components=component_dicts,
                        missing_categories=missing_cat_names if missing_cat_names else None,
                        weather_context=effective_weather,
                        base_text=styling_rationale,
                    )
                    if enriched and enriched != styling_rationale:
                        styling_rationale = enriched
                except Exception:
                    pass

            snapshot = {
                "title": title,
                "matchScore": match_score,
                "components": [c.model_dump(exclude_none=True) for c in components],
                "selectedItemIds": [c.id for c in components],
                "reasons": reasons,
                "colorHarmony": color_harmony,
                "bodyFit": f"Assembled for a {effective_fit} fit.",
                "occasionMatch": f"Matched for {effective_occasion.title()}.",
                "styleScoreImpact": f"{int(round(candidate.score))}% match from owned pieces.",
                "improvementSuggestion": "Full coverage across core pieces." if not missing_pieces else f"Consider adding {missing_pieces[0].category} to elevate the ensemble.",
                "selectedOccasion": effective_occasion,
                "selectedMood": effective_mood,
                "selectedColorPalette": effective_palette,
            }

            candidate_responses.append(
                OutfitCandidateResponse(
                    id=cand_id,
                    title=title,
                    occasion=effective_occasion,
                    styleDescription=style_desc,
                    matchScore=match_score,
                    scoreBreakdown=score_breakdown,
                    components=components,
                    reasons=reasons,
                    stylingRationale=styling_rationale,
                    colorHarmony=color_harmony,
                    stylingTips=styling_tips,
                    missingPieces=missing_pieces,
                    selectedOccasion=effective_occasion,
                    selectedMood=effective_mood,
                    selectedColorPalette=effective_palette,
                    snapshot=snapshot,
                )
            )

        return (
            OutfitCompositionResponse(
                candidates=candidate_responses,
                totalCandidates=len(candidate_responses),
                occasion=effective_occasion,
                mood=effective_mood,
                fit=effective_fit,
                colorPalette=effective_palette,
                query=clean_query,
                weatherContext=effective_weather,
            ),
            None,
        )

