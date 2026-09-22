"""Ollama fashion reasoning adapter — first model-execution layer (Phase 3C).

Satisfies the `FashionReasoner` port from infrastructure (`app/ai/` is the
established adapter home per AI_INTEGRATION_ARCHITECTURE: F-3 keeps HTTP
out of domain, F-7 keeps vendor code behind the adapter). The domain
never imports this module.

Pipeline: validated input → prompt builder → `/api/chat` (JSON mode) →
fence-strip → `json.loads` → 3A structural validation → evidence-ID check
→ FFO-reference check → `FashionReasoningOutput`. Failures raise the
typed `ReasoningExecutionError` (never silent repair, never raw model
JSON to callers). Read-only: no writes, no state, no provider calls
beyond the single chat request.

Config: explicit constructor args with `FANSIVIBE_OLLAMA_*` env defaults
(same server vars as `llm_backend`); reasoning-specific knobs have their
own env vars. No credentials, no machine paths. `temperature` defaults
to 0.0 for benchmark determinism (not a mathematical guarantee).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field

import httpx

from app.ai.reasoning_prompt import build_system_prompt, build_user_prompt
from app.domain.services.ffo_reasoning import (
    REASONING_CONTRACT_VERSION,
    FashionReasoningInput,
    FashionReasoningOutput,
    ReasoningContractError,
    validate_output,
)

logger = logging.getLogger("fansivibe.ai.reasoning")

_CHAT_PATH = "/api/chat"


class ReasoningExecutionError(Exception):
    """Typed model-execution failure with a machine-readable category.

    Categories: unavailable (connection), timeout, http_error,
    malformed_json, invalid_output (contract/evidence/FFO/version/max
    violations). Plain Exception (like EmbeddingError): infrastructure
    events, not content problems.
    """

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class ReasoningConfig:
    """Ollama reasoning knobs; explicit args win, env fills the rest."""

    base_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    timeout_s: float = 60.0
    temperature: float = 0.0
    max_retries: int = 1
    num_predict: int | None = None

    @classmethod
    def from_env(cls, **overrides) -> "ReasoningConfig":
        """Build from `FANSIVIBE_OLLAMA_*` / `FANSIVIBE_REASONING_*` env."""
        env: dict = {
            "base_url": os.environ.get("FANSIVIBE_OLLAMA_HOST", cls.base_url),
            "model": os.environ.get("FANSIVIBE_OLLAMA_MODEL", cls.model),
        }
        if os.environ.get("FANSIVIBE_REASONING_TIMEOUT_S"):
            env["timeout_s"] = float(os.environ["FANSIVIBE_REASONING_TIMEOUT_S"])
        if os.environ.get("FANSIVIBE_REASONING_TEMPERATURE"):
            env["temperature"] = float(os.environ["FANSIVIBE_REASONING_TEMPERATURE"])
        if os.environ.get("FANSIVIBE_REASONING_MAX_RETRIES"):
            env["max_retries"] = int(os.environ["FANSIVIBE_REASONING_MAX_RETRIES"])
        if os.environ.get("FANSIVIBE_REASONING_NUM_PREDICT"):
            env["num_predict"] = int(os.environ["FANSIVIBE_REASONING_NUM_PREDICT"])
        env.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**env)


class _RetryableTransport(Exception):
    """Internal: transport failure worth one more attempt (never escapes).

    Carries its terminal category so exhausted retries surface the true
    failure (timeout/unavailable/http_error), never a generic error.
    """

    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def _strip_fences(text: str) -> str:
    """Remove a single markdown fence pair (transport hygiene, not repair)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


class OllamaFashionReasoner:
    """`FashionReasoner` over Ollama `/api/chat` in JSON mode."""

    contract_version: str = REASONING_CONTRACT_VERSION

    def __init__(
        self,
        config: ReasoningConfig | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._config = config or ReasoningConfig.from_env()
        self._client = http_client

    def describe(self) -> dict:
        """Model configuration for evaluation metadata (no secrets)."""
        return {
            "provider": "ollama",
            "base_url": self._config.base_url,
            "model": self._config.model,
            "temperature": self._config.temperature,
            "timeout_s": self._config.timeout_s,
            "max_retries": self._config.max_retries,
            "num_predict": self._config.num_predict,
            "contract_version": self.contract_version,
        }

    def _payload(self, reasoning_input: FashionReasoningInput) -> dict:
        options: dict = {"temperature": self._config.temperature}
        if self._config.num_predict is not None:
            options["num_predict"] = self._config.num_predict
        return {
            "model": self._config.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": build_user_prompt(reasoning_input)},
            ],
            "options": options,
        }

    def _post(self, payload: dict) -> httpx.Response:
        url = self._config.base_url.rstrip("/") + _CHAT_PATH
        if self._client is not None:
            return self._client.post(url, json=payload, timeout=self._config.timeout_s)
        with httpx.Client(timeout=self._config.timeout_s) as client:
            return client.post(url, json=payload)

    def _attempt(self, reasoning_input: FashionReasoningInput) -> dict:
        try:
            response = self._post(self._payload(reasoning_input))
        except httpx.TimeoutException as exc:
            raise _RetryableTransport(
                "timeout", f"ollama timeout after {self._config.timeout_s}s"
            ) from exc
        except httpx.TransportError as exc:
            raise _RetryableTransport("unavailable", f"ollama unreachable: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ReasoningExecutionError("unavailable", f"ollama request failed: {exc}") from exc
        status = response.status_code
        if status >= 500:
            raise _RetryableTransport("http_error", f"ollama HTTP {status}")
        if status != 200:
            raise ReasoningExecutionError("http_error", f"ollama HTTP {status}")
        try:
            body = response.json()
        except ValueError as exc:
            raise ReasoningExecutionError("malformed_json", "ollama non-JSON body") from exc
        content = (body.get("message") or {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ReasoningExecutionError("malformed_json", "ollama empty content")
        try:
            parsed = json.loads(_strip_fences(content))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ReasoningExecutionError("malformed_json", "model output is not JSON") from exc
        if not isinstance(parsed, dict):
            raise ReasoningExecutionError("malformed_json", "model output is not an object")
        return parsed

    def _check_ffo_refs(
        self, output: FashionReasoningOutput, reasoning_input: FashionReasoningInput
    ) -> None:
        permitted = set(reasoning_input.entities)
        for item in reasoning_input.evidence:
            permitted.update(item.ffo_references)
        offenders = sorted(
            {
                ref
                for conclusion in output.conclusions
                for ref in conclusion.ffo_refs
                if ref not in permitted
            }
        )
        if offenders:
            raise ReasoningExecutionError(
                "invalid_output", f"unpermitted FFO references: {offenders}"
            )

    def reason(self, reasoning_input: FashionReasoningInput) -> FashionReasoningOutput:
        """Execute one reasoning call; typed errors, max 1+max_retries attempts."""
        started = time.perf_counter()
        attempts = 1 + max(0, self._config.max_retries)
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                parsed = self._attempt(reasoning_input)
                try:
                    output = validate_output(parsed, input=reasoning_input)
                except ReasoningContractError as exc:
                    raise ReasoningExecutionError("invalid_output", str(exc)) from exc
                self._check_ffo_refs(output, reasoning_input)
                logger.debug(
                    "reasoning ok model=%s latency=%.2fs conclusions=%d",
                    self._config.model,
                    time.perf_counter() - started,
                    len(output.conclusions),
                )
                return output
            except _RetryableTransport as exc:
                last_error = exc
                logger.debug(
                    "reasoning retry %d/%d model=%s: %s",
                    attempt, attempts, self._config.model, exc,
                )
        assert last_error is not None
        logger.info(
            "reasoning failed model=%s category=%s latency=%.2fs",
            self._config.model, last_error.category, time.perf_counter() - started,
        )
        raise ReasoningExecutionError(last_error.category, str(last_error)) from last_error


__all__ = [
    "OllamaFashionReasoner",
    "ReasoningConfig",
    "ReasoningExecutionError",
]
