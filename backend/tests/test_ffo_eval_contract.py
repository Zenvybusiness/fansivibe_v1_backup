"""Phase 3L focused tests — reference evaluation contract.

No Ollama: evaluator asserted directly with handcrafted outputs; corpus
checks run against Seed v0.1. Covers canonical refs, accepted aliases,
kind roles, rel endpoints, extras (still FP), misses (recall), the three
empty-cited combinations, rule effects, and invalid/doc_id refs.
"""

from __future__ import annotations

import pytest

from app.data.ffo import corpus
from app.domain.services.ffo_benchmark import (
    FFO_REF_ROLES,
    BenchmarkError,
    evaluate,
    load_benchmark,
    validate_case,
)
from app.domain.services.ffo_reasoning import corpus_digest
from app.domain.services.ffo_retrieval import ffo_references, retrieve

VERSIONS = {
    "ffo_version": "1.0",
    "corpus_digest": corpus_digest({"term-denim": 1}, "1.0"),
    "evidence_schema": "evidence-pack/1",
    "reasoning_contract_version": "2.0",
}


def _by_id(case_id):
    return next(c for c in load_benchmark()["cases"] if c["case_id"] == case_id)


def _input(intent="explain"):
    return {"request": {"query": "q", "intent": intent}, "versions": dict(VERSIONS)}


def _conclusion(ids=("term-denim",), refs=("denim", "textile"), standing="supported"):
    return {
        "statement": "s",
        "evidence_ids": list(ids),
        "ffo_refs": list(refs),
        "reasoning_note": "n",
        "standing": standing,
    }


def _output(conclusions=(), **overrides):
    data = {
        "answer": "a",
        "conclusions": list(conclusions),
        "uncertainties": [],
        "missing_evidence": [],
        "contradictions": [],
        "confidence": "high",
        "unsupported": False,
        "versions": dict(VERSIONS),
    }
    data.update(overrides)
    return data


def _ffo(case_id, refs):
    case = _by_id(case_id)
    out = _output(conclusions=[_conclusion(ids=tuple(case["expected_evidence_ids"]) or ("x",), refs=refs)])
    return evaluate(case, _input(case["expected_intent"]), out)


# --- G1/G6: canonical + relationship endpoints score perfectly ---


def test_canonical_reference():
    result = _ffo("exp-denim-textile", ("denim", "textile"))
    assert result.metrics["ffo_correctness"]["score"] == 1.0
    assert result.metrics["ffo_recall"]["score"] == 1.0


def test_relationship_endpoints():
    result = _ffo("unc-grunge-origins", ("grunge", "punk"))
    assert result.metrics["ffo_correctness"]["score"] == 1.0
    assert result.metrics["ffo_recall"]["score"] == 1.0


# --- G2/G3: accepted alias passes as its canonical; non-alias rejected ---


def test_accepted_alias_counts_with_canonical_detail():
    result = _ffo("idn-wine-color", ("wine",))
    assert result.metrics["ffo_correctness"]["score"] == 1.0
    # recall is literal over the accepted set: wine covers 1 of 2
    assert result.metrics["ffo_recall"]["score"] == 0.5
    detail = result.metrics["ffo_correctness"]["detail"]
    assert detail["alias_hits"] == ["wine"]
    assert detail["canonical_hits"] == []
    # canonical stays preferred: mixed citation keeps both visible
    mixed = _ffo("idn-wine-color", ("burgundy", "wine"))
    assert mixed.metrics["ffo_correctness"]["score"] == 1.0
    assert mixed.metrics["ffo_correctness"]["detail"]["canonical_hits"] == ["burgundy"]


def test_rejected_non_alias():
    result = _ffo("idn-wine-color", ("wine-color",))
    assert result.metrics["ffo_correctness"]["score"] == 0.0
    assert result.metrics["ffo_recall"]["score"] == 0.0


def test_accepted_aliases_are_real_ffo_aliases():
    alias_data = {}
    for doc in corpus.load_documents():
        if doc.get("doc_type") == "alias":
            alias_data.setdefault(doc["canonical_id"], []).append(doc["alias"])
    for case in load_benchmark()["cases"]:
        for canonical, variants in case.get("accepted_aliases", {}).items():
            for variant in variants:
                assert variant in alias_data.get(canonical, []), (case["case_id"], variant)


# --- G4/G5: entity_kind explicitly expected vs not expected ---


def test_entity_kind_explicitly_expected():
    result = _ffo("exp-denim-textile", ("denim", "textile"))
    assert result.metrics["ffo_correctness"]["score"] == 1.0
    assert _by_id("exp-denim-textile")["ffo_ref_roles"]["textile"] == "entity_kind"


def test_entity_kind_not_expected_is_fp():
    result = _ffo("idn-trench", ("trench-coat", "garment"))
    assert result.metrics["ffo_correctness"]["score"] == 0.5
    assert "garment" not in _by_id("idn-trench").get("ffo_ref_roles", {})


# --- G7/G8: extra valid-but-unexpected ref is FP; missing ref hits recall ---


def test_extra_valid_but_unexpected_reference():
    result = _ffo("exp-denim-textile", ("denim", "textile", "garment"))
    assert result.metrics["ffo_correctness"]["score"] == pytest.approx(2 / 3)
    assert result.metrics["ffo_recall"]["score"] == 1.0


def test_missing_reference():
    result = _ffo("exp-denim-textile", ("denim",))
    assert result.metrics["ffo_correctness"]["score"] == 1.0
    assert result.metrics["ffo_recall"]["score"] == 0.5
    assert result.metrics["ffo_correctness"]["detail"]["missed"] == ["textile"]


# --- G9/G10: empty-cited combinations ---


def test_empty_cited_nonempty_expected_fails():
    result = _ffo("exp-denim-textile", ())
    assert result.metrics["ffo_correctness"]["score"] == 0.0
    assert result.metrics["ffo_recall"]["score"] == 0.0
    assert result.metrics["ffo_correctness"]["pass"] is False


def test_empty_cited_empty_expected_passes():
    case = _by_id("ins-kimono-sizing")
    out = _output(unsupported=False, missing_evidence=["m"])
    result = evaluate(case, _input("explain"), out)
    assert result.metrics["ffo_correctness"]["score"] == 1.0
    assert result.metrics["ffo_recall"]["score"] == 1.0


def test_noncited_when_none_expected_fails_correctness():
    case = _by_id("ins-kimono-sizing")
    out = _output(
        conclusions=[_conclusion(ids=("term-denim",), refs=("denim",))],
        missing_evidence=["m"],
    )
    result = evaluate(case, _input("explain"), out)
    assert result.metrics["ffo_correctness"]["score"] == 0.0
    assert result.metrics["ffo_recall"]["score"] == 1.0


# --- G11: rule effect reference ---


def test_rule_effect_is_referenceable():
    docs = {d["doc_id"]: d for d in corpus.load_documents()}
    assert ffo_references(docs["rule-fitted-wide-balanced"]) == ["balanced_volume"]
    assert ffo_references(docs["rule-cropped-highrise-legline"]) == ["elongated_leg_line"]
    result = _ffo("anx-volume-balance", ("balanced_volume",))
    assert result.metrics["ffo_correctness"]["score"] == 1.0
    assert result.metrics["ffo_recall"]["score"] == 1.0
    assert _by_id("anx-volume-balance")["ffo_ref_roles"] == {"balanced_volume": "rule_effect"}


def test_rule_effect_retrieved_with_evidence():
    pack = retrieve("balanced_volume")
    by_id = {item.doc_id: item for item in pack.items}
    assert "balanced_volume" in by_id["rule-fitted-wide-balanced"].ffo_references


# --- G12: invalid/doc_id reference ---


def test_invalid_doc_id_reference():
    result = _ffo("exp-denim-textile", ("term-denim",))
    assert result.metrics["ffo_correctness"]["score"] == 0.0
    assert result.metrics["ffo_recall"]["score"] == 0.0


# --- contract shape ---


def test_roles_cover_expected_refs_where_tagged():
    for case in load_benchmark()["cases"]:
        roles = case.get("ffo_ref_roles", {})
        for role in roles.values():
            assert role in FFO_REF_ROLES, (case["case_id"], role)


def test_bad_contract_shapes_rejected():
    base = dict(_by_id("idn-wine-color"))
    bad_alias = dict(base, accepted_aliases={"wine": ["vino"]})
    with pytest.raises(BenchmarkError, match="not expected"):
        validate_case(bad_alias)
    bad_dup = dict(base, accepted_aliases={"burgundy": ["burgundy"]})
    with pytest.raises(BenchmarkError, match="duplicates"):
        validate_case(bad_dup)
    bad_role = dict(base, ffo_ref_roles={"burgundy": "hypernym"})
    with pytest.raises(BenchmarkError, match="role"):
        validate_case(bad_role)
