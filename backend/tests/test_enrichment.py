"""Unit tests for the optional LLM wording enrichment.

No database and no live LLM — `llm_backend` is monkeypatched. The key honesty
invariant: rules-only output is identical when the LLM is unavailable, and a
provider call can only rewrite wording (never scores/reasons/ranking).
"""

import app.ai.llm_backend as llm_backend
from app.application.enrichment import enrich_hairstyle_result
from app.domain.services.analysis_rules import recommend_hairstyle
from app.domain.value_objects import AppearanceProfile
from app.infrastructure.external.knowledge import CatalogKnowledgeSource


def _result():
    return recommend_hairstyle(
        CatalogKnowledgeSource(), AppearanceProfile(faceShape="Oval")
    )


def test_rules_only_output_unchanged_when_llm_disabled(monkeypatch):
    monkeypatch.setattr(llm_backend, "is_available", lambda: False)
    result = _result()
    enriched = enrich_hairstyle_result(result)
    assert enriched.top == result.top
    assert enriched.alternatives == result.alternatives
    assert enriched.appearance == result.appearance


def test_llm_rewrites_wording_only(monkeypatch):
    monkeypatch.setattr(llm_backend, "is_available", lambda: True)
    monkeypatch.setattr(
        llm_backend,
        "enrich_reply",
        lambda intent, base, context: "A freshly worded description.",
    )
    result = _result()
    enriched = enrich_hairstyle_result(result)

    assert enriched.top.description == "A freshly worded description."
    assert enriched.top.id == result.top.id
    assert enriched.top.matchScore == result.top.matchScore
    assert enriched.top.reasons == result.top.reasons
    assert [a.matchScore for a in enriched.alternatives] == [
        a.matchScore for a in result.alternatives
    ]


def test_enrichment_failure_degrades_to_rules(monkeypatch):
    monkeypatch.setattr(llm_backend, "is_available", lambda: True)

    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm_backend, "enrich_reply", boom)
    result = _result()
    enriched = enrich_hairstyle_result(result)
    assert enriched.top == result.top
