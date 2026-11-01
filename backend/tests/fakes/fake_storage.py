"""In-memory fake object storage adapter for automated unit and integration tests.

Implements `ObjectStoragePort` deterministically without real network I/O or
external Cloudflare infrastructure.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
import hashlib
from typing import Optional

from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageError,
    StorageNotFoundError,
    StorageObjectMetadata,
    StoragePayloadError,
    StorageTimeoutError,
)


class FakeStorageAdapter(ObjectStoragePort):
    """In-memory storage double supporting deterministic test assertions.

    Stores bytes in an internal dictionary, creates deterministic presigned URLs,
    and supports failure/timeout simulation.
    """

    def __init__(
        self,
        *,
        bucket_name: str = "test-fake-bucket",
        base_url: str = "https://fake-r2.local",
    ) -> None:
        self.bucket_name = bucket_name
        self.base_url = base_url.rstrip("/")
        self._objects: dict[str, tuple[bytes, StorageObjectMetadata]] = {}
        self.simulate_failure: Optional[Exception] = None
        self.simulate_timeout: bool = False
        self.is_closed: bool = False

    def _check_simulation(self, key: Optional[str] = None) -> None:
        if self.simulate_timeout:
            raise StorageTimeoutError(
                "Simulated storage operation timeout", key=key
            )
        if self.simulate_failure is not None:
            raise self.simulate_failure

    def put_object_bytes(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "image/webp",
        custom_metadata: Optional[dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        """Helper for test setup to inject bytes directly into fake storage."""
        etag = hashlib.md5(data).hexdigest()
        meta = StorageObjectMetadata(
            key=key,
            size_bytes=len(data),
            content_type=content_type,
            etag=etag,
            last_modified=datetime.now(timezone.utc),
            custom_metadata=dict(custom_metadata or {}),
        )
        self._objects[key] = (data, meta)
        return meta

    async def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "image/webp",
        custom_metadata: Optional[dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        self._check_simulation(key)
        return self.put_object_bytes(
            key,
            data,
            content_type=content_type,
            custom_metadata=custom_metadata,
        )

    async def generate_presigned_put_url(
        self,
        *,
        key: str,
        content_type: str,
        size_bytes: Optional[int] = None,
        expires_in_s: int = 900,
    ) -> str:
        self._check_simulation(key)
        size_param = f"&size={size_bytes}" if size_bytes is not None else ""
        return (
            f"{self.base_url}/{self.bucket_name}/{key}"
            f"?action=put&contentType={content_type}&expires={expires_in_s}{size_param}"
        )

    async def generate_presigned_get_url(
        self,
        *,
        key: str,
        expires_in_s: int = 900,
        response_content_type: Optional[str] = None,
        response_content_disposition: Optional[str] = None,
    ) -> str:
        self._check_simulation(key)
        params = [f"action=get", f"expires={expires_in_s}"]
        if response_content_type:
            params.append(f"response-content-type={response_content_type}")
        if response_content_disposition:
            params.append(f"response-content-disposition={response_content_disposition}")
        query = "&".join(params)
        return f"{self.base_url}/{self.bucket_name}/{key}?{query}"

    async def get_object_stream(
        self,
        key: str,
        *,
        chunk_size: int = 65536,
    ) -> AsyncIterator[bytes]:
        self._check_simulation(key)
        if key not in self._objects:
            raise StorageNotFoundError(f"Object not found in fake storage: {key}", key=key)

        data, _ = self._objects[key]
        for i in range(0, len(data), chunk_size):
            self._check_simulation(key)
            yield data[i : i + chunk_size]

    async def read_object(
        self,
        key: str,
        *,
        max_bytes: int = 2 * 1024 * 1024,
    ) -> bytes:
        self._check_simulation(key)
        if key not in self._objects:
            raise StorageNotFoundError(f"Object not found in fake storage: {key}", key=key)

        data, _ = self._objects[key]
        if len(data) > max_bytes:
            raise StoragePayloadError(
                f"Object exceeds maximum allowed size of {max_bytes} bytes (actual: {len(data)})",
                key=key,
            )
        return data

    async def get_object_metadata(
        self,
        key: str,
    ) -> Optional[StorageObjectMetadata]:
        self._check_simulation(key)
        item = self._objects.get(key)
        if item is None:
            return None
        return item[1]

    async def object_exists(self, key: str) -> bool:
        self._check_simulation(key)
        return key in self._objects

    async def delete_object(self, key: str) -> bool:
        self._check_simulation(key)
        self._objects.pop(key, None)
        return True

    async def copy_object(
        self,
        *,
        source_key: str,
        destination_key: str,
        content_type: Optional[str] = None,
        custom_metadata: Optional[dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        self._check_simulation(source_key)
        if source_key not in self._objects:
            raise StorageNotFoundError(
                f"Source object not found in fake storage: {source_key}",
                key=source_key,
            )

        data, src_meta = self._objects[source_key]
        new_content_type = content_type or src_meta.content_type
        new_custom_metadata = (
            dict(custom_metadata) if custom_metadata is not None else dict(src_meta.custom_metadata)
        )

        new_meta = StorageObjectMetadata(
            key=destination_key,
            size_bytes=len(data),
            content_type=new_content_type,
            etag=src_meta.etag,
            last_modified=datetime.now(timezone.utc),
            custom_metadata=new_custom_metadata,
        )
        self._objects[destination_key] = (data, new_meta)
        return new_meta

    async def close(self) -> None:
        self.is_closed = True

    # --- Test Inspection Helpers ---

    def object_exists_sync(self, key: str) -> bool:
        return key in self._objects

    def get_stored_keys(self) -> list[str]:
        return list(self._objects.keys())

    def get_stored_bytes(self, key: str) -> bytes:
        if key not in self._objects:
            raise KeyError(key)
        return self._objects[key][0]

    def clear(self) -> None:
        self._objects.clear()
        self.simulate_failure = None
        self.simulate_timeout = False
        self.is_closed = False
