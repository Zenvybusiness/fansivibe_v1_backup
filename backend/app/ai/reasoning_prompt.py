"""Reasoning prompt construction — dedicated builder (Phase 3C, hardened 3E).

Separated from HTTP/client code by design: this module renders strings
only and never touches the network. Sections stay explicit:

  A. SYSTEM INSTRUCTIONS (static rules for the model)
  B. USER REQUEST (query + intent)
  C. STRUCTURED CONTEXT (optional fields or "none")
  D. RETRIEVED EVIDENCE (compact per-document blocks)
  E. OUTPUT CONTRACT (JSON shape, pins, max_conclusions)

Evidence serialization is compact by rule: id, type, label, FFO refs,
confidence, provenance source, retrieval reason/scores, plus one
validated `knowledge:` content line per item (Phase 3D contract field).
It carries no corpus dumps and never filesystem paths — only the
supplied evidence items. Phase 3E adds explicit ID-fidelity and
versions-echo rules after the 3D baseline showed the model dropping
version keys and citing knowledge text as evidence IDs; validation
itself is unchanged (still strict, still authoritative).
"""

from __future__ import annotations


def build_system_prompt() -> str:
    """Static model instructions (no per-request data)."""
    return (
        "You are Fansivibe's fashion reasoning engine. Answer ONLY from the "
        "supplied evidence.\n"
        "Rules:\n"
        "- Use only supplied evidence for factual fashion claims; do not invent evidence.\n"
        "- Reference evidence using the supplied evidence IDs.\n"
        "- Use only supplied FFO references; never invent entity names.\n"
        "- Distinguish supported conclusions (standing supported) from uncertainty "
        "(standing uncertain) and conflicts (standing contested).\n"
        "- Report insufficient evidence (empty conclusions plus missing_evidence) "
        "when the evidence is inadequate.\n"
        "- Report contradictions when supplied evidence conflicts.\n"
        "- Obey max_conclusions.\n"
        "- Return exactly one JSON object matching the output contract below.\n"
        "- Do not return markdown around the JSON output.\n"
        "- Return ONLY that JSON object and nothing else.\n"
        "- Copy every evidence_id character-for-character from the Valid evidence IDs list in section C; never invent an ID and never use knowledge text, labels, or statements as an ID.\n"
        "- Copy every ffo_ref character-for-character from the Valid FFO references list in section C; output each ref exactly as shown, one string per ref; never invent, combine, split, or abbreviate a ref and never use evidence IDs, labels, or knowledge text as a ref.\n"
        "- Keep every conclusion and ffo_ref strictly scoped to the user query in section A of the user message; do not add adjacent, broader, narrower, or merely related concepts unless the query or the cited evidence explicitly requires them.\n"
        "- For each conclusion include one admission record naming that conclusion's subject and atomic claims with their cited evidence IDs, in the same order as conclusions; copy every cited ID exactly and never invent evidence or IDs (the server validates admission).\n"
        "- Admission subject_ref must contain exactly one valid FFO reference copied character-for-character from the valid FFO reference namespace. Do not place evidence IDs, explanations, labels, brackets, or prose in subject_ref.\n"
        "- Echo the versions object from section D exactly, with all four keys unchanged."
    )


def _render_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "(" + "/".join(str(item) for item in value) + ")"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{key}={_render_value(val)}" for key, val in value.items()) + "}"
    return str(value)


def render_content(doc_type: str, content: dict) -> str:
    """Compact knowledge line for one evidence item (empty when no content)."""
    if not content:
        return ""
    if doc_type == "relationship":
        return f"{content.get('subject')} {content.get('rel_type')} {content.get('object')}"
    if doc_type == "rule":
        payload = content.get("payload", {})
        return f"when {_render_value(payload.get('when'))} → {payload.get('effect')}"
    if doc_type == "alias":
        return f"variant '{content.get('alias')}'"
    if doc_type == "term":
        payload = content.get("payload", {})
        return ", ".join(f"{key}={_render_value(val)}" for key, val in payload.items())
    return ""


def serialize_evidence_item(evidence) -> str:
    """One explicit-field block (delimiter-free ID).

    All pre-existing information is preserved (type, label, FFO refs,
    confidence, retrieval reason/scores, source, status, knowledge
    content). IDs and FFO refs are rendered delimiter-free (exact raw
    strings, one per line) so there is nothing to strip; field labels keep
    the ID and ref namespaces apart.
    """
    retrieval = evidence.reason
    scores = []
    if evidence.lexical_score is not None:
        scores.append(f"lexical {evidence.lexical_score}")
    if evidence.semantic_score is not None:
        scores.append(f"semantic {evidence.semantic_score}")
    if scores:
        retrieval = f"{retrieval} ({', '.join(scores)})"
    refs = "\n".join(evidence.ffo_references) or "none"
    lines = [
        f"ID: {evidence.doc_id}",
        f"Type: {evidence.doc_type}",
        f"Label: {evidence.label}",
        "FFO refs:\n" + refs,
        f"Confidence: {evidence.confidence}",
        f"Retrieved: {retrieval}",
        f"Source: {evidence.provenance.get('source', 'unknown')}",
        f"Status: {evidence.status}",
    ]
    knowledge = render_content(evidence.doc_type, evidence.content)
    if knowledge:
        lines.append(f"knowledge: {knowledge}")
    return "\n".join(lines)


def ffo_universe(entities, evidence_items) -> list[str]:
    """Deterministic FFO-reference universe: entities ∪ evidence refs, sorted."""
    return sorted({*entities, *(r for item in evidence_items for r in item.ffo_references)})


def serialize_ffo_inventory(entities, evidence_items) -> str:
    """Closed FFO-reference namespace; mirrors the evidence-ID inventory."""
    universe = ffo_universe(entities, evidence_items)
    refs = "\n".join(universe) or "none"
    return f"Valid FFO references:\n{refs}"


def serialize_evidence(evidence_items, entities=()) -> str:
    """Inventory-first section (never the corpus, never metadata dumps)."""
    if not evidence_items:
        return "No evidence documents were retrieved."
    inventory = "Valid evidence IDs:\n" + "\n".join(
        item.doc_id for item in evidence_items
    )
    return (
        inventory
        + "\n\n"
        + serialize_ffo_inventory(entities, evidence_items)
        + "\n\n"
        + "\n\n".join(serialize_evidence_item(item) for item in evidence_items)
    )


def _render_context(context) -> str:
    fields = {
        "occasion": context.occasion,
        "climate": context.climate,
        "region": context.region,
        "style_preference": context.style_preference,
        "wardrobe_refs": list(context.wardrobe_refs) or None,
        "budget": context.budget,
        "fit_preference": context.fit_preference,
    }
    lines = [f"- {key}: {value}" for key, value in fields.items() if value is not None]
    return "\n".join(lines) if lines else "none"


def build_user_prompt(reasoning_input) -> str:
    """Full user message: request, context, evidence, output contract."""
    versions = reasoning_input.versions
    entities = ", ".join(reasoning_input.entities) or "none"
    pins = (
        '{"ffo_version": "'
        + versions.ffo_version
        + '", "corpus_digest": "'
        + versions.corpus_digest
        + '", "evidence_schema": "'
        + versions.evidence_schema
        + '", "reasoning_contract_version": "'
        + versions.reasoning_contract_version
        + '"}'
    )
    return (
        "## A. USER REQUEST\n"
        f"query: {reasoning_input.request.query}\n"
        f"intent: {reasoning_input.request.intent}\n"
        f"FFO entities mentioned: {entities}\n"
        "\n## B. STRUCTURED CONTEXT\n"
        f"{_render_context(reasoning_input.context)}\n"
        "\n## C. RETRIEVED EVIDENCE\n"
        "Evidence IDs are listed under Valid evidence IDs below — copy one exactly; never use the knowledge text as an ID.\n"
        "FFO refs are listed under Valid FFO references below — copy one exactly; never use evidence IDs, labels, or knowledge text as a ref.\n"
        f"{serialize_evidence(reasoning_input.evidence, reasoning_input.entities)}\n"
        "\n## D. OUTPUT CONTRACT\n"
        "The following fields are TOP-LEVEL fields of the single JSON object:\n"
        "answer\n"
        "conclusions\n"
        "uncertainties\n"
        "missing_evidence\n"
        "contradictions\n"
        "unsupported\n"
        "confidence\n"
        "versions\n"
        "\n"
        "Do not place any of these fields inside a conclusion object.\n"
        "\n"
        "Each item inside conclusions[] may contain ONLY the fields explicitly defined for a conclusion.\n"
        "\n"
        "confidence is a top-level field, never a conclusion field.\n"
        "\n"
        "Return exactly one JSON object with the top-level fields defined above:\n"
        "{\n"
        '  "answer": str (required, non-empty),\n'
        '  "conclusions": [\n'
        "    {\n"
        '      "statement": str,\n'
        '      "evidence_ids": [ids from section C],\n'
        '      "ffo_refs": [exact strings from Valid FFO references in section C],\n'
        '      "reasoning_note": str,\n'
        '      "standing": "supported|uncertain|contested",\n'
        '      "admission": {\n'
        '        "subject_ref": "exact string from Valid FFO references list in section C",\n'
        '        "atomic_claims": [{"text": str, "cited_doc_ids": [ids from section C]}]\n'
        "      }\n"
        "    }\n"
        "  ],\n"
        '  "uncertainties": [str],\n'
        '  "missing_evidence": [str],\n'
        '  "contradictions": [str],\n'
        '  "confidence": "high|medium|low|unknown",\n'
        '  "unsupported": bool,\n'
        '  "versions": ' + pins + "\n"
        "}\n"
        "Echo the versions object exactly as shown above — all four keys, unchanged.\n"
        '"evidence_ids" must contain only exact strings copied character-for-character from the Valid evidence IDs list in section C. evidence_ids are evidence document IDs, not FFO references. Never place FFO references, entity names, labels, knowledge text, statements, or relationship phrases in evidence_ids.\n'
        '"admission" holds one record per conclusion in the same order: "subject_ref" must be exactly one string copied from the Valid FFO references list in section C. subject_ref is an FFO reference, not an evidence document ID. Evidence document IDs use the prefixes term-, alias-, rel-, or rule- and must never be placed in subject_ref. "atomic_claims" lists its claims each with "cited_doc_ids" copied character-for-character from the Valid evidence IDs list in section C, never knowledge text, labels, FFO refs, or statements. Evidence IDs and FFO refs are different namespaces.\n'
        '"ffo_refs" must contain only exact strings copied character-for-character from the Valid FFO references list in section C. For relationship evidence, use the individual endpoint FFO references from the Valid FFO references list. Never copy the relationship Label or knowledge text itself as an ffo_ref.\n'
        f"max_conclusions: {reasoning_input.constraints.max_conclusions}\n"
        "Confidence is categorical, never a probability. "
        "Empty conclusions require missing_evidence (insufficient evidence). "
        "Contested conclusions require contradictions. "
        "conclusions is an array. "
        "uncertainties is an array. "
        "missing_evidence is an array. "
        "contradictions is an array. "
        "unsupported is a boolean. "
        "When there are no contradictions, output []. "
        "Never output the string 'None', 'none', 'N/A', or similar text for an array field. "
        "No markdown fences or prose around the JSON."
    )


__all__ = [
    "build_system_prompt",
    "build_user_prompt",
    "ffo_universe",
    "render_content",
    "serialize_evidence",
    "serialize_evidence_item",
    "serialize_ffo_inventory",
]
