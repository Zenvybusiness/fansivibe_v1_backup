"""GPU Memory Monitor using nvidia-smi.

Phase 1 foundation: Strictly observational. Provides real-time VRAM measurements,
safety headroom calculations, and capacity verification without model manipulation.
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Callable, Optional

from app.ai.manager.types import GPUMemorySnapshot, HardwareMonitoringError

logger = logging.getLogger("fansivibe.ai.manager.memory_gpu")

_NVIDIA_SMI_CMD = [
    "nvidia-smi",
    "--query-gpu=memory.total,memory.used,memory.free,utilization.gpu,name,driver_version",
    "--format=csv,noheader,nounits",
]

# Default safety headroom (300 MiB) to absorb transient PyTorch allocations & context buffers
DEFAULT_GPU_SAFETY_HEADROOM_BYTES = 300 * 1024 * 1024


class GPUMemoryMonitor:
    """Observational GPU hardware monitor."""

    def __init__(
        self,
        command_runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
        default_headroom_bytes: int = DEFAULT_GPU_SAFETY_HEADROOM_BYTES,
    ) -> None:
        self._runner = command_runner or subprocess.run
        self.default_headroom_bytes = default_headroom_bytes

    def get_snapshot(self, timeout_s: float = 3.0) -> GPUMemorySnapshot:
        """Query physical GPU VRAM and utilization via nvidia-smi."""
        t0 = time.time()
        try:
            res = self._runner(
                _NVIDIA_SMI_CMD,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except FileNotFoundError as exc:
            raise HardwareMonitoringError(
                "GPU", "nvidia-smi executable not found in system PATH."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise HardwareMonitoringError(
                "GPU", f"nvidia-smi timed out after {timeout_s}s."
            ) from exc
        except Exception as exc:
            raise HardwareMonitoringError(
                "GPU", f"Unexpected error executing nvidia-smi: {exc}"
            ) from exc

        if res.returncode != 0:
            err = (res.stderr or "").strip()
            raise HardwareMonitoringError(
                "GPU", f"nvidia-smi returned exit code {res.returncode}: {err}"
            )

        output = (res.stdout or "").strip()
        if not output:
            raise HardwareMonitoringError("GPU", "nvidia-smi returned empty stdout.")

        # Take first line if multiple GPUs exist (host has single RTX 3050)
        line = output.splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            raise HardwareMonitoringError(
                "GPU", f"Malformed nvidia-smi output: expected >= 3 fields, got: '{line}'"
            )

        try:
            total_mib = float(parts[0])
            used_mib = float(parts[1])
            free_mib = float(parts[2])
            util_pct = float(parts[3]) if len(parts) > 3 and parts[3] != "[Not Supported]" else None
            device_name = parts[4] if len(parts) > 4 else None
            driver_ver = parts[5] if len(parts) > 5 else None

            total_bytes = int(total_mib * 1024 * 1024)
            used_bytes = int(used_mib * 1024 * 1024)
            free_bytes = int(free_mib * 1024 * 1024)

            return GPUMemorySnapshot(
                total_bytes=total_bytes,
                used_bytes=used_bytes,
                free_bytes=free_bytes,
                utilization_pct=util_pct,
                device_name=device_name,
                driver_version=driver_ver,
                timestamp=t0,
            )
        except ValueError as exc:
            raise HardwareMonitoringError(
                "GPU", f"Failed to parse numeric memory values from nvidia-smi output: '{line}'"
            ) from exc

    def get_available_vram_bytes(self, safety_headroom_bytes: Optional[int] = None) -> int:
        """Return free VRAM bytes minus safety headroom, floored at 0."""
        headroom = (
            safety_headroom_bytes
            if safety_headroom_bytes is not None
            else self.default_headroom_bytes
        )
        snapshot = self.get_snapshot()
        return max(0, snapshot.free_bytes - headroom)

    def is_vram_sufficient(
        self, required_bytes: int, safety_headroom_bytes: Optional[int] = None
    ) -> bool:
        """Check whether free VRAM can accommodate required_bytes plus safety headroom."""
        headroom = (
            safety_headroom_bytes
            if safety_headroom_bytes is not None
            else self.default_headroom_bytes
        )
        snapshot = self.get_snapshot()
        return snapshot.free_bytes >= (required_bytes + headroom)

