"""Core lifecycle types, enums, value objects and exceptions for AI Model Management.

Phase 1 foundation: defines three memory states (COLD, WARM, HOT), workload classifications,
hardware measurement snapshots, and typed domain exceptions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional


class ModelState(str, Enum):
    """Residency state of an AI model in system memory hierarchy.

    COLD: Persistent model files exist on NVMe storage, but weights are not loaded in RAM or VRAM.
    WARM: Weights/components are resident in verified CPU host memory (RAM) and can be promoted
          to GPU without reading from disk.
    HOT:  Inference components are resident in GPU VRAM and ready for immediate execution.
    UNKNOWN: Initial or unprobed state.
    """

    COLD = "COLD"
    WARM = "WARM"
    HOT = "HOT"
    UNKNOWN = "UNKNOWN"


class WorkloadType(str, Enum):
    """Execution category of an AI workload."""

    REASONING_VISION = "REASONING_VISION"
    VTON_DIFFUSION = "VTON_DIFFUSION"


class ModelProviderType(str, Enum):
    """Engine or execution environment powering the model."""

    OLLAMA = "OLLAMA"
    PYTORCH = "PYTORCH"
    MOCK = "MOCK"


class LeaseState(str, Enum):
    """Lifecycle state of a GPU execution lease."""

    ACQUIRED = "ACQUIRED"
    RUNNING = "RUNNING"
    CANCELLING = "CANCELLING"
    RELEASED = "RELEASED"
    QUARANTINED = "QUARANTINED"


# ---------------------------------------------------------------------------
# Typed Exceptions
# ---------------------------------------------------------------------------


class ModelManagerError(Exception):
    """Base exception for all AI Model Resource Manager operations."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InsufficientVRAMError(ModelManagerError):
    """Raised when GPU VRAM is insufficient to promote a model or allocate buffers."""

    def __init__(
        self,
        required_bytes: int,
        available_bytes: int,
        model_id: str = "",
        details: Optional[str] = None,
    ) -> None:
        msg = (
            f"Insufficient VRAM for model '{model_id}': requires {required_bytes} bytes, "
            f"but only {available_bytes} bytes available."
        )
        if details:
            msg += f" Details: {details}"
        super().__init__(msg)
        self.required_bytes = required_bytes
        self.available_bytes = available_bytes
        self.model_id = model_id


class InsufficientRAMError(ModelManagerError):
    """Raised when host system RAM is insufficient to stage a model in WARM cache."""

    def __init__(
        self,
        required_bytes: int,
        available_bytes: int,
        model_id: str = "",
        details: Optional[str] = None,
    ) -> None:
        msg = (
            f"Insufficient host RAM for model '{model_id}': requires {required_bytes} bytes, "
            f"but only {available_bytes} bytes available."
        )
        if details:
            msg += f" Details: {details}"
        super().__init__(msg)
        self.required_bytes = required_bytes
        self.available_bytes = available_bytes
        self.model_id = model_id


class InvalidStateTransitionError(ModelManagerError):
    """Raised when an illegal or unsupported lifecycle state transition is requested."""

    def __init__(self, model_id: str, current_state: ModelState, target_state: ModelState) -> None:
        super().__init__(
            f"Invalid transition for model '{model_id}': cannot transition from "
            f"{current_state.value} to {target_state.value}."
        )
        self.model_id = model_id
        self.current_state = current_state
        self.target_state = target_state


class ModelNotFoundError(ModelManagerError):
    """Raised when a requested model ID is not registered in the ModelRegistry."""

    def __init__(self, model_id: str) -> None:
        super().__init__(f"Model '{model_id}' is not registered in ModelRegistry.")
        self.model_id = model_id


class HardwareMonitoringError(ModelManagerError):
    """Raised when querying GPU or system hardware metrics fails."""

    def __init__(self, subsystem: str, error: str) -> None:
        super().__init__(f"Failed to query {subsystem} hardware metrics: {error}")
        self.subsystem = subsystem
        self.error = error


class DependencyUnavailableError(ModelManagerError):
    """Raised when a required driver, tool, or library is missing from the environment."""

    def __init__(self, dependency: str, guidance: str = "") -> None:
        msg = f"Required dependency '{dependency}' is unavailable."
        if guidance:
            msg += f" {guidance}"
        super().__init__(msg)
        self.dependency = dependency


class GPUResourceQuarantinedError(ModelManagerError):
    """Raised when GPU lease acquisition is rejected because GPU is quarantined."""

    def __init__(
        self,
        message: str = "GPU is currently quarantined due to unresponsive or uncertain workload",
        evidence: Optional[dict[str, Any]] = None,
        retry_after_s: int = 15,
    ) -> None:
        super().__init__(message)
        self.evidence = evidence or {}
        self.retry_after_s = retry_after_s


class SchedulerQueueFullError(ModelManagerError):
    """Raised when in-process request queue exceeds maximum queue depth."""

    def __init__(
        self,
        message: str = "GPU scheduler queue is full",
        current_depth: int = 0,
        max_depth: int = 10,
        retry_after_s: int = 5,
    ) -> None:
        super().__init__(message)
        self.current_depth = current_depth
        self.max_depth = max_depth
        self.retry_after_s = retry_after_s


class SchedulerTimeoutError(ModelManagerError):
    """Raised when waiting for lease acquisition or execution exceeds timeout."""

    def __init__(self, message: str, phase: str = "acquisition", timeout_s: float = 0.0) -> None:
        super().__init__(message)
        self.phase = phase
        self.timeout_s = timeout_s


class SchedulerShutdownError(ModelManagerError):
    """Raised when acquiring a lease while scheduler is shutting down."""

    def __init__(self, message: str = "GPU scheduler is shutting down") -> None:
        super().__init__(message)


class WorkloadUncertainError(ModelManagerError):
    """Raised when workload termination cannot be verified after cancellation."""

    def __init__(self, message: str, lease_id: str = "") -> None:
        super().__init__(message)
        self.lease_id = lease_id


# ---------------------------------------------------------------------------
# Snapshots and Data Containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GPUMemorySnapshot:
    """Read-only measurement of physical GPU memory state."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    utilization_pct: Optional[float] = None
    device_name: Optional[str] = None
    driver_version: Optional[str] = None
    timestamp: float = 0.0

    @property
    def total_mib(self) -> float:
        return round(self.total_bytes / (1024 * 1024), 2)

    @property
    def used_mib(self) -> float:
        return round(self.used_bytes / (1024 * 1024), 2)

    @property
    def free_mib(self) -> float:
        return round(self.free_bytes / (1024 * 1024), 2)


@dataclass(frozen=True)
class SystemMemorySnapshot:
    """Read-only measurement of physical host RAM and swap state."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    available_bytes: int
    swap_total_bytes: int
    swap_used_bytes: int
    swap_free_bytes: int
    timestamp: float = 0.0

    @property
    def total_mib(self) -> float:
        return round(self.total_bytes / (1024 * 1024), 2)

    @property
    def used_mib(self) -> float:
        return round(self.used_bytes / (1024 * 1024), 2)

    @property
    def available_mib(self) -> float:
        return round(self.available_bytes / (1024 * 1024), 2)

    @property
    def swap_used_mib(self) -> float:
        return round(self.swap_used_bytes / (1024 * 1024), 2)

    @property
    def swap_free_mib(self) -> float:
        return round(self.swap_free_bytes / (1024 * 1024), 2)


@dataclass(frozen=True)
class StorageSnapshot:
    """Read-only measurement of storage capacity and free space."""

    total_bytes: int
    used_bytes: int
    free_bytes: int
    mount_point: str
    timestamp: float = 0.0

    @property
    def total_gib(self) -> float:
        return round(self.total_bytes / (1024 * 1024 * 1024), 2)

    @property
    def used_gib(self) -> float:
        return round(self.used_bytes / (1024 * 1024 * 1024), 2)

    @property
    def free_gib(self) -> float:
        return round(self.free_bytes / (1024 * 1024 * 1024), 2)


@dataclass
class ModelInfo:
    """Registration entry for an AI model in the ModelRegistry."""

    model_id: str
    family: str
    provider: ModelProviderType
    workload_type: WorkloadType
    current_state: ModelState = ModelState.COLD
    min_vram_bytes: Optional[int] = None
    min_ram_bytes: Optional[int] = None
    storage_path: Optional[str] = None
    is_verified: bool = False
    verification_notes: Optional[str] = None
    last_state_change: float = 0.0

    def __post_init__(self) -> None:
        if self.last_state_change == 0.0:
            self.last_state_change = time.time()


@dataclass
class GPUSchedulerLease:
    """Exclusive execution lease granting GPU access to a single workload."""

    lease_id: str
    model_id: str
    workload_type: WorkloadType
    priority: int
    holder_pid: int
    acquired_at: float
    timeout_s: float
    state: LeaseState = LeaseState.ACQUIRED
    _lock_fd: Optional[int] = None
    _abort_fn: Optional[Callable[[], Any]] = None
    _is_stopped_fn: Optional[Callable[[], Any]] = None
    _released_at: Optional[float] = None
    _quarantine_reason: Optional[str] = None
    _workload_completed: bool = False

    def mark_workload_completed(self) -> None:
        """Mark that the workload completed its execution cleanly."""
        self._workload_completed = True

    def register_abort_handler(self, fn: Callable[[], Any]) -> None:
        """Register a callback to signal abort to the underlying workload."""
        self._abort_fn = fn

    def register_termination_check(self, fn: Callable[[], Any]) -> None:
        """Register a verification check that returns True when workload stopped."""
        self._is_stopped_fn = fn

    def to_metadata(self) -> dict[str, Any]:
        """Convert lease details to diagnostic metadata."""
        return {
            "lease_id": self.lease_id,
            "holder_pid": self.holder_pid,
            "holder_worker": f"worker-{self.holder_pid}",
            "model_id": self.model_id,
            "workload_type": (
                self.workload_type.value
                if hasattr(self.workload_type, "value")
                else str(self.workload_type)
            ),
            "priority": self.priority,
            "acquired_at": self.acquired_at,
            "timeout_s": self.timeout_s,
            "state": self.state.value if hasattr(self.state, "value") else str(self.state),
        }


