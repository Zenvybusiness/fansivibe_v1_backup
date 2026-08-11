"""Domain value objects for the hairstyle recommendation pipeline.

Pure Python (no FastAPI, no SQLAlchemy, no HTTP — BA-3). These mirror the
canonical wire DTOs (`FANSIVIBE_API_CONTRACT_V1.md` §4.2/§4.3 and
`hairstyle_mock_data.dart`) and are the typed structure the decision engine
produces and the API serializes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HairstyleRecommendation:
    """A single hairstyle recommendation (the `top` pick or an `alternative`).

    Mirrors `HairstyleRecommendation` in `hairstyle_mock_data.dart` and the
    wire DTO: ``id`` is the stable catalog look code (PR-3).
    """

    id: str
    name: str
    description: str
    matchScore: float
    reasons: list[str]
    stylingTips: str
    maintenance: str
    bestFor: str


@dataclass(frozen=True)
class AppearanceProfile:
    """The face attributes the ranking was grounded on (run-level snapshot).

    ``sourceRunId`` is the producing run (provenance, R-1).
    """

    faceShape: str
    skinTone: str = ""
    bodyType: str = ""
    styleType: str = ""
    sourceRunId: str = ""


@dataclass(frozen=True)
class HairstyleResult:
    """The immutable completed-run snapshot (TRX-5 `result`)."""

    appearance: AppearanceProfile
    top: HairstyleRecommendation
    alternatives: list[HairstyleRecommendation] = field(default_factory=list)

    def to_snapshot(self) -> dict:
        return {
            "appearance": {
                "faceShape": self.appearance.faceShape,
                "skinTone": self.appearance.skinTone,
                "bodyType": self.appearance.bodyType,
                "styleType": self.appearance.styleType,
                "sourceRunId": self.appearance.sourceRunId,
            },
            "recommendations": {
                "top": _recommendation_to_snapshot(self.top),
                "alternatives": [_recommendation_to_snapshot(a) for a in self.alternatives],
            },
        }


def _recommendation_to_snapshot(rec: HairstyleRecommendation) -> dict:
    return {
        "id": rec.id,
        "name": rec.name,
        "description": rec.description,
        "matchScore": rec.matchScore,
        "reasons": list(rec.reasons),
        "stylingTips": rec.stylingTips,
        "maintenance": rec.maintenance,
        "bestFor": rec.bestFor,
    }
