"""Unit and adapter tests for CloudflareR2StorageAdapter.

Validates:
- Presigned PUT generation with parameters, content type, and expiration.
- Presigned GET generation with response header overrides.
- Streaming object reads in chunks with proper body closing.
- Bounded memory read enforcement (StoragePayloadError).
- Object existence checks and metadata parsing.
- Server-side object copying without buffering payload in RAM.
- Object deletion.
- Missing object error mapping (StorageNotFoundError).
- Provider error mapping (StoragePermissionError, StorageTimeoutError, StorageError).
- Sanitization of credentials, AWS signatures, and tokens in error messages.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock
import pytest
from botocore.exceptions import (
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
    StoragePayloadError,
    StoragePermissionError,
    StorageTimeoutError,
)
from app.infrastructure.external.storage import (
    CloudflareR2StorageAdapter,
    _sanitize_message,
)


@pytest.fixture
def mock_s3_client():
    return MagicMock()


@pytest.fixture
def r2_adapter(mock_s3_client):
    return CloudflareR2StorageAdapter(
        bucket_name="test-wardrobe-bucket",
        endpoint_url="https://test-account.r2.cloudflarestorage.com",
        access_key_id="test-access-key-id",
        secret_access_key="test-secret-access-key",
        region_name="auto",
        s3_client=mock_s3_client,
    )


def make_client_error(code: str, message: str) -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": message}},
        operation_name="MockOperation",
    )


class TestCloudflareR2StorageAdapter:
    """Comprehensive unit testing of Cloudflare R2 S3-compatible adapter."""

    def test_implements_object_storage_port(self, r2_adapter):
        assert isinstance(r2_adapter, ObjectStoragePort)

    def test_invalid_configuration_raises_storage_configuration_error(self):
        with pytest.raises(StorageConfigurationError):
            CloudflareR2StorageAdapter(
                bucket_name="",
                endpoint_url="https://endpoint.com",
                access_key_id="key",
                secret_access_key="secret",
            )
        with pytest.raises(StorageConfigurationError):
            CloudflareR2StorageAdapter(
                bucket_name="bucket",
                endpoint_url="",
                access_key_id="key",
                secret_access_key="secret",
            )
        with pytest.raises(StorageConfigurationError):
            CloudflareR2StorageAdapter(
                bucket_name="bucket",
                endpoint_url="https://endpoint.com",
                access_key_id="",
                secret_access_key="secret",
            )

    @pytest.mark.anyio
    async def test_presigned_put_url_generation(self, r2_adapter, mock_s3_client):
        mock_s3_client.generate_presigned_url.return_value = (
            "https://test-account.r2.cloudflarestorage.com/test-wardrobe-bucket/staging/key.webp?X-Amz-Signature=abc"
        )

        url = await r2_adapter.generate_presigned_put_url(
            key="staging/users/u-1/wardrobe/up-1.webp",
            content_type="image/webp",
            size_bytes=1048576,
            expires_in_s=900,
        )

        mock_s3_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="put_object",
            Params={
                "Bucket": "test-wardrobe-bucket",
                "Key": "staging/users/u-1/wardrobe/up-1.webp",
                "ContentType": "image/webp",
            },
            ExpiresIn=900,
        )
        assert "X-Amz-Signature=abc" in url

    @pytest.mark.anyio
    async def test_presigned_get_url_generation(self, r2_adapter, mock_s3_client):
        mock_s3_client.generate_presigned_url.return_value = (
            "https://test-account.r2.cloudflarestorage.com/test-wardrobe-bucket/users/u-1/item.webp?X-Amz-Signature=xyz"
        )

        url = await r2_adapter.generate_presigned_get_url(
            key="users/u-1/wardrobe/item-1/canonical.webp",
            expires_in_s=600,
            response_content_type="image/webp",
            response_content_disposition="inline",
        )

        mock_s3_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={
                "Bucket": "test-wardrobe-bucket",
                "Key": "users/u-1/wardrobe/item-1/canonical.webp",
                "ResponseContentType": "image/webp",
                "ResponseContentDisposition": "inline",
            },
            ExpiresIn=600,
        )
        assert "X-Amz-Signature=xyz" in url

    @pytest.mark.anyio
    async def test_streaming_read_and_close(self, r2_adapter, mock_s3_client):
        payload = b"RIFF1234WEBPVP8Xchunked-payload"
        mock_body = MagicMock()
        mock_body.read.side_effect = [payload[:16], payload[16:], b""]

        mock_s3_client.get_object.return_value = {"Body": mock_body}

        chunks = []
        async for chunk in r2_adapter.get_object_stream("staging/key.webp", chunk_size=16):
            chunks.append(chunk)

        assert b"".join(chunks) == payload
        mock_s3_client.get_object.assert_called_once_with(
            Bucket="test-wardrobe-bucket", Key="staging/key.webp"
        )
        mock_body.close.assert_called_once()

    @pytest.mark.anyio
    async def test_read_object_bounded_limit(self, r2_adapter, mock_s3_client):
        payload = b"small-payload"
        mock_body = MagicMock()
        mock_body.read.side_effect = [payload, b""]
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        result = await r2_adapter.read_object("key.webp", max_bytes=100)
        assert result == payload

    @pytest.mark.anyio
    async def test_read_object_exceeding_max_bytes_raises_payload_error(
        self, r2_adapter, mock_s3_client
    ):
        large_chunk = b"x" * 1024
        mock_body = MagicMock()
        mock_body.read.side_effect = [large_chunk, large_chunk, b""]
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        with pytest.raises(StoragePayloadError) as excinfo:
            await r2_adapter.read_object("key.webp", max_bytes=1500)
        assert "exceeds maximum allowed size of 1500 bytes" in str(excinfo.value)
        mock_body.close.assert_called_once()

    @pytest.mark.anyio
    async def test_get_object_metadata_and_existence(
        self, r2_adapter, mock_s3_client
    ):
        mock_s3_client.head_object.return_value = {
            "ContentLength": 524288,
            "ContentType": "image/webp",
            "ETag": '"etag-abc-123"',
            "Metadata": {"sha256": "digest123"},
        }

        meta = await r2_adapter.get_object_metadata("users/u-1/item.webp")
        assert meta is not None
        assert meta.key == "users/u-1/item.webp"
        assert meta.size_bytes == 524288
        assert meta.content_type == "image/webp"
        assert meta.etag == "etag-abc-123"
        assert meta.custom_metadata["sha256"] == "digest123"

        assert await r2_adapter.object_exists("users/u-1/item.webp") is True

    @pytest.mark.anyio
    async def test_missing_object_head_returns_none(
        self, r2_adapter, mock_s3_client
    ):
        mock_s3_client.head_object.side_effect = make_client_error(
            "404", "Not Found"
        )

        meta = await r2_adapter.get_object_metadata("missing.webp")
        assert meta is None
        assert await r2_adapter.object_exists("missing.webp") is False

    @pytest.mark.anyio
    async def test_delete_object(self, r2_adapter, mock_s3_client):
        result = await r2_adapter.delete_object("users/u-1/item.webp")
        assert result is True
        mock_s3_client.delete_object.assert_called_once_with(
            Bucket="test-wardrobe-bucket", Key="users/u-1/item.webp"
        )

    @pytest.mark.anyio
    async def test_copy_object(self, r2_adapter, mock_s3_client):
        mock_s3_client.copy_object.return_value = {"CopyObjectResult": {}}
        mock_s3_client.head_object.return_value = {
            "ContentLength": 1024,
            "ContentType": "image/webp",
            "ETag": '"etag-dst"',
            "Metadata": {"verified": "true"},
        }

        meta = await r2_adapter.copy_object(
            source_key="staging/up-1.webp",
            destination_key="canonical/item-1.webp",
            content_type="image/webp",
            custom_metadata={"verified": "true"},
        )
        assert meta.key == "canonical/item-1.webp"
        assert meta.size_bytes == 1024
        assert meta.content_type == "image/webp"
        assert meta.custom_metadata["verified"] == "true"

        mock_s3_client.copy_object.assert_called_once_with(
            Bucket="test-wardrobe-bucket",
            Key="canonical/item-1.webp",
            CopySource={"Bucket": "test-wardrobe-bucket", "Key": "staging/up-1.webp"},
            MetadataDirective="REPLACE",
            ContentType="image/webp",
            Metadata={"verified": "true"},
        )

    @pytest.mark.anyio
    async def test_provider_error_mapping(self, r2_adapter, mock_s3_client):
        # 404 / NoSuchKey
        mock_s3_client.get_object.side_effect = make_client_error(
            "NoSuchKey", "The specified key does not exist."
        )
        with pytest.raises(StorageNotFoundError):
            async for _ in r2_adapter.get_object_stream("missing.webp"):
                pass

        # 403 / AccessDenied
        mock_s3_client.get_object.side_effect = make_client_error(
            "AccessDenied", "Access Denied"
        )
        with pytest.raises(StoragePermissionError):
            async for _ in r2_adapter.get_object_stream("denied.webp"):
                pass

        # ConnectTimeout
        mock_s3_client.get_object.side_effect = ConnectTimeoutError(
            endpoint_url="https://test.r2.cloudflarestorage.com"
        )
        with pytest.raises(StorageTimeoutError):
            async for _ in r2_adapter.get_object_stream("timeout.webp"):
                pass

        # ReadTimeout
        mock_s3_client.get_object.side_effect = ReadTimeoutError(
            endpoint_url="https://test.r2.cloudflarestorage.com"
        )
        with pytest.raises(StorageTimeoutError):
            async for _ in r2_adapter.get_object_stream("timeout.webp"):
                pass

        # EndpointConnectionError
        mock_s3_client.get_object.side_effect = EndpointConnectionError(
            endpoint_url="https://test.r2.cloudflarestorage.com"
        )
        with pytest.raises(StorageTimeoutError):
            async for _ in r2_adapter.get_object_stream("net-error.webp"):
                pass

        # Generic 500 error
        mock_s3_client.get_object.side_effect = make_client_error(
            "InternalError", "Internal server error"
        )
        with pytest.raises(StorageError):
            async for _ in r2_adapter.get_object_stream("internal-error.webp"):
                pass

    @pytest.mark.anyio
    async def test_error_sanitization_prevents_signature_leakage(
        self, r2_adapter, mock_s3_client
    ):
        raw_error_message = (
            "Signature validation failed for request: "
            "https://test.r2.com/bucket/key?X-Amz-Signature=1234567890abcdef&AWSAccessKeyId=AKIAIOSFODNN7EXAMPLE"
        )
        mock_s3_client.delete_object.side_effect = make_client_error(
            "SignatureDoesNotMatch", raw_error_message
        )

        with pytest.raises(StoragePermissionError) as excinfo:
            await r2_adapter.delete_object("key.webp")

        err_repr = repr(excinfo.value)
        assert "1234567890abcdef" not in err_repr
        assert "AKIAIOSFODNN7EXAMPLE" not in err_repr

    def test_sanitize_message_utility(self):
        msg = "Error at https://r2.com?X-Amz-Signature=deadbeef0123&AWSAccessKeyId=testkey&token=secrettoken"
        clean = _sanitize_message(msg)
        assert "deadbeef0123" not in clean
        assert "testkey" not in clean
        assert "secrettoken" not in clean
        assert "[REDACTED]" in clean

    @pytest.mark.anyio
    async def test_close_calls_underlying_client_close(
        self, r2_adapter, mock_s3_client
    ):
        await r2_adapter.close()
        mock_s3_client.close.assert_called_once()

    @pytest.mark.anyio
    async def test_streaming_read_timeout_maps_to_storage_timeout_and_closes_body(
        self, r2_adapter, mock_s3_client
    ):
        mock_body = MagicMock()
        mock_body.read.side_effect = ReadTimeoutError(
            endpoint_url="https://test.r2.cloudflarestorage.com"
        )
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        with pytest.raises(StorageTimeoutError):
            async for _ in r2_adapter.get_object_stream("timeout-chunk.webp"):
                pass

        mock_body.close.assert_called_once()

    @pytest.mark.anyio
    async def test_streaming_client_error_maps_to_storage_error_and_closes_body(
        self, r2_adapter, mock_s3_client
    ):
        mock_body = MagicMock()
        mock_body.read.side_effect = make_client_error(
            "InternalError", "S3 read failed abruptly"
        )
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        with pytest.raises(StorageError) as excinfo:
            async for _ in r2_adapter.get_object_stream("err-chunk.webp"):
                pass

        assert "S3 read failed abruptly" in str(excinfo.value)
        mock_body.close.assert_called_once()

    @pytest.mark.anyio
    async def test_streaming_task_cancellation_invokes_body_close(
        self, r2_adapter, mock_s3_client
    ):
        import asyncio
        import time

        mock_body = MagicMock()

        def slow_read(n):
            time.sleep(0.05)
            return b"x" * 64

        mock_body.read.side_effect = slow_read
        mock_s3_client.get_object.return_value = {"Body": mock_body}

        async def run_stream():
            async for _ in r2_adapter.get_object_stream("cancel-test.webp"):
                pass

        task = asyncio.create_task(run_stream())
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        mock_body.close.assert_called_once()

    @pytest.mark.anyio
    async def test_put_object_success(self, r2_adapter, mock_s3_client):
        mock_s3_client.put_object.return_value = {"ETag": '"0123456789abcdef"'}
        payload = b"RIFF5678WEBPcanonical"
        key = "users/u-1/wardrobe/up-1/hash.webp"
        custom_metadata = {"purpose": "wardrobe_item", "canonical_hash": "hash"}

        meta = await r2_adapter.put_object(
            key=key,
            data=payload,
            content_type="image/webp",
            custom_metadata=custom_metadata,
        )

        mock_s3_client.put_object.assert_called_once_with(
            Bucket="test-wardrobe-bucket",
            Key=key,
            Body=payload,
            ContentType="image/webp",
            Metadata=custom_metadata,
        )
        assert meta.key == key
        assert meta.size_bytes == len(payload)
        assert meta.content_type == "image/webp"
        assert meta.etag == "0123456789abcdef"
        assert meta.custom_metadata == custom_metadata

    @pytest.mark.anyio
    async def test_put_object_permission_error_mapping(self, r2_adapter, mock_s3_client):
        mock_s3_client.put_object.side_effect = make_client_error("AccessDenied", "Forbidden bucket")
        with pytest.raises(StoragePermissionError) as excinfo:
            await r2_adapter.put_object(key="test.webp", data=b"data")
        assert excinfo.value.key == "test.webp"

    @pytest.mark.anyio
    async def test_put_object_timeout_error_mapping(self, r2_adapter, mock_s3_client):
        mock_s3_client.put_object.side_effect = ConnectTimeoutError(endpoint_url="https://r2.test")
        with pytest.raises(StorageTimeoutError) as excinfo:
            await r2_adapter.put_object(key="test.webp", data=b"data")
        assert excinfo.value.key == "test.webp"

    @pytest.mark.anyio
    async def test_put_object_sanitizes_secrets_in_errors(self, r2_adapter, mock_s3_client):
        mock_s3_client.put_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Failed with X-Amz-Signature=abcdef123456"}},
            "PutObject",
        )
        with pytest.raises(StorageError) as excinfo:
            await r2_adapter.put_object(key="test.webp", data=b"data")
        assert "[REDACTED]" in str(excinfo.value)
        assert "abcdef123456" not in str(excinfo.value)

