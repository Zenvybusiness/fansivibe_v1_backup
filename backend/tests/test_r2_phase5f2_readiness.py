"""Phase 5F.2: Cloudflare R2 Provisioning Preparation & Isolated Readiness Tests.

Tests run strictly in isolation (real boto3 SigV4 signing + mocked S3 client / FakeStorageAdapter,
zero live Cloudflare R2 network calls, zero Genlook calls, zero paid infrastructure).

Covers all 10 Task 4 readiness areas plus Task 3 security/environment invariants:
1. Successful private image upload (put_object + object_exists + metadata + user-scoped key).
2. Image retrieval (read_object + get_object_stream + bounded max_bytes guard).
3. Signed GET URL generation (real boto3 SigV4 presigned URL, confirmed object_exists gate,
   zero log/DB persistence of signed URLs).
4. URL expiration (X-Amz-Expires validation, out-of-range TTL rejection, expired URL fetch error).
5. Object deletion (delete_object, idempotent NoSuchKey, delete_objects_safe sanitization,
   try-on delete_job_and_media & cleanup_retention_data).
6. Invalid credentials (InvalidAccessKeyId, SignatureDoesNotMatch, AccessDenied, NoCredentialsError,
   check_health unhealthy, zero secret leakage).
7. Missing bucket (NoSuchBucket mapped to StorageConfigurationError across operations + check_health).
8. Network failure (ConnectTimeoutError, ReadTimeoutError, EndpointConnectionError -> StorageTimeoutError).
9. Invalid image content (empty bytes, invalid MIME, corrupt/non-image/SVG payloads rejected before R2).
10. Storage errors during try-on completion (person upload failure -> 503, garment sign failure -> failed,
    result put_object failure / missing object_exists -> failed STORAGE_FAILURE, never completed).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import io
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    PartialCredentialsError,
    ReadTimeoutError,
)
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.api.deps import (
    get_current_user_id,
    get_storage_adapter,
    get_tryon_repository,
    get_tryon_wardrobe_repository,
)
from app.api.errors import _sanitize_log_message
import app.application.tryon as tryon_app
from app.config.settings import Settings, clear_settings_cache
from app.domain.ports.repositories import WardrobeItemRecord
from app.domain.ports.storage import (
    StorageConfigurationError,
    StorageError,
    StorageNotFoundError,
    StoragePayloadError,
    StoragePermissionError,
    StorageTimeoutError,
)
from app.infrastructure.external.genlook_tryon import GenlookTryOnProvider
from app.infrastructure.external.storage import (
    CloudflareR2StorageAdapter,
    get_default_storage_adapter,
    reset_default_storage_adapter,
    validate_scoped_object_key,
)
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter
from tests.test_tryon_phase5f_genlook import (
    MockGenlookServer,
    TEST_API_KEY,
    _WardrobeRepoStub,
    _genlook_settings,
)

USER_A = uuid4()
USER_B = uuid4()
REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_image_bytes(
    fmt: str = "JPEG",
    size: tuple[int, int] = (128, 128),
    color: tuple[int, int, int] = (70, 110, 170),
) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format=fmt)
    return buf.getvalue()


VALID_JPEG = _make_image_bytes("JPEG")
VALID_PNG = _make_image_bytes("PNG", color=(40, 140, 90))
VALID_WEBP = _make_image_bytes("WEBP", color=(180, 90, 50))


def _make_client_error(code: str, message: str, op: str = "S3Operation") -> ClientError:
    return ClientError(
        error_response={"Error": {"Code": code, "Message": message}},
        operation_name=op,
    )


def _make_r2_adapter(s3_client: MagicMock | None = None) -> CloudflareR2StorageAdapter:
    return CloudflareR2StorageAdapter(
        bucket_name="fansivibe-test-private",
        endpoint_url="https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
        access_key_id="r2_test_access_key_id_only",
        secret_access_key="r2_test_secret_access_key_never_logged",
        region_name="auto",
        s3_client=s3_client,
    )


@pytest.fixture(autouse=True)
def _reset_state():
    tryon_app.reset_for_tests()
    reset_default_storage_adapter()
    clear_settings_cache()
    yield
    app.dependency_overrides.clear()
    tryon_app.reset_for_tests()
    reset_default_storage_adapter()
    clear_settings_cache()


# ==============================================================================
# 1 & 2. Private Upload & Retrieval
# ==============================================================================


class TestR2PrivateUploadAndRetrieval:
    @pytest.mark.anyio
    async def test_successful_private_image_upload_and_metadata(self):
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {"ETag": '"etag-r2-img-1"'}
        mock_s3.head_object.return_value = {
            "ContentLength": len(VALID_WEBP),
            "ContentType": "image/webp",
            "ETag": '"etag-r2-img-1"',
            "Metadata": {"purpose": "tryon_result"},
        }
        adapter = _make_r2_adapter(mock_s3)
        key = f"users/{USER_A}/tryon/{uuid4()}/result.webp"
        validate_scoped_object_key(key, user_id=str(USER_A))

        meta = await adapter.put_object(
            key=key,
            data=VALID_WEBP,
            content_type="image/webp",
            custom_metadata={"purpose": "tryon_result"},
        )
        assert meta.key == key
        assert meta.size_bytes == len(VALID_WEBP)
        assert meta.content_type == "image/webp"
        assert meta.etag == "etag-r2-img-1"
        assert await adapter.object_exists(key) is True
        fetched_meta = await adapter.get_object_metadata(key)
        assert fetched_meta is not None
        assert fetched_meta.size_bytes == len(VALID_WEBP)
        assert fetched_meta.custom_metadata == {"purpose": "tryon_result"}

    @pytest.mark.anyio
    async def test_image_retrieval_streaming_and_read_object(self):
        mock_s3 = MagicMock()
        body = MagicMock()
        mid = len(VALID_PNG) // 2
        body.read.side_effect = [VALID_PNG[:mid], VALID_PNG[mid:], b""]
        mock_s3.get_object.return_value = {"Body": body}
        adapter = _make_r2_adapter(mock_s3)

        key = f"users/{USER_A}/wardrobe/{uuid4()}/canonical.png"
        retrieved = await adapter.read_object(key, max_bytes=1024 * 1024)
        assert retrieved == VALID_PNG
        body.close.assert_called_once()

        body_stream = MagicMock()
        body_stream.read.side_effect = [VALID_JPEG, b""]
        mock_s3.get_object.return_value = {"Body": body_stream}
        chunks = [c async for c in adapter.get_object_stream(key, chunk_size=65536)]
        assert b"".join(chunks) == VALID_JPEG
        body_stream.close.assert_called_once()

    @pytest.mark.anyio
    async def test_cross_user_key_scoping_rejected(self):
        key_a = f"users/{USER_A}/tryon/{uuid4()}/person.jpg"
        with pytest.raises(StoragePermissionError):
            validate_scoped_object_key(key_a, user_id=str(USER_B))


# ==============================================================================
# 3 & 4. Signed GET URL Generation & Expiration (Real Boto3 SigV4 Signing)
# ==============================================================================


class TestR2SignedGetUrlAndExpiration:
    @pytest.mark.anyio
    async def test_real_sigv4_presigned_get_url_generation_with_zero_network(self):
        # Use real boto3 client (no s3_client mock) to validate real R2 SigV4 URL generation
        with patch("socket.socket.connect") as mock_sock:
            adapter = _make_r2_adapter(s3_client=None)
            key = f"users/{USER_A}/wardrobe/{uuid4()}/garment.webp"
            url = await adapter.generate_presigned_get_url(
                key=key,
                expires_in_s=300,
                response_content_type="image/webp",
            )
            mock_sock.assert_not_called()

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        assert parsed.scheme == "https"
        assert parsed.netloc == "0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"
        assert parsed.path == f"/fansivibe-test-private/{key}"
        assert qs["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
        assert qs["X-Amz-Expires"] == ["300"]
        assert "X-Amz-Signature" in qs and len(qs["X-Amz-Signature"][0]) == 64
        assert "r2_test_secret_access_key_never_logged" not in url

    @pytest.mark.anyio
    async def test_confirmed_presigned_url_requires_existing_object_and_is_not_logged(
        self, caplog
    ):
        mock_s3 = MagicMock()
        mock_s3.head_object.side_effect = _make_client_error("404", "Not Found", "HeadObject")
        adapter = _make_r2_adapter(mock_s3)
        key = f"users/{USER_A}/wardrobe/{uuid4()}/garment.webp"

        with pytest.raises(StorageNotFoundError):
            await tryon_app.create_confirmed_presigned_input_url(
                storage=adapter, key=key, expires_in_s=300
            )

        # Now confirm object exists and sign with a real SigV4 client
        real_adapter = _make_r2_adapter(s3_client=None)
        with patch.object(real_adapter, "object_exists", return_value=True):
            with caplog.at_level(logging.DEBUG):
                signed_url = await tryon_app.create_confirmed_presigned_input_url(
                    storage=real_adapter, key=key, expires_in_s=300
                )
        assert "X-Amz-Signature=" in signed_url
        assert "X-Amz-Signature=" not in caplog.text

    @pytest.mark.anyio
    async def test_url_expiration_bounds_and_expired_fetch_handling(self):
        adapter = _make_r2_adapter(s3_client=None)
        key = f"users/{USER_A}/wardrobe/{uuid4()}/garment.webp"

        # Invalid TTLs fail closed
        for bad_ttl in (0, -10, 604801):
            with pytest.raises(StoragePayloadError, match="expiration"):
                await adapter.generate_presigned_get_url(key=key, expires_in_s=bad_ttl)
            with pytest.raises(StoragePayloadError, match="expiration"):
                await adapter.generate_presigned_put_url(
                    key=key, content_type="image/webp", expires_in_s=bad_ttl
                )

        # Verify distinct TTLs are encoded accurately into SigV4 query parameter
        url_60 = await adapter.generate_presigned_get_url(key=key, expires_in_s=60)
        url_900 = await adapter.generate_presigned_get_url(key=key, expires_in_s=900)
        assert parse_qs(urlparse(url_60).query)["X-Amz-Expires"] == ["60"]
        assert parse_qs(urlparse(url_900).query)["X-Amz-Expires"] == ["900"]

        # Simulate R2 rejecting an expired presigned GET (AccessDenied / ExpiredRequest)
        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = _make_client_error(
            "AccessDenied", "Request has expired", "GetObject"
        )
        err_adapter = _make_r2_adapter(mock_s3)
        with pytest.raises(StoragePermissionError):
            await err_adapter.read_object(key)


# ==============================================================================
# 5. Object Deletion & Retention
# ==============================================================================


class TestR2DeletionAndRetention:
    @pytest.mark.anyio
    async def test_delete_object_idempotent_and_safe_batch_sanitized(self, caplog):
        mock_s3 = MagicMock()
        mock_s3.delete_object.side_effect = [
            {},
            _make_client_error("NoSuchKey", "Not found", "DeleteObject"),
            _make_client_error(
                "AccessDenied",
                "Denied for https://r2.test?X-Amz-Signature=deadbeefcafebabe1234",
                "DeleteObject",
            ),
        ]
        adapter = _make_r2_adapter(mock_s3)
        k1 = f"users/{USER_A}/tryon/j1/person.jpg"
        k2 = f"users/{USER_A}/tryon/j1/missing.jpg"
        k3 = f"users/{USER_A}/tryon/j1/denied.jpg"

        assert await adapter.delete_object(k1) is True
        assert await adapter.delete_object(k2) is True  # NoSuchKey is idempotent

        with caplog.at_level(logging.WARNING):
            succeeded, failed = await adapter.delete_objects_safe([k3])
        assert succeeded == []
        assert failed == [k3]
        assert "deadbeefcafebabe1234" not in caplog.text

    @pytest.mark.anyio
    async def test_tryon_delete_and_retention_cleanup_remove_r2_objects(self):
        mock_s3 = MagicMock()
        mock_s3.delete_object.return_value = {}
        adapter = _make_r2_adapter(mock_s3)
        repo = tryon_app._IN_MEMORY_REPO

        job_id = uuid4()
        p_key = f"users/{USER_A}/tryon/{job_id}/person.jpg"
        r_key = f"users/{USER_A}/tryon/{job_id}/result.png"
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=[str(uuid4())],
            provider="genlook",
            status="processing",
            consent_version="tryon-v1",
            consent_accepted_at=old_time,
            person_media_ref={"key": p_key},
        )
        repo.update_result(
            job_id=job_id,
            result_media_ref={"key": r_key, "mediaType": "image/png"},
            completed_at=old_time,
        )
        # Backdate created_at for retention cutoff test
        repo._jobs[job_id] = tryon_app.TryOnJobRecord(
            **{**repo._jobs[job_id].__dict__, "created_at": old_time, "updated_at": old_time}
        )

        summary = await tryon_app.cleanup_retention_data(job_repo=repo, storage=adapter)
        assert summary.person_photos_purged == 1
        assert summary.storage_objects_deleted == 1
        mock_s3.delete_object.assert_called_once_with(
            Bucket="fansivibe-test-private", Key=p_key
        )

        mock_s3.reset_mock()
        deleted = await tryon_app.delete_job_and_media(
            user_id=str(USER_A), job_id=str(job_id), job_repo=repo, storage=adapter
        )
        assert deleted is True
        mock_s3.delete_object.assert_called_once_with(
            Bucket="fansivibe-test-private", Key=r_key
        )


# ==============================================================================
# 6, 7, 8. Invalid Credentials, Missing Bucket & Network Failures
# ==============================================================================


class TestR2FailureModes:
    @pytest.mark.anyio
    @pytest.mark.parametrize("error_code", ["InvalidAccessKeyId", "SignatureDoesNotMatch", "AccessDenied"])
    async def test_invalid_credentials_mapped_and_redacted(self, error_code):
        mock_s3 = MagicMock()
        raw_msg = (
            f"{error_code}: https://r2.test/key?X-Amz-Signature=99887766aabbccdd"
            "&X-Amz-Credential=r2_test_access_key_id_only/20261125/auto/s3/aws4_request"
        )
        mock_s3.put_object.side_effect = _make_client_error(error_code, raw_msg, "PutObject")
        mock_s3.head_bucket.side_effect = _make_client_error(error_code, raw_msg, "HeadBucket")
        adapter = _make_r2_adapter(mock_s3)

        with pytest.raises(StoragePermissionError) as exc_info:
            await adapter.put_object(f"users/{USER_A}/tryon/j1/person.jpg", VALID_JPEG, content_type="image/jpeg")
        assert "99887766aabbccdd" not in repr(exc_info.value)
        assert "r2_test_secret_access_key_never_logged" not in repr(exc_info.value)

        health = await adapter.check_health()
        assert health["status"] == "unhealthy"
        assert health["error_code"] == error_code
        assert "r2_test_secret_access_key_never_logged" not in str(health)

    @pytest.mark.anyio
    @pytest.mark.parametrize("exc", [NoCredentialsError(), PartialCredentialsError(provider="env", cred_var="AWS_SECRET")])
    async def test_botocore_missing_credentials_mapped_to_permission_error(self, exc):
        mock_s3 = MagicMock()
        mock_s3.get_object.side_effect = exc
        adapter = _make_r2_adapter(mock_s3)
        with pytest.raises(StoragePermissionError):
            await adapter.read_object(f"users/{USER_A}/tryon/j1/person.jpg")

    @pytest.mark.anyio
    async def test_missing_bucket_mapped_to_configuration_error_and_unhealthy_health(self):
        mock_s3 = MagicMock()
        err = _make_client_error("NoSuchBucket", "The specified bucket does not exist.", "PutObject")
        mock_s3.put_object.side_effect = err
        mock_s3.get_object.side_effect = err
        mock_s3.head_object.side_effect = err
        mock_s3.delete_object.side_effect = err
        mock_s3.head_bucket.side_effect = err
        adapter = _make_r2_adapter(mock_s3)
        key = f"users/{USER_A}/tryon/j1/person.jpg"

        with pytest.raises(StorageConfigurationError, match="bucket does not exist"):
            await adapter.put_object(key, VALID_JPEG, content_type="image/jpeg")
        with pytest.raises(StorageConfigurationError):
            await adapter.read_object(key)
        with pytest.raises(StorageConfigurationError):
            await adapter.get_object_metadata(key)
        with pytest.raises(StorageConfigurationError):
            await adapter.delete_object(key)

        health = await adapter.check_health()
        assert health["status"] == "unhealthy"
        assert health["error_code"] == "NoSuchBucket"

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "net_exc",
        [
            ConnectTimeoutError(endpoint_url="https://acc.r2.cloudflarestorage.com"),
            ReadTimeoutError(endpoint_url="https://acc.r2.cloudflarestorage.com"),
            EndpointConnectionError(endpoint_url="https://acc.r2.cloudflarestorage.com"),
        ],
    )
    async def test_network_failures_mapped_to_timeout_error_and_unavailable_health(self, net_exc):
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = net_exc
        mock_s3.get_object.side_effect = net_exc
        mock_s3.head_bucket.side_effect = net_exc
        adapter = _make_r2_adapter(mock_s3)
        key = f"users/{USER_A}/tryon/j1/person.jpg"

        with pytest.raises(StorageTimeoutError):
            await adapter.put_object(key, VALID_JPEG, content_type="image/jpeg")
        with pytest.raises(StorageTimeoutError):
            await adapter.read_object(key)

        health = await adapter.check_health()
        assert health["status"] == "unavailable"
        assert health["error"] == type(net_exc).__name__


# ==============================================================================
# 9. Invalid Image Content
# ==============================================================================


class TestR2InvalidImageContent:
    @pytest.mark.anyio
    async def test_empty_payload_and_unsupported_mime_rejected_by_r2_adapter(self):
        adapter = _make_r2_adapter(MagicMock())
        key = f"users/{USER_A}/tryon/{uuid4()}/person.jpg"

        with pytest.raises(StoragePayloadError, match="empty"):
            await adapter.put_object(key, b"", content_type="image/jpeg")

        with pytest.raises(StoragePayloadError, match="Unsupported content_type"):
            await adapter.put_object(key, b"<html>bad</html>", content_type="text/html")

        with pytest.raises(StoragePayloadError, match="Unsupported content_type"):
            await adapter.generate_presigned_put_url(key=key, content_type="application/pdf")

    def test_corrupt_and_disguised_person_image_rejected_before_storage_write(self):
        storage = FakeStorageAdapter()
        app.dependency_overrides[get_storage_adapter] = lambda: storage
        app.dependency_overrides[get_tryon_repository] = lambda: tryon_app._IN_MEMORY_REPO
        app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: _WardrobeRepoStub()
        app.dependency_overrides[get_current_user_id] = lambda: USER_A

        client = TestClient(app)
        for idx, (payload, mime) in enumerate(
            [
                (b"not-an-image", "image/jpeg"),
                (VALID_PNG, "image/jpeg"),  # MIME spoofing
                (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/png"),
            ]
        ):
            resp = client.post(
                "/v1/tryon/jobs",
                files={"person_image": (f"bad_{idx}.jpg", payload, mime)},
                data={
                    "outfit_source": "today",
                    "garment_ids": '["g-1"]',
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": f"invalid-img-{idx}"},
            )
            assert resp.status_code == 422
        assert storage.get_stored_keys() == []


# ==============================================================================
# 10. Storage Errors During Try-On Completion
# ==============================================================================


class TestR2StorageErrorsDuringTryOnCompletion:
    def _setup_genlook_job(self, monkeypatch, storage, *, server: MockGenlookServer):
        repo = tryon_app._IN_MEMORY_REPO
        wardrobe_repo = _WardrobeRepoStub()
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(storage.put_object(item.image_ref["key"], VALID_WEBP, content_type="image/webp"))

        job_id = uuid4()
        person_key = f"users/{USER_A}/tryon/{job_id}/person.jpg"
        asyncio.run(storage.put_object(person_key, VALID_JPEG, content_type="image/jpeg"))

        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=gid,
            garment_ids=[str(gid)],
            provider="genlook",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
            person_media_ref={"key": person_key, "contentHash": "person-hash-1"},
        )

        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)
        monkeypatch.setattr(tryon_app, "get_settings", lambda: _genlook_settings())
        return repo, wardrobe_repo, job_id

    def test_result_put_object_failure_marks_job_failed_never_completed(self, monkeypatch):
        class _FailResultPutStorage(FakeStorageAdapter):
            async def put_object(self, key: str, data: bytes, *, content_type: str = "image/webp", custom_metadata=None):
                if "/result." in key:
                    raise StorageTimeoutError("R2 PutObject timed out during completion", key=key)
                return await super().put_object(key, data, content_type=content_type, custom_metadata=custom_metadata)

        storage = _FailResultPutStorage()
        server = MockGenlookServer(initial_credits=5, result_bytes=VALID_PNG)
        repo, wardrobe_repo, job_id = self._setup_genlook_job(monkeypatch, storage, server=server)

        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=USER_A,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=wardrobe_repo,
            )
        )

        job = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error_code == "STORAGE_FAILURE"
        assert job.result_media_ref is None
        assert repo.get_image_bytes(job_id) is None

        app.dependency_overrides[get_current_user_id] = lambda: USER_A
        app.dependency_overrides[get_tryon_repository] = lambda: repo
        app.dependency_overrides[get_storage_adapter] = lambda: storage
        img_resp = TestClient(app).get(f"/v1/tryon/jobs/{job_id}/image")
        assert img_resp.status_code == 409

    def test_result_missing_durability_confirmation_marks_job_failed(self, monkeypatch):
        class _UnconfirmedResultPutStorage(FakeStorageAdapter):
            async def object_exists(self, key: str) -> bool:
                if "/result." in key:
                    return False
                return await super().object_exists(key)

        storage = _UnconfirmedResultPutStorage()
        server = MockGenlookServer(initial_credits=5, result_bytes=VALID_PNG)
        repo, wardrobe_repo, job_id = self._setup_genlook_job(monkeypatch, storage, server=server)

        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=USER_A,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=wardrobe_repo,
            )
        )

        job = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error_code == "STORAGE_FAILURE"
        assert job.result_media_ref is None

    def test_garment_signing_failure_aborts_before_calling_genlook(self, monkeypatch):
        class _FailSignStorage(FakeStorageAdapter):
            async def generate_presigned_get_url(self, *, key: str, expires_in_s: int = 900, **kw) -> str:
                raise StoragePermissionError("R2 signing denied", key=key)

        storage = _FailSignStorage()
        server = MockGenlookServer(initial_credits=5, result_bytes=VALID_PNG)
        repo, wardrobe_repo, job_id = self._setup_genlook_job(monkeypatch, storage, server=server)

        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=USER_A,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=wardrobe_repo,
            )
        )

        job = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert job is not None
        assert job.status == "failed"
        assert job.error_code == "STORAGE_FAILURE"
        assert server.calls == []
        assert server.credits == 5


# ==============================================================================
# Task 3. Security, Environment & Singleton Invariants
# ==============================================================================


class TestR2EnvironmentAndSecurityInvariants:
    def test_defaults_remain_fake_storage_and_mock_vton(self):
        s = Settings(_env_file=None)
        assert s.media_storage_provider == "fake"
        assert s.tryon_provider == "mock"

    def test_env_ignored_and_env_example_has_placeholders_only(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert ".env" in gitignore.splitlines()
        assert ".env.*" in gitignore.splitlines()

        env_example = (REPO_ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
        kv: dict[str, str] = {}
        for line in env_example.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            k, v = stripped.split("=", 1)
            kv[k.strip()] = v.strip()

        assert kv["MEDIA_STORAGE_PROVIDER"] == "fake"
        assert kv["FANSIVIBE_TRYON_PROVIDER"] == "mock"
        for empty_key in (
            "R2_ACCOUNT_ID",
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME",
            "R2_ENDPOINT_URL",
            "GENLOOK_API_KEY",
        ):
            assert kv[empty_key] == ""

    def test_flutter_lib_contains_zero_r2_or_genlook_credentials(self):
        flutter_lib = REPO_ROOT / "newproject" / "flutter_application_1" / "lib"
        forbidden = (
            "R2_ACCESS_KEY_ID",
            "R2_SECRET_ACCESS_KEY",
            "R2_ACCOUNT_ID",
            "r2.cloudflarestorage.com",
            "GENLOOK_API_KEY",
        )
        for dart_file in flutter_lib.rglob("*.dart"):
            text = dart_file.read_text(encoding="utf-8", errors="ignore")
            for token in forbidden:
                assert token not in text, f"Forbidden secret/token {token!r} found in {dart_file}"

    def test_error_log_sanitizer_scrubs_sigv4_presigned_urls(self):
        raw = (
            "GET https://acc.r2.cloudflarestorage.com/b/k?X-Amz-Algorithm=AWS4-HMAC-SHA256"
            "&X-Amz-Credential=key123%2F20261125%2Fauto%2Fs3%2Faws4_request"
            "&X-Amz-Signature=deadbeef1234567890&X-Amz-Security-Token=tok999"
        )
        scrubbed = _sanitize_log_message(raw)
        assert "deadbeef1234567890" not in scrubbed
        assert "key123" not in scrubbed
        assert "tok999" not in scrubbed
        assert "X-Amz-Signature=[REDACTED]" in scrubbed

    def test_default_storage_adapter_recreates_when_credentials_rotate(self, monkeypatch):
        monkeypatch.setenv("MEDIA_STORAGE_PROVIDER", "r2")
        monkeypatch.setenv("R2_BUCKET_NAME", "bucket-rot")
        monkeypatch.setenv("R2_ACCOUNT_ID", "acct-rot")
        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key-v1")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sec-v1")
        clear_settings_cache()
        a1 = get_default_storage_adapter(Settings(_env_file=None))

        monkeypatch.setenv("R2_ACCESS_KEY_ID", "key-v2")
        monkeypatch.setenv("R2_SECRET_ACCESS_KEY", "sec-v2")
        clear_settings_cache()
        a2 = get_default_storage_adapter(Settings(_env_file=None))
        assert a1 is not a2

    def test_tryon_health_does_not_leak_raw_exception_string(self, monkeypatch):
        class _ExplodingStorage(FakeStorageAdapter):
            async def check_health(self):
                raise RuntimeError("secret-leak-X-Amz-Signature=badsecret")

        monkeypatch.setenv("FANSIVIBE_OPERATOR_API_KEY", "test-operator-health-key-32chars-min")
        clear_settings_cache()
        try:
            app.dependency_overrides[get_storage_adapter] = lambda: _ExplodingStorage()
            unauth = TestClient(app).get("/v1/tryon/health")
            assert unauth.status_code == 401
            assert "badsecret" not in unauth.text

            resp = TestClient(app).get(
                "/v1/tryon/health",
                headers={"X-Operator-Key": "test-operator-health-key-32chars-min"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "degraded"
            assert body["storage"]["status"] == "unavailable"
            assert body["storage"]["error"] == "RuntimeError"
            assert "badsecret" not in resp.text
        finally:
            clear_settings_cache()


# ==============================================================================
# Task 4. Isolated Verification of Live R2 Probe Script (No Live R2 / Genlook)
# ==============================================================================


class TestR2LiveProbeScript:
    @pytest.mark.anyio
    async def test_live_probe_reports_blocked_when_r2_not_configured(self):
        from scripts.verify_r2_live import run_live_r2_probe

        s = Settings(_env_file=None, media_storage_provider="fake")
        res = await run_live_r2_probe(settings=s)
        assert res.status == "BLOCKED"
        assert res.exit_code == 2
        assert "MEDIA_STORAGE_PROVIDER=r2" in res.missing_fields

    @pytest.mark.anyio
    async def test_live_probe_roundtrip_passes_and_redacts_secrets_with_mocked_transport(
        self, capsys
    ):
        import httpx
        from scripts.verify_r2_live import _verify_signed_url_expiration_config, run_live_r2_probe

        store: dict[str, tuple[bytes, str]] = {}
        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}

        def _put_obj(**kw):
            store[kw["Key"]] = (kw["Body"], kw.get("ContentType", "image/webp"))
            return {"ETag": '"probe-etag"'}

        def _head_obj(**kw):
            key = kw["Key"]
            if key not in store:
                raise _make_client_error("404", "Not Found", "HeadObject")
            data, ct = store[key]
            return {"ContentLength": len(data), "ContentType": ct, "ETag": '"probe-etag"'}

        def _del_obj(**kw):
            store.pop(kw["Key"], None)
            return {}

        mock_s3.put_object.side_effect = _put_obj
        mock_s3.head_object.side_effect = _head_obj
        mock_s3.delete_object.side_effect = _del_obj

        # Delegate generate_presigned_url to a real boto3 S3 signer so SigV4 URLs are authentic
        real_adapter = _make_r2_adapter(s3_client=None)
        mock_s3.generate_presigned_url.side_effect = real_adapter._client.generate_presigned_url

        adapter = _make_r2_adapter(mock_s3)
        s = Settings(
            _env_file=None,
            media_storage_provider="r2",
            r2_bucket_name="fansivibe-test-private",
            r2_account_id="0123456789abcdef0123456789abcdef",
            r2_access_key_id="r2_test_access_key_id_only",
            r2_secret_access_key="r2_test_secret_access_key_never_logged",
        )

        def _fake_http_get(url: str) -> httpx.Response:
            parsed = urlparse(url)
            key = parsed.path.removeprefix("/fansivibe-test-private/")
            if "X-Amz-Signature=" not in parsed.query:
                return httpx.Response(403, content=b"AccessDenied")
            _verify_signed_url_expiration_config(
                url,
                expected_ttl_s=60,
                expected_bucket="fansivibe-test-private",
                expected_key=key,
            )
            if key not in store:
                return httpx.Response(404, content=b"NoSuchKey")
            return httpx.Response(200, content=store[key][0])

        res = await run_live_r2_probe(settings=s, adapter=adapter, http_get=_fake_http_get)
        captured = capsys.readouterr()
        assert res.status == "PASS"
        assert res.exit_code == 0
        assert res.unsigned_status_code == 403
        assert res.signed_status_code == 200
        assert res.post_delete_status_code == 404
        assert store == {}
        assert "r2_test_secret_access_key_never_logged" not in str(res)
        assert "X-Amz-Signature" not in captured.out


class TestR2ExpiryVerificationScript:
    @pytest.mark.anyio
    async def test_expiry_script_reports_blocked_without_r2_config(self):
        from scripts.verify_r2_expiry import run_signed_url_expiry_verification

        s = Settings(_env_file=None, media_storage_provider="fake")
        res = await run_signed_url_expiry_verification(settings=s)
        assert res.status == "BLOCKED"
        assert res.exit_code == 2

    @pytest.mark.anyio
    async def test_expiry_script_verifies_pre_200_post_403_and_cleanup(self):
        import httpx
        from scripts.verify_r2_expiry import run_signed_url_expiry_verification

        store: dict[str, tuple[bytes, str]] = {}
        mock_s3 = MagicMock()

        def _put_obj(**kw):
            store[kw["Key"]] = (kw["Body"], kw.get("ContentType", "image/webp"))
            return {"ETag": '"exp-etag"'}

        def _head_obj(**kw):
            key = kw["Key"]
            if key not in store:
                raise _make_client_error("404", "Not Found", "HeadObject")
            data, ct = store[key]
            return {"ContentLength": len(data), "ContentType": ct, "ETag": '"exp-etag"'}

        def _del_obj(**kw):
            store.pop(kw["Key"], None)
            return {}

        mock_s3.put_object.side_effect = _put_obj
        mock_s3.head_object.side_effect = _head_obj
        mock_s3.delete_object.side_effect = _del_obj
        real_adapter = _make_r2_adapter(s3_client=None)
        mock_s3.generate_presigned_url.side_effect = real_adapter._client.generate_presigned_url

        adapter = _make_r2_adapter(mock_s3)
        s = Settings(
            _env_file=None,
            media_storage_provider="r2",
            r2_bucket_name="fansivibe-test-private",
            r2_account_id="0123456789abcdef0123456789abcdef",
            r2_access_key_id="r2_test_access_key_id_only",
            r2_secret_access_key="r2_test_secret_access_key_never_logged",
        )

        calls = {"n": 0}

        def _fake_http_get(url: str) -> httpx.Response:
            calls["n"] += 1
            parsed = urlparse(url)
            key = parsed.path.removeprefix("/fansivibe-test-private/")
            if calls["n"] == 1:
                return httpx.Response(200, content=store[key][0])
            return httpx.Response(
                403,
                content=b"<Error><Code>ExpiredRequest</Code><Message>Request has expired</Message></Error>",
            )

        res = await run_signed_url_expiry_verification(
            settings=s,
            adapter=adapter,
            http_get=_fake_http_get,
            ttl_s=3,
            wait_margin_s=0.0,
            sleep_fn=lambda _secs: None,
        )
        assert res.status == "PASS"
        assert res.exit_code == 0
        assert res.pre_expiry_status_code == 200
        assert res.post_expiry_status_code == 403
        assert res.rejection_error_code == "ExpiredRequest"
        assert res.cleanup_verified is True
        assert store == {}
        assert "X-Amz-Signature" not in str(res)
        assert "r2_test_secret_access_key_never_logged" not in str(res)
