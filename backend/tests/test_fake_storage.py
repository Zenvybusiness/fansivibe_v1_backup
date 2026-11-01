"""Unit tests for FakeStorageAdapter in-memory test double.

Validates:
- Strict conformance to ObjectStoragePort protocol.
- Presigned PUT and GET URL generation are deterministic.
- Byte storage, retrieval, and chunked streaming reads.
- Bounded read_object memory limits and payload error rejection.
- Object existence checks and metadata verification.
- Object deletion and server-side copy operations.
- Missing object error handling.
- Simulated failure and timeout injection.
- Zero network I/O or external cloud dependency.
"""

from __future__ import annotations

import pytest

from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageError,
    StorageNotFoundError,
    StoragePayloadError,
    StorageTimeoutError,
)
from tests.fakes.fake_storage import FakeStorageAdapter


@pytest.fixture
def fake_storage() -> FakeStorageAdapter:
    adapter = FakeStorageAdapter(bucket_name="test-wardrobe-bucket")
    yield adapter
    adapter.clear()


class TestFakeStorageAdapter:
    """Validate in-memory fake storage double behavior and contract compliance."""

    def test_implements_object_storage_port(self, fake_storage: FakeStorageAdapter):
        assert isinstance(fake_storage, ObjectStoragePort)

    @pytest.mark.anyio
    async def test_presigned_put_url_generation(self, fake_storage: FakeStorageAdapter):
        url = await fake_storage.generate_presigned_put_url(
            key="staging/users/u-1/wardrobe/up-1.webp",
            content_type="image/webp",
            size_bytes=1024,
            expires_in_s=900,
        )
        assert "https://fake-r2.local/test-wardrobe-bucket" in url
        assert "staging/users/u-1/wardrobe/up-1.webp" in url
        assert "contentType=image/webp" in url
        assert "expires=900" in url
        assert "size=1024" in url

    @pytest.mark.anyio
    async def test_presigned_get_url_generation(self, fake_storage: FakeStorageAdapter):
        url = await fake_storage.generate_presigned_get_url(
            key="users/u-1/wardrobe/item-1/hash.webp",
            expires_in_s=600,
            response_content_type="image/webp",
        )
        assert "https://fake-r2.local/test-wardrobe-bucket" in url
        assert "users/u-1/wardrobe/item-1/hash.webp" in url
        assert "action=get" in url
        assert "expires=600" in url
        assert "response-content-type=image/webp" in url

    @pytest.mark.anyio
    async def test_put_read_and_metadata_verification(
        self, fake_storage: FakeStorageAdapter
    ):
        data = b"RIFF....WEBPVP8Xfake-webp-image-payload"
        key = "users/u-1/wardrobe/item-100/master.webp"

        meta = fake_storage.put_object_bytes(
            key,
            data,
            content_type="image/webp",
            custom_metadata={"item_id": "item-100", "role": "master"},
        )
        assert meta.key == key
        assert meta.size_bytes == len(data)
        assert meta.content_type == "image/webp"
        assert meta.etag is not None
        assert meta.custom_metadata["item_id"] == "item-100"

        # Check existence
        assert await fake_storage.object_exists(key) is True
        assert await fake_storage.object_exists("non-existent-key") is False

        # Read metadata
        fetched_meta = await fake_storage.get_object_metadata(key)
        assert fetched_meta is not None
        assert fetched_meta.key == key
        assert fetched_meta.size_bytes == len(data)

        # Read bytes
        fetched_bytes = await fake_storage.read_object(key)
        assert fetched_bytes == data

    @pytest.mark.anyio
    async def test_streaming_read_in_chunks(
        self, fake_storage: FakeStorageAdapter
    ):
        payload = b"0123456789" * 100  # 1000 bytes
        key = "test/streaming/object.bin"
        fake_storage.put_object_bytes(key, payload, content_type="application/octet-stream")

        chunks = []
        async for chunk in fake_storage.get_object_stream(key, chunk_size=250):
            chunks.append(chunk)

        assert len(chunks) == 4
        assert b"".join(chunks) == payload

    @pytest.mark.anyio
    async def test_read_object_bounded_limit_enforcement(
        self, fake_storage: FakeStorageAdapter
    ):
        large_payload = b"x" * 2000
        key = "test/oversized.bin"
        fake_storage.put_object_bytes(key, large_payload)

        # Reading with smaller max_bytes fails with StoragePayloadError
        with pytest.raises(StoragePayloadError) as excinfo:
            await fake_storage.read_object(key, max_bytes=1000)
        assert "exceeds maximum allowed size of 1000 bytes" in str(excinfo.value)

    @pytest.mark.anyio
    async def test_read_missing_object_raises_not_found(
        self, fake_storage: FakeStorageAdapter
    ):
        with pytest.raises(StorageNotFoundError) as excinfo:
            await fake_storage.read_object("missing/key.webp")
        assert "missing/key.webp" in str(excinfo.value)

    @pytest.mark.anyio
    async def test_delete_object(self, fake_storage: FakeStorageAdapter):
        key = "to-be-deleted.webp"
        fake_storage.put_object_bytes(key, b"content")
        assert await fake_storage.object_exists(key) is True

        result = await fake_storage.delete_object(key)
        assert result is True
        assert await fake_storage.object_exists(key) is False

        # Deleting already-missing key succeeds safely
        assert await fake_storage.delete_object(key) is True

    @pytest.mark.anyio
    async def test_copy_object(self, fake_storage: FakeStorageAdapter):
        src_key = "staging/users/u-1/wardrobe/up-1.webp"
        dst_key = "users/u-1/wardrobe/item-1/promoted.webp"
        data = b"promoted-webp-bytes"

        fake_storage.put_object_bytes(
            src_key,
            data,
            content_type="image/webp",
            custom_metadata={"uploaded_by": "u-1"},
        )

        copy_meta = await fake_storage.copy_object(
            source_key=src_key,
            destination_key=dst_key,
            content_type="image/webp",
            custom_metadata={"promoted": "true"},
        )
        assert copy_meta.key == dst_key
        assert copy_meta.size_bytes == len(data)
        assert copy_meta.custom_metadata["promoted"] == "true"

        # Verify destination exists with correct data
        assert await fake_storage.object_exists(dst_key) is True
        assert await fake_storage.read_object(dst_key) == data

    @pytest.mark.anyio
    async def test_copy_missing_source_raises_not_found(
        self, fake_storage: FakeStorageAdapter
    ):
        with pytest.raises(StorageNotFoundError):
            await fake_storage.copy_object(
                source_key="non-existent-src.webp",
                destination_key="dst.webp",
            )

    @pytest.mark.anyio
    async def test_simulated_failure_injection(
        self, fake_storage: FakeStorageAdapter
    ):
        fake_storage.simulate_failure = StorageError("Custom simulated provider failure")

        with pytest.raises(StorageError) as excinfo:
            await fake_storage.object_exists("any-key")
        assert "Custom simulated provider failure" in str(excinfo.value)

    @pytest.mark.anyio
    async def test_simulated_timeout_injection(
        self, fake_storage: FakeStorageAdapter
    ):
        fake_storage.simulate_timeout = True

        with pytest.raises(StorageTimeoutError) as excinfo:
            await fake_storage.generate_presigned_put_url(
                key="test.webp", content_type="image/webp"
            )
        assert "Simulated storage operation timeout" in str(excinfo.value)

    @pytest.mark.anyio
    async def test_close_lifecycle(self, fake_storage: FakeStorageAdapter):
        assert fake_storage.is_closed is False
        await fake_storage.close()
        assert fake_storage.is_closed is True

    @pytest.mark.anyio
    async def test_put_object_successful_upload_and_metadata(
        self, fake_storage: FakeStorageAdapter
    ):
        data = b"RIFF1234WEBPVP8Xcanonical_image_bytes"
        key = "users/u-1/wardrobe/up-1/hash.webp"
        custom_meta = {"upload_id": "up-1", "user_id": "u-1"}

        meta = await fake_storage.put_object(
            key=key,
            data=data,
            content_type="image/webp",
            custom_metadata=custom_meta,
        )

        assert meta.key == key
        assert meta.size_bytes == len(data)
        assert meta.content_type == "image/webp"
        assert meta.custom_metadata == custom_meta
        assert meta.etag is not None
        assert await fake_storage.object_exists(key) is True
        assert await fake_storage.read_object(key) == data

    @pytest.mark.anyio
    async def test_put_object_overwrite_behavior(
        self, fake_storage: FakeStorageAdapter
    ):
        key = "users/u-1/wardrobe/up-1/hash.webp"
        data_v1 = b"original-bytes"
        data_v2 = b"overwritten-new-canonical-bytes"

        await fake_storage.put_object(key=key, data=data_v1, content_type="image/webp")
        assert await fake_storage.read_object(key) == data_v1

        meta_v2 = await fake_storage.put_object(
            key=key, data=data_v2, content_type="image/webp", custom_metadata={"version": "2"}
        )
        assert meta_v2.size_bytes == len(data_v2)
        assert meta_v2.custom_metadata["version"] == "2"
        assert await fake_storage.read_object(key) == data_v2

    @pytest.mark.anyio
    async def test_put_object_simulated_error(
        self, fake_storage: FakeStorageAdapter
    ):
        fake_storage.simulate_failure = StorageError("R2 disk full simulation")
        with pytest.raises(StorageError) as excinfo:
            await fake_storage.put_object(
                key="test.webp",
                data=b"some-bytes",
            )
        assert "R2 disk full simulation" in str(excinfo.value)

