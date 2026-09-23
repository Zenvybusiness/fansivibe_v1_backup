"""Role-aware FFO reference selector — post-LLM deterministic filter (Phase 3P).

Implements the approved 3O design. Pure function over one conclusion's
proposed refs plus the evidence pack: remove-only (never adds, never
repairs), statements/evidence/versions untouched. Invalid refs pass
through untouched so the existing validator still rejects them — the
selector never launders failures into passes.

Role model (derived from evidence structure, no new namespace):
  canonical_entity      ref == a doc's canonical_id (preferred, always kept)
  alias                 ref == an alias doc's alias (kept as proposed)
  relationship_endpoint ref == a relationship's subject/object (kept)
  rule_effect           ref == a rule payload's effect (kept)
  entity_kind           ref == a doc's entity_kind (gated: keep iff the kind
                        word-matches the conclusion statement, or is shared
                        by >=2 distinct cited canonicals; else dropped)

Kind matching is case-insensitive with word boundaries and no stemming,
so `garment` never matches `garments`. Query/intent ride the signature
for contract stability; current rules do not gate on them (3O: generic
query-relevance filtering was rejected after the 3J null).
"""

from __future__ import annotations

import re

CANONICAL_KEEP = "canonical_keep"
ALIAS_KEEP = "alias_keep"
RELATIONSHIP_ENDPOINT_KEEP = "relationship_endpoint_keep"
RULE_EFFECT_KEEP = "rule_effect_keep"
KIND_STATEMENT_MATCH_KEEP = "kind_statement_match_keep"
KIND_SHARED_CANONICAL_KEEP = "kind_shared_canonical_keep"
KIND_UNLINKED_DROP = "kind_unlinked_drop"
UNRECOGNIZED_PASSTHROUGH_KEEP = "unrecognized_passthrough_keep"


def _content(evidence) -> dict:
    content = getattr(evidence, "content", None)
    return content if isinstance(content, dict) else {}


def _role(ref: str, evidence_items) -> str | None:
    """Best role for ref across the pack (canonical > alias > endpoint > effect > kind)."""
    kind = None
    for item in evidence_items:
        content = _content(item)
        if content.get("canonical_id") == ref:
            return "canonical_entity"
        if content.get("alias") == ref:
            return "alias"
        if ref in (content.get("subject"), content.get("object")):
            return "relationship_endpoint"
        payload = content.get("payload")
        if isinstance(payload, dict) and payload.get("effect") == ref:
            return "rule_effect"
        if content.get("entity_kind") == ref:
            kind = "entity_kind"
    return kind


def _word_match(ref: str, statement: str) -> bool:
    return re.search(r"\b" + re.escape(ref) + r"\b", statement, re.IGNORECASE) is not None


def _cited_canonicals_for_kind(kind: str, cited_items) -> set:
    """Distinct cited canonical_ids whose entity_kind is `kind`."""
    canonicals = set()
    for item in cited_items:
        content = _content(item)
        if content.get("entity_kind") == kind and content.get("canonical_id"):
            canonicals.add(content["canonical_id"])
    return canonicals


def select_refs(statement, proposed_refs, cited_ids, evidence_items, query="", intent=""):
    """Filter one conclusion's proposed refs; return (kept_refs, decisions).

    Deterministic, order-preserving, remove-only. Every decision carries a
    stable rule_id. `query`/`intent` are contract-reserved (unused by the
    current kind-gating rules).
    """
    by_id = {item.doc_id: item for item in evidence_items}
    cited = [by_id[doc_id] for doc_id in cited_ids if doc_id in by_id]
    kept: list[str] = []
    decisions: list[dict] = []
    for ref in proposed_refs:
        role = _role(ref, evidence_items)
        if role == "canonical_entity":
            action, rule = "keep", CANONICAL_KEEP
        elif role == "alias":
            action, rule = "keep", ALIAS_KEEP
        elif role == "relationship_endpoint":
            action, rule = "keep", RELATIONSHIP_ENDPOINT_KEEP
        elif role == "rule_effect":
            action, rule = "keep", RULE_EFFECT_KEEP
        elif role == "entity_kind":
            if _word_match(ref, statement):
                action, rule = "keep", KIND_STATEMENT_MATCH_KEEP
            elif len(_cited_canonicals_for_kind(ref, cited)) >= 2:
                action, rule = "keep", KIND_SHARED_CANONICAL_KEEP
            else:
                action, rule = "drop", KIND_UNLINKED_DROP
        else:
            action, rule = "keep", UNRECOGNIZED_PASSTHROUGH_KEEP
        if action == "keep":
            kept.append(ref)
        decisions.append({"reference": ref, "role": role, "action": action, "rule_id": rule})
    return kept, decisions


__all__ = [
    "ALIAS_KEEP",
    "CANONICAL_KEEP",
    "KIND_SHARED_CANONICAL_KEEP",
    "KIND_STATEMENT_MATCH_KEEP",
    "KIND_UNLINKED_DROP",
    "RELATIONSHIP_ENDPOINT_KEEP",
    "RULE_EFFECT_KEEP",
    "UNRECOGNIZED_PASSTHROUGH_KEEP",
    "select_refs",
]
