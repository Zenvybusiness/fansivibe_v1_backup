"""Ollama model lifecycle manager (Phase 3AL).

Manages model availability checks, tag inspection, and startup warmup
to keep the reasoning model pinned in GPU/system memory with configured
keep_alive, avoiding cold-start latency spikes on user queries.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

import httpx

from app.config.settings import get_settings

logger = logging.getLogger("fansivibe.ai.lifecycle")


@dataclass(frozen=True)
class ModelStatus:
    """Readiness status of the reasoning model in Ollama."""

    available: bool
    model_present: bool
    model_name: str
    host: str
    latency_ms: float
    error: Optional[str] = None
    details: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OllamaLifecycleManager:
    """Manages Ollama model probe and warmup lifecycle."""

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        keep_alive: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.host = (host or settings.reasoning_host).rstrip("/")
        self.model = model or settings.reasoning_model
        self.keep_alive = keep_alive or settings.reasoning_keep_alive
        self._client = client

    def check_availability(self, timeout_s: float = 3.0) -> ModelStatus:
        """Probe Ollama /api/tags to verify host reachability and model presence."""
        url = f"{self.host}/api/tags"
        t0 = time.monotonic()
        try:
            timeout = httpx.Timeout(timeout_s, connect=2.0)
            if self._client is not None:
                resp = self._client.get(url, timeout=timeout)
            else:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.get(url)
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)

            if resp.status_code != 200:
                return ModelStatus(
                    available=False,
                    model_present=False,
                    model_name=self.model,
                    host=self.host,
                    latency_ms=elapsed_ms,
                    error=f"Ollama returned HTTP {resp.status_code}",
                )

            data = resp.json()
            models_list = data.get("models", [])
            tag_names: list[str] = [
                m.get("name", "") for m in models_list if isinstance(m, dict)
            ]

            target = self.model.lower()
            target_base = target.split(":")[0]
            matched = any(
                tag == target
                or tag.split(":")[0] == target_base
                or tag.startswith(f"{target}:")
                for tag in tag_names
            )

            return ModelStatus(
                available=True,
                model_present=matched,
                model_name=self.model,
                host=self.host,
                latency_ms=elapsed_ms,
                error=None if matched else f"Model '{self.model}' not found in local Ollama library",
                details={
                    "available_models": tag_names,
                    "model_count": len(tag_names),
                },
            )
        except Exception as exc:
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
            logger.warning(
                "Ollama availability probe failed on %s: %s (%s ms)",
                url,
                exc,
                elapsed_ms,
            )
            return ModelStatus(
                available=False,
                model_present=False,
                model_name=self.model,
                host=self.host,
                latency_ms=elapsed_ms,
                error=f"{type(exc).__name__}: {exc}",
            )

    def warmup(self, timeout_s: float = 30.0) -> bool:
        """Trigger a lightweight warmup request to pin the model in memory."""
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_predict": 1},
        }
        t0 = time.monotonic()
        try:
            logger.info(
                "Initiating model warmup for '%s' (keep_alive=%s)...",
                self.model,
                self.keep_alive,
            )
            timeout = httpx.Timeout(timeout_s, connect=5.0)
            if self._client is not None:
                resp = self._client.post(url, json=payload, timeout=timeout)
            else:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(url, json=payload)
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)

            if resp.status_code == 200:
                logger.info(
                    "Model warmup successful for '%s' in %s ms (pinned with keep_alive=%s)",
                    self.model,
                    elapsed_ms,
                    self.keep_alive,
                )
                return True
            logger.warning(
                "Model warmup for '%s' returned HTTP %s in %s ms: %s",
                self.model,
                resp.status_code,
                elapsed_ms,
                resp.text[:200],
            )
            return False
        except Exception as exc:
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
            logger.warning(
                "Model warmup failed for '%s' after %s ms: %s",
                self.model,
                elapsed_ms,
                exc,
            )
            return False
