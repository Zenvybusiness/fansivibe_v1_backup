"""Phase 5F: Genlook Commercial VTON API Integration Tests.

Uses a mocked Genlook HTTP service (zero live network calls, zero credit spend)
to test all Genlook integration invariants:
- API key authentication (x-api-key header, non-leakage on result CDN URLs, 401/403, fail-closed missing key)
- Person image upload (POST /images/upload multipart file, MIME/size <= 10MB validation, imageId persistence & safe reuse)
- Try-on creation payload (official products/person schema, no invented category field, 1 garment, signed product URL)
- Polling & terminal states (PENDING -> PROCESSING -> COMPLETED, RUNNING, FAILED, cancellation)
- Timeouts, HTTP 4xx/5xx, 402 insufficient credits, 429 rate limiting with Retry-After
- Duplicate generation prevention (Idempotency-Key replay on POST /try-on + generationId resume on retry/restart)
- Result download & validation, private storage persistence + object_exists confirmation, no temp URL stored
- OW-1 user isolation (job, garment, imageId reuse)
- Restart recovery & secret non-leakage in logs, errors, health endpoint, and Settings repr
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import io
import json
import logging
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.api.deps import (
    get_current_user_id,
    get_storage_adapter,
    get_tryon_repository,
    get_tryon_wardrobe_repository,
)
import app.application.tryon as tryon_app
from app.config.settings import Settings, clear_settings_cache
from app.domain.ports.repositories import TryOnJobRecord, WardrobeItemRecord
from app.domain.ports.tryon_provider import (
    CommercialProviderConfigurationError,
    ProviderAuthError,
    ProviderPayloadError,
    ProviderQuotaExceededError,
    ProviderTransientError,
    TryOnProvider,
)
from app.infrastructure.external.genlook_tryon import (
    GENLOOK_MAX_IMAGE_BYTES,
    GenlookTryOnConfig,
    GenlookTryOnProvider,
    build_genlook_product_spec,
)
from app.main import app
from tests.fakes.fake_storage import FakeStorageAdapter

USER_A = uuid4()
USER_B = uuid4()
TEST_API_KEY = "gk_test_secret_genlook_key_9876543210"


def _make_image_bytes(
    fmt: str = "JPEG",
    size: tuple[int, int] = (128, 128),
    color: tuple[int, int, int] = (80, 120, 180),
) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format=fmt)
    return buf.getvalue()


VALID_JPEG = _make_image_bytes("JPEG")
VALID_PNG = _make_image_bytes("PNG", color=(30, 150, 90))
VALID_WEBP = _make_image_bytes("WEBP", color=(200, 90, 40))


class _WardrobeRepoStub:
    def __init__(self) -> None:
        self.items: dict[tuple[UUID, UUID], WardrobeItemRecord] = {}

    def add(
        self,
        user_id: UUID,
        item_id: UUID,
        *,
        name: str = "Navy Linen Shirt",
        category: str = "tops",
        color: str = "navy",
        material: str | None = "linen",
        fit: str | None = "relaxed",
        image_ref: dict[str, Any] | None = None,
    ) -> WardrobeItemRecord:
        now = datetime.now(timezone.utc)
        rec = WardrobeItemRecord(
            id=item_id,
            user_id=user_id,
            name=name,
            category=category,
            color=color,
            material=material,
            is_favorite=False,
            image_ref=image_ref
            if image_ref is not None
            else {"key": f"users/{user_id}/wardrobe/{item_id}/garment.webp"},
            created_at=now,
            updated_at=now,
            fit=fit,
        )
        self.items[(user_id, item_id)] = rec
        return rec

    def get_by_id(self, *, user_id: UUID, item_id: UUID) -> WardrobeItemRecord | None:
        return self.items.get((user_id, item_id))


class MockResponse:
    def __init__(
        self,
        status_code: int,
        json_body: Any = None,
        *,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json = json_body
        self.headers = headers or {}
        if content is not None:
            self.content = content
        elif json_body is not None:
            self.content = json.dumps(json_body).encode("utf-8")
        else:
            self.content = b""

    def json(self) -> Any:
        if self._json is None:
            raise ValueError("No JSON body")
        return self._json


class MockGenlookServer:
    """In-memory mock of Genlook Try-On API v1 endpoints & CDN result downloads."""

    def __init__(
        self,
        *,
        valid_api_key: str = TEST_API_KEY,
        initial_credits: int = 10,
        result_bytes: bytes = VALID_PNG,
    ) -> None:
        self.valid_api_key = valid_api_key
        self.credits = initial_credits
        self.result_bytes = result_bytes
        self.uploads: dict[str, dict[str, Any]] = {}
        self.generations: dict[str, dict[str, Any]] = {}
        self.idempotency_map: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []
        self.poll_sequences: dict[str, list[dict[str, Any]]] = {}
        self.next_upload_responses: list[Any] = []
        self.next_tryon_responses: list[Any] = []
        self.next_poll_responses: list[Any] = []
        self.next_download_responses: list[Any] = []
        self.next_delete_responses: list[Any] = []
        self.deleted_customers: list[str] = []
        self.upload_counter = 0
        self.gen_counter = 0

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: Any = None,
        files: Any = None,
        data: Any = None,
        json: Any = None,
    ) -> MockResponse:
        headers = headers or {}
        self.calls.append(
            {
                "method": "POST",
                "url": url,
                "headers": dict(headers),
                "files": files,
                "data": dict(data) if isinstance(data, dict) else data,
                "json": json,
            }
        )

        # Auth check
        api_key = headers.get("x-api-key")
        if not api_key:
            return MockResponse(401, {"code": "MISSING_API_KEY", "message": "Missing x-api-key", "status": 401})
        if api_key != self.valid_api_key:
            return MockResponse(401, {"code": "INVALID_API_KEY", "message": "Invalid API key", "status": 401})

        if url.endswith("/images/upload"):
            if self.next_upload_responses:
                nxt = self.next_upload_responses.pop(0)
                if isinstance(nxt, Exception):
                    raise nxt
                return nxt
            self.upload_counter += 1
            image_id = f"ephemeral/customer/ttl-1d/acc_test/img_{self.upload_counter}.jpeg"
            self.uploads[image_id] = {"files": files, "data": data}
            return MockResponse(
                201,
                {
                    "imageId": image_id,
                    "imageUrl": f"https://storage.googleapis.com/genlook-tmp/{image_id}",
                },
                headers={"x-request-id": f"req-up-{self.upload_counter}"},
            )

        if url.endswith("/try-on"):
            if self.next_tryon_responses:
                nxt = self.next_tryon_responses.pop(0)
                if isinstance(nxt, Exception):
                    raise nxt
                return nxt

            idem_key = headers.get("Idempotency-Key")
            if idem_key and idem_key in self.idempotency_map:
                existing_gid = self.idempotency_map[idem_key]
                existing = self.generations[existing_gid]
                return MockResponse(
                    201,
                    {
                        "generationId": existing_gid,
                        "status": "PENDING",
                        "productExternalIds": existing["productExternalIds"],
                    },
                    headers={
                        "x-request-id": f"req-idem-{existing_gid}",
                        "Idempotency-Replayed": "true",
                        "X-RateLimit-Limit": "20",
                        "X-RateLimit-Remaining": "19",
                    },
                )

            if self.credits <= 0:
                return MockResponse(
                    402,
                    {
                        "code": "INSUFFICIENT_CREDITS",
                        "message": "Balance is 0.",
                        "status": 402,
                    },
                )

            person_id = (((json or {}).get("person") or {}).get("image") or {}).get("source", {}).get("id")
            if person_id not in self.uploads:
                return MockResponse(
                    404,
                    {
                        "code": "CUSTOMER_IMAGE_NOT_FOUND",
                        "message": "Customer image expired or missing.",
                        "status": 404,
                    },
                )

            self.credits -= 1
            self.gen_counter += 1
            gid = f"cm8gen_{self.gen_counter}"
            ext_ids = [p.get("externalId", "one-shot") for p in (json or {}).get("products", [])]
            self.generations[gid] = {
                "status": "PENDING",
                "productExternalIds": ext_ids,
                "payload": json,
            }
            if idem_key:
                self.idempotency_map[idem_key] = gid
            if gid not in self.poll_sequences:
                self.poll_sequences[gid] = [
                    {"status": "PENDING"},
                    {"status": "PROCESSING"},
                    {
                        "status": "COMPLETED",
                        "resultImageUrl": f"https://cdn.genlook-results.example/{gid}/out.png",
                    },
                ]
            return MockResponse(
                201,
                {
                    "generationId": gid,
                    "status": "PENDING",
                    "productExternalIds": ext_ids,
                },
                headers={
                    "x-request-id": f"req-tryon-{self.gen_counter}",
                    "X-RateLimit-Limit": "20",
                    "X-RateLimit-Remaining": "19",
                },
            )

        return MockResponse(404, {"code": "ROUTE_NOT_FOUND", "message": "Unknown path", "status": 404})

    def delete(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: Any = None,
    ) -> MockResponse:
        headers = headers or {}
        self.calls.append({"method": "DELETE", "url": url, "headers": dict(headers)})

        if self.next_delete_responses:
            nxt = self.next_delete_responses.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt

        api_key = headers.get("x-api-key")
        if api_key != self.valid_api_key:
            return MockResponse(401, {"code": "INVALID_API_KEY", "message": "Invalid API key", "status": 401})

        if "/customers/" in url:
            ext_uid = url.rsplit("/customers/", 1)[1]
            self.deleted_customers.append(ext_uid)
            return MockResponse(204)

        return MockResponse(404, {"code": "ROUTE_NOT_FOUND", "message": "Unknown path", "status": 404})

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: Any = None,
    ) -> MockResponse:
        headers = headers or {}
        self.calls.append({"method": "GET", "url": url, "headers": dict(headers)})

        # Result image CDN URL (must NOT receive x-api-key)
        if url.startswith("https://cdn.genlook-results.example/"):
            if self.next_download_responses:
                nxt = self.next_download_responses.pop(0)
                if isinstance(nxt, Exception):
                    raise nxt
                return nxt
            return MockResponse(
                200,
                content=self.result_bytes,
                headers={"content-type": "image/png"},
            )

        api_key = headers.get("x-api-key")
        if api_key != self.valid_api_key:
            return MockResponse(401, {"code": "INVALID_API_KEY", "message": "Invalid API key", "status": 401})

        if url.endswith("/account/credits"):
            return MockResponse(200, {"creditBalance": self.credits})

        if "/generations/" in url:
            if self.next_poll_responses:
                nxt = self.next_poll_responses.pop(0)
                if isinstance(nxt, Exception):
                    raise nxt
                return nxt
            gid = url.rsplit("/generations/", 1)[1]
            seq = self.poll_sequences.get(gid)
            if seq is None:
                return MockResponse(404, {"code": "GENERATION_NOT_FOUND", "message": "Not found", "status": 404})
            step = seq.pop(0) if len(seq) > 1 else seq[0]
            body = {
                "generationId": gid,
                "createdAt": "2026-11-25T10:00:00.000Z",
                "updatedAt": "2026-11-25T10:00:05.000Z",
                **step,
            }
            return MockResponse(200, body, headers={"x-request-id": f"req-poll-{gid}"})

        return MockResponse(404, {"code": "ROUTE_NOT_FOUND", "message": "Unknown path", "status": 404})

    def delete(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: Any = None,
    ) -> MockResponse:
        headers = headers or {}
        self.calls.append({"method": "DELETE", "url": url, "headers": dict(headers)})

        if self.next_delete_responses:
            nxt = self.next_delete_responses.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt

        api_key = headers.get("x-api-key")
        if api_key != self.valid_api_key:
            return MockResponse(401, {"code": "INVALID_API_KEY", "message": "Invalid API key", "status": 401})

        if "/customers/" in url:
            ext_uid = url.rsplit("/customers/", 1)[1]
            self.deleted_customers.append(ext_uid)
            return MockResponse(204)

        return MockResponse(404, {"code": "ROUTE_NOT_FOUND", "message": "Unknown path", "status": 404})


def _genlook_settings(**overrides: Any) -> SimpleNamespace:
    base = {
        "environment": "development",
        "tryon_enabled": True,
        "tryon_provider": "genlook",
        "tryon_consent_version": "tryon-v1",
        "tryon_daily_quota_per_user": 20,
        "tryon_max_concurrent_jobs_per_user": 5,
        "tryon_retention_enabled": True,
        "tryon_retention_person_photo_hours": 24,
        "tryon_retention_result_hours": 72,
        "tryon_retention_failed_jobs_hours": 24,
        "tryon_retention_cancelled_jobs_hours": 12,
        "genlook_api_key": TEST_API_KEY,
        "genlook_api_base_url": "https://api.genlook.app/tryon/v1",
        "genlook_connect_timeout_s": 5.0,
        "genlook_request_timeout_s": 10.0,
        "genlook_poll_interval_s": 0.01,
        "genlook_poll_timeout_s": 5.0,
        "genlook_max_retries": 2,
        "genlook_keep_for_days": 1,
        "genlook_ai_label": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def env_setup():
    tryon_app.reset_for_tests()
    clear_settings_cache()
    storage = FakeStorageAdapter()
    job_repo = tryon_app._IN_MEMORY_REPO
    wardrobe_repo = _WardrobeRepoStub()

    app.dependency_overrides[get_storage_adapter] = lambda: storage
    app.dependency_overrides[get_tryon_repository] = lambda: job_repo
    app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo
    app.dependency_overrides[get_current_user_id] = lambda: USER_A

    yield {"storage": storage, "job_repo": job_repo, "wardrobe_repo": wardrobe_repo}

    app.dependency_overrides.clear()
    tryon_app.reset_for_tests()
    clear_settings_cache()


# ==============================================================================
# 1. Credential Configuration & Fail-Closed Security Tests
# ==============================================================================


class TestGenlookConfiguration:
    def test_genlook_provider_requires_api_key_in_settings(self, monkeypatch):
        monkeypatch.delenv("GENLOOK_API_KEY", raising=False)
        with pytest.raises(ValidationError, match="GENLOOK_API_KEY"):
            Settings(_env_file=None, tryon_provider="genlook", genlook_api_key=None)

        with pytest.raises(ValidationError, match="GENLOOK_API_KEY"):
            Settings(_env_file=None, tryon_provider="genlook", genlook_api_key="   ")

    def test_production_genlook_requires_strong_key_and_https(self):
        with pytest.raises(ValidationError, match="16 characters"):
            Settings(
                _env_file=None,
                environment="production",
                database_url="postgresql+psycopg://prod:StrongPass123!@db.internal:5432/prod",
                auth_secret="a" * 32,
                allow_dev_token=False,
                media_storage_provider="r2",
                r2_bucket_name="prod-bucket",
                r2_account_id="acc-123",
                r2_access_key_id="key-123",
                r2_secret_access_key="sec-123",
                media_upload_hmac_secret="b" * 32,
                tryon_provider="genlook",
                genlook_api_key="short-key",
            )

        with pytest.raises(ValidationError, match="HTTPS"):
            Settings(
                _env_file=None,
                environment="production",
                database_url="postgresql+psycopg://prod:StrongPass123!@db.internal:5432/prod",
                auth_secret="a" * 32,
                allow_dev_token=False,
                media_storage_provider="r2",
                r2_bucket_name="prod-bucket",
                r2_account_id="acc-123",
                r2_access_key_id="key-123",
                r2_secret_access_key="sec-123",
                media_upload_hmac_secret="b" * 32,
                tryon_provider="genlook",
                genlook_api_key=TEST_API_KEY,
                genlook_api_base_url="http://insecure.example/v1",
            )

    def test_keep_for_days_validated(self):
        with pytest.raises(ValidationError, match="1, 3, or 7"):
            Settings(_env_file=None, genlook_keep_for_days=14)

    def test_secret_masked_in_settings_and_config_repr(self):
        s = Settings(_env_file=None, tryon_provider="genlook", genlook_api_key=TEST_API_KEY)
        assert TEST_API_KEY not in repr(s)
        assert TEST_API_KEY not in str(s)

        cfg = GenlookTryOnConfig(api_key=TEST_API_KEY)
        assert TEST_API_KEY not in repr(cfg)
        assert "..." in repr(cfg)

    def test_provider_rejects_empty_api_key(self):
        with pytest.raises(CommercialProviderConfigurationError):
            GenlookTryOnProvider(GenlookTryOnConfig(api_key=""))

    def test_submit_job_fails_closed_when_genlook_key_missing(self, monkeypatch, env_setup):
        settings = _genlook_settings(genlook_api_key=None)
        monkeypatch.setattr(tryon_app, "get_settings", lambda: settings)
        gid = uuid4()
        env_setup["wardrobe_repo"].add(USER_A, gid)

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "missing-key-1"},
        )
        assert resp.status_code == 503


# ==============================================================================
# 2. Genlook Provider Unit Tests (Upload, Try-On, Polling, Errors, Credits)
# ==============================================================================


class TestGenlookProviderUnit:
    def _cfg(self, **overrides: Any) -> GenlookTryOnConfig:
        base = {
            "api_key": TEST_API_KEY,
            "poll_interval_s": 0.01,
            "poll_timeout_s": 1.0,
            "max_retries": 2,
            "backoff_factor": 1.0,
        }
        base.update(overrides)
        return GenlookTryOnConfig(**base)

    def test_conforms_to_tryon_provider_protocol(self):
        provider = GenlookTryOnProvider(self._cfg())
        assert isinstance(provider, TryOnProvider)
        assert provider.provider_id == "genlook"

    def test_upload_multipart_mime_and_10mb_guard(self):
        server = MockGenlookServer()
        provider = GenlookTryOnProvider(self._cfg(), http_client=server)

        res = provider.upload_person_image(
            person_bytes=VALID_WEBP,
            mime_type="image/webp",
            external_user_id=str(USER_A),
        )
        assert res.image_id.startswith("ephemeral/customer/")
        assert res.keep_for_days == 1

        up_call = server.calls[0]
        assert up_call["headers"]["x-api-key"] == TEST_API_KEY
        assert up_call["files"]["file"][0] == "person.webp"
        assert up_call["files"]["file"][2] == "image/webp"
        assert up_call["data"]["keepForDays"] == "1"
        assert up_call["data"]["externalUserId"] == str(USER_A)

        # > 10 MB rejected client-side before any HTTP call
        oversized = b"\xff\xd8\xff" + b"\x00" * (GENLOOK_MAX_IMAGE_BYTES + 1)
        with pytest.raises(ProviderPayloadError, match="10 MB"):
            provider.upload_person_image(person_bytes=oversized)
        assert len(server.calls) == 1

        # Declared MIME mismatch rejected
        with pytest.raises(ProviderPayloadError, match="does not match"):
            provider.upload_person_image(person_bytes=VALID_JPEG, mime_type="image/png")

    def test_tryon_payload_format_and_no_invented_category(self):
        server = MockGenlookServer()
        provider = GenlookTryOnProvider(self._cfg(), http_client=server)
        up = provider.upload_person_image(person_bytes=VALID_JPEG)

        spec = build_genlook_product_spec(
            item_id="garment-123",
            name="Olive Cotton Overshirt",
            category="outerwear",
            color="olive",
            material="cotton",
            fit="boxy",
            image_url="https://r2.example.com/signed-garment?X-Amz-Signature=abc",
        )
        created = provider.create_tryon(
            image_id=up.image_id,
            product=spec,
            idempotency_key="fv-tryon-test-1",
            external_user_id=str(USER_A),
        )
        assert created.generation_id == "cm8gen_1"
        assert created.status == "PENDING"
        assert created.rate_limit_limit == 20
        assert created.rate_limit_remaining == 19

        tryon_call = server.calls[-1]
        assert tryon_call["headers"]["x-api-key"] == TEST_API_KEY
        assert tryon_call["headers"]["Idempotency-Key"] == "fv-tryon-test-1"
        body = tryon_call["json"]
        assert body["person"] == {"image": {"source": {"id": up.image_id}}}
        assert len(body["products"]) == 1
        prod = body["products"][0]
        assert prod["externalId"] == "garment-123"
        assert prod["title"] == "Olive Cotton Overshirt"
        assert "Olive" in prod["description"] or "olive" in prod["description"]
        assert prod["images"] == [{"source": {"url": "https://r2.example.com/signed-garment?X-Amz-Signature=abc"}}]
        assert "category" not in prod
        assert "category" not in body
        assert body["output"]["aiLabel"] is True

    def test_polling_running_and_completed_never_forwards_api_key_to_cdn(self):
        server = MockGenlookServer(result_bytes=VALID_PNG)
        server.poll_sequences["cm8gen_1"] = [
            {"status": "PENDING"},
            {"status": "RUNNING"},
            {"status": "COMPLETED", "resultImageUrl": "https://cdn.genlook-results.example/cm8gen_1/out.png"},
        ]
        provider = GenlookTryOnProvider(self._cfg(), http_client=server)
        out = provider.render(
            person_digest="digest-1",
            garment_labels=["g-1"],
            seed="s-1",
            outfit_source="wardrobe",
            person_bytes=VALID_JPEG,
            garment_image_url="https://r2.example.com/garment.webp?sig=1",
            idempotency_key="idem-poll-1",
        )
        assert out == VALID_PNG

        cdn_calls = [c for c in server.calls if c["url"].startswith("https://cdn.genlook-results.example/")]
        assert len(cdn_calls) == 1
        assert "x-api-key" not in cdn_calls[0]["headers"]

    def test_401_403_raise_auth_error_without_retry(self):
        server = MockGenlookServer(valid_api_key="different-key")
        provider = GenlookTryOnProvider(self._cfg(), http_client=server)
        with pytest.raises(ProviderAuthError):
            provider.upload_person_image(person_bytes=VALID_JPEG)
        assert len(server.calls) == 1

    def test_402_insufficient_credits_raises_quota_error_without_retry(self):
        server = MockGenlookServer(initial_credits=0)
        provider = GenlookTryOnProvider(self._cfg(), http_client=server)
        up = provider.upload_person_image(person_bytes=VALID_JPEG)
        spec = build_genlook_product_spec(item_id="g1", name="Shirt", image_url="https://r2.example.com/g1.webp")
        with pytest.raises(ProviderQuotaExceededError, match="INSUFFICIENT_CREDITS"):
            provider.create_tryon(image_id=up.image_id, product=spec, idempotency_key="idem-402")
        # 1 upload + 1 try-on (no retry on 402)
        assert len(server.calls) == 2

    def test_429_rate_limit_retries_with_retry_after_and_exhausts_cleanly(self):
        server = MockGenlookServer()
        provider = GenlookTryOnProvider(self._cfg(max_retries=1), http_client=server)
        up = provider.upload_person_image(person_bytes=VALID_JPEG)
        spec = build_genlook_product_spec(item_id="g1", name="Shirt", image_url="https://r2.example.com/g1.webp")

        # 1st attempt: 429 Retry-After: 0.01, 2nd attempt: 201 success (same Idempotency-Key)
        server.next_tryon_responses.append(
            MockResponse(
                429,
                {"code": "RATE_LIMITED", "message": "Too many concurrent", "status": 429, "details": {"retryAfter": 0.01}},
                headers={"Retry-After": "0.01"},
            )
        )
        res = provider.create_tryon(image_id=up.image_id, product=spec, idempotency_key="idem-429-ok")
        assert res.generation_id == "cm8gen_1"

        # Exhausted 429 raises ProviderQuotaExceededError
        server.next_tryon_responses.extend(
            [
                MockResponse(429, {"code": "RATE_LIMITED", "message": "Busy", "status": 429}, headers={"Retry-After": "0.01"}),
                MockResponse(429, {"code": "RATE_LIMITED", "message": "Busy", "status": 429}, headers={"Retry-After": "0.01"}),
            ]
        )
        with pytest.raises(ProviderQuotaExceededError, match="429"):
            provider.create_tryon(image_id=up.image_id, product=spec, idempotency_key="idem-429-fail")

    def test_timeout_and_5xx_retry_with_same_idempotency_key_no_double_charge(self):
        server = MockGenlookServer(initial_credits=5)
        provider = GenlookTryOnProvider(self._cfg(max_retries=2), http_client=server)
        up = provider.upload_person_image(person_bytes=VALID_JPEG)
        spec = build_genlook_product_spec(item_id="g1", name="Shirt", image_url="https://r2.example.com/g1.webp")

        # Simulate timeout then 502 then success
        server.next_tryon_responses.extend(
            [
                httpx.ReadTimeout("timeout"),
                MockResponse(502, {"code": "INTERNAL_ERROR", "message": "Bad gateway", "status": 502}),
            ]
        )
        res = provider.create_tryon(image_id=up.image_id, product=spec, idempotency_key="idem-safe-retry")
        assert res.generation_id == "cm8gen_1"
        assert server.credits == 4  # Charged once!
        tryon_calls = [c for c in server.calls if c["url"].endswith("/try-on")]
        assert len(tryon_calls) == 3
        assert all(c["headers"]["Idempotency-Key"] == "idem-safe-retry" for c in tryon_calls)

    def test_polling_timeout_and_failed_status_handling(self):
        server = MockGenlookServer()
        provider = GenlookTryOnProvider(self._cfg(poll_interval_s=0.01, poll_timeout_s=0.05), http_client=server)
        up = provider.upload_person_image(person_bytes=VALID_JPEG)
        spec = build_genlook_product_spec(item_id="g1", name="Shirt", image_url="https://r2.example.com/g1.webp")
        created = provider.create_tryon(image_id=up.image_id, product=spec, idempotency_key="idem-timeout")

        # Keep generation PENDING forever -> poll timeout raises ProviderTransientError
        server.poll_sequences[created.generation_id] = [{"status": "PENDING"}]
        with pytest.raises(ProviderTransientError, match="timed out"):
            provider.poll_generation(created.generation_id)

        # FAILED generation with PRODUCT_IMAGE_FETCH_FAILED -> ProviderPayloadError
        server.poll_sequences[created.generation_id] = [
            {
                "status": "FAILED",
                "errorCode": "PRODUCT_IMAGE_FETCH_FAILED",
                "errorMessage": "Signed URL expired",
            }
        ]
        with pytest.raises(ProviderPayloadError, match="PRODUCT_IMAGE_FETCH_FAILED"):
            provider.poll_generation(created.generation_id)

    def test_result_download_rejects_svg_html_and_corrupt_bytes(self):
        server = MockGenlookServer()
        provider = GenlookTryOnProvider(self._cfg(), http_client=server)

        for bad_bytes in (
            b'<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>',
            b"<html><body>Not found</body></html>",
            b"\xff\xd8\xff\x00\x00\x00\x00",
        ):
            server.next_download_responses.append(MockResponse(200, content=bad_bytes))
            with pytest.raises(ProviderPayloadError):
                provider.download_result_image("https://cdn.genlook-results.example/cm8gen_1/out.png")

    def test_check_credits_and_health(self):
        server = MockGenlookServer(initial_credits=42)
        provider = GenlookTryOnProvider(self._cfg(), http_client=server)
        assert provider.check_credits() == 42
        health = provider.check_health()
        assert health["provider"] == "genlook"
        assert health["status"] == "healthy"
        assert health["credit_balance"] == 42
        assert TEST_API_KEY not in json.dumps(health)


# ==============================================================================
# 3. Full End-to-End Application, Storage, Isolation & Billing Safety Tests
# ==============================================================================


class TestGenlookEndToEndLifecycle:
    def _patch_genlook(self, monkeypatch, server: MockGenlookServer, settings: Any = None):
        cfg = settings or _genlook_settings()
        monkeypatch.setattr(tryon_app, "get_settings", lambda: cfg)
        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)

    def test_full_submission_signed_garment_url_storage_and_no_temp_url_persisted(
        self, monkeypatch, env_setup, caplog
    ):
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        self._patch_genlook(monkeypatch, server)

        storage: FakeStorageAdapter = env_setup["storage"]
        repo = env_setup["job_repo"]
        wardrobe_repo = env_setup["wardrobe_repo"]

        garment_id = uuid4()
        item = wardrobe_repo.add(USER_A, garment_id, name="Charcoal Blazer", category="outerwear", color="charcoal")
        asyncio.run(storage.put_object(item.image_ref["key"], VALID_WEBP, content_type="image/webp"))

        with caplog.at_level(logging.DEBUG):
            client = TestClient(app)
            resp = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(garment_id)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "e2e-genlook-1"},
            )
            assert resp.status_code == 202
            body = resp.json()
            assert body["is_mock"] is False
            job_id = UUID(body["job_id"])

            status_resp = client.get(f"/v1/tryon/jobs/{job_id}")
            assert status_resp.status_code == 200
            status_json = status_resp.json()
            assert status_json["status"] == "completed"
            assert status_json["is_mock"] is False
            assert status_json["result_media_ref"]["provider"] == "genlook"
            assert status_json["result_media_ref"]["creditsCharged"] == 1
            assert "resultImageUrl" not in json.dumps(status_json)
            assert "cdn.genlook-results.example" not in json.dumps(status_json)
            assert TEST_API_KEY not in json.dumps(status_json)

            img_resp = client.get(f"/v1/tryon/jobs/{job_id}/image")
            assert img_resp.status_code == 200
            assert img_resp.headers["content-type"].startswith("image/png")
            assert img_resp.content == VALID_PNG

        # Verify signed garment URL from FakeStorageAdapter was sent to Genlook
        tryon_calls = [c for c in server.calls if c["url"].endswith("/try-on")]
        assert len(tryon_calls) == 1
        sent_url = tryon_calls[0]["json"]["products"][0]["images"][0]["source"]["url"]
        assert item.image_ref["key"] in sent_url
        assert "action=get" in sent_url

        # Verify private storage persistence and temporary Genlook URL absence in repo
        rec = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert rec is not None
        assert storage.object_exists_sync(rec.result_media_ref["key"])
        assert "cdn.genlook-results.example" not in json.dumps(rec.result_media_ref)
        assert rec.person_media_ref["genlook"]["imageId"].startswith("ephemeral/customer/")
        assert rec.person_media_ref["genlook"]["generationId"] == "cm8gen_1"

        # Zero secret leakage in logs
        assert TEST_API_KEY not in caplog.text

    def test_missing_garment_image_fails_closed_without_placeholder(self, monkeypatch, env_setup):
        server = MockGenlookServer()
        self._patch_genlook(monkeypatch, server)

        garment_id = uuid4()
        # Wardrobe item exists, but its private storage object is missing!
        env_setup["wardrobe_repo"].add(USER_A, garment_id)

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(garment_id)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "e2e-missing-garment-img"},
        )
        assert resp.status_code == 202
        job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=UUID(resp.json()["job_id"]))
        assert job.status == "failed"
        assert job.error_code == "STORAGE_FAILURE"
        # Genlook was NEVER called with a placeholder
        assert len(server.calls) == 0

    def test_multi_garment_rejected_for_genlook(self, monkeypatch, env_setup):
        server = MockGenlookServer()
        self._patch_genlook(monkeypatch, server)
        g1, g2 = uuid4(), uuid4()
        env_setup["wardrobe_repo"].add(USER_A, g1)
        env_setup["wardrobe_repo"].add(USER_A, g2)

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(g1), str(g2)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "e2e-multi-1"},
        )
        assert resp.status_code == 422

    def test_image_id_reused_for_same_user_isolated_across_users(self, monkeypatch, env_setup):
        server = MockGenlookServer(initial_credits=10)
        self._patch_genlook(monkeypatch, server)

        storage: FakeStorageAdapter = env_setup["storage"]
        wardrobe_repo = env_setup["wardrobe_repo"]
        g_a = uuid4()
        g_b = uuid4()
        item_a = wardrobe_repo.add(USER_A, g_a)
        item_b = wardrobe_repo.add(USER_B, g_b)
        asyncio.run(storage.put_object(item_a.image_ref["key"], VALID_WEBP, content_type="image/webp"))
        asyncio.run(storage.put_object(item_b.image_ref["key"], VALID_WEBP, content_type="image/webp"))

        client = TestClient(app)
        # Job 1 for User A uploads imageId_1
        r1 = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
            data={"outfit_source": "wardrobe", "garment_ids": json.dumps([str(g_a)]), "consent_version": "tryon-v1", "consent_accepted": "true"},
            headers={"Idempotency-Key": "reuse-a-1"},
        )
        assert r1.status_code == 202

        # Job 2 for User A with same photo reuses imageId_1 (no 2nd upload!)
        r2 = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
            data={"outfit_source": "wardrobe", "garment_ids": json.dumps([str(g_a)]), "consent_version": "tryon-v1", "consent_accepted": "true"},
            headers={"Idempotency-Key": "reuse-a-2"},
        )
        assert r2.status_code == 202
        assert server.upload_counter == 1

        # Job for User B with identical JPEG bytes MUST NOT reuse User A's imageId
        app.dependency_overrides[get_current_user_id] = lambda: USER_B
        r3 = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
            data={"outfit_source": "wardrobe", "garment_ids": json.dumps([str(g_b)]), "consent_version": "tryon-v1", "consent_accepted": "true"},
            headers={"Idempotency-Key": "reuse-b-1"},
        )
        assert r3.status_code == 202
        assert server.upload_counter == 2

        # User B cannot access User A's job or image
        assert client.get(f"/v1/tryon/jobs/{r1.json()['job_id']}").status_code == 404
        assert client.get(f"/v1/tryon/jobs/{r1.json()['job_id']}/image").status_code == 404

    def test_retry_after_poll_timeout_and_restart_resumes_generation_without_double_charge(
        self, monkeypatch, env_setup
    ):
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        # Very short poll timeout on first run
        self._patch_genlook(monkeypatch, server, _genlook_settings(genlook_poll_timeout_s=0.03, genlook_poll_interval_s=0.01))

        storage: FakeStorageAdapter = env_setup["storage"]
        repo = env_setup["job_repo"]
        wardrobe_repo = env_setup["wardrobe_repo"]
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(storage.put_object(item.image_ref["key"], VALID_WEBP, content_type="image/webp"))

        # Make cm8gen_1 stay PENDING so poll times out
        server.poll_sequences["cm8gen_1"] = [{"status": "PENDING"}]

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
            data={"outfit_source": "wardrobe", "garment_ids": json.dumps([str(gid)]), "consent_version": "tryon-v1", "consent_accepted": "true"},
            headers={"Idempotency-Key": "resume-1"},
        )
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])

        failed_job = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert failed_job.status == "failed"
        assert failed_job.error_code == "PROVIDER_TRANSIENT_FAILURE"
        assert failed_job.person_media_ref["genlook"]["generationId"] == "cm8gen_1"
        assert server.credits == 9  # 1 credit used

        # Simulate backend restart recovery on an interrupted processing job with generationId
        repo.update_status(job_id=job_id, status="processing")
        recovered = tryon_app.recover_interrupted_jobs(repo)
        assert recovered == 1
        assert repo.get_by_id(user_id=USER_A, job_id=job_id).error_code == "INTERRUPTED_BY_RESTART"

        # Now Genlook finishes cm8gen_1; retry must resume GET /generations/cm8gen_1 without a 2nd POST /try-on
        server.poll_sequences["cm8gen_1"] = [
            {"status": "COMPLETED", "resultImageUrl": "https://cdn.genlook-results.example/cm8gen_1/out.png"}
        ]
        self._patch_genlook(monkeypatch, server, _genlook_settings(genlook_poll_timeout_s=2.0, genlook_poll_interval_s=0.01))

        retry_resp = client.post(f"/v1/tryon/jobs/{job_id}/retry")
        assert retry_resp.status_code == 202

        done_job = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert done_job.status == "completed"
        assert server.credits == 9  # STILL 9 — zero duplicate charge!
        tryon_posts = [c for c in server.calls if c["url"].endswith("/try-on")]
        assert len(tryon_posts) == 1

    def test_uncertain_post_tryon_timeout_replays_idempotency_key_on_retry(self, monkeypatch, env_setup):
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        self._patch_genlook(monkeypatch, server, _genlook_settings(genlook_max_retries=0))

        storage: FakeStorageAdapter = env_setup["storage"]
        repo = env_setup["job_repo"]
        wardrobe_repo = env_setup["wardrobe_repo"]
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(storage.put_object(item.image_ref["key"], VALID_WEBP, content_type="image/webp"))

        # First attempt: Genlook accepted request into idempotency_map, but response timed out before reaching backend!
        def _accept_then_timeout():
            server.credits -= 1
            server.gen_counter += 1
            gen_id = f"cm8gen_{server.gen_counter}"
            server.generations[gen_id] = {"status": "PENDING", "productExternalIds": [str(gid)], "payload": {}}
            server.poll_sequences[gen_id] = [
                {"status": "COMPLETED", "resultImageUrl": f"https://cdn.genlook-results.example/{gen_id}/out.png"}
            ]
            # Wait for job_id to exist so we can map its attempt key
            return gen_id

        pre_gen_id = _accept_then_timeout()
        server.next_tryon_responses.append(httpx.ReadTimeout("dropped response after accept"))

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
            data={"outfit_source": "wardrobe", "garment_ids": json.dumps([str(gid)]), "consent_version": "tryon-v1", "consent_accepted": "true"},
            headers={"Idempotency-Key": "uncertain-1"},
        )
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])
        failed = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert failed.status == "failed"
        pending_key = failed.person_media_ref["genlook"]["pendingIdempotencyKey"]
        assert pending_key == f"fv-tryon-{job_id}-a0"

        # Bind that pending key in MockGenlookServer as already accepted on Genlook's side
        server.idempotency_map[pending_key] = pre_gen_id

        retry_resp = client.post(f"/v1/tryon/jobs/{job_id}/retry")
        assert retry_resp.status_code == 202
        done = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert done.status == "completed"
        assert done.result_media_ref["generationId"] == pre_gen_id
        # Credits remained 9 (not decremented a second time!)
        assert server.credits == 9

    def test_health_endpoint_reports_genlook_without_secret(self, monkeypatch, env_setup):
        server = MockGenlookServer(initial_credits=17)
        self._patch_genlook(monkeypatch, server)
        monkeypatch.setenv("FANSIVIBE_TRYON_PROVIDER", "genlook")
        monkeypatch.setenv("GENLOOK_API_KEY", TEST_API_KEY)
        monkeypatch.setenv("FANSIVIBE_OPERATOR_API_KEY", "test-operator-key-32-chars-minimum")
        clear_settings_cache()

        client = TestClient(app)

        # 1. Unauthenticated / wrong-auth access is blocked
        assert client.get("/v1/tryon/health").status_code == 401
        assert client.get("/v1/tryon/health/credits").status_code == 401
        assert client.get(
            "/v1/tryon/health",
            headers={"Authorization": "Bearer user-jwt-must-not-work"},
        ).status_code == 401
        assert client.get(
            "/v1/tryon/health",
            headers={"X-Operator-Key": "wrong-operator-key"},
        ).status_code == 403
        assert len(server.calls) == 0

        # 2. Ordinary operator health does NOT call external /account/credits
        resp = client.get(
            "/v1/tryon/health",
            headers={"X-Operator-Key": "test-operator-key-32-chars-minimum"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["local_backend"]["status"] == "healthy"
        assert data["provider_config"]["provider"] == "genlook"
        assert data["provider_config"]["configured"] is True
        assert "credit_balance" not in data["provider_config"]
        assert data["credits"]["checked"] is False
        assert TEST_API_KEY not in resp.text
        assert len(server.calls) == 0

        # 3. Explicit credits endpoint performs external credit query for authorized operator
        credits_resp = client.get(
            "/v1/tryon/health/credits",
            headers={"X-Operator-Key": "test-operator-key-32-chars-minimum"},
        )
        assert credits_resp.status_code == 200
        credits_data = credits_resp.json()
        assert credits_data["provider"] == "genlook"
        assert credits_data["credit_balance"] == 17
        assert TEST_API_KEY not in credits_resp.text
        assert len(server.calls) == 1

    def test_cancellation_during_polling_stops_cleanly_and_retention_cleans_up(
        self, monkeypatch, env_setup
    ):
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        storage: FakeStorageAdapter = env_setup["storage"]
        repo = env_setup["job_repo"]
        wardrobe_repo = env_setup["wardrobe_repo"]
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(storage.put_object(item.image_ref["key"], VALID_WEBP, content_type="image/webp"))

        # Test cancellation during poll
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
            person_media_ref={"key": person_key, "contentHash": "digest-cancel"},
        )

        # Cancel job on the first poll call
        orig_get = server.get

        def _cancelling_get(url, **kw):
            if "/generations/" in url:
                tryon_app.cancel_job(user_id=str(USER_A), job_id=str(job_id), job_repo=repo)
            return orig_get(url, **kw)

        server.get = _cancelling_get  # type: ignore[method-assign]
        self._patch_genlook(monkeypatch, server)
        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=USER_A,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=wardrobe_repo,
            )
        )
        cancelled = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert cancelled is not None
        assert cancelled.status == "cancelled"
        assert cancelled.result_media_ref is None

        # Test retention cleanup purges person_media_ref (and genlook imageId) after 24h
        old_job_id = uuid4()
        old_person_key = f"users/{USER_A}/tryon/{old_job_id}/person.jpg"
        old_result_key = f"users/{USER_A}/tryon/{old_job_id}/result.png"
        asyncio.run(storage.put_object(old_person_key, VALID_JPEG, content_type="image/jpeg"))
        asyncio.run(storage.put_object(old_result_key, VALID_PNG, content_type="image/png"))
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        repo._jobs[old_job_id] = TryOnJobRecord(
            id=old_job_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=gid,
            garment_ids=(str(gid),),
            provider="genlook",
            status="completed",
            consent_version="tryon-v1",
            consent_accepted_at=old_time,
            created_at=old_time,
            updated_at=old_time,
            completed_at=old_time,
            person_media_ref={
                "key": old_person_key,
                "genlook": {"imageId": "ephemeral/customer/old"},
            },
            result_media_ref={"key": old_result_key, "mediaType": "image/png"},
        )
        summary = asyncio.run(
            tryon_app.cleanup_retention_data(job_repo=repo, storage=storage)
        )
        assert summary.person_photos_purged >= 1
        assert not storage.object_exists_sync(old_person_key)
        assert storage.object_exists_sync(old_result_key)
        assert repo.get_by_id(user_id=USER_A, job_id=old_job_id).person_media_ref is None

        # Delete removes result object and job row
        assert asyncio.run(
            tryon_app.delete_job_and_media(
                user_id=str(USER_A), job_id=str(old_job_id), job_repo=repo, storage=storage
            )
        ) is True
        assert not storage.object_exists_sync(old_result_key)
        assert repo.get_by_id(user_id=USER_A, job_id=old_job_id) is None


# ==============================================================================
# 4. PostgreSQL Persistence & Lifecycle Tests (Isolated Test DB)
# ==============================================================================


class TestGenlookPostgresIntegration:
    """Verifies Genlook repository methods and full lifecycle on PostgreSQL."""

    def _assert_disposable_db(self) -> None:
        from app.infrastructure.db import session as db_session_mod

        db_name = db_session_mod.engine.url.database or ""
        assert db_name != "fansivibe", "Refusing to run integration tests against dev DB"

    def _seed_user(self, session, email: str) -> UUID:
        from app.infrastructure.db.models import UserState, Users

        user = Users(
            auth_provider="local",
            auth_subject=email,
            display_name=email.split("@")[0],
        )
        session.add(user)
        session.flush()
        session.add(UserState(user_id=user.id))
        session.commit()
        return user.id

    def _seed_garment(
        self,
        session,
        *,
        user_id: UUID,
        name: str = "Navy Linen Shirt",
        image_key: str | None = None,
    ) -> UUID:
        from app.infrastructure.db.models import WardrobeItems

        item_id = uuid4()
        key = image_key or f"users/{user_id}/wardrobe/{item_id}/canonical.webp"
        item = WardrobeItems(
            id=item_id,
            user_id=user_id,
            name=name,
            category_id="tops",
            color_id="navy",
            material_id=None,
            is_favorite=False,
            image_ref={"key": key, "mediaType": "image/webp"},
        )
        session.add(item)
        session.commit()
        return item.id

    def test_update_person_media_ref_and_find_reusable_image_id_rules(self, db) -> None:
        from app.infrastructure.db.repositories import TryOnJobRepositorySQL

        self._assert_disposable_db()
        Session = db
        now = datetime.now(timezone.utc)
        digest_a = "sha256-person-a"
        digest_other = "sha256-person-other"

        with Session() as s1:
            user_a = self._seed_user(s1, "pg-gl-reuse-a@example.com")
            user_b = self._seed_user(s1, "pg-gl-reuse-b@example.com")
            repo1 = TryOnJobRepositorySQL(s1)

            # 1. Valid Genlook job for User A
            job_ok = uuid4()
            repo1.create(
                job_id=job_ok,
                user_id=user_a,
                outfit_source="wardrobe",
                garment_id=None,
                garment_ids=[str(uuid4())],
                provider="genlook",
                status="queued",
                consent_version="tryon-v1",
                consent_accepted_at=now,
                person_media_ref={
                    "key": f"users/{user_a}/tryon/{job_ok}/person.jpg",
                    "contentHash": digest_a,
                },
                idempotency_key="pg-gl-reuse-1",
                request_fingerprint="fp-1",
            )
            updated = repo1.update_person_media_ref(
                job_id=job_ok,
                person_media_ref={
                    "key": f"users/{user_a}/tryon/{job_ok}/person.jpg",
                    "contentHash": digest_a,
                    "genlook": {
                        "imageId": "ephemeral/customer/pg_img_ok",
                        "imageExpiresAt": (now + timedelta(hours=12)).isoformat(),
                        "generationId": "cm8gen_pg_1",
                    },
                },
            )
            assert updated is not None
            assert updated.person_media_ref["genlook"]["imageId"] == "ephemeral/customer/pg_img_ok"
            assert updated.person_media_ref["genlook"]["generationId"] == "cm8gen_pg_1"

            # 2. Expired Genlook imageExpiresAt (must be skipped)
            job_expired_img = uuid4()
            repo1.create(
                job_id=job_expired_img,
                user_id=user_a,
                outfit_source="wardrobe",
                garment_id=None,
                garment_ids=[str(uuid4())],
                provider="genlook",
                status="completed",
                consent_version="tryon-v1",
                consent_accepted_at=now,
                person_media_ref={
                    "key": f"users/{user_a}/tryon/{job_expired_img}/person.jpg",
                    "contentHash": digest_other,
                    "genlook": {
                        "imageId": "ephemeral/customer/pg_img_expired",
                        "imageExpiresAt": (now - timedelta(minutes=1)).isoformat(),
                    },
                },
                idempotency_key="pg-gl-reuse-2",
                request_fingerprint="fp-2",
            )

            # 3. Different consent version (must be skipped)
            job_old_consent = uuid4()
            repo1.create(
                job_id=job_old_consent,
                user_id=user_a,
                outfit_source="wardrobe",
                garment_id=None,
                garment_ids=[str(uuid4())],
                provider="genlook",
                status="completed",
                consent_version="tryon-v0",
                consent_accepted_at=now,
                person_media_ref={
                    "key": f"users/{user_a}/tryon/{job_old_consent}/person.jpg",
                    "contentHash": digest_other,
                    "genlook": {
                        "imageId": "ephemeral/customer/pg_img_old_consent",
                        "imageExpiresAt": (now + timedelta(hours=12)).isoformat(),
                    },
                },
                idempotency_key="pg-gl-reuse-3",
                request_fingerprint="fp-3",
            )

        # Verify in a completely fresh SQLAlchemy session
        with Session() as s2:
            repo2 = TryOnJobRepositorySQL(s2)
            loaded = repo2.get_by_id(user_id=user_a, job_id=job_ok)
            assert loaded is not None
            assert loaded.person_media_ref["genlook"]["generationId"] == "cm8gen_pg_1"

            # Matching user, consent, contentHash, and non-expired window -> reused
            found = repo2.find_reusable_genlook_image_id(
                user_id=user_a,
                person_digest=digest_a,
                consent_version="tryon-v1",
                min_created_at=now - timedelta(hours=24),
                now=now,
            )
            assert found == "ephemeral/customer/pg_img_ok"

            # Ownership isolation: User B cannot reuse User A's imageId
            assert (
                repo2.find_reusable_genlook_image_id(
                    user_id=user_b,
                    person_digest=digest_a,
                    consent_version="tryon-v1",
                    min_created_at=now - timedelta(hours=24),
                    now=now,
                )
                is None
            )

            # Consent mismatch -> rejected
            assert (
                repo2.find_reusable_genlook_image_id(
                    user_id=user_a,
                    person_digest=digest_a,
                    consent_version="tryon-v2",
                    min_created_at=now - timedelta(hours=24),
                    now=now,
                )
                is None
            )

            # Content hash mismatch -> rejected
            assert (
                repo2.find_reusable_genlook_image_id(
                    user_id=user_a,
                    person_digest="sha256-nonexistent",
                    consent_version="tryon-v1",
                    min_created_at=now - timedelta(hours=24),
                    now=now,
                )
                is None
            )

            # Expired imageExpiresAt -> rejected
            assert (
                repo2.find_reusable_genlook_image_id(
                    user_id=user_a,
                    person_digest=digest_other,
                    consent_version="tryon-v1",
                    min_created_at=now - timedelta(hours=24),
                    now=now,
                )
                is None
            )

            # Retention cutoff (created_at < min_created_at) -> rejected
            assert (
                repo2.find_reusable_genlook_image_id(
                    user_id=user_a,
                    person_digest=digest_a,
                    consent_version="tryon-v1",
                    min_created_at=now + timedelta(minutes=5),
                    now=now,
                )
                is None
            )

    def test_genlook_end_to_end_postgres_idempotency_retry_recovery_and_persistence(
        self, db, monkeypatch
    ) -> None:
        from app.infrastructure.db.repositories import TryOnJobRepositorySQL

        self._assert_disposable_db()
        tryon_app.reset_for_tests()
        Session = db

        with Session() as s:
            user_a = self._seed_user(s, "pg-gl-e2e-a@example.com")
            user_b = self._seed_user(s, "pg-gl-e2e-b@example.com")
            garment_id = self._seed_garment(s, user_id=user_a, name="Navy Wool Coat")

        storage = FakeStorageAdapter()
        garment_key = f"users/{user_a}/wardrobe/{garment_id}/canonical.webp"
        asyncio.run(storage.put_object(garment_key, VALID_WEBP, content_type="image/webp"))

        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)

        # Step 1: First attempt times out during polling after generationId is persisted
        short_cfg = _genlook_settings(genlook_poll_timeout_s=0.03, genlook_poll_interval_s=0.01)
        monkeypatch.setattr(tryon_app, "get_settings", lambda: short_cfg)
        server.poll_sequences["cm8gen_1"] = [{"status": "PENDING"}]

        app.dependency_overrides[get_current_user_id] = lambda: user_a
        app.dependency_overrides[get_storage_adapter] = lambda: storage
        try:
            client = TestClient(app)
            r1 = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(garment_id)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "pg-gl-e2e-idem-1"},
            )
            assert r1.status_code == 202
            job_id = UUID(r1.json()["job_id"])

            # Idempotent replay returns same job without creating a duplicate row or charging again
            r1_replay = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(garment_id)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "pg-gl-e2e-idem-1"},
            )
            assert r1_replay.status_code == 202
            assert UUID(r1_replay.json()["job_id"]) == job_id

            # Same Idempotency-Key with modified payload returns 409 Conflict
            r1_conflict = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("me.png", VALID_PNG, "image/png")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(garment_id)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "pg-gl-e2e-idem-1"},
            )
            assert r1_conflict.status_code == 409

            with Session() as s_chk1:
                repo_chk1 = TryOnJobRepositorySQL(s_chk1)
                row1 = repo_chk1.get_by_id(user_id=user_a, job_id=job_id)
                assert row1 is not None
                assert row1.status == "failed"
                assert row1.error_code == "PROVIDER_TRANSIENT_FAILURE"
                assert row1.person_media_ref["genlook"]["generationId"] == "cm8gen_1"
                assert row1.person_media_ref["genlook"]["imageId"].startswith("ephemeral/customer/")
                assert repo_chk1.get_by_id(user_id=user_b, job_id=job_id) is None

                # Simulate restart recovery before retry
                repo_chk1.update_status(job_id=job_id, status="processing")
                assert tryon_app.recover_interrupted_jobs(repo_chk1) == 1
                row_rec = repo_chk1.get_by_id(user_id=user_a, job_id=job_id)
                assert row_rec is not None
                assert row_rec.status == "failed"
                assert row_rec.error_code == "INTERRUPTED_BY_RESTART"
                assert row_rec.person_media_ref["genlook"]["generationId"] == "cm8gen_1"

            # Step 2: Retry resumes existing cm8gen_1 generation and completes in PostgreSQL
            server.poll_sequences["cm8gen_1"] = [
                {
                    "status": "COMPLETED",
                    "resultImageUrl": "https://cdn.genlook-results.example/cm8gen_1/out.png",
                }
            ]
            normal_cfg = _genlook_settings(genlook_poll_timeout_s=2.0, genlook_poll_interval_s=0.01)
            monkeypatch.setattr(tryon_app, "get_settings", lambda: normal_cfg)

            r_retry = client.post(f"/v1/tryon/jobs/{job_id}/retry")
            assert r_retry.status_code == 202
            assert server.credits == 9  # Single charge across initial + idempotent replay + restart + retry

            with Session() as s_chk2:
                repo_chk2 = TryOnJobRepositorySQL(s_chk2)
                done = repo_chk2.get_by_id(user_id=user_a, job_id=job_id)
                assert done is not None
                assert done.status == "completed"
                assert done.retry_count == 1
                assert done.result_media_ref is not None
                assert done.result_media_ref["provider"] == "genlook"
                assert done.result_media_ref["generationId"] == "cm8gen_1"
                assert "cdn.genlook-results.example" not in json.dumps(done.result_media_ref)
                assert storage.object_exists_sync(done.result_media_ref["key"])

            img_resp = client.get(f"/v1/tryon/jobs/{job_id}/image")
            assert img_resp.status_code == 200
            assert img_resp.content == VALID_PNG

            # Step 3: Second job for User A with same photo reuses imageId from PostgreSQL
            r2 = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(garment_id)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "pg-gl-e2e-idem-2"},
            )
            assert r2.status_code == 202
            assert server.upload_counter == 1  # Reused imageId from PostgreSQL!
        finally:
            app.dependency_overrides.clear()
            tryon_app.reset_for_tests()

    def test_cross_session_cancellation_visible_to_background_session(self, db) -> None:
        from app.infrastructure.db.repositories import TryOnJobRepositorySQL

        self._assert_disposable_db()
        Session = db
        job_id = uuid4()

        with Session() as s_seed:
            user_a = self._seed_user(s_seed, "pg-gl-cancel-a@example.com")
            TryOnJobRepositorySQL(s_seed).create(
                job_id=job_id,
                user_id=user_a,
                outfit_source="wardrobe",
                garment_id=None,
                garment_ids=[str(uuid4())],
                provider="genlook",
                status="queued",
                consent_version="tryon-v1",
                consent_accepted_at=datetime.now(timezone.utc),
                person_media_ref={"key": f"users/{user_a}/tryon/{job_id}/person.jpg"},
            )

        # Simulate long-lived background worker session that loads & updates the row
        with Session() as s_bg:
            bg_repo = TryOnJobRepositorySQL(s_bg)
            bg_repo.update_status(
                job_id=job_id,
                status="processing",
                processing_started_at=datetime.now(timezone.utc),
            )
            assert bg_repo.get_by_id(user_id=user_a, job_id=job_id).status == "processing"

            # Concurrent HTTP request cancels the job in a separate session
            with Session() as s_req:
                req_repo = TryOnJobRepositorySQL(s_req)
                cancelled = tryon_app.cancel_job(
                    user_id=str(user_a), job_id=str(job_id), job_repo=req_repo
                )
                assert cancelled.status == "cancelled"

            # Background session must observe committed cancellation despite expire_on_commit=False
            refreshed = bg_repo.get_by_id(user_id=user_a, job_id=job_id)
            assert refreshed is not None
            assert refreshed.status == "cancelled"

    def test_stale_worker_update_result_cannot_overwrite_concurrent_cancellation_without_refresh(
        self, db
    ) -> None:
        from app.infrastructure.db.repositories import TryOnJobRepositorySQL

        self._assert_disposable_db()
        Session = db
        job_id = uuid4()

        with Session() as s_seed:
            user_a = self._seed_user(s_seed, "pg-gl-stale-res-a@example.com")
            TryOnJobRepositorySQL(s_seed).create(
                job_id=job_id,
                user_id=user_a,
                outfit_source="wardrobe",
                garment_id=None,
                garment_ids=[str(uuid4())],
                provider="genlook",
                status="queued",
                consent_version="tryon-v1",
                consent_accepted_at=datetime.now(timezone.utc),
                person_media_ref={"key": f"users/{user_a}/tryon/{job_id}/person.jpg"},
            )

        with Session() as s_bg:
            bg_repo = TryOnJobRepositorySQL(s_bg)
            bg_repo.update_status(
                job_id=job_id,
                status="processing",
                processing_started_at=datetime.now(timezone.utc),
            )

            # Concurrent request cancels the job in another session
            with Session() as s_req:
                req_repo = TryOnJobRepositorySQL(s_req)
                cancelled = tryon_app.cancel_job(
                    user_id=str(user_a), job_id=str(job_id), job_repo=req_repo
                )
                assert cancelled.status == "cancelled"

            # Background session calls update_result directly WITHOUT calling get_by_id first
            result_row = bg_repo.update_result(
                job_id=job_id,
                result_media_ref={"key": f"users/{user_a}/tryon/{job_id}/result.png"},
                completed_at=datetime.now(timezone.utc),
            )
            assert result_row is not None
            assert result_row.status == "cancelled"

            with Session() as s_chk:
                persisted = TryOnJobRepositorySQL(s_chk).get_by_id(
                    user_id=user_a, job_id=job_id
                )
                assert persisted is not None
                assert persisted.status == "cancelled"
                assert persisted.result_media_ref is None


# ==============================================================================
# 5. Phase 5F.4A: Synthetic Image Compatibility & URL Failure Matrix
# ==============================================================================


class TestGenlookImageCompatibilityMatrix:
    """Synthetic-only image validation, R2 signed URL TTL, and error handling."""

    def test_supported_person_formats_jpeg_png_webp_and_exif_strip(
        self, monkeypatch, env_setup
    ) -> None:
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_WEBP)
        monkeypatch.setattr(tryon_app, "get_settings", lambda: _genlook_settings())
        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)

        storage: FakeStorageAdapter = env_setup["storage"]
        wardrobe_repo = env_setup["wardrobe_repo"]
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(
            storage.put_object(item.image_ref["key"], VALID_WEBP, content_type="image/webp")
        )

        # Build synthetic JPEG with orientation + GPS EXIF metadata
        exif = Image.Exif()
        exif[0x0112] = 6
        exif[0x010F] = "SyntheticCam"
        exif[0x8825] = {1: "N", 2: (10.0, 20.0, 30.0)}
        buf = io.BytesIO()
        Image.new("RGB", (120, 80), color=(40, 90, 140)).save(
            buf, format="JPEG", exif=exif.tobytes()
        )
        jpeg_with_exif = buf.getvalue()

        client = TestClient(app)
        for idx, (fname, payload, mime) in enumerate(
            [
                ("person.jpg", jpeg_with_exif, "image/jpeg"),
                ("person.png", VALID_PNG, "image/png"),
                ("person.webp", VALID_WEBP, "image/webp"),
            ]
        ):
            resp = client.post(
                "/v1/tryon/jobs",
                files={"person_image": (fname, payload, mime)},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(gid)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": f"compat-fmt-{idx}"},
            )
            assert resp.status_code == 202
            job_id = UUID(resp.json()["job_id"])
            rec = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=job_id)
            assert rec is not None
            assert rec.status == "completed"
            stored_person = asyncio.run(storage.read_object(rec.person_media_ref["key"]))
            with Image.open(io.BytesIO(stored_person)) as img:
                assert len(img.getexif()) == 0

    def test_unsupported_formats_and_10mb_person_limit_rejected_before_genlook(
        self, monkeypatch, env_setup
    ) -> None:
        server = MockGenlookServer(initial_credits=10)
        monkeypatch.setattr(tryon_app, "get_settings", lambda: _genlook_settings())
        wardrobe_repo = env_setup["wardrobe_repo"]
        gid = uuid4()
        wardrobe_repo.add(USER_A, gid)

        # Unsupported formats (GIF, BMP, SVG, fake HEIC/unknown magic, spoofed MIME, <64px)
        gif_buf = io.BytesIO()
        Image.new("RGB", (128, 128), color=(1, 2, 3)).save(gif_buf, format="GIF")
        tiny_png = _make_image_bytes("PNG", size=(32, 32))

        client = TestClient(app)
        bad_cases = [
            ("p.gif", gif_buf.getvalue(), "image/gif"),
            ("p.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml"),
            ("p.heic", b"\x00\x00\x00\x18ftypheic", "image/heic"),
            ("spoof.jpg", VALID_PNG, "image/jpeg"),
            ("tiny.png", tiny_png, "image/png"),
        ]
        for idx, (fname, payload, mime) in enumerate(bad_cases):
            resp = client.post(
                "/v1/tryon/jobs",
                files={"person_image": (fname, payload, mime)},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(gid)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": f"compat-bad-{idx}"},
            )
            assert resp.status_code == 422

        # > 10 MB person image rejected by submit_job for Genlook before storage/API call
        monkeypatch.setattr(
            tryon_app,
            "validate_and_sanitize_person_image",
            lambda _b, _ct: (b"\xff\xd8\xff" + b"\x00" * GENLOOK_MAX_IMAGE_BYTES, "image/jpeg"),
        )
        over_10mb = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("big.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "compat-over-10mb"},
        )
        assert over_10mb.status_code == 422
        assert len(server.calls) == 0

    def test_r2_signed_garment_url_ttl_accessibility_and_expired_url_error_handling(
        self, monkeypatch, env_setup
    ) -> None:
        from unittest.mock import MagicMock, patch
        from urllib.parse import parse_qs, urlparse
        from app.infrastructure.external.storage import CloudflareR2StorageAdapter

        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_JPEG)
        monkeypatch.setattr(tryon_app, "get_settings", lambda: _genlook_settings())
        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)

        # Real boto3 SigV4 path-style R2 adapter with mocked S3 object existence & storage
        r2_objects: dict[str, tuple[bytes, str]] = {}
        r2 = CloudflareR2StorageAdapter(
            bucket_name="fansivibe-media-dev",
            endpoint_url="https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
            access_key_id="r2-test-ak",
            secret_access_key="r2-test-sk",
            region_name="auto",
        )

        async def _fake_put(key, data, *, content_type="image/webp", custom_metadata=None):
            r2_objects[key] = (data, content_type)
            return SimpleNamespace(key=key, size_bytes=len(data), content_type=content_type)

        async def _fake_exists(key):
            return key in r2_objects

        async def _fake_read(key, *, max_bytes=20 * 1024 * 1024):
            return r2_objects[key][0]

        monkeypatch.setattr(r2, "put_object", _fake_put)
        monkeypatch.setattr(r2, "object_exists", _fake_exists)
        monkeypatch.setattr(r2, "read_object", _fake_read)

        app.dependency_overrides[get_storage_adapter] = lambda: r2
        gid = uuid4()
        item = env_setup["wardrobe_repo"].add(USER_A, gid)
        r2_objects[item.image_ref["key"]] = (VALID_WEBP, "image/webp")

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "compat-r2-ttl-1"},
        )
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])

        tryon_calls = [c for c in server.calls if c["url"].endswith("/try-on")]
        assert len(tryon_calls) == 1
        sent_url = tryon_calls[0]["json"]["products"][0]["images"][0]["source"]["url"]
        parsed = urlparse(sent_url)
        qs = parse_qs(parsed.query)
        assert parsed.scheme == "https"
        assert parsed.path == f"/fansivibe-media-dev/{item.image_ref['key']}"
        assert qs["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
        assert qs["X-Amz-Expires"] == ["300"]
        assert "X-Amz-Signature" in qs

        # Now simulate expired/inaccessible garment signed URL on Genlook side -> PRODUCT_IMAGE_FETCH_FAILED
        server.poll_sequences["cm8gen_2"] = [
            {
                "status": "FAILED",
                "errorCode": "PRODUCT_IMAGE_FETCH_FAILED",
                "errorMessage": "Signed URL expired (403)",
            }
        ]
        resp2 = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("p.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "compat-r2-expired-1"},
        )
        assert resp2.status_code == 202
        failed_job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=UUID(resp2.json()["job_id"]))
        assert failed_job is not None
        assert failed_job.status == "failed"
        assert failed_job.error_code == "PAYLOAD_REJECTED"
        assert failed_job.person_media_ref["genlook"]["lastErrorCode"] == "PRODUCT_IMAGE_FETCH_FAILED"
        assert failed_job.person_media_ref["genlook"]["refunded"] is True

    def test_result_image_validation_and_expired_result_url_handling(self) -> None:
        server = MockGenlookServer()
        provider = GenlookTryOnProvider(
            GenlookTryOnConfig(api_key=TEST_API_KEY, poll_interval_s=0.01, poll_timeout_s=1.0),
            http_client=server,
        )

        # Accepts JPEG, PNG, WebP
        for valid_bytes in (VALID_JPEG, VALID_PNG, VALID_WEBP):
            server.next_download_responses.append(MockResponse(200, content=valid_bytes))
            assert provider.download_result_image("https://cdn.genlook-results.example/ok") == valid_bytes

        # Expired / inaccessible resultImageUrl (403/404/410 -> ProviderPayloadError; 503/timeout -> ProviderTransientError)
        for status_code in (403, 404, 410):
            server.next_download_responses.append(MockResponse(status_code, content=b"Expired"))
            with pytest.raises(ProviderPayloadError, match=f"HTTP {status_code}"):
                provider.download_result_image("https://cdn.genlook-results.example/expired")

        server.next_download_responses.append(MockResponse(503, content=b"Busy"))
        with pytest.raises(ProviderTransientError, match="HTTP 503"):
            provider.download_result_image("https://cdn.genlook-results.example/busy")

        server.next_download_responses.append(httpx.ReadTimeout("cdn timeout"))
        with pytest.raises(ProviderTransientError, match="ReadTimeout"):
            provider.download_result_image("https://cdn.genlook-results.example/timeout")

        # > 20 MB result image rejected
        server.next_download_responses.append(
            MockResponse(200, content=b"\xff\xd8\xff" + b"\x00" * (20 * 1024 * 1024))
        )
        with pytest.raises(ProviderPayloadError, match="size out of bounds"):
            provider.download_result_image("https://cdn.genlook-results.example/huge")


class TestPhase5F5AAuditHardening:
    """Tests for defects surfaced during the Phase 5F.5A pre-production audit."""

    def test_download_result_image_blocks_ssrf_urls_and_oversized_content_length(self) -> None:
        server = MockGenlookServer()
        provider = GenlookTryOnProvider(
            GenlookTryOnConfig(api_key=TEST_API_KEY, poll_interval_s=0.01, poll_timeout_s=1.0),
            http_client=server,
        )

        unsafe_urls = [
            "http://cdn.genlook-results.example/out.png",
            "https://localhost/out.png",
            "https://127.0.0.1/out.png",
            "https://169.254.169.254/latest/meta-data/",
            "https://10.0.0.5/out.png",
            "https://internal.service.local/out.png",
            "https://user:pass@cdn.genlook-results.example/out.png",
        ]
        for bad_url in unsafe_urls:
            with pytest.raises(ProviderPayloadError, match="safety validation"):
                provider.download_result_image(bad_url)
        assert len(server.calls) == 0

        # Content-Length exceeding 20 MB is rejected before decoding
        server.next_download_responses.append(
            MockResponse(
                200,
                content=VALID_PNG,
                headers={"Content-Length": str(20 * 1024 * 1024 + 1)},
            )
        )
        with pytest.raises(ProviderPayloadError, match="size out of bounds"):
            provider.download_result_image("https://cdn.genlook-results.example/oversized")

    def test_post_completed_result_download_failure_preserves_generation_id_for_zero_cost_retry(
        self, monkeypatch, env_setup
    ) -> None:
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        monkeypatch.setattr(tryon_app, "get_settings", lambda: _genlook_settings())
        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)

        storage: FakeStorageAdapter = env_setup["storage"]
        repo = env_setup["job_repo"]
        wardrobe_repo = env_setup["wardrobe_repo"]
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(storage.put_object(item.image_ref["key"], VALID_WEBP, content_type="image/webp"))

        # Generation completes (1 credit charged), but temporary CDN URL returns 403
        server.next_download_responses.append(MockResponse(403, content=b"Expired"))

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "audit-5f5a-dl-403"},
        )
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])

        failed = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert failed is not None
        assert failed.status == "failed"
        gl = failed.person_media_ref["genlook"]
        assert gl["generationId"] == "cm8gen_1"
        assert gl["generationStatus"] == "COMPLETED"
        assert gl["creditsCharged"] == 1
        assert gl["refunded"] is False
        assert server.credits == 9

        # Retry resumes GET /generations/cm8gen_1 and succeeds without a second POST /try-on
        retry_resp = client.post(f"/v1/tryon/jobs/{job_id}/retry")
        assert retry_resp.status_code == 202
        done = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert done is not None
        assert done.status == "completed"
        assert server.credits == 9
        tryon_posts = [c for c in server.calls if c["url"].endswith("/try-on")]
        assert len(tryon_posts) == 1

    def test_retry_job_respects_kill_switch_and_max_retry_cap(self, monkeypatch, env_setup) -> None:
        from app.api.errors import ApiError

        repo = env_setup["job_repo"]
        job_id = uuid4()
        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=[str(uuid4())],
            provider="genlook",
            status="failed",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )

        monkeypatch.setattr(tryon_app, "get_settings", lambda: _genlook_settings(tryon_enabled=False))
        with pytest.raises(ApiError) as exc_disabled:
            tryon_app.retry_job(user_id=str(USER_A), job_id=str(job_id), job_repo=repo)
        assert exc_disabled.value.status_code == 503

        monkeypatch.setattr(tryon_app, "get_settings", lambda: _genlook_settings())
        for expected_count in range(1, tryon_app._MAX_TRYON_RETRIES + 1):
            retried = tryon_app.retry_job(user_id=str(USER_A), job_id=str(job_id), job_repo=repo)
            assert retried.retry_count == expected_count
            repo.update_failure(
                job_id=job_id,
                error_code="PROVIDER_TRANSIENT_FAILURE",
                error_message="fail",
                completed_at=datetime.now(timezone.utc),
            )

        with pytest.raises(ApiError) as exc_cap:
            tryon_app.retry_job(user_id=str(USER_A), job_id=str(job_id), job_repo=repo)
        assert exc_cap.value.status_code == 409
        assert exc_cap.value.details.get("kind") == "max_retries_exceeded"

    def test_mock_mode_poll_does_not_mutate_non_mock_jobs(self, monkeypatch, env_setup) -> None:
        repo = env_setup["job_repo"]
        job_id = uuid4()
        repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=[str(uuid4())],
            provider="genlook",
            status="queued",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )
        monkeypatch.setattr(tryon_app, "get_settings", lambda: _genlook_settings(tryon_provider="mock"))
        client = TestClient(app)
        for _ in range(3):
            resp = client.get(f"/v1/tryon/jobs/{job_id}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "queued"
            assert resp.json()["result_media_ref"] is None


class TestPhase5F5A1Remediation:
    """Focused regression tests for Phase 5F.5A.1 critical remediations."""

    def test_genlook_delete_customer_idempotency_and_transient_retry(self) -> None:
        server = MockGenlookServer()
        provider = GenlookTryOnProvider(
            GenlookTryOnConfig(api_key=TEST_API_KEY, max_retries=1, backoff_factor=0.01),
            http_client=server,
        )

        # 204 -> True
        assert provider.delete_customer("user-123") is True
        assert server.deleted_customers == ["user-123"]

        # 200 -> True
        server.next_delete_responses.append(MockResponse(200, {"deleted": True}))
        assert provider.delete_customer("user-123") is True

        # 404 -> False (idempotent already absent)
        server.next_delete_responses.append(MockResponse(404, {"code": "NOT_FOUND"}))
        assert provider.delete_customer("user-123") is False

        # Transient 503 retries once and succeeds
        server.next_delete_responses.append(MockResponse(503, {"code": "UNAVAILABLE"}))
        assert provider.delete_customer("user-123") is True

        # 401 fails closed without leaking API key
        server.next_delete_responses.append(MockResponse(401, {"message": f"bad {TEST_API_KEY}"}))
        with pytest.raises(ProviderAuthError) as exc_info:
            provider.delete_customer("user-123")
        assert TEST_API_KEY not in str(exc_info.value)

    def test_cancel_before_provider_dispatch_never_calls_genlook_or_spends_credit(
        self, monkeypatch, env_setup
    ) -> None:
        server = MockGenlookServer(initial_credits=10)
        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                tryon_provider="genlook",
                genlook_api_key=TEST_API_KEY,
                tryon_enabled=True,
            ),
        )
        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)

        storage: FakeStorageAdapter = env_setup["storage"]
        repo = env_setup["job_repo"]
        wardrobe_repo = env_setup["wardrobe_repo"]
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
            person_media_ref={"key": person_key, "contentHash": "d1"},
        )

        # Cancel immediately before provider upload/try-on
        cancel_resp = TestClient(app).post(f"/v1/tryon/jobs/{job_id}/cancel")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["status"] == "cancelled"
        assert "may still consume a credit" in (cancel_resp.json()["error_message"] or "")

        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=USER_A,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=wardrobe_repo,
            )
        )
        assert len(server.calls) == 0
        assert server.credits == 10

    def test_cancelled_genlook_job_survives_restart_and_retry_reuses_generation_id(
        self, monkeypatch, env_setup
    ) -> None:
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                tryon_provider="genlook",
                genlook_api_key=TEST_API_KEY,
                tryon_enabled=True,
                genlook_poll_interval_s=0.01,
                genlook_poll_timeout_s=2.0,
            ),
        )
        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)

        storage: FakeStorageAdapter = env_setup["storage"]
        repo = env_setup["job_repo"]
        wardrobe_repo = env_setup["wardrobe_repo"]
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
            person_media_ref={"key": person_key, "contentHash": "d-cancel-restart"},
        )

        # Cancel on first poll AFTER POST /try-on created cm8gen_1
        orig_get = server.get

        def _cancel_on_poll(url, **kw):
            if "/generations/" in url:
                tryon_app.cancel_job(user_id=str(USER_A), job_id=str(job_id), job_repo=repo)
                server.get = orig_get  # type: ignore[method-assign]
            return orig_get(url, **kw)

        server.get = _cancel_on_poll  # type: ignore[method-assign]
        asyncio.run(
            tryon_app.execute_tryon_inference(
                job_id=job_id,
                user_id=USER_A,
                job_repo=repo,
                storage=storage,
                wardrobe_repo=wardrobe_repo,
            )
        )

        # Cancellation survives backend restart recovery
        assert tryon_app.recover_interrupted_jobs(repo) == 0
        cancelled = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert cancelled is not None
        assert cancelled.status == "cancelled"
        assert cancelled.person_media_ref["genlook"]["generationId"] == "cm8gen_1"
        assert server.credits == 9

        # Status endpoint exposes credit notice
        status_resp = TestClient(app).get(f"/v1/tryon/jobs/{job_id}")
        assert status_resp.status_code == 200
        assert "may still consume a credit" in (status_resp.json()["error_message"] or "")

        # Retrying resumes cm8gen_1 without a 2nd POST /try-on
        retry_resp = TestClient(app).post(f"/v1/tryon/jobs/{job_id}/retry")
        assert retry_resp.status_code == 202
        done = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert done is not None and done.status == "completed"
        assert server.credits == 9
        assert len([c for c in server.calls if c["url"].endswith("/try-on")]) == 1

    def test_completed_remote_generation_storage_failure_preserves_generation_id(
        self, monkeypatch, env_setup
    ) -> None:
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                tryon_provider="genlook",
                genlook_api_key=TEST_API_KEY,
                tryon_enabled=True,
                genlook_poll_interval_s=0.01,
                genlook_poll_timeout_s=2.0,
            ),
        )
        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)

        storage: FakeStorageAdapter = env_setup["storage"]
        repo = env_setup["job_repo"]
        wardrobe_repo = env_setup["wardrobe_repo"]
        gid = uuid4()
        item = wardrobe_repo.add(USER_A, gid)
        asyncio.run(storage.put_object(item.image_ref["key"], VALID_WEBP, content_type="image/webp"))

        orig_put = storage.put_object

        async def _fail_result_put(key, data, *, content_type="image/webp", custom_metadata=None):
            if "/result." in key:
                raise RuntimeError("Simulated R2 put outage")
            return await orig_put(key, data, content_type=content_type, custom_metadata=custom_metadata)

        monkeypatch.setattr(storage, "put_object", _fail_result_put)

        client = TestClient(app)
        resp = client.post(
            "/v1/tryon/jobs",
            files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
            data={
                "outfit_source": "wardrobe",
                "garment_ids": json.dumps([str(gid)]),
                "consent_version": "tryon-v1",
                "consent_accepted": "true",
            },
            headers={"Idempotency-Key": "r2-put-fail-resume"},
        )
        assert resp.status_code == 202
        job_id = UUID(resp.json()["job_id"])

        failed = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.error_code == "STORAGE_FAILURE"
        assert failed.person_media_ref["genlook"]["generationId"] == "cm8gen_1"
        assert server.credits == 9

        # Restore R2 and retry -> completes without duplicate POST /try-on
        monkeypatch.setattr(storage, "put_object", orig_put)
        retry_resp = client.post(f"/v1/tryon/jobs/{job_id}/retry")
        assert retry_resp.status_code == 202
        done = repo.get_by_id(user_id=USER_A, job_id=job_id)
        assert done is not None and done.status == "completed"
        assert server.credits == 9
        assert len([c for c in server.calls if c["url"].endswith("/try-on")]) == 1

    def test_consistent_12mp_output_limit_across_download_storage_and_retrieval(
        self, monkeypatch, env_setup
    ) -> None:
        from app.config.image import MAX_OUTPUT_IMAGE_PIXELS, MAX_PILLOW_IMAGE_PIXELS, configure_pillow_limits
        from app.domain.ports.tryon_provider import validate_raster_image_bytes

        configure_pillow_limits()
        assert MAX_OUTPUT_IMAGE_PIXELS == 12_000_000
        assert MAX_PILLOW_IMAGE_PIXELS == 12_000_000

        # 12 MP exact (4000x3000) succeeds everywhere
        ok_12mp = _make_image_bytes("PNG", size=(4000, 3000))
        server = MockGenlookServer(result_bytes=ok_12mp)
        provider = GenlookTryOnProvider(
            GenlookTryOnConfig(api_key=TEST_API_KEY, poll_interval_s=0.01, poll_timeout_s=1.0),
            http_client=server,
        )
        assert provider.download_result_image("https://cdn.genlook-results.example/12mp.png") == ok_12mp
        assert validate_raster_image_bytes(ok_12mp, "Out", provider_id="genlook") == "image/png"
        assert tryon_app.validate_and_inspect_output_image(ok_12mp, allow_svg=False, provider_id="genlook") == ("image/png", "png")

        # 14 MP (>12 MP) fails consistently at download, Pillow decode, storage validation, and retrieval
        over_12mp = _make_image_bytes("PNG", size=(4000, 3500))
        server.next_download_responses.append(MockResponse(200, content=over_12mp))
        with pytest.raises(ProviderPayloadError):
            provider.download_result_image("https://cdn.genlook-results.example/14mp.png")
        with pytest.raises(ProviderPayloadError):
            validate_raster_image_bytes(over_12mp, "Out", provider_id="genlook")
        with pytest.raises(ProviderPayloadError):
            tryon_app.validate_and_inspect_output_image(over_12mp, allow_svg=False, provider_id="genlook")

        # Retrieval endpoint also enforces 12 MP ceiling if oversized bytes were stored
        storage: FakeStorageAdapter = env_setup["storage"]
        repo = env_setup["job_repo"]
        job_id = uuid4()
        res_key = f"users/{USER_A}/tryon/{job_id}/result.png"
        asyncio.run(storage.put_object(res_key, over_12mp, content_type="image/png"))
        rec = repo.create(
            job_id=job_id,
            user_id=USER_A,
            outfit_source="wardrobe",
            garment_id=None,
            garment_ids=[str(uuid4())],
            provider="genlook",
            status="processing",
            consent_version="tryon-v1",
            consent_accepted_at=datetime.now(timezone.utc),
        )
        repo.update_result(
            job_id=rec.id,
            result_media_ref={"key": res_key, "mediaType": "image/png", "isMock": False},
            completed_at=datetime.now(timezone.utc),
        )
        img_resp = TestClient(app).get(f"/v1/tryon/jobs/{job_id}/image")
        assert img_resp.status_code == 404

    def test_concurrent_submissions_cannot_exceed_daily_quota_on_postgres(
        self, db, monkeypatch
    ) -> None:
        from concurrent.futures import ThreadPoolExecutor
        from app.infrastructure.db.models import UserState, Users, WardrobeItems
        from app.infrastructure.db.repositories import TryOnJobRepositorySQL, WardrobeItemRepositorySQL

        Session = db
        with Session() as s:
            user = Users(auth_provider="local", auth_subject="quota-race@example.com", display_name="Quota Race")
            s.add(user)
            s.flush()
            s.add(UserState(user_id=user.id))
            garment_id = uuid4()
            s.add(
                WardrobeItems(
                    id=garment_id,
                    user_id=user.id,
                    name="Quota Test Shirt",
                    category_id="tops",
                    color_id="navy",
                    image_ref={"key": f"users/{user.id}/wardrobe/{garment_id}/canonical.webp"},
                )
            )
            s.commit()
            user_id = user.id

        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                tryon_provider="mock",
                tryon_enabled=True,
                tryon_daily_quota_per_user=3,
                tryon_max_concurrent_jobs_per_user=10,
            ),
        )

        def _submit(idx: int) -> tuple[str, bool]:
            with Session() as s:
                repo = TryOnJobRepositorySQL(s)
                wardrobe_repo = WardrobeItemRepositorySQL(s)
                try:
                    job, created = tryon_app.submit_job(
                        user_id=str(user_id),
                        outfit_source="wardrobe",
                        garment_ids=[str(garment_id)],
                        person_content_type="image/jpeg",
                        person_bytes=VALID_JPEG,
                        consent_version="tryon-v1",
                        consent_accepted=True,
                        idempotency_key=f"concurrent-quota-{idx}",
                        wardrobe_repo=wardrobe_repo,
                        job_repo=repo,
                    )
                    return str(job.id), created
                except Exception as exc:
                    return f"ERR:{getattr(exc, 'status_code', type(exc).__name__)}", False

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(_submit, range(8)))

        created_count = sum(1 for _, created in results if created)
        rate_limited_count = sum(1 for val, _ in results if val == "ERR:429")
        assert created_count == 3, results
        assert rate_limited_count == 5, results

        with Session() as s:
            repo = TryOnJobRepositorySQL(s)
            assert repo.count_today_jobs(user_id=user_id, day=datetime.now(timezone.utc).date()) == 3

        # Idempotent replay of an existing key MUST still succeed even at daily quota limit
        def _replay(_idx: int) -> tuple[str, bool]:
            with Session() as s:
                repo = TryOnJobRepositorySQL(s)
                wardrobe_repo = WardrobeItemRepositorySQL(s)
                job, created = tryon_app.submit_job(
                    user_id=str(user_id),
                    outfit_source="wardrobe",
                    garment_ids=[str(garment_id)],
                    person_content_type="image/jpeg",
                    person_bytes=VALID_JPEG,
                    consent_version="tryon-v1",
                    consent_accepted=True,
                    idempotency_key="concurrent-quota-replay-shared",
                    wardrobe_repo=wardrobe_repo,
                    job_repo=repo,
                )
                return str(job.id), created

        # First allow 1 more quota slot, then race 4 identical idempotency keys
        monkeypatch.setattr(
            tryon_app,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                tryon_provider="mock",
                tryon_enabled=True,
                tryon_daily_quota_per_user=4,
                tryon_max_concurrent_jobs_per_user=10,
            ),
        )
        with ThreadPoolExecutor(max_workers=4) as pool:
            replay_results = list(pool.map(_replay, range(4)))

        assert len({jid for jid, _ in replay_results}) == 1
        assert sum(1 for _, created in replay_results if created) == 1
        with Session() as s:
            assert TryOnJobRepositorySQL(s).count_today_jobs(
                user_id=user_id, day=datetime.now(timezone.utc).date()
            ) == 4

        # Replay of an already-accepted key still succeeds even when daily quota is 4/4 full
        replayed_id, replayed_created = _replay(99)
        assert replayed_created is False
        assert replayed_id == replay_results[0][0]


# ==============================================================================
# 8. Phase 5F.5C: Garment Storage Reference & Genlook Dispatch Regression Tests
# ==============================================================================


class TestPhase5F5CGarmentStorageReference:
    """Tests A-H exercising the real wardrobe publication -> repository -> try-on path."""

    @staticmethod
    def _make_sqlite_session():
        from sqlalchemy import create_engine, event
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy.ext.compiler import compiles
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.infrastructure.db.models import (
            Colors,
            LearningSignals,
            Materials,
            MediaUploadAuthorization,
            SignalTypes,
            Users,
            WardrobeCategories,
            WardrobeItems,
        )

        @compiles(JSONB, "sqlite")
        def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover
            return "JSON"

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_fns(dbapi_connection, _connection_record):
            dbapi_connection.create_function(
                "char_length", 1, lambda s: len(s) if s is not None else 0
            )
            dbapi_connection.create_function("gen_random_uuid", 0, lambda: str(uuid4()))

        Users.__table__.create(engine)
        WardrobeCategories.__table__.create(engine)
        Colors.__table__.create(engine)
        Materials.__table__.create(engine)
        SignalTypes.__table__.create(engine)
        LearningSignals.__table__.create(engine)
        MediaUploadAuthorization.__table__.create(engine)
        WardrobeItems.__table__.create(engine)

        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        session = SessionLocal()
        for code, label in (("tops", "Tops"), ("outerwear", "Outerwear"), ("bottoms", "Bottoms")):
            session.add(WardrobeCategories(code=code, label=label, sort_order=1, active=True))
        for code, label in (("navy", "Navy"), ("black", "Black"), ("charcoal", "Charcoal")):
            session.add(Colors(code=code, label=label, sort_order=1, active=True))
        for code, label in (("cotton", "Cotton"), ("linen", "Linen")):
            session.add(Materials(code=code, label=label, sort_order=1, active=True))
        session.add(SignalTypes(code="item_added", label="Item Added", sort_order=1, active=True))
        session.commit()
        return engine, session

    @staticmethod
    def _seed_published_upload(session, user_id: UUID, *, upload_id: UUID | None = None, canonical_key: str | None = None):
        from app.infrastructure.db.models import MediaUploadAuthorization, Users
        from app.application.media import sha256_hex

        if session.get(Users, user_id) is None:
            session.add(
                Users(
                    id=user_id,
                    auth_provider="test",
                    auth_subject=f"sub-{user_id}",
                    display_name="Test User",
                )
            )
            session.flush()

        uid = upload_id or uuid4()
        lease_token = uuid4()
        key = canonical_key or f"users/{user_id}/wardrobe/{uid}/attempts/{lease_token}.webp"
        now = datetime.now(timezone.utc)
        auth = MediaUploadAuthorization(
            upload_id=uid,
            user_id=user_id,
            idempotency_key=f"idem-{uid}",
            key_version="v1",
            request_fingerprint="fp",
            staging_key=f"staging/users/{user_id}/wardrobe/{uid}.webp",
            content_type="image/webp",
            size_bytes=len(VALID_WEBP),
            status="published",
            canonical_key=key,
            canonical_sha256=sha256_hex(VALID_WEBP),
            canonical_size_bytes=len(VALID_WEBP),
            canonical_width=128,
            canonical_height=128,
            completed_at=now,
            expires_at=now + timedelta(hours=24),
        )
        session.add(auth)
        session.commit()
        return auth

    @staticmethod
    def _patch_genlook(monkeypatch, server: MockGenlookServer, settings: Any = None):
        cfg = settings or _genlook_settings()
        monkeypatch.setattr(tryon_app, "get_settings", lambda: cfg)
        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)

    def test_a_and_g_validate_media_association_object_key_reaches_single_garment_genlook_request(
        self, monkeypatch, env_setup
    ) -> None:
        """Test A & Test G: validate_media_association -> WardrobeItemRepositorySQL -> Genlook single-garment dispatch."""
        from urllib.parse import parse_qs, urlparse
        from app.application.wardrobe import AddWardrobeItem
        from app.infrastructure.db.repositories import LearningSignalRepositorySQL, WardrobeItemRepositorySQL
        from app.infrastructure.external.storage import CloudflareR2StorageAdapter

        engine, session = self._make_sqlite_session()
        try:
            auth = self._seed_published_upload(session, USER_A)
            wardrobe_repo = WardrobeItemRepositorySQL(session)
            add_item = AddWardrobeItem(
                wardrobe=wardrobe_repo,
                signals=LearningSignalRepositorySQL(session),
                db=session,
            )
            created_item = add_item(
                user_id=USER_A,
                name="Black Merino Tee",
                category="tops",
                color="black",
                material="cotton",
                isFavorite=False,
                image_ref={"uploadId": str(auth.upload_id), "objectKey": auth.canonical_key},
                fit="regular",
            )
            # Confirm validate_media_association persisted canonical objectKey (and NOT "key")
            reloaded = wardrobe_repo.get_by_id(user_id=USER_A, item_id=created_item.id)
            assert reloaded is not None
            assert reloaded.image_ref is not None
            assert reloaded.image_ref["objectKey"] == auth.canonical_key
            assert "key" not in reloaded.image_ref

            # Wire real R2 SigV4 adapter with mocked S3 backing store containing the published WebP
            r2_objects: dict[str, tuple[bytes, str]] = {auth.canonical_key: (VALID_WEBP, "image/webp")}
            r2 = CloudflareR2StorageAdapter(
                bucket_name="fansivibe-media-dev",
                endpoint_url="https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
                access_key_id="r2-test-ak",
                secret_access_key="r2-test-sk",
                region_name="auto",
            )

            async def _fake_put(key, data, *, content_type="image/webp", custom_metadata=None):
                r2_objects[key] = (data, content_type)
                return SimpleNamespace(key=key, size_bytes=len(data), content_type=content_type)

            async def _fake_exists(key):
                return key in r2_objects

            async def _fake_read(key, *, max_bytes=20 * 1024 * 1024):
                return r2_objects[key][0]

            monkeypatch.setattr(r2, "put_object", _fake_put)
            monkeypatch.setattr(r2, "object_exists", _fake_exists)
            monkeypatch.setattr(r2, "read_object", _fake_read)

            server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
            self._patch_genlook(monkeypatch, server)

            app.dependency_overrides[get_storage_adapter] = lambda: r2
            app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo
            app.dependency_overrides[get_current_user_id] = lambda: USER_A

            client = TestClient(app)
            resp = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("person.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(created_item.id)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "phase5f5c-test-a-1"},
            )
            assert resp.status_code == 202
            job_id = UUID(resp.json()["job_id"])

            job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=job_id)
            assert job is not None
            assert job.status == "completed"
            assert job.error_code is None
            assert server.credits == 9

            tryon_calls = [c for c in server.calls if c["url"].endswith("/try-on")]
            assert len(tryon_calls) == 1
            payload = tryon_calls[0]["json"]
            assert len(payload["products"]) == 1
            product = payload["products"][0]
            assert product["externalId"] == str(created_item.id)
            assert product["title"] == "Black Merino Tee"
            assert "tops" in product["description"]
            assert "black" in product["description"]
            assert payload["output"] == {"aiLabel": True}
            assert "category" not in product
            assert "category" not in payload
            assert payload["person"]["image"]["source"]["id"].startswith("ephemeral/customer/")

            sent_url = product["images"][0]["source"]["url"]
            parsed = urlparse(sent_url)
            qs = parse_qs(parsed.query)
            assert parsed.scheme == "https"
            assert parsed.path == f"/fansivibe-media-dev/{auth.canonical_key}"
            assert qs["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
            assert qs["X-Amz-Expires"] == ["300"]
            assert "X-Amz-Signature" in qs
        finally:
            session.close()
            engine.dispose()

    def test_b_legacy_wardrobe_image_ref_formats_still_work(self, monkeypatch, env_setup) -> None:
        """Test B: documented legacy fields (object_key, canonical_key, canonicalKey, key, agreeing pair, scans/)."""
        from app.infrastructure.db.models import Users
        from app.infrastructure.db.repositories import WardrobeItemRepositorySQL

        engine, session = self._make_sqlite_session()
        try:
            session.add(
                Users(
                    id=USER_A,
                    auth_provider="test",
                    auth_subject="legacy-user-a",
                    display_name="Legacy A",
                )
            )
            session.commit()
            wardrobe_repo = WardrobeItemRepositorySQL(session)
            storage: FakeStorageAdapter = env_setup["storage"]

            key_wardrobe = f"users/{USER_A}/wardrobe/{uuid4()}/canonical.webp"
            key_scan = f"users/{USER_A}/scans/{uuid4()}/input.webp"
            asyncio.run(storage.put_object(key_wardrobe, VALID_WEBP, content_type="image/webp"))
            asyncio.run(storage.put_object(key_scan, VALID_WEBP, content_type="image/webp"))

            legacy_refs = [
                ("object_key", {"object_key": key_wardrobe}, key_wardrobe),
                ("canonical_key", {"canonical_key": key_wardrobe}, key_wardrobe),
                ("canonicalKey", {"canonicalKey": key_wardrobe}, key_wardrobe),
                ("key", {"key": key_wardrobe}, key_wardrobe),
                ("agreeing_pair", {"objectKey": key_wardrobe, "key": key_wardrobe}, key_wardrobe),
                ("legacy_scans", {"key": key_scan}, key_scan),
            ]

            server = MockGenlookServer(initial_credits=20, result_bytes=VALID_PNG)
            self._patch_genlook(monkeypatch, server)
            app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo
            app.dependency_overrides[get_current_user_id] = lambda: USER_A
            client = TestClient(app)

            for idx, (label, ref_dict, expected_key) in enumerate(legacy_refs):
                item = wardrobe_repo.create(
                    user_id=USER_A,
                    name=f"Legacy {label}",
                    category="tops",
                    color="navy",
                    material="cotton",
                    isFavorite=False,
                    image_ref=ref_dict,
                )
                wardrobe_repo.commit()

                resp = client.post(
                    "/v1/tryon/jobs",
                    files={"person_image": ("person.jpg", VALID_JPEG, "image/jpeg")},
                    data={
                        "outfit_source": "wardrobe",
                        "garment_ids": json.dumps([str(item.id)]),
                        "consent_version": "tryon-v1",
                        "consent_accepted": "true",
                    },
                    headers={"Idempotency-Key": f"legacy-fmt-{idx}"},
                )
                assert resp.status_code == 202, label
                job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=UUID(resp.json()["job_id"]))
                assert job is not None and job.status == "completed", label

                last_tryon = [c for c in server.calls if c["url"].endswith("/try-on")][-1]
                sent_url = last_tryon["json"]["products"][0]["images"][0]["source"]["url"]
                assert expected_key in sent_url
        finally:
            session.close()
            engine.dispose()

    def test_c_missing_malformed_url_and_staging_storage_keys_fail_safely(
        self, monkeypatch, env_setup
    ) -> None:
        """Test C: missing, empty, URL-only, URL-in-key, traversal, and staging keys fail safely before Genlook."""
        from app.infrastructure.db.models import Users
        from app.infrastructure.db.repositories import WardrobeItemRepositorySQL

        engine, session = self._make_sqlite_session()
        try:
            session.add(
                Users(
                    id=USER_A,
                    auth_provider="test",
                    auth_subject="badref-user-a",
                    display_name="BadRef A",
                )
            )
            session.commit()
            wardrobe_repo = WardrobeItemRepositorySQL(session)

            bad_refs: list[tuple[str, dict[str, Any] | None]] = [
                ("none", None),
                ("empty_dict", {}),
                ("missing_key_only_upload_id", {"uploadId": str(uuid4())}),
                ("empty_object_key", {"objectKey": ""}),
                ("whitespace_object_key", {"objectKey": "   "}),
                ("non_string_key", {"objectKey": 12345}),
                ("public_url_only", {"url": "https://cdn.example.com/garment.webp"}),
                ("download_url_only", {"downloadUrl": "https://r2.example.com/signed.webp"}),
                ("url_inside_object_key", {"objectKey": "https://evil.example.com/garment.webp"}),
                ("s3_url_inside_key", {"key": f"s3://bucket/users/{USER_A}/wardrobe/g.webp"}),
                ("staging_key", {"objectKey": f"staging/users/{USER_A}/wardrobe/{uuid4()}.webp"}),
                ("traversal", {"objectKey": f"users/{USER_A}/wardrobe/../../other/garment.webp"}),
                ("leading_slash", {"objectKey": f"/users/{USER_A}/wardrobe/{uuid4()}/g.webp"}),
                ("query_in_key", {"objectKey": f"users/{USER_A}/wardrobe/{uuid4()}/g.webp?X-Amz-Expires=300"}),
                ("tryon_namespace", {"objectKey": f"users/{USER_A}/tryon/{uuid4()}/person.jpg"}),
            ]

            server = MockGenlookServer(initial_credits=10)
            self._patch_genlook(monkeypatch, server)
            app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo
            app.dependency_overrides[get_current_user_id] = lambda: USER_A
            client = TestClient(app)

            for idx, (label, bad_ref) in enumerate(bad_refs):
                item = wardrobe_repo.create(
                    user_id=USER_A,
                    name=f"Bad {label}",
                    category="tops",
                    color="black",
                    material=None,
                    isFavorite=False,
                    image_ref=bad_ref,
                )
                wardrobe_repo.commit()

                resp = client.post(
                    "/v1/tryon/jobs",
                    files={"person_image": ("person.jpg", VALID_JPEG, "image/jpeg")},
                    data={
                        "outfit_source": "wardrobe",
                        "garment_ids": json.dumps([str(item.id)]),
                        "consent_version": "tryon-v1",
                        "consent_accepted": "true",
                    },
                    headers={"Idempotency-Key": f"bad-ref-{idx}"},
                )
                assert resp.status_code == 202, label
                job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=UUID(resp.json()["job_id"]))
                assert job is not None
                assert job.status == "failed", label
                assert job.error_code == "PAYLOAD_REJECTED", label
            assert len(server.calls) == 0
            assert server.credits == 10
        finally:
            session.close()
            engine.dispose()

    def test_d_conflicting_storage_key_fields_fail_safely(self, monkeypatch, env_setup) -> None:
        """Test D: conflicting key fields (e.g. objectKey != key) fail safely without silent precedence."""
        from app.api.routers.wardrobe import _to_wire
        from app.infrastructure.db.models import Users
        from app.infrastructure.db.repositories import WardrobeItemRepositorySQL

        engine, session = self._make_sqlite_session()
        try:
            session.add(
                Users(
                    id=USER_A,
                    auth_provider="test",
                    auth_subject="conflict-user-a",
                    display_name="Conflict A",
                )
            )
            session.commit()
            wardrobe_repo = WardrobeItemRepositorySQL(session)
            storage: FakeStorageAdapter = env_setup["storage"]

            k1 = f"users/{USER_A}/wardrobe/{uuid4()}/a.webp"
            k2 = f"users/{USER_A}/wardrobe/{uuid4()}/b.webp"
            asyncio.run(storage.put_object(k1, VALID_WEBP, content_type="image/webp"))
            asyncio.run(storage.put_object(k2, VALID_WEBP, content_type="image/webp"))

            conflicting_refs = [
                {"objectKey": k1, "key": k2},
                {"objectKey": k1, "object_key": k2},
                {"objectKey": k1, "key": ""},
                {"canonical_key": k1, "canonicalKey": k2},
            ]

            server = MockGenlookServer(initial_credits=10)
            self._patch_genlook(monkeypatch, server)
            app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo
            app.dependency_overrides[get_current_user_id] = lambda: USER_A
            client = TestClient(app)

            for idx, ref_dict in enumerate(conflicting_refs):
                item = wardrobe_repo.create(
                    user_id=USER_A,
                    name=f"Conflict {idx}",
                    category="tops",
                    color="black",
                    material=None,
                    isFavorite=False,
                    image_ref=ref_dict,
                )
                wardrobe_repo.commit()

                # Wardrobe wire serializer must also refuse to sign conflicting refs
                wire = asyncio.run(_to_wire(item, storage=storage))
                assert wire.imageUrl is None

                resp = client.post(
                    "/v1/tryon/jobs",
                    files={"person_image": ("person.jpg", VALID_JPEG, "image/jpeg")},
                    data={
                        "outfit_source": "wardrobe",
                        "garment_ids": json.dumps([str(item.id)]),
                        "consent_version": "tryon-v1",
                        "consent_accepted": "true",
                    },
                    headers={"Idempotency-Key": f"conflict-ref-{idx}"},
                )
                assert resp.status_code == 202
                job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=UUID(resp.json()["job_id"]))
                assert job is not None
                assert job.status == "failed"
                assert job.error_code == "PAYLOAD_REJECTED"
            assert len(server.calls) == 0
            assert server.credits == 10
        finally:
            session.close()
            engine.dispose()

    def test_e_cross_user_storage_keys_rejected(self, monkeypatch, env_setup) -> None:
        """Test E: foreign user's objectKey inside caller's wardrobe item is rejected before storage/Genlook."""
        from app.api.routers.wardrobe import _to_wire
        from app.infrastructure.db.models import Users
        from app.infrastructure.db.repositories import WardrobeItemRepositorySQL

        engine, session = self._make_sqlite_session()
        try:
            session.add(Users(id=USER_A, auth_provider="test", auth_subject="cross-a", display_name="Cross A"))
            session.add(Users(id=USER_B, auth_provider="test", auth_subject="cross-b", display_name="Cross B"))
            session.commit()
            wardrobe_repo = WardrobeItemRepositorySQL(session)
            storage: FakeStorageAdapter = env_setup["storage"]

            foreign_key = f"users/{USER_B}/wardrobe/{uuid4()}/canonical.webp"
            asyncio.run(storage.put_object(foreign_key, VALID_WEBP, content_type="image/webp"))

            # Item owned by USER_A but tampered image_ref points to USER_B's key
            tampered = wardrobe_repo.create(
                user_id=USER_A,
                name="Tampered Shirt",
                category="tops",
                color="navy",
                material=None,
                isFavorite=False,
                image_ref={"objectKey": foreign_key},
            )
            # Item owned by USER_B
            foreign_item = wardrobe_repo.create(
                user_id=USER_B,
                name="User B Shirt",
                category="tops",
                color="navy",
                material=None,
                isFavorite=False,
                image_ref={"objectKey": foreign_key},
            )
            wardrobe_repo.commit()

            wire = asyncio.run(_to_wire(tampered, storage=storage))
            assert wire.imageUrl is None

            server = MockGenlookServer(initial_credits=10)
            self._patch_genlook(monkeypatch, server)
            app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo
            app.dependency_overrides[get_current_user_id] = lambda: USER_A
            client = TestClient(app)

            # 1. Tampered cross-user key fails with PAYLOAD_REJECTED before Genlook
            r1 = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("person.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(tampered.id)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "cross-user-key-1"},
            )
            assert r1.status_code == 202
            job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=UUID(r1.json()["job_id"]))
            assert job is not None
            assert job.status == "failed"
            assert job.error_code == "PAYLOAD_REJECTED"

            # 2. Foreign garment ID rejected at submission with 422
            r2 = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("person.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(foreign_item.id)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "cross-user-item-1"},
            )
            assert r2.status_code == 422
            assert len(server.calls) == 0
            assert server.credits == 10
        finally:
            session.close()
            engine.dispose()

    def test_f_missing_r2_object_fails_before_genlook_dispatch(self, monkeypatch, env_setup) -> None:
        """Test F: valid published image_ref whose object is missing in R2 fails before Genlook dispatch."""
        from app.application.wardrobe import AddWardrobeItem
        from app.infrastructure.db.repositories import WardrobeItemRepositorySQL

        engine, session = self._make_sqlite_session()
        try:
            auth = self._seed_published_upload(session, USER_A)
            wardrobe_repo = WardrobeItemRepositorySQL(session)
            item = AddWardrobeItem(wardrobe=wardrobe_repo, db=session)(
                user_id=USER_A,
                name="Missing Object Jacket",
                category="outerwear",
                color="black",
                material="cotton",
                isFavorite=False,
                image_ref={"uploadId": str(auth.upload_id), "objectKey": auth.canonical_key},
            )

            # Storage does NOT contain auth.canonical_key
            server = MockGenlookServer(initial_credits=10)
            self._patch_genlook(monkeypatch, server)
            app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo
            app.dependency_overrides[get_current_user_id] = lambda: USER_A

            resp = TestClient(app).post(
                "/v1/tryon/jobs",
                files={"person_image": ("person.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(item.id)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "missing-r2-obj-1"},
            )
            assert resp.status_code == 202
            job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=UUID(resp.json()["job_id"]))
            assert job is not None
            assert job.status == "failed"
            assert job.error_code == "STORAGE_FAILURE"
            assert len(server.calls) == 0
            assert server.credits == 10
        finally:
            session.close()
            engine.dispose()

    def test_h_mock_catvton_and_commercial_providers_work_with_object_key_and_remain_unaffected(
        self, monkeypatch, env_setup
    ) -> None:
        """Test H: mock, CatVTON, and commercial providers handle canonical objectKey garment refs cleanly."""
        from app.application.wardrobe import AddWardrobeItem
        from app.domain.ports.tryon_provider import CatVTONTryOnProvider, CommercialTryOnProvider
        from app.infrastructure.db.repositories import WardrobeItemRepositorySQL

        engine, session = self._make_sqlite_session()
        try:
            auth = self._seed_published_upload(session, USER_A)
            wardrobe_repo = WardrobeItemRepositorySQL(session)
            item = AddWardrobeItem(wardrobe=wardrobe_repo, db=session)(
                user_id=USER_A,
                name="Provider Compat Shirt",
                category="tops",
                color="navy",
                material="cotton",
                isFavorite=False,
                image_ref={"uploadId": str(auth.upload_id), "objectKey": auth.canonical_key},
            )
            storage: FakeStorageAdapter = env_setup["storage"]
            asyncio.run(storage.put_object(auth.canonical_key, VALID_WEBP, content_type="image/webp"))

            captured_garments: list[tuple[str, bytes | None]] = []

            def _fake_catvton_render(self_p, **kwargs):
                captured_garments.append(("catvton", kwargs.get("garment_bytes")))
                return VALID_PNG

            def _fake_commercial_render(self_p, **kwargs):
                captured_garments.append(("commercial", kwargs.get("garment_bytes")))
                return VALID_PNG

            monkeypatch.setattr(CatVTONTryOnProvider, "render", _fake_catvton_render)
            monkeypatch.setattr(CommercialTryOnProvider, "render", _fake_commercial_render)

            app.dependency_overrides[get_tryon_wardrobe_repository] = lambda: wardrobe_repo
            app.dependency_overrides[get_current_user_id] = lambda: USER_A
            client = TestClient(app)

            for provider_name, cfg_overrides in (
                ("mock", {"tryon_provider": "mock"}),
                ("catvton", {"tryon_provider": "catvton"}),
                (
                    "commercial",
                    {
                        "tryon_provider": "commercial",
                        "tryon_commercial_provider_name": "fashn",
                        "tryon_commercial_api_key": "sk_test_commercial_1234567890",
                        "tryon_commercial_endpoint_url": "https://api.commercial.example/v1/tryon",
                        "tryon_commercial_connect_timeout_s": 5.0,
                        "tryon_commercial_inference_timeout_s": 30.0,
                        "tryon_commercial_max_retries": 0,
                    },
                ),
            ):
                cfg = _genlook_settings(**cfg_overrides)
                monkeypatch.setattr(tryon_app, "get_settings", lambda c=cfg: c)

                r = client.post(
                    "/v1/tryon/jobs",
                    files={"person_image": ("person.jpg", VALID_JPEG, "image/jpeg")},
                    data={
                        "outfit_source": "wardrobe",
                        "garment_ids": json.dumps([str(item.id)]),
                        "consent_version": "tryon-v1",
                        "consent_accepted": "true",
                    },
                    headers={"Idempotency-Key": f"compat-provider-{provider_name}"},
                )
                assert r.status_code == 202
                job_id = UUID(r.json()["job_id"])
                if provider_name == "mock":
                    assert r.json()["is_mock"] is True
                    poll = client.get(f"/v1/tryon/jobs/{job_id}")
                    assert poll.status_code == 200
                    poll = client.get(f"/v1/tryon/jobs/{job_id}")
                    assert poll.json()["status"] == "completed"
                else:
                    job = env_setup["job_repo"].get_by_id(user_id=USER_A, job_id=job_id)
                    assert job is not None and job.status == "completed"

            assert captured_garments == [
                ("catvton", VALID_WEBP),
                ("commercial", VALID_WEBP),
            ]
        finally:
            session.close()
            engine.dispose()


class TestPhase5F5CPostgresWardrobeToGenlook:
    """Full PostgreSQL media upload -> wardrobe create -> try-on Genlook dispatch test."""

    def test_full_pg_media_upload_to_wardrobe_to_genlook_dispatch(self, db, monkeypatch) -> None:
        from app.infrastructure.db.models import (
            Colors,
            Materials,
            MediaUploadAuthorization,
            SignalTypes,
            WardrobeCategories,
        )
        from app.infrastructure.db.repositories import TryOnJobRepositorySQL, WardrobeItemRepositorySQL

        from app.infrastructure.db import session as db_session_mod

        assert (db_session_mod.engine.url.database or "") != "fansivibe"
        tryon_app.reset_for_tests()
        Session = db

        with Session() as s:
            from app.infrastructure.db.models import UserState, Users

            user = Users(auth_provider="local", auth_subject="pg-5f5c@example.com", display_name="PG 5F5C")
            s.add(user)
            s.flush()
            s.add(UserState(user_id=user.id))
            if s.get(WardrobeCategories, "tops") is None:
                s.add(WardrobeCategories(code="tops", label="Tops", sort_order=1, active=True))
            if s.get(Colors, "black") is None:
                s.add(Colors(code="black", label="Black", sort_order=1, active=True))
            if s.get(Materials, "cotton") is None:
                s.add(Materials(code="cotton", label="Cotton", sort_order=1, active=True))
            if s.get(SignalTypes, "item_added") is None:
                s.add(SignalTypes(code="item_added", label="Item Added", sort_order=1, active=True))
            s.commit()
            user_id = user.id

        storage = FakeStorageAdapter()
        server = MockGenlookServer(initial_credits=10, result_bytes=VALID_PNG)
        orig_init = GenlookTryOnProvider.__init__

        def _patched_init(self_p, config, **kw):
            kw.setdefault("http_client", server)
            orig_init(self_p, config, **kw)

        monkeypatch.setattr(GenlookTryOnProvider, "__init__", _patched_init)
        monkeypatch.setattr(tryon_app, "get_settings", lambda: _genlook_settings())

        app.dependency_overrides[get_current_user_id] = lambda: user_id
        app.dependency_overrides[get_storage_adapter] = lambda: storage
        try:
            client = TestClient(app)

            # 1. Authorize upload
            auth_resp = client.post(
                "/v1/media/uploads",
                json={
                    "purpose": "wardrobe_item",
                    "contentType": "image/webp",
                    "sizeBytes": len(VALID_WEBP),
                },
                headers={"Idempotency-Key": "pg-5f5c-upload-1"},
            )
            assert auth_resp.status_code == 201, auth_resp.text
            upload_id = auth_resp.json()["uploadId"]
            staging_key = auth_resp.json()["stagingKey"]

            # 2. Simulate direct PUT to R2 staging
            asyncio.run(storage.put_object(staging_key, VALID_WEBP, content_type="image/webp"))

            # 3. Complete upload -> produces canonical objectKey
            comp_resp = client.post(f"/v1/media/uploads/{upload_id}/complete")
            assert comp_resp.status_code == 200, comp_resp.text
            published_ref = comp_resp.json()
            object_key = published_ref["objectKey"]
            assert object_key.startswith(f"users/{user_id}/wardrobe/{upload_id}/")

            # 4. Create wardrobe item via real HTTP endpoint -> validate_media_association + WardrobeItemRepositorySQL
            w_resp = client.post(
                "/v1/wardrobe/items",
                json={
                    "name": "Published Genlook Tee",
                    "category": "tops",
                    "color": "black",
                    "material": "cotton",
                    "imageRef": {"uploadId": upload_id, "objectKey": object_key},
                },
            )
            assert w_resp.status_code == 201, w_resp.text
            garment_id = UUID(w_resp.json()["id"])

            with Session() as s_chk:
                rec = WardrobeItemRepositorySQL(s_chk).get_by_id(user_id=user_id, item_id=garment_id)
                assert rec is not None and rec.image_ref is not None
                assert rec.image_ref["objectKey"] == object_key
                assert "key" not in rec.image_ref

            # 5. Submit try-on job -> real PostgreSQL TryOnJobRepositorySQL + Genlook dispatch
            t_resp = client.post(
                "/v1/tryon/jobs",
                files={"person_image": ("me.jpg", VALID_JPEG, "image/jpeg")},
                data={
                    "outfit_source": "wardrobe",
                    "garment_ids": json.dumps([str(garment_id)]),
                    "consent_version": "tryon-v1",
                    "consent_accepted": "true",
                },
                headers={"Idempotency-Key": "pg-5f5c-tryon-1"},
            )
            assert t_resp.status_code == 202, t_resp.text
            job_id = UUID(t_resp.json()["job_id"])

            with Session() as s_job:
                job = TryOnJobRepositorySQL(s_job).get_by_id(user_id=user_id, job_id=job_id)
                assert job is not None
                assert job.status == "completed"
                assert job.error_code is None

            tryon_calls = [c for c in server.calls if c["url"].endswith("/try-on")]
            assert len(tryon_calls) == 1
            sent_url = tryon_calls[0]["json"]["products"][0]["images"][0]["source"]["url"]
            assert object_key in sent_url
            assert server.credits == 9
        finally:
            app.dependency_overrides.clear()
            tryon_app.reset_for_tests()



