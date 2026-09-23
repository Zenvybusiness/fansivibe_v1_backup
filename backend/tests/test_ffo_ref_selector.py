"""Phase 3P unit tests — role-aware FFO reference selector.

No Ollama except via `httpx.MockTransport` for the adapter-immutability
and invalid-passthrough tests. The selector is a pure remove-only filter;
the validator remains the authority that rejects invalid refs.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from app.ai.ollama_reasoner import (
    OllamaFashionReasoner,
    ReasoningConfig,
    ReasoningExecutionError,
)
from app.ai.reasoning_prompt import build_user_prompt
from app.data.ffo import corpus
from app.domain.services.ffo_reasoning import (
    REASONING_CONTRACT_VERSION,
    ReasoningEvidence,
    corpus_digest,
    validate_input,
)
from app.domain.services.ffo_ref_selector import (
    ALIAS_KEEP,
    CANONICAL_KEEP,
    KIND_SHARED_CANONICAL_KEEP,
    KIND_STATEMENT_MATCH_KEEP,
    KIND_UNLINKED_DROP,
    RELATIONSHIP_ENDPOINT_KEEP,
    RULE_EFFECT_KEEP,
    UNRECOGNIZED_PASSTHROUGH_KEEP,
    select_refs,
)

VERSIONS = {
    "ffo_version": "1.0",
    "corpus_digest": corpus_digest({"term-denim": 1}, "1.0"),
    "evidence_schema": "evidence-pack/1",
    "reasoning_contract_version": REASONING_CONTRACT_VERSION,
}


def _ev(doc_id, doc_type, refs, content):
    return SimpleNamespace(
        doc_id=doc_id, doc_type=doc_type, ffo_references=list(refs), content=dict(content),
    )


TERM_DENIM = _ev("term-denim", "term", ["denim", "textile"], {
    "doc_id": "term-denim", "entity_kind": "textile", "canonical_id": "denim", "payload": {}})
TERM_LINEN = _ev("term-linen", "term", ["linen", "material"], {
    "doc_id": "term-linen", "entity_kind": "material", "canonical_id": "linen", "payload": {}})
TERM_COTTON = _ev("term-cotton", "term", ["cotton", "material"], {
    "doc_id": "term-cotton", "entity_kind": "material", "canonical_id": "cotton", "payload": {}})
ALIAS_WINE = _ev("alias-wine", "alias", ["burgundy", "wine", "color"], {
    "doc_id": "alias-wine", "alias": "wine", "canonical_id": "burgundy"})
REL = _ev("rel-grunge-influenced-punk", "relationship", ["grunge", "punk"], {
    "doc_id": "rel-grunge-influenced-punk", "rel_type": "INFLUENCED",
    "subject": "grunge", "object": "punk"})
RULE = _ev("rule-fitted-wide-balanced", "rule", ["balanced_volume"], {
    "doc_id": "rule-fitted-wide-balanced",
    "payload": {"when": {"top": "fitted"}, "effect": "balanced_volume"}})


def _decisions(kept_dec):
    return {d["reference"]: d for d in kept_dec[1]}


def test_canonical_entity_passes():
    kept, decisions = select_refs("Denim is durable.", ["denim"], ["term-denim"], [TERM_DENIM])
    assert kept == ["denim"]
    assert decisions[0]["rule_id"] == CANONICAL_KEEP


def test_alias_passes_unsilently():
    kept, decisions = select_refs("Wine is nice.", ["burgundy", "wine"], ["alias-wine"], [ALIAS_WINE])
    assert kept == ["burgundy", "wine"]
    assert _decisions((kept, decisions))["wine"]["rule_id"] == ALIAS_KEEP


def test_relationship_endpoint_passes():
    kept, _ = select_refs("Grunge influenced punk.", ["grunge", "punk"],
                           ["rel-grunge-influenced-punk"], [REL])
    assert kept == ["grunge", "punk"]


def test_rule_effect_passes():
    kept, decisions = select_refs("Volume is balanced.", ["balanced_volume"],
                                  ["rule-fitted-wide-balanced"], [RULE])
    assert kept == ["balanced_volume"]
    assert decisions[0]["rule_id"] == RULE_EFFECT_KEEP


def test_kind_present_in_conclusion_passes():
    kept, decisions = select_refs("Denim is a type of textile.", ["denim", "textile"],
                                  ["term-denim"], [TERM_DENIM])
    assert kept == ["denim", "textile"]
    assert _decisions((kept, decisions))["textile"]["rule_id"] == KIND_STATEMENT_MATCH_KEEP


def test_kind_absent_single_canonical_drops():
    kept, decisions = select_refs("Trench coat is outerwear.", ["trench-coat", "garment"],
                                  ["term-trench-coat"], [_ev(
                                      "term-trench-coat", "term", ["trench-coat", "garment"],
                                      {"doc_id": "t", "entity_kind": "garment",
                                       "canonical_id": "trench-coat", "payload": {}})])
    assert kept == ["trench-coat"]
    drop = _decisions((kept, decisions))["garment"]
    assert (drop["action"], drop["rule_id"]) == ("drop", KIND_UNLINKED_DROP)


def test_shared_kind_across_two_canonicals_passes():
    kept, decisions = select_refs("Cotton and linen are natural fibers.",
                                  ["cotton", "linen", "material"],
                                  ["term-cotton", "term-linen"], [TERM_COTTON, TERM_LINEN])
    assert kept == ["cotton", "linen", "material"]
    assert _decisions((kept, decisions))["material"]["rule_id"] == KIND_SHARED_CANONICAL_KEEP


def test_word_boundary_behavior():
    pack = [_ev("t", "term", ["x", "garment"],
                {"doc_id": "t", "entity_kind": "garment", "canonical_id": "x", "payload": {}})]
    kept, _ = select_refs("Jeans and other garments.", ["x", "garment"], ["t"], pack)
    assert kept == ["x"]


def test_case_insensitive_behavior():
    kept, _ = select_refs("Denim is a TEXTILE.", ["denim", "textile"],
                          ["term-denim"], [TERM_DENIM])
    assert kept == ["denim", "textile"]


def test_no_stemming():
    pack = [_ev("t", "term", ["x", "fit"],
                {"doc_id": "t", "entity_kind": "fit", "canonical_id": "x", "payload": {}})]
    kept, _ = select_refs("These fits are relaxed.", ["x", "fit"], ["t"], pack)
    assert kept == ["x"]


def test_plural_non_exact_forms():
    kept, _ = select_refs("Natural materials.", ["cotton", "material"],
                          ["term-cotton"], [TERM_COTTON])
    assert kept == ["cotton"]


def test_remove_only_invariant():
    cases = [
        ("s", ["denim", "textile", "ghost"], ["term-denim"], [TERM_DENIM]),
        ("s", ["wine", "burgundy"], ["alias-wine"], [ALIAS_WINE]),
        ("s", [], ["term-denim"], [TERM_DENIM]),
    ]
    for stmt, refs, ids, pack in cases:
        kept, _ = select_refs(stmt, refs, ids, pack)
        assert set(kept) <= set(refs)


def _real_evidence(*doc_ids):
    from app.domain.services.ffo_retrieval import ffo_references as _refs

    docs = {d["doc_id"]: d for d in corpus.load_documents()}
    out = []
    for doc_id in doc_ids:
        record = {
            "doc_id": doc_id, "doc_type": docs[doc_id]["doc_type"], "label": doc_id,
            "reason": "test", "lexical_score": None, "semantic_score": None,
            "ffo_references": _refs(docs[doc_id]),
            "provenance": {}, "confidence": 0.5,
            "status": "published", "content": corpus.evidence_content(docs[doc_id]),
        }
        out.append(ReasoningEvidence(**record))
    return out


@pytest.mark.parametrize("doc_ids,statement,refs", [
    (("term-denim",), "Denim is a type of textile.", ["denim", "textile"]),
    (("term-burgundy",), "Burgundy is a color.", ["burgundy", "color"]),
    (("term-chelsea-boots",), "A Chelsea boot is a type of footwear.",
     ["chelsea-boots", "footwear"]),
    (("term-cotton", "term-linen"), "Cotton and linen are both natural fibers.",
     ["cotton", "linen", "material"]),
])
def test_legitimate_3m_kind_cases_retained(doc_ids, statement, refs):
    evidence = _real_evidence(*doc_ids)
    kept, _ = select_refs(statement, refs, list(doc_ids), evidence)
    assert kept == refs


# --- adapter-level: immutability + invalid passthrough ---


def _adapter_input():
    data = {
        "request": {"query": "what is denim", "intent": "explain"},
        "context": {},
        "entities": ["denim"],
        "evidence": [{
            "doc_id": "term-denim", "doc_type": "term", "label": "denim",
            "reason": "exact_canonical", "lexical_score": 700, "semantic_score": None,
            "ffo_references": ["denim", "textile"],
            "provenance": {"source": "s", "source_type": "AUTHORITATIVE", "confidence": 0.9},
            "confidence": 0.9, "status": "published",
            "content": {"doc_id": "term-denim", "entity_kind": "textile",
                        "canonical_id": "denim", "payload": {"name": "denim"}},
        }],
        "constraints": {"evidence_only": True, "max_conclusions": 3},
        "requirements": {"include_reasoning_notes": True},
        "versions": dict(VERSIONS),
    }
    return validate_input(data)


def _reason(payload, reasoning_input=None):
    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(payload)}}
        )

    adapter = OllamaFashionReasoner(
        ReasoningConfig(model="m"),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return adapter.reason(reasoning_input or _adapter_input())


def _valid_output(refs):
    return {
        "answer": "Denim is a durable textile.",
        "conclusions": [{
            "statement": "Denim is durable.",
            "evidence_ids": ["term-denim"],
            "ffo_refs": refs,
            "reasoning_note": "n",
            "standing": "supported",
            "admission": {
                "subject_ref": "denim",
                "atomic_claims": [
                    {"text": "Denim is durable.",
                     "cited_doc_ids": ["term-denim"]}
                ],
            },
        }],
        "uncertainties": [], "missing_evidence": [], "contradictions": [],
        "confidence": "high", "unsupported": False, "versions": dict(VERSIONS),
    }


def test_adapter_filters_kind_but_preserves_everything_else():
    out = _reason(_valid_output(["denim", "textile"]))
    assert out.conclusions[0].ffo_refs == ("denim",)
    assert out.conclusions[0].statement == "Denim is durable."
    assert out.conclusions[0].evidence_ids == ("term-denim",)
    assert out.conclusions[0].reasoning_note == "n"
    assert out.conclusions[0].standing == "supported"
    assert out.answer == "Denim is a durable textile."
    assert out.confidence == "high"
    assert out.versions.to_dict() == VERSIONS


def test_adapter_input_evidence_unchanged():
    parsed = _adapter_input()
    before = parsed.to_dict()
    _reason(_valid_output(["denim", "textile"]), parsed)
    assert parsed.to_dict() == before


def test_invalid_invented_refs_remain_invalid():
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(_valid_output(["dark_denim_jeans"]))
    assert caught.value.category == "invalid_output"


def test_relationship_text_refs_remain_invalid():
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(_valid_output(["white-sneakers PAIRS_WITH dark-denim-jeans"]))
    assert caught.value.category == "invalid_output"


def test_rule_effect_not_synthesized():
    kept, _ = select_refs("Volume is balanced.", ["balanced_volume"],
                          ["term-denim"], [TERM_DENIM])
    assert kept == ["balanced_volume"]  # valid universe ref passes through...
    kept2, decisions2 = select_refs("Volume is balanced.", ["balanced_volume"],
                                    ["rule-fitted-wide-balanced"], [RULE, TERM_DENIM])
    assert kept2 == ["balanced_volume"]
    assert decisions2[0]["rule_id"] == RULE_EFFECT_KEEP
    # ...but the selector never invents it when unproposed
    kept3, _ = select_refs("Volume is balanced.", ["denim"], ["term-denim"], [TERM_DENIM])
    assert kept3 == ["denim"]
