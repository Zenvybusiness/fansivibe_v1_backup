"""Cloudflare R2 object storage adapter using S3-compatible client.

Implements `ObjectStoragePort` for production wardrobe media persistence (Stage 2 P0-4 / M16).
Conforms to:
- S3-compatible protocol using boto3 with SigV4 and path-style addressing.
- Zero FastAPI RAM buffering (PR-8): streaming reads and direct presigned uploads.
- Secure credential isolation: credentials stay on the backend and are never leaked.
- Sanitized error handling: credentials, signatures, and presigned URLs are stripped from logs/errors.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone
import logging
import re
from typing import TYPE_CHECKING, Any, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

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

if TYPE_CHECKING:
    from app.config.settings import Settings

logger = logging.getLogger(__name__)

# Patterns to sanitize from error messages and logs
_SECRET_PATTERNS = [
    re.compile(r"X-Amz-Signature=[0-9a-fA-F]+"),
    re.compile(r"X-Amz-Credential=[^&\s]+"),
    re.compile(r"AWSAccessKeyId=[^&\s]+"),
    re.compile(r"Signature=[^&\s]+"),
    re.compile(r"(?<=[?&]token=)[^&\s]+"),
]


def _sanitize_message(message: str) -> str:
    """Strip sensitive query parameters, AWS signatures, and tokens from text."""
    sanitized = message
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


class CloudflareR2StorageAdapter(ObjectStoragePort):
    """Cloudflare R2 storage adapter adhering strictly to ObjectStoragePort."""

    def __init__(
        self,
        *,
        bucket_name: str,
        endpoint_url: str,
        access_key_id: str,
        secret_access_key: str,
        region_name: str = "auto",
        connect_timeout_s: float = 3.0,
        read_timeout_s: float = 10.0,
        max_retries: int = 2,
        s3_client: Optional[Any] = None,
    ) -> None:
        if not bucket_name:
            raise StorageConfigurationError("bucket_name must not be empty")
        if not endpoint_url:
            raise StorageConfigurationError("endpoint_url must not be empty")
        if not access_key_id or not secret_access_key:
            raise StorageConfigurationError(
                "access_key_id and secret_access_key must not be empty"
            )

        self._bucket_name = bucket_name
        self._endpoint_url = endpoint_url.rstrip("/")
        self._region_name = region_name or "auto"
        self._connect_timeout_s = connect_timeout_s
        self._read_timeout_s = read_timeout_s
        self._max_retries = max_retries

        if s3_client is not None:
            self._client = s3_client
        else:
            botocore_config = Config(
                region_name=self._region_name,
                connect_timeout=self._connect_timeout_s,
                read_timeout=self._read_timeout_s,
                retries={"max_attempts": self._max_retries, "mode": "standard"},
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            )
            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                config=botocore_config,
            )

    @property
    def bucket_name(self) -> str:
        return self._bucket_name

    def _map_client_error(self, exc: ClientError, *, key: Optional[str] = None) -> StorageError:
        error_dict = exc.response.get("Error", {})
        code = str(error_dict.get("Code", "Unknown"))
        raw_msg = str(error_dict.get("Message", "S3 operation failed"))
        safe_msg = _sanitize_message(raw_msg)

        if code in ("404", "NoSuchKey", "NotFound"):
            return StorageNotFoundError(f"Object not found: {key}", key=key, cause=exc)
        if code in (
            "403",
            "AccessDenied",
            "InvalidAccessKeyId",
            "SignatureDoesNotMatch",
            "Unauthorized",
        ):
            return StoragePermissionError(
                "Storage access denied or invalid credentials",
                key=key,
                cause=exc,
            )
        if code in ("RequestTimeout", "EndpointConnectionError"):
            return StorageTimeoutError("Storage request timed out", key=key, cause=exc)
        return StorageError(f"Storage error [{code}]: {safe_msg}", key=key, cause=exc)

    def _map_exception(self, exc: Exception, *, key: Optional[str] = None) -> StorageError:
        if isinstance(exc, StorageError):
            return exc
        if isinstance(exc, ClientError):
            return self._map_client_error(exc, key=key)
        if isinstance(exc, (ConnectTimeoutError, ReadTimeoutError, asyncio.TimeoutError)):
            return StorageTimeoutError("Storage operation timed out", key=key, cause=exc)
        if isinstance(exc, EndpointConnectionError):
            return StorageTimeoutError("Failed to connect to storage endpoint", key=key, cause=exc)
        safe_msg = _sanitize_message(str(exc))
        return StorageError(f"Storage operation failed: {safe_msg}", key=key, cause=exc)

    async def generate_presigned_put_url(
        self,
        *,
        key: str,
        content_type: str,
        size_bytes: Optional[int] = None,
        expires_in_s: int = 900,
    ) -> str:
        params: dict[str, Any] = {
            "Bucket": self._bucket_name,
            "Key": key,
            "ContentType": content_type,
        }

        def _generate() -> str:
            return self._client.generate_presigned_url(
                ClientMethod="put_object",
                Params=params,
                ExpiresIn=expires_in_s,
            )

        try:
            return await asyncio.to_thread(_generate)
        except Exception as exc:
            raise self._map_exception(exc, key=key)

    async def generate_presigned_get_url(
        self,
        *,
        key: str,
        expires_in_s: int = 900,
        response_content_type: Optional[str] = None,
        response_content_disposition: Optional[str] = None,
    ) -> str:
        params: dict[str, Any] = {
            "Bucket": self._bucket_name,
            "Key": key,
        }
        if response_content_type:
            params["ResponseContentType"] = response_content_type
        if response_content_disposition:
            params["ResponseContentDisposition"] = response_content_disposition

        def _generate() -> str:
            return self._client.generate_presigned_url(
                ClientMethod="get_object",
                Params=params,
                ExpiresIn=expires_in_s,
            )

        try:
            return await asyncio.to_thread(_generate)
        except Exception as exc:
            raise self._map_exception(exc, key=key)

    async def get_object_stream(
        self,
        key: str,
        *,
        chunk_size: int = 65536,
    ) -> AsyncIterator[bytes]:
        def _get():
            return self._client.get_object(Bucket=self._bucket_name, Key=key)

        try:
            response = await asyncio.to_thread(_get)
        except Exception as exc:
            raise self._map_exception(exc, key=key)

        body = response.get("Body")
        if body is None:
            return

        try:
            while True:
                try:
                    chunk = await asyncio.to_thread(body.read, chunk_size)
                except Exception as exc:
                    raise self._map_exception(exc, key=key)
                if not chunk:
                    break
                yield chunk
        finally:
            close_fn = getattr(body, "close", None)
            if callable(close_fn):
                try:
                    if asyncio.iscoroutinefunction(close_fn):
                        await close_fn()
                    else:
                        close_fn()
                except Exception:
                    pass

    async def read_object(
        self,
        key: str,
        *,
        max_bytes: int = 2 * 1024 * 1024,
    ) -> bytes:
        chunks: list[bytes] = []
        total = 0
        stream = self.get_object_stream(key)
        try:
            async for chunk in stream:
                total += len(chunk)
                if total > max_bytes:
                    raise StoragePayloadError(
                        f"Object exceeds maximum allowed size of {max_bytes} bytes",
                        key=key,
                    )
                chunks.append(chunk)
        finally:
            await stream.aclose()
        return b"".join(chunks)


    async def get_object_metadata(
        self,
        key: str,
    ) -> Optional[StorageObjectMetadata]:
        def _head():
            return self._client.head_object(Bucket=self._bucket_name, Key=key)

        try:
            resp = await asyncio.to_thread(_head)
            return StorageObjectMetadata(
                key=key,
                size_bytes=int(resp.get("ContentLength", 0)),
                content_type=str(resp.get("ContentType", "application/octet-stream")),
                etag=resp.get("ETag", "").strip('"') if resp.get("ETag") else None,
                last_modified=resp.get("LastModified"),
                custom_metadata=dict(resp.get("Metadata", {})),
            )
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in ("404", "NoSuchKey", "NotFound"):
                return None
            raise self._map_client_error(exc, key=key)
        except Exception as exc:
            raise self._map_exception(exc, key=key)

    async def object_exists(self, key: str) -> bool:
        meta = await self.get_object_metadata(key)
        return meta is not None

    async def delete_object(self, key: str) -> bool:
        def _delete():
            return self._client.delete_object(Bucket=self._bucket_name, Key=key)

        try:
            await asyncio.to_thread(_delete)
            return True
        except Exception as exc:
            raise self._map_exception(exc, key=key)

    async def copy_object(
        self,
        *,
        source_key: str,
        destination_key: str,
        content_type: Optional[str] = None,
        custom_metadata: Optional[dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        def _copy():
            copy_source = {"Bucket": self._bucket_name, "Key": source_key}
            params: dict[str, Any] = {
                "Bucket": self._bucket_name,
                "Key": destination_key,
                "CopySource": copy_source,
            }
            if content_type or custom_metadata is not None:
                params["MetadataDirective"] = "REPLACE"
                if content_type:
                    params["ContentType"] = content_type
                if custom_metadata is not None:
                    params["Metadata"] = custom_metadata
            return self._client.copy_object(**params)

        try:
            await asyncio.to_thread(_copy)
            meta = await self.get_object_metadata(destination_key)
            if meta is None:
                raise StorageError(
                    f"Copy succeeded but destination object {destination_key} was not found",
                    key=destination_key,
                )
            return meta
        except Exception as exc:
            raise self._map_exception(exc, key=source_key)

    async def put_object(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "image/webp",
        custom_metadata: Optional[dict[str, str]] = None,
    ) -> StorageObjectMetadata:
        def _put():
            params: dict[str, Any] = {
                "Bucket": self._bucket_name,
                "Key": key,
                "Body": data,
                "ContentType": content_type,
            }
            if custom_metadata:
                params["Metadata"] = custom_metadata
            return self._client.put_object(**params)

        try:
            resp = await asyncio.to_thread(_put)
            etag = resp.get("ETag", "").strip('"') if isinstance(resp, dict) else None
            return StorageObjectMetadata(
                key=key,
                size_bytes=len(data),
                content_type=content_type,
                etag=etag,
                last_modified=datetime.now(timezone.utc),
                custom_metadata=dict(custom_metadata or {}),
            )
        except Exception as exc:
            raise self._map_exception(exc, key=key)

    async def close(self) -> None:
        close_fn = getattr(self._client, "close", None)
        if callable(close_fn):
            await asyncio.to_thread(close_fn)


# --- Storage Factory & Dependency Singleton Seam ---

_adapter_instance: Optional[ObjectStoragePort] = None
_adapter_config_fingerprint: Optional[tuple] = None


def create_storage_adapter(settings: Settings) -> ObjectStoragePort:
    """Factory creating the appropriate ObjectStoragePort based on Settings."""
    provider = settings.media_storage_provider.lower().strip()
    if provider == "r2":
        if not settings.effective_r2_endpoint_url:
            raise StorageConfigurationError(
                "Cloudflare R2 requires R2_ENDPOINT_URL or R2_ACCOUNT_ID"
            )
        if not settings.r2_bucket_name:
            raise StorageConfigurationError("Cloudflare R2 requires R2_BUCKET_NAME")
        if not settings.r2_access_key_id or not settings.r2_secret_access_key:
            raise StorageConfigurationError(
                "Cloudflare R2 requires R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY"
            )

        return CloudflareR2StorageAdapter(
            bucket_name=settings.r2_bucket_name,
            endpoint_url=settings.effective_r2_endpoint_url,
            access_key_id=settings.r2_access_key_id,
            secret_access_key=settings.r2_secret_access_key,
            region_name=settings.r2_region,
            connect_timeout_s=settings.r2_connect_timeout_s,
            read_timeout_s=settings.r2_read_timeout_s,
            max_retries=settings.r2_max_retries,
        )

    # In-memory fake double for local development and test runs
    from tests.fakes.fake_storage import FakeStorageAdapter

    return FakeStorageAdapter(
        bucket_name=settings.r2_bucket_name or "fansivibe-dev-storage",
    )


def get_default_storage_adapter(settings: Settings) -> ObjectStoragePort:
    """Retrieve or initialize the process-wide storage adapter singleton."""
    global _adapter_instance, _adapter_config_fingerprint
    fingerprint = (
        settings.media_storage_provider,
        settings.r2_bucket_name,
        settings.effective_r2_endpoint_url,
        settings.r2_region,
    )
    if _adapter_instance is None or _adapter_config_fingerprint != fingerprint:
        _adapter_instance = create_storage_adapter(settings)
        _adapter_config_fingerprint = fingerprint
    return _adapter_instance


def reset_default_storage_adapter() -> None:
    """Reset the cached storage adapter singleton (used in tests)."""
    global _adapter_instance, _adapter_config_fingerprint
    _adapter_instance = None
    _adapter_config_fingerprint = None
