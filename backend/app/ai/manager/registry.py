"""Model Registry for centralized tracking of AI models, requirements and states.

Phase 1 foundation: Maintains verified model metadata and honest requirement tracking.
Enforces that unverified values (such as FASHN VTON requirements) are explicitly marked unverified.
"""

from __future__ import annotations

import copy
import logging
import threading
import time
from typing import Dict, List, Optional

from app.ai.manager.types import (
    ModelInfo,
    ModelNotFoundError,
    ModelProviderType,
    ModelState,
    WorkloadType,
)

logger = logging.getLogger("fansivibe.ai.manager.registry")

# Canonical initial models with honest verification flags
_DEFAULT_MODELS: tuple[ModelInfo, ...] = (
    ModelInfo(
        model_id="qwen3-vl:4b-instruct",
        family="qwen3vl",
        provider=ModelProviderType.OLLAMA,
        workload_type=WorkloadType.REASONING_VISION,
        current_state=ModelState.COLD,
        min_vram_bytes=3_527_545_978,  # Static weight residency: 3,527,545,978 bytes (~3.29 GiB / 3,364 MiB) measured via Ollama /api/ps
        min_ram_bytes=None,  # Runs out-of-process in Ollama server; no in-process Python RAM cache
        is_verified=True,
        verification_notes=(
            "Measured static weight residency from local Ollama /api/ps (3,527,545,978 bytes ~3.29 GiB). "
            "Note: Peak execution allocation in physical GPU VRAM reaches ~4,596 MiB (~4.49 GiB) in nvidia-smi "
            "with context and vision activations. Base residency is not a guaranteed safe execution budget ceiling."
        ),
    ),
    ModelInfo(
        model_id="fashn-vton-v1.5",
        family="mmdit",
        provider=ModelProviderType.PYTORCH,
        workload_type=WorkloadType.VTON_DIFFUSION,
        current_state=ModelState.COLD,
        min_vram_bytes=None,  # UNVERIFIED: Not invented. Pending physical benchmark after installation.
        min_ram_bytes=None,  # UNVERIFIED: Not invented.
        is_verified=False,
        verification_notes=(
            "UNVERIFIED: PyTorch, Diffusers, and model weights are not installed on host. "
            "Exact VRAM and host RAM requirements must be physically measured after approved dependency installation."
        ),
    ),
    ModelInfo(
        model_id="mock-vton",
        family="mock",
        provider=ModelProviderType.MOCK,
        workload_type=WorkloadType.VTON_DIFFUSION,
        current_state=ModelState.COLD,
        min_vram_bytes=0,
        min_ram_bytes=0,
        is_verified=True,
        verification_notes="Deterministic $0 in-memory SVG mock; zero VRAM and zero RAM required.",
    ),
)


class ModelRegistry:
    """Thread-safe registry for AI models."""

    def __init__(self, pre_register_defaults: bool = True) -> None:
        self._lock = threading.Lock()
        self._models: Dict[str, ModelInfo] = {}
        if pre_register_defaults:
            for m in _DEFAULT_MODELS:
                self._models[m.model_id] = copy.deepcopy(m)

    def register(self, model_info: ModelInfo) -> None:
        """Register or update a model specification."""
        with self._lock:
            self._models[model_info.model_id] = copy.deepcopy(model_info)

    def get(self, model_id: str) -> ModelInfo:
        """Retrieve model metadata by ID or raise ModelNotFoundError."""
        with self._lock:
            info = self._models.get(model_id)
            if info is None:
                raise ModelNotFoundError(model_id)
            return copy.deepcopy(info)

    def list_models(self) -> List[ModelInfo]:
        """List all currently registered models."""
        with self._lock:
            return [copy.deepcopy(m) for m in self._models.values()]

    def is_registered(self, model_id: str) -> bool:
        """Check whether a model ID is registered."""
        with self._lock:
            return model_id in self._models

    def update_state(
        self,
        model_id: str,
        new_state: ModelState,
        observation_timestamp: Optional[float] = None,
    ) -> ModelInfo:
        """Update the residency state of a model with monotonic observation fencing.

        Thread-safe method that updates a registered model's current residency state
        while enforcing monotonic observation fencing on an independent observation
        timeline (last_observation_timestamp) separate from state-transition history
        (last_state_change).

        Args:
            model_id: Unique identifier of the registered model.
            new_state: Newly observed ModelState (HOT, COLD, UNKNOWN).
            observation_timestamp: Optional POSIX timestamp (in seconds) representing
                when the observation was made. When None, current wall-clock time
                (time.time()) is used, but cannot bypass an established timestamp fence
                (i.e. if current time is strictly less than an established future/higher
                last_observation_timestamp, the legacy call is rejected as stale).

        Fencing Rules:
            - Newer observation (observation_timestamp > info.last_observation_timestamp):
              ACCEPTED. last_observation_timestamp advances to observation_timestamp.
              last_state_change is updated to observation_timestamp ONLY IF the model's
              current_state actually changes (new_state != info.current_state).
            - Stale observation (observation_timestamp < info.last_observation_timestamp):
              REJECTED. The stale observation is safely discarded/ignored without
              altering current_state, last_state_change, or last_observation_timestamp.
            - Equal timestamp (observation_timestamp == info.last_observation_timestamp):
              DETERMINISTIC LAST-WRITE-WINS: ACCEPTED. If new_state != info.current_state,
              current_state and last_state_change are updated. If new_state == info.current_state,
              this is an idempotent refresh and last_state_change remains unchanged.
            - Legacy un-timestamped callers:
              When observation_timestamp is None, effective_ts = time.time(). If effective_ts
              is strictly less than info.last_observation_timestamp, the call is rejected to
              prevent bypassing an established fence. Otherwise, it is accepted and advances
              last_observation_timestamp, updating last_state_change only on state change.

        Returns:
            An isolated ModelInfo snapshot reflecting the post-fencing state.

        Raises:
            ModelNotFoundError: If model_id is not registered.
        """
        with self._lock:
            info = self._models.get(model_id)
            if info is None:
                raise ModelNotFoundError(model_id)

            if observation_timestamp is not None:
                effective_ts = observation_timestamp
                is_legacy = False
            else:
                effective_ts = time.time()
                is_legacy = True

            if effective_ts < info.last_observation_timestamp:
                logger.debug(
                    "Rejected %s observation for model '%s': "
                    "timestamp=%.6f < last_observation_timestamp=%.6f",
                    "untimestamped" if is_legacy else "stale",
                    model_id,
                    effective_ts,
                    info.last_observation_timestamp,
                )
                return copy.deepcopy(info)

            info.last_observation_timestamp = effective_ts
            if new_state != info.current_state:
                info.current_state = new_state
                info.last_state_change = effective_ts

            return copy.deepcopy(info)

    def update_memory_requirements(
        self,
        model_id: str,
        *,
        min_vram_bytes: Optional[int] = None,
        min_ram_bytes: Optional[int] = None,
        is_verified: bool = False,
        verification_notes: Optional[str] = None,
    ) -> ModelInfo:
        """Update verified memory requirements for a model after measurement."""
        with self._lock:
            info = self._models.get(model_id)
            if info is None:
                raise ModelNotFoundError(model_id)
            if min_vram_bytes is not None:
                info.min_vram_bytes = min_vram_bytes
            if min_ram_bytes is not None:
                info.min_ram_bytes = min_ram_bytes
            info.is_verified = is_verified
            if verification_notes is not None:
                info.verification_notes = verification_notes
            return copy.deepcopy(info)

    def reset_for_tests(self) -> None:
        """Reset registry back to clean default state (test isolation only)."""
        with self._lock:
            self._models.clear()
            for m in _DEFAULT_MODELS:
                self._models[m.model_id] = copy.deepcopy(m)

