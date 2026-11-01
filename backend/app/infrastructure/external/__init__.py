"""External infrastructure adapters and ephemeral repositories."""

from app.infrastructure.external.ephemeral_repositories import (
    EphemeralUserStateRepository,
    EphemeralWardrobeItemRepository,
)
from app.infrastructure.external.storage import (
    CloudflareR2StorageAdapter,
    create_storage_adapter,
    get_default_storage_adapter,
    reset_default_storage_adapter,
)

__all__ = [
    "EphemeralWardrobeItemRepository",
    "EphemeralUserStateRepository",
    "CloudflareR2StorageAdapter",
    "create_storage_adapter",
    "get_default_storage_adapter",
    "reset_default_storage_adapter",
]
