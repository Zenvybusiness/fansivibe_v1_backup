"""The hairstyle decision engine — rules-first, deterministic (DE-0).

Implements the engine stages from `DECISION_ENGINE_ARCHITECTURE.md` for the
hairstyle task only (no empty framework — per-task composition):

  1. ContextBuilder     — profile × knowledge
  2. CandidateGeneration — the hairstyle look catalog
  3. Scoring            — deterministic face-shape weights over the seed score
  4. Ranking            — top + alternatives
  5. Explanation        — grounded reasons + description from the catalog

The LLM (when wired) may only rewrite *wording* — never structure or scores
(BA-8, AI-0). Scores are capped at 1.0 and stay in [0, 1].
"""

from __future__ import annotations

from app.domain.ports.external import KnowledgeSource
from app.domain.value_objects import (
    AppearanceProfile,
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


def _score(look: HairstyleRecommendation, face_shape: str) -> float:
    boost = _BOOSTS.get(look.id, {}).get(face_shape, 0.0)
    return min(1.0, look.matchScore + boost)


def _as_scored(look: HairstyleRecommendation, score: float) -> HairstyleRecommendation:
    return HairstyleRecommendation(
        id=look.id,
        name=look.name,
        description=look.description,
        matchScore=round(score, 2),
        reasons=list(look.reasons),
        stylingTips=look.stylingTips,
        maintenance=look.maintenance,
        bestFor=look.bestFor,
    )


def recommend_hairstyle(
    knowledge: KnowledgeSource,
    appearance: AppearanceProfile,
) -> HairstyleResult:
    """Run the full hairstyle recommendation pipeline over the profile.

    Rules-first: the top pick matches the assistant's face-shape switch
    (`app/ai/tools.py:recommend_hairstyle`) — pompadour-first for
    round/square/rectangle, quiff-first otherwise.
    """
    face_shape = appearance.faceShape.strip().lower() if appearance.faceShape else "oval"

    scored = [
        _as_scored(look, _score(look, face_shape))
        for look in knowledge.list_hairstyle_looks()
    ]
    scored.sort(key=lambda r: r.matchScore, reverse=True)

    if not scored:
        raise ValueError("knowledge source returned no hairstyle looks")

    top = scored[0]
    alternatives = scored[1:]

    return HairstyleResult(
        appearance=AppearanceProfile(
            faceShape=appearance.faceShape,
            skinTone=appearance.skinTone,
            bodyType=appearance.bodyType,
            styleType=appearance.styleType,
            sourceRunId=appearance.sourceRunId,
        ),
        top=top,
        alternatives=alternatives,
    )
