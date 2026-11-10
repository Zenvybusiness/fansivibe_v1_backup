"""AI Model Resource Manager (Phase 1, Phase 2 Batch 1 & Batch 2).

Provides centralized, observational monitoring of GPU VRAM, host system RAM,
NVMe storage, model registration, honest memory requirement tracking,
cross-process shared GPU scheduling arbitrated by kernel advisory file locking,
and model adapters for runtime inspection and explicit verified eviction.
"""

from app.ai.manager.adapters import (
    OllamaAdapterError,
    OllamaConnectionError,
    OllamaLoadedModel,
    OllamaModelAdapter,
    OllamaModelNotFoundError,
    OllamaModelResidency,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnloadError,
    OllamaUnloadResult,
    OllamaUnloadTimeoutError,
)
from app.ai.manager.memory_gpu import (
    DEFAULT_GPU_SAFETY_HEADROOM_BYTES,
    GPUMemoryMonitor,
)
from app.ai.manager.memory_system import (
    DEFAULT_RAM_SAFETY_HEADROOM_BYTES,
    SystemMemoryMonitor,
)
from app.ai.manager.registry import ModelRegistry
from app.ai.manager.scheduler import (
    DEFAULT_GRACE_PERIOD_S,
    DEFAULT_LEASE_TIMEOUT_S,
    DEFAULT_LOCKFILE_PATH,
    DEFAULT_MAX_QUEUE_DEPTH,
    DEFAULT_METADATA_PATH,
    DEFAULT_POLL_INTERVAL_S,
    DEFAULT_QUARANTINE_PATH,
    GPUResourceScheduler,
)
from app.ai.manager.storage import (
    DEFAULT_STORAGE_HEADROOM_BYTES,
    StorageManager,
)
from app.ai.manager.types import (
    DependencyUnavailableError,
    GPUMemorySnapshot,
    GPUSchedulerLease,
    GPUResourceQuarantinedError,
    HardwareMonitoringError,
    InsufficientRAMError,
    InsufficientVRAMError,
    InvalidStateTransitionError,
    LeaseState,
    ModelInfo,
    ModelManagerError,
    ModelNotFoundError,
    ModelProviderType,
    ModelState,
    SchedulerQueueFullError,
    SchedulerShutdownError,
    SchedulerTimeoutError,
    StorageSnapshot,
    SystemMemorySnapshot,
    WorkloadType,
    WorkloadUncertainError,
)

__all__ = [
    # Types & Enums
    "ModelState",
    "WorkloadType",
    "ModelProviderType",
    "ModelInfo",
    "LeaseState",
    "GPUSchedulerLease",
    "GPUMemorySnapshot",
    "SystemMemorySnapshot",
    "StorageSnapshot",
    # Adapter Types
    "OllamaLoadedModel",
    "OllamaModelResidency",
    "OllamaUnloadResult",
    # Exceptions
    "ModelManagerError",
    "InsufficientVRAMError",
    "InsufficientRAMError",
    "InvalidStateTransitionError",
    "ModelNotFoundError",
    "HardwareMonitoringError",
    "DependencyUnavailableError",
    "GPUResourceQuarantinedError",
    "SchedulerQueueFullError",
    "SchedulerTimeoutError",
    "SchedulerShutdownError",
    "WorkloadUncertainError",
    "OllamaAdapterError",
    "OllamaConnectionError",
    "OllamaTimeoutError",
    "OllamaResponseError",
    "OllamaModelNotFoundError",
    "OllamaUnloadError",
    "OllamaUnloadTimeoutError",
    # Registry & Monitors
    "ModelRegistry",
    "GPUMemoryMonitor",
    "SystemMemoryMonitor",
    "StorageManager",
    # Scheduler
    "GPUResourceScheduler",
    # Adapters
    "OllamaModelAdapter",
    # Constants
    "DEFAULT_GPU_SAFETY_HEADROOM_BYTES",
    "DEFAULT_RAM_SAFETY_HEADROOM_BYTES",
    "DEFAULT_STORAGE_HEADROOM_BYTES",
    "DEFAULT_LOCKFILE_PATH",
    "DEFAULT_METADATA_PATH",
    "DEFAULT_QUARANTINE_PATH",
    "DEFAULT_MAX_QUEUE_DEPTH",
    "DEFAULT_LEASE_TIMEOUT_S",
    "DEFAULT_POLL_INTERVAL_S",
    "DEFAULT_GRACE_PERIOD_S",
]
