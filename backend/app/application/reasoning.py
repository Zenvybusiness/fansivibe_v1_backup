"""Benchmark execution use cases — Phase 3C orchestration (no model code).

`execute_benchmark_case` runs one Phase 3B case end to end: build a
validated reasoning input from the case (lexical evidence via the
existing retrieval service), call the injected reasoner, validate the
output, and score it with the Phase 3B evaluator. Ground truth is only
read, never altered.

Manual command (requires a running Ollama; never part of the suite)::

    python -m app.application.reasoning --list
    python -m app.application.reasoning --case exp-denim-textile
"""

from __future__ import annotations

import argparse
import json
import sys

from app.data.ffo import FFO_VERSION, corpus
from app.domain.services.ffo_benchmark import EvaluationResult, evaluate, load_benchmark
from app.domain.services.ffo_reasoning import (
    EVIDENCE_SCHEMA_VERSION,
    REASONING_CONTRACT_VERSION,
    ReasoningEvidence,
    corpus_digest,
    validate_input,
)
from app.domain.services.ffo_retrieval import retrieve


def _corpus_versions() -> dict:
    index = corpus.build_index(corpus.load_documents())
    return corpus.corpus_versions(index)


def build_case_input(case: dict) -> dict:
    """Reasoning-input dict for one benchmark case (lexical evidence).

    Every evidence item carries its validated corpus content (Phase 3D):
    looked up by doc_id from the validated corpus — unknown ids fail fast
    via CorpusError instead of reaching the model content-free.
    """
    pack = retrieve(case["query"], **dict(case.get("retrieval_filters", {})))
    by_id = corpus.build_index(corpus.load_documents())["by_id"]
    evidence = []
    for item in pack.items:
        if item.doc_id not in by_id:
            raise corpus.CorpusError(f"evidence '{item.doc_id}' has no corpus document")
        record = ReasoningEvidence.from_retrieval(item).to_dict()
        record["content"] = corpus.evidence_content(by_id[item.doc_id])
        evidence.append(record)
    return {
        "request": {"query": case["query"], "intent": case["expected_intent"]},
        "context": dict(case.get("context") or {}),
        "entities": list(case.get("expected_ffo_refs", [])),
        "evidence": evidence,
        "constraints": {
            "evidence_only": True,
            "max_conclusions": case.get("expected_max_conclusions") or 3,
        },
        "requirements": {"include_reasoning_notes": True},
        "versions": {
            "ffo_version": FFO_VERSION,
            "corpus_digest": corpus_digest(_corpus_versions(), FFO_VERSION),
            "evidence_schema": EVIDENCE_SCHEMA_VERSION,
            "reasoning_contract_version": REASONING_CONTRACT_VERSION,
        },
    }


def execute_benchmark_case(case: dict, *, reasoner) -> EvaluationResult:
    """Run one case through any FashionReasoner and score it (read-only)."""
    parsed = validate_input(build_case_input(case))
    output = reasoner.reason(parsed)
    return evaluate(case, parsed.to_dict(), output.to_dict())


def main(argv: list[str] | None = None) -> int:
    """Manual benchmark CLI (outside the test suite by design)."""
    from app.ai.ollama_reasoner import OllamaFashionReasoner, ReasoningConfig

    parser = argparse.ArgumentParser(description="Run the 3B benchmark against Ollama.")
    parser.add_argument("--list", action="store_true", help="list case ids")
    parser.add_argument("--case", default=None, help="single case id (default: all)")
    parser.add_argument("--model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--timeout-s", type=float, default=None)
    args = parser.parse_args(argv)

    bench = load_benchmark()
    if args.list:
        print("\n".join(c["case_id"] for c in bench["cases"]))
        return 0
    cases = bench["cases"]
    if args.case:
        cases = [c for c in cases if c["case_id"] == args.case]
        if not cases:
            print(f"unknown case '{args.case}'", file=sys.stderr)
            return 2
    reasoner = OllamaFashionReasoner(
        ReasoningConfig.from_env(model=args.model, base_url=args.base_url, timeout_s=args.timeout_s)
    )
    print(f"model: {reasoner.describe()}")
    failed = 0
    for case in cases:
        try:
            result = execute_benchmark_case(case, reasoner=reasoner)
        except Exception as exc:  # noqa: BLE001 — manual tool reports, never hides
            print(f"{case['case_id']}: ERROR {type(exc).__name__}: {exc}")
            failed += 1
            continue
        bad = sorted(n for n, m in result.metrics.items() if not m["pass"])
        print(f"{case['case_id']}: {'PASS' if result.passed else 'FAIL ' + ','.join(bad)}")
        failed += 0 if result.passed else 1
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_case_input", "execute_benchmark_case", "main"]
