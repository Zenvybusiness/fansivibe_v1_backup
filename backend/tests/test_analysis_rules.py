"""Unit tests for the hairstyle decision engine (rules-first).

These never touch a database — they use the in-code catalog knowledge source.
"""

import pytest

from app.domain.services.analysis_rules import recommend_hairstyle
from app.domain.value_objects import AppearanceProfile
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

KNOWLEDGE = CatalogKnowledgeSource()


def _result(face_shape: str, **extra):
    return recommend_hairstyle(
        KNOWLEDGE,
        AppearanceProfile(faceShape=face_shape, **extra),
    )


def test_candidates_come_from_catalog():
    result = _result("Oval")
    all_ids = [result.top.id] + [a.id for a in result.alternatives]
    assert sorted(all_ids) == [
        "brushed_up_undercut",
        "classic_pompadour",
        "side_part",
        "textured_quiff",
    ]


def test_oval_ranks_quiff_first():
    result = _result("Oval")
    assert result.top.id == "textured_quiff"
    assert result.alternatives[0].id == "classic_pompadour"


def test_round_ranks_pompadour_first():
    result = _result("Round")
    assert result.top.id == "classic_pompadour"


def test_square_ranks_pompadour_first():
    result = _result("Square")
    assert result.top.id == "classic_pompadour"


def test_scores_are_bounded_and_descending():
    result = _result("Heart")
    scores = [result.top.matchScore] + [a.matchScore for a in result.alternatives]
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_appearance_profile_is_carried_with_source_run():
    result = _result("Oval", skinTone="Warm Medium", styleType="Modern Classic", sourceRunId="abc-123")
    assert result.appearance.skinTone == "Warm Medium"
    assert result.appearance.styleType == "Modern Classic"
    assert result.appearance.sourceRunId == "abc-123"


def test_defaults_to_oval_when_shape_missing():
    result = recommend_hairstyle(KNOWLEDGE, AppearanceProfile(faceShape=""))
    assert result.top.id == "textured_quiff"


def test_reasons_are_grounded_in_catalog():
    result = _result("Oval")
    assert result.top.reasons  # never empty
    assert any("quiff" in r.lower() or "volume" in r.lower() for r in result.top.reasons)


def test_snapshot_shape_matches_wire():
    result = _result("Oval")
    snapshot = result.to_snapshot()
    assert set(snapshot.keys()) == {"appearance", "recommendations"}
    assert set(snapshot["appearance"].keys()) == {
        "faceShape",
        "skinTone",
        "bodyType",
        "styleType",
        "sourceRunId",
    }
    recs = snapshot["recommendations"]
    assert set(recs.keys()) == {"top", "alternatives"}
    assert set(recs["top"].keys()) == {
        "id",
        "name",
        "description",
        "matchScore",
        "reasons",
        "stylingTips",
        "maintenance",
        "bestFor",
    }


def test_empty_knowledge_raises():
    class EmptySource:
        def list_hairstyle_looks(self):
            return []

    with pytest.raises(ValueError):
        recommend_hairstyle(EmptySource(), AppearanceProfile(faceShape="Oval"))
