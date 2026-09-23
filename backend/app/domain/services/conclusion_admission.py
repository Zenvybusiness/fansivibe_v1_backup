"""Conclusion admission contract — deterministic pre-3P gate (Phase 3T).

Implements the approved 3S design, nothing more. A proposed conclusion is
admissible iff BOTH hold:

  (A) subject-anchor — the conclusion's subject resolves to a query target,
      or a cited relationship/rule document explicitly edges it to one.
      Retrieved-pack co-occurrence is NOT an edge.
  (B) claim-support — every atomic claim cites >=1 evidence document that
      exists in the current pack. Citation membership is checked;
      natural-language entailment truth is NOT (see test U).

Outcomes: admit | reject | qualify | coverage_flag (set-level only).

Target sets derive from the QUERY TEXT matched against a caller-supplied
universe (canonicals + aliases + rule effects + entity kinds). They NEVER
derive from benchmark expected refs, evaluator output, or model-generated
target lists: `build_case_input` fills `input.entities` from benchmark
expectations, so that field is inadmissible here by construction.

Remove-only and immutable: conclusions (statements, evidence_ids,
ffo_refs, standing, uncertainties, contradictions, versions) are never
rewritten, only admitted or dropped. Rejected conclusions never reach 3P;
admitted ones proceed unchanged. This module never adds/removes FFO refs.

Stdlib only. No model calls, no benchmark imports, no corpus imports:
the caller supplies `universe` and the evidence pack.
"""

from __future__ import annotations

# Outcomes (the only four permitted by 3S).
ADMIT = "admit"
REJECT = "reject"
QUALIFY = "qualify"
COVERAGE_FLAG = "coverage_flag"

# Machine-readable reject/qualify reasons (deterministic, structural only).
TARGET_ADMIT = "target_subject"
EDGE_ADMIT = "edge_licensed_subject"
ALIAS_QUALIFY = "alias_form_subject"
SUBJECT_UNRESOLVED = "subject_unresolved"
NON_TARGET_NO_EDGE = "non_target_no_edge"
EMPTY_CITATION = "empty_citation"
UNKNOWN_DOC = "unknown_doc"
OUT_OF_PACK_DOC = "out_of_pack_doc"
DUPLICATE = "duplicate"
MISSING_RECORD = "missing_record"
UNSUPPORTED_OUTPUT = "unsupported_with_conclusions"


def _tokens(value: str) -> list[str]:
    return str(value).lower().replace("-", " ").replace("_", " ").split()


def _tok_eq(a: str, b: str) -> bool:
    """Token equality with single trailing-s tolerance (plural-light, no stemming).

    `top` == `tops`, but `garment` != `garments` handling stays exact-word
    elsewhere; this tolerance exists only so query inflections
    ("fitted tops") still anchor their canonical ("fitted-top").
    """
    if a == b:
        return True
    return a == b + "s" or b == a + "s"


def _tok_subset(small: list[str], big: list[str]) -> bool:
    return bool(small) and all(any(_tok_eq(t, u) for u in big) for t in small)


def _field(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _content(item) -> dict:
    content = _field(item, "content", None)
    return content if isinstance(content, dict) else {}


def derive_targets(query, universe, evidence=()) -> set[str]:
    """Query-mentioned target canonicals. No benchmark knowledge used.

    Strong match: canonical/alias/effect token set ⊆ query token set.
    Fallback (only when strong set is empty): a query token naming an
    entity_kind admits the pack's canonicals of that kind (e.g. query
    "fit" over a pack of fit terms). Pack-derived, deterministic.
    """
    canonicals = set(universe.get("canonicals", ()))
    aliases = dict(universe.get("aliases", {}))
    effects = set(universe.get("effects", ()))
    kinds = set(universe.get("kinds", ()))
    qtokens = _tokens(query)
    targets: set[str] = set()
    for canonical in canonicals:
        if _tok_subset(_tokens(canonical), qtokens):
            targets.add(canonical)
    for alias, canonical in aliases.items():
        if _tok_subset(_tokens(alias), qtokens):
            targets.add(canonical)
    for effect in effects:
        if _tok_subset(_tokens(effect), qtokens):
            targets.add(effect)
    if not targets:
        hit_kinds = {k for k in kinds if any(_tok_eq(t, k.lower()) for t in qtokens)}
        if hit_kinds:
            for item in evidence:
                content = _content(item)
                if content.get("entity_kind") in hit_kinds and content.get("canonical_id"):
                    targets.add(content["canonical_id"])
    return targets


def resolve_subject(subject_ref, universe):
    """Resolve a subject ref to (canonical, via_alias). None if unresolvable.

    Resolution scope is the FFO reference namespace only: canonical ids,
    aliases, and rule effects (the `effect` exposed by `ffo_references()` —
    no new namespace). Anything else (evidence IDs, bracketed forms,
    prose) fails closed. 3V: rule effects added; previously unresolvable.
    """
    if not isinstance(subject_ref, str) or not subject_ref.strip():
        return None
    ref = subject_ref.strip()
    if ref in universe.get("canonicals", ()):
        return ref, False
    if ref in universe.get("effects", ()):
        return ref, False
    canonical = universe.get("aliases", {}).get(ref)
    if canonical is not None:
        return canonical, True
    return None


def _rel_endpoints(item):
    content = _content(item)
    return content.get("subject"), content.get("object")


def _rule_effect(item):
    content = _content(item)
    payload = content.get("payload")
    if isinstance(payload, dict):
        return payload.get("effect")
    return None


def _rule_when_tokens(item) -> list[str]:
    """Tokens of a rule payload's `when` mapping (the effect's context)."""
    content = _content(item)
    payload = content.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("when"), dict):
        return []
    tokens: list[str] = []
    for key, value in payload["when"].items():
        tokens.extend(_tokens(key))
        tokens.extend(_tokens(value))
    return tokens


def _edge_licenses(resolved, targets, cited_items) -> bool:
    """True iff a cited relationship/rule doc explicitly edges subject→anchor.

    3V: a cited rule whose effect IS the (non-target) subject also licenses,
    but only when the rule's `when` context names a query anchor — the rule
    must establish the effect AND its relationship to the anchor.
    Pack co-occurrence (uncited rule) never licenses.
    """
    target_tokens = [t for target in targets for t in _tokens(target)]
    for item in cited_items:
        if _field(item, "doc_type") == "relationship":
            subject, obj = _rel_endpoints(item)
            if resolved in (subject, obj) and (subject in targets or obj in targets):
                return True
        elif _field(item, "doc_type") == "rule":
            if _rule_effect(item) in targets:
                return True
            if (_rule_effect(item) == resolved and resolved not in targets
                    and any(any(_tok_eq(w, t) for t in target_tokens)
                            for w in _rule_when_tokens(item))):
                return True
    return False


def adjudicate_record(record, *, targets, evidence_by_id, universe) -> tuple[str, str]:
    """Adjudicate one admission record. Returns (outcome, reason).

    Checks structure only: subject resolution, anchor/edge, citation
    membership. Claim TEXT is never interpreted (no entailment engine).
    Duplicate detection happens in `apply_admission` (needs set context).
    """
    resolved = resolve_subject(_field(record, "subject_ref"), universe)
    return _adjudicate_resolved(record, resolved, targets, evidence_by_id, universe)


def _adjudicate_resolved(record, resolved, targets, evidence_by_id, universe=None) -> tuple[str, str]:
    claims = _field(record, "atomic_claims", None)
    if not isinstance(claims, (list, tuple)) or not claims:
        return REJECT, EMPTY_CITATION
    cited: list[str] = []
    for claim in claims:
        doc_ids = _field(claim, "cited_doc_ids", None)
        if not isinstance(doc_ids, (list, tuple)) or not doc_ids:
            return REJECT, EMPTY_CITATION
        for doc_id in doc_ids:
            if not isinstance(doc_id, str) or not doc_id.strip():
                return REJECT, UNKNOWN_DOC
            if doc_id not in evidence_by_id:
                return REJECT, OUT_OF_PACK_DOC
            cited.append(doc_id)
    if resolved is None:
        return REJECT, SUBJECT_UNRESOLVED
    canonical, via_alias = resolved
    if canonical not in targets:
        cited_items = [evidence_by_id[d] for d in dict.fromkeys(cited)]
        if not _edge_licenses(canonical, targets, cited_items):
            return REJECT, NON_TARGET_NO_EDGE
        return ADMIT, EDGE_ADMIT
    if via_alias:
        return QUALIFY, ALIAS_QUALIFY
    return ADMIT, TARGET_ADMIT


def _claim_key(record) -> tuple:
    claims = _field(record, "atomic_claims", ()) or ()
    texts = []
    for claim in claims:
        text = _field(claim, "text", "")
        texts.append(text.strip() if isinstance(text, str) else "")
    return tuple(texts)


def apply_admission(conclusions, records, *, query, universe, evidence,
                    unsupported: bool = False) -> dict:
    """Gate a conclusion list. Returns admitted/outcomes/coverage, immutably.

    `conclusions`: model output conclusions (dicts or objects; never mutated,
    admitted entries keep object identity). `records`: parallel admission
    records (dicts/objects with subject_ref + atomic_claims[{text,
    cited_doc_ids}]); a conclusion without a usable record is rejected
    (fail-closed: the prompt must emit records before this gate activates).
    """
    evidence = list(evidence or [])
    evidence_by_id = {}
    for item in evidence:
        doc_id = _field(item, "doc_id")
        if isinstance(doc_id, str) and doc_id and doc_id not in evidence_by_id:
            evidence_by_id[doc_id] = item
    targets = derive_targets(query, universe, evidence)
    conclusions = list(conclusions or [])
    records = list(records or [])

    admitted: list = []
    outcomes: list[dict] = []
    seen: set = set()
    subjects_covered: set[str] = set()

    for index, conclusion in enumerate(conclusions):
        if unsupported:
            outcomes.append({"index": index, "outcome": REJECT,
                             "reason": UNSUPPORTED_OUTPUT})
            continue
        record = records[index] if index < len(records) else None
        if record is None:
            outcomes.append({"index": index, "outcome": REJECT,
                             "reason": MISSING_RECORD})
            continue
        resolved = resolve_subject(_field(record, "subject_ref"), universe)
        outcome, reason = _adjudicate_resolved(
            record, resolved, targets, evidence_by_id, universe)
        if outcome == ADMIT:
            statement = _field(conclusion, "statement", "")
            key = (resolved[0] if resolved else None, _claim_key(record),
                   statement.strip() if isinstance(statement, str) else statement)
            if key in seen:
                outcome, reason = REJECT, DUPLICATE
            else:
                seen.add(key)
        outcomes.append({"index": index, "outcome": outcome, "reason": reason})
        if outcome in (ADMIT, QUALIFY) and resolved is not None:
            admitted.append(conclusion)
            subjects_covered.add(resolved[0])

    uncovered = sorted(t for t in targets if t not in subjects_covered)
    pack_cover = set()
    for item in evidence:
        content = _content(item)
        if content.get("canonical_id"):
            pack_cover.add(content["canonical_id"])
        if content.get("alias") in universe.get("aliases", {}):
            pack_cover.add(universe["aliases"][content["alias"]])
        for endpoint in _rel_endpoints(item):
            if endpoint:
                pack_cover.add(endpoint)
        if _rule_effect(item):
            pack_cover.add(_rule_effect(item))
    missing_evidence = []
    for target in uncovered:
        if target in pack_cover:
            missing_evidence.append(
                f"no admitted conclusion covers query target '{target}' (evidence present)")
        else:
            missing_evidence.append(
                f"no covering evidence for query target '{target}'")
    return {
        "admitted": admitted,
        "outcomes": outcomes,
        "targets": sorted(targets),
        "coverage_flags": uncovered,
        "missing_evidence": missing_evidence,
    }


__all__ = [
    "ADMIT", "REJECT", "QUALIFY", "COVERAGE_FLAG",
    "TARGET_ADMIT", "EDGE_ADMIT", "ALIAS_QUALIFY",
    "SUBJECT_UNRESOLVED", "NON_TARGET_NO_EDGE",
    "EMPTY_CITATION", "UNKNOWN_DOC", "OUT_OF_PACK_DOC",
    "DUPLICATE", "MISSING_RECORD", "UNSUPPORTED_OUTPUT",
    "derive_targets", "resolve_subject", "adjudicate_record",
    "apply_admission",
]
