"""Phase 3H focused tests — delimiter-free FFO-reference namespace.

No Ollama: serialization asserted directly (including over the full
76-doc corpus); adapter rejection runs over `httpx.MockTransport`.
Validator semantics unchanged — these tests pin that FFO refs render as
exact raw strings (one per line, no delimiters) and that ONLY the
supplied FFO-reference universe (entities ∪ evidence refs) is
referenceable.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.ollama_reasoner import (
    OllamaFashionReasoner,
    ReasoningConfig,
    ReasoningExecutionError,
)
from app.ai.reasoning_prompt import (
    build_user_prompt,
    ffo_universe,
    serialize_evidence,
)
from app.data.ffo import corpus
from app.domain.services.ffo_reasoning import (
    REASONING_CONTRACT_VERSION,
    ReasoningEvidence,
    corpus_digest,
    validate_input,
)
from app.domain.services.ffo_retrieval import retrieve

VERSIONS = {
    "ffo_version": "1.0",
    "corpus_digest": corpus_digest({"term-denim": 1}, "1.0"),
    "evidence_schema": "evidence-pack/1",
    "reasoning_contract_version": REASONING_CONTRACT_VERSION,
}

EVIDENCE = [
    {
        "doc_id": "term-denim",
        "doc_type": "term",
        "label": "denim",
        "reason": "exact_canonical",
        "lexical_score": 700,
        "semantic_score": None,
        "ffo_references": ["denim", "textile"],
        "provenance": {"source": "s", "source_type": "AUTHORITATIVE", "confidence": 0.9},
        "confidence": 0.9,
        "status": "published",
        "content": {
            "doc_id": "term-denim",
            "entity_kind": "textile",
            "canonical_id": "denim",
            "payload": {"durability": "high", "name": "denim"},
        },
    },
    {
        "doc_id": "alias-jeans",
        "doc_type": "alias",
        "label": "blue jeans",
        "reason": "exact_alias",
        "lexical_score": 600,
        "semantic_score": None,
        "ffo_references": ["denim", "jeans"],
        "provenance": {"source": "s", "source_type": "AUTHORITATIVE", "confidence": 0.8},
        "confidence": 0.8,
        "status": "published",
        "content": {"doc_id": "alias-jeans", "alias": "jeans", "canonical_id": "denim"},
    },
]


def _input(**overrides):
    data = {
        "request": {"query": "what is denim", "intent": "explain"},
        "context": {},
        "entities": ["denim"],
        "evidence": [dict(e) for e in EVIDENCE],
        "constraints": {"evidence_only": True, "max_conclusions": 3},
        "requirements": {"include_reasoning_notes": True},
        "versions": dict(VERSIONS),
    }
    data.update(overrides)
    return validate_input(data)


def _output(**overrides):
    data = {
        "answer": "Denim is a durable textile.",
        "conclusions": [
            {
                "statement": "Denim is a durable textile.",
                "evidence_ids": ["term-denim"],
                "ffo_refs": ["denim"],
                "reasoning_note": "n",
                "standing": "supported",
                "admission": {
                    "subject_ref": "denim",
                    "atomic_claims": [
                        {"text": "Denim is a durable textile.",
                         "cited_doc_ids": ["term-denim"]}
                    ],
                },
            }
        ],
        "uncertainties": [],
        "missing_evidence": [],
        "contradictions": [],
        "confidence": "high",
        "unsupported": False,
        "versions": dict(VERSIONS),
    }
    data.update(overrides)
    return data


def _reason(payload, reasoning_input=None):
    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(payload)}}
        )

    adapter = OllamaFashionReasoner(
        ReasoningConfig(model="m"),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return adapter.reason(reasoning_input or _input())


def _full_corpus_evidence():
    docs = corpus.load_documents()
    by_id = corpus.build_index(docs)["by_id"]
    pack = retrieve("", documents=docs)  # blank query: unscored, all pass filters
    out = []
    for item in pack.items:
        record = ReasoningEvidence.from_retrieval(item).to_dict()
        record["content"] = corpus.evidence_content(by_id[item.doc_id])
        out.append(ReasoningEvidence(**record))
    return out


def _inventory_lines(text):
    lines = text.splitlines()
    start = lines.index("Valid FFO references:") + 1
    refs = []
    for line in lines[start:]:
        if not line.strip() or line.startswith(("ID: ", "Valid evidence IDs:")):
            break
        refs.append(line)
    return refs


# --- serialization (delimiter-free) ---


def test_raw_refs_emitted_unchanged_one_per_line():
    parsed = _input()
    text = serialize_evidence(parsed.evidence, parsed.entities)
    assert _inventory_lines(text) == ["denim", "jeans", "textile"]
    assert "FFO refs:\ndenim\ntextile" in text
    assert "FFO refs:\ndenim\njeans" in text


def test_no_delimiters_added_around_refs():
    parsed = _input()
    text = serialize_evidence(parsed.evidence, parsed.entities)
    universe = set(ffo_universe(parsed.entities, parsed.evidence))
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in universe:
            continue
        for ref in universe:
            assert stripped != f"[{ref}]", f"bracketed ref: {stripped}"
            assert stripped != f"<{ref}>", f"angle-bracketed ref: {stripped}"
            assert stripped != f"({ref})", f"parenthesized ref: {stripped}"
            assert stripped != f"{ref},", f"comma-suffixed ref: {stripped}"


def test_multiple_refs_individually_represented():
    parsed = _input()
    text = serialize_evidence(parsed.evidence, parsed.entities)
    for ref in ("denim", "jeans", "textile"):
        assert sum(1 for line in text.splitlines() if line.strip() == ref) >= 2


def test_evidence_ids_distinct_from_refs():
    parsed = _input()
    text = serialize_evidence(parsed.evidence, parsed.entities)
    universe = set(ffo_universe(parsed.entities, parsed.evidence))
    ids = {e.doc_id for e in parsed.evidence}
    assert ids.isdisjoint(universe)
    for doc_id in ids:
        assert f"ID: {doc_id}" in text



def test_no_ref_created_and_universe_unchanged():
    parsed = _input()
    expected = set(parsed.entities) | {
        r for e in parsed.evidence for r in e.ffo_references
    }
    assert set(ffo_universe(parsed.entities, parsed.evidence)) == expected
    text = serialize_evidence(parsed.evidence, parsed.entities)
    ref_lines = {line.strip() for line in text.splitlines()} & expected
    assert ref_lines == expected


def _item_ref_lines(text):
    lines = text.splitlines()
    refs = []
    in_refs = False
    for line in lines:
        if line.strip() == "FFO refs:":
            in_refs = True
            continue
        if in_refs:
            if ": " in line or not line.strip():
                in_refs = False
            else:
                refs.append(line.strip())
    return refs


def test_delimiter_free_over_full_corpus():
    evidence = _full_corpus_evidence()
    assert len(evidence) == 76
    universe = set(ffo_universe((), evidence))
    text = serialize_evidence(evidence)
    assert _inventory_lines(text) == sorted(universe)
    item_refs = _item_ref_lines(text)
    assert item_refs, "expected per-item FFO ref lines"
    for ref in item_refs:
        assert ref in universe or ref == "none", f"non-universe ref line: {ref}"
        assert ref == ref.strip()
        assert not (ref[0] in "<[(" and ref[-1] in ">])")
        assert not ref.endswith(",")


def test_universe_deterministic():
    parsed = _input()
    once = ffo_universe(parsed.entities, parsed.evidence)
    again = ffo_universe(list(reversed(parsed.entities)), list(reversed(parsed.evidence)))
    assert once == again == sorted(once)


# --- rejection (validator unchanged, still authoritative) ---


def test_each_ref_individually_addressable():
    for ref in ("denim", "jeans", "textile"):
        bad = _output()
        bad["conclusions"][0]["ffo_refs"] = [ref]
        assert _reason(bad).conclusions[0].ffo_refs == (ref,)


def test_evidence_id_cannot_become_ref():
    bad = _output()
    bad["conclusions"][0]["ffo_refs"] = ["term-denim"]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_label_cannot_become_ref():
    bad = _output()
    bad["conclusions"][0]["ffo_refs"] = ["blue jeans"]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_content_cannot_become_ref():
    bad = _output()
    bad["conclusions"][0]["ffo_refs"] = ["durability=high, name=denim"]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_comma_mashed_and_delimited_refs_rejected():
    for refs in (["denim, textile"], ["<denim>"], ["[denim]"], ["(denim)"], ["DENIM"]):
        bad = _output()
        bad["conclusions"][0]["ffo_refs"] = refs
        with pytest.raises(ReasoningExecutionError) as caught:
            _reason(bad)
        assert caught.value.category == "invalid_output"


def test_empty_and_none_refs_rejected():
    for refs in ([""], ["none"], ["  "]):
        bad = _output()
        bad["conclusions"][0]["ffo_refs"] = refs
        with pytest.raises(ReasoningExecutionError) as caught:
            _reason(bad)
        assert caught.value.category == "invalid_output"


def test_doc_id_style_ref_rejected():
    bad = _output()
    bad["conclusions"][0]["ffo_refs"] = ["alias-jeans"]
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(bad)
    assert caught.value.category == "invalid_output"


def test_user_prompt_carries_ffo_inventory():
    assert "Valid FFO references:" in build_user_prompt(_input())


# --- Phase 3J: query-scope rule present, all 3H constraints preserved ---


def test_query_scope_rule_present():
    from app.ai.reasoning_prompt import build_system_prompt

    rule = (
        "Keep every conclusion and ffo_ref strictly scoped to the user query "
        "in section A of the user message; do not add adjacent, broader, "
        "narrower, or merely related concepts unless the query or the cited "
        "evidence explicitly requires them."
    )
    assert rule in build_system_prompt()


def test_3h_prompt_constraints_preserved():
    from app.ai.reasoning_prompt import build_system_prompt

    system = build_system_prompt()
    user = build_user_prompt(_input())
    for kept in (
        "Valid evidence IDs list in section C",
        "Valid FFO references list in section C",
        "Echo the versions object from section D exactly",
        "Return ONLY that JSON object and nothing else",
        "Answer ONLY from the supplied evidence",
    ):
        assert kept in system, f"3H system rule lost: {kept}"

    for kept in (
        "Valid evidence IDs:",
        "Valid FFO references:",
        "Echo the versions object exactly as shown above",
        "max_conclusions:",
        "different namespaces",
    ):
        assert kept in user, f"3H user-prompt element lost: {kept}"
