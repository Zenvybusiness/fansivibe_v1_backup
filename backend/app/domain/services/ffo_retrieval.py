"""FFO knowledge retrieval V0 — deterministic lexical + metadata (Phase 2C).

Internal/domain-level service over the validated Phase 2B corpus. No
embeddings, no vector DB, no HTTP, no Ollama. Same query + same corpus →
same ordered results, always.

Scoring tiers (integer, higher wins; ties break by doc_id ascending):
  700 exact_canonical  query == a term's canonical_id (normalized)
  600 exact_alias      query == an alias, or an alias doc's canonical target
  500 exact_phrase     query is a proper substring of one text field
                       (canonical/alias/payload strings only)
  400 token            query/doc share ≥1 token over those text fields
  300 ffo_reference    query == a secondary FFO ref (entity_kind, rule
                       effect/when values, relationship subject/object)
  200 domain           query == derived domain name
  100 metadata         query == language/region/status value
  0   unscored         empty query (filters still apply)

Score = max firing tier; reason = that tier's name. matched_terms names
the evidence ("why was this retrieved?"). Filters (doc_type, domain,
entity, language, region) are hard AND-gates applied before scoring.

Domain derivation (static maps; fallback "general", currently unreachable
in Seed v0.1 — bags/jewelry group under "accessories" per the 14-domain
list; rules are styling heuristics in v0.1):
  term by entity_kind; relationship by rel_type; rule -> styling.

Deferred (need volume or new deps): TF-IDF/field weights, vector search,
hybrid fusion, reranking, DB-backed corpus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.data.ffo import FFO_VERSION, corpus

TIER_SCORES = {
    "exact_canonical": 700,
    "exact_alias": 600,
    "exact_phrase": 500,
    "token": 400,
    "ffo_reference": 300,
    "domain": 200,
    "metadata": 100,
    "unscored": 0,
}

ENTITY_DOMAIN = {
    "garment": "garments",
    "footwear": "footwear",
    "accessory": "accessories",
    "bag": "accessories",
    "jewelry": "accessories",
    "material": "materials/textiles",
    "textile": "materials/textiles",
    "color": "color",
    "pattern": "patterns",
    "silhouette": "silhouette",
    "fit": "fit",
    "aesthetic": "aesthetics",
    "culture": "regional/cultural",
}

REL_TYPE_DOMAIN = {
    "PAIRS_WITH": "styling",
    "LAYERED_WITH": "styling",
    "COMPLEMENTS": "styling",
    "INFLUENCED": "fashion history",
    "POPULARIZED_BY": "fashion history",
    "INSPIRED_BY": "fashion history",
    "REVIVED": "fashion history",
    "MADE_FROM": "materials/textiles",
}

RULE_DOMAIN = "styling"
FALLBACK_DOMAIN = "general"


def _norm(value: object) -> str:
    """Lowercase, separator-insensitive comparison form."""
    return " ".join(str(value or "").lower().replace("-", " ").replace("_", " ").split())


def _tokens(text: object) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", "", _norm(text))
    return {tok for tok in cleaned.split() if len(tok) >= 2}


def _payload_strings(payload: object) -> list[str]:
    """One-level string flattening of a payload (no deep walk by design)."""
    if not isinstance(payload, dict):
        return []
    out: list[str] = []
    for value in payload.values():
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, list):
            out.extend(item for item in value if isinstance(item, str))
    return out


def doc_domain(doc: dict) -> str:
    """Derived 14-domain bucket for one corpus document."""
    if doc.get("doc_type") == "term":
        return ENTITY_DOMAIN.get(doc.get("entity_kind"), FALLBACK_DOMAIN)
    if doc.get("doc_type") == "relationship":
        return REL_TYPE_DOMAIN.get(doc.get("rel_type"), FALLBACK_DOMAIN)
    if doc.get("doc_type") == "rule":
        return RULE_DOMAIN
    if doc.get("doc_type") == "alias":
        return doc_domain({**doc, "doc_type": "term"})
    return FALLBACK_DOMAIN


def doc_label(doc: dict) -> str:
    """Human label: canonical, alias, relation triple, rule effect, doc_id."""
    if doc.get("canonical_id"):
        return str(doc["canonical_id"])
    if doc.get("alias"):
        return str(doc["alias"])
    if doc.get("doc_type") == "relationship":
        return f"{doc.get('subject')} {doc.get('rel_type')} {doc.get('object')}"
    payload = doc.get("payload")
    if isinstance(payload, dict) and payload.get("effect"):
        return str(payload["effect"])
    return str(doc.get("doc_id", ""))


def ffo_references(doc: dict) -> list[str]:
    """Ordered unique FFO refs: canonical, alias, entity kind, subject/object."""
    refs: list[str] = []
    for key in ("canonical_id", "alias", "entity_kind", "subject", "object"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip() and value not in refs:
            refs.append(value)
    return refs


def _text_fields(doc: dict) -> list[str]:
    """Phrase/token surface: names + payload strings only.

    Structured refs (entity_kind, subject, object, effect, when-values,
    doc_id, rel_type) are deliberately excluded so whole-field equality
    resolves at the ffo_reference tier instead of collapsing into phrase.
    """
    fields = [doc.get("canonical_id"), doc.get("alias")]
    fields.extend(_payload_strings(doc.get("payload")))
    return [f for f in fields if isinstance(f, str) and f.strip()]


def _secondary_refs(doc: dict) -> list[str]:
    """FFO refs below primary identity: entity kind, subjects/objects,
    rule effect + when-values."""
    refs: list[str] = []
    for key in ("entity_kind", "subject", "object"):
        value = doc.get(key)
        if isinstance(value, str) and value.strip() and value not in refs:
            refs.append(value)
    payload = doc.get("payload")
    if isinstance(payload, dict):
        if isinstance(payload.get("effect"), str):
            refs.append(payload["effect"])
        when = payload.get("when")
        if isinstance(when, dict):
            refs.extend(v for v in when.values() if isinstance(v, str))
    return refs


@dataclass(frozen=True)
class RetrievalResult:
    """One ordered evidence item — answers 'why was this retrieved?'."""

    doc_id: str
    doc_type: str
    label: str
    matched_terms: tuple
    score: int
    reason: str
    domain: str
    ffo_references: tuple
    provenance: dict
    confidence: float
    status: str

    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "label": self.label,
            "matched_terms": list(self.matched_terms),
            "score": self.score,
            "reason": self.reason,
            "domain": self.domain,
            "ffo_references": list(self.ffo_references),
            "provenance": dict(self.provenance),
            "confidence": self.confidence,
            "status": self.status,
        }


@dataclass(frozen=True)
class EvidencePack:
    """Query + filters + ordered evidence + corpus version info.

    Reasoning input for a future layer — NOT a model prompt.
    """

    query: str
    filters: dict
    items: tuple
    metadata: dict
    corpus: dict

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "filters": dict(self.filters),
            "items": [item.to_dict() for item in self.items],
            "metadata": dict(self.metadata),
            "corpus": {
                "ffo_version": self.corpus["ffo_version"],
                "document_count": self.corpus["document_count"],
                "versions": dict(self.corpus["versions"]),
            },
        }


def _score_doc(doc: dict, query: str) -> tuple[int, str, list]:
    """Max-tier score + reason + matched evidence for one doc; (0,...) when blank."""
    q = _norm(query)
    if not q:
        return 0, "unscored", []
    canonical = doc.get("canonical_id")
    if isinstance(canonical, str) and _norm(canonical) == q:
        if doc.get("doc_type") == "term":
            return 700, "exact_canonical", [canonical]
        return 600, "exact_alias", [canonical]
    alias = doc.get("alias")
    if isinstance(alias, str) and _norm(alias) == q:
        return 600, "exact_alias", [alias]
    for text in _text_fields(doc):
        field = _norm(text)
        if q in field and q != field:
            return 500, "exact_phrase", [query.strip()]
    overlap = sorted(_tokens(query) & _tokens(" ".join(_text_fields(doc))))
    if overlap:
        return 400, "token", overlap
    for ref in _secondary_refs(doc):
        if _norm(ref) == q:
            return 300, "ffo_reference", [ref]
    if _norm(doc_domain(doc)) == q:
        return 200, "domain", [doc_domain(doc)]
    for key in ("language", "region", "status"):
        value = doc.get(key)
        if isinstance(value, str) and _norm(value) == q:
            return 100, "metadata", [value]
    return 0, "unscored", []


def _passes_filters(doc: dict, *, doc_type, domain, entity, language, region) -> bool:
    if doc_type is not None and doc.get("doc_type") != doc_type:
        return False
    if domain is not None and _norm(doc_domain(doc)) != _norm(domain):
        return False
    if entity is not None and _norm(entity) not in {_norm(r) for r in ffo_references(doc)}:
        return False
    if language is not None and _norm(doc.get("language")) != _norm(language):
        return False
    if region is not None:
        regions = {r for r in (_norm(doc.get("region")),) if r}
        payload = doc.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("region"), str):
            regions.add(_norm(payload["region"]))
        if _norm(region) not in regions:
            return False
    return True


def retrieve(
    query: str,
    *,
    doc_type: str | None = None,
    domain: str | None = None,
    entity: str | None = None,
    language: str | None = None,
    region: str | None = None,
    limit: int | None = None,
    documents: list | None = None,
) -> EvidencePack:
    """Deterministic V0 retrieval over validated corpus documents.

    `documents` injects a set for tests; default is the shipped seed via
    the existing corpus loader (validated — invalid seed raises).
    """
    if doc_type is not None and doc_type not in corpus.DOC_TYPES:
        raise ValueError(f"unknown doc_type '{doc_type}'")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("'limit' must be a positive integer")
    docs = documents if documents is not None else corpus.load_documents()
    index = corpus.build_index(docs)
    filters = {
        "doc_type": doc_type,
        "domain": domain,
        "entity": entity,
        "language": language,
        "region": region,
    }
    ranked: list[tuple] = []
    for doc in docs:
        if not _passes_filters(
            doc, doc_type=doc_type, domain=domain, entity=entity,
            language=language, region=region,
        ):
            continue
        score, reason, matched = _score_doc(doc, query)
        if _norm(query) and score == 0:
            continue
        ranked.append((doc, score, reason, matched))
    ranked.sort(key=lambda row: (-row[1], row[0].get("doc_id", "")))
    if limit is not None:
        ranked = ranked[:limit]
    items = tuple(
        RetrievalResult(
            doc_id=doc["doc_id"],
            doc_type=doc["doc_type"],
            label=doc_label(doc),
            matched_terms=tuple(matched),
            score=score,
            reason=reason,
            domain=doc_domain(doc),
            ffo_references=tuple(ffo_references(doc)),
            provenance=dict(doc["provenance"]),
            confidence=float(doc["provenance"]["confidence"]),
            status=doc["status"],
        )
        for doc, score, reason, matched in ranked
    )
    return EvidencePack(
        query=query,
        filters=filters,
        items=items,
        metadata={"returned": len(items), "total_candidates": len(docs), "limit": limit},
        corpus={
            "ffo_version": FFO_VERSION,
            "document_count": len(docs),
            "versions": corpus.corpus_versions(index),
        },
    )


__all__ = [
    "EvidencePack",
    "RetrievalResult",
    "TIER_SCORES",
    "doc_domain",
    "doc_label",
    "ffo_references",
    "retrieve",
]
