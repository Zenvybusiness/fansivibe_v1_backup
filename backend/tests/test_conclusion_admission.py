"""Phase 3T unit tests — conclusion admission contract (deterministic only).

No Ollama, no benchmark, no model. Fixtures mirror real 3Q pack shapes
(doc_ids/content keys match corpus `evidence_content`), but all universes
and packs are constructed inline: no benchmark file is read, so no
benchmark knowledge can leak into the mechanism under test.
"""

from __future__ import annotations

import copy
from types import SimpleNamespace

from app.domain.services.conclusion_admission import (
    ADMIT,
    ALIAS_QUALIFY,
    COVERAGE_FLAG,
    DUPLICATE,
    EDGE_ADMIT,
    EMPTY_CITATION,
    MISSING_RECORD,
    NON_TARGET_NO_EDGE,
    OUT_OF_PACK_DOC,
    QUALIFY,
    REJECT,
    SUBJECT_UNRESOLVED,
    TARGET_ADMIT,
    UNKNOWN_DOC,
    UNSUPPORTED_OUTPUT,
    apply_admission,
    derive_targets,
    resolve_subject,
)
from app.domain.services.ffo_ref_selector import select_refs

UNIVERSE = {
    "canonicals": {
        "denim", "cotton", "linen", "dark-denim-jeans", "wide_leg_jeans",
        "slim-fit", "regular-fit", "relaxed-fit", "streetwear", "classic",
        "japanese-streetwear", "oxford-shirt", "trench-coat", "cropped",
        "elongated_leg_line", "balanced_volume", "burgundy", "polka-dot",
        "white-sneakers", "textile", "material",
    },
    "aliases": {
        "wine": "burgundy",
        "trench": "trench-coat",
        "loose jeans": "wide_leg_jeans",
        "baggy jeans": "wide_leg_jeans",
        "polka dots": "polka-dot",
    },
    "kinds": {"garment", "textile", "material", "fit", "aesthetic", "culture", "color"},
    "effects": {"elongated_leg_line", "balanced_volume"},
}


def _ev(doc_id, doc_type, content):
    return {"doc_id": doc_id, "doc_type": doc_type, "content": dict(content)}


def _term(doc_id, canonical, kind):
    return _ev(doc_id, "term", {"doc_id": doc_id, "canonical_id": canonical,
                                "entity_kind": kind, "payload": {}})


def _rel(doc_id, subject, obj):
    return _ev(doc_id, "relationship", {"doc_id": doc_id, "rel_type": "X",
                                        "subject": subject, "object": obj})


def _rule(doc_id, effect):
    return _ev(doc_id, "rule", {"doc_id": doc_id,
                                "payload": {"effect": effect, "when": {}}})


def _conc(statement, eids, refs=None, standing="supported"):
    return {"statement": statement, "evidence_ids": list(eids),
            "ffo_refs": list(refs or []), "standing": standing}


def _rec(subject, *claims):
    return {"subject_ref": subject,
            "atomic_claims": [{"text": t, "cited_doc_ids": list(d)} for t, d in claims]}


DENIM_PACK = [
    _term("term-denim", "denim", "textile"),
    _term("term-dark-denim-jeans", "dark-denim-jeans", "garment"),
    _term("term-wide-leg-jeans", "wide_leg_jeans", "garment"),
    _rel("rel-denim-made-from-cotton", "denim", "cotton"),
]


def _outcome(res, index=0):
    return res["outcomes"][index]


# ---- target derivation (query text only, never benchmark) ----

def test_targets_single_term():
    assert derive_targets("denim", UNIVERSE, DENIM_PACK) == {"denim"}


def test_targets_comparison_members():
    pack = [_term("term-cotton", "cotton", "material"),
            _term("term-linen", "linen", "material")]
    assert derive_targets("cotton vs linen", UNIVERSE, pack) == {"cotton", "linen"}


def test_targets_exclude_adjacent_pack_members():
    assert "dark-denim-jeans" not in derive_targets("denim", UNIVERSE, DENIM_PACK)
    assert "wide_leg_jeans" not in derive_targets("denim", UNIVERSE, DENIM_PACK)


def test_targets_exclude_unqueried_fit():
    pack = [_term("term-slim-fit", "slim-fit", "fit"),
            _term("term-regular-fit", "regular-fit", "fit"),
            _term("term-relaxed-fit", "relaxed-fit", "fit")]
    targets = derive_targets("slim vs regular fit", UNIVERSE, pack)
    assert targets == {"slim-fit", "regular-fit"}


def test_targets_specific_for_general_excluded():
    pack = [_term("term-streetwear", "streetwear", "aesthetic"),
            _term("term-japanese-streetwear", "japanese-streetwear", "culture")]
    targets = derive_targets("streetwear vs classic", UNIVERSE, pack)
    assert "streetwear" in targets
    assert "japanese-streetwear" not in targets


def test_targets_alias_and_effect():
    assert derive_targets("wine", UNIVERSE, []) == {"burgundy"}
    assert derive_targets("trench", UNIVERSE, []) == {"trench-coat"}
    assert "elongated_leg_line" in derive_targets(
        "elongated leg line from cropped proportions", UNIVERSE, [])
    assert "cropped" in derive_targets(
        "elongated leg line from cropped proportions", UNIVERSE, [])


def test_targets_plural_tolerance():
    assert "fitted-top" in derive_targets(
        "oversized and fitted tops",
        {**UNIVERSE, "canonicals": UNIVERSE["canonicals"] | {"oversized", "fitted-top"}},
        [])


def test_targets_kind_fallback_for_generic_query():
    pack = [_term("term-slim-fit", "slim-fit", "fit"),
            _term("term-regular-fit", "regular-fit", "fit"),
            _term("term-relaxed-fit", "relaxed-fit", "fit")]
    assert derive_targets("fit", UNIVERSE, pack) == {"slim-fit", "regular-fit", "relaxed-fit"}


def test_targets_empty_for_unknown_query():
    assert derive_targets("kimono sizing", UNIVERSE, []) == set()


def test_resolve_subject_canonical_alias_unknown():
    assert resolve_subject("denim", UNIVERSE) == ("denim", False)
    assert resolve_subject("wine", UNIVERSE) == ("burgundy", True)
    assert resolve_subject("silk", UNIVERSE) is None
    assert resolve_subject("", UNIVERSE) is None
    assert resolve_subject(None, UNIVERSE) is None


# ---- A/B: target subjects admitted, alias qualifies ----

def test_a_target_subject_admitted():
    res = apply_admission(
        [_conc("Denim is made from cotton.",
               ["term-denim", "rel-denim-made-from-cotton"], ["denim", "cotton"])],
        [_rec("denim", ("Denim is a textile.", ["term-denim"]),
              ("Denim is made from cotton.", ["rel-denim-made-from-cotton"]))],
        query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert _outcome(res) == {"index": 0, "outcome": ADMIT, "reason": TARGET_ADMIT}
    assert len(res["admitted"]) == 1
    assert res["coverage_flags"] == []


def test_b_alias_subject_qualifies_not_rejects():
    pack = [_ev("alias-wine", "alias", {"doc_id": "alias-wine", "alias": "wine",
                                        "canonical_id": "burgundy"})]
    res = apply_admission(
        [_conc("Burgundy is a wine colour.", ["alias-wine"], ["burgundy", "wine"])],
        [_rec("wine", ("Burgundy is a wine colour.", ["alias-wine"]))],
        query="wine", universe=UNIVERSE, evidence=pack)
    assert _outcome(res) == {"index": 0, "outcome": QUALIFY, "reason": ALIAS_QUALIFY}
    assert len(res["admitted"]) == 1  # qualify still proceeds (to 3P)


def test_subject_unresolved_rejected():
    res = apply_admission(
        [_conc("Silk is smooth.", ["term-denim"], ["silk"])],
        [_rec("silk", ("Silk is smooth.", ["term-denim"]))],
        query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert _outcome(res)["outcome"] == REJECT
    assert _outcome(res)["reason"] == SUBJECT_UNRESOLVED
    assert res["admitted"] == []


# ---- C/D/E/F: edge licensing ----

def test_c_non_target_without_edge_rejected():
    res = apply_admission(
        [_conc("Dark denim jeans are slim.", ["term-dark-denim-jeans"], ["dark-denim-jeans"])],
        [_rec("dark-denim-jeans", ("Dark denim jeans are slim.", ["term-dark-denim-jeans"]))],
        query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert _outcome(res) == {"index": 0, "outcome": REJECT, "reason": NON_TARGET_NO_EDGE}


def test_d_relationship_edge_admits():
    pack = [_term("term-trench-coat", "trench-coat", "garment"),
            _rel("rel-trench-layered-oxford", "trench-coat", "oxford-shirt")]
    res = apply_admission(
        [_conc("Trench coat is layered with oxford shirt.",
               ["rel-trench-layered-oxford"], ["trench-coat", "oxford-shirt"])],
        [_rec("oxford-shirt",
              ("Oxford shirt layers with trench coat.", ["rel-trench-layered-oxford"]))],
        query="trench coat", universe=UNIVERSE, evidence=pack)
    assert _outcome(res) == {"index": 0, "outcome": ADMIT, "reason": EDGE_ADMIT}


def test_e_rule_edge_admits():
    pack = [_ev("alias-loose-jeans", "alias",
                {"doc_id": "alias-loose-jeans", "alias": "loose jeans",
                 "canonical_id": "wide_leg_jeans"}),
            _rule("rule-cropped-highrise-legline", "elongated_leg_line")]
    res = apply_admission(
        [_conc("Loose jeans have an elongated leg line.",
               ["alias-loose-jeans", "rule-cropped-highrise-legline"],
               ["wide_leg_jeans", "elongated_leg_line"])],
        [_rec("loose jeans",
              ("Loose jeans have an elongated leg line.",
               ["alias-loose-jeans", "rule-cropped-highrise-legline"]))],
        query="elongated leg line from cropped proportions",
        universe=UNIVERSE, evidence=pack)
    assert _outcome(res)["outcome"] == ADMIT
    assert _outcome(res)["reason"] == EDGE_ADMIT


def test_f_mere_cooccurrence_rejected():
    pack = [_term("term-wide-leg-jeans", "wide_leg_jeans", "garment"),
            _rule("rule-cropped-highrise-legline", "elongated_leg_line")]
    res = apply_admission(
        [_conc("Loose jeans have an elongated leg line.",
               ["term-wide-leg-jeans"], ["wide_leg_jeans"])],
        [_rec("wide_leg_jeans",
              ("Loose jeans have an elongated leg line.", ["term-wide-leg-jeans"]))],
        query="elongated leg line from cropped proportions",
        universe=UNIVERSE, evidence=pack)
    # rule doc sits in-pack but UNCITED: co-occurrence is not an edge.
    assert _outcome(res) == {"index": 0, "outcome": REJECT,
                             "reason": NON_TARGET_NO_EDGE}


# ---- G/H/I/K: citation validity ----

def test_g_claim_requires_citation():
    res = apply_admission(
        [_conc("Cotton is soft.", ["term-cotton"], ["cotton"])],
        [_rec("cotton", ("Cotton is soft.", []))],
        query="cotton vs linen", universe=UNIVERSE,
        evidence=[_term("term-cotton", "cotton", "material")])
    assert _outcome(res)["reason"] == EMPTY_CITATION


def test_h_unknown_evidence_id_rejected():
    res = apply_admission(
        [_conc("Cotton is soft.", ["term-cotton"], ["cotton"])],
        [_rec("cotton", ("Cotton is soft.", [42]))],
        query="cotton vs linen", universe=UNIVERSE,
        evidence=[_term("term-cotton", "cotton", "material")])
    assert _outcome(res) == {"index": 0, "outcome": REJECT, "reason": UNKNOWN_DOC}


def test_i_citation_outside_pack_rejected():
    res = apply_admission(
        [_conc("Linen is formal.", ["term-linen"], ["linen"])],
        [_rec("linen", ("Linen is formal.", ["term-silk"]))],
        query="cotton vs linen", universe=UNIVERSE,
        evidence=[_term("term-linen", "linen", "material")])
    assert _outcome(res) == {"index": 0, "outcome": REJECT, "reason": OUT_OF_PACK_DOC}


def test_k_unattributable_claim_rejected_for_structural_reason():
    # Structural proxy for "supported only by an uncited document": the claim
    # cites nothing usable in-pack, so it fails as stated. Semantic truth is
    # deliberately NOT judged here (see test_u).
    res = apply_admission(
        [_conc("Linen is formal.", ["term-linen"], ["linen"])],
        [_rec("linen", ("Linen is formal.", ["term-silk"]))],
        query="cotton vs linen", universe=UNIVERSE,
        evidence=[_term("term-cotton", "cotton", "material"),
                  _term("term-linen", "linen", "material")])
    assert _outcome(res)["outcome"] == REJECT
    assert res["admitted"] == []


# ---- J: duplicates ----

def test_j_duplicate_conclusion_rejected():
    conc = _conc("Loose jeans elongate.", ["alias-loose-jeans"], ["wide_leg_jeans"])
    pack = [_term("term-cropped-silhouette", "cropped", "garment")]
    rec = _rec("cropped", ("Cropped elongates.", ["term-cropped-silhouette"]))
    res = apply_admission(
        [dict(conc), dict(conc)], [dict(rec), copy.deepcopy(rec)],
        query="elongated leg line from cropped proportions",
        universe=UNIVERSE, evidence=pack)
    assert res["outcomes"][0]["outcome"] == ADMIT
    assert res["outcomes"][1] == {"index": 1, "outcome": REJECT, "reason": DUPLICATE}
    assert len(res["admitted"]) == 1


# ---- L: coverage ----

def test_l_uncovered_target_produces_coverage_event():
    res = apply_admission(
        [], [],
        query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert res["admitted"] == []
    assert res["coverage_flags"] == ["denim"]
    assert res["missing_evidence"] == [
        "no admitted conclusion covers query target 'denim' (evidence present)"]


def test_l_target_without_pack_cover_declares_missing_evidence():
    res = apply_admission([], [], query="denim", universe=UNIVERSE, evidence=[])
    assert res["coverage_flags"] == ["denim"]
    assert res["missing_evidence"] == ["no covering evidence for query target 'denim'"]


# ---- M/N: existing semantics preserved ----

def test_m_contested_conclusion_passes_through_untouched():
    conc = _conc("Fit is contested.", ["term-denim"], ["denim"], standing="contested")
    res = apply_admission(
        [conc], [_rec("denim", ("Denim is contested.", ["term-denim"]))],
        query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert res["outcomes"][0]["outcome"] == ADMIT
    assert res["admitted"][0]["standing"] == "contested"  # never rewritten


def test_n_unsupported_output_with_conclusions_rejected():
    conc = _conc("Denim exists.", ["term-denim"], ["denim"])
    res = apply_admission(
        [conc], [_rec("denim", ("Denim exists.", ["term-denim"]))],
        query="denim", universe=UNIVERSE, evidence=DENIM_PACK, unsupported=True)
    assert res["outcomes"] == [{"index": 0, "outcome": REJECT,
                                "reason": UNSUPPORTED_OUTPUT}]
    assert res["admitted"] == []


def test_n_unsupported_empty_output_passes_through():
    res = apply_admission([], [], query="kimono sizing",
                          universe=UNIVERSE, evidence=[], unsupported=True)
    assert res["admitted"] == []
    assert res["coverage_flags"] == []


def test_missing_record_fail_closed():
    res = apply_admission(
        [_conc("Denim exists.", ["term-denim"], ["denim"])], [],
        query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert res["outcomes"] == [{"index": 0, "outcome": REJECT, "reason": MISSING_RECORD}]


# ---- O: critical positive controls (3S §15) ----

def test_o_joint_cotton_linen_admitted():
    pack = [_term("term-cotton", "cotton", "material"),
            _term("term-linen", "linen", "material")]
    res = apply_admission(
        [_conc("Cotton and linen are natural fibers.",
               ["term-cotton", "term-linen"], ["cotton", "linen", "material"])],
        [_rec("cotton", ("Cotton is natural.", ["term-cotton"]),
              ("Linen is natural.", ["term-linen"]))],
        query="cotton vs linen", universe=UNIVERSE, evidence=pack)
    assert res["outcomes"][0]["outcome"] == ADMIT


def test_o_layered_trench_oxford_admitted():
    pack = [_term("term-trench-coat", "trench-coat", "garment"),
            _rel("rel-trench-layered-oxford", "trench-coat", "oxford-shirt")]
    res = apply_admission(
        [_conc("Trench coat is layered with oxford shirt.",
               ["rel-trench-layered-oxford"], ["trench-coat", "oxford-shirt"])],
        [_rec("trench-coat",
              ("Trench coat layers with oxford shirt.", ["rel-trench-layered-oxford"]))],
        query="trench coat", universe=UNIVERSE, evidence=pack)
    assert res["outcomes"][0]["outcome"] == ADMIT


def test_o_exp_denim_textile_admitted():
    res = apply_admission(
        [_conc("Denim is a textile.", ["term-denim"], ["denim", "textile"])],
        [_rec("denim", ("Denim is a textile.", ["term-denim"]))],
        query="what is denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert res["outcomes"][0]["outcome"] == ADMIT


def test_o_cmp_slim_pair_admitted_relaxed_rejected():
    pack = [_term("term-slim-fit", "slim-fit", "fit"),
            _term("term-regular-fit", "regular-fit", "fit"),
            _term("term-relaxed-fit", "relaxed-fit", "fit")]
    concs = [_conc("Slim beats regular.", ["term-slim-fit", "term-regular-fit"],
                   ["slim-fit", "regular-fit"]),
             _conc("Regular drapes.", ["term-regular-fit"], ["regular-fit"]),
             _conc("Relaxed is roomy.", ["term-relaxed-fit"], ["relaxed-fit"])]
    recs = [_rec("slim-fit", ("Slim is fitted.", ["term-slim-fit"])),
            _rec("regular-fit", ("Regular drapes.", ["term-regular-fit"])),
            _rec("relaxed-fit", ("Relaxed is roomy.", ["term-relaxed-fit"]))]
    res = apply_admission(concs, recs, query="slim vs regular fit",
                          universe=UNIVERSE, evidence=pack)
    assert [o["outcome"] for o in res["outcomes"]] == [ADMIT, ADMIT, REJECT]
    assert res["outcomes"][2]["reason"] == NON_TARGET_NO_EDGE
    assert len(res["admitted"]) == 2


def test_o_max_fit_bounds_admitted():
    pack = [_term("term-slim-fit", "slim-fit", "fit"),
            _term("term-regular-fit", "regular-fit", "fit"),
            _term("term-relaxed-fit", "relaxed-fit", "fit")]
    res = apply_admission(
        [_conc("regular-fit, relaxed-fit, slim-fit are types of fit.",
               ["term-regular-fit", "term-relaxed-fit", "term-slim-fit"],
               ["regular-fit", "relaxed-fit", "slim-fit"])],
        [_rec("regular-fit", ("These are fit types.",
                              ["term-regular-fit", "term-relaxed-fit", "term-slim-fit"]))],
        query="fit", universe=UNIVERSE, evidence=pack)
    assert res["outcomes"][0]["outcome"] == ADMIT


def test_o_idn_trench_admitted():
    pack = [_ev("alias-trench", "alias", {"doc_id": "alias-trench", "alias": "trench",
                                          "canonical_id": "trench-coat"}),
            _term("term-trench-coat", "trench-coat", "garment")]
    res = apply_admission(
        [_conc("Trench coat is outerwear.", ["term-trench-coat"], ["trench-coat"])],
        [_rec("trench-coat", ("Trench coat is outerwear.", ["term-trench-coat"]))],
        query="trench", universe=UNIVERSE, evidence=pack)
    assert res["outcomes"][0]["outcome"] == ADMIT


# ---- P: critical negative controls (3S §16) ----

def _p_res(subject, claims, eids, evidence, query):
    return apply_admission([_conc("stmt", eids, [subject])],
                           [_rec(subject, *claims)],
                           query=query, universe=UNIVERSE, evidence=evidence)


def test_p_dark_denim_rejected():
    res = _p_res("dark-denim-jeans",
                 [("Dark denim jeans are slim.", ["term-dark-denim-jeans"])],
                 ["term-dark-denim-jeans"], DENIM_PACK, "denim")
    assert res["outcomes"][0] == {"index": 0, "outcome": REJECT,
                                  "reason": NON_TARGET_NO_EDGE}


def test_p_wide_leg_rejected():
    res = _p_res("wide_leg_jeans",
                 [("Wide-leg jeans are relaxed.", ["term-wide-leg-jeans"])],
                 ["term-wide-leg-jeans"], DENIM_PACK, "denim")
    assert res["outcomes"][0]["reason"] == NON_TARGET_NO_EDGE


def test_p_japanese_streetwear_substitution_rejected_with_coverage():
    pack = [_term("term-classic", "classic", "aesthetic"),
            _term("term-japanese-streetwear", "japanese-streetwear", "culture"),
            _term("term-streetwear", "streetwear", "aesthetic")]
    res = _p_res("japanese-streetwear",
                 [("Streetwear is East Asian.", ["term-japanese-streetwear"])],
                 ["term-japanese-streetwear"], pack, "streetwear vs classic")
    assert res["outcomes"][0]["reason"] == NON_TARGET_NO_EDGE
    assert "streetwear" in res["coverage_flags"]  # real target uncovered


def test_p_unsupported_cotton_claim_rejected():
    res = _p_res("cotton", [("Cotton is soft and casual.", [])],
                 ["term-cotton"],
                 [_term("term-cotton", "cotton", "material")], "cotton vs linen")
    assert res["outcomes"][0]["reason"] == EMPTY_CITATION


def test_p_unsupported_linen_claim_rejected():
    res = _p_res("linen", [("Linen is formal.", ["term-oxford-shirt"])],
                 ["term-linen"],
                 [_term("term-linen", "linen", "material")], "cotton vs linen")
    assert res["outcomes"][0]["reason"] == OUT_OF_PACK_DOC


def test_p_uncited_effect_claim_rejected():
    pack = [_ev("alias-baggy-jeans", "alias",
                {"doc_id": "alias-baggy-jeans", "alias": "baggy jeans",
                 "canonical_id": "wide_leg_jeans"}),
            _rule("rule-cropped-highrise-legline", "elongated_leg_line")]
    res = _p_res("wide_leg_jeans",
                 [("Baggy jeans elongate the leg.", ["alias-baggy-jeans"])],
                 ["alias-baggy-jeans"], pack,
                 "elongated leg line from cropped proportions")
    assert res["outcomes"][0]["reason"] == NON_TARGET_NO_EDGE


def test_p_duplicate_loose_jeans_rejected():
    pack = [_term("term-cropped-silhouette", "cropped", "garment")]
    rec = _rec("cropped", ("Cropped elongates.", ["term-cropped-silhouette"]))
    conc = _conc("Loose jeans elongate.", ["term-cropped-silhouette"], ["cropped"])
    res = apply_admission([dict(conc), dict(conc)], [rec, copy.deepcopy(rec)],
                          query="elongated leg line from cropped proportions",
                          universe=UNIVERSE, evidence=pack)
    assert res["outcomes"][1]["reason"] == DUPLICATE


# ---- Q: 3P receives only admitted conclusions (frozen 3P, composed) ----

def test_q_rejected_conclusions_never_reach_3p():
    pack = DENIM_PACK
    concs = [_conc("Denim is made from cotton.",
                   ["term-denim", "rel-denim-made-from-cotton"], ["denim", "cotton"]),
             _conc("Dark denim jeans are slim.", ["term-dark-denim-jeans"],
                   ["dark-denim-jeans"])]
    recs = [_rec("denim", ("Denim is made from cotton.",
                            ["term-denim", "rel-denim-made-from-cotton"])),
            _rec("dark-denim-jeans", ("Dark denim jeans are slim.",
                                       ["term-dark-denim-jeans"]))]
    res = apply_admission(concs, recs, query="denim",
                          universe=UNIVERSE, evidence=pack)
    assert [o["outcome"] for o in res["outcomes"]] == [ADMIT, REJECT]
    # Frozen 3P takes attribute-style evidence; the production wiring adapts
    # pack dicts at this boundary (3P itself untouched).
    ns_pack = [SimpleNamespace(**item) for item in pack]
    seen_by_3p = []
    for conc in res["admitted"]:
        kept, _ = select_refs(conc["statement"], conc["ffo_refs"],
                              conc["evidence_ids"], ns_pack, "denim", "analyze")
        seen_by_3p.append((conc["statement"], kept))
    assert [s for s, _ in seen_by_3p] == ["Denim is made from cotton."]
    assert all("dark-denim-jeans" not in refs for _, refs in seen_by_3p)


# ---- R/S/T: immutability ----

def test_r_statements_not_modified():
    concs = [_conc("Denim is made from cotton.", ["term-denim"], ["denim"])]
    before = copy.deepcopy(concs)
    res = apply_admission(concs, [_rec("denim", ("Denim.", ["term-denim"]))],
                          query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert res["admitted"][0] is concs[0]
    assert concs == before


def test_s_evidence_pack_not_modified():
    pack = copy.deepcopy(DENIM_PACK)
    snapshot = copy.deepcopy(pack)
    apply_admission(
        [_conc("Denim.", ["term-denim"], ["denim"])],
        [_rec("denim", ("Denim.", ["term-denim"]))],
        query="denim", universe=UNIVERSE, evidence=pack)
    assert pack == snapshot


def test_t_no_refs_invented():
    concs = [_conc("Denim.", ["term-denim"], ["denim"])]
    res = apply_admission(concs, [_rec("denim", ("Denim.", ["term-denim"]))],
                          query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert res["admitted"][0]["ffo_refs"] == ["denim"]
    assert "ffo_refs" not in res["outcomes"][0]
    assert res["outcomes"][0]["outcome"] == ADMIT


# ---- U: no semantic entailment engine ----

def test_u_semantically_bogus_but_structured_claim_passes():
    # Locks the determinism boundary: citation membership is checked,
    # natural-language truth is not. Catching this is held-out eval's job.
    res = apply_admission(
        [_conc("Denim is made of moon cheese.", ["term-denim"], ["denim"])],
        [_rec("denim", ("Denim is made of moon cheese.", ["term-denim"]))],
        query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert res["outcomes"][0]["outcome"] == ADMIT


# ---- 3V Fix 1: rule-effect subjects (D1-D10) ----

RULE_CROPPED = _ev("rule-cropped-highrise-legline", "rule", {
    "doc_id": "rule-cropped-highrise-legline",
    "payload": {"effect": "elongated_leg_line",
                "when": {"bottom": "high-rise", "top": "cropped"}}})
TERM_CROPPED = _term("term-cropped-silhouette", "cropped", "garment")

EFFECT_QUERY = "elongated leg line from cropped proportions"


def test_d1_valid_rule_effect_target_admitted():
    res = apply_admission(
        [_conc("Cropped proportions elongate the leg.", ["rule-cropped-highrise-legline"],
               ["elongated_leg_line"])],
        [_rec("elongated_leg_line",
              ("Cropped proportions elongate the leg.",
               ["rule-cropped-highrise-legline"]))],
        query=EFFECT_QUERY, universe=UNIVERSE,
        evidence=[RULE_CROPPED, TERM_CROPPED])
    assert res["outcomes"][0] == {"index": 0, "outcome": ADMIT, "reason": TARGET_ADMIT}


def test_d2_cited_rule_licenses_non_target_effect():
    res = apply_admission(
        [_conc("The leg line is elongated.", ["rule-cropped-highrise-legline"],
               ["elongated_leg_line"])],
        [_rec("elongated_leg_line",
              ("The leg line is elongated.", ["rule-cropped-highrise-legline"]))],
        query="cropped", universe=UNIVERSE, evidence=[RULE_CROPPED, TERM_CROPPED])
    assert res["outcomes"][0] == {"index": 0, "outcome": ADMIT, "reason": EDGE_ADMIT}


def test_d3_unrelated_rule_effect_rejected():
    res = apply_admission(
        [_conc("The leg line is elongated.", ["rule-cropped-highrise-legline"],
               ["elongated_leg_line"])],
        [_rec("elongated_leg_line",
              ("The leg line is elongated.", ["rule-cropped-highrise-legline"]))],
        query="denim", universe=UNIVERSE, evidence=[RULE_CROPPED, TERM_CROPPED])
    assert res["outcomes"][0] == {"index": 0, "outcome": REJECT,
                                  "reason": NON_TARGET_NO_EDGE}


def test_d4_cooccurring_rule_effect_rejected():
    res = apply_admission(
        [_conc("Cropped elongates.", ["term-cropped-silhouette"],
               ["elongated_leg_line"])],
        [_rec("elongated_leg_line", ("Cropped elongates.", ["term-cropped-silhouette"]))],
        query="cropped", universe=UNIVERSE, evidence=[RULE_CROPPED, TERM_CROPPED])
    assert res["outcomes"][0]["reason"] == NON_TARGET_NO_EDGE


def test_d5_unknown_rule_effect_rejected():
    assert resolve_subject("mystery_effect", UNIVERSE) is None
    res = apply_admission(
        [_conc("Mystery.", ["rule-cropped-highrise-legline"], ["mystery_effect"])],
        [_rec("mystery_effect", ("Mystery.", ["rule-cropped-highrise-legline"]))],
        query=EFFECT_QUERY, universe=UNIVERSE, evidence=[RULE_CROPPED])
    assert res["outcomes"][0]["reason"] == SUBJECT_UNRESOLVED


def test_d6_effect_without_rule_evidence_rejected():
    res = apply_admission(
        [_conc("Cropped elongates.", ["term-cropped-silhouette"],
               ["elongated_leg_line"])],
        [_rec("elongated_leg_line", ("Cropped elongates.", ["term-cropped-silhouette"]))],
        query="cropped", universe=UNIVERSE, evidence=[TERM_CROPPED])
    # No rule document in the pack at all: nothing establishes the effect.
    assert res["outcomes"][0]["reason"] == NON_TARGET_NO_EDGE


def test_d7_effect_claim_still_requires_citation():
    res = apply_admission(
        [_conc("Cropped elongates.", ["rule-cropped-highrise-legline"],
               ["elongated_leg_line"])],
        [_rec("elongated_leg_line", ("Cropped elongates.", []))],
        query=EFFECT_QUERY, universe=UNIVERSE, evidence=[RULE_CROPPED])
    assert res["outcomes"][0]["reason"] == EMPTY_CITATION


def test_d8_duplicate_effect_conclusion_rejected():
    conc = _conc("Cropped elongates.", ["rule-cropped-highrise-legline"],
                 ["elongated_leg_line"])
    rec = _rec("elongated_leg_line",
               ("Cropped elongates.", ["rule-cropped-highrise-legline"]))
    res = apply_admission([dict(conc), dict(conc)], [rec, copy.deepcopy(rec)],
                          query=EFFECT_QUERY, universe=UNIVERSE,
                          evidence=[RULE_CROPPED])
    assert res["outcomes"][0]["outcome"] == ADMIT
    assert res["outcomes"][1]["reason"] == DUPLICATE


def test_d9_valid_effect_reaches_3p():
    from types import SimpleNamespace as NS
    pack = [NS(doc_id="rule-cropped-highrise-legline", doc_type="rule",
               ffo_references=["elongated_leg_line"],
               content=dict(RULE_CROPPED["content"]))]
    res = apply_admission(
        [_conc("Cropped elongates.", ["rule-cropped-highrise-legline"],
               ["elongated_leg_line"])],
        [_rec("elongated_leg_line",
              ("Cropped elongates.", ["rule-cropped-highrise-legline"]))],
        query=EFFECT_QUERY, universe=UNIVERSE, evidence=[RULE_CROPPED])
    assert len(res["admitted"]) == 1
    kept, decisions = select_refs(res["admitted"][0]["statement"],
                                  list(res["admitted"][0]["ffo_refs"]),
                                  list(res["admitted"][0]["evidence_ids"]),
                                  pack, EFFECT_QUERY, "style")
    assert kept == ["elongated_leg_line"]
    assert decisions[0]["rule_id"] == "rule_effect_keep"


def test_d10_invalid_effect_never_reaches_3p():
    res = apply_admission(
        [_conc("The leg line is elongated.", ["rule-cropped-highrise-legline"],
               ["elongated_leg_line"])],
        [_rec("elongated_leg_line",
              ("The leg line is elongated.", ["rule-cropped-highrise-legline"]))],
        query="denim", universe=UNIVERSE, evidence=[RULE_CROPPED, TERM_CROPPED])
    assert res["admitted"] == []


def test_h_rule_effect_positive_control_anx_volume_shape():
    pack = [_ev("rule-fitted-wide-balanced", "rule", {
        "doc_id": "rule-fitted-wide-balanced",
        "payload": {"effect": "balanced_volume",
                    "when": {"bottom": "wide", "top": "fitted"}}})]
    res = apply_admission(
        [_conc("Wide bottom plus fitted top balances volume.",
               ["rule-fitted-wide-balanced"], ["balanced_volume"])],
        [_rec("balanced_volume",
              ("Wide bottom plus fitted top balances volume.",
               ["rule-fitted-wide-balanced"]))],
        query="balanced volume", universe=UNIVERSE, evidence=pack)
    assert res["outcomes"][0] == {"index": 0, "outcome": ADMIT,
                                  "reason": TARGET_ADMIT}


# ---- 3V Fix 2: subject_ref namespace hardening (F1-F11) ----

def test_f1_canonical_accepted():
    assert resolve_subject("denim", UNIVERSE) == ("denim", False)


def test_f2_alias_accepted():
    assert resolve_subject("wine", UNIVERSE) == ("burgundy", True)


def test_f3_rule_effect_accepted():
    assert resolve_subject("elongated_leg_line", UNIVERSE) == ("elongated_leg_line", False)


def test_f4_bracketed_canonical_rejected():
    assert resolve_subject("[denim]", UNIVERSE) is None


def test_f5_bracketed_alias_rejected():
    assert resolve_subject("[loose jeans]", UNIVERSE) is None


def test_f6_bracketed_relationship_rejected():
    assert resolve_subject("[rel-denim-made-from-cotton]", UNIVERSE) is None


def test_f7_id_prefix_rejected():
    assert resolve_subject("ID: term-denim", UNIVERSE) is None


def test_f8_evidence_doc_id_rejected():
    assert resolve_subject("term-denim", UNIVERSE) is None
    assert resolve_subject("alias-loose-jeans", UNIVERSE) is None


def test_f9_knowledge_prose_rejected():
    assert resolve_subject("Denim is a durable textile.", UNIVERSE) is None
    assert resolve_subject("dark denim jeans", UNIVERSE) is None


def test_f10_empty_subject_rejected():
    assert resolve_subject("", UNIVERSE) is None
    assert resolve_subject("   ", UNIVERSE) is None
    assert resolve_subject(None, UNIVERSE) is None


def test_f11_unknown_ffo_ref_rejected():
    assert resolve_subject("silk-denim", UNIVERSE) is None
    assert resolve_subject("Denim", UNIVERSE) is None  # case-sensitive: fail closed


def test_f_namespace_violations_fail_at_apply_level():
    for bad_subject in ("[denim]", "ID: term-denim", "term-denim",
                        "Denim is durable.", "", "silk-denim"):
        res = apply_admission(
            [_conc("Denim.", ["term-denim"], ["denim"])],
            [_rec(bad_subject, ("Denim.", ["term-denim"]))],
            query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
        assert res["outcomes"][0]["reason"] == SUBJECT_UNRESOLVED, bad_subject
        assert res["admitted"] == []


# ---- V: remove-only guarantees ----

def test_v_remove_only():
    concs = [_conc("Denim.", ["term-denim"], ["denim"]),
             _conc("Dark denim.", ["term-dark-denim-jeans"], ["dark-denim-jeans"])]
    universe_before = copy.deepcopy(UNIVERSE)
    res = apply_admission(
        concs,
        [_rec("denim", ("Denim.", ["term-denim"])),
         _rec("dark-denim-jeans", ("Dark.", ["term-dark-denim-jeans"]))],
        query="denim", universe=UNIVERSE, evidence=DENIM_PACK)
    assert len(concs) == 2  # input list intact, rejected kept (not rewritten)
    assert concs[1] == {"statement": "Dark denim.",
                        "evidence_ids": ["term-dark-denim-jeans"],
                        "ffo_refs": ["dark-denim-jeans"], "standing": "supported"}
    assert UNIVERSE == universe_before
    assert len(res["admitted"]) == 1
    assert COVERAGE_FLAG == "coverage_flag"  # outcome name pinned for 3P wiring
