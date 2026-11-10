"""System Host Memory Monitor using /proc/meminfo.

Phase 1 foundation: Strictly observational. Measures physical host RAM and swap state
using standard Linux /proc/meminfo with zero external dependencies.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable, Optional

from app.ai.manager.types import HardwareMonitoringError, SystemMemorySnapshot

logger = logging.getLogger("fansivibe.ai.manager.memory_system")

_DEFAULT_MEMINFO_PATH = "/proc/meminfo"
DEFAULT_RAM_SAFETY_HEADROOM_BYTES = 500 * 1024 * 1024  # 500 MiB


class SystemMemoryMonitor:
    """Observational host RAM and swap memory monitor."""

    def __init__(
        self,
        meminfo_path: str = _DEFAULT_MEMINFO_PATH,
        content_reader: Optional[Callable[[str], str]] = None,
        default_headroom_bytes: int = DEFAULT_RAM_SAFETY_HEADROOM_BYTES,
    ) -> None:
        self.meminfo_path = meminfo_path
        self._reader = content_reader or self._default_read
        self.default_headroom_bytes = default_headroom_bytes

    @staticmethod
    def _default_read(path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def get_snapshot(self) -> SystemMemorySnapshot:
        """Parse /proc/meminfo and return an immutable SystemMemorySnapshot."""
        t0 = time.time()
        try:
            content = self._reader(self.meminfo_path)
        except FileNotFoundError as exc:
            raise HardwareMonitoringError(
                "Host RAM", f"Memory info source '{self.meminfo_path}' does not exist."
            ) from exc
        except Exception as exc:
            raise HardwareMonitoringError(
                "Host RAM", f"Failed to read memory info from '{self.meminfo_path}': {exc}"
            ) from exc

        parsed: dict[str, int] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, rest = line.split(":", 1)
            parts = rest.strip().split()
            if not parts:
                continue
            try:
                # /proc/meminfo values are in kB
                val_kb = int(parts[0])
                parsed[key.strip()] = val_kb * 1024  # convert to bytes
            except ValueError:
                continue

        required_keys = ("MemTotal", "MemFree", "MemAvailable")
        missing = [k for k in required_keys if k not in parsed]
        if missing:
            raise HardwareMonitoringError(
                "Host RAM", f"Missing essential memory fields in meminfo: {missing}"
            )

        total_bytes = parsed["MemTotal"]
        free_bytes = parsed["MemFree"]
        available_bytes = parsed["MemAvailable"]
        used_bytes = max(0, total_bytes - free_bytes)

        swap_total_bytes = parsed.get("SwapTotal", 0)
        swap_free_bytes = parsed.get("SwapFree", 0)
        swap_used_bytes = max(0, swap_total_bytes - swap_free_bytes)

        return SystemMemorySnapshot(
            total_bytes=total_bytes,
            used_bytes=used_bytes,
            free_bytes=free_bytes,
            available_bytes=available_bytes,
            swap_total_bytes=swap_total_bytes,
            swap_used_bytes=swap_used_bytes,
            swap_free_bytes=swap_free_bytes,
            timestamp=t0,
        )

    def is_ram_sufficient(
        self, required_bytes: int, safety_headroom_bytes: Optional[int] = None
    ) -> bool:
        """Check whether available system RAM can accommodate required_bytes plus headroom."""
        headroom = (
            safety_headroom_bytes
            if safety_headroom_bytes is not None
            else self.default_headroom_bytes
        )
        snapshot = self.get_snapshot()
        return snapshot.available_bytes >= (required_bytes + headroom)

    def is_memory_pressured(
        self,
        min_available_bytes: int = 1024 * 1024 * 1024,  # 1.0 GiB floor
        max_swap_pct: float = 90.0,
    ) -> bool:
        """Return True if system memory is under pressure (low available RAM or high swap)."""
        snapshot = self.get_snapshot()
        if snapshot.available_bytes < min_available_bytes:
            return True
        if snapshot.swap_total_bytes > 0:
            swap_pct = (snapshot.swap_used_bytes / snapshot.swap_total_bytes) * 100.0
            if swap_pct >= max_swap_pct:
                return True
        return False

