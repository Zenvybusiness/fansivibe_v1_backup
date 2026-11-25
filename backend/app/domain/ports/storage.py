"""Object storage port and contracts for Fansivibe media management.

Single source of truth for media object storage contracts (Stage 2 P0-4 / M16).
This port isolates domain logic and application workflows from concrete
storage providers (Cloudflare R2, AWS S3, or in-memory test fakes).

Invariants & Guarantees:
- Provider-neutral contract: Domain code never imports or couples to boto3,
  botocore, or Cloudflare-specific SDKs.
- Zero credential exposure: Storage credentials reside strictly within the
  backend adapter layer and are never returned through this boundary.
- Zero FastAPI RAM buffering (PR-8): Media reads and upload paths support
  streaming interfaces to prevent large binary payload buffering in memory.
- Bounded memory safety: Helper methods like `read_object` enforce a strict
  maximum byte limit (default 2MB) to prevent memory exhaustion attacks.
- OW-1 ownership compliance: Object keys are strictly namespaced by caller
  identity (e.g. `users/{user_id}/wardrobe/...`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True)
class StorageObjectMetadata:
    """Provider-independent metadata for an object stored in object storage."""

    key: str
    size_bytes: int
    content_type: str
    etag: Optional[str] = None
    last_modified: Optional[datetime] = None
    custom_metadata: dict[str, str] = field(default_factory=dict)


# --- Exception Taxonomy ---


class StorageError(Exception):
    """Base exception for all object storage operations."""

    def __init__(
        self,
        message: str,
        *,
        key: Optional[str] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.key = key
        self.cause = cause

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, key={self.key!r})"


class StorageNotFoundError(StorageError):
    """Raised when the requested object key does not exist in storage."""


class StoragePermissionError(StorageError):
    """Raised when access is denied or authentication with storage failed."""


class StorageTimeoutError(StorageError):
    """Raised when a storage network or socket operation times out."""


class StorageConfigurationError(StorageError):
    """Raised when storage configuration is invalid or missing required credentials."""


class StoragePayloadError(StorageError):
    """Raised when an object payload is invalid or exceeds bounds (e.g. >2MB)."""


# Canonical field produced by `validate_media_association` first, followed by
# documented legacy field names still present in historical rows/tests.
WARDROBE_IMAGE_KEY_FIELDS: tuple[str, ...] = (
    "objectKey",
    "object_key",
    "canonical_key",
    "canonicalKey",
    "key",
)

_URL_SCHEME_PREFIXES: tuple[str, ...] = (
    "http:",
    "https:",
    "s3:",
    "r2:",
    "file:",
    "data:",
    "javascript:",
    "//",
)


@dataclass(frozen=True)
class ResolvedStorageObjectKey:
    """Validated storage object key resolved from a wardrobe image reference."""

    key: str
    source_field: str


def validate_scoped_object_key(key: str, *, user_id: str | None = None) -> None:
    """Validate object key structure, preventing path traversal and enforcing scoping."""
    if not key or not key.strip():
        raise StoragePayloadError("Object key must not be empty", key=key)
    if ".." in key or key.startswith("/") or "\\" in key or "\x00" in key:
        raise StoragePayloadError(
            f"Invalid object key path traversal detected: {key}", key=key
        )
    if user_id is not None:
        u_str = str(user_id)
        expected_user = f"users/{u_str}/"
        expected_staging = f"staging/users/{u_str}/"
        if not (key.startswith(expected_user) or key.startswith(expected_staging)):
            raise StoragePermissionError(
                f"Object key {key} is not scoped to user {u_str}",
                key=key,
            )


def _normalize_user_scope(user_id: UUID | str) -> str:
    raw = str(user_id).strip() if user_id is not None else ""
    if not raw:
        raise StoragePermissionError("User ID is required for scoped storage key resolution")
    try:
        return str(UUID(raw))
    except ValueError:
        return raw


def resolve_wardrobe_image_key(
    image_ref: Any,
    *,
    user_id: UUID | str,
    allow_legacy_scans: bool = True,
) -> ResolvedStorageObjectKey:
    """Resolve and validate the canonical storage object key from a wardrobe `image_ref`.

    Rules enforced:
    1. Prefers canonical `objectKey` produced by `validate_media_association`.
    2. Supports documented legacy key fields (`object_key`, `canonical_key`,
       `canonicalKey`, `key`) only when present and valid.
    3. Rejects missing, empty, non-string, malformed, or unsafe keys.
    4. Never interprets URL fields (`url`, `downloadUrl`, `imageUrl`, etc.) or
       URL-shaped strings as R2 object keys.
    5. Rejects conflicting values when multiple recognized key fields disagree.
    6. Enforces user ownership (`users/{user_id}/`) and permitted wardrobe
       storage namespaces (never `staging/` or foreign user prefixes).
    """
    if not isinstance(image_ref, Mapping):
        raise StoragePayloadError("Wardrobe image reference is missing or invalid")

    u_str = _normalize_user_scope(user_id)

    present_candidates: list[tuple[str, str]] = []
    for field_name in WARDROBE_IMAGE_KEY_FIELDS:
        if field_name not in image_ref:
            continue
        raw_val = image_ref[field_name]
        if raw_val is None:
            continue
        if not isinstance(raw_val, str):
            raise StoragePayloadError(
                f"Wardrobe image reference field '{field_name}' must be a string"
            )
        cleaned = raw_val.strip()
        if not cleaned:
            raise StoragePayloadError(
                f"Wardrobe image reference field '{field_name}' must not be empty",
                key=raw_val,
            )
        present_candidates.append((field_name, cleaned))

    if not present_candidates:
        raise StoragePayloadError("Wardrobe image reference does not contain a storage key")

    unique_values = {val for _, val in present_candidates}
    if len(unique_values) > 1:
        field_names = ", ".join(name for name, _ in present_candidates)
        raise StoragePayloadError(
            f"Conflicting storage key fields in wardrobe image reference ({field_names})"
        )

    source_field, resolved_key = present_candidates[0]

    lowered = resolved_key.lower()
    if (
        "://" in resolved_key
        or lowered.startswith(_URL_SCHEME_PREFIXES)
        or "?" in resolved_key
        or "#" in resolved_key
    ):
        raise StoragePayloadError(
            "Wardrobe storage key must be an object key, not a URL",
            key=resolved_key,
        )

    if any(ord(ch) < 32 or ord(ch) == 127 or ch.isspace() for ch in resolved_key):
        raise StoragePayloadError(
            "Wardrobe storage key contains invalid whitespace or control characters",
            key=resolved_key,
        )

    if (
        resolved_key.startswith("/")
        or resolved_key.endswith("/")
        or "\\" in resolved_key
        or "\x00" in resolved_key
    ):
        raise StoragePayloadError(
            "Invalid wardrobe storage key path format",
            key=resolved_key,
        )

    segments = resolved_key.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        raise StoragePayloadError(
            "Invalid wardrobe storage key path segments",
            key=resolved_key,
        )

    if segments[0] == "staging":
        raise StoragePermissionError(
            "Staging storage keys cannot be used as wardrobe media",
            key=resolved_key,
        )

    validate_scoped_object_key(resolved_key, user_id=u_str)

    permitted_prefixes = [f"users/{u_str}/wardrobe/"]
    if allow_legacy_scans:
        permitted_prefixes.append(f"users/{u_str}/scans/")
    if not any(resolved_key.startswith(prefix) for prefix in permitted_prefixes):
        raise StoragePermissionError(
            "Wardrobe storage key is outside permitted wardrobe media namespace",
            key=resolved_key,
        )

    return ResolvedStorageObjectKey(key=resolved_key, source_field=source_field)


# --- Port Specification ---


@runtime_checkable
class ObjectStoragePort(Protocol):
    """Asynchronous object storage contract for media persistence and retrieval."""

    async def generate_presigned_put_url(
        self,
        *,
        key: str,
        content_type: str,
        size_bytes: Optional[int] = None,
        expires_in_s: int = 900,
    ) -> str:
        """Generate a short-lived presigned PUT URL for direct client-to-storage upload.

        Args:
            key: Target object key (e.g. `staging/users/{user_id}/wardrobe/{upload_id}.webp`).
            content_type: MIME type of the payload (e.g. `image/webp`).
            size_bytes: Optional expected content length in bytes.
            expires_in_s: Expiration window in seconds (default 15 minutes / 900s).

        Returns:
            Fully-qualified presigned HTTPS PUT URL with signed authorization query parameters.
        """
        ...

    async def generate_presigned_get_url(
        self,
        *,
        key: str,
        expires_in_s: int = 900,
        response_content_type: Optional[str] = None,
        response_content_disposition: Optional[str] = None,
    ) -> str:
        """Generate a short-lived presigned GET URL for authenticated media retrieval.

        Args:
            key: Target object key.
            expires_in_s: Expiration window in seconds (default 15 minutes / 900s).
            response_content_type: Optional Content-Type header override in response.
            response_content_disposition: Optional Content-Disposition header override.

        Returns:
            Fully-qualified presigned HTTPS GET URL with signed authorization query parameters.
        """
        ...

    def get_object_stream(
        self,
        key: str,
        *,
        chunk_size: int = 65536,
    ) -> AsyncIterator[bytes]:
        """Stream object bytes asynchronously in chunks without full memory buffering.

        Args:
            key: Target object key.
            chunk_size: Stream chunk size in bytes (default 64KB).

        Yields:
            Byte chunks until end of stream.

        Raises:
            StorageNotFoundError: If the key does not exist.
            StorageError: On connection or provider failures.
        """
        ...

    async def read_object(
        self,
        key: str,
        *,
        max_bytes: int = 2 * 1024 * 1024,
    ) -> bytes:
        """Read and return object bytes with strict bounded memory protection.

        Args:
            key: Target object key.
            max_bytes: Maximum allowed byte length (default 2MB / 2,097,152 bytes).

        Returns:
            Complete binary bytes of the object.

        Raises:
            StorageNotFoundError: If key does not exist.
            StoragePayloadError: If the object exceeds `max_bytes`.
            StorageError: On provider failure.
        """
        ...

    async def get_object_metadata(
        self,
        key: str,
    ) -> Optional[StorageObjectMetadata]:
        """Fetch metadata for an object without downloading its payload.

        Args:
            key: Target object key.

        Returns:
            StorageObjectMetadata if the object exists, or None if not found.

        Raises:
            StoragePermissionError: If storage credentials/access are denied.
            StorageError: On provider failure.
        """
        ...

    async def object_exists(self, key: str) -> bool:
        """Check if an object exists in storage.

        Args:
            key: Target object key.

        Returns:
            True if object exists, False otherwise.
        """
        ...

    async def delete_object(self, key: str) -> bool:
        """Delete an object from storage.

        Args:
            key: Target object key.

        Returns:
            True if deleted (or if object was already absent).

        Raises:
            StoragePermissionError: If access is denied.
            StorageError: On provider failure.
        """
        ...

    async def copy_object(
        self,
        *,
        source_key: str,
        destination_key: str,
        content_type: Optional[str] = None,
        custom_metadata: Optional[dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        """Perform a server-side object copy without downloading bytes to the backend.

        Used to promote verified objects from staging to canonical keys.

        Args:
            source_key: Source object key (e.g. `staging/users/...`).
            destination_key: Target object key (e.g. `users/{user_id}/wardrobe/...`).
            content_type: Optional updated MIME type for the promoted object.
            custom_metadata: Optional metadata dictionary to associate with destination.

        Returns:
            StorageObjectMetadata of the copied object at destination_key.

        Raises:
            StorageNotFoundError: If source_key does not exist.
            StoragePermissionError: If access is denied.
            StorageError: On provider failure.
        """
        ...

    async def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "image/webp",
        custom_metadata: Optional[dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        """Upload raw binary bytes to the specified object key.

        Used to persist server-generated canonical images to storage.

        Args:
            key: Target object key (e.g. `users/{user_id}/wardrobe/{upload_id}/{hash}.webp`).
            data: Binary payload bytes.
            content_type: MIME type of the payload (default `image/webp`).
            custom_metadata: Optional custom metadata dictionary.

        Returns:
            StorageObjectMetadata for the written object.

        Raises:
            StoragePermissionError: If storage credentials/access are denied.
            StorageError: On provider failure.
        """
        ...

    async def close(self) -> None:
        """Release underlying client sessions and network resources."""
        ...
