"""Storage Manager for NVMe and persistent model weight storage.

Phase 1 foundation: Strictly observational. Measures disk capacity and free space,
and verifies model file paths without hardcoding model storage locations.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from typing import Callable, Optional

from app.ai.manager.types import HardwareMonitoringError, StorageSnapshot

logger = logging.getLogger("fansivibe.ai.manager.storage")

DEFAULT_STORAGE_HEADROOM_BYTES = 1024 * 1024 * 1024  # 1.0 GiB safety margin


class StorageManager:
    """Observational storage capacity and path verification manager."""

    def __init__(
        self,
        disk_usage_getter: Optional[Callable[[str], shutil._ntuple_diskusage]] = None,
        path_exists_checker: Optional[Callable[[str], bool]] = None,
        file_size_getter: Optional[Callable[[str], int]] = None,
        default_headroom_bytes: int = DEFAULT_STORAGE_HEADROOM_BYTES,
    ) -> None:
        self._disk_usage = disk_usage_getter or shutil.disk_usage
        self._exists = path_exists_checker or os.path.exists
        self._size = file_size_getter or os.path.getsize
        self.default_headroom_bytes = default_headroom_bytes

    def get_snapshot(self, path: str = "/") -> StorageSnapshot:
        """Measure capacity and free space for the filesystem containing `path`."""
        t0 = time.time()
        try:
            usage = self._disk_usage(path)
            return StorageSnapshot(
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                mount_point=path,
                timestamp=t0,
            )
        except FileNotFoundError as exc:
            raise HardwareMonitoringError(
                "Storage", f"Target filesystem path '{path}' does not exist."
            ) from exc
        except Exception as exc:
            raise HardwareMonitoringError(
                "Storage", f"Failed to inspect storage at '{path}': {exc}"
            ) from exc

    def verify_path_exists(self, path: str) -> bool:
        """Check whether a model path or weight file exists on storage."""
        if not path or not path.strip():
            return False
        try:
            return self._exists(os.path.abspath(path))
        except Exception:
            return False

    def get_file_size(self, path: str) -> Optional[int]:
        """Return size in bytes of a file on storage, or None if missing or inaccessible."""
        if not self.verify_path_exists(path):
            return None
        try:
            return self._size(os.path.abspath(path))
        except Exception:
            return None

    def has_sufficient_space(
        self,
        required_bytes: int,
        path: str = "/",
        safety_headroom_bytes: Optional[int] = None,
    ) -> bool:
        """Check whether storage has free space for required_bytes plus headroom."""
        headroom = (
            safety_headroom_bytes
            if safety_headroom_bytes is not None
            else self.default_headroom_bytes
        )
        snapshot = self.get_snapshot(path)
        return snapshot.free_bytes >= (required_bytes + headroom)

    @staticmethod
    def detect_ollama_storage_path() -> Optional[str]:
        """Detect Ollama model directory from environment or known system locations without hardcoding.

        Checks environment variables first:
        1. FANSIVIBE_OLLAMA_MODELS_PATH
        2. OLLAMA_MODELS
        Then checks standard locations only if they exist on the filesystem.
        """
        env_path = os.environ.get("FANSIVIBE_OLLAMA_MODELS_PATH") or os.environ.get("OLLAMA_MODELS")
        if env_path and os.path.exists(env_path):
            return os.path.abspath(env_path)

        candidates = [
            os.path.expanduser("~/.ollama/models"),
            "/usr/share/ollama/.ollama/models",
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                return os.path.abspath(candidate)

        return None

