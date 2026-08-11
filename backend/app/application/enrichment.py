"""Optional LLM wording enrichment for the hairstyle result (additive).

Rules-first output is always the deliverable (DE-0). When the self-hosted
LLM seam is reachable, only the natural-language *wording* of descriptions is
rewritten — never structure, scores, reasons, or ranking (BA-8, AI-0). Any
failure degrades to the deterministic wording; nothing about a provider ever
reaches the wire (C-8).
"""

from __future__ import annotations

from app.ai import llm_backend
from app.domain.value_objects import HairstyleRecommendation, HairstyleResult


def _enrich_description(rec: HairstyleRecommendation) -> HairstyleRecommendation:
    new_description = llm_backend.enrich_reply(
        "hairstyle",
        rec.description,
        context=f"Face shape: {rec.bestFor}. Suitability: {rec.description}",
    )
    if not new_description or new_description == rec.description:
        return rec
    return HairstyleRecommendation(
        id=rec.id,
        name=rec.name,
        description=new_description,
        matchScore=rec.matchScore,  # scores never change
        reasons=list(rec.reasons),  # grounded bullets never change
        stylingTips=rec.stylingTips,
        maintenance=rec.maintenance,
        bestFor=rec.bestFor,
    )


def enrich_hairstyle_result(result: HairstyleResult) -> HairstyleResult:
    """Return the result with LLM-rewritten description wording when available.

    When the LLM is unavailable (or any call fails), returns the result
    unchanged — the deterministic rules wording is the baseline.
    """
    if not llm_backend.is_available():
        return result
    try:
        return HairstyleResult(
            appearance=result.appearance,
            top=_enrich_description(result.top),
            alternatives=[_enrich_description(a) for a in result.alternatives],
        )
    except Exception:
        return result
