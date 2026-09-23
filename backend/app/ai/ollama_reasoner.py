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
from dataclasses import dataclass, field, replace

import httpx

from app.ai.reasoning_prompt import build_system_prompt, build_user_prompt
from app.domain.services.conclusion_admission import MISSING_RECORD, apply_admission
from app.domain.services.ffo_ref_selector import select_refs
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
    connect_timeout_s: float = 5.0
    temperature: float = 0.0
    max_retries: int = 1
    num_predict: int | None = None
    keep_alive: str | None = None

    @classmethod
    def from_env(cls, **overrides) -> "ReasoningConfig":
        """Build from canonical `FANSIVIBE_OLLAMA_*` / `FANSIVIBE_REASONING_*` env."""
        env: dict = {
            "base_url": os.environ.get(
                "FANSIVIBE_OLLAMA_BASE_URL",
                os.environ.get("FANSIVIBE_OLLAMA_HOST", cls.base_url),
            ),
            "model": os.environ.get("FANSIVIBE_OLLAMA_MODEL", cls.model),
        }
        raw_timeout = os.environ.get(
            "FANSIVIBE_OLLAMA_TIMEOUT",
            os.environ.get("FANSIVIBE_REASONING_TIMEOUT_S"),
        )
        if raw_timeout:
            env["timeout_s"] = float(raw_timeout)
        if os.environ.get("FANSIVIBE_OLLAMA_CONNECT_TIMEOUT"):
            env["connect_timeout_s"] = float(os.environ["FANSIVIBE_OLLAMA_CONNECT_TIMEOUT"])
        if os.environ.get("FANSIVIBE_REASONING_TEMPERATURE"):
            env["temperature"] = float(os.environ["FANSIVIBE_REASONING_TEMPERATURE"])
        if os.environ.get("FANSIVIBE_REASONING_MAX_RETRIES"):
            env["max_retries"] = int(os.environ["FANSIVIBE_REASONING_MAX_RETRIES"])
        if os.environ.get("FANSIVIBE_REASONING_NUM_PREDICT"):
            env["num_predict"] = int(os.environ["FANSIVIBE_REASONING_NUM_PREDICT"])
        if os.environ.get("FANSIVIBE_REASONING_KEEP_ALIVE"):
            env["keep_alive"] = os.environ.get("FANSIVIBE_REASONING_KEEP_ALIVE")
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
        data = {
            "provider": "ollama",
            "base_url": self._config.base_url,
            "model": self._config.model,
            "temperature": self._config.temperature,
            "timeout_s": self._config.timeout_s,
            "connect_timeout_s": self._config.connect_timeout_s,
            "max_retries": self._config.max_retries,
            "num_predict": self._config.num_predict,
            "contract_version": self.contract_version,
        }
        if self._config.keep_alive is not None:
            data["keep_alive"] = self._config.keep_alive
        return data

    def _payload(self, reasoning_input: FashionReasoningInput) -> dict:
        options: dict = {"temperature": self._config.temperature}
        if self._config.num_predict is not None:
            options["num_predict"] = self._config.num_predict
        payload = {
            "model": self._config.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": build_user_prompt(reasoning_input)},
            ],
            "options": options,
        }
        if self._config.keep_alive is not None:
            payload["keep_alive"] = self._config.keep_alive
        return payload

    def _post(self, payload: dict) -> httpx.Response:
        url = self._config.base_url.rstrip("/") + _CHAT_PATH
        timeout = httpx.Timeout(self._config.timeout_s, connect=self._config.connect_timeout_s)
        if self._client is not None:
            return self._client.post(url, json=payload, timeout=timeout)
        with httpx.Client(timeout=timeout) as client:
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

    def _admission_universe(self, reasoning_input: FashionReasoningInput) -> dict:
        """FFO universe for admission, derived from the evidence pack only.

        Pack-derived (never `input.entities`: `build_case_input` fills that
        from benchmark expectations, which must not leak into admission).
        """
        canonicals: set = set()
        aliases: dict = {}
        kinds: set = set()
        effects: set = set()
        for item in reasoning_input.evidence:
            content = getattr(item, "content", None)
            if not isinstance(content, dict):
                continue
            if content.get("canonical_id"):
                canonicals.add(content["canonical_id"])
            if content.get("alias") and content.get("canonical_id"):
                aliases[content["alias"]] = content["canonical_id"]
            if content.get("entity_kind"):
                kinds.add(content["entity_kind"])
            payload = content.get("payload")
            if isinstance(payload, dict) and payload.get("effect"):
                effects.add(payload["effect"])
            for key in ("subject", "object"):
                if content.get(key):
                    canonicals.add(content[key])
        return {"canonicals": canonicals, "aliases": aliases,
                "kinds": kinds, "effects": effects}

    def _admission_records(self, parsed: dict) -> list:
        """Positional admission records from raw model JSON (3T validates)."""
        conclusions = parsed.get("conclusions", [])
        if not isinstance(conclusions, list):
            return []
        return [c.get("admission") if isinstance(c, dict) else None
                for c in conclusions]

    def _admission_result(self, output, reasoning_input, records) -> dict:
        """3T gate over validated conclusions; pure, remove-only (3P untouched)."""
        return apply_admission(
            list(output.conclusions),
            list(records or []),
            query=reasoning_input.request.query,
            universe=self._admission_universe(reasoning_input),
            evidence=list(reasoning_input.evidence),
            unsupported=output.unsupported,
        )

    def _apply_admission(self, output, reasoning_input, records):
        """Admission gate (3T) before ref selection (3P); returns (output, result).

        Fail-closed: conclusions without records are an invalid output (the
        prompt requires records). Merit rejections that empty the conclusions
        fall back to the 3A insufficient-evidence shape (coverage-derived
        missing_evidence only when the model supplied none) — never
        fabrication, never rewritten statements/refs.
        """
        result = self._admission_result(output, reasoning_input, records)
        outcomes = result["outcomes"]
        if outcomes and all(o["reason"] == MISSING_RECORD for o in outcomes):
            raise ReasoningExecutionError(
                "invalid_output", "admission: conclusions lack admission records"
            )
        admitted = result["admitted"]
        if not admitted and list(output.conclusions):
            missing = tuple(output.missing_evidence) or tuple(result["missing_evidence"])
            logger.debug("admission emptied conclusions reasons=%s",
                         sorted({o["reason"] for o in outcomes}))
            return (replace(output, conclusions=(), missing_evidence=missing), result)
        if len(admitted) != len(output.conclusions):
            logger.debug(
                "admission dropped conclusions=%d reasons=%s",
                len(output.conclusions) - len(admitted),
                sorted({o["reason"] for o in outcomes if o["outcome"] == "reject"}),
            )
        return replace(output, conclusions=tuple(admitted)), result

    def _select_refs(
        self, output: FashionReasoningOutput, reasoning_input: FashionReasoningInput
    ) -> FashionReasoningOutput:
        """Role-aware ref filter (3P): remove-only, statements untouched.

        Runs after structural validation, before the FFO permission check
        (which still rejects anything outside the permitted universe).
        """
        query = reasoning_input.request.query
        intent = reasoning_input.request.intent
        conclusions = []
        for conclusion in output.conclusions:
            kept, decisions = select_refs(
                conclusion.statement,
                conclusion.ffo_refs,
                conclusion.evidence_ids,
                reasoning_input.evidence,
                query,
                intent,
            )
            dropped = [d["reference"] for d in decisions if d["action"] == "drop"]
            if dropped:
                logger.debug("selector dropped refs=%s", sorted(set(dropped)))
            conclusions.append(replace(conclusion, ffo_refs=tuple(kept)))
        return replace(output, conclusions=tuple(conclusions))

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
                output, _ = self._apply_admission(
                    output, reasoning_input, self._admission_records(parsed)
                )
                output = self._select_refs(output, reasoning_input)
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
