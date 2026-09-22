"""Ollama reasoning integration — separated by design (Phase 3C §11).

Runs ONE benchmark case against a live Ollama server when present and
SKIPS otherwise. Never part of the normal regression gate: the suite
must stay runnable without Ollama installed. No model quality is
asserted here — only that the execution path produces a structured,
version-pinned evaluation result.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest

from app.ai.ollama_reasoner import OllamaFashionReasoner, ReasoningConfig
from app.application.reasoning import execute_benchmark_case
from app.domain.services.ffo_benchmark import EvaluationResult, load_benchmark

import httpx


def _ollama_up(timeout_s: float = 2.0) -> bool:
    if os.environ.get("FANSIVIBE_DISABLE_LLM") == "1":
        return False
    host = urlparse(
        os.environ.get("FANSIVIBE_OLLAMA_HOST", "http://localhost:11434")
    ).hostname or "localhost"
    try:
        with socket.create_connection((host, 11434), timeout=timeout_s):
            return True
    except OSError:
        return False


def _model_present(model: str, base_url: str, timeout_s: float = 5.0) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=timeout_s)
        names = {
            (entry.get("name") or "") for entry in response.json().get("models", [])
        }
        return model in names or model.split(":")[0] in {n.split(":")[0] for n in names}
    except Exception:
        return False


def test_live_ollama_reasoning_smoke():
    if not _ollama_up():
        pytest.skip("Ollama not reachable; live reasoning smoke skipped")
    config = ReasoningConfig.from_env(timeout_s=120.0)
    if not _model_present(config.model, config.base_url):
        pytest.skip(f"model '{config.model}' not pulled; live reasoning smoke skipped")
    case = next(
        c for c in load_benchmark()["cases"] if c["case_id"] == "exp-denim-textile"
    )
    reasoner = OllamaFashionReasoner(config)
    result = execute_benchmark_case(case, reasoner=reasoner)
    assert isinstance(result, EvaluationResult)
    assert result.case_id == "exp-denim-textile"
    assert result.benchmark_version == "1.0"
