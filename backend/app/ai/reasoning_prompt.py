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
        "- Reference evidence using the supplied evidence IDs in square brackets.\n"
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
        "- Copy every evidence_id character-for-character from the square-bracketed IDs in section C; never invent an ID and never use knowledge text, labels, or statements as an ID.\n"
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
    """One explicit-field block; square brackets appear ONLY around the ID.

    All pre-existing information is preserved (type, label, FFO refs,
    confidence, retrieval reason/scores, source, status, knowledge
    content). Bracket reservation is enforceable: no corpus string value
    contains brackets and renderers emit only parens/braces.
    """
    retrieval = evidence.reason
    scores = []
    if evidence.lexical_score is not None:
        scores.append(f"lexical {evidence.lexical_score}")
    if evidence.semantic_score is not None:
        scores.append(f"semantic {evidence.semantic_score}")
    if scores:
        retrieval = f"{retrieval} ({', '.join(scores)})"
    refs = ", ".join(evidence.ffo_references) or "none"
    lines = [
        f"ID: [{evidence.doc_id}]",
        f"Type: {evidence.doc_type}",
        f"Label: {evidence.label}",
        f"FFO refs: {refs}",
        f"Confidence: {evidence.confidence}",
        f"Retrieved: {retrieval}",
        f"Source: {evidence.provenance.get('source', 'unknown')}",
        f"Status: {evidence.status}",
    ]
    knowledge = render_content(evidence.doc_type, evidence.content)
    if knowledge:
        lines.append(f"knowledge: {knowledge}")
    return "\n".join(lines)


def serialize_evidence(evidence_items) -> str:
    """Inventory-first section (never the corpus, never metadata dumps)."""
    if not evidence_items:
        return "No evidence documents were retrieved."
    inventory = "Valid evidence IDs:\n" + ", ".join(
        f"[{item.doc_id}]" for item in evidence_items
    )
    return inventory + "\n\n" + "\n\n".join(
        serialize_evidence_item(item) for item in evidence_items
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
        f"{serialize_evidence(reasoning_input.evidence)}\n"
        "\n## D. OUTPUT CONTRACT\n"
        "Return exactly one JSON object with these fields:\n"
        '{"answer": str (required, non-empty), '
        '"conclusions": [{"statement": str, "evidence_ids": [ids from section C], '
        '"ffo_refs": [refs from section C or the entity list above], '
        '"reasoning_note": str, "standing": "supported|uncertain|contested"}], '
        '"uncertainties": [str], "missing_evidence": [str], "contradictions": [str], '
        '"confidence": "high|medium|low|unknown", "unsupported": bool, '
        '"versions": ' + pins + '}\n'
        "Echo the versions object exactly as shown above — all four keys, unchanged.\n"
        '"evidence_ids" must be chosen only from the square-bracketed IDs in section C, never knowledge text.\n'
        f"max_conclusions: {reasoning_input.constraints.max_conclusions}\n"
        "Confidence is categorical, never a probability. "
        "Empty conclusions require missing_evidence (insufficient evidence). "
        "Contested conclusions require contradictions. "
        "No markdown fences or prose around the JSON."
    )


__all__ = [
    "build_system_prompt",
    "build_user_prompt",
    "render_content",
    "serialize_evidence",
    "serialize_evidence_item",
]
