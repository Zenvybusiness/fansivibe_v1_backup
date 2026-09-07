"""The hairstyle decision engine — rules-first, deterministic (DE-0).

Implements the engine stages from `DECISION_ENGINE_ARCHITECTURE.md` for the
hairstyle task only (no empty framework — per-task composition):

  1. ContextBuilder       — appearance + preferences → DecisionContext
  2. CandidateGeneration  — the hairstyle look catalog (KnowledgeSource port)
  3. Filtering            — hard rules: excluded looks (preferences)
  4. Scoring              — weighted signals (seed + face-shape + preference)
  5. Ranking              — score-descending order, top + alternatives
  6. Explanation          — grounded reasons from the catalog (never invented)
  7. Recommendation       — typed HairstyleResult + derived confidence

Confidence is a derived, deterministic run-level value in [0, 1]
(`AI_DOMAIN_MODEL.md` §4.4) from data completeness × top-pick decisiveness; a
sparse profile sets `needs_more_data` instead of fabricating inputs (AI-0).
The LLM (when wired) may only rewrite *wording* — never structure or scores
(BA-8, AI-0). Scores are capped at 1.0 and stay in [0, 1].
"""


from dataclasses import dataclass, field
from typing import Optional, List

from app.domain.ports.external import KnowledgeError, KnowledgeSource
from app.domain.value_objects import (
    AppearanceProfile,
    HairstylePreferences,
    HairstyleResult,
    HairstyleRecommendation,
    GroomingRecommendation,
)
from app.infrastructure.db.repositories import SavedLookRecord


@dataclass
class PersonalizationContext:
    """Assembled personalization context from all available memory sources.

    This is a read-only data structure that gathers explicit preferences,
    supported behavioral signals, and appearance information from the
    user's memory state. It does NOT contain derived preference algorithms
    or ranking logic — those remain the responsibility of the Decision Engine.

    Fields retain their source semantics:
    - appearance: AI-inferred from analysis runs
    - explicit_preferences: User-stated (from preferences screen)
    - saved_looks: User-saved looks (from save actions)
    - signal_count: Supported behavioral signals (look_saved)
    """

    appearance: Optional[AppearanceProfile] = None
    explicit_preferences: Optional[List[str]] = None  # preferred_occasions
    saved_looks: Optional[List[SavedLookRecord]] = None


def assemble_personalization_context(
    *,
    user_id: str,
    user_state: dict,
    saved_looks_repo,
) -> PersonalizationContext:
    """Assemble personalization context from all available memory sources.

    Reads from:
    - user_state.style_profile → appearance (AI-inferred)
    - user_state.preferences.preferred_occasions → explicit preferences (user-stated)
    - saved_looks table → user-saved looks (user-saved)

    Returns a PersonalizationContext with all available data.
    Missing data is represented as None/empty, not fabricated.
    """
    context = PersonalizationContext()

    # 1. Appearance from style_profile (AI-inferred)
    style_profile = user_state.get("style_profile")
    if style_profile and isinstance(style_profile, dict):
        appearance = AppearanceProfile(
            faceShape=style_profile.get("face_shape", "") or "",
            skinTone=style_profile.get("skin_tone", "") or "",
            bodyType=style_profile.get("body_type", "") or "",
            styleType=style_profile.get("style_type", "") or "",
            sourceRunId=style_profile.get("source_run_id", "") or "",
        )
        context.appearance = appearance

    # 2. Explicit preferences from preferences JSONB (user-stated)
    preferences = user_state.get("preferences")
    if preferences and isinstance(preferences, dict):
        raw_occasions = preferences.get("preferred_occasions")
        if raw_occasions:
            if isinstance(raw_occasions, list):
                context.explicit_preferences = [str(o) for o in raw_occasions]
            else:
                context.explicit_preferences = [str(raw_occasions)]

    # 3. Saved looks from saved_looks table (user-saved)
    try:
        user_saved_looks = saved_looks_repo.get_for_user(user_id=user_id)
        if user_saved_looks:
            context.saved_looks = user_saved_looks
    except Exception:
        pass

    return context


def personalization_context_to_decision_context(
    personalization: PersonalizationContext,
    knowledge_version: str = "",
) -> DecisionContext:
    """Map PersonalizationContext to DecisionContext for the existing engine.

    Only fields that the Decision Engine actually needs are included.
    - appearance: passed through if available
    - preferences: HairstylePreferences with empty sets by default
      (mapping from preferred_occasions to preferredLookIds is NOT implemented
       as it would be a derived preference algorithm, deferred to later stages)
    - completeness: computed from appearance profile
    - knowledge_version: passed through

    This mapping ensures backward compatibility: when no personalization
    data exists, the engine functions exactly as before.
    """
    # Build HairstylePreferences - by default empty sets
    # Mapping from user-stated preferred_occasions to preferredLookIds
    # is NOT implemented here (would be a derived preference algorithm)
    preferences = HairstylePreferences()

    # Compute completeness from appearance if available
    completeness = 0.0
    if personalization.appearance is not None:
        completeness = _completeness(personalization.appearance)

    # Build and return DecisionContext
    return DecisionContext(
        appearance=personalization.appearance or AppearanceProfile(
            faceShape="",
            skinTone="",
            bodyType="",
            styleType="",
            sourceRunId="",
        ),
        preferences=preferences,
        completeness=completeness,
        knowledge_version=knowledge_version,
    )

# Deterministic per-look face-shape boosts. Scores = seed + boost, capped at 1.0.
_BOOSTS: dict[str, dict[str, float]] = {
    "textured_quiff": {"oval": 0.06, "heart": 0.03, "rectangle": 0.03},
    "classic_pompadour": {"round": 0.12, "square": 0.10, "rectangle": 0.06},
    "side_part": {"oval": 0.05, "square": 0.06, "diamond": 0.06, "round": 0.02},
    "brushed_up_undercut": {"oval": 0.04, "heart": 0.04, "diamond": 0.05, "square": 0.02},
}

# Soft preference boost for a look the user marked as preferred.
_PREFERENCE_BOOST = 0.03

# Appearance signals that count toward profile completeness.
_APPEARANCE_SIGNALS = ("faceShape", "skinTone", "bodyType", "styleType")

# Score gap (0.0..0.1) that is treated as a fully decisive top pick.
_DECISIVE_GAP = 0.1

_DEFAULT_FACE_SHAPE = "oval"


# --- Grooming boosts --------------------------------------------------------

# Per-look face-shape boosts for grooming looks. Mapped from the "bestFor"
# field in the grooming catalog entries.
_GROOMING_BOOSTS: dict[str, dict[str, float]] = {
    "structured_goatee": {"oval": 0.06, "heart": 0.05, "diamond": 0.05, "square": 0.02},
    "classic_stubble": {"oval": 0.05, "round": 0.04, "square": 0.05},
    "full_beard": {"oval": 0.08, "square": 0.07, "diamond": 0.05},
    "goatee_with_mustache": {"rectangular": 0.07, "heart": 0.05},
}


@dataclass(frozen=True)
class DecisionContext:
    """Stage-1 output — the single object all later stages read.

    ``completeness`` is the fraction of non-empty appearance signals (0.0..1.0);
    ``knowledge_version`` is provenance (KN-1), passed through from the port.
    """

    appearance: AppearanceProfile
    preferences: HairstylePreferences
    completeness: float
    knowledge_version: str = ""


@dataclass(frozen=True)
class ScoredCandidate:
    """Stage-4 output — a candidate with its score and per-signal breakdown."""

    id: str
    score: float
    signals: dict[str, float]
    look: HairstyleRecommendation


@dataclass(frozen=True)
class Explanation:
    """Stage-6 output — grounded reasons for one ranked candidate.

    ``reasons`` come from the validated reason catalog (never invented);
    ``summary`` is the catalog's description, the "why this suits you" text.
    """

    id: str
    title: str
    summary: str
    reasons: list[str] = field(default_factory=list)


def _face_shape(appearance: AppearanceProfile) -> str:
    raw = (appearance.faceShape or "").strip().lower()
    return raw or _DEFAULT_FACE_SHAPE


def _completeness(appearance: AppearanceProfile) -> float:
    present = sum(1 for signal in _APPEARANCE_SIGNALS if getattr(appearance, signal, ""))
    return present / len(_APPEARANCE_SIGNALS)


# --- Stage 1 — Context Builder ---------------------------------------------


def build_context(
    appearance: AppearanceProfile,
    preferences: Optional[HairstylePreferences] = None,
    knowledge_version: str = "",
) -> DecisionContext:
    """Assemble the typed context the later stages read (stage 1)."""
    return DecisionContext(
        appearance=appearance,
        preferences=preferences or HairstylePreferences(),
        completeness=_completeness(appearance),
        knowledge_version=knowledge_version,
    )


# --- Stage 2 — Candidate Generation ----------------------------------------


def generate_candidates(
    knowledge: KnowledgeSource, context: DecisionContext
) -> list[HairstyleRecommendation]:
    """Retrieve the candidate set from the knowledge source (stage 2).

    The engine never hardcodes candidates (BA-11); the port's deprecated
    filtering (KN-3) already applies before the engine sees them.
    """
    candidates = knowledge.retrieve_hairstyle_looks()
    if not candidates:
        raise KnowledgeError("knowledge source returned no hairstyle looks")
    return candidates


# --- Stage 3 — Filtering ----------------------------------------------------


def filter_candidates(
    candidates: list[HairstyleRecommendation], context: DecisionContext
) -> list[HairstyleRecommendation]:
    """Apply hard exclusion rules (stage 3).

    Binary keep/drop and deterministic (BA-3): candidates whose id the user
    excluded are dropped; nothing is scored or reordered here.
    """
    excluded = context.preferences.excludedLookIds
    if not excluded:
        return list(candidates)
    return [look for look in candidates if look.id not in excluded]


# --- Stage 4 — Scoring ------------------------------------------------------


def score_candidates(
    candidates: list[HairstyleRecommendation],
    context: DecisionContext,
    saved_look_ids: frozenset[str] = frozenset(),
) -> list[ScoredCandidate]:
    """Compose weighted scoring signals per candidate (stage 4).

    score = min(1.0, seed + face_shape_boost + preference_boost + saved_look_boost).
    The per-signal breakdown feeds the Explanation stage (truthful "why this").
    - preference_boost: +0.03 if look is in preferredLookIds (explicit user preference).
    - saved_look_boost: +0.03 if look appears in user's saved look history (derived behavior).
      Both boosts are independent and cumulative; a look saved AND preferred gets +0.06 total.
    If no saved look history is provided, behavior is identical to current (backward compatible).
    """
    face = _face_shape(context.appearance)
    preferred = context.preferences.preferredLookIds

    scored: list[ScoredCandidate] = []
    for look in candidates:
        face_boost = _BOOSTS.get(look.id, {}).get(face, 0.0)
        preference_boost = _PREFERENCE_BOOST if look.id in preferred else 0.0
        saved_look_boost = 0.03 if look.id in saved_look_ids else 0.0
        score = min(1.0, look.matchScore + face_boost + preference_boost + saved_look_boost)
        scored.append(
            ScoredCandidate(
                id=look.id,
                score=round(score, 2),
                signals={
                    "seed": look.matchScore,
                    "face_shape": face_boost,
                    "preference": preference_boost,
                    "saved_look": saved_look_boost,
                },
                look=look,
            )
        )
    return scored


# --- Stage 5 — Ranking ------------------------------------------------------


def rank_candidates(scored: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Order candidates by score, top pick first (stage 5).

    Ordering-only: scores are never recomputed here. Ties keep catalog order
    (stable sort), so ranking is deterministic for deterministic inputs.
    """
    return sorted(scored, key=lambda candidate: candidate.score, reverse=True)


# --- Stage 6 — Explanation --------------------------------------------------


def build_explanations(
    ranked: list[ScoredCandidate], context: DecisionContext
) -> list[Explanation]:
    """Produce grounded human reasons for each ranked candidate (stage 6).

    Reasons come verbatim from the validated catalog reason catalog and the
    score-signal breakdown — never invented, never LLM-authored structure.
    """
    face = _face_shape(context.appearance)
    explanations: list[Explanation] = []
    for candidate in ranked:
        face_reason = _face_match_reason(candidate, face)
        reasons = list(candidate.look.reasons)
        if face_reason and face_reason not in reasons:
            reasons = [face_reason] + reasons
        explanations.append(
            Explanation(
                id=candidate.id,
                title=candidate.look.name,
                summary=candidate.look.description,
                reasons=reasons,
            )
        )
    return explanations


def _face_match_reason(candidate: ScoredCandidate, face_shape: str) -> Optional[str]:
    boost = candidate.signals.get("face_shape", 0.0)
    if boost <= 0.0:
        return None
    return (
        f"Strongest match for your {face_shape} face shape "
        f"(+{boost:0.2f} face-shape fit)."
    )


# --- Confidence (derived, deterministic) -------------------------------------


def derive_confidence(
    context: DecisionContext, ranked: list[ScoredCandidate]
) -> float:
    """Derive the run-level confidence in [0, 1] (deterministic).

    50% data completeness + 50% top-pick decisiveness (how clearly the top
    beats the runner-up). Sparse grounding or a tight ranking lowers it
    without ever fabricating a result (AI-0, AI_INTEGRATION_ARCHITECTURE §8).
    """
    completeness = context.completeness
    if len(ranked) >= 2:
        gap = ranked[0].score - ranked[1].score
        decisiveness = min(1.0, max(0.0, gap / _DECISIVE_GAP))
    else:
        decisiveness = 1.0
    return round(0.5 * completeness + 0.5 * decisiveness, 2)


# --- Stage 7 — Recommendation ------------------------------------------------


def _as_recommendation(
    candidate: ScoredCandidate, explanation: Optional[Explanation] = None
) -> HairstyleRecommendation:
    reasons = (
        list(explanation.reasons)
        if explanation is not None
        else list(candidate.look.reasons)
    )
    return HairstyleRecommendation(
        id=candidate.look.id,
        name=candidate.look.name,
        description=candidate.look.description,
        matchScore=candidate.score,
        reasons=reasons,
        stylingTips=candidate.look.stylingTips,
        maintenance=candidate.look.maintenance,
        bestFor=candidate.look.bestFor,
    )


def recommend_hairstyle(
    knowledge: KnowledgeSource,
    appearance: AppearanceProfile,
    preferences: Optional[HairstylePreferences] = None,
    *,
    personalization_context: Optional[PersonalizationContext] = None,
) -> HairstyleResult:
    """Run the full hairstyle recommendation pipeline (thin orchestrator).

    The orchestrator knows the stage order and implements no stage logic —
    each stage is a small pure function above. Rules-first: the top pick
    matches the assistant's face-shape switch (`app/ai/tools.py:
    recommend_hairstyle`) — pompadour-first for round/square/rectangle,
    quiff-first otherwise.

    If ``personalization_context`` is provided, the decision engine incorporates
    saved look history boost and preference signals from memory. When omitted,
    the engine functions exactly as before (backward compatible).
    """
    context = build_context(
        appearance,
        preferences,
        knowledge_version=getattr(knowledge, "knowledge_version", ""),
    )

    candidates = generate_candidates(knowledge, context)
    filtered = filter_candidates(candidates, context)

    # Extract saved look IDs from personalization context if available
    saved_look_ids = frozenset()
    if personalization_context is not None and personalization_context.saved_looks:
        saved_look_ids = frozenset(
            look.look_id for look in personalization_context.saved_looks if look.look_id
        )

    scored = score_candidates(filtered, context, saved_look_ids=saved_look_ids)
    ranked = rank_candidates(scored)

    if not ranked:
        raise KnowledgeError("no hairstyle looks after filtering")

    explanations = build_explanations(ranked, context)
    confidence = derive_confidence(context, ranked)
    needs_more_data = context.completeness < 1.0

    by_id = {explanation.id: explanation for explanation in explanations}

    return HairstyleResult(
        appearance=AppearanceProfile(
            faceShape=appearance.faceShape,
            skinTone=appearance.skinTone,
            bodyType=appearance.bodyType,
            styleType=appearance.styleType,
            sourceRunId=appearance.sourceRunId,
        ),
        top=_as_recommendation(ranked[0], by_id[ranked[0].id]),
        alternatives=[
            _as_recommendation(candidate, by_id[candidate.id])
            for candidate in ranked[1:]
        ],
        confidence=confidence,
        needs_more_data=needs_more_data,
    )


# --- Grooming decision engine ------------------------------------------------

def build_grooming_context(
    appearance: AppearanceProfile,
    preferences: Optional[HairstylePreferences] = None,
    knowledge_version: str = "",
) -> DecisionContext:
    """Assemble the typed context the later stages read (stage 1 for grooming)."""
    return DecisionContext(
        appearance=appearance,
        preferences=preferences or HairstylePreferences(),
        completeness=_completeness(appearance),
        knowledge_version=knowledge_version,
    )


def generate_grooming_candidates(
    knowledge: KnowledgeSource, context: DecisionContext
) -> list[GroomingRecommendation]:
    """Retrieve the candidate set from the knowledge source (stage 2 for grooming).

    The engine never hardcodes candidates (BA-11); the port's deprecated
    filtering (KN-3) already applies before the engine sees them.
    """
    candidates = knowledge.retrieve_grooming_looks()
    if not candidates:
        raise KnowledgeError("knowledge source returned no grooming looks")
    return candidates


def filter_grooming_candidates(
    candidates: list[GroomingRecommendation], context: DecisionContext
) -> list[GroomingRecommendation]:
    """Apply hard exclusion rules (stage 3 for grooming).

    Binary keep/drop and deterministic (BA-3): candidates whose id the user
    excluded are dropped; nothing is scored or reordered here.
    """
    excluded = context.preferences.excludedLookIds
    if not excluded:
        return list(candidates)
    return [look for look in candidates if look.id not in excluded]


def score_grooming_candidates(
    candidates: list[GroomingRecommendation],
    context: DecisionContext,
    saved_look_ids: frozenset[str] = frozenset(),
) -> list[ScoredCandidate]:
    """Compose weighted scoring signals per candidate (stage 4 for grooming).

    score = min(1.0, seed + face_shape_boost + preference_boost + saved_look_boost).
    The per-signal breakdown feeds the Explanation stage (truthful "why this").
    - preference_boost: +0.03 if look is in preferredLookIds (explicit user preference).
    - saved_look_boost: +0.03 if look appears in user's saved look history (derived behavior).
      Both boosts are independent and cumulative; a look saved AND preferred gets +0.06 total.
    If no saved look history is provided, behavior is identical to current (backward compatible).
    """
    face = _face_shape(context.appearance)
    preferred = context.preferences.preferredLookIds

    scored: list[ScoredCandidate] = []
    for look in candidates:
        face_boost = _GROOMING_BOOSTS.get(look.id, {}).get(face, 0.0)
        preference_boost = _PREFERENCE_BOOST if look.id in preferred else 0.0
        saved_look_boost = 0.03 if look.id in saved_look_ids else 0.0
        score = min(1.0, look.matchScore + face_boost + preference_boost + saved_look_boost)
        scored.append(
            ScoredCandidate(
                id=look.id,
                score=round(score, 2),
                signals={
                    "seed": look.matchScore,
                    "face_shape": face_boost,
                    "preference": preference_boost,
                    "saved_look": saved_look_boost,
                },
                look=look,  # type: ignore[assignment]  # GroomingRecommendation is compatible
            )
        )
    return scored


def rank_grooming_candidates(scored: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Order candidates by score, top pick first (stage 5 for grooming).

    Ordering-only: scores are never recomputed here. Ties keep catalog order
    (stable sort), so ranking is deterministic for deterministic inputs.
    """
    return sorted(scored, key=lambda candidate: candidate.score, reverse=True)


def build_grooming_explanations(
    ranked: list[ScoredCandidate], context: DecisionContext
) -> list[Explanation]:
    """Produce grounded human reasons for each ranked candidate (stage 6 for grooming).

    Reasons come verbatim from the validated catalog reason catalog and the
    score-signal breakdown — never invented, never LLM-authored structure.
    """
    face = _face_shape(context.appearance)
    explanations: list[Explanation] = []
    for candidate in ranked:
        face_reason = _face_match_reason(candidate, face)
        reasons = list(candidate.look.reasons)
        if face_reason and face_reason not in reasons:
            reasons = [face_reason] + reasons
        explanations.append(
            Explanation(
                id=candidate.id,
                title=candidate.look.name,
                summary=candidate.look.description,
                reasons=reasons,
            )
        )
    return explanations


def _face_match_reason(candidate: ScoredCandidate, face_shape: str) -> Optional[str]:
    boost = candidate.signals.get("face_shape", 0.0)
    if boost <= 0.0:
        return None
    return (
        f"Strongest match for your {face_shape} face shape "
        f"(+{boost:0.2f} face-shape fit)."
    )


def derive_grooming_confidence(
    context: DecisionContext, ranked: list[ScoredCandidate]
) -> float:
    """Derive the run-level confidence in [0, 1] (deterministic).

    50% data completeness + 50% top-pick decisiveness (how clearly the top
    beats the runner-up). Sparse grounding or a tight ranking lowers it
    without ever fabricating a result (AI-0, AI_INTEGRATION_ARCHITECTURE §8).
    """
    completeness = context.completeness
    if len(ranked) >= 2:
        gap = ranked[0].score - ranked[1].score
        decisiveness = min(1.0, max(0.0, gap / _DECISIVE_GAP))
    else:
        decisiveness = 1.0
    return round(0.5 * completeness + 0.5 * decisiveness, 2)


def _as_grooming_recommendation(
    candidate: ScoredCandidate, explanation: Optional[Explanation] = None
) -> GroomingRecommendation:
    reasons = (
        list(explanation.reasons)
        if explanation is not None
        else list(candidate.look.reasons)
    )
    return GroomingRecommendation(
        id=candidate.look.id,
        name=candidate.look.name,
        description=candidate.look.description,
        matchScore=candidate.score,
        reasons=reasons,
        stylingTips=candidate.look.stylingTips,
        maintenance=candidate.look.maintenance,
        bestFor=candidate.look.bestFor,
        icon=None,
    )


def recommend_grooming(
    knowledge: KnowledgeSource,
    appearance: AppearanceProfile,
    preferences: Optional[HairstylePreferences] = None,
    *,
    personalization_context: Optional[PersonalizationContext] = None,
) -> "GroomingResult":
    """Run the full grooming recommendation pipeline (thin orchestrator).

    The orchestrator knows the stage order and implements no stage logic —
    each stage is a small pure function above. Rules-first: the top pick
    matches the grooming catalog's best-for face shapes.

    If ``personalization_context`` is provided, the decision engine incorporates
    saved look history boost and preference signals from memory. When omitted,
    the engine functions exactly as before (backward compatible).
    """
    context = build_grooming_context(
        appearance,
        preferences,
        knowledge_version=getattr(knowledge, "knowledge_version", ""),
    )

    candidates = generate_grooming_candidates(knowledge, context)
    filtered = filter_grooming_candidates(candidates, context)

    # Extract saved look IDs from personalization context if available
    saved_look_ids = frozenset()
    if personalization_context is not None and personalization_context.saved_looks:
        saved_look_ids = frozenset(
            look.look_id for look in personalization_context.saved_looks if look.look_id
        )

    scored = score_grooming_candidates(filtered, context, saved_look_ids=saved_look_ids)
    ranked = rank_grooming_candidates(scored)

    if not ranked:
        raise KnowledgeError("no grooming looks after filtering")

    explanations = build_grooming_explanations(ranked, context)
    confidence = derive_grooming_confidence(context, ranked)
    needs_more_data = context.completeness < 1.0

    by_id = {explanation.id: explanation for explanation in explanations}

    return GroomingResult(
        appearance=AppearanceProfile(
            faceShape=appearance.faceShape,
            skinTone=appearance.skinTone,
            bodyType=appearance.bodyType,
            styleType=appearance.styleType,
            sourceRunId=appearance.sourceRunId,
        ),
        top=_as_grooming_recommendation(ranked[0], by_id[ranked[0].id]),
        alternatives=[
            _as_grooming_recommendation(candidate, by_id[candidate.id])
            for candidate in ranked[1:]
        ],
        confidence=confidence,
        needs_more_data=needs_more_data,
    )


# ---------------------------------------------------------------------------
# Grooming result type (mirrors HairstyleResult but for grooming)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroomingResult:
    """The immutable completed-run snapshot for grooming (TRX-5 `result`).

    ``confidence`` is the engine's derived run-level value in [0, 1]
    (`AI_DOMAIN_MODEL.md` §4.4: derived from the model run, never stored as
    truth); ``needs_more_data`` honestly signals a sparse grounding profile
    instead of fabricating one (AI-0).
    """

    appearance: AppearanceProfile
    top: GroomingRecommendation
    alternatives: list[GroomingRecommendation] = field(default_factory=list)
    confidence: float = 0.0
    needs_more_data: bool = False

    def to_snapshot(self) -> dict:
        return {
            "appearance": {
                "faceShape": self.appearance.faceShape,
                "skinTone": self.appearance.skinTone,
                "bodyType": self.appearance.bodyType,
                "styleType": self.appearance.styleType,
                "sourceRunId": self.appearance.sourceRunId,
            },
            "confidence": self.confidence,
            "needs_more_data": self.needs_more_data,
            "recommendations": {
                "top": _recommendation_to_grooming_snapshot(self.top),
                "alternatives": [
                    _recommendation_to_grooming_snapshot(a) for a in self.alternatives
                ],
            },
        }


def _recommendation_to_grooming_snapshot(rec: GroomingRecommendation) -> dict:
    return {
        "id": rec.id,
        "name": rec.name,
        "description": rec.description,
        "matchScore": rec.matchScore,
        "reasons": list(rec.reasons),
        "stylingTips": rec.stylingTips,
        "maintenance": rec.maintenance,
        "bestFor": rec.bestFor,
        "icon": rec.icon,
    }


# ---------------------------------------------------------------------------
# Clothing Intelligence Engine — deterministic rules (CL-0)
# Pure Python, no FastAPI, no SQLAlchemy, no HTTP — BA-3.
# Mirrors the grooming engine pattern: stage-by-stage pure functions,
# deterministic results from deterministic inputs, confidence derived
# from data completeness without fabricating inputs (AI-0).
# ---------------------------------------------------------------------------


from typing import Optional

from app.domain.value_objects import (
    ClothingIntelligence,
    ColorCharacteristics,
    MaterialCharacteristics,
    SeasonSuitability,
    Formality,
    StylingExplanation,
    CompatibleCategory,
    OccasionContext,
    WardrobeContext,
)


# ---------------------------------------------------------------------------
# Canonical mappings — reference data, not user-provided
# ---------------------------------------------------------------------------

# Natural material codes (from migration 0005 vocabularies)
_NATURAL_MATERIAL_CODES = frozenset({
    "cotton", "linen", "wool", "cashmere", "silk", "leather", "suede"
})

# Seasonal material mappings
_MATERIAL_SEASON_MAP: dict[str, set[str]] = {
    "spring": {"cotton", "linen"},
    "summer": {"cotton", "linen", "silk"},
    "fall": {"wool", "cashmere"},
    "winter": {"heavy_wool", "leather", "fleece"},
}

# Category formality mappings
_CATEGORY_FORMALITY: dict[str, dict[str, bool]] = {
    "tops": {"is_formal": False, "is_casual": True, "is_business": False},
    "bottoms": {"is_formal": False, "is_casual": True, "is_business": False},
    "outerwear": {"is_formal": False, "is_casual": True, "is_business": False},
    "footwear": {"is_formal": True, "is_casual": True, "is_business": False},
    "accessories": {"is_formal": True, "is_casual": True, "is_business": False},
}

# Category seasonal suitability
_CATEGORY_SEASON_MAP: dict[str, set[str]] = {
    "tops": {"spring", "summer", "fall", "winter"},
    "bottoms": {"spring", "summer", "fall", "winter"},
    "outerwear": {"spring", "fall", "winter"},
    "footwear": {"spring", "summer", "fall", "winter"},
    "accessories": {"spring", "summer", "fall", "winter"},
}

# Compatible category pairings
_COMPATIBLE_PAIRINGS: dict[str, list[str]] = {
    "tops": ["bottoms", "outerwear"],
    "bottoms": ["tops", "footwear"],
    "outerwear": ["tops", "bottoms"],
    "footwear": ["bottoms", "accessories"],
    "accessories": ["footwear", "tops"],
}

# Preferred occasion mappings per category
_CATEGORY_OCCASIONS: dict[str, set[str]] = {
    "tops": {"casual", "office", "date", "party"},
    "bottoms": {"casual", "office", "date"},
    "outerwear": {"casual", "party", "date"},
    "footwear": {"casual", "office", "travel"},
    "accessories": {"casual", "office", "date"},
}

# Neutral color codes
_NEUTRAL_COLOR_CODES = frozenset({"black", "white", "charcoal", "grey"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_neutral_color(color: str) -> bool:
    return color in _NEUTRAL_COLOR_CODES


def _is_natural_material(material: str) -> bool:
    return material in _NATURAL_MATERIAL_CODES


def _get_season_for_material(material: str) -> set[str]:
    result: set[str] = set()
    for season, materials in _MATERIAL_SEASON_MAP.items():
        if material in materials:
            result.add(season)
    return result


def _get_formality(category: str) -> Formality:
    base = _CATEGORY_FORMALITY.get(category, {"is_formal": False, "is_casual": True, "is_business": False})
    true_keys = [k for k, v in base.items() if v]
    rationale_map = {
        "is_formal": "Formal attire",
        "is_casual": "Casual attire",
        "is_business": "Business attire",
    }
    rationale = "; ".join(rationale_map[k] for k in true_keys) if true_keys else "Attire classification"
    return Formality(
        is_formal=base["is_formal"],
        is_casual=base["is_casual"],
        is_business=base["is_business"],
        rationale=rationale,
    )


def _get_compatible_categories(category: str) -> list[CompatibleCategory]:
    pairings = _COMPATIBLE_PAIRINGS.get(category, [])
    return [
        CompatibleCategory(category=pair, rationale=f"Pairs well with {category.title()} for coordinated outfits")
        for pair in pairings
    ]


def _get_suitable_occasions(category: str, preferred_occasions: list[str]) -> list[OccasionContext]:
    base_occasions = _CATEGORY_OCCASIONS.get(category, {"casual", "office", "date", "party", "travel"})
    result: list[OccasionContext] = []
    for occ in sorted(base_occasions):
        overlap = len(set([occ]) & set(preferred_occasions)) if preferred_occasions else 0
        confidence = round(
            min(1.0, (overlap / max(1, len(preferred_occasions))) + 0.3) if preferred_occasions else 0.3,
            2,
        )
        result.append(OccasionContext(
            occasion=occ,
            confidence=confidence,
            rationale=f"Suitable for {occ} occasions" + (f" — you have this in your preferences" if occ in preferred_occasions else ""),
        ))
    return result


def _build_explanation(intelligence: "ClothingIntelligence") -> StylingExplanation:
    parts: list[str] = []
    parts.append(f"Your {intelligence.item_category} in {intelligence.item_color}")
    if intelligence.material_characteristics.material and intelligence.material_characteristics.material != "unknown":
        nat = "natural" if _is_natural_material(intelligence.material_characteristics.material) else "material"
        parts.append(f"{intelligence.material_characteristics.material} ({nat} material)")
    else:
        parts.append("material not specified")
    if intelligence.season_suitability.rationale:
        parts.append(intelligence.season_suitability.rationale)
    parts.append(f"({intelligence.wardrobe_context.total_items} items in your wardrobe, {intelligence.wardrobe_context.favorite_count} favorites)")
    suitable_occasions = [o.occasion for o in intelligence.suitable_occasions if o.confidence > 0.4]
    if suitable_occasions:
        parts.append(f"Suitable for: {', '.join(suitable_occasions)}")
    if intelligence.confidence < 0.5:
        parts.append(f"(confidence: {intelligence.confidence:.0f}/1.0 — based on available data)")
    text = ". ".join(parts) + "."
    return StylingExplanation(text=text)


# ---------------------------------------------------------------------------
# Engine — single entry point
# ---------------------------------------------------------------------------

def compute_clothing_intelligence(
    item_category: str,
    item_color: str,
    item_material: Optional[str],
    item_is_favorite: bool,
    wardrobe_context: WardrobeContext,
    preferred_occasions: list[str],
) -> ClothingIntelligence:
    """Run the Clothing Intelligence engine — deterministic rules only.

    Produces a ClothingIntelligence result from existing WardrobeItem fields
    and user wardrobe context. No AI provider calls, no DB changes, no new
    endpoints. Confidence controls how strongly the explanation can claim
    something (per Step 6B §4).
    """
    # 1. Color characteristics
    is_neutral = _is_neutral_color(item_color)
    color_chars = ColorCharacteristics(
        item_color=item_color,
        is_neutral=is_neutral,
    )

    # 2. Material characteristics
    is_natural = _is_natural_material(item_material) if item_material else False
    material_chars = MaterialCharacteristics(
        material=item_material if item_material else "unknown",
        is_natural=is_natural,
        is_seasonal=bool(_get_season_for_material(item_material) if item_material else set()),
    )

    # 3. Season suitability
    cat_seasons = _CATEGORY_SEASON_MAP.get(item_category, set())
    mat_seasons = _get_season_for_material(item_material) if item_material else set()
    all_seasons = cat_seasons | mat_seasons

    season = SeasonSuitability(
        suitable_for_spring="spring" in all_seasons,
        suitable_for_summer="summer" in all_seasons,
        suitable_for_fall="fall" in all_seasons,
        suitable_for_winter="winter" in all_seasons,
        rationale="Baseline seasonal mapping per category and material",
    )

    # 4. Formality
    formality = _get_formality(item_category)

    # 5. Compatible categories
    compatible = _get_compatible_categories(item_category)

    # 6. Suitable occasions
    occasions = _get_suitable_occasions(item_category, preferred_occasions)

    # 7. Confidence calculation
    has_all_fields = item_material is not None and item_color and item_category
    has_preferences = len(preferred_occasions) > 0
    is_fav = item_is_favorite

    confidence = round(
        0.4 * (1.0 if has_all_fields else 0.5) +
        0.3 * (1.0 if has_preferences else 0.3) +
        0.3 * (1.0 if is_fav else 0.2),
        2,
    )

    # 8. Explanation
    explanation = _build_explanation(ClothingIntelligence(
        item_id="",
        item_category=item_category,
        item_color=item_color,
        item_is_favorite=item_is_favorite,
        wardrobe_context=wardrobe_context,
        color_characteristics=color_chars,
        material_characteristics=material_chars,
        season_suitability=season,
        formality=formality,
        compatible_categories=compatible,
        suitable_occasions=occasions,
        confidence=confidence,
        explanation=StylingExplanation(text=""),
    ))

    # 9. Build the result
    result = ClothingIntelligence(
        item_id="",
        item_category=item_category,
        item_color=item_color,
        item_is_favorite=item_is_favorite,
        wardrobe_context=wardrobe_context,
        color_characteristics=color_chars,
        material_characteristics=material_chars,
        season_suitability=season,
        formality=formality,
        compatible_categories=compatible,
        suitable_occasions=occasions,
        confidence=confidence,
        explanation=explanation,
    )

    return result


def _build_explanation_clothing_intelligence(
    item_category: str,
    item_color: str,
    item_material: Optional[str],
    item_is_favorite: bool,
    wardrobe_context: WardrobeContext,
    preferred_occasions: list[str],
    confidence: float,
) -> StylingExplanation:
    """Build a human-readable explanation from the intelligence result."""
    parts: list[str] = []
    parts.append(f"Your {item_category} in {item_color}")
    if item_material and item_material != "unknown":
        nat = "natural" if _is_natural_material(item_material) else "material"
        parts.append(f"{item_material} ({nat} material)")
    else:
        parts.append("material not specified")
    if wardrobe_context.season_suitability.rationale:
        parts.append(wardrobe_context.season_suitability.rationale)
    parts.append(f"({wardrobe_context.total_items} items in your wardrobe, {wardrobe_context.favorite_count} favorites)")
    suitable_occasions = [o.occasion for o in _get_suitable_occasions(item_category, preferred_occasions) if o.confidence > 0.4]
    if suitable_occasions:
        parts.append(f"Suitable for: {', '.join(suitable_occasions)}")
    if confidence < 0.5:
        parts.append(f"(confidence: {confidence:.0f}/1.0 — based on available data)")
    text = ". ".join(parts) + "."
    return StylingExplanation(text=text)


# ---------------------------------------------------------------------------
# Exported engine function
# ---------------------------------------------------------------------------

__all__ = [
    "compute_clothing_intelligence",
    "_build_explanation_clothing_intelligence",
    "compute_outfit_intelligence",
]


# ---------------------------------------------------------------------------
# Outfit Intelligence — deterministic rules (CL-1)
# Builds on ClothingIntelligence from Steps 6A-6C, adding outfit-level
# assessment: category pairing, color harmony, seasonal consistency,
# formality balance, favorite boost, occasion handling, category coverage,
# sparse wardrobe handling, conflicts, confidence, confidence level,
# data availability, and explanation.
# ---------------------------------------------------------------------------


def compute_outfit_intelligence(
    clothing_intelligence: ClothingIntelligence,
    item_color: str,
    item_material: Optional[str],
    item_is_favorite: bool,
    wardrobe_context: WardrobeContext,
    preferred_occasions: list[str],
) -> OutfitIntelligence:
    """Run the Outfit Intelligence engine — deterministic rules only.

    Builds on the ClothingIntelligence result from Steps 6A-6C, adding
    outfit-level assessment. No AI provider calls, no DB changes, no new
    endpoints. Confidence follows STEP 7A exactly.

    Confidence formula (STEP 7A):
      base = 0.5
      + category coverage adjustment
      + favorite adjustment
      - missing-category penalty
      - seasonal conflict penalty
      - color conflict penalty
      + seasonal consistency / color harmony bonuses
      then clamp 0.0–1.0
      then map to strong / reasonable / insufficient
    """
    from app.domain.value_objects import (
        ClothingIntelligence,
        ColorCharacteristics,
        MaterialCharacteristics,
        OutfitHarmony,
        OutfitFormalityBalance,
        OutfitCoverage,
        OutfitConflict,
        OutfitConfidenceLevel,
        OutfitIntelligence,
        OutfitComposition,
        SeasonSuitability,
        Formality,
        StylingExplanation,
        CompatibleCategory,
        OccasionContext,
        WardrobeContext,
    )

    # ------------------------------------------------------------------
    # 1. Reuse pre-computed ClothingIntelligence (STEP 7C)
    # ------------------------------------------------------------------
    clothing_result = clothing_intelligence
    item_category = clothing_result.item_category

    # ------------------------------------------------------------------
    # 2. Category pairing (compatible categories from the item's category)
    # ------------------------------------------------------------------
    compatible = _get_compatible_categories(item_category)

    # ------------------------------------------------------------------
    # 3. Suitable occasions (from ClothingIntelligence + preference blending)
    # ------------------------------------------------------------------
    occasions = _get_suitable_occasions(item_category, preferred_occasions)

    # ------------------------------------------------------------------
    # 4. Color harmony assessment
    # ------------------------------------------------------------------
    is_neutral = item_color in _NEUTRAL_COLOR_CODES
    mat_is_natural = (
        _is_natural_material(item_material) if item_material else False
    )
    # Two items are harmonious if both are neutral, both are natural in
    similar_neutral = is_neutral and mat_is_natural
    # If we have a material and it's natural + color is neutral -> harmonious
    # If both colors are neutral -> harmonious
    # Simple heuristic: harmonious when color is neutral OR material is natural
    if is_neutral or mat_is_natural:
        harmony_is_harmonious = True
        harmony_rationale = "Neutral color and natural material promote harmony"
        harmony_accent_color = item_color
    else:
        harmony_is_harmonious = False
        harmony_rationale = "Bright color with synthetic material — consider accent coordination"
        harmony_accent_color = item_color

    harmony = OutfitHarmony(
        is_harmonious=harmony_is_harmonious,
        rationale=harmony_rationale,
        accent_color=harmony_accent_color,
    )

    # ------------------------------------------------------------------
    # 5. Formality balance assessment
    # ------------------------------------------------------------------
    cat_formality = _CATEGORY_FORMALITY.get(
        item_category, {"is_formal": False, "is_casual": True, "is_business": False}
    )
    true_keys = [k for k, v in cat_formality.items() if v]
    formality_desc = "; ".join(
        ["Formal attire" if k == "is_formal" else "Casual attire" if k == "is_casual" else "Business attire" for k in true_keys]
    ) if true_keys else "Attire classification"
    is_balanced = len(true_keys) <= 1  # single focus (formal OR casual) is balanced
    formality_balance = OutfitFormalityBalance(
        is_balanced=is_balanced,
        formality_desc=formality_desc,
        items=[item_category],
    )

    # ------------------------------------------------------------------
    # 6. Outfit coverage (category coverage + sparse wardrobe handling)
    # ------------------------------------------------------------------
    all_categories = {
        "tops", "bottoms", "outerwear", "footwear", "accessories"
    }
    item_categories = {item_category}
    covered_categories = [cat for cat in all_categories if cat in item_categories]
    missing_categories = [cat for cat in all_categories if cat not in item_categories]

    total_wardrobe_categories = len(wardrobe_context.items_per_category)
    wardrobe_size = wardrobe_context.total_items
    # Coverage ratio: fraction of standard wardrobe categories the item belongs to
    # plus a bonus for having a fuller wardrobe
    if wardrobe_size >= 20:
        coverage_ratio = min(1.0, len(covered_categories) / 5.0 + 0.1 * (wardrobe_size / 20.0))
    else:
        coverage_ratio = len(covered_categories) / 5.0

    # Sparse wardrobe: <3 items is the sparse/minimal wardrobe condition (STEP 7A)
    is_sparse = wardrobe_size < 3
    data_availability = "sparse" if is_sparse else ("partial" if wardrobe_size < 20 else "full")

    coverage = OutfitCoverage(
        covered_categories=covered_categories,
        missing_categories=missing_categories,
        coverage_ratio=round(coverage_ratio, 2),
    )

    # ------------------------------------------------------------------
    # 7. Conflict detection
    # ------------------------------------------------------------------
    conflicts: list[OutfitConflict] = []

    # Color conflict: if the item color is bright and material is synthetic
    if not is_neutral and not mat_is_natural:
        conflicts.append(
            OutfitConflict(
                type="color_conflict",
                severity="moderate",
                description=f"{item_color} with synthetic material may not coordinate easily",
            )
        )

    # Seasonal conflict: check if material season conflicts with item category season
    cat_seasons = _CATEGORY_SEASON_MAP.get(item_category, set())
    mat_seasons = _get_season_for_material(item_material) if item_material else set()
    conflict_seasons = cat_seasons & mat_seasons  # overlap is fine, conflict is opposite
    # Actually, conflict is when the material season is NOT in the category seasons
    if item_material and not (mat_seasons & cat_seasons):
        # Material season doesn't match category seasons at all
        conflicts.append(
            OutfitConflict(
                type="seasonal_conflict",
                severity="mild",
                description=f"{item_material} may not be optimal for {item_category} season",
            )
        )

    # Formality mismatch: if item is in a category that strongly leans one way
    # and we have strong formality signals
    if not is_balanced and len(conflicts) < 2:
        conflicts.append(
            OutfitConflict(
                type="formality_mismatch",
                severity="mild",
                description=f"{item_category} tends toward {formality_desc.lower()}",
            )
        )

    # ------------------------------------------------------------------
    # 8. Confidence calculation (STEP 7A exactly)
    # ------------------------------------------------------------------
    # STEP 7A confidence formula:
    #   base = 0.5
    #   + category coverage adjustment
    #   + favorite adjustment
    #   - missing-category penalty
    #   - seasonal conflict penalty
    #   - color conflict penalty
    #   + seasonal consistency / color harmony bonuses
    #   clamp 0.0–1.0
    #   map to strong / reasonable / insufficient

    has_all_fields = item_material is not None and item_color and item_category
    has_preferences = len(preferred_occasions) > 0
    is_fav = item_is_favorite

    # Category coverage adjustment: full coverage = +0.1, partial = +0.05, sparse = 0
    if coverage_ratio >= 1.0:
        coverage_adjustment = 0.1
    elif coverage_ratio >= 0.5:
        coverage_adjustment = 0.05
    else:
        coverage_adjustment = 0.0

    # Favorite adjustment
    fav_adjustment = 0.05 if is_fav else 0.0

    # Missing-category penalty: penalize if categories are missing
    missing_penalty = 0.0 if coverage_ratio >= 1.0 else (-0.1 if coverage_ratio < 0.3 else -0.05)

    # Seasonal conflict penalty
    seasonal_conflict_penalty = -0.05 if conflicts else 0.0

    # Color conflict penalty
    color_conflict_penalty = -0.05 if any(c.type == "color_conflict" for c in conflicts) else 0.0

    # Seasonal consistency / color harmony bonuses
    harmony_bonus = 0.05 if harmony_is_harmonious else 0.0
    consistency_bonus = 0.05 if is_balanced else 0.0

    # Base computation
    confidence_raw = (
        0.5  # base
        + coverage_adjustment
        + fav_adjustment
        + missing_penalty
        + seasonal_conflict_penalty
        + color_conflict_penalty
        + harmony_bonus
        + consistency_bonus
    )

    # Clamp 0.0–1.0
    confidence = max(0.0, min(1.0, round(confidence_raw, 2)))

    # Map to confidence level (STEP 7A exactly)
    if confidence >= 0.7:
        level = "strong"
    elif confidence >= 0.3:
        level = "reasonable"
    else:
        level = "insufficient"

    confidence_level = OutfitConfidenceLevel(
        level=level,
        range_start=0.0 if level == "insufficient" else (0.5 if level == "reasonable" else 0.8),
        range_end=0.5 if level == "insufficient" else (0.8 if level == "reasonable" else 1.0),
    )

    # ------------------------------------------------------------------
    # 9. Explanation building
    # ------------------------------------------------------------------
    explanation_parts: list[str] = []
    explanation_parts.append(f"Your {item_category} in {item_color}")
    if item_material and item_material != "unknown":
        nat = "natural" if _is_natural_material(item_material) else "material"
        explanation_parts.append(f"{item_material} ({nat} material)")
    else:
        explanation_parts.append("material not specified")
    if clothing_result.season_suitability.rationale:
        explanation_parts.append(clothing_result.season_suitability.rationale)
    explanation_parts.append(
        f"({wardrobe_context.total_items} items in your wardrobe, {wardrobe_context.favorite_count} favorites)"
    )
    suitable_occasions_list = [o.occasion for o in occasions if o.confidence > 0.4]
    if suitable_occasions_list:
        explanation_parts.append(f"Suitable for: {', '.join(suitable_occasions_list)}")
    if confidence < 0.5:
        explanation_parts.append(f"(confidence: {confidence:.0f}/1.0 — based on available data)")
    if conflicts:
        conflict_descs = [c.description for c in conflicts]
        explanation_parts.append(f"Note: {'; '.join(conflict_descs)}")
    explanation_text = ". ".join(explanation_parts) + "."

    explanation = StylingExplanation(text=explanation_text)

    # ------------------------------------------------------------------
    # 10. Build and return the result
    # ------------------------------------------------------------------
    result = OutfitIntelligence(
        item_id="",
        item_category=item_category,
        item_color=item_color,
        item_is_favorite=item_is_favorite,
        wardrobe_context=wardrobe_context,
        clothing_intelligence=clothing_result,
        compatible_categories=compatible,
        suitable_occasions=occasions,
        color_harmony=harmony,
        formality_balance=formality_balance,
        outfit_coverage=coverage,
        conflicts=conflicts,
        confidence=confidence,
        confidence_level=confidence_level,
        data_availability=data_availability,
        explanation=explanation,
        selected_item_ids=[],  # will be populated by Assistant engine
        outfit_composition=OutfitComposition(top_ids=[], bottom_ids=[], outerwear_ids=[], footwear_ids=[], accessory_ids=[]),
    )

    return result
