"""Self-hosted LLM fashion reasoning & enrichment (Ollama).

The backend runs on the server, serving Ollama models (such as `qwen3-vl:4b-instruct`).
When Ollama is unreachable, times out, or fails, the engine falls back cleanly
to our deterministic rules text — the structured contract and wardrobe IDs
are never lost or altered.

Integrates with the two-tier GPU scheduler (Sub-Batch 3.2) for priority-1
interactive inference leases.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, List, Optional

import httpx

from app.telemetry.metrics import get_metrics_collector

logger = logging.getLogger("fansivibe.ai.llm")


@dataclass
class LlmProvenanceState:
    provider: str = "ollama"
    model: Optional[str] = None
    status: str = "not_requested"
    reason: Optional[str] = None
    error_type: Optional[str] = None
    duration_ms: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "reason": self.reason,
            "errorType": self.error_type,
            "durationMs": self.duration_ms,
        }

_HOST = os.environ.get("FANSIVIBE_OLLAMA_HOST", "http://localhost:11434")
_DEFAULT_MODEL = os.environ.get("FANSIVIBE_OLLAMA_MODEL", "qwen3-vl:4b-instruct")
_TIMEOUT = 10.0


def _system_prompt() -> str:
    return (
        "You are Fansivibe's AI Stylist. Be warm, specific, elegant, and helpful. "
        "Never judge appearance or shame users. Ground all wardrobe recommendations "
        "in the user's actual owned garments. Clearly distinguish between garments the user owns "
        "and suggestions for items they do not own. Do not use markdown code fences or raw symbols."
    )


def get_active_model() -> str:
    """Return the model to use, dynamically checking Ollama tags if needed."""
    env_model = os.environ.get("FANSIVIBE_OLLAMA_MODEL")
    if env_model and env_model != "llama3.1:8b":
        return env_model

    try:
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(f"{_HOST}/api/tags")
            if resp.status_code == 200:
                models = [m.get("name") for m in resp.json().get("models", [])]
                if env_model in models:
                    return env_model
                if "qwen3-vl:4b-instruct" in models:
                    return "qwen3-vl:4b-instruct"
                for m in models:
                    if m and ("qwen" in m or "llama" in m):
                        return m
                if models:
                    return models[0]
    except Exception:
        pass

    return _DEFAULT_MODEL


def is_available() -> bool:
    if os.environ.get("FANSIVIBE_DISABLE_LLM") == "1":
        return False
    try:
        with httpx.Client(timeout=1.5) as client:
            return client.get(f"{_HOST}/api/tags").status_code == 200
    except Exception:
        return False


def _acquire_gpu_lease_context(model_id: str):
    """Acquire Priority 1 GPU lease context manager, or nullcontext if scheduler unavailable."""
    try:
        from app.ai.manager.scheduler import get_gpu_scheduler
        from app.ai.manager.types import WorkloadType
        scheduler = get_gpu_scheduler()
        return scheduler.acquire_lease_sync(
            model_id=model_id,
            workload_type=WorkloadType.REASONING_VISION,
            priority=1,
            timeout_s=_TIMEOUT + 5.0,
            acquisition_timeout_s=3.0,
        )
    except Exception as exc:
        logger.debug("Scheduler lease acquisition unavailable: %s", exc)
        return nullcontext(None)


def _execute_chat_inference(
    messages: list[dict],
    model: str,
    client: Optional[httpx.Client] = None,
) -> Optional[str]:
    """Execute Ollama chat inference under two-tier GPU scheduler lease coordination.

    Complete request lifecycle:
    1. Acquire the Priority 1 GPU lease (synchronous context manager).
    2. Register termination check and submit inference request to Ollama.
    3. Receive HTTP response and check status code.
    4. Read the complete response body (_ = response.content).
    5. Mark workload completion ONLY AFTER complete body is read.
    6. Complete parsing and extract content.
    7. Safely release GPU lease via context manager __exit__.
    """
    cm = _acquire_gpu_lease_context(model)

    with cm as lease:
        request_submitted = False
        if lease is not None:
            lease.register_termination_check(lambda: not request_submitted)

        try:
            request_submitted = True
            payload = {
                "model": model,
                "stream": False,
                "messages": messages,
            }
            if client is not None:
                response = client.post(f"{_HOST}/api/chat", json=payload, timeout=_TIMEOUT)
            else:
                with httpx.Client(timeout=_TIMEOUT) as http_client:
                    response = http_client.post(f"{_HOST}/api/chat", json=payload)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            request_submitted = False
            raise

        response.raise_for_status()

        # Critical requirement: receiving HTTP 200 headers alone must NOT mark inference
        # as completed. The lease must remain active until the complete response body has been received.
        _ = response.content

        # Mark workload completion ONLY after confirmed receipt of full response body
        if lease is not None:
            lease.mark_workload_completed()

        body = response.json()
        content = (body.get("message") or {}).get("content", "")
        return content.strip() if isinstance(content, str) and content.strip() else None


def _failure_reason(exc: Exception) -> str:
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return "timeout"
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return "provider_unreachable"
    return "error"


def _record_llm_call(
    state: LlmProvenanceState,
    *,
    started_at: float,
    status: str,
    reason: str,
    error_type: Optional[str] = None,
) -> None:
    duration_s = max(0.0, time.perf_counter() - started_at)
    state.status = status
    state.reason = reason
    state.error_type = error_type
    state.duration_ms = int(round(duration_s * 1000))
    get_metrics_collector().record_llm_enrichment(
        provider=state.provider,
        model=state.model or "unknown",
        status=status,
        reason=reason,
        error_type=error_type or "none",
        duration_s=duration_s,
    )
    logger.info(
        "LLM enrichment provider=%s model=%s status=%s reason=%s error_type=%s duration_ms=%d",
        state.provider,
        state.model or "unknown",
        status,
        reason,
        error_type or "none",
        state.duration_ms,
    )


def unavailable_provenance(
    reason: str = "provider_unavailable",
) -> LlmProvenanceState:
    state = LlmProvenanceState(model=os.environ.get("FANSIVIBE_OLLAMA_MODEL", _DEFAULT_MODEL))
    _record_llm_call(
        state,
        started_at=time.perf_counter(),
        status="fallback",
        reason=reason,
    )
    return state


def enrich_reply(
    intent: str,
    base_text: str,
    context: str,
    client: Optional[httpx.Client] = None,
    provenance_out: Optional[LlmProvenanceState] = None,
) -> str:
    """Return a personalized reply from the local model, or [base_text] on any failure."""
    state = provenance_out or LlmProvenanceState()
    started_at = time.perf_counter()
    try:
        model = get_active_model()
        state.model = model
        messages = [
            {"role": "system", "content": _system_prompt()},
            {"role": "system", "content": f"User context:\n{context}"},
            {"role": "user", "content": base_text},
        ]
        content = _execute_chat_inference(messages, model, client=client)
        if content:
            _record_llm_call(state, started_at=started_at, status="generated", reason="none")
            return content
        _record_llm_call(state, started_at=started_at, status="fallback", reason="empty_response")
        return base_text
    except Exception as exc:
        _record_llm_call(
            state,
            started_at=started_at,
            status="fallback",
            reason=_failure_reason(exc),
            error_type=type(exc).__name__,
        )
        return base_text


def enrich_stylist_recommendation(
    *,
    user_query: str,
    occasion: str,
    selected_components: List[dict],
    missing_categories: Optional[List[str]] = None,
    weather_context: Optional[str] = None,
    unowned_garment_query: Optional[str] = None,
    base_text: str,
    conversation_history: Optional[List[dict]] = None,
    client: Optional[httpx.Client] = None,
    provenance_out: Optional[LlmProvenanceState] = None,
) -> str:
    """Generate an explainable AI Stylist natural language recommendation.

    Strictly grounded in:
    1. Real selected wardrobe components (names, colors, materials).
    2. Explicit distinction for unowned garments or suggested additions.
    3. Weather and occasion context when provided.
    Falls back gracefully to [base_text] on any model failure, timeout, or network issue.
    """
    state = provenance_out or LlmProvenanceState()
    started_at = time.perf_counter()
    try:
        model = get_active_model()
        state.model = model

        # Build structured context for the stylist reasoning
        garment_lines = [
            f"- {c.get('name', 'Garment')} ({c.get('category', 'piece')}, {c.get('color', '')}, {c.get('material', '') or 'fabric'})"
            for c in selected_components
        ]
        garments_str = "\n".join(garment_lines) if garment_lines else "No specific pieces"

        missing_str = ""
        if missing_categories:
            missing_str = f"Missing Categories (Not in user's wardrobe): {', '.join(missing_categories)}."

        weather_str = f"Current Weather: {weather_context}." if weather_context else ""

        unowned_note = ""
        if unowned_garment_query:
            unowned_note = (
                f"Note: User specifically asked to style '{unowned_garment_query}', but they do NOT own it in their wardrobe. "
                f"Acknowledge politely that '{unowned_garment_query}' isn't in their current collection, present this outfit from their available items, "
                f"and mention how '{unowned_garment_query}' could be paired if acquired."
            )

        instructions = (
            "You are Fansivibe's AI Stylist. Craft an encouraging, stylish, and concise recommendation (2-4 sentences).\n"
            f"Occasion: {occasion}\n"
            f"{weather_str}\n"
            f"Owned Wardrobe Garments Selected for the Outfit:\n{garments_str}\n"
            f"{missing_str}\n"
            f"{unowned_note}\n\n"
            "Requirements:\n"
            "1. Explain why the owned garments coordinate well together (color harmony, fit, occasion appropriateness).\n"
            "2. Never claim unowned garments are in their wardrobe. Clearly label any missing item suggestions as additions to look out for.\n"
            "3. Offer 1 practical styling tip (e.g. cuffing, tucking, layering).\n"
            "4. Output only clean text without markdown or symbols."
        )

        messages: list[dict] = [{"role": "system", "content": instructions}]
        if conversation_history:
            for turn in conversation_history[-4:]:
                r = turn.get("role")
                c = turn.get("content")
                if r in ("user", "assistant") and isinstance(c, str) and c.strip():
                    messages.append({"role": r, "content": c.strip()})

        messages.append({"role": "user", "content": user_query or f"Recommend an outfit for {occasion}."})

        content = _execute_chat_inference(messages, model, client=client)
        if content:
            _record_llm_call(state, started_at=started_at, status="generated", reason="none")
            return content
        _record_llm_call(state, started_at=started_at, status="fallback", reason="empty_response")
        return base_text
    except Exception as exc:
        _record_llm_call(
            state,
            started_at=started_at,
            status="fallback",
            reason=_failure_reason(exc),
            error_type=type(exc).__name__,
        )
        return base_text

