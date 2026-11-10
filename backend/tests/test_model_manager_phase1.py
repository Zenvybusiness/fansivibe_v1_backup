"""Isolated Unit Tests for AI Model Resource Manager Phase 1 Components.

Tests:
- Core lifecycle types, enums, snapshots, and typed exceptions
- ModelRegistry registration, isolation, verification flags, and state updates
- GPUMemoryMonitor parsing, headroom calculation, and error handling
- SystemMemoryMonitor /proc/meminfo parsing, pressure detection, and headroom
- StorageManager disk capacity, path verification, and Ollama path detection
- Real hardware integration tests (read-only live probes)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from typing import NamedTuple

import pytest

from app.ai.manager.memory_gpu import (
    DEFAULT_GPU_SAFETY_HEADROOM_BYTES,
    GPUMemoryMonitor,
)
from app.ai.manager.memory_system import (
    DEFAULT_RAM_SAFETY_HEADROOM_BYTES,
    SystemMemoryMonitor,
)
from app.ai.manager.registry import ModelRegistry
from app.ai.manager.storage import (
    DEFAULT_STORAGE_HEADROOM_BYTES,
    StorageManager,
)
from app.ai.manager.types import (
    DependencyUnavailableError,
    GPUMemorySnapshot,
    HardwareMonitoringError,
    InsufficientRAMError,
    InsufficientVRAMError,
    InvalidStateTransitionError,
    ModelInfo,
    ModelManagerError,
    ModelNotFoundError,
    ModelProviderType,
    ModelState,
    StorageSnapshot,
    SystemMemorySnapshot,
    WorkloadType,
)

# ---------------------------------------------------------------------------
# 1. Types, Enums & Exceptions Tests
# ---------------------------------------------------------------------------


def test_model_state_enum_values():
    assert ModelState.COLD.value == "COLD"
    assert ModelState.WARM.value == "WARM"
    assert ModelState.HOT.value == "HOT"
    assert ModelState.UNKNOWN.value == "UNKNOWN"


def test_workload_and_provider_enums():
    assert WorkloadType.REASONING_VISION.value == "REASONING_VISION"
    assert WorkloadType.VTON_DIFFUSION.value == "VTON_DIFFUSION"
    assert ModelProviderType.OLLAMA.value == "OLLAMA"
    assert ModelProviderType.PYTORCH.value == "PYTORCH"
    assert ModelProviderType.MOCK.value == "MOCK"


def test_gpu_memory_snapshot_properties():
    snap = GPUMemorySnapshot(
        total_bytes=6 * 1024 * 1024 * 1024,
        used_bytes=1024 * 1024 * 1024,
        free_bytes=5 * 1024 * 1024 * 1024,
        utilization_pct=12.5,
        device_name="RTX 3050",
        driver_version="595.99",
        timestamp=100.0,
    )
    assert snap.total_mib == 6144.0
    assert snap.used_mib == 1024.0
    assert snap.free_mib == 5120.0
    assert snap.utilization_pct == 12.5
    assert snap.device_name == "RTX 3050"


def test_system_memory_snapshot_properties():
    snap = SystemMemorySnapshot(
        total_bytes=16 * 1024 * 1024 * 1024,
        used_bytes=8 * 1024 * 1024 * 1024,
        free_bytes=2 * 1024 * 1024 * 1024,
        available_bytes=6 * 1024 * 1024 * 1024,
        swap_total_bytes=2 * 1024 * 1024 * 1024,
        swap_used_bytes=1024 * 1024 * 1024,
        swap_free_bytes=1024 * 1024 * 1024,
        timestamp=100.0,
    )
    assert snap.total_mib == 16384.0
    assert snap.available_mib == 6144.0
    assert snap.swap_used_mib == 1024.0
    assert snap.swap_free_mib == 1024.0


def test_storage_snapshot_properties():
    snap = StorageSnapshot(
        total_bytes=500 * 1024 * 1024 * 1024,
        used_bytes=100 * 1024 * 1024 * 1024,
        free_bytes=400 * 1024 * 1024 * 1024,
        mount_point="/",
        timestamp=100.0,
    )
    assert snap.total_gib == 500.0
    assert snap.used_gib == 100.0
    assert snap.free_gib == 400.0


def test_typed_exceptions():
    err_vram = InsufficientVRAMError(
        required_bytes=4000,
        available_bytes=2000,
        model_id="test-model",
        details="Headroom depleted",
    )
    assert isinstance(err_vram, ModelManagerError)
    assert "test-model" in str(err_vram)
    assert err_vram.required_bytes == 4000
    assert err_vram.available_bytes == 2000

    err_ram = InsufficientRAMError(
        required_bytes=5000,
        available_bytes=1000,
        model_id="test-ram",
    )
    assert isinstance(err_ram, ModelManagerError)
    assert "test-ram" in str(err_ram)

    err_trans = InvalidStateTransitionError("m1", ModelState.COLD, ModelState.HOT)
    assert isinstance(err_trans, ModelManagerError)
    assert err_trans.current_state == ModelState.COLD
    assert err_trans.target_state == ModelState.HOT

    err_not_found = ModelNotFoundError("missing-id")
    assert "missing-id" in str(err_not_found)

    err_hw = HardwareMonitoringError("GPU", "Driver timeout")
    assert err_hw.subsystem == "GPU"
    assert "Driver timeout" in str(err_hw)

    err_dep = DependencyUnavailableError("torch", "Run pip install")
    assert err_dep.dependency == "torch"
    assert "Run pip install" in str(err_dep)


# ---------------------------------------------------------------------------
# 2. ModelRegistry Tests
# ---------------------------------------------------------------------------


def test_model_registry_canonical_defaults():
    registry = ModelRegistry()
    models = registry.list_models()
    ids = {m.model_id for m in models}

    assert "qwen3-vl:4b-instruct" in ids
    assert "fashn-vton-v1.5" in ids
    assert "mock-vton" in ids

    # Qwen verification
    qwen = registry.get("qwen3-vl:4b-instruct")
    assert qwen.is_verified is True
    assert qwen.min_vram_bytes is not None
    assert qwen.min_vram_bytes > 3_000_000_000
    assert qwen.provider == ModelProviderType.OLLAMA
    assert qwen.workload_type == WorkloadType.REASONING_VISION

    # Mandatory rule: FASHN must NOT have invented requirements!
    fashn = registry.get("fashn-vton-v1.5")
    assert fashn.is_verified is False
    assert fashn.min_vram_bytes is None
    assert fashn.min_ram_bytes is None
    assert "UNVERIFIED" in (fashn.verification_notes or "")
    assert fashn.provider == ModelProviderType.PYTORCH
    assert fashn.workload_type == WorkloadType.VTON_DIFFUSION

    # Mock tryon verification
    mock = registry.get("mock-vton")
    assert mock.is_verified is True
    assert mock.min_vram_bytes == 0
    assert mock.min_ram_bytes == 0


def test_model_registry_crud_and_isolation():
    registry = ModelRegistry(pre_register_defaults=False)
    assert len(registry.list_models()) == 0

    custom = ModelInfo(
        model_id="custom-model:v1",
        family="test",
        provider=ModelProviderType.MOCK,
        workload_type=WorkloadType.REASONING_VISION,
    )
    registry.register(custom)

    retrieved = registry.get("custom-model:v1")
    assert retrieved.model_id == "custom-model:v1"
    assert retrieved.current_state == ModelState.COLD

    # Verify deep copy isolation: modifying retrieved does not mutate internal registry
    retrieved.current_state = ModelState.HOT
    assert registry.get("custom-model:v1").current_state == ModelState.COLD

    # State update
    updated = registry.update_state("custom-model:v1", ModelState.HOT)
    assert updated.current_state == ModelState.HOT
    assert registry.get("custom-model:v1").current_state == ModelState.HOT

    # Requirement update
    req_updated = registry.update_memory_requirements(
        "custom-model:v1",
        min_vram_bytes=2_000_000_000,
        is_verified=True,
        verification_notes="Physically measured",
    )
    assert req_updated.min_vram_bytes == 2_000_000_000
    assert req_updated.is_verified is True

    # Error handling for missing model
    with pytest.raises(ModelNotFoundError):
        registry.get("non-existent")

    with pytest.raises(ModelNotFoundError):
        registry.update_state("non-existent", ModelState.HOT)


def test_model_registry_thread_safety():
    registry = ModelRegistry()
    errors = []

    def worker(worker_id: int):
        try:
            for i in range(50):
                registry.register(
                    ModelInfo(
                        model_id=f"thread-model-{worker_id}-{i}",
                        family="test",
                        provider=ModelProviderType.MOCK,
                        workload_type=WorkloadType.REASONING_VISION,
                    )
                )
                registry.get("qwen3-vl:4b-instruct")
                registry.list_models()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


# ---------------------------------------------------------------------------
# 3. GPUMemoryMonitor Tests
# ---------------------------------------------------------------------------


def test_gpu_memory_monitor_success_parsing():
    def mock_runner(cmd, **kwargs):
        stdout = "6144, 15, 5792, 0, NVIDIA GeForce RTX 3050 Laptop GPU, 595.99.02\n"
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=stdout, stderr="")

    monitor = GPUMemoryMonitor(command_runner=mock_runner)
    snap = monitor.get_snapshot()

    assert snap.total_bytes == 6144 * 1024 * 1024
    assert snap.used_bytes == 15 * 1024 * 1024
    assert snap.free_bytes == 5792 * 1024 * 1024
    assert snap.utilization_pct == 0.0
    assert snap.device_name == "NVIDIA GeForce RTX 3050 Laptop GPU"
    assert snap.driver_version == "595.99.02"

    # Headroom check (free is 5792 MiB)
    headroom_300mb = 300 * 1024 * 1024
    assert monitor.is_vram_sufficient(5000 * 1024 * 1024, safety_headroom_bytes=headroom_300mb)
    assert not monitor.is_vram_sufficient(5600 * 1024 * 1024, safety_headroom_bytes=headroom_300mb)
    assert monitor.get_available_vram_bytes(safety_headroom_bytes=headroom_300mb) == (5792 - 300) * 1024 * 1024


def test_gpu_memory_monitor_errors():
    # 1. Missing executable
    def missing_runner(cmd, **kwargs):
        raise FileNotFoundError("nvidia-smi not found")

    m1 = GPUMemoryMonitor(command_runner=missing_runner)
    with pytest.raises(HardwareMonitoringError) as exc_info:
        m1.get_snapshot()
    assert "not found" in str(exc_info.value)

    # 2. Non-zero exit code
    def failing_runner(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=12, stdout="", stderr="Driver error")

    m2 = GPUMemoryMonitor(command_runner=failing_runner)
    with pytest.raises(HardwareMonitoringError) as exc_info:
        m2.get_snapshot()
    assert "exit code 12" in str(exc_info.value)

    # 3. Malformed output
    def malformed_runner(cmd, **kwargs):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="not,enough", stderr="")

    m3 = GPUMemoryMonitor(command_runner=malformed_runner)
    with pytest.raises(HardwareMonitoringError) as exc_info:
        m3.get_snapshot()
    assert "Malformed" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 4. SystemMemoryMonitor Tests
# ---------------------------------------------------------------------------

_SAMPLE_MEMINFO = """
MemTotal:       16069160 kB
MemFree:          703884 kB
MemAvailable:    6133228 kB
Buffers:          345678 kB
Cached:          6543210 kB
SwapTotal:       2097148 kB
SwapFree:         203204 kB
"""


def test_system_memory_monitor_parsing():
    monitor = SystemMemoryMonitor(content_reader=lambda path: _SAMPLE_MEMINFO)
    snap = monitor.get_snapshot()

    assert snap.total_bytes == 16069160 * 1024
    assert snap.free_bytes == 703884 * 1024
    assert snap.available_bytes == 6133228 * 1024
    assert snap.swap_total_bytes == 2097148 * 1024
    assert snap.swap_free_bytes == 203204 * 1024
    assert snap.swap_used_bytes == (2097148 - 203204) * 1024

    # Available is ~5989.5 MiB
    assert monitor.is_ram_sufficient(3000 * 1024 * 1024)
    assert not monitor.is_ram_sufficient(6000 * 1024 * 1024)

    # Memory pressure check: swap used is (1893944 / 2097148) = 90.3%
    assert monitor.is_memory_pressured(max_swap_pct=90.0)
    assert not monitor.is_memory_pressured(max_swap_pct=95.0, min_available_bytes=1000 * 1024 * 1024)


def test_system_memory_monitor_errors():
    def missing_reader(path):
        raise FileNotFoundError("no meminfo")

    m = SystemMemoryMonitor(content_reader=missing_reader)
    with pytest.raises(HardwareMonitoringError) as exc_info:
        m.get_snapshot()
    assert "does not exist" in str(exc_info.value)

    # Missing essential keys
    def incomplete_reader(path):
        return "MemTotal: 1000 kB\n"

    m2 = SystemMemoryMonitor(content_reader=incomplete_reader)
    with pytest.raises(HardwareMonitoringError) as exc_info:
        m2.get_snapshot()
    assert "Missing essential" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 5. StorageManager Tests
# ---------------------------------------------------------------------------


class _MockDiskUsage(NamedTuple):
    total: int
    used: int
    free: int


def test_storage_manager_parsing():
    mock_usage = _MockDiskUsage(
        total=500 * 1024 * 1024 * 1024,
        used=100 * 1024 * 1024 * 1024,
        free=400 * 1024 * 1024 * 1024,
    )
    storage = StorageManager(
        disk_usage_getter=lambda path: mock_usage,
        path_exists_checker=lambda path: path == "/valid/model.safetensors",
        file_size_getter=lambda path: 2_000_000_000 if path == "/valid/model.safetensors" else 0,
    )

    snap = storage.get_snapshot("/")
    assert snap.total_gib == 500.0
    assert snap.free_gib == 400.0

    assert storage.has_sufficient_space(50 * 1024 * 1024 * 1024)
    assert not storage.has_sufficient_space(450 * 1024 * 1024 * 1024)

    assert storage.verify_path_exists("/valid/model.safetensors")
    assert not storage.verify_path_exists("/invalid/path")

    assert storage.get_file_size("/valid/model.safetensors") == 2_000_000_000
    assert storage.get_file_size("/invalid/path") is None


def test_storage_manager_detect_ollama_path(monkeypatch, tmp_path):
    # Case 1: Environment variable set
    custom_dir = tmp_path / "custom_ollama"
    custom_dir.mkdir()
    monkeypatch.setenv("FANSIVIBE_OLLAMA_MODELS_PATH", str(custom_dir))

    detected = StorageManager.detect_ollama_storage_path()
    assert detected == str(custom_dir.resolve())

    # Case 2: Environment variable unset, fallback to existing or None
    monkeypatch.delenv("FANSIVIBE_OLLAMA_MODELS_PATH", raising=False)
    monkeypatch.delenv("OLLAMA_MODELS", raising=False)
    detected_fallback = StorageManager.detect_ollama_storage_path()
    # If standard system path /usr/share/ollama/.ollama/models exists on host, it will be found;
    # otherwise None. In either case, it must not raise an error.
    assert detected_fallback is None or os.path.exists(detected_fallback)


# ---------------------------------------------------------------------------
# 6. Live Hardware Integration Probes (Read-Only)
# ---------------------------------------------------------------------------


def test_live_system_memory_monitor_on_host():
    """Verify observational SystemMemoryMonitor against actual host /proc/meminfo."""
    if not os.path.exists("/proc/meminfo"):
        pytest.skip("Not a Linux system with /proc/meminfo")

    monitor = SystemMemoryMonitor()
    snap = monitor.get_snapshot()

    assert snap.total_bytes > 0
    assert snap.available_bytes > 0
    assert snap.free_bytes > 0
    assert snap.total_mib >= 8192.0  # Host has 15 GiB RAM


def test_live_storage_manager_on_host():
    """Verify observational StorageManager against actual host filesystem."""
    storage = StorageManager()
    snap = storage.get_snapshot("/")

    assert snap.total_bytes > 0
    assert snap.free_bytes > 0
    assert snap.total_gib >= 100.0  # Host has 468 GB NVMe SSD


def test_live_gpu_memory_monitor_on_host():
    """Verify observational GPUMemoryMonitor against actual nvidia-smi if present."""
    if shutil.which("nvidia-smi") is None:
        pytest.skip("nvidia-smi not available on PATH")

    monitor = GPUMemoryMonitor()
    try:
        snap = monitor.get_snapshot()
        assert snap.total_bytes > 0
        assert snap.free_bytes > 0
        assert snap.total_mib >= 4096.0  # Host has 6144 MiB RTX 3050
        assert "RTX 3050" in (snap.device_name or "")
    except HardwareMonitoringError as exc:
        pytest.fail(f"Live nvidia-smi monitoring failed unexpectedly: {exc}")

