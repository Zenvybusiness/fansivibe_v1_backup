"""Fashion reasoning API schemas (Phase 3AJ).

Wire contract for ``POST /v1/reasoning``. Preserves the typed domain
reasoning structure without leaking internal execution details, raw
model JSON, or provider-specific envelopes.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ReasoningContextSchema(BaseModel):
    """Optional contextual constraints for reasoning."""

    occasion: Optional[str] = Field(None, max_length=100, description="Occasion name (e.g. casual, office)")
    climate: Optional[str] = Field(None, max_length=100, description="Climate condition (e.g. warm, cold)")
    region: Optional[str] = Field(None, max_length=100, description="Cultural / regional styling context")
    style_preference: Optional[str] = Field(None, max_length=100, description="Style preference")
    wardrobe_refs: List[str] = Field(default_factory=list, max_length=20, description="Referenced wardrobe item IDs")
    budget: Optional[str] = Field(None, max_length=100, description="Budget constraint")
    fit_preference: Optional[str] = Field(None, max_length=100, description="Fit preference (e.g. slim, oversized)")


class FashionReasoningRequest(BaseModel):
    """Request payload for ``POST /v1/reasoning``."""

    query: str = Field(..., min_length=1, max_length=500, description="Fashion domain reasoning query (max 500 chars)")
    intent: Optional[str] = Field(
        None,
        max_length=50,
        description="Optional intent: explain, identify, compare, style, match, analyze. Inferred if omitted.",
    )
    context: Optional[ReasoningContextSchema] = Field(
        None, description="Optional structured styling context"
    )
    max_conclusions: Optional[int] = Field(
        default=3, ge=1, le=5, description="Maximum number of conclusions to derive (1-5)"
    )
    evidence_only: Optional[bool] = Field(
        default=True, description="Strictly ground answers only in retrieved corpus evidence"
    )


class ReasoningVersionsSchema(BaseModel):
    """Authoritative version pins matching the reasoning contract."""

    ffo_version: str
    corpus_digest: str
    evidence_schema: str
    reasoning_contract_version: str


class ReasoningConclusionSchema(BaseModel):
    """One evidence-grounded conclusion."""

    statement: str = Field(..., description="The verified conclusion statement")
    evidence_ids: List[str] = Field(..., description="Corpus document IDs cited in support")
    ffo_refs: List[str] = Field(
        default_factory=list, description="Validated FFO ontology entity references"
    )
    reasoning_note: str = Field(
        default="", description="Optional reasoning explanation or derivation trace"
    )
    standing: str = Field(
        default="supported", description="Epistemic standing: supported, uncertain, or contested"
    )


class FashionReasoningResponse(BaseModel):
    """Structured reasoning response from ``POST /v1/reasoning``."""

    answer: str = Field(..., description="Natural language synthesis answering the user query")
    conclusions: List[ReasoningConclusionSchema] = Field(
        default_factory=list, description="Admitted, evidence-backed conclusions"
    )
    uncertainties: List[str] = Field(
        default_factory=list, description="Explicit uncertainties identified in the reasoning chain"
    )
    missing_evidence: List[str] = Field(
        default_factory=list, description="Information missing from the evidence pack"
    )
    contradictions: List[str] = Field(
        default_factory=list, description="Contradictions between evidence items"
    )
    confidence: str = Field(
        ..., description="Categorical confidence: high, medium, low, or unknown"
    )
    unsupported: bool = Field(
        default=False, description="True when query is out of scope / unsupported by the ontology"
    )
    versions: ReasoningVersionsSchema = Field(
        ..., description="Authoritative version pins verified against input"
    )
