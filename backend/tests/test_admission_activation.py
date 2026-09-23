"""Phase 3U activation tests — 3T wired into the live Ollama path.

No live Ollama: `httpx.MockTransport` serves controlled model JSON.
3T and 3P are exercised, never modified. Prompt pins assert the minimal
admission-record schema addition; pipeline tests assert execution order
(admission BEFORE 3P) and byte-stability of 3P for admitted conclusions.
"""

from __future__ import annotations

import copy
import json

import httpx
import pytest

from app.ai.ollama_reasoner import OllamaFashionReasoner, ReasoningConfig, ReasoningExecutionError
from app.ai.reasoning_prompt import build_system_prompt, build_user_prompt
from app.domain.services.conclusion_admission import (
    EDGE_ADMIT,
    NON_TARGET_NO_EDGE,
    TARGET_ADMIT,
)
from app.domain.services.ffo_reasoning import (
    REASONING_CONTRACT_VERSION,
    corpus_digest,
    validate_input,
)
from app.domain.services.ffo_ref_selector import select_refs

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
        "content": {"doc_id": "term-denim", "entity_kind": "textile",
                    "canonical_id": "denim", "payload": {"name": "denim"}},
    },
    {
        "doc_id": "term-dark-denim-jeans",
        "doc_type": "term",
        "label": "dark denim jeans",
        "reason": "lexical",
        "lexical_score": 500,
        "semantic_score": None,
        "ffo_references": ["dark-denim-jeans", "garment"],
        "provenance": {"source": "s", "source_type": "AUTHORITATIVE", "confidence": 0.9},
        "confidence": 0.9,
        "status": "published",
        "content": {"doc_id": "term-dark-denim-jeans", "entity_kind": "garment",
                    "canonical_id": "dark-denim-jeans", "payload": {}},
    },
    {
        "doc_id": "rel-denim-made-from-cotton",
        "doc_type": "relationship",
        "label": "denim made from cotton",
        "reason": "lexical",
        "lexical_score": 500,
        "semantic_score": None,
        "ffo_references": ["denim", "cotton"],
        "provenance": {"source": "s", "source_type": "AUTHORITATIVE", "confidence": 0.9},
        "confidence": 0.9,
        "status": "published",
        "content": {"doc_id": "rel-denim-made-from-cotton", "rel_type": "MADE_FROM",
                    "subject": "denim", "object": "cotton"},
    },
]


def _input(**overrides):
    data = {
        "request": {"query": "denim", "intent": "analyze"},
        "context": {},
        "entities": ["denim"],
        "evidence": [dict(e) for e in EVIDENCE],
        "constraints": {"evidence_only": True, "max_conclusions": 3},
        "requirements": {"include_reasoning_notes": True},
        "versions": dict(VERSIONS),
    }
    data.update(overrides)
    return validate_input(data)


def _rec(subject, *claims):
    return {"subject_ref": subject,
            "atomic_claims": [{"text": t, "cited_doc_ids": list(d)} for t, d in claims]}


def _conc(statement, eids, refs, record):
    conclusion = {"statement": statement, "evidence_ids": list(eids),
                  "ffo_refs": list(refs), "reasoning_note": "n",
                  "standing": "supported"}
    if record is not None:
        conclusion["admission"] = record
    return conclusion


def _output(*conclusions):
    return {
        "answer": "Denim analysis.",
        "conclusions": list(conclusions),
        "uncertainties": [], "missing_evidence": [], "contradictions": [],
        "confidence": "high", "unsupported": False, "versions": dict(VERSIONS),
    }


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


GOOD_RECORD = _rec("denim", ("Denim is made from cotton.",
                              ["term-denim", "rel-denim-made-from-cotton"]))


# ---- E1: prompt carries the admission-record schema ----

def test_e1_system_prompt_requires_admission_records():
    prompt = build_system_prompt()
    assert "admission record" in prompt
    assert "same order as conclusions" in prompt


def test_e1_user_prompt_contract_has_admission_schema():
    prompt = build_user_prompt(_input())
    assert '"admission"' in prompt
    assert '"subject_ref"' in prompt
    assert '"atomic_claims"' in prompt
    assert '"cited_doc_ids"' in prompt


# ---- E2/E7: valid records accepted, target admitted ----

def test_e2_valid_records_accepted_target_admitted():
    out = _reason(_output(_conc("Denim is made from cotton.",
                                ["term-denim", "rel-denim-made-from-cotton"],
                                ["denim", "cotton"], GOOD_RECORD)))
    assert len(out.conclusions) == 1
    assert out.conclusions[0].statement == "Denim is made from cotton."


def test_e7_admission_result_marks_target_admit():
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"))
    parsed_in = _input()
    from app.domain.services.ffo_reasoning import validate_output
    output = validate_output(_output(_conc("Denim is made from cotton.",
                                           ["term-denim"], ["denim"], GOOD_RECORD)),
                             input=parsed_in)
    result = adapter._admission_result(output, parsed_in, adapter._admission_records(
        _output(_conc("Denim is made from cotton.", ["term-denim"], ["denim"],
                      GOOD_RECORD))))
    assert result["outcomes"][0]["reason"] == TARGET_ADMIT


# ---- E3/E4/E5: fail-closed paths ----

def test_e3_missing_record_fails_closed():
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(_output(_conc("Denim is made from cotton.", ["term-denim"],
                              ["denim"], None)))
    assert caught.value.category == "invalid_output"
    assert "admission" in str(caught.value)


def test_e4_unknown_evidence_id_rejected_to_insufficient():
    record = _rec("denim", ("Denim.", [None]))
    out = _reason(_output(_conc("Denim.", ["term-denim"], ["denim"], record)))
    assert out.conclusions == ()
    assert out.missing_evidence != ()


def test_e5_out_of_pack_evidence_rejected_to_insufficient():
    record = _rec("denim", ("Denim.", ["term-silk"]))
    out = _reason(_output(_conc("Denim.", ["term-denim"], ["denim"], record)))
    assert out.conclusions == ()
    assert any("denim" in m for m in out.missing_evidence)


# ---- E6/E8/E9: edge licensing through the live path ----

def test_e6_non_target_without_edge_rejected():
    record = _rec("dark-denim-jeans",
                  ("Dark denim jeans are slim.", ["term-dark-denim-jeans"]))
    out = _reason(_output(_conc("Dark denim jeans are slim.",
                                ["term-dark-denim-jeans"], ["dark-denim-jeans"],
                                record)))
    assert out.conclusions == ()
    assert any("denim" in m for m in out.missing_evidence)


def test_e8_relationship_edge_admits_non_target():
    record = _rec("cotton", ("Cotton makes denim.",
                             ["rel-denim-made-from-cotton"]))
    out = _reason(_output(_conc("Cotton makes denim.",
                                ["rel-denim-made-from-cotton"], ["denim", "cotton"],
                                record)))
    assert len(out.conclusions) == 1


def test_e9_cooccurrence_alone_does_not_admit():
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"))
    parsed_in = _input()
    from app.domain.services.ffo_reasoning import validate_output
    raw = _output(_conc("Dark denim jeans are slim.", ["term-dark-denim-jeans"],
                        ["dark-denim-jeans"],
                        _rec("dark-denim-jeans",
                             ("Dark denim jeans are slim.", ["term-dark-denim-jeans"]))))
    output = validate_output(raw, input=parsed_in)
    result = adapter._admission_result(output, parsed_in,
                                       adapter._admission_records(raw))
    assert result["outcomes"][0]["reason"] == NON_TARGET_NO_EDGE


# ---- E10: duplicates ----

def test_e10_duplicate_conclusion_rejected():
    conc = _conc("Denim is made from cotton.", ["term-denim"], ["denim"],
                 copy.deepcopy(GOOD_RECORD))
    out = _reason(_output(conc, copy.deepcopy(conc)))
    assert len(out.conclusions) == 1


# ---- E11/E12: 3T controls survive activation ----

def test_e11_positive_control_survives_activation():
    out = _reason(_output(_conc("Denim is made from cotton.",
                                ["term-denim", "rel-denim-made-from-cotton"],
                                ["denim", "cotton"], GOOD_RECORD)))
    assert len(out.conclusions) == 1
    assert out.conclusions[0].ffo_refs == ("denim", "cotton")


def test_e12_negative_control_rejected():
    record = _rec("dark-denim-jeans",
                  ("Dark denim jeans are slim.", ["term-dark-denim-jeans"]))
    out = _reason(_output(_conc("Dark denim jeans are slim.",
                                ["term-dark-denim-jeans"], ["dark-denim-jeans"],
                                record)))
    assert out.conclusions == ()


# ---- E13/E14/E15: order + 3P byte-stability ----

def test_e13_rejected_never_reach_3p_e14_admitted_do():
    from types import SimpleNamespace
    from app.domain.services.ffo_reasoning import validate_output
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"))
    parsed_in = _input()
    raw = _output(
        _conc("Denim is made from cotton.", ["term-denim"], ["denim"],
              copy.deepcopy(GOOD_RECORD)),
        _conc("Dark denim jeans are slim.", ["term-dark-denim-jeans"],
              ["dark-denim-jeans"],
              _rec("dark-denim-jeans",
                   ("Dark denim jeans are slim.", ["term-dark-denim-jeans"]))),
    )
    output = validate_output(raw, input=parsed_in)
    result = adapter._admission_result(output, parsed_in,
                                       adapter._admission_records(raw))
    assert [o["outcome"] for o in result["outcomes"]] == ["admit", "reject"]
    # Only admitted conclusions are handed to frozen 3P.
    ns_pack = [SimpleNamespace(**e) for e in EVIDENCE]
    seen = []
    for conc in result["admitted"]:
        kept, _ = select_refs(conc.statement, list(conc.ffo_refs),
                              list(conc.evidence_ids), ns_pack, "denim", "analyze")
        seen.append((conc.statement, tuple(kept)))
    assert [s for s, _ in seen] == ["Denim is made from cotton."]
    assert all("dark-denim-jeans" not in refs for _, refs in seen)


def test_e15_3p_byte_stable_for_admitted():
    from types import SimpleNamespace
    ns_pack = [SimpleNamespace(**e) for e in EVIDENCE]
    out = _reason(_output(_conc("Denim is made from cotton.",
                                ["term-denim", "rel-denim-made-from-cotton"],
                                ["denim", "cotton"], GOOD_RECORD)))
    direct, _ = select_refs("Denim is made from cotton.", ["denim", "cotton"],
                            ["term-denim", "rel-denim-made-from-cotton"],
                            ns_pack, "denim", "analyze")
    assert list(out.conclusions[0].ffo_refs) == direct


# ---- E16/E17/E18: immutability through activation ----

def test_e16_statements_unchanged_e17_evidence_ids_unchanged():
    out = _reason(_output(_conc("Denim is made from cotton.",
                                ["term-denim", "rel-denim-made-from-cotton"],
                                ["denim", "cotton"], GOOD_RECORD)))
    assert out.conclusions[0].statement == "Denim is made from cotton."
    assert out.conclusions[0].evidence_ids == ("term-denim", "rel-denim-made-from-cotton")


def test_e18_no_refs_invented_by_admission():
    out = _reason(_output(_conc("Denim is made from cotton.",
                                ["term-denim", "rel-denim-made-from-cotton"],
                                ["denim", "cotton"], GOOD_RECORD)))
    assert set(out.conclusions[0].ffo_refs) <= {"denim", "cotton"}


# ---- E19: invalid FFO refs still invalid ----

def test_e19_invalid_ffo_refs_remain_invalid():
    bad = _conc("Denim.", ["term-denim"], ["silk-denim"], GOOD_RECORD)
    with pytest.raises(ReasoningExecutionError) as caught:
        _reason(_output(bad))
    assert caught.value.category == "invalid_output"


# ---- E20: evidence pack untouched ----

def test_e20_evidence_pack_not_modified():
    parsed_in = _input()
    before = parsed_in.to_dict()
    _reason(_output(_conc("Denim is made from cotton.",
                          ["term-denim", "rel-denim-made-from-cotton"],
                          ["denim", "cotton"], GOOD_RECORD)),
            parsed_in)
    assert parsed_in.to_dict() == before


# ---- order proof: admission precedes 3P inside reason() ----

def test_execution_order_admission_before_3p():
    calls = []
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"))
    real_admission = adapter._apply_admission
    real_select = adapter._select_refs

    def tracked_admission(output, reasoning_input, records):
        calls.append("admission")
        return real_admission(output, reasoning_input, records)

    def tracked_select(output, reasoning_input):
        calls.append("3P")
        return real_select(output, reasoning_input)

    adapter._apply_admission = tracked_admission
    adapter._select_refs = tracked_select

    def handler(request):
        return httpx.Response(
            200, json={"model": "m", "message": {"content": json.dumps(
                _output(_conc("Denim is made from cotton.",
                              ["term-denim", "rel-denim-made-from-cotton"],
                              ["denim", "cotton"], GOOD_RECORD)))}})
    adapter._client = httpx.Client(transport=httpx.MockTransport(handler))
    adapter.reason(_input())
    assert calls == ["admission", "3P"]


RULE_EVIDENCE = {
    "doc_id": "rule-fitted-wide-balanced",
    "doc_type": "rule",
    "label": "fitted wide balanced",
    "reason": "lexical",
    "lexical_score": 500,
    "semantic_score": None,
    "ffo_references": ["balanced_volume"],
    "provenance": {"source": "s", "source_type": "AUTHORITATIVE", "confidence": 0.75},
    "confidence": 0.75,
    "status": "published",
    "content": {"doc_id": "rule-fitted-wide-balanced",
                "payload": {"effect": "balanced_volume",
                            "when": {"bottom": "wide", "top": "fitted"}}},
}


def test_g_rule_effect_admitted_reaches_3p_unchanged():
    parsed_in = _input(request={"query": "balanced volume", "intent": "analyze"},
                       evidence=[dict(RULE_EVIDENCE)])
    record = _rec("balanced_volume",
                  ("Wide bottom plus fitted top balances volume.",
                   ["rule-fitted-wide-balanced"]))
    out = _reason(_output(_conc("Wide bottom plus fitted top balances volume.",
                                ["rule-fitted-wide-balanced"], ["balanced_volume"],
                                record)),
                  parsed_in)
    assert len(out.conclusions) == 1
    assert out.conclusions[0].statement == \
        "Wide bottom plus fitted top balances volume."
    assert out.conclusions[0].evidence_ids == ("rule-fitted-wide-balanced",)
    assert out.conclusions[0].ffo_refs == ("balanced_volume",)


def test_g_malformed_subject_namespace_rejected_live():
    bad = _conc("Denim is made from cotton.", ["term-denim"], ["denim"],
                _rec("[term-denim]", ("Denim is made from cotton.", ["term-denim"])))
    out = _reason(_output(bad))
    # Bracketed subject is not an FFO ref: conclusion dropped (fail closed),
    # 3A insufficient-evidence shape out (never silent repair/normalization).
    assert out.conclusions == ()
    assert any("denim" in m for m in out.missing_evidence)


def test_edge_admit_reason_visible_for_rel_edge():
    adapter = OllamaFashionReasoner(ReasoningConfig(model="m"))
    parsed_in = _input()
    from app.domain.services.ffo_reasoning import validate_output
    raw = _output(_conc("Cotton makes denim.", ["rel-denim-made-from-cotton"],
                        ["denim", "cotton"],
                        _rec("cotton", ("Cotton makes denim.",
                                        ["rel-denim-made-from-cotton"]))))
    output = validate_output(raw, input=parsed_in)
    result = adapter._admission_result(output, parsed_in,
                                       adapter._admission_records(raw))
    assert result["outcomes"][0]["reason"] == EDGE_ADMIT
