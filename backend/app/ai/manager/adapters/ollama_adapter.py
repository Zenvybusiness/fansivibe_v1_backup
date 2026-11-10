"""Ollama Model Adapter for AI Model Resource Manager (Phase 2 Batch 2 & Batch 2.1 Hardening).

Provides an authoritative interface between Fansivibe's shared AI Model Resource Manager
and an external Ollama daemon.

Key Responsibilities:
- Inspecting loaded models and VRAM residency via Ollama `/api/ps`.
- Normalizing Ollama runtime states into manager-compatible `ModelState` (HOT, COLD, UNKNOWN).
- Strictly enforcing that `ModelState.WARM` is never falsely claimed for Ollama models.
- Correct residency classification: `size_vram_bytes > 0` produces HOT; `size_vram_bytes == 0`,
  missing, or invalid VRAM produces UNKNOWN; absent from `/api/ps` produces COLD.
- Monotonic observation fencing synchronization with `ModelRegistry`.
- Bounded-deadline unload verification polling loops protecting against stalled HTTP calls.
- Per-model serialization of concurrent unloads across sync threads and async coroutines.
- Explicit, verifiable model eviction via `POST /api/generate` (`keep_alive: 0`) with
  mandatory polling verification on `/api/ps` to ensure VRAM release before reporting success.
- Comprehensive fault tolerance, structured error taxonomy, and deterministic mocking support.
- Composition and reuse of existing `OllamaLifecycleManager` for tag checks and warmup.

Caller Coordination & Concurrency Contract (F-04):
- The adapter DOES NOT acquire or release GPU scheduler leases.
- Callers (e.g. higher-level orchestrators) MUST ensure that no active workload is using the
  target model before initiating an unload operation.
- Phase 2 Batch 3 will introduce integrated GPU scheduler lease acquisition and eviction coordination.
- Model inspection operations (list_loaded_models, get_model_residency, is_model_loaded)
  remain strictly read-only and non-mutating; they do not alter daemon state or acquire leases.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, List, Optional

import httpx

from app.ai.lifecycle import ModelStatus, OllamaLifecycleManager
from app.ai.manager.registry import ModelRegistry
from app.ai.manager.types import ModelManagerError, ModelState
from app.config.settings import get_settings

logger = logging.getLogger("fansivibe.ai.manager.ollama")

_PS_ENDPOINT = "/api/ps"
_GENERATE_ENDPOINT = "/api/generate"


# ---------------------------------------------------------------------------
# Structured Domain Exceptions
# ---------------------------------------------------------------------------


class OllamaAdapterError(ModelManagerError):
    """Base exception for all Ollama adapter operations."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class OllamaConnectionError(OllamaAdapterError):
    """Raised when Ollama daemon is unreachable or connection is refused."""

    def __init__(self, message: str, host: str = "") -> None:
        super().__init__(message)
        self.host = host


class OllamaTimeoutError(OllamaAdapterError):
    """Raised when an HTTP operation to Ollama times out."""

    def __init__(self, message: str, timeout_s: float = 0.0) -> None:
        super().__init__(message)
        self.timeout_s = timeout_s


class OllamaResponseError(OllamaAdapterError):
    """Raised when Ollama returns an HTTP error or malformed/unexpected payload."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class OllamaModelNotFoundError(OllamaAdapterError):
    """Raised when the specified model is not found in the Ollama library."""

    def __init__(self, model_name: str) -> None:
        super().__init__(f"Model '{model_name}' was not found in Ollama library.")
        self.model_name = model_name


class OllamaUnloadError(OllamaAdapterError):
    """Raised when an explicit model unload operation fails or cannot be confirmed."""

    def __init__(self, message: str, model_name: str = "") -> None:
        super().__init__(message)
        self.model_name = model_name


class OllamaUnloadTimeoutError(OllamaUnloadError):
    """Raised when model remains loaded in /api/ps after unload request timeout."""

    def __init__(self, model_name: str, timeout_s: float) -> None:
        super().__init__(
            f"Model '{model_name}' remained loaded in Ollama /api/ps after unload timeout of {timeout_s:.1f}s.",
            model_name=model_name,
        )
        self.timeout_s = timeout_s


# ---------------------------------------------------------------------------
# Value Objects and Normalized Containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OllamaLoadedModel:
    """Normalized snapshot of a loaded model reported by Ollama /api/ps."""

    name: str
    model: str
    size_bytes: Optional[int] = None
    size_vram_bytes: Optional[int] = None
    expires_at: Optional[str] = None
    digest: Optional[str] = None
    details: Optional[dict[str, Any]] = None

    @property
    def size_mib(self) -> Optional[float]:
        if self.size_bytes is None:
            return None
        return round(self.size_bytes / (1024 * 1024), 2)

    @property
    def size_vram_mib(self) -> Optional[float]:
        if self.size_vram_bytes is None:
            return None
        return round(self.size_vram_bytes / (1024 * 1024), 2)


@dataclass(frozen=True)
class OllamaModelResidency:
    """Normalized residency state of a specific model in Ollama.
    
    Invariants:
    - State is strictly HOT, COLD, or UNKNOWN.
    - WARM is forbidden because Ollama does not expose CPU-resident pinned memory.
    """

    model_name: str
    state: ModelState
    is_loaded: bool
    size_vram_bytes: Optional[int] = None
    size_bytes: Optional[int] = None
    expires_at: Optional[str] = None
    loaded_model: Optional[OllamaLoadedModel] = None
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if self.state == ModelState.WARM:
            raise ValueError(
                "ModelState.WARM is not supported for Ollama models: "
                "Ollama does not expose verifiable CPU-pinned model memory."
            )

    @property
    def is_hot(self) -> bool:
        return self.state == ModelState.HOT

    @property
    def is_cold(self) -> bool:
        return self.state == ModelState.COLD

    @property
    def is_unknown(self) -> bool:
        return self.state == ModelState.UNKNOWN


@dataclass(frozen=True)
class OllamaUnloadResult:
    """Structured result of an explicit model unload operation."""

    model_name: str
    success: bool
    verified_unloaded: bool
    elapsed_ms: float
    attempts: int
    final_state: ModelState
    error: Optional[str] = None
    details: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Model Name Normalization Helper
# ---------------------------------------------------------------------------


def matches_model_name(candidate: str, target: str) -> bool:
    """Compare candidate model name from Ollama with target name.

    Performs case-insensitive matching and handles implicit ':latest' tag
    normalization. Strictly prohibits prefix-only matching (e.g. 'qwen:4b'
    will never match 'qwen:8b').
    """
    c = candidate.strip().lower()
    t = target.strip().lower()
    if c == t:
        return True
    if not t.endswith(":latest") and c == f"{t}:latest":
        return True
    if not c.endswith(":latest") and t == f"{c}:latest":
        return True
    return False


# ---------------------------------------------------------------------------
# Ollama Model Adapter
# ---------------------------------------------------------------------------


class OllamaModelAdapter:
    """Model adapter providing hardware-aware lifecycle operations for Ollama.

    Caller Coordination & Concurrency Contract (F-04):
    - The adapter DOES NOT acquire or release GPU scheduler leases.
    - Callers (such as higher-level orchestrators) MUST ensure that no active workload is
      using the target model before requesting model unloading.
    - Batch 3 will introduce integrated GPU scheduler lease coordination.
    - Model inspection methods (list_loaded_models, get_model_residency, is_model_loaded)
      are strictly read-only and non-mutating.
    - Unload operations are safely serialized per-model across both synchronous threads
      and asynchronous coroutines (F-05).
    """

    def __init__(
        self,
        host: Optional[str] = None,
        default_model: Optional[str] = None,
        connect_timeout_s: Optional[float] = None,
        request_timeout_s: float = 10.0,
        unload_timeout_s: float = 5.0,
        poll_interval_s: float = 0.2,
        client: Optional[httpx.AsyncClient] = None,
        sync_client: Optional[httpx.Client] = None,
        registry: Optional[ModelRegistry] = None,
        lifecycle_manager: Optional[OllamaLifecycleManager] = None,
    ) -> None:
        settings = get_settings()
        self.host = (host or settings.reasoning_host).rstrip("/")
        self.default_model = default_model or settings.reasoning_model
        self.connect_timeout_s = (
            connect_timeout_s
            if connect_timeout_s is not None
            else settings.reasoning_connect_timeout_s
        )
        self.request_timeout_s = request_timeout_s
        self.unload_timeout_s = unload_timeout_s
        self.poll_interval_s = poll_interval_s

        self._registry = registry
        self._injected_async_client = client
        self._injected_sync_client = sync_client
        self._owned_async_client: Optional[httpx.AsyncClient] = None
        self._owned_sync_client: Optional[httpx.Client] = None

        # Mutual exclusion for unload operations (F-05)
        # Shared lock + condition variable coordinates sync threads and async tasks
        self._unload_lock = threading.Lock()
        self._unload_cv = threading.Condition(self._unload_lock)
        self._unloading_models: set[str] = set()

        # Reuse existing OllamaLifecycleManager for tag inspection and warmup
        if lifecycle_manager is not None:
            self._lifecycle_manager = lifecycle_manager
        else:
            self._lifecycle_manager = OllamaLifecycleManager(
                host=self.host,
                model=self.default_model,
                client=self._injected_sync_client,
            )

    # -----------------------------------------------------------------------
    # Unload Mutual Exclusion Coordination (F-05)
    # -----------------------------------------------------------------------

    @staticmethod
    def _normalize_lock_name(model_name: str) -> str:
        """Normalize model name to canonical key for per-model locking."""
        name = model_name.strip().lower()
        if name.endswith(":latest"):
            name = name[:-7]
        return name

    def _acquire_unload_sync(self, model_name: str, timeout_s: float) -> bool:
        """Acquire unload mutual exclusion for model_name synchronously.

        Blocks waiting threads on a threading.Condition variable until the target model
        is free or timeout_s expires. Concurrent unloads of different models do not block.
        """
        canonical = self._normalize_lock_name(model_name)
        deadline = time.monotonic() + timeout_s
        with self._unload_cv:
            while canonical in self._unloading_models:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._unload_cv.wait(timeout=remaining)
            self._unloading_models.add(canonical)
            return True

    def _release_unload_sync(self, model_name: str) -> None:
        """Release unload mutual exclusion for model_name synchronously."""
        canonical = self._normalize_lock_name(model_name)
        with self._unload_cv:
            self._unloading_models.discard(canonical)
            self._unload_cv.notify_all()

    async def _acquire_unload_async(self, model_name: str, timeout_s: float) -> bool:
        """Acquire unload mutual exclusion for model_name asynchronously.

        Yields to event loop via asyncio.sleep without blocking synchronous threads
        or the event loop. Concurrent unloads of different models do not block.
        """
        canonical = self._normalize_lock_name(model_name)
        deadline = time.monotonic() + timeout_s
        while True:
            with self._unload_cv:
                if canonical not in self._unloading_models:
                    self._unloading_models.add(canonical)
                    return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(0.02, remaining))

    def _release_unload_async(self, model_name: str) -> None:
        """Release unload mutual exclusion for model_name asynchronously."""
        self._release_unload_sync(model_name)

    # -----------------------------------------------------------------------
    # Client Lifecycle
    # -----------------------------------------------------------------------

    def _get_sync_client(self) -> httpx.Client:
        if self._injected_sync_client is not None:
            return self._injected_sync_client
        if self._owned_sync_client is None or self._owned_sync_client.is_closed:
            timeout = httpx.Timeout(self.request_timeout_s, connect=self.connect_timeout_s)
            self._owned_sync_client = httpx.Client(timeout=timeout)
        return self._owned_sync_client

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._injected_async_client is not None:
            return self._injected_async_client
        if self._owned_async_client is None or self._owned_async_client.is_closed:
            timeout = httpx.Timeout(self.request_timeout_s, connect=self.connect_timeout_s)
            self._owned_async_client = httpx.AsyncClient(timeout=timeout)
        return self._owned_async_client

    def close(self) -> None:
        """Close synchronously owned HTTP client if open."""
        if self._owned_sync_client is not None and not self._owned_sync_client.is_closed:
            self._owned_sync_client.close()

    async def aclose(self) -> None:
        """Close asynchronously owned HTTP client if open."""
        if self._owned_async_client is not None and not self._owned_async_client.is_closed:
            await self._owned_async_client.aclose()
        self.close()

    def __enter__(self) -> "OllamaModelAdapter":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    async def __aenter__(self) -> "OllamaModelAdapter":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    # -----------------------------------------------------------------------
    # Response Parsing & Normalization
    # -----------------------------------------------------------------------

    def _parse_ps_response(self, response_data: Any) -> List[OllamaLoadedModel]:
        """Parse raw response from Ollama /api/ps into normalized OllamaLoadedModel items."""
        if not isinstance(response_data, dict):
            raise OllamaResponseError(
                f"Expected JSON object from Ollama /api/ps, got {type(response_data).__name__}"
            )
        if "error" in response_data:
            raise OllamaResponseError(f"Ollama returned error: {response_data['error']}")

        models_raw = response_data.get("models")
        if models_raw is None:
            raise OllamaResponseError("Missing 'models' key in Ollama /api/ps response")
        if not isinstance(models_raw, list):
            raise OllamaResponseError(
                f"Expected 'models' to be a list, got {type(models_raw).__name__}"
            )

        loaded_models: List[OllamaLoadedModel] = []
        for idx, item in enumerate(models_raw):
            if not isinstance(item, dict):
                raise OllamaResponseError(
                    f"Model entry at index {idx} in /api/ps is not an object: {type(item).__name__}"
                )
            name = str(item.get("name") or item.get("model") or "").strip()
            model_id = str(item.get("model") or item.get("name") or "").strip()
            if not name and not model_id:
                raise OllamaResponseError(
                    f"Model entry at index {idx} in /api/ps missing both 'name' and 'model'"
                )

            # Extract fields without fabricating missing information
            size_raw = item.get("size")
            size_bytes: Optional[int] = None
            if size_raw is not None and isinstance(size_raw, int) and not isinstance(size_raw, bool):
                size_bytes = size_raw

            size_vram_raw = item.get("size_vram")
            size_vram_bytes: Optional[int] = None
            if (
                size_vram_raw is not None
                and isinstance(size_vram_raw, int)
                and not isinstance(size_vram_raw, bool)
            ):
                size_vram_bytes = size_vram_raw

            expires_at = item.get("expires_at")
            if expires_at is not None and not isinstance(expires_at, str):
                expires_at = None

            digest = item.get("digest")
            if digest is not None and not isinstance(digest, str):
                digest = None

            details = item.get("details")
            if details is not None and not isinstance(details, dict):
                details = None

            loaded_models.append(
                OllamaLoadedModel(
                    name=name,
                    model=model_id,
                    size_bytes=size_bytes,
                    size_vram_bytes=size_vram_bytes,
                    expires_at=expires_at,
                    digest=digest,
                    details=details,
                )
            )

        return loaded_models

    def _classify_residency(
        self,
        target: str,
        loaded_model: Optional[OllamaLoadedModel],
    ) -> tuple[ModelState, bool, Optional[str]]:
        """Classify residency state for a model based on /api/ps evidence (F-01).

        Classification Rules:
        - Model absent from successful /api/ps response: COLD (is_loaded=False).
        - size_vram_bytes > 0: HOT (is_loaded=True, confirmed resident in GPU VRAM).
        - size_vram_bytes == 0: UNKNOWN (is_loaded=True, reported in /api/ps with 0 VRAM;
          no GPU residency proven; does not claim CPU residency).
        - size_vram_bytes is None: UNKNOWN (is_loaded=True, missing or unparseable VRAM telemetry).
        - size_vram_bytes < 0: UNKNOWN (is_loaded=True, invalid negative VRAM telemetry).
        - Ollama WARM remains strictly prohibited.
        """
        if loaded_model is None:
            return ModelState.COLD, False, None

        vram = loaded_model.size_vram_bytes
        if vram is None:
            return (
                ModelState.UNKNOWN,
                True,
                "Missing or unparseable size_vram in Ollama /api/ps response; GPU residency is UNKNOWN.",
            )
        if vram < 0:
            return (
                ModelState.UNKNOWN,
                True,
                f"Invalid negative size_vram ({vram}) in Ollama /api/ps response; GPU residency is UNKNOWN.",
            )
        if vram == 0:
            return (
                ModelState.UNKNOWN,
                True,
                "Model reported in Ollama /api/ps with size_vram=0; GPU residency is UNKNOWN.",
            )
        # vram > 0
        return ModelState.HOT, True, None

    def _sync_registry_state(
        self,
        model_name: str,
        state: ModelState,
        observation_timestamp: Optional[float] = None,
    ) -> None:
        """Propagate state change to ModelRegistry with observation timestamp fencing (F-02)."""
        if self._registry is None:
            return
        try:
            if self._registry.is_registered(model_name):
                self._registry.update_state(
                    model_name,
                    state,
                    observation_timestamp=observation_timestamp,
                )
        except Exception as exc:
            logger.warning(
                "Failed to update registry state for '%s' to %s: %s",
                model_name,
                state.value,
                exc,
            )

    # -----------------------------------------------------------------------
    # Model Inspection (Synchronous & Asynchronous - Strictly Read-Only)
    # -----------------------------------------------------------------------

    def list_loaded_models(
        self,
        *,
        timeout_s: Optional[float] = None,
    ) -> List[OllamaLoadedModel]:
        """Query Ollama /api/ps and return all currently resident models (read-only).

        Inspection is strictly read-only and non-mutating: does not acquire scheduler leases
        or alter daemon residency. Accepts an optional timeout_s bounding this query (F-03).
        """
        url = f"{self.host}{_PS_ENDPOINT}"
        client = self._get_sync_client()
        effective_timeout = (
            timeout_s if timeout_s is not None else self.request_timeout_s
        )
        try:
            resp = client.get(url, timeout=effective_timeout)
            if resp.status_code != 200:
                raise OllamaResponseError(
                    f"Ollama /api/ps returned HTTP {resp.status_code}",
                    status_code=resp.status_code,
                    response_text=resp.text[:500],
                )
            return self._parse_ps_response(resp.json())
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Failed to connect to Ollama at {self.host}: {exc}", host=self.host
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Ollama /api/ps timed out after {effective_timeout}s: {exc}",
                timeout_s=effective_timeout,
            ) from exc
        except (ValueError, KeyError) as exc:
            raise OllamaResponseError(f"Malformed JSON from Ollama /api/ps: {exc}") from exc

    async def list_loaded_models_async(
        self,
        *,
        timeout_s: Optional[float] = None,
    ) -> List[OllamaLoadedModel]:
        """Asynchronously query Ollama /api/ps and return resident models (read-only).

        Inspection is strictly read-only and non-mutating: does not acquire scheduler leases
        or alter daemon residency. Accepts an optional timeout_s bounding this query (F-03).
        """
        url = f"{self.host}{_PS_ENDPOINT}"
        client = self._get_async_client()
        effective_timeout = (
            timeout_s if timeout_s is not None else self.request_timeout_s
        )
        try:
            resp = await client.get(url, timeout=effective_timeout)
            if resp.status_code != 200:
                raise OllamaResponseError(
                    f"Ollama /api/ps returned HTTP {resp.status_code}",
                    status_code=resp.status_code,
                    response_text=resp.text[:500],
                )
            return self._parse_ps_response(resp.json())
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Failed to connect to Ollama at {self.host}: {exc}", host=self.host
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Ollama /api/ps timed out after {effective_timeout}s: {exc}",
                timeout_s=effective_timeout,
            ) from exc
        except (ValueError, KeyError) as exc:
            raise OllamaResponseError(f"Malformed JSON from Ollama /api/ps: {exc}") from exc

    def get_model_residency(
        self,
        model_name: Optional[str] = None,
        *,
        raise_on_error: bool = False,
    ) -> OllamaModelResidency:
        """Inspect Ollama /api/ps and return normalized residency state for target model.

        Inspection is strictly read-only and non-mutating: does not acquire scheduler leases
        or alter daemon residency (F-04).

        Returns:
            OllamaModelResidency with state:
            - HOT: Model confirmed resident in GPU VRAM (size_vram_bytes > 0).
            - COLD: Ollama responded normally and model is absent from /api/ps.
            - UNKNOWN: Network error, timeout, or model resident with size_vram == 0 or
              missing/invalid VRAM telemetry (F-01).
        """
        target = model_name or self.default_model
        obs_time = time.time()
        try:
            loaded_models = self.list_loaded_models()
        except OllamaAdapterError as exc:
            if raise_on_error:
                raise
            logger.warning("Failed to inspect Ollama residency for '%s': %s", target, exc)
            return OllamaModelResidency(
                model_name=target,
                state=ModelState.UNKNOWN,
                is_loaded=False,
                error=str(exc),
            )

        for m in loaded_models:
            if matches_model_name(m.name, target) or matches_model_name(m.model, target):
                state, is_loaded, err = self._classify_residency(target, m)
                self._sync_registry_state(target, state, observation_timestamp=obs_time)
                return OllamaModelResidency(
                    model_name=target,
                    state=state,
                    is_loaded=is_loaded,
                    size_vram_bytes=m.size_vram_bytes,
                    size_bytes=m.size_bytes,
                    expires_at=m.expires_at,
                    loaded_model=m,
                    error=err,
                )

        state, is_loaded, err = self._classify_residency(target, None)
        self._sync_registry_state(target, state, observation_timestamp=obs_time)
        return OllamaModelResidency(
            model_name=target,
            state=state,
            is_loaded=is_loaded,
            error=err,
        )

    async def get_model_residency_async(
        self,
        model_name: Optional[str] = None,
        *,
        raise_on_error: bool = False,
    ) -> OllamaModelResidency:
        """Asynchronously inspect Ollama /api/ps and return normalized residency state.

        Inspection is strictly read-only and non-mutating: does not acquire scheduler leases
        or alter daemon residency (F-04).
        """
        target = model_name or self.default_model
        obs_time = time.time()
        try:
            loaded_models = await self.list_loaded_models_async()
        except OllamaAdapterError as exc:
            if raise_on_error:
                raise
            logger.warning("Failed to inspect Ollama residency for '%s': %s", target, exc)
            return OllamaModelResidency(
                model_name=target,
                state=ModelState.UNKNOWN,
                is_loaded=False,
                error=str(exc),
            )

        for m in loaded_models:
            if matches_model_name(m.name, target) or matches_model_name(m.model, target):
                state, is_loaded, err = self._classify_residency(target, m)
                self._sync_registry_state(target, state, observation_timestamp=obs_time)
                return OllamaModelResidency(
                    model_name=target,
                    state=state,
                    is_loaded=is_loaded,
                    size_vram_bytes=m.size_vram_bytes,
                    size_bytes=m.size_bytes,
                    expires_at=m.expires_at,
                    loaded_model=m,
                    error=err,
                )

        state, is_loaded, err = self._classify_residency(target, None)
        self._sync_registry_state(target, state, observation_timestamp=obs_time)
        return OllamaModelResidency(
            model_name=target,
            state=state,
            is_loaded=is_loaded,
            error=err,
        )

    def is_model_loaded(
        self,
        model_name: Optional[str] = None,
        *,
        raise_on_error: bool = False,
    ) -> bool:
        """Return True if target model is confirmed HOT in Ollama."""
        residency = self.get_model_residency(model_name, raise_on_error=raise_on_error)
        if residency.state == ModelState.UNKNOWN and raise_on_error:
            raise OllamaAdapterError(
                f"Cannot determine if '{model_name or self.default_model}' is loaded: {residency.error}"
            )
        return residency.is_hot

    async def is_model_loaded_async(
        self,
        model_name: Optional[str] = None,
        *,
        raise_on_error: bool = False,
    ) -> bool:
        """Asynchronously return True if target model is confirmed HOT in Ollama."""
        residency = await self.get_model_residency_async(model_name, raise_on_error=raise_on_error)
        if residency.state == ModelState.UNKNOWN and raise_on_error:
            raise OllamaAdapterError(
                f"Cannot determine if '{model_name or self.default_model}' is loaded: {residency.error}"
            )
        return residency.is_hot

    # -----------------------------------------------------------------------
    # Explicit Model Unloading & Eviction (Verified via /api/ps)
    # -----------------------------------------------------------------------

    def unload_model(
        self,
        model_name: Optional[str] = None,
        *,
        verification_timeout_s: Optional[float] = None,
        poll_interval_s: Optional[float] = None,
        raise_on_error: bool = True,
    ) -> OllamaUnloadResult:
        """Explicitly request model unloading from Ollama and verify via /api/ps.

        Uses Ollama's documented eviction API:
            POST /api/generate with {"model": target, "keep_alive": 0, "stream": False}

        Caller Coordination & Scheduler Contract (F-04):
        - The adapter DOES NOT acquire or release GPU scheduler leases.
        - Callers (such as higher-level orchestrators) MUST ensure that no active workload is
          using the target model before requesting model unloading.
        - Phase 2 Batch 3 will introduce integrated GPU scheduler lease coordination.

        Invariants:
        - Never assumes HTTP 200 proves VRAM release.
        - Actively polls /api/ps until the model is confirmed absent.
        - Never reports success without positive confirmation.
        - Repeated calls on already unloaded models succeed safely (COLD).
        - Monotonic deadline bounds total duration and individual request timeouts (F-03).
        - Safely serialized per-model against concurrent unloads (F-05).
        """
        target = model_name or self.default_model
        timeout_s = (
            verification_timeout_s
            if verification_timeout_s is not None
            else self.unload_timeout_s
        )
        poll_interval = (
            poll_interval_s if poll_interval_s is not None else self.poll_interval_s
        )

        t0 = time.monotonic()
        deadline = t0 + timeout_s

        # Acquire per-model unload mutual exclusion (F-05)
        rem_lock = max(0.001, deadline - time.monotonic())
        if not self._acquire_unload_sync(target, rem_lock):
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
            err = OllamaUnloadTimeoutError(target, timeout_s)
            logger.warning(
                "Timed out waiting for concurrent unload lock on model '%s' after %.2f ms.",
                target,
                elapsed_ms,
            )
            if raise_on_error:
                raise err
            return OllamaUnloadResult(
                model_name=target,
                success=False,
                verified_unloaded=False,
                elapsed_ms=elapsed_ms,
                attempts=0,
                final_state=ModelState.UNKNOWN,
                error=str(err),
            )

        try:
            url = f"{self.host}{_GENERATE_ENDPOINT}"
            payload = {"model": target, "keep_alive": 0, "stream": False}
            client = self._get_sync_client()

            logger.info("Requesting model unload for '%s' from Ollama...", target)

            rem_post = deadline - time.monotonic()
            if rem_post <= 0:
                elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
                err = OllamaUnloadTimeoutError(target, timeout_s)
                if raise_on_error:
                    raise err
                return OllamaUnloadResult(
                    model_name=target,
                    success=False,
                    verified_unloaded=False,
                    elapsed_ms=elapsed_ms,
                    attempts=0,
                    final_state=ModelState.UNKNOWN,
                    error=str(err),
                )

            post_timeout = min(self.request_timeout_s, max(0.001, rem_post))

            try:
                resp = client.post(url, json=payload, timeout=post_timeout)
                if resp.status_code == 404:
                    raise OllamaModelNotFoundError(target)
                if resp.status_code != 200:
                    raise OllamaResponseError(
                        f"Ollama /api/generate unload returned HTTP {resp.status_code}",
                        status_code=resp.status_code,
                        response_text=resp.text[:500],
                    )
            except httpx.ConnectError as exc:
                err = OllamaConnectionError(
                    f"Failed to connect to Ollama during unload of '{target}': {exc}",
                    host=self.host,
                )
                if raise_on_error:
                    raise err from exc
                return OllamaUnloadResult(
                    model_name=target,
                    success=False,
                    verified_unloaded=False,
                    elapsed_ms=round((time.monotonic() - t0) * 1000, 2),
                    attempts=1,
                    final_state=ModelState.UNKNOWN,
                    error=str(err),
                )
            except httpx.TimeoutException as exc:
                err = OllamaTimeoutError(
                    f"Ollama unload request for '{target}' timed out: {exc}",
                    timeout_s=post_timeout,
                )
                if raise_on_error:
                    raise err from exc
                return OllamaUnloadResult(
                    model_name=target,
                    success=False,
                    verified_unloaded=False,
                    elapsed_ms=round((time.monotonic() - t0) * 1000, 2),
                    attempts=1,
                    final_state=ModelState.UNKNOWN,
                    error=str(err),
                )
            except OllamaAdapterError as exc:
                if raise_on_error:
                    raise
                return OllamaUnloadResult(
                    model_name=target,
                    success=False,
                    verified_unloaded=False,
                    elapsed_ms=round((time.monotonic() - t0) * 1000, 2),
                    attempts=1,
                    final_state=ModelState.UNKNOWN,
                    error=str(exc),
                )

            # Verification Loop: Poll /api/ps until model is gone (F-03)
            attempts = 1
            last_error: Optional[str] = None

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break

                sleep_time = min(poll_interval, remaining)
                time.sleep(sleep_time)

                remaining_after_sleep = deadline - time.monotonic()
                if remaining_after_sleep <= 0:
                    break

                attempts += 1
                poll_timeout = min(self.request_timeout_s, max(0.001, remaining_after_sleep))
                try:
                    loaded = self.list_loaded_models(timeout_s=poll_timeout)
                    model_still_present = any(
                        matches_model_name(m.name, target) or matches_model_name(m.model, target)
                        for m in loaded
                    )
                    if not model_still_present:
                        elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
                        logger.info(
                            "Model '%s' verified unloaded from Ollama in %s ms (%d attempts).",
                            target,
                            elapsed_ms,
                            attempts,
                        )
                        self._sync_registry_state(
                            target,
                            ModelState.COLD,
                            observation_timestamp=time.time(),
                        )
                        return OllamaUnloadResult(
                            model_name=target,
                            success=True,
                            verified_unloaded=True,
                            elapsed_ms=elapsed_ms,
                            attempts=attempts,
                            final_state=ModelState.COLD,
                        )
                except OllamaAdapterError as exc:
                    last_error = str(exc)
                    logger.debug("Transient error polling /api/ps during unload verification: %s", exc)

            # Timeout reached without confirmation
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
            if last_error:
                msg = (
                    f"Residency of '{target}' could not be verified after unload due to "
                    f"inspection errors ({last_error}) after {elapsed_ms} ms."
                )
                err = OllamaUnloadError(msg, model_name=target)
                final_state = ModelState.UNKNOWN
            else:
                err = OllamaUnloadTimeoutError(target, timeout_s)
                final_state = ModelState.HOT

            if raise_on_error:
                raise err

            logger.warning(
                "Unload verification failed for '%s': %s (final_state=%s)",
                target,
                err,
                final_state.value,
            )
            return OllamaUnloadResult(
                model_name=target,
                success=False,
                verified_unloaded=False,
                elapsed_ms=elapsed_ms,
                attempts=attempts,
                final_state=final_state,
                error=str(err),
            )
        finally:
            self._release_unload_sync(target)

    async def unload_model_async(
        self,
        model_name: Optional[str] = None,
        *,
        verification_timeout_s: Optional[float] = None,
        poll_interval_s: Optional[float] = None,
        raise_on_error: bool = True,
    ) -> OllamaUnloadResult:
        """Asynchronously request model unloading from Ollama and verify via /api/ps.

        Caller Coordination & Scheduler Contract (F-04):
        - The adapter DOES NOT acquire or release GPU scheduler leases.
        - Callers (such as higher-level orchestrators) MUST ensure that no active workload is
          using the target model before requesting model unloading.
        - Phase 2 Batch 3 will introduce integrated GPU scheduler lease coordination.

        Invariants:
        - Never assumes HTTP 200 proves VRAM release.
        - Actively polls /api/ps until the model is confirmed absent.
        - Never reports success without positive confirmation.
        - Repeated calls on already unloaded models succeed safely (COLD).
        - Monotonic deadline bounds total duration and individual request timeouts (F-03).
        - Safely serialized per-model against concurrent unloads (F-05).
        """
        target = model_name or self.default_model
        timeout_s = (
            verification_timeout_s
            if verification_timeout_s is not None
            else self.unload_timeout_s
        )
        poll_interval = (
            poll_interval_s if poll_interval_s is not None else self.poll_interval_s
        )

        t0 = time.monotonic()
        deadline = t0 + timeout_s

        # Acquire per-model unload mutual exclusion (F-05)
        rem_lock = max(0.001, deadline - time.monotonic())
        if not await self._acquire_unload_async(target, rem_lock):
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
            err = OllamaUnloadTimeoutError(target, timeout_s)
            logger.warning(
                "Timed out waiting for concurrent async unload lock on model '%s' after %.2f ms.",
                target,
                elapsed_ms,
            )
            if raise_on_error:
                raise err
            return OllamaUnloadResult(
                model_name=target,
                success=False,
                verified_unloaded=False,
                elapsed_ms=elapsed_ms,
                attempts=0,
                final_state=ModelState.UNKNOWN,
                error=str(err),
            )

        try:
            url = f"{self.host}{_GENERATE_ENDPOINT}"
            payload = {"model": target, "keep_alive": 0, "stream": False}
            client = self._get_async_client()

            logger.info("Requesting async model unload for '%s' from Ollama...", target)

            rem_post = deadline - time.monotonic()
            if rem_post <= 0:
                elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
                err = OllamaUnloadTimeoutError(target, timeout_s)
                if raise_on_error:
                    raise err
                return OllamaUnloadResult(
                    model_name=target,
                    success=False,
                    verified_unloaded=False,
                    elapsed_ms=elapsed_ms,
                    attempts=0,
                    final_state=ModelState.UNKNOWN,
                    error=str(err),
                )

            post_timeout = min(self.request_timeout_s, max(0.001, rem_post))

            try:
                resp = await client.post(url, json=payload, timeout=post_timeout)
                if resp.status_code == 404:
                    raise OllamaModelNotFoundError(target)
                if resp.status_code != 200:
                    raise OllamaResponseError(
                        f"Ollama /api/generate unload returned HTTP {resp.status_code}",
                        status_code=resp.status_code,
                        response_text=resp.text[:500],
                    )
            except httpx.ConnectError as exc:
                err = OllamaConnectionError(
                    f"Failed to connect to Ollama during async unload of '{target}': {exc}",
                    host=self.host,
                )
                if raise_on_error:
                    raise err from exc
                return OllamaUnloadResult(
                    model_name=target,
                    success=False,
                    verified_unloaded=False,
                    elapsed_ms=round((time.monotonic() - t0) * 1000, 2),
                    attempts=1,
                    final_state=ModelState.UNKNOWN,
                    error=str(err),
                )
            except httpx.TimeoutException as exc:
                err = OllamaTimeoutError(
                    f"Ollama async unload request for '{target}' timed out: {exc}",
                    timeout_s=post_timeout,
                )
                if raise_on_error:
                    raise err from exc
                return OllamaUnloadResult(
                    model_name=target,
                    success=False,
                    verified_unloaded=False,
                    elapsed_ms=round((time.monotonic() - t0) * 1000, 2),
                    attempts=1,
                    final_state=ModelState.UNKNOWN,
                    error=str(err),
                )
            except OllamaAdapterError as exc:
                if raise_on_error:
                    raise
                return OllamaUnloadResult(
                    model_name=target,
                    success=False,
                    verified_unloaded=False,
                    elapsed_ms=round((time.monotonic() - t0) * 1000, 2),
                    attempts=1,
                    final_state=ModelState.UNKNOWN,
                    error=str(exc),
                )

            # Verification Loop: Poll /api/ps until model is gone (F-03)
            attempts = 1
            last_error: Optional[str] = None

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break

                sleep_time = min(poll_interval, remaining)
                await asyncio.sleep(sleep_time)

                remaining_after_sleep = deadline - time.monotonic()
                if remaining_after_sleep <= 0:
                    break

                attempts += 1
                poll_timeout = min(self.request_timeout_s, max(0.001, remaining_after_sleep))
                try:
                    loaded = await self.list_loaded_models_async(timeout_s=poll_timeout)
                    model_still_present = any(
                        matches_model_name(m.name, target) or matches_model_name(m.model, target)
                        for m in loaded
                    )
                    if not model_still_present:
                        elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
                        logger.info(
                            "Model '%s' verified unloaded asynchronously in %s ms (%d attempts).",
                            target,
                            elapsed_ms,
                            attempts,
                        )
                        self._sync_registry_state(
                            target,
                            ModelState.COLD,
                            observation_timestamp=time.time(),
                        )
                        return OllamaUnloadResult(
                            model_name=target,
                            success=True,
                            verified_unloaded=True,
                            elapsed_ms=elapsed_ms,
                            attempts=attempts,
                            final_state=ModelState.COLD,
                        )
                except OllamaAdapterError as exc:
                    last_error = str(exc)
                    logger.debug(
                        "Transient error during async unload verification polling: %s", exc
                    )

            # Timeout reached without confirmation
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
            if last_error:
                msg = (
                    f"Residency of '{target}' could not be verified after async unload due to "
                    f"inspection errors ({last_error}) after {elapsed_ms} ms."
                )
                err = OllamaUnloadError(msg, model_name=target)
                final_state = ModelState.UNKNOWN
            else:
                err = OllamaUnloadTimeoutError(target, timeout_s)
                final_state = ModelState.HOT

            if raise_on_error:
                raise err

            logger.warning(
                "Async unload verification failed for '%s': %s (final_state=%s)",
                target,
                err,
                final_state.value,
            )
            return OllamaUnloadResult(
                model_name=target,
                success=False,
                verified_unloaded=False,
                elapsed_ms=elapsed_ms,
                attempts=attempts,
                final_state=final_state,
                error=str(err),
            )
        except asyncio.CancelledError:
            elapsed_ms = round((time.monotonic() - t0) * 1000, 2)
            logger.warning(
                "Async unload of '%s' was cancelled after %.2f ms.",
                target,
                elapsed_ms,
            )
            raise
        finally:
            self._release_unload_async(target)

    # -----------------------------------------------------------------------
    # Reused Lifecycle Operations (Delegating to OllamaLifecycleManager)
    # -----------------------------------------------------------------------

    def check_installed(
        self,
        model_name: Optional[str] = None,
        timeout_s: float = 3.0,
    ) -> ModelStatus:
        """Check whether target model is installed on disk in Ollama library.

        Reuses existing OllamaLifecycleManager.check_availability() to probe
        /api/tags without duplicating inspection code.
        """
        target = model_name or self.default_model
        if target != self._lifecycle_manager.model:
            mgr = OllamaLifecycleManager(
                host=self.host,
                model=target,
                client=self._get_sync_client(),
            )
            return mgr.check_availability(timeout_s=timeout_s)
        return self._lifecycle_manager.check_availability(timeout_s=timeout_s)

    def warmup(
        self,
        model_name: Optional[str] = None,
        timeout_s: float = 30.0,
    ) -> bool:
        """Trigger warmup request to pin target model in Ollama memory.

        Reuses existing OllamaLifecycleManager.warmup() without duplicating code.
        """
        target = model_name or self.default_model
        if target != self._lifecycle_manager.model:
            mgr = OllamaLifecycleManager(
                host=self.host,
                model=target,
                keep_alive=get_settings().reasoning_keep_alive,
                client=self._get_sync_client(),
            )
            return mgr.warmup(timeout_s=timeout_s)
        return self._lifecycle_manager.warmup(timeout_s=timeout_s)

