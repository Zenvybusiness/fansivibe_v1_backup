"""Domain port protocols and value records."""

from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageConfigurationError,
    StorageError,
    StorageNotFoundError,
    StorageObjectMetadata,
    StoragePayloadError,
    StoragePermissionError,
    StorageTimeoutError,
)

__all__ = [
    "ObjectStoragePort",
    "StorageObjectMetadata",
    "StorageError",
    "StorageNotFoundError",
    "StoragePermissionError",
    "StorageTimeoutError",
    "StorageConfigurationError",
    "StoragePayloadError",
]
