"""Fashion reasoning evaluation benchmark — deterministic scoring (Phase 3B).

Compares structured properties of future reasoner outputs against curated
ground truth (never natural-language string matching). Metrics stay
separable — no single "fashion intelligence score".

Metric set (binary pass except precision/recall, which are continuous):
  intent_accuracy        input intent == expected intent
  grounding_accuracy     derived output status == expected grounding
  evidence_precision     cited ∩ expected / cited (1.0 when nothing cited)
  evidence_recall        cited ∩ expected / expected (1.0 when none expected)
  ffo_correctness        cited refs ∩ accepted refs / cited (0.0 when refs
                         required but none cited; 1.0 when none required
                         and none cited)
  ffo_recall             cited refs ∩ accepted refs / accepted refs
                         (1.0 when none expected)
  unsupported_handling   unsupported flag == (expected == unsupported)
  missing_detection      missing non-empty == case requires/expects it
  contradiction_handling contradictions non-empty == case requires/expects it
  uncertainty_compliance uncertainties non-empty == case requires/expects it
  constraint_compliance  supported conclusions ≥ min AND total ≤ max (if set)
  version_preservation   output pins == input pins and ffo == benchmark ffo

Accepted refs = expected_ffo_refs ∪ accepted_aliases values (canonical
stays preferred; alias hits are reported separately, never converted).
Roles (canonical/entity_kind/rel_endpoint/rule_effect) are explicit
per-case metadata for readability; matching stays set-based.

The evaluator is total over outputs (malformed outputs score 0 with
reasons, never raise); it raises BenchmarkError only on malformed cases.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.data import ffo as _ffo_pkg
from app.domain.services.ffo_reasoning import REASONING_CONTRACT_VERSION, SUPPORTED_INTENTS

BENCHMARK_VERSION = "1.1"
BENCHMARK_PATH = (
    Path(_ffo_pkg.__file__).resolve().parent / "benchmark" / "benchmark_v01.json"
)

GROUNDINGS = ("supported", "insufficient", "contested", "uncertain", "unsupported")
CONFIDENCES = ("high", "medium", "low", "unknown")

FFO_REF_ROLES = ("canonical", "entity_kind", "rel_endpoint", "rule_effect")

METRIC_NAMES = (
    "intent_accuracy",
    "grounding_accuracy",
    "evidence_precision",
    "evidence_recall",
    "ffo_correctness",
    "ffo_recall",
    "unsupported_handling",
    "missing_detection",
    "contradiction_handling",
    "uncertainty_compliance",
    "constraint_compliance",
    "version_preservation",
)

_FILTER_KEYS = ("doc_type", "domain", "entity", "language", "region", "limit")


class BenchmarkError(ValueError):
    """Malformed benchmark case or file (never a model-output problem)."""


def _need(data: dict, key: str, where: str, types) -> object:
    value = data.get(key)
    if not isinstance(value, types):
        raise BenchmarkError(f"{where}: '{key}' has the wrong shape")
    return value


def validate_case(raw: dict) -> dict:
    """Structural validation of one benchmark case; returns it unchanged."""
    if not isinstance(raw, dict):
        raise BenchmarkError("case: must be an object")
    case_id = raw.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        raise BenchmarkError("case: 'case_id' must be a non-empty string")
    where = f"case '{case_id}'"
    query = raw.get("query")
    if not isinstance(query, str) or not query.strip():
        raise BenchmarkError(f"{where}: 'query' must be a non-empty string")
    if raw.get("expected_intent") not in SUPPORTED_INTENTS:
        raise BenchmarkError(f"{where}: 'expected_intent' must be supported (no deferred intents)")
    context = raw.get("context")
    if context is not None and not isinstance(context, dict):
        raise BenchmarkError(f"{where}: 'context' must be an object or null")
    for key in ("expected_ffo_refs", "expected_evidence_ids"):
        items = raw.get(key, ())
        if isinstance(items, str) or not isinstance(items, (list, tuple)):
            raise BenchmarkError(f"{where}: '{key}' must be a list")
        if any(not isinstance(v, str) or not v.strip() for v in items):
            raise BenchmarkError(f"{where}: '{key}' must hold non-empty strings")
    for key in ("min_supported_conclusions",):
        value = raw.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise BenchmarkError(f"{where}: '{key}' must be >= 0")
    for key in (
        "requires_contradictions", "requires_missing_evidence", "requires_uncertainties",
    ):
        if not isinstance(raw.get(key), bool):
            raise BenchmarkError(f"{where}: '{key}' must be a boolean")
    if raw.get("expected_grounding") not in GROUNDINGS:
        raise BenchmarkError(f"{where}: 'expected_grounding' must be one of {list(GROUNDINGS)}")
    if raw.get("expected_confidence") not in CONFIDENCES:
        raise BenchmarkError(f"{where}: 'expected_confidence' must be one of {list(CONFIDENCES)}")
    maxc = raw.get("expected_max_conclusions")
    if maxc is not None and (isinstance(maxc, bool) or not isinstance(maxc, int) or maxc < 1):
        raise BenchmarkError(f"{where}: 'expected_max_conclusions' must be >= 1 or null")
    if not isinstance(raw.get("rationale"), str) or not raw["rationale"].strip():
        raise BenchmarkError(f"{where}: 'rationale' is required")
    filters = raw.get("retrieval_filters", {})
    if not isinstance(filters, dict) or any(k not in _FILTER_KEYS for k in filters):
        raise BenchmarkError(f"{where}: 'retrieval_filters' keys must be a subset of {list(_FILTER_KEYS)}")
    aliases = raw.get("accepted_aliases", {})
    if not isinstance(aliases, dict):
        raise BenchmarkError(f"{where}: 'accepted_aliases' must be an object")
    expected_refs = list(raw.get("expected_ffo_refs", ()))
    for canonical, variants in aliases.items():
        if canonical not in expected_refs:
            raise BenchmarkError(f"{where}: 'accepted_aliases' key '{canonical}' is not expected")
        if isinstance(variants, str) or not isinstance(variants, (list, tuple)):
            raise BenchmarkError(f"{where}: 'accepted_aliases' values must be lists")
        for variant in variants:
            if not isinstance(variant, str) or not variant.strip():
                raise BenchmarkError(f"{where}: 'accepted_aliases' must hold non-empty strings")
            if variant == canonical or variant in expected_refs:
                raise BenchmarkError(f"{where}: alias '{variant}' duplicates an expected ref")
    roles = raw.get("ffo_ref_roles", {})
    if not isinstance(roles, dict):
        raise BenchmarkError(f"{where}: 'ffo_ref_roles' must be an object")
    for ref, role in roles.items():
        if ref not in expected_refs:
            raise BenchmarkError(f"{where}: 'ffo_ref_roles' key '{ref}' is not expected")
        if role not in FFO_REF_ROLES:
            raise BenchmarkError(f"{where}: role '{role}' must be one of {list(FFO_REF_ROLES)}")
    return raw


def load_benchmark(path: Path = BENCHMARK_PATH) -> dict:
    """Load + validate the benchmark file; cases sorted deterministically."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BenchmarkError(f"cannot load benchmark '{path}': {exc}") from exc
    if not isinstance(data, dict):
        raise BenchmarkError("benchmark: must be an object")
    if data.get("benchmark_version") != BENCHMARK_VERSION:
        raise BenchmarkError(
            f"benchmark version '{data.get('benchmark_version')}' != '{BENCHMARK_VERSION}'"
        )
    if not isinstance(data.get("ffo_version"), str) or not data["ffo_version"]:
        raise BenchmarkError("benchmark: 'ffo_version' is required")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise BenchmarkError("benchmark: 'cases' must be a non-empty list")
    validated = [validate_case(case) for case in cases]
    ids = [case["case_id"] for case in validated]
    if len(set(ids)) != len(ids):
        raise BenchmarkError("benchmark: duplicate case_id")
    validated.sort(key=lambda case: case["case_id"])
    return {
        "benchmark_version": data["benchmark_version"],
        "ffo_version": data["ffo_version"],
        "seed_ref": data.get("seed_ref", ""),
        "cases": validated,
    }


def derive_status(output: dict) -> str:
    """Grounding status derived from output structure (mirrors §6 semantics)."""
    conclusions = output.get("conclusions") or []
    if output.get("unsupported") is True:
        return "unsupported"
    if any(isinstance(c, dict) and c.get("standing") == "contested" for c in conclusions):
        return "contested"
    if not conclusions:
        return "insufficient"
    if any(isinstance(c, dict) and c.get("standing") == "uncertain" for c in conclusions):
        return "uncertain"
    return "supported"


def _cited_ids(output: dict) -> list:
    ids: list[str] = []
    for conclusion in output.get("conclusions") or []:
        if not isinstance(conclusion, dict):
            continue
        for ref in conclusion.get("evidence_ids") or []:
            if isinstance(ref, str) and ref not in ids:
                ids.append(ref)
    return ids


def _cited_refs(output: dict) -> list:
    refs: list[str] = []
    for conclusion in output.get("conclusions") or []:
        if not isinstance(conclusion, dict):
            continue
        for ref in conclusion.get("ffo_refs") or []:
            if isinstance(ref, str) and ref not in refs:
                refs.append(ref)
    return refs


def _supported_count(output: dict) -> int:
    return sum(
        1
        for c in output.get("conclusions") or []
        if isinstance(c, dict) and c.get("standing") == "supported"
    )


def evaluate(case: dict, input_dict: dict, output_dict: dict) -> "EvaluationResult":
    """Score one (case, input, output) triple; total over malformed outputs."""
    if not isinstance(case, dict) or not isinstance(input_dict, dict):
        raise BenchmarkError("evaluate: case and input must be objects")
    output = output_dict if isinstance(output_dict, dict) else {}
    expected_ids = list(case.get("expected_evidence_ids", ()))
    expected_refs = list(case.get("expected_ffo_refs", ()))
    cited, cited_refs = _cited_ids(output), _cited_refs(output)
    metrics: dict[str, dict] = {}

    def record(name: str, score: float, expected, actual, reason: str, detail=None) -> None:
        metrics[name] = {
            "score": score,
            "pass": score == 1.0,
            "expected": expected,
            "actual": actual,
            "reason": reason,
        }
        if detail is not None:
            metrics[name]["detail"] = detail

    actual_intent = (input_dict.get("request") or {}).get("intent")
    record(
        "intent_accuracy", 1.0 if actual_intent == case["expected_intent"] else 0.0,
        case["expected_intent"], actual_intent, "input intent vs expected intent",
    )
    actual_status = derive_status(output)
    record(
        "grounding_accuracy", 1.0 if actual_status == case["expected_grounding"] else 0.0,
        case["expected_grounding"], actual_status, "derived output status vs expected",
    )
    precision = len([i for i in cited if i in expected_ids]) / len(cited) if cited else 1.0
    record("evidence_precision", precision, sorted(expected_ids), sorted(cited),
           "cited ids covered by expected ids")
    recall = len([i for i in expected_ids if i in cited]) / len(expected_ids) if expected_ids else 1.0
    record("evidence_recall", recall, sorted(expected_ids), sorted(cited),
           "expected ids covered by cited ids")
    accepted = set(expected_refs) | {
        alias
        for variants in case.get("accepted_aliases", {}).values()
        for alias in variants
    }
    alias_of = {
        alias: canonical
        for canonical, variants in case.get("accepted_aliases", {}).items()
        for alias in variants
    }
    hits = [r for r in cited_refs if r in accepted]
    if cited_refs:
        correctness = len(hits) / len(cited_refs)
    else:
        correctness = 1.0 if not accepted else 0.0
    detail = {
        "canonical_hits": sorted({r for r in hits if r not in alias_of}),
        "alias_hits": sorted({r: alias_of[r] for r in hits if r in alias_of}),
        "missed": sorted(accepted - set(cited_refs)),
    }
    record("ffo_correctness", correctness, sorted(accepted), sorted(cited_refs),
           "cited FFO refs covered by accepted refs (canonical + aliases)",
           detail=detail)
    recall_refs = len(hits) / len(accepted) if accepted else 1.0
    record("ffo_recall", recall_refs, sorted(accepted), sorted(cited_refs),
           "accepted FFO refs covered by cited refs", detail=detail)
    record(
        "unsupported_handling",
        1.0 if bool(output.get("unsupported", False)) == (case["expected_grounding"] == "unsupported") else 0.0,
        case["expected_grounding"] == "unsupported", bool(output.get("unsupported", False)),
        "unsupported flag matches expected grounding",
    )
    want_missing = bool(case.get("requires_missing_evidence")) or case["expected_grounding"] in (
        "insufficient", "unsupported",
    )
    record(
        "missing_detection", 1.0 if bool(output.get("missing_evidence")) == want_missing else 0.0,
        want_missing, bool(output.get("missing_evidence")),
        "missing_evidence presence matches expectation",
    )
    want_contra = bool(case.get("requires_contradictions")) or case["expected_grounding"] == "contested"
    record(
        "contradiction_handling", 1.0 if bool(output.get("contradictions")) == want_contra else 0.0,
        want_contra, bool(output.get("contradictions")),
        "contradictions presence matches expectation",
    )
    want_uncert = bool(case.get("requires_uncertainties")) or case["expected_grounding"] == "uncertain"
    record(
        "uncertainty_compliance", 1.0 if bool(output.get("uncertainties")) == want_uncert else 0.0,
        want_uncert, bool(output.get("uncertainties")),
        "uncertainties presence matches expectation",
    )
    maxc, supported = case.get("expected_max_conclusions"), _supported_count(output)
    total = len(output.get("conclusions") or [])
    ok = (maxc is None or total <= maxc) and supported >= case.get("min_supported_conclusions", 0)
    record("constraint_compliance", 1.0 if ok else 0.0,
           {"min_supported": case.get("min_supported_conclusions", 0), "max": maxc},
           {"supported": supported, "total": total}, "conclusion bounds")
    in_versions = (input_dict.get("versions") or {})
    out_versions = (output.get("versions") or {})
    pins_ok = bool(in_versions) and in_versions == out_versions
    record("version_preservation", 1.0 if pins_ok else 0.0,
           in_versions, out_versions, "output pins equal input pins")
    return EvaluationResult(
        case_id=case["case_id"],
        metrics=metrics,
        passed=all(m["pass"] for m in metrics.values()),
        benchmark_version=BENCHMARK_VERSION,
        ffo_version=in_versions.get("ffo_version", "") if isinstance(in_versions, dict) else "",
        reasoning_contract_version=(
            in_versions.get("reasoning_contract_version", "")
            if isinstance(in_versions, dict) else ""
        ),
    )


@dataclass(frozen=True)
class EvaluationResult:
    """One case evaluation: separable metric results, no single score."""

    case_id: str
    metrics: dict
    passed: bool
    benchmark_version: str
    ffo_version: str
    reasoning_contract_version: str

    def to_dict(self) -> dict:
        return {
            "case_id": self.case_id,
            "metrics": {name: dict(m) for name, m in self.metrics.items()},
            "passed": self.passed,
            "benchmark_version": self.benchmark_version,
            "ffo_version": self.ffo_version,
            "reasoning_contract_version": self.reasoning_contract_version,
        }


__all__ = [
    "BENCHMARK_PATH",
    "BENCHMARK_VERSION",
    "CONFIDENCES",
    "FFO_REF_ROLES",
    "GROUNDINGS",
    "METRIC_NAMES",
    "BenchmarkError",
    "EvaluationResult",
    "derive_status",
    "evaluate",
    "load_benchmark",
    "validate_case",
]
