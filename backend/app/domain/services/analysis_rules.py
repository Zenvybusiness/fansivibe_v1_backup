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

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.domain.ports.external import KnowledgeError, KnowledgeSource
from app.domain.value_objects import (
    AppearanceProfile,
    GroomingRecommendation,
    HairstylePreferences,
    HairstyleRecommendation,
    HairstyleResult,
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
    candidates: list[HairstyleRecommendation], context: DecisionContext
) -> list[ScoredCandidate]:
    """Compose weighted scoring signals per candidate (stage 4).

    score = min(1.0, seed + face_shape_boost + preference_boost). The
    per-signal breakdown feeds the Explanation stage (truthful "why this").
    """
    face = _face_shape(context.appearance)
    preferred = context.preferences.preferredLookIds

    scored: list[ScoredCandidate] = []
    for look in candidates:
        face_boost = _BOOSTS.get(look.id, {}).get(face, 0.0)
        preference_boost = _PREFERENCE_BOOST if look.id in preferred else 0.0
        score = min(1.0, look.matchScore + face_boost + preference_boost)
        scored.append(
            ScoredCandidate(
                id=look.id,
                score=round(score, 2),
                signals={
                    "seed": look.matchScore,
                    "face_shape": face_boost,
                    "preference": preference_boost,
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
) -> HairstyleResult:
    """Run the full hairstyle recommendation pipeline (thin orchestrator).

    The orchestrator knows the stage order and implements no stage logic —
    each stage is a small pure function above. Rules-first: the top pick
    matches the assistant's face-shape switch (`app/ai/tools.py:
    recommend_hairstyle`) — pompadour-first for round/square/rectangle,
    quiff-first otherwise.
    """
    context = build_context(
        appearance,
        preferences,
        knowledge_version=getattr(knowledge, "knowledge_version", ""),
    )

    candidates = generate_candidates(knowledge, context)
    filtered = filter_candidates(candidates, context)
    scored = score_candidates(filtered, context)
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
    candidates: list[GroomingRecommendation], context: DecisionContext
) -> list[ScoredCandidate]:
    """Compose weighted scoring signals per candidate (stage 4 for grooming).

    score = min(1.0, seed + face_shape_boost + preference_boost). The
    per-signal breakdown feeds the Explanation stage (truthful "why this").
    """
    face = _face_shape(context.appearance)
    preferred = context.preferences.preferredLookIds

    scored: list[ScoredCandidate] = []
    for look in candidates:
        face_boost = _GROOMING_BOOSTS.get(look.id, {}).get(face, 0.0)
        preference_boost = _PREFERENCE_BOOST if look.id in preferred else 0.0
        score = min(1.0, look.matchScore + face_boost + preference_boost)
        scored.append(
            ScoredCandidate(
                id=look.id,
                score=round(score, 2),
                signals={
                    "seed": look.matchScore,
                    "face_shape": face_boost,
                    "preference": preference_boost,
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
) -> "GroomingResult":
    """Run the full grooming recommendation pipeline (thin orchestrator).

    The orchestrator knows the stage order and implements no stage logic —
    each stage is a small pure function above. Rules-first: the top pick
    matches the grooming catalog's best-for face shapes.
    """
    context = build_grooming_context(
        appearance,
        preferences,
        knowledge_version=getattr(knowledge, "knowledge_version", ""),
    )

    candidates = generate_grooming_candidates(knowledge, context)
    filtered = filter_grooming_candidates(candidates, context)
    scored = score_grooming_candidates(filtered, context)
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
