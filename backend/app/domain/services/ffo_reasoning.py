"""Fashion reasoning contracts — domain data-model layer (Phase 3A).

Boundary: FashionReasoningInput → FashionReasoner PORT → FashionReasoningOutput.
No prompts, no model calls, no tuning — pure typed structures + structural
validation. A future adapter consumes inputs and produces outputs; nothing
here knows about any model.

Four sections stay distinct (never merged into a prompt string):
  A. request   — query, intent, context, FFO entity mentions
  B. evidence  — Phase 2C/2D items, verbatim (provenance included)
  C. constraints — evidence_only, max_conclusions
  D. task      — output requirements + version pins

Grounding semantics (what an output may claim):
  supported     — ≥1 conclusion, each standing on cited evidence ids
  insufficient  — no conclusions + non-empty missing_evidence
  contested     — ≥1 contested conclusion + non-empty contradictions
  uncertain     — conclusions with standing uncertain (evidence thin)
  unsupported   — unsupported=True + empty conclusions (out of scope)

Confidence is categorical (high/medium/low/unknown) — deliberately NOT a
probability: the architecture has no calibration support.

Version pins (input ↔ output must match exactly or validation fails):
  ffo_version, corpus_digest, evidence_schema, reasoning contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

REASONING_CONTRACT_VERSION = "2.0"
EVIDENCE_SCHEMA_VERSION = "evidence-pack/1"

SUPPORTED_INTENTS = ("explain", "identify", "compare", "style", "match", "analyze")
DEFERRED_INTENTS = {"recommend": "overlaps outfit generation; needs a product decision"}

STANDINGS = ("supported", "uncertain", "contested")
CONFIDENCES = ("high", "medium", "low", "unknown")
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class ReasoningContractError(ValueError):
    """Structural contract violation (deterministic messages, no user data)."""


def corpus_digest(versions: dict, ffo_version: str) -> str:
    """Authoritative corpus digest (Phase 3F-B) — the ONLY digest algorithm.

    Deterministic SHA-256 (stdlib `hashlib`) over canonical JSON of
    sorted `[{doc_id, version}]` plus `ffo_version`::

        {"corpus": [{"doc_id": k, "version": v}, ...sorted by doc_id...],
         "ffo_version": ffo_version}

    serialized with `sort_keys=True, separators=(",", ":")`. Computed
    server-side from validated corpus state; a model echo is verified by
    exact full-hex comparison against the server value, never trusted.
    """
    if (
        not isinstance(versions, dict)
        or not isinstance(ffo_version, str)
        or not ffo_version.strip()
        or any(
            not isinstance(k, str) or isinstance(v, bool)
            or not isinstance(v, int) or v < 1
            for k, v in versions.items()
        )
    ):
        raise ReasoningContractError(
            "versions: digest needs {doc ids: versions >= 1} + non-empty ffo_version"
        )
    canonical = json.dumps(
        {
            "corpus": [
                {"doc_id": k, "version": versions[k]} for k in sorted(versions)
            ],
            "ffo_version": ffo_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _need_str(data: dict, key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ReasoningContractError(f"{where}: '{key}' must be a non-empty string")
    return value


def _need_str_tuple(data: dict, key: str, where: str) -> tuple:
    value = data.get(key, ())
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ReasoningContractError(f"{where}: '{key}' must be a list of strings")
    items = tuple(value)
    if any(not isinstance(v, str) or not v.strip() for v in items):
        raise ReasoningContractError(f"{where}: '{key}' must be a list of strings")
    return items


@dataclass(frozen=True)
class ReasoningRequest:
    """Section A (core): what was asked + the controlled intent."""

    query: str
    intent: str

    def to_dict(self) -> dict:
        return {"query": self.query, "intent": self.intent}


@dataclass(frozen=True)
class ReasoningContext:
    """Section A (optional): structured context for future use.

    All fields optional. wardrobe_refs are wardrobe-item ID references
    (resolution happens later — no persistence here). budget is free text
    (no currency math in this contract). Fields without FFO/project
    vocabulary stay optional by design.
    """

    occasion: str | None = None
    climate: str | None = None
    region: str | None = None
    style_preference: str | None = None
    wardrobe_refs: tuple = ()
    budget: str | None = None
    fit_preference: str | None = None

    def to_dict(self) -> dict:
        return {
            "occasion": self.occasion,
            "climate": self.climate,
            "region": self.region,
            "style_preference": self.style_preference,
            "wardrobe_refs": list(self.wardrobe_refs),
            "budget": self.budget,
            "fit_preference": self.fit_preference,
        }


@dataclass(frozen=True)
class ReasoningConstraints:
    """Section C: system constraints on the future reasoning step."""

    evidence_only: bool = True
    max_conclusions: int = 3

    def to_dict(self) -> dict:
        return {"evidence_only": self.evidence_only, "max_conclusions": self.max_conclusions}


@dataclass(frozen=True)
class OutputRequirements:
    """Section D: what the output must contain."""

    include_reasoning_notes: bool = True

    def to_dict(self) -> dict:
        return {"include_reasoning_notes": self.include_reasoning_notes}


@dataclass(frozen=True)
class ReasoningVersions:
    """Section D: version pins; output pins must equal input pins.

    Phase 3F-B: the 76-entry `corpus_versions` map is replaced by
    `corpus_digest` (see `corpus_digest`) — one short echo instead of a
    verbatim map. `evidence_schema` stays `evidence-pack/1` (EvidencePack
    itself is unchanged).
    """

    ffo_version: str
    corpus_digest: str
    evidence_schema: str
    reasoning_contract_version: str

    def to_dict(self) -> dict:
        return {
            "ffo_version": self.ffo_version,
            "corpus_digest": self.corpus_digest,
            "evidence_schema": self.evidence_schema,
            "reasoning_contract_version": self.reasoning_contract_version,
        }


@dataclass(frozen=True)
class ReasoningEvidence:
    """Section B: one evidence item, verbatim from Phase 2C/2D structures.

    Conclusions cite these by doc_id; provenance travels untouched so a
    future layer can show WHY each item was retrieved (reason +
    lexical/semantic scores) without re-reading the corpus.

    Phase 3D adds optional `content`: validated knowledge from the source
    corpus document (see `corpus.evidence_content`), always carrying its
    doc_id so belonging is checkable. Absent content parses fine
    (backward compatible); present-but-mismatched content is rejected.
    """

    doc_id: str
    doc_type: str
    label: str
    reason: str
    lexical_score: int | float | None
    semantic_score: float | None
    ffo_references: tuple
    provenance: dict
    confidence: float
    status: str
    content: dict = field(default_factory=dict)

    @classmethod
    def from_retrieval(cls, result) -> "ReasoningEvidence":
        """From a Phase 2C RetrievalResult (no semantic side)."""
        return cls(
            doc_id=result.doc_id,
            doc_type=result.doc_type,
            label=result.label,
            reason=result.reason,
            lexical_score=result.score,
            semantic_score=None,
            ffo_references=tuple(result.ffo_references),
            provenance=dict(result.provenance),
            confidence=float(result.confidence),
            status=result.status,
        )

    @classmethod
    def from_hybrid(cls, result) -> "ReasoningEvidence":
        """From a Phase 2D HybridResult (both signals where present)."""
        reason = result.lexical_reason or result.semantic_reason or "unscored"
        return cls(
            doc_id=result.doc_id,
            doc_type=result.doc_type,
            label=result.label,
            reason=reason,
            lexical_score=result.lexical_score,
            semantic_score=result.semantic_score,
            ffo_references=tuple(result.ffo_references),
            provenance=dict(result.provenance),
            confidence=float(result.confidence),
            status=result.status,
        )

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "label": self.label,
            "reason": self.reason,
            "lexical_score": self.lexical_score,
            "semantic_score": self.semantic_score,
            "ffo_references": list(self.ffo_references),
            "provenance": dict(self.provenance),
            "confidence": self.confidence,
            "status": self.status,
            "content": dict(self.content),
        }


@dataclass(frozen=True)
class FashionReasoningInput:
    """Full reasoning input: request + context + entities + evidence + C + D."""

    request: ReasoningRequest
    context: ReasoningContext = field(default_factory=ReasoningContext)
    entities: tuple = ()
    evidence: tuple = ()
    constraints: ReasoningConstraints = field(default_factory=ReasoningConstraints)
    requirements: OutputRequirements = field(default_factory=OutputRequirements)
    versions: ReasoningVersions | None = None

    def to_dict(self) -> dict:
        return {
            "request": self.request.to_dict(),
            "context": self.context.to_dict(),
            "entities": list(self.entities),
            "evidence": [e.to_dict() for e in self.evidence],
            "constraints": self.constraints.to_dict(),
            "requirements": self.requirements.to_dict(),
            "versions": self.versions.to_dict() if self.versions else None,
        }


@dataclass(frozen=True)
class ReasoningConclusion:
    """One evidence-backed conclusion; cites ≥1 input evidence doc_id."""

    statement: str
    evidence_ids: tuple
    ffo_refs: tuple = ()
    reasoning_note: str = ""
    standing: str = "supported"

    def to_dict(self) -> dict:
        return {
            "statement": self.statement,
            "evidence_ids": list(self.evidence_ids),
            "ffo_refs": list(self.ffo_refs),
            "reasoning_note": self.reasoning_note,
            "standing": self.standing,
        }


@dataclass(frozen=True)
class FashionReasoningOutput:
    """Full reasoning output; every conclusion traces to evidence doc_ids."""

    answer: str
    conclusions: tuple = ()
    uncertainties: tuple = ()
    missing_evidence: tuple = ()
    contradictions: tuple = ()
    confidence: str = "unknown"
    unsupported: bool = False
    versions: ReasoningVersions | None = None

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "conclusions": [c.to_dict() for c in self.conclusions],
            "uncertainties": list(self.uncertainties),
            "missing_evidence": list(self.missing_evidence),
            "contradictions": list(self.contradictions),
            "confidence": self.confidence,
            "unsupported": self.unsupported,
            "versions": self.versions.to_dict() if self.versions else None,
        }


def _parse_context(data: dict) -> ReasoningContext:
    if data is None:
        return ReasoningContext()
    if not isinstance(data, dict):
        raise ReasoningContractError("context: must be an object")
    fields = {}
    for key in (
        "occasion", "climate", "region", "style_preference", "budget", "fit_preference",
    ):
        value = data.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ReasoningContractError(f"context: '{key}' must be a non-empty string")
        fields[key] = value
    fields["wardrobe_refs"] = _need_str_tuple(data, "wardrobe_refs", "context")
    return ReasoningContext(**fields)


def _parse_versions(data: dict) -> ReasoningVersions:
    if not isinstance(data, dict):
        raise ReasoningContractError("versions: must be an object")
    ffo_version = _need_str(data, "ffo_version", "versions")
    if "corpus_versions" in data:
        raise ReasoningContractError(
            "versions: 'corpus_versions' was removed in contract 2.0 "
            "(use 'corpus_digest'; old inputs are rejected, never converted)"
        )
    digest = data.get("corpus_digest")
    if not isinstance(digest, str) or not _DIGEST_RE.match(digest):
        raise ReasoningContractError(
            "versions: 'corpus_digest' must be a full SHA-256 hex string"
        )
    evidence_schema = _need_str(data, "evidence_schema", "versions")
    contract = _need_str(data, "reasoning_contract_version", "versions")
    if contract != REASONING_CONTRACT_VERSION:
        raise ReasoningContractError(
            f"versions: contract '{contract}' != '{REASONING_CONTRACT_VERSION}'"
        )
    return ReasoningVersions(
        ffo_version=ffo_version,
        corpus_digest=digest,
        evidence_schema=evidence_schema,
        reasoning_contract_version=contract,
    )


def _parse_evidence(data: dict) -> tuple:
    items = data.get("evidence", ())
    if isinstance(items, str) or not isinstance(items, (list, tuple)):
        raise ReasoningContractError("evidence: must be a list")
    parsed = []
    for pos, raw in enumerate(items):
        where = f"evidence[{pos}]"
        if not isinstance(raw, dict):
            raise ReasoningContractError(f"{where}: must be an object")
        doc_id = _need_str(raw, "doc_id", where)
        provenance = raw.get("provenance")
        if not isinstance(provenance, dict) or not provenance.get("source"):
            raise ReasoningContractError(f"{where}: 'provenance.source' is required")
        confidence = provenance.get("confidence", 0.0)
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ReasoningContractError(f"{where}: 'provenance.confidence' must be a number")
        content = raw.get("content", {})
        if not isinstance(content, dict):
            raise ReasoningContractError(f"{where}: 'content' must be an object")
        if content and content.get("doc_id") != doc_id:
            raise ReasoningContractError(
                f"{where}: content does not belong to '{doc_id}'"
            )
        parsed.append(
            ReasoningEvidence(
                doc_id=doc_id,
                doc_type=raw.get("doc_type", ""),
                label=raw.get("label", doc_id),
                reason=raw.get("reason", "unscored"),
                lexical_score=raw.get("lexical_score"),
                semantic_score=raw.get("semantic_score"),
                ffo_references=tuple(raw.get("ffo_references", ())),
                provenance=dict(provenance),
                confidence=float(confidence),
                status=raw.get("status", ""),
                content=dict(content),
            )
        )
    return tuple(parsed)


def validate_input(data: dict) -> FashionReasoningInput:
    """Parse + validate a reasoning input dict; raises ReasoningContractError."""
    if not isinstance(data, dict):
        raise ReasoningContractError("input: must be an object")
    request = data.get("request")
    if not isinstance(request, dict):
        raise ReasoningContractError("request: must be an object")
    query = _need_str(request, "query", "request")
    intent = _need_str(request, "intent", "request")
    if intent in DEFERRED_INTENTS:
        raise ReasoningContractError(f"request: intent '{intent}' deferred ({DEFERRED_INTENTS[intent]})")
    if intent not in SUPPORTED_INTENTS:
        raise ReasoningContractError(
            f"request: intent '{intent}' must be one of {list(SUPPORTED_INTENTS)}"
        )
    versions = data.get("versions")
    if versions is None:
        raise ReasoningContractError("versions: required (no silent version mixing)")
    return FashionReasoningInput(
        request=ReasoningRequest(query=query, intent=intent),
        context=_parse_context(data.get("context")),
        entities=_need_str_tuple(data, "entities", "input"),
        evidence=_parse_evidence(data),
        constraints=ReasoningConstraints(
            evidence_only=bool(data.get("constraints", {}).get("evidence_only", True)),
            max_conclusions=_parse_max_conclusions(data.get("constraints", {})),
        ),
        requirements=OutputRequirements(
            include_reasoning_notes=bool(
                data.get("requirements", {}).get("include_reasoning_notes", True)
            )
        ),
        versions=_parse_versions(versions),
    )


def _parse_max_conclusions(data: dict) -> int:
    if not isinstance(data, dict):
        raise ReasoningContractError("constraints: must be an object")
    value = data.get("max_conclusions", 3)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ReasoningContractError("constraints: 'max_conclusions' must be >= 1")
    return value


def validate_output(data: dict, *, input: FashionReasoningInput) -> FashionReasoningOutput:
    """Parse + validate an output against its input (evidence ids, max, pins)."""
    if not isinstance(data, dict):
        raise ReasoningContractError("output: must be an object")
    answer = _need_str(data, "answer", "output")
    if data.get("confidence") not in CONFIDENCES:
        raise ReasoningContractError(
            f"output: 'confidence' must be one of {list(CONFIDENCES)} (categorical, not a probability)"
        )
    unsupported = data.get("unsupported", False)
    if not isinstance(unsupported, bool):
        raise ReasoningContractError("output: 'unsupported' must be a boolean")
    known_ids = {e.doc_id for e in input.evidence}
    conclusions = []
    for pos, raw in enumerate(data.get("conclusions", ())):
        where = f"conclusions[{pos}]"
        if not isinstance(raw, dict):
            raise ReasoningContractError(f"{where}: must be an object")
        statement = _need_str(raw, "statement", where)
        evidence_ids = _need_str_tuple(raw, "evidence_ids", where)
        if not evidence_ids:
            raise ReasoningContractError(f"{where}: 'evidence_ids' must be non-empty")
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ReasoningContractError(f"{where}: duplicate evidence references")
        unknown = [i for i in evidence_ids if i not in known_ids]
        if unknown:
            raise ReasoningContractError(f"{where}: unknown evidence ids {unknown}")
        standing = raw.get("standing", "supported")
        if standing not in STANDINGS:
            raise ReasoningContractError(f"{where}: 'standing' must be one of {list(STANDINGS)}")
        note = raw.get("reasoning_note", "")
        if not isinstance(note, str):
            raise ReasoningContractError(f"{where}: 'reasoning_note' must be a string")
        conclusions.append(
            ReasoningConclusion(
                statement=statement,
                evidence_ids=evidence_ids,
                ffo_refs=_need_str_tuple(raw, "ffo_refs", where),
                reasoning_note=note,
                standing=standing,
            )
        )
    if len(conclusions) > input.constraints.max_conclusions:
        raise ReasoningContractError(
            f"output: {len(conclusions)} conclusions exceed max {input.constraints.max_conclusions}"
        )
    contradictions = _need_str_tuple(data, "contradictions", "output")
    if any(c.standing == "contested" for c in conclusions) and not contradictions:
        raise ReasoningContractError("output: contested conclusions require 'contradictions'")
    if unsupported and conclusions:
        raise ReasoningContractError("output: 'unsupported' forbids conclusions")
    if not conclusions and not unsupported:
        missing = _need_str_tuple(data, "missing_evidence", "output")
        if not missing:
            raise ReasoningContractError(
                "output: empty conclusions require 'missing_evidence' (insufficient evidence)"
            )
    versions = _parse_versions(data.get("versions"))
    if versions.to_dict() != input.versions.to_dict():
        raise ReasoningContractError("output: version pins must equal input pins")
    return FashionReasoningOutput(
        answer=answer,
        conclusions=tuple(conclusions),
        uncertainties=_need_str_tuple(data, "uncertainties", "output"),
        missing_evidence=_need_str_tuple(data, "missing_evidence", "output"),
        contradictions=contradictions,
        confidence=data["confidence"],
        unsupported=unsupported,
        versions=versions,
    )


__all__ = [
    "CONFIDENCES",
    "DEFERRED_INTENTS",
    "EVIDENCE_SCHEMA_VERSION",
    "REASONING_CONTRACT_VERSION",
    "STANDINGS",
    "SUPPORTED_INTENTS",
    "FashionReasoningInput",
    "FashionReasoningOutput",
    "OutputRequirements",
    "ReasoningConclusion",
    "ReasoningConstraints",
    "ReasoningContext",
    "ReasoningContractError",
    "ReasoningEvidence",
    "ReasoningRequest",
    "ReasoningVersions",
    "corpus_digest",
    "validate_input",
    "validate_output",
]
