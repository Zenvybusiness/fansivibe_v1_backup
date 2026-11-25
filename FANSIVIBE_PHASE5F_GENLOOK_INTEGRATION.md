# Fansivibe — Phase 5F: Genlook Commercial VTON API Integration

**Status:** Implemented & Preflight Verified (`GENLOOK_API_KEY` Configured Locally; Mocked Genlook HTTP Service Verified; Live API Smoke Test Gated on Server Startup & Operator Approval)  
**Date:** 2026-11-25  
**Base API:** `https://api.genlook.app/tryon/v1`  

---

## 1. Architecture Mapping

Fansivibe retains its existing hexagonal / feature-first structure without modifying the Flutter wire contract, PostgreSQL schema, or existing `MockTryOnProvider` / `CatVTONTryOnProvider` / `CommercialTryOnProvider` implementations.

| Existing Fansivibe Component | File | Genlook Integration Role |
|---|---|---|
| `TryOnProvider` protocol | [`tryon_provider.py`](backend/app/domain/ports/tryon_provider.py) | Provider port implemented by `GenlookTryOnProvider` (`provider_id = "genlook"`). |
| `GenlookTryOnProvider` | [`genlook_tryon.py`](backend/app/infrastructure/external/genlook_tryon.py) | Dedicated HTTP adapter for Genlook Try-On API v1 (`POST /images/upload`, `POST /try-on`, `GET /generations/{generationId}`, `GET /account/credits`, result download). |
| `MockTryOnProvider` | [`tryon_provider.py`](backend/app/domain/ports/tryon_provider.py) | Unchanged default local test-data provider (`tryon_provider = "mock"`). |
| `CatVTONTryOnProvider` | [`tryon_provider.py`](backend/app/domain/ports/tryon_provider.py) | Unchanged local non-commercial research provider (`tryon_provider = "catvton"`). |
| `CommercialTryOnProvider` | [`tryon_provider.py`](backend/app/domain/ports/tryon_provider.py) | Preserved for existing generic commercial contract compatibility (`tryon_provider = "commercial"`). |
| Try-On Application Service | [`tryon.py`](backend/app/application/tryon.py) | Validates inputs, enforces single-garment + OW-1 wardrobe ownership, generates short-lived signed garment URLs, persists `imageId` / `pendingIdempotencyKey` / `generationId`, confirms result storage, records credit metadata. |
| Try-On Router | [`tryon.py`](backend/app/api/routers/tryon.py) | Existing `/v1/tryon/jobs*` endpoints unchanged for Flutter; `/v1/tryon/health` reports Genlook provider health & credit balance. |
| PostgreSQL Repository | [`repositories.py`](backend/app/infrastructure/db/repositories.py) | `TryOnJobRepositorySQL` (plus `InMemoryTryOnJobRepository`) adds `update_person_media_ref` and `find_reusable_genlook_image_id` using existing `tryon_jobs.person_media_ref` JSONB (zero DB migration). |
| Private Object Storage | [`storage.py`](backend/app/infrastructure/external/storage.py) | `CloudflareR2StorageAdapter` / `FakeStorageAdapter` issues 300s presigned GET URLs for owned garment images and durably stores final try-on outputs under `users/{user_id}/tryon/{job_id}/result.{ext}`. |
| Flutter Try-On Feature | [`try_on_screen.dart`](newproject/flutter_application_1/lib/features/try_on/presentation/try_on_screen.dart) | Unchanged UI; consumes `is_mock: false`, `queued`/`processing`/`completed`/`failed` states, `GET /image` bytes, and AI fit disclaimer. |

---

## 2. API Endpoint Mapping

| Fansivibe Operation | Genlook Endpoint | Request & Auth Details | Response Handling |
|---|---|---|---|
| Person photo upload | `POST /images/upload` | `x-api-key: <GENLOOK_API_KEY>`, `multipart/form-data` with `file`, `crop=true`, `keepForDays=1` (configurable `1\|3\|7`), opaque `externalUserId` (UUID, no PII). Validated <= 10 MB, JPEG/PNG/WebP. | Captures `imageId` and persists it with `imageExpiresAt` in `person_media_ref["genlook"]` before `POST /try-on`. |
| Try-on creation | `POST /try-on` | `x-api-key: <GENLOOK_API_KEY>`, `Idempotency-Key: fv-tryon-{job_id}-a{attemptSeq}`, JSON with single inline `products[0]` (`externalId`, `title`, `description`, `images: [{source: {url: <300s signed R2 URL>}}]`), `person.image.source.id`, `output.aiLabel=true`, `externalUserId`. No invented `category` parameter. | Captures `generationId`, `status`, `productExternalIds`, `x-request-id`, `X-RateLimit-*`, `Idempotency-Replayed` and persists `generationId` before polling. |
| Status polling | `GET /generations/{generationId}` | `x-api-key: <GENLOOK_API_KEY>`. Bounded by `GENLOOK_POLL_TIMEOUT_S` (default 120s) and `GENLOOK_POLL_INTERVAL_S` (default 1s); checks job cancellation every poll. | Maps `PENDING`/`PROCESSING`/`RUNNING` → continue polling; `COMPLETED` → download `resultImageUrl`; `FAILED` → map `errorCode` (`INSUFFICIENT_CREDITS`, `PRODUCT_IMAGE_FETCH_FAILED`, `GENERATION_FAILED`, etc.). |
| Result fetch | `GET <resultImageUrl>` | Server-side fetch **without** `x-api-key` header. Validates HTTP 200, size <= 20 MB, raster magic bytes, and Pillow decoding (no SVG). | Persisted to private storage (`put_object`) + confirmed via `object_exists`, then saved to `result_media_ref` without storing the temporary `resultImageUrl`. |
| Operational health / credits | `GET /account/credits` | `x-api-key: <GENLOOK_API_KEY>`. | Reads `creditBalance` for `/v1/tryon/health` without exposing credentials. |

---

## 3. Configuration Instructions & Environment Variables

Set the following **backend-only** environment variables (never in Flutter):

| Variable | Required | Default | Description |
|---|---|---|---|
| `FANSIVIBE_TRYON_PROVIDER` | Conditional | `mock` | Set to `genlook` to route try-on jobs to Genlook. |
| `FANSIVIBE_TRYON_ENABLED` | No | `true` | Global try-on kill switch (`false` returns 503). |
| `GENLOOK_API_KEY` | Yes when `genlook` | `None` | Genlook API key (`gk_...`). Fails closed if missing; production requires >= 16 chars. |
| `GENLOOK_API_BASE_URL` | No | `https://api.genlook.app/tryon/v1` | Genlook Try-On API v1 base URL (HTTPS required in production). |
| `GENLOOK_CONNECT_TIMEOUT_S` | No | `10.0` | HTTP connect timeout in seconds (`> 0`). |
| `GENLOOK_REQUEST_TIMEOUT_S` | No | `30.0` | HTTP request timeout for upload/create/poll/download (`> 0`). |
| `GENLOOK_POLL_INTERVAL_S` | No | `1.0` | Delay between `GET /generations/{id}` polls (`> 0`). |
| `GENLOOK_POLL_TIMEOUT_S` | No | `120.0` | Maximum polling duration per attempt (`> 0`). |
| `GENLOOK_MAX_RETRIES` | No | `2` | Bounded retry count for transient HTTP/network failures (`>= 0`). |
| `GENLOOK_KEEP_FOR_DAYS` | No | `1` | Genlook person image retention (`1`, `3`, or `7` days max). |
| `GENLOOK_AI_LABEL` | No | `true` | Requests Genlook AI-modified transparency labeling. |

Example template added to [`backend/.env.example`](backend/.env.example) without any real secret.

---

## 4. Provider Lifecycle & Data Flow

1. **Submission (`POST /v1/tryon/jobs`)**:
   - Verifies JWT user identity (`get_current_user_id`), explicit consent (`consent_accepted=true`, `consent_version="tryon-v1"`), idempotency key, daily quota, and active job limit.
   - Enforces `len(garment_ids) == 1` for Genlook and OW-1 ownership via `WardrobeItemRepository.get_by_id`.
   - Validates and sanitizes person photo via Pillow (`<= 10 MB` for Genlook, magic bytes + EXIF/GPS stripped, orientation baked in).
   - Persists person photo to private storage (`users/{user_id}/tryon/{job_id}/person.{ext}`) with `object_exists` confirmation BEFORE returning `202 Accepted` (`is_mock: false`) and scheduling background inference.
2. **Background Execution (`execute_tryon_inference`)**:
   - Confirms person photo and owned wardrobe garment image exist in private storage; issues a 300-second presigned GET URL for the real garment image (never a placeholder).
   - Checks `person_media_ref["genlook"]` for an active `generationId` (resumes polling without re-submitting) or `pendingIdempotencyKey` (replays safely on retry).
   - Checks `find_reusable_genlook_image_id` to reuse an existing `imageId` **only** when user ownership, consent version, SHA-256 `contentHash`, and both Fansivibe retention (`24h`) and Genlook `imageExpiresAt` hold.
   - Uploads person photo via `POST /images/upload` if needed and persists `imageId` immediately.
   - Persists `pendingIdempotencyKey` before `POST /try-on`, then persists `generationId` immediately after `POST /try-on` before polling `GET /generations/{generationId}`.
   - On `COMPLETED`, downloads `resultImageUrl` server-side, validates raster image bytes, stores under `users/{user_id}/tryon/{job_id}/result.{ext}`, confirms `object_exists`, and stores `result_media_ref` (`provider: "genlook"`, `generationId`, `creditsCharged: 1`, no temporary Genlook URL).
3. **Billing Safety & Uncertain States**:
   - In-flight retries on `POST /try-on` (`408/409 IDEMPOTENCY_IN_PROGRESS/5xx/network timeout`) reuse the exact same `Idempotency-Key` (honored by Genlook for 24 hours).
   - If a backend timeout or restart occurs after `POST /try-on` was sent (either with `generationId` saved or `pendingIdempotencyKey` saved), retrying via `POST /v1/tryon/jobs/{id}/retry` either resumes `GET /generations/{generationId}` or replays the same `Idempotency-Key` instead of creating a duplicate paid generation.
   - If Genlook reports `status: "FAILED"`, Genlook automatically refunds the credit; Fansivibe records `creditsCharged: 0, refunded: true` and clears `generationId` / advances `attemptSeq` for any explicit user retry.

---

## 5. Security, Privacy & Compliance Behaviour

- **Credential Isolation:** `GENLOOK_API_KEY` is loaded strictly in backend `Settings` (`repr=False`), excluded from Flutter, logs, API responses, `GET /v1/tryon/health`, and exception messages; log sanitizers scrub `gk_*` and `x-api-key` patterns.
- **Consent & Ownership:** Explicit try-on consent is validated on every job; OW-1 prevents cross-user access to jobs, garments, results, and `imageId` reuse.
- **Retention & Training:**
  - Genlook's privacy policy/terms state a **maximum 7-day retention window** for uploaded photos and generated images, **no AI model training on customer photos or results**, and **no creation of biometric identifiers / faceprints**.
  - Fansivibe defaults `GENLOOK_KEEP_FOR_DAYS=1` (matching Fansivibe's 24h person-photo retention) and preserves `cleanup_retention_data` (24h person photo purge, 12h cancelled, 24h failed, 72h completed).
  - **Pre-production requirement:** Legal/compliance review and execution of the **Genlook Data Processing Agreement (DPA)** (`https://genlook.app/privacy` / `https://genlook.app/terms`) is required before enabling production traffic.
- **Disclosures:** Genlook `aiLabel: true` is sent on generation creation, and Flutter `TryOnScreen` preserves the AI-generated disclosure banner and explicit disclaimer: *"Visual representation only; does not represent physical garment sizing or fit."*

---

## 6. Verification & Test Results

### Automated Backend Tests (Mocked Genlook HTTP Service)
- Command:
  ```bash
  backend/.venv/bin/pytest \
    backend/tests/test_tryon_phase5f_genlook.py \
    backend/tests/test_tryon_mock_api.py \
    backend/tests/test_tryon_phase5c_e2e.py \
    backend/tests/test_tryon_phase5d_commercial_and_reliability.py \
    backend/tests/test_tryon_phase5e_1_security_hardening.py \
    backend/tests/test_tryon_phase5e_2_readiness.py \
    backend/tests/test_tryon_provider_contract_phase5e.py \
    backend/tests/test_tryon_reliability_and_security.py -v
  ```
- Result: **168 passed, 4 skipped** (25/25 new Phase 5F tests in `test_tryon_phase5f_genlook.py` passed; the 4 skipped tests are pre-existing PostgreSQL integration tests in `test_tryon_phase5e_2_readiness.py` skipped because `FANSIVIBE_TEST_DATABASE_URL` is unset).

### Isolated Settings Tests
- Command:
  ```bash
  (cd /tmp && PYTHONPATH=/home/tony/projects/fansivibe_v1_backup/backend /home/tony/projects/fansivibe_v1_backup/backend/.venv/bin/pytest /home/tony/projects/fansivibe_v1_backup/backend/tests/test_settings.py -v)
  ```
- Result: **17 passed**.

### Flutter Analyzer & Try-On Tests
- Command:
  ```bash
  cd newproject/flutter_application_1 && flutter analyze && flutter test test/try_on_genlook_compat_test.dart test/try_on_flow_test.dart test/try_on_phase5d_test.dart
  ```
- Result: `flutter analyze` **0 issues**; `flutter test` **15 passed** (including 2 new Phase 5F Genlook wire/UI compatibility tests).

### Live Genlook API Smoke Test
- **Not executed:** `GENLOOK_API_KEY` is not configured in the local `.env` or environment, so no live Genlook API calls were attempted and zero paid credits were consumed.

---

## 7. Remaining Limitations

1. **Live Genlook API Smoke Test:** Blocked — `GENLOOK_API_KEY` and live Cloudflare R2 credentials (`MEDIA_STORAGE_PROVIDER=r2`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ACCOUNT_ID`/`R2_ENDPOINT_URL`) are unset, and operator confirmation for a paid Genlook request has not yet been given.
2. **Single Garment Scope:** Phase 5F intentionally constrains Genlook requests to 1 owned wardrobe garment per job (`len(garment_ids) == 1`); multi-product outfit try-on is deferred.
3. **Production Gate:** `FANSIVIBE_TRYON_PROVIDER` remains `mock` by default; production traffic remains disabled and Genlook DPA review is required prior to launch.

---

## 8. Phase 5F.1: Live Genlook Verification Attempt (2026-11-25)

| Stage / Area | Status | Details |
|---|---|---|
| 1. Configuration readiness | **BLOCKED** | Defaults (`FANSIVIBE_TRYON_PROVIDER=mock`, `FANSIVIBE_TRYON_ENABLED=true`, `GENLOOK_API_BASE_URL=https://api.genlook.app/tryon/v1`) and `DATABASE_URL` verified; missing live variables: `GENLOOK_API_KEY`, `MEDIA_STORAGE_PROVIDER` (currently `fake`), `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_ACCOUNT_ID` or `R2_ENDPOINT_URL`. |
| 2. PostgreSQL verification | **PASS** | Verified against isolated PostgreSQL database `fansivibe_disposable_test` (Alembic head `0038`; `fansivibe` dev DB untouched) via `TestGenlookPostgresIntegration` (`test_tryon_phase5f_genlook.py`) and `TestPostgresTryOnIntegration` (`test_tryon_phase5e_2_readiness.py`): `update_person_media_ref`, `find_reusable_genlook_image_id`, `generationId` persistence, `imageId` reuse + OW-1 ownership restrictions, consent-version and content-hash checks, retry/restart recovery (`recover_interrupted_jobs`), idempotency replay/conflict (`409`), and completed-job `result_media_ref` persistence. (Genlook HTTP calls in `TestGenlookPostgresIntegration` used `MockGenlookServer`.) |
| 3. R2 readiness | **BLOCKED** | Unit/config/DI/fake storage tests passed (`55/55`); live R2 verification (private upload, temporary signed GET URL accessible to Genlook without auth headers, signed URL expiry, private result persistence) blocked on missing `MEDIA_STORAGE_PROVIDER=r2` and `R2_*` credentials. |
| 4. Live Genlook smoke test | **BLOCKED** | Not executed because Stages 1 & 3 are blocked and operator approval for a paid Genlook API call was not enabled. Zero live Genlook calls made; zero credits spent. |
| 5. Flutter end-to-end (live) | **NOT TESTED** | Live Flutter → FastAPI → R2 → Genlook → PostgreSQL → Flutter flow blocked by Stages 1, 3, and 4. Mocked/widget Flutter compatibility (`try_on_genlook_compat_test.dart`, `try_on_flow_test.dart`, `try_on_phase5d_test.dart`: `15/15` passed; `flutter analyze`: `0` issues) passed. |
| 6. Regression verification | **PASS** | `235/235` backend VTON + storage tests passed against `fansivibe_disposable_test` (0 skipped); `17/17` isolated `test_settings.py` passed; `15/15` Flutter try-on tests passed; `flutter analyze` 0 issues; `backend/.venv` confirmed free of `torch`/`diffusers`/`torchvision`/`detectron2`; `mock` default and `commercial` provider preserved. |

---

## 9. Phase 5F.4A: Genlook Live Try-On Readiness (2026-11-25)

### 9.1 Implementation Readiness & Documentation Comparison (`api.genlook.app/tryon/v1`)

Audited `GenlookTryOnProvider` (`backend/app/infrastructure/external/genlook_tryon.py`), `backend/app/application/tryon.py`, `backend/app/api/routers/tryon.py`, `backend/app/config/settings.py`, `backend/app/infrastructure/db/repositories.py`, `backend/app/infrastructure/external/storage.py`, and `backend/app/main.py` against current official Genlook API documentation:

| Area | Fansivibe Implementation | Official Genlook Docs | Status |
|---|---|---|---|
| API base URL | `https://api.genlook.app/tryon/v1` (`GENLOOK_DEFAULT_BASE_URL` / `GENLOOK_API_BASE_URL`); HTTPS required in production | `https://api.genlook.app/tryon/v1` | **MATCH** |
| Auth header | `x-api-key: <GENLOOK_API_KEY>` sent only to Genlook endpoints; stripped from result CDN fetches (`Accept: image/*`) | `x-api-key: gk_...` | **MATCH** |
| Person image upload | `POST /images/upload` multipart `file`, `crop="true"`, `keepForDays="1"` (`1\|3\|7`), opaque `externalUserId=str(user_id)`. Validated JPEG/PNG/WebP `<= 10 MB` | `POST /images/upload` multipart `file` (JPEG/PNG/WebP/HEIC `<= 10 MB`), `crop` (`true`/`false`), `keepForDays` (`1\|3\|7`), `externalUserId` | **MATCH** (Fansivibe intentionally restricts to JPEG/PNG/WebP for Pillow safety; HEIC rejected at 422) |
| Person image reuse | `person_media_ref["genlook"]["imageId"]` + `imageExpiresAt`; `find_reusable_genlook_image_id` enforces OW-1 user ownership, `consent_version`, `consent_accepted_at`, SHA-256 `contentHash`, 24h retention, `imageExpiresAt > now`; `404 CUSTOMER_IMAGE_NOT_FOUND` triggers automatic re-upload | Reusable `imageId` within `keepForDays` TTL (`1\|3\|7` days) | **MATCH** |
| Garment URL from R2 | `create_confirmed_presigned_input_url` checks `object_exists` and generates 300s SigV4 presigned GET URL (`CloudflareR2StorageAdapter`, path-style HTTPS, no auth header required by caller) | `products[].images[].source.url` publicly/signed-accessible HTTPS URL | **MATCH** (live R2 SigV4 verified in Phase 5F.3B/3C) |
| Single-garment payload | Enforces `len(garment_ids) == 1` & OW-1 wardrobe ownership; inline `products[0]` (`externalId`, `title`, `description`, `images`), `person.image.source.id`, `output.aiLabel`, `externalUserId`; no invented `category` field | `products` (1–4 items), `person.image.source.id`, `output.aiLabel`, `externalUserId` | **MATCH** |
| Idempotency key | `fv-tryon-{job_id}-a{attemptSeq}` persisted to `pendingIdempotencyKey` before `POST /try-on`; sent via `Idempotency-Key` header (`<= 255` ASCII); `409 IDEMPOTENCY_IN_PROGRESS` treated as transient retry; `422 IDEMPOTENCY_KEY_REUSED` fails closed | `Idempotency-Key` header (1–255 ASCII chars, 24h retention, `Idempotency-Replayed: true`, `409 IDEMPOTENCY_IN_PROGRESS`, `422 IDEMPOTENCY_KEY_REUSED`) | **MATCH** |
| Async polling | `GET /generations/{generationId}` every `GENLOOK_POLL_INTERVAL_S` (1.0s) up to `GENLOOK_POLL_TIMEOUT_S` (120.0s); handles `PENDING`, `PROCESSING`, `RUNNING`, `COMPLETED`, `FAILED`; maps `402 INSUFFICIENT_CREDITS`, `429 RATE_LIMITED`, `PRODUCT_IMAGE_FETCH_FAILED`, `GENERATION_FAILED` | `GET /generations/:id` returning `PENDING`/`PROCESSING`/`COMPLETED`/`FAILED`, `resultImageUrl`, `errorCode`, `errorMessage` | **MATCH** |
| Cancellation handling | `POST /v1/tryon/jobs/{id}/cancel` transitions job to `cancelled`; worker checks `_is_job_cancelled()` each poll loop (`GenlookCancelledError`) + post-render/post-storage guards; **Phase 5F.4A fix:** added `.execution_options(populate_existing=True)` to `TryOnJobRepositorySQL.get_by_id` so background sessions with `expire_on_commit=False` observe concurrent DB cancellations immediately | Local polling cancellation (Genlook v1 API does not expose server-side job cancellation endpoint) | **FIXED & VERIFIED** |
| Temporary result URL download | Server-side `GET <resultImageUrl>` without `x-api-key`; validates HTTP 200, `<= 20 MB`, raster magic bytes + Pillow decode (`<= 12 MP`), rejects SVG/HTML/corrupt | Temporary `resultImageUrl` returned on `COMPLETED` | **MATCH** |
| Private R2 result storage & PG persistence | Stored via `storage.put_object` + `object_exists` at `users/{user_id}/tryon/{job_id}/result.{ext}`; temporary `resultImageUrl` never persisted; `person_media_ref["genlook"]` and `result_media_ref` persisted in PostgreSQL `tryon_jobs` | Server-side persistence required because Genlook retention is max 7 days | **MATCH** |
| Retry & restart recovery | `main.py` lifespan calls `recover_interrupted_jobs` (`INTERRUPTED_BY_RESTART`) without clearing `generationId` or `pendingIdempotencyKey`; `POST /v1/tryon/jobs/{id}/retry` resumes `GET /generations/{id}` or replays `Idempotency-Key` | `Idempotency-Key` replay & `GET /generations/:id` status lookup | **MATCH** |

### 9.2 Local Configuration Status (Verified Without Calling `/account/credits`)

- `GENLOOK_API_KEY` (process environment): **Missing**
- `GENLOOK_API_KEY` (`backend/.env`): **Missing**
- `FANSIVIBE_TRYON_PROVIDER` (`backend/.env`): **`mock`** (preserved; not switched)
- `MEDIA_STORAGE_PROVIDER` (`backend/.env`): **`r2`** (`R2_BUCKET_NAME`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` set; live R2 verified in Phase 5F.3C)

### 9.3 Synthetic Image Compatibility & URL Error Matrix (Mocked Genlook HTTP)

Verified via synthetic images in `TestGenlookImageCompatibilityMatrix` (`backend/tests/test_tryon_phase5f_genlook.py`):
- **Supported person formats:** `JPEG`, `PNG`, `WEBP` accepted (`64..4096` px, `<= 12 MP`, `<= 10 MB`), orientation transposed, EXIF/GPS stripped before storage and Genlook upload.
- **Unsupported formats & bounds:** `GIF`, `SVG`, `HEIC`, MIME-spoofed payloads, `< 64px`, `> 4096px`, `> 12 MP` decompression bombs, and `> 10 MB` (`GENLOOK_MAX_IMAGE_BYTES + 1`) rejected with `422` before storage write or any Genlook HTTP call.
- **Garment URL accessibility & R2 TTL:** Real `CloudflareR2StorageAdapter` SigV4 path-style presigned GET URL verified (`https://<account>.r2.cloudflarestorage.com/<bucket>/<key>`, `X-Amz-Algorithm=AWS4-HMAC-SHA256`, `X-Amz-Expires=300`, no auth headers required by Genlook). Missing garment object in R2 fails closed with `STORAGE_FAILURE` (0 credits spent).
- **Expired / inaccessible URL handling:** Genlook `FAILED` with `PRODUCT_IMAGE_FETCH_FAILED` maps to `ProviderPayloadError` (`PAYLOAD_REJECTED`), clears `generationId`, sets `refunded=True`. Result URL `403`/`404`/`410` maps to `ProviderPayloadError`; `503`/timeout maps to `ProviderTransientError` (preserving `generationId` for zero-cost retry).
- **Result image validation:** Accepts raster `JPEG`/`PNG`/`WEBP` (`<= 20 MB`, `<= 12 MP`); rejects SVG, HTML, corrupt payloads, and `> 20 MB` outputs.

### 9.4 First Live Smoke-Test Procedure (Operator-Controlled, Single Generation Only)

> [!CAUTION]
> **DO NOT EXECUTE** without explicit operator confirmation immediately prior to the paid generation. Every live `POST /try-on` call consumes **1 Genlook credit** (unless Genlook marks the generation `FAILED`, in which case Genlook refunds the credit).

#### Preconditions
1. Cloudflare R2 (`fansivibe-media-dev`) and PostgreSQL (Alembic head `0038`) are healthy.
2. Obtain explicit operator approval for **1 single-garment live Genlook generation** (1 credit) using **1 authorised test person photograph** and **1 owned wardrobe garment** on **1 isolated test user account**.
3. Provision `GENLOOK_API_KEY` (`gk_...`) in gitignored `backend/.env` (`chmod 600 backend/.env`) and temporarily set `FANSIVIBE_TRYON_PROVIDER=genlook` (leave `FANSIVIBE_TRYON_ENABLED=true`, `GENLOOK_KEEP_FOR_DAYS=1`, `GENLOOK_AI_LABEL=true`). Never commit `backend/.env` or print keys/signed URLs.
4. Restart the FastAPI server so `get_settings()` loads `genlook` and `r2`.

#### Execution Steps (Single Request, Duplicate-Spend Guarded)
1. **Baseline health & credit check (0 credits consumed):**
   - Call `GET /v1/tryon/health`.
   - Confirm `"status": "healthy"`, `"storage.provider": "r2"`, `"provider.provider": "genlook"`, and record `provider.credit_balance` **before** the test (`CREDITS_BEFORE`). Abort if `credit_balance < 1` or status is `unavailable`.
2. **Prepare 1 test user & 1 wardrobe garment:**
   - Register/login 1 test account (`POST /v1/auth/register` or `/v1/auth/login`) -> obtain Bearer token.
   - Upload 1 garment photo (`POST /v1/media/uploads` -> PUT to R2 -> `POST /v1/media/uploads/{id}/complete`) and create 1 wardrobe item (`POST /v1/wardrobe/items`, e.g., `category: "tops"`) -> `GARMENT_ID`.
3. **Explicit Operator Confirmation Gate:**
   - Confirm: `CREDITS_BEFORE`, single test `USER_ID`, single `GARMENT_ID`, authorised non-sensitive test person photograph (`JPEG`/`PNG`/`WEBP <= 10 MB`), and unique single-use `Idempotency-Key` (e.g., `smoke-genlook-live-001`).
   - **Stop and require explicit operator confirmation before sending step 4.**
4. **Submit exactly 1 generation request:**
   - Send `POST /v1/tryon/jobs` with `Idempotency-Key: smoke-genlook-live-001`, `outfit_source=wardrobe`, `garment_ids=["<GARMENT_ID>"]`, `consent_version=tryon-v1`, `consent_accepted=true`, and the authorised person image.
   - Verify HTTP `202 Accepted` with `"is_mock": false` and record `JOB_ID`.
   - **Duplicate-spend guard:** Do **not** submit a second `POST /v1/tryon/jobs`. If the client disconnects or times out, poll `GET /v1/tryon/jobs/{JOB_ID}` or replay the exact same `Idempotency-Key` (`smoke-genlook-live-001`). Only call `POST /v1/tryon/jobs/{JOB_ID}/retry` if the job reaches `failed` with a transient/restart code (it will resume `generationId` or replay `pendingIdempotencyKey`).
5. **Poll & retrieve 1 result image:**
   - Poll `GET /v1/tryon/jobs/{JOB_ID}` every 1–2s until `status == "completed"` (expect ~8–15s). Confirm `result_media_ref.provider == "genlook"`, `result_media_ref.isMock == false`, and **no** temporary `resultImageUrl` appears in the response.
   - Fetch `GET /v1/tryon/jobs/{JOB_ID}/image` -> confirm HTTP `200`, raster MIME (`image/jpeg`/`image/png`/`image/webp`), and visually inspect the single output image.
6. **Observe credit consumption & clean up:**
   - Call `GET /v1/tryon/health` -> record `CREDITS_AFTER` and verify `CREDITS_BEFORE - CREDITS_AFTER == 1` (or `0` if Genlook failed & auto-refunded).
   - Delete test job/media (`DELETE /v1/tryon/jobs/{JOB_ID}`), test wardrobe item (`DELETE /v1/wardrobe/items/{GARMENT_ID}`), and test account (`DELETE /v1/users/me`).
   - **Immediately revert** `FANSIVIBE_TRYON_PROVIDER=mock` in `backend/.env` and restart FastAPI so no accidental follow-up traffic hits Genlook.

### 9.5 Genlook DPA & Privacy Checklist (Pre-Production Gate — Not Legal Advice)

- [ ] **Execute Genlook DPA:** Review and execute Data Processing Agreement with **Parakeet Labs SASU** (`https://genlook.app/dpa`) under GDPR Art. 28 / applicable privacy laws before any real user traffic.
- [ ] **Subprocessor & Cross-Border Transfer Review:** Review Genlook Annex 3 subprocessors (Google Cloud / Vertex AI, Comfy Cloud, etc.) and validate international data transfer safeguards (e.g., EU/US SCCs) against Fansivibe's target jurisdictions.
- [ ] **Biometric / Appearance Data Notice & Consent:** Legal review of `tryon-v1` consent copy to ensure explicit, informed user consent covering third-party AI try-on processing, temporary upload (`keepForDays=1`), and non-biometric/non-training disclosures.
- [ ] **GDPR Erasure Integration (`DELETE /v1/users/me`):** Fansivibe currently passes opaque `externalUserId` and `keepForDays=1` (24h auto-expiry on Genlook), and `DELETE /v1/users/me` purges local DB + R2 objects; confirm whether immediate synchronous deletion via Genlook erasure API/support channel is required for strict GDPR Art. 17 SLA before production.
- [ ] **AI-Generated Content Disclosure (`aiLabel` / EU AI Act Art. 50):** Confirm `GENLOOK_AI_LABEL=true` remains enabled and Flutter's AI-generated disclosure + sizing disclaimer satisfy target market transparency rules.
- [ ] **Retention Parity Audit:** Verify scheduled execution of `POST /v1/tryon/maintenance/retention-cleanup` (operator-authenticated) enforces 24h person photo / 72h result / 24h failed / 12h cancelled retention in production.

---

## 10. Phase 5F.4B: Genlook Credential Verification & Live-Test Preflight (2026-11-25)

**Zero Genlook API requests made; zero credits endpoint calls; zero credits consumed; `FANSIVIBE_TRYON_PROVIDER` remains `mock`.**

| Check Area | Outcome | Verified Details |
|---|---|---|
| **1. Local Configuration (`Settings` / `get_settings()`)** | **PASS** | Verified from both repository root and `backend/` working directories without printing `.env` or secret values: `GENLOOK_API_KEY` is present and non-empty in `backend/.env` (`0o600`, gitignored; absent from shell `os.environ`) and loads into `Settings.genlook_api_key`; `MEDIA_STORAGE_PROVIDER=r2`; `FANSIVIBE_TRYON_PROVIDER=mock`; `FANSIVIBE_TRYON_ENABLED=true`; `GENLOOK_API_BASE_URL=https://api.genlook.app/tryon/v1`. |
| **2. Provider Initialization (Zero Network)** | **PASS** | Instantiated `GenlookTryOnConfig` and `GenlookTryOnProvider` using the configured key (default client and `_NoNetworkClient` spy, zero network I/O). Confirmed `provider_id="genlook"`, base URL `https://api.genlook.app/tryon/v1`, and in-memory `x-api-key` + `X-Correlation-ID` auth header construction. |
| **3. Secret Redaction** | **PASS** | Confirmed configured key never appears in `Settings.__repr__`, `GenlookTryOnConfig.__repr__`, `sanitize_genlook_text()`, `app.api.errors._sanitize_log_message()`, `_extract_error()`, `_raise_for_http_error()` (`ProviderAuthError`), or `fansivibe` `DEBUG` logs during initialization/header construction. |
| **4. Running Server Configuration** | **FAIL (Not Running)** | No FastAPI / Uvicorn process is currently running on the host (port `8000` unbound). Therefore no running process has loaded the newly configured `GENLOOK_API_KEY` yet. Server was intentionally not started; `FANSIVIBE_TRYON_PROVIDER` remains `mock`. |
| **5. Phase 5F Suite (Mocked HTTP + Disposable PG)** | **PASS** | Executed `tests/test_tryon_phase5f_genlook.py` against isolated `fansivibe_disposable_test`: `32/32 passed` (idempotency keys, cross-session cancellation visibility, retry/restart recovery, secret redaction, synthetic image compatibility). |
| **6. Live Smoke-Test Gate Readiness** | **BLOCKED (Gated)** | **Ready:** R2 private storage (`fansivibe-media-dev` `HeadBucket` healthy at `373.04 ms`), PostgreSQL (`0038`), idempotency & cancellation/retry protections, credit-observation procedure (`GET /v1/tryon/health`), and immediate `mock` rollback. **Remaining before live run:** start FastAPI server, obtain explicit operator approval for 1 paid generation, and stage/select 1 isolated test user, 1 authorised test person image, and 1 owned wardrobe garment image per §9.4. |
| **7. Live Genlook API Call / Credit Check** | **NOT TESTED** | Intentionally skipped per strict Phase 5F.4B restrictions. |

---

## 11. Phase 5F.4C: Backend Startup & Isolated VTON Test Preparation (2026-11-25)

**Zero Genlook API requests made; zero credits endpoint calls; zero credits consumed; `FANSIVIBE_TRYON_PROVIDER` remains `mock`.**

| Stage | Outcome | Verified Details |
|---|---|---|
| **1. FastAPI Startup & Env** | **PASS** | Started FastAPI via `./start.sh` (Uvicorn PID `93731` on `http://100.105.35.91:8000`; `fansivibe-postgres18` healthy at Alembic head `0038`; Ollama `active` with `qwen3-vl:4b-instruct`). Verified `/proc/93731/environ` and `Settings`: `MEDIA_STORAGE_PROVIDER=r2`, `FANSIVIBE_TRYON_PROVIDER=mock`, `GENLOOK_API_KEY` configured, `FANSIVIBE_TRYON_ENABLED` resolves to `True` via `Settings` default. Verified `GET /health` (`200`), `GET /ready` (`200`, `database: connected`), and `GET /v1/tryon/health` (`200`, `status: healthy`, `provider: mock`, `storage: r2` / `fansivibe-media-dev`, `390.66 ms`). |
| **2. R2 Object Inspection** | **PASS (0 deleted)** | Inspected all `18` objects in `fansivibe-media-dev` (`list_objects_v2` + `head_object`, without downloading bytes). All `18` belong to two synthetic test user prefixes (`78776297-042d-47b1-aac0-e4c42b55e624` and `14be85e1-56b5-4fe6-8650-48a35802a422`, `9` objects each: `8` x `885`-byte `person.jpg` + `1` x `1071`-byte mock `result.svg`, `LastModified` `2026-11-25T17:54:37Z`–`17:55:10Z`, `META_KEYS=[]`). Neither UUID exists in `fansivibe` (`users`, `wardrobe_items`, `tryon_jobs` count `0`) or `fansivibe_disposable_test`. All `18` objects preserved untouched. |
| **3. Isolated Test Account** | **PASS** | Created one dedicated VTON test account via `POST /v1/auth/register` (`201`) and verified `POST /v1/auth/login` (`200`) + `GET /v1/users/me` (`200`). Recorded `user_id`: `2e733fa4-22d0-4468-9c9a-411202164510` (`vton-smoke-5f4c-74a37c80@test.fansivibe.invalid`; password and token redacted). |
| **4. Test Images** | **BLOCKED (Awaiting Operator)** | Waiting for operator-provided authorised images: 1 garment image (`image/jpeg` or `image/webp`, `<= 2 MB` per `POST /v1/media/uploads`) and 1 person image with explicit permission (`image/jpeg`, `image/png`, or `image/webp`, `64..4096` px, `<= 12 MP`, `<= 10 MB`). No unpermitted or internet images used; no try-on job created. |
| **5. Readiness Check** | **PARTIAL (Blocked at Stage 4)** | FastAPI running, R2 healthy, isolated test user created, `mock` provider active, zero Genlook requests made. Person image and wardrobe garment staging await operator-provided images. |

---

## 12. Phase 5F.4D: Authorised Test Image Staging Attempt (2026-11-25)

**Status: BLOCKED on missing local test asset files (`~/fansivibe_vton_test_assets/garment.webp` and `~/fansivibe_vton_test_assets/person.jpg`); zero Genlook API requests made; zero credits consumed; `FANSIVIBE_TRYON_PROVIDER` remains `mock`.**

| Task / Area | Outcome | Verified Details |
|---|---|---|
| **1. Test Asset Presence & Limit Validation** | **BLOCKED** | Checked `HOME=/home/tony` (`USER=tony`): `/home/tony/fansivibe_vton_test_assets/` does not exist, and recursive search under `/home/tony` (maxdepth 4), `/home/tony/projects/fansivibe_v1_backup`, and `/tmp` found neither `garment.webp` nor `person.jpg`. Application limits verified in code: wardrobe media (`backend/app/api/schemas/media.py`) accepts `image/webp` / `image/jpeg`, `1..2,097,152` bytes; try-on person image (`backend/app/application/tryon.py`) accepts `image/jpeg` / `image/png` / `image/webp`, `64..4096` px, `<= 12,000,000` pixels, `<= 20 MB` (`<= 10 MB` for Genlook). |
| **2. Person Photo Authorisation** | **BLOCKED** | Cannot verify authorisation/metadata for a non-existent `person.jpg`. No alternative or internet images were substituted. |
| **3. Backend & Storage Baseline** | **PASS** | Confirmed FastAPI (`PID 93731`) healthy via `GET /health` (`200`) and `GET /v1/tryon/health` (`200`, `provider: mock`, `storage: r2` / `fansivibe-media-dev`, `latency_ms: 211.38`). |
| **4. Tasks 3–10 (Upload, Ownership, Cleanup)** | **NOT EXECUTED** | Blocked at Tasks 1–2. No wardrobe upload, no try-on job, no R2 object creation or deletion performed; existing 18 R2 objects remain untouched. |

---

## 13. Phase 5F.4D (Resumed): Authorised Test Image Staging Verification (2026-11-26)

**Status: PASS (all 10 steps verified on `FANSIVIBE_TRYON_PROVIDER=mock` + live private Cloudflare R2 `fansivibe-media-dev`); zero Genlook API requests made; zero credits consumed; original 18 R2 objects preserved byte-for-byte.**

### 13.1 Application Image Validator Results

| Asset | File Size (bytes) | Magic Bytes (Leading Hex) | Detected MIME / Format | Dimensions | Pixel Count | Application Validator Outcome |
|---|---|---|---|---|---|---|
| `/home/tony/fansivibe_vton_test_assets/garment.webp` | `23,886` | `52494646465d000057454250` (`RIFF...WEBP`, `VP8X`) | `image/webp` (`WEBP`) | `500 × 500` | `250,000` | **PASS** (`UploadAuthorizationRequest` + `TranscoderProcessManager` subprocess -> canonical `25,252` bytes `500 × 500` `image/webp`, EXIF stripped, SHA-256 `48e552346ddc5ab3d408b87fef2da0aaef54d4972e3cc84e9a63985b066f4c88`) |
| `/home/tony/fansivibe_vton_test_assets/person.jpg` | `140,429` | `ffd8ffe000104a464946` (`\xff\xd8\xff` JFIF/JPEG) | `image/jpeg` (`JPEG`) | `860 × 1147` | `986,420` | **PASS** (`validate_and_sanitize_person_image` -> sanitized `124,679` bytes `860 × 1147` `image/jpeg`, `exif_len=0`, within `64..4096` px, `<= 12 MP`, and `<= 10 MB` Genlook cap) |

### 13.2 Person-Photo Authorisation & Staging Verification

| Check | Outcome | Verified Details |
|---|---|---|
| **Person-photo authorisation** | **PASS** | Operator (`tony`) placed `/home/tony/fansivibe_vton_test_assets/person.jpg` inside `0700` `tony`-owned directory and explicitly authorised Phase 5F.4D Authorised Test Image Staging. JPEG segment & EXIF/IFD inspection confirmed zero copyright, artist, GPS, or stock tags; `POST /v1/tryon/jobs` enforced `consent_accepted=true` + `consent_version=tryon-v1` strictly under `FANSIVIBE_TRYON_PROVIDER=mock`. |
| **Garment upload & retrieval** | **PASS** | Using isolated test user `2e733fa4-22d0-4468-9c9a-411202164510` against running FastAPI (`PID 93731`): `POST /v1/media/uploads` (`201`, `uploadId=70f0fe47-cda3-45d0-8f78-cca629445cf2`) -> direct R2 PUT (`200`, `23,886` bytes) -> `POST /v1/media/uploads/{id}/complete` (`200`, staging deleted, canonical `25,252` bytes WebP) -> `POST /v1/wardrobe/items` (`201`, `item_id=3a2db077-f45b-474f-b0e0-567a843ac7ac`, `tops`/`black`) -> DB ownership confirmed (`media_upload_authorizations` `published` + `wardrobe_items`) -> `GET /v1/media/url` (`200` + signed R2 GET `200`, SHA-256 verified, signed URL withheld) & `GET /v1/wardrobe/items/{id}` (`200`). |
| **Mock try-on person upload** | **PASS** | `POST /v1/tryon/jobs` (`202`, `job_id=c7acd8d0-8a61-4cc4-97d9-eb7b1a06e4ab`, `is_mock=true`) persisted EXIF-stripped `person.jpg` (`124,679` bytes) to private R2; `GET /v1/tryon/jobs/{id}` polled `processing` (`50%`) -> `completed` (`100%`, mock `result.svg` `1,007` bytes in R2); `GET /v1/tryon/jobs/{id}/image` returned `200` `image/svg+xml` containing `TEST DATA`. |
| **Private R2 & OW-1 isolation** | **PASS** | Unsigned direct R2 HTTP GET returned `400` on all 3 objects (garment, person, result). Unauthenticated API requests returned `401`. Temporary secondary user OW-1 cross-user attempts returned `404` (`GET /v1/media/url` by `uploadId` and `objectKey`, `GET /v1/wardrobe/items/{id}`, `POST /v1/wardrobe/items` referencing owner `uploadId`, `GET /v1/tryon/jobs/{id}`, `GET /v1/tryon/jobs/{id}/image`, `DELETE /v1/tryon/jobs/{id}`, `DELETE /v1/wardrobe/items/{id}`) and `422` (`POST /v1/tryon/jobs` with foreign garment). |
| **R2 object keys created (redacted URLs)** | **RECORDED** | Temporary staging (auto-deleted on `/complete`): `staging/users/2e733fa4-22d0-4468-9c9a-411202164510/wardrobe/70f0fe47-cda3-45d0-8f78-cca629445cf2.webp`. Persisted during test & deleted in cleanup: `users/2e733fa4-22d0-4468-9c9a-411202164510/wardrobe/70f0fe47-cda3-45d0-8f78-cca629445cf2/attempts/bf71e619-bdcb-429f-aad3-084a36498d3e.webp`, `users/2e733fa4-22d0-4468-9c9a-411202164510/tryon/c7acd8d0-8a61-4cc4-97d9-eb7b1a06e4ab/person.jpg`, `users/2e733fa4-22d0-4468-9c9a-411202164510/tryon/c7acd8d0-8a61-4cc4-97d9-eb7b1a06e4ab/result.svg`. |
| **Cleanup & Genlook safety** | **PASS** | Deleted test try-on job (`204`, removing R2 `person.jpg` + `result.svg`), wardrobe item (`204`), canonical garment R2 object, `media_upload_authorizations` row, `learning_signals` row, temporary `user_sessions` row, and temporary OW-1 secondary user (`DELETE /v1/users/me` `204`). Post-cleanup `list_objects_v2` confirmed `18` R2 objects matching pre-run `Size` + `ETag` snapshot (`0` keys for `2e733fa4-22d0-4468-9c9a-411202164510`), DB counts `0` (`wardrobe_items`, `tryon_jobs`, `media_upload_authorizations`, `learning_signals`) with isolated test account and its `2` pre-existing Phase 5F.4C `user_sessions` preserved, `total_genlook_jobs=0`, and `GET /v1/tryon/health` reports `provider: mock`. Zero Genlook HTTP requests made; zero credits consumed. |

---

## 14. Phase 5F.5A: Genlook Live Integration Readiness Audit (2026-11-26)

**Audit-only verification; `FANSIVIBE_TRYON_PROVIDER` remains `mock`; zero Genlook HTTP requests made; zero credits consumed; zero `.env`, R2, or schema changes.**

### 14.1 Audit Scope & Methodology

Audited actual source implementation, ORM/migration definitions, tests, official Genlook developer documentation, and Genlook legal/privacy terms across:
- `backend/app/infrastructure/external/genlook_tryon.py`
- `backend/app/application/tryon.py`
- `backend/app/api/routers/tryon.py`
- `backend/app/api/routers/users.py` & `backend/app/application/auth.py`
- `backend/app/config/settings.py` & `backend/app/config/image.py`
- `backend/app/api/errors.py` & `backend/app/api/deps.py`
- `backend/app/infrastructure/external/storage.py` & `backend/app/domain/ports/storage.py`
- `backend/app/domain/ports/tryon_provider.py` & `backend/app/domain/ports/repositories.py`
- `backend/app/infrastructure/db/repositories.py`, `models.py`, `session.py`, and `alembic/versions/0037_tryon_jobs.py` + `0038_tryon_jobs_idempotency_unique.py`
- `newproject/flutter_application_1/lib/features/try_on/` and `test/try_on_*.dart`

### 14.2 Source-Code Audit Matrix (15 Verification Areas)

| # | Audit Area | Status | Source File & Symbol | Evidence & Findings | Remaining Risk |
|---|---|---|---|---|---|
| 1 | Provider interface compliance | **PASS** | `backend/app/domain/ports/tryon_provider.py` (`TryOnProvider`), `genlook_tryon.py` (`GenlookTryOnProvider`) | `GenlookTryOnProvider` defines `provider_id = "genlook"` and `render(...)` matching `TryOnProvider` protocol (`isinstance(..., TryOnProvider)` verified). | Low: Genlook-specific hooks (`product_spec`, `on_image_uploaded`, `on_generation_created`) are passed via `**kwargs`. |
| 2 | Configuration selection & fail-closed behavior | **PASS** | `settings.py` (`Settings._validate_production_invariants`), `application/tryon.py` (`submit_job`, `retry_job`) | Default `tryon_provider="mock"`; `genlook` fails validation without `GENLOOK_API_KEY` (production requires `>= 16` chars + `https://`); `submit_job` and (fixed) `retry_job` fail closed (`503`) if disabled/unconfigured. | Low: Running FastAPI PID `93731` still holds `mock` in memory until controlled restart. |
| 3 | API-key isolation & log/error redaction | **PASS** | `settings.py` (`genlook_api_key`, `repr=False`), `genlook_tryon.py` (`sanitize_genlook_text`, `GenlookTryOnConfig.__repr__`), `errors.py` (`_sanitize_log_message`) | Key never sent to Flutter or CDN `resultImageUrl`; scrubbed via `gk_*` and `x-api-key` patterns across errors/logs/`__repr__`; `GET /v1/tryon/health` masks errors to class names. | Low: `GENLOOK_API_KEY` sits in process `Settings` memory when loaded; `GET /v1/tryon/health` is unauthenticated (exposes `credit_balance` when `genlook` active). |
| 4 | Official Genlook request structure | **PASS** | `genlook_tryon.py` (`upload_person_image`, `create_tryon`, `build_genlook_product_spec`) | Matches `https://api.genlook.app/tryon/v1`: `x-api-key`, `POST /images/upload` (`file`, `crop`, `keepForDays`, `externalUserId`), `POST /try-on` (`products[0]` inline, `person.image.source.id`, `output.aiLabel`, `Idempotency-Key`, no invented `category`). | Low: Live payload acceptance against Genlook production endpoint is unverified until Phase 5F.5B (`MockGenlookServer` only). |
| 5 | Person image upload & `imageId` reuse | **PASS** | `application/tryon.py` (`validate_and_sanitize_person_image`, `_execute_tryon_inference_impl`), `repositories.py` (`find_reusable_genlook_image_id`) | Magic bytes + Pillow decode + EXIF/GPS strip + `<= 10 MB` cap enforced before upload; reuse requires matching `user_id`, `consent_version`, `consent_accepted_at`, SHA-256 `contentHash`, `< 24h` retention, and `imageExpiresAt > now`; `404 CUSTOMER_IMAGE_NOT_FOUND` falls back to re-upload. | Low: `imageExpiresAt` is computed locally (`now + keepForDays`) because upload response does not return an authoritative expiry timestamp. |
| 6 | Garment URL accessibility & expiry | **PASS** | `application/tryon.py` (`create_confirmed_presigned_input_url`), `storage.py` (`CloudflareR2StorageAdapter`) | Confirms `object_exists` in R2 then generates 300s SigV4 path-style presigned GET URL (`X-Amz-Expires=300`); live R2 200->403 expiry proven in Phase 5F.3C. | Low/Medium: Canonical wardrobe items are transcoded to `image/webp`; Genlook's acceptance of signed R2 WebP product URLs is not yet live-verified until Phase 5F.5B. |
| 7 | Idempotency & duplicate-charge prevention | **PASS** | `application/tryon.py` (`submit_job`, `_execute_tryon_inference_impl`), `genlook_tryon.py` (`create_tryon`), `0038_tryon_jobs_idempotency_unique.py` | DB unique `(user_id, idempotency_key)` + `request_fingerprint` prevents duplicate client submits; `pendingIdempotencyKey` (`fv-tryon-{job_id}-a{attemptSeq}`) persisted before `POST /try-on` and `generationId` persisted immediately after; **audit fix:** post-`COMPLETED` `download_result_image` 4xx no longer clears `generationId` or falsely sets `refunded=True`. | Low: A crash strictly in the millisecond after Genlook writes `generationId` and before `on_generation_created` commits is still protected by replaying `pendingIdempotencyKey` within Genlook's 24h window. |
| 8 | Polling limits, timeout handling & cancellation | **PASS (Backend) / GAP (Flutter UX)** | `genlook_tryon.py` (`poll_generation`), `repositories.py` (`get_by_id`, `update_result`), `try_on_screen.dart` (`_maxPolls`) | Backend polls `GET /generations/{id}` bounded by `GENLOOK_POLL_TIMEOUT_S=120s` / `GENLOOK_POLL_INTERVAL_S=1s`, checks cancellation each poll, and refreshes SQL identity map; **audit fix:** added `populate_existing=True` to `update_status`/`update_result`/`update_failure`/`update_retry`/`update_person_media_ref`/`find_by_idempotency_key` closing the stale-worker race window. | Medium (Flutter UX): Genlook v1 has no remote cancel endpoint (in-flight Genlook credit is not refunded on local cancel); Flutter `TryOnScreen._maxPolls = 30` (30s) times out earlier than backend `120s`. |
| 9 | Retry & backend restart recovery | **PASS** | `main.py` (`lifespan`), `application/tryon.py` (`recover_interrupted_jobs`, `retry_job`) | Startup marks orphaned `queued`/`processing` jobs `INTERRUPTED_BY_RESTART` while keeping `generationId` / `pendingIdempotencyKey`; **audit fix:** `retry_job` now enforces `tryon_enabled`/`off`, `_MAX_TRYON_RETRIES = 3`, and concurrent active job limit. | Low: If server restarts during `POST /try-on` after Genlook charged 1 credit, user must call `/retry` within 24h to replay `Idempotency-Key`. |
| 10 | Result download, MIME validation, decoding & R2 persistence | **PASS** | `genlook_tryon.py` (`download_result_image`), `application/tryon.py` (`validate_and_inspect_output_image`, `_execute_tryon_inference_impl`) | **Audit fix:** Added `_is_safe_result_url` SSRF guard, `follow_redirects=False`, `Content-Length` pre-check, and bounded streaming (`<= 20 MB`); validates magic bytes + Pillow decode (`<= 16.7 MP` output / `<= 8192` px, rejects SVG), stores to private R2 `result.{ext}`, and confirms `object_exists` before DB `completed`. | Low: `validate_raster_image_bytes` uses `12 MP` ceiling while `validate_and_inspect_output_image` allows `16.7 MP` (`MAX_OUTPUT_IMAGE_PIXELS`); if Genlook 2K output exceeds `12 MP`, `validate_raster_image_bytes` would reject it. |
| 11 | Temporary result URL handling | **PASS** | `genlook_tryon.py`, `application/tryon.py`, `routers/tryon.py` | Temporary `resultImageUrl` is downloaded server-side only, never persisted to `tryon_jobs`, and never returned to Flutter (`GET /v1/tryon/jobs/{id}/image` streams private R2 bytes). | Low. |
| 12 | User ownership, consent & quota enforcement | **PASS (API) / GAP (Consent Record)** | `application/tryon.py` (`submit_job`), `repositories.py` (`TryOnJobRepositorySQL`), `deps.py` (`get_current_user_id`) | JWT auth (`401`), OW-1 scoping (`404` cross-user job/image/delete/imageId reuse, `422` foreign garment), daily quota (`20/day`) & active job cap (`2` default in `Settings`) enforced. | High (Compliance): `consent_accepted=true` records API checkbox only; neither backend nor Flutter copy names Genlook/Parakeet Labs SASU or proves depicted-person permission for live photos. |
| 13 | Error classification & safe client responses | **PASS** | `genlook_tryon.py` (`_raise_for_http_error`, `_map_failed_generation`), `application/tryon.py`, `errors.py` | Maps `401/403` -> `PROVIDER_AUTH_ERROR`, `402/429` -> `PROVIDER_QUOTA_EXCEEDED`, `400/404/413/422`/`PRODUCT_IMAGE_FETCH_FAILED`/`CONTENT_POLICY_VIOLATION` -> `PAYLOAD_REJECTED`, `408/5xx`/timeout -> `PROVIDER_TRANSIENT_FAILURE`; client responses emit safe messages only. | Low: `GET /v1/tryon/health` is unauthenticated. |
| 14 | Cleanup & retention behavior | **PASS (Job) / FAIL (Account Erasure)** | `application/tryon.py` (`cleanup_retention_data`, `delete_job_and_media`), `users.py` (`delete_me`), `application/auth.py` (`DeleteAccount`) | `cleanup_retention_data` purges person photos (`24h`), cancelled (`12h`), failed (`24h`), completed (`72h`) from R2 and DB; `DELETE /v1/tryon/jobs/{id}` deletes R2 + DB row; **audit fix:** `get_tryon_job` in `mock` mode no longer triggers mock rendering on historical `genlook` jobs. | High (Privacy/Retention): `DELETE /v1/users/me` (`DeleteAccount`) cascades `tryon_jobs`/`wardrobe_items` rows in PG **without** deleting R2 objects or calling Genlook customer erasure (`externalUserId`), leaving orphaned R2 objects if job/item delete wasn't called first. |
| 15 | Concurrency & race conditions | **PASS** | `repositories.py` (`TryOnJobRepositorySQL`), `application/tryon.py`, `0038_tryon_jobs_idempotency_unique.py` | DB unique constraint `(user_id, idempotency_key)` + race fallback; **audit fix:** `populate_existing=True` across all `TryOnJobRepositorySQL` read/write methods prevents stale identity-map overwrites; `_BYTE_CACHE` evicted in `finally`. | Low: `tryon_daily_quota_per_user` check-then-insert has no per-user advisory lock (unlike `media` uploads), so simultaneous requests with different idempotency keys could slightly exceed daily quota under burst concurrency. |

### 14.3 Official Genlook API Contract Verification (Checked 2026-11-26)

Primary sources checked via web search on **2026-11-26**:
- Genlook Try-On API v1 documentation & OpenAPI reference (`https://genlook.app/docs`, `https://api.genlook.app/tryon/v1/openapi.json`)
- Genlook Legal & Privacy (`https://genlook.app/terms`, `https://genlook.app/privacy`, `https://genlook.app/dpa`)

| Contract Item | Confirmed Official Genlook Behavior | Fansivibe Implementation | Unverified Assumptions |
|---|---|---|---|
| Base URL & Auth | `https://api.genlook.app/tryon/v1`; `x-api-key: gk_...` header | Matches (`GENLOOK_DEFAULT_BASE_URL`, `_auth_headers`) | Exact key rate tier / workspace limits on operator's `gk_*` key |
| Person upload (`POST /images/upload`) | Multipart `file` (`JPEG`/`PNG`/`WebP`/`HEIC <= 10 MB`), `crop`, `keepForDays` (`1\|3\|7`), `externalUserId`; returns `imageId`, `imageUrl` | Sends `file` (`JPEG`/`PNG`/`WebP <= 10 MB`), `crop="true"`, `keepForDays="1"`, `externalUserId=str(user_id)`; stores `imageId` | Whether live response includes `expiresAt` field or relies on `keepForDays` |
| Try-on create (`POST /try-on`) | JSON `products` (1–4 inline `{externalId, title, description, images}`), `person.image.source.id`, `output.aiLabel`, `Idempotency-Key` (1–255 ASCII, 24h TTL); returns `generationId` | Sends single inline `products[0]` with 300s R2 SigV4 URL, `person.image.source.id`, `output.aiLabel=true`, `Idempotency-Key: fv-tryon-{job_id}-a{seq}` | Live fetch of Cloudflare R2 SigV4 `.webp` garment URL by Genlook workers |
| Polling & results (`GET /generations/:id`) | States `PENDING`, `PROCESSING`, `COMPLETED` (`resultImageUrl`), `FAILED` (`errorCode`, `errorMessage`); failed jobs auto-refund credits | Polls bounded by `120s` / `1s`; handles `RUNNING` defensively; downloads `resultImageUrl` without `x-api-key` | Exact CDN host & expiry TTL of `resultImageUrl` |
| Credits, rate limits & errors | 1 credit per standard 1-garment try-on; `402 INSUFFICIENT_CREDITS`; `429 RATE_LIMITED` (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`, default 20 concurrent); `{code, message, status}` | `GET /account/credits` in `check_credits`; maps `402`, `429`, `409 IDEMPOTENCY_IN_PROGRESS`, `404 CUSTOMER_IMAGE_NOT_FOUND`, `401/403`, `408/5xx` | Exact error code strings for every failure mode on live API |
| Erasure & free test mode | `client.customers.delete` / `externalUserId` deletion; `mock: true` / title `"mock"` test mode | Passes opaque `externalUserId` on upload & create; uses local `MockTryOnProvider` instead of Genlook `mock` mode | `DELETE` REST path for `externalUserId` not yet wired into `DELETE /v1/users/me` |

### 14.4 Commercial, Privacy, Consent & AI Transparency Findings

- **Genlook ToS (`https://genlook.app/terms`, Parakeet Labs SASU, French law):** Permits business/API integration (`api.genlook.app`); customer retains rights to submitted content (must hold proper authorization); prohibits reselling the standalone Genlook service, uploading photos without consent, violating privacy/biometric laws, or presenting outputs as guaranteed physical fit. **Unresolved:** Operator/legal confirmation that Fansivibe's consumer mobile app B2C usage falls cleanly under permitted API usage without reselling restrictions.
- **Genlook DPA (`https://genlook.app/dpa`):** Automatically incorporated upon API key usage; Fansivibe = Controller, Parakeet Labs SASU = Processor; 48h breach notification; 30-day subprocessor change notice; SCCs / EU-UK-Swiss-US transfer mechanisms; 7-day max photo deletion and explicit no-AI-training guarantee. **Annex 3 subprocessors:** Google Cloud (Cloud Storage, BigQuery — EU), Google Cloud (Vertex AI, Gemini — Global), RunPod (EU / US entity), Comfy Cloud. **Blocker:** Repository has no record that the operator has actually reviewed and accepted the ToS/DPA and Annex 3 subprocessors.
- **Person-Photo Consent:** Operator placing `person.jpg` in `~/fansivibe_vton_test_assets/` and `consent_accepted=true` (`tryon-v1`) + clean JPEG EXIF do **not** constitute proof of the depicted person's legal consent to transmit their image to Genlook and its subprocessors. Before Phase 5F.5B, the operator must record who is depicted and hold verifiable written/first-party consent from that person (or verify non-personal/licensed synthetic origin). Production Flutter consent text (`try_on_screen.dart:864`) must also disclose third-party AI processing (Genlook / Parakeet Labs SASU) before customer launch.
- **AI Transparency (`aiLabel`):** `GENLOOK_AI_LABEL=true` sends `output.aiLabel=true` (Genlook applies EU AI Act Art. 50 "AI modified" marking), and Flutter `TryOnScreen` renders `"AI Try-On Result"` + `"Visual representation only; does not represent physical garment sizing or fit."` when `is_mock == false`.

### 14.5 Defects Corrected During Phase 5F.5A Audit

1. **Stale SQLAlchemy identity-map mutations (`backend/app/infrastructure/db/repositories.py`):** Added `.execution_options(populate_existing=True)` to `TryOnJobRepositorySQL.update_status`, `update_result`, `update_failure`, `update_retry`, `update_person_media_ref`, and `find_by_idempotency_key` so background worker sessions with `expire_on_commit=False` cannot overwrite a concurrent `cancelled` commit.
2. **Result download SSRF & unbounded read (`backend/app/infrastructure/external/genlook_tryon.py`):** Added `_is_safe_result_url` blocking `http://`, userinfo, `localhost`, `.local`/`.internal`, and private/loopback/link-local/reserved IP literals on `resultImageUrl`; enforced `follow_redirects=False`, case-insensitive `Content-Length` pre-check, and bounded streaming (`<= 20 MB`).
3. **False `refunded=True` & lost `generationId` on post-`COMPLETED` download failure (`backend/app/application/tryon.py` & `genlook_tryon.py`):** Tagged download failures (`RESULT_DOWNLOAD_REJECTED`) so `execute_tryon_inference` preserves `generationId`, `generationStatus="COMPLETED"`, `creditsCharged=1`, and `refunded=False`, preventing duplicate paid `POST /try-on` on retry.
4. **Retry kill-switch & cap (`backend/app/application/tryon.py`):** `retry_job` now enforces `tryon_enabled`, `tryon_provider != "off"`, production invariants, `_MAX_TRYON_RETRIES = 3`, and concurrent active job limit.
5. **Mock polling guard (`backend/app/api/routers/tryon.py`):** Restricted `poll_job` in `get_tryon_job` to `job.provider == "mock" and job.status in ("queued", "processing")` so reverting to `mock` never mutates historical `genlook` jobs.

### 14.6 Phase 5F.5A Test Verification (Zero Live External Calls)

- **Isolated Settings & Storage Config:**
  `cd /tmp && env -i PATH="$PATH" PYTHONPATH=/home/tony/projects/fansivibe_v1_backup/backend /home/tony/projects/fansivibe_v1_backup/backend/.venv/bin/pytest /home/tony/projects/fansivibe_v1_backup/backend/tests/test_settings.py /home/tony/projects/fansivibe_v1_backup/backend/tests/test_storage_config.py -v` -> **34 passed** (0.88s).
- **Backend VTON, Genlook, R2 & Media Security Suites (`fansivibe_disposable_test`, `FANSIVIBE_TRYON_PROVIDER=mock`):**
  `cd backend && FANSIVIBE_TRYON_PROVIDER=mock FANSIVIBE_TEST_DATABASE_URL="postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe_disposable_test" .venv/bin/pytest tests/test_tryon_phase5f_genlook.py tests/test_tryon_mock_api.py tests/test_tryon_phase5c_e2e.py tests/test_tryon_phase5d_commercial_and_reliability.py tests/test_tryon_phase5e_1_security_hardening.py tests/test_tryon_phase5e_2_readiness.py tests/test_tryon_provider_contract_phase5e.py tests/test_tryon_reliability_and_security.py tests/test_r2_phase5f2_readiness.py tests/test_storage_adapter.py tests/test_storage_di.py tests/test_fake_storage.py tests/test_media_api.py tests/test_media_association_p4.py -v` -> **337 passed, 0 skipped** (16.86s; includes 5 new Phase 5F.5A hardening tests).
- **Flutter Analyze & Try-On Compatibility:**
  `cd newproject/flutter_application_1 && flutter analyze && flutter test test/try_on_genlook_compat_test.dart test/try_on_flow_test.dart test/try_on_phase5d_test.dart` -> `flutter analyze` **0 issues**; `flutter test` **15 passed**.

### 14.7 Phase 5F.5B Controlled Live Smoke-Test Readiness Checklist

1. **[OPERATOR APPROVAL REQUIRED] DPA & ToS Sign-Off:** Operator confirms review and acceptance of `https://genlook.app/terms`, `https://genlook.app/privacy`, and `https://genlook.app/dpa` (including Annex 3 subprocessors: Google Cloud, Vertex AI/Gemini, RunPod, Comfy Cloud) and confirms B2C API eligibility.
2. **[OPERATOR APPROVAL REQUIRED] Depicted Person Authorisation:** Operator verifies and records who is depicted in `/home/tony/fansivibe_vton_test_assets/person.jpg` and confirms documented permission from that person for cloud VTON processing by Genlook and its subprocessors.
3. **Isolated Test Account & Garment:** Use isolated test account (`2e733fa4-22d0-4468-9c9a-411202164510`) and upload `/home/tony/fansivibe_vton_test_assets/garment.webp` via `POST /v1/media/uploads` -> R2 -> `/complete` -> `POST /v1/wardrobe/items`.
4. **[OPERATOR APPROVAL REQUIRED] Provider Switch & Server Restart:** Switch `FANSIVIBE_TRYON_PROVIDER=genlook` in `backend/.env` (keeping `GENLOOK_KEEP_FOR_DAYS=1`, `GENLOOK_AI_LABEL=true`, `MEDIA_STORAGE_PROVIDER=r2`), restart FastAPI (`PID 93731` must be replaced to load `genlook` + Phase 5F.5A fixes), and verify `GET /ready` (`200`) and `/proc/<pid>/environ` without printing secrets.
5. **Pre-Test Credit Balance Check (0 credits):** Call `GET /v1/tryon/health`, verify `storage.provider == "r2"`, `provider.provider == "genlook"`, `status == "healthy"`, and record `CREDITS_BEFORE` (`>= 1`).
6. **[OPERATOR APPROVAL REQUIRED] Maximum 1 Paid Generation:** Explicitly authorize 1 single-garment `POST /v1/tryon/jobs` call with unique `Idempotency-Key` (e.g., `smoke-genlook-5f5b-001`), `consent_version=tryon-v1`, `consent_accepted=true`. Never submit a second `POST /v1/tryon/jobs` on timeout; only poll `GET /v1/tryon/jobs/{id}` or replay the exact key.
7. **Expected Credit Consumption & Result Validation:** Expect `1` credit consumed (`CREDITS_BEFORE - CREDITS_AFTER == 1`) on `COMPLETED` (or `0` if `FAILED` and auto-refunded). Verify `GET /v1/tryon/jobs/{id}/image` returns `200` raster image (no SVG, no temporary `resultImageUrl` leaked).
8. **Private R2 Storage & Retention Check:** Verify `person.{ext}` and `result.{ext}` exist in private R2 (`fansivibe-media-dev`), unsigned GET returns `400`, and OW-1 cross-user access returns `404`.
9. **Post-Test Credit Reconciliation, Cleanup & Immediate Mock Revert:** Call `GET /v1/tryon/health` to record `CREDITS_AFTER`; delete test job (`DELETE /v1/tryon/jobs/{id}`), wardrobe item (`DELETE /v1/wardrobe/items/{id}`), and test session/account (`DELETE /v1/users/me` *after* job & garment deletion); verify R2 bucket matches baseline `18` objects; **[OPERATOR APPROVAL REQUIRED / MANDATORY]** revert `FANSIVIBE_TRYON_PROVIDER=mock` in `backend/.env` and restart FastAPI immediately.
10. **Failure & Refund Handling:** If generation fails with `GENERATION_FAILED` or `PRODUCT_IMAGE_FETCH_FAILED`, record `errorCode`, verify `CREDITS_AFTER == CREDITS_BEFORE` (auto-refund), do NOT automatically retry without operator approval, and revert to `mock`.

### 14.8 Phase 5F.5A Readiness Decision

**Decision:** **`CONDITIONALLY READY — SPECIFIC OPERATOR ACTIONS REQUIRED.`**

- **Blocking Phase 5F.5B:** (1) Operator review/acceptance of Genlook ToS & DPA (`genlook.app/dpa`), (2) verifiable depicted-person consent record for `person.jpg`, (3) explicit operator authorization for 1 paid generation + server restart on `genlook` + immediate revert to `mock`.
- **Additional Blockers Before Customer/Production Launch:** Implement R2 object purge + Genlook `externalUserId` erasure inside `DELETE /v1/users/me`; update Flutter `TryOnScreen` (`_maxPolls` 30s -> >=120s, third-party Genlook consent disclosure, non-mock CTA text); authenticate/rate-limit `GET /v1/tryon/health`; and align `validate_raster_image_bytes` (`12 MP`) vs `MAX_OUTPUT_IMAGE_PIXELS` (`16.7 MP`) if 2K Genlook outputs are ever enabled.

---

## 15. Phase 5F.5A.1: Pre-Live Critical Remediation (2026-11-26)

**Remediation-only verification; `FANSIVIBE_TRYON_PROVIDER` remains `mock`; zero Genlook HTTP requests made; zero credits consumed; zero database migrations; zero commits/pushes.**

### 15.1 Technical Remediations Completed

1. **Task 1 — Complete Account Erasure (`DELETE /v1/users/me`):**
   - Added `EraseAccount` (`backend/app/application/auth.py`), `AuthRepositorySQL.account_exists` and `AuthRepositorySQL.collect_user_media_keys` (`backend/app/infrastructure/db/repositories.py`), `CloudflareR2StorageAdapter.list_keys` (`backend/app/infrastructure/external/storage.py`, mirrored in `FakeStorageAdapter`), and `GenlookTryOnProvider.delete_customer` (`backend/app/infrastructure/external/genlook_tryon.py`, implementing the official `DELETE /customers/{externalUserId}` contract returning `200`/`204`/`404` idempotently).
   - Wired `DELETE /v1/users/me` (`backend/app/api/routers/users.py`) to collect DB media keys (`media_upload_authorizations` staging/canonical, `wardrobe_items.image_ref`, `tryon_jobs.person_media_ref`/`result_media_ref`, `analysis_runs.input_media`) plus user-scoped R2 prefix scans (`users/{user_id}/`, `staging/users/{user_id}/`), purge R2 objects BEFORE deleting the PG `users` row, invoke `delete_customer(str(user_id))` ONLY when `tryon_provider == "genlook"` (zero calls in `mock`), and then cascade-delete PG records and clear in-memory caches.
   - Any transient storage or Genlook failure aborts BEFORE deleting `users` / `user_sessions` and returns `503`, keeping the caller's session alive for safe, idempotent retry without orphaned R2 objects. Live Genlook `DELETE /customers/{externalUserId}` execution remains unverified on the live Genlook endpoint until Phase 5F.5B/operator testing due to the zero-Genlook-API-call restriction.
2. **Task 2 — Health Endpoint Separation & Access Control (`GET /v1/tryon/health`):**
   - Restricted `GET /v1/tryon/health` (`include_in_schema=False`) via `require_operator_auth` (`X-Operator-Key`), rejecting unauthenticated callers and user JWTs (`401`) and wrong keys (`403`), and failing closed (`503`) if unconfigured.
   - Separated `local_backend`, `storage` (R2 `HeadBucket`), and `provider_config` (local settings/client validation only — zero outbound `/account/credits` requests on ordinary health checks).
   - Isolated external provider credit/account checks into `GET /v1/tryon/health/credits` (`require_operator_auth`, `include_in_schema=False`).
3. **Task 3 — Atomic Quota Concurrency (`TryOnJobRepositorySQL.create_with_quota`):**
   - Added `TryOnJobRepositorySQL.create_with_quota` (`backend/app/infrastructure/db/repositories.py`) and `InMemoryTryOnJobRepository.create_with_quota` (`backend/app/application/tryon.py`), plus protocol signature in `backend/app/domain/ports/repositories.py`.
   - Serializes per-user quota checks and inserts in PostgreSQL using transaction-scoped `pg_advisory_xact_lock` (`tryon_job_quota:{user_id}`) with `SET LOCAL lock_timeout = '3s'`, re-checking `find_by_idempotency_key`, `count_today_jobs`, and `count_active_jobs` inside the lock before insert. Preserves idempotent replay (`created=False`) even when the daily quota is full.
4. **Task 4 — Flutter Polling & Lifecycle Alignment (`TryOnScreen`):**
   - Updated `newproject/flutter_application_1/lib/features/try_on/presentation/try_on_screen.dart` from `_maxPolls = 30` (~30s) to `defaultMaxPollDuration = Duration(seconds: 135)` (aligned with backend 120s Genlook timeout + upload/download headroom).
   - Added `WidgetsBindingObserver` lifecycle handling to pause ticks while backgrounded (`paused`/`hidden`) and poll immediately on `resumed` using wall-clock elapsed time.
   - Separated client polling timeout (`_Phase.timedOut`, `'Still processing'` + `'Check Status'`) from provider generation failure (`_Phase.failed`), preserving `_activeJobId` and `_pendingIdempotencyKey` across polling timeouts and submit-failure retries without triggering duplicate `POST /v1/tryon/jobs` or `POST /retry` calls.
5. **Task 5 — Cancellation & Retry Billing Safety:**
   - Added `is_cancelled_fn` guards inside `GenlookTryOnProvider.render` (`backend/app/infrastructure/external/genlook_tryon.py`) before `upload_person_image`, `create_tryon`, and re-upload on `GenlookImageExpiredError`, plus pre-dispatch check in `_execute_tryon_inference_impl` (`backend/app/application/tryon.py`).
   - Added user-facing remote cancellation credit notice in `routers/tryon.py` (`_cancelled_notice_for_job` on both `POST /cancel` and `GET /jobs/{id}`) and Flutter `TryOnScreen` explaining that an already-submitted remote generation may still consume a credit.
   - Verified `generationId`, `status="cancelled"`, and bounded `_MAX_TRYON_RETRIES = 3` survive `recover_interrupted_jobs` (backend restart), and completed remote generations whose storage/output steps fail retain `generationId` for zero-cost retry.
6. **Task 6 — Consistent Result Image Validation (12 MP):**
   - Standardized `MAX_OUTPUT_IMAGE_PIXELS = 12_000_000` and `MAX_PILLOW_IMAGE_PIXELS = 12_000_000` (`backend/app/config/image.py`), matching `MAX_PERSON_IMAGE_PIXELS` and `validate_raster_image_bytes` (`backend/app/domain/ports/tryon_provider.py`, now importing `MAX_OUTPUT_IMAGE_PIXELS` directly instead of duplicating a constant). Avoided raising limits (raising to 16.7 MP would increase uncompressed RGBA buffer RAM from ~48 MB to ~67 MB per concurrent image decode). Enforced consistently across download validation, Pillow decoding, R2 result storage validation, and `GET /v1/tryon/jobs/{id}/image`.

### 15.2 Git Inventory Reconciliation (Pre-Existing vs Phase 5F.5A vs Phase 5F.5A.1)

- **Modified before Phase 5F.5A (Phase 5F / 5F.2 / 5F.3A / 5F.3C / 5F.4A / 5F.4D):**
  `backend/.env.example`, `backend/app/api/errors.py`, `backend/app/config/settings.py`, `backend/app/infrastructure/external/storage.py` (pre-existing R2 hardening; `list_keys` added in 5F.5A.1), `backend/app/domain/ports/repositories.py` (`update_person_media_ref`/`find_reusable_genlook_image_id` pre-5F.5A; `create_with_quota` added in 5F.5A.1), `backend/tests/test_media_api.py`, `backend/tests/test_storage_config.py`.
- **Untracked pre-existing (created before Phase 5F.5A):**
  `FANSIVIBE_PHASE5F2_R2_SETUP.md`, `FANSIVIBE_PHASE5F_GENLOOK_INTEGRATION.md` (updated in 5F.5A & 5F.5A.1), `backend/app/infrastructure/external/genlook_tryon.py` (updated in 5F.5A & 5F.5A.1), `backend/scripts/`, `backend/tests/test_r2_phase5f2_readiness.py` (updated in 5F.5A.1), `backend/tests/test_tryon_phase5f_genlook.py` (updated in 5F.5A & 5F.5A.1), `experiments/vton_catvton/repo/`, `newproject/flutter_application_1/test/try_on_genlook_compat_test.dart` (updated in 5F.5A.1).
- **Modified during Phase 5F.5A (audit fixes):**
  `backend/app/api/routers/tryon.py`, `backend/app/application/tryon.py`, `backend/app/infrastructure/db/repositories.py`, `backend/app/infrastructure/external/genlook_tryon.py`, `backend/tests/test_tryon_phase5f_genlook.py`, `FANSIVIBE_PHASE5F_GENLOOK_INTEGRATION.md`, `CURRENT_STATE.md`.
- **Modified during Phase 5F.5A.1 (critical remediation):**
  `backend/app/api/routers/users.py`, `backend/app/application/auth.py`, `backend/app/infrastructure/external/storage.py`, `backend/app/infrastructure/external/genlook_tryon.py`, `backend/app/api/routers/tryon.py`, `backend/app/application/tryon.py`, `backend/app/domain/ports/repositories.py`, `backend/app/infrastructure/db/repositories.py`, `backend/app/config/image.py`, `backend/app/domain/ports/tryon_provider.py`, `newproject/flutter_application_1/lib/features/try_on/presentation/try_on_screen.dart`, `backend/tests/fakes/fake_storage.py`, `backend/tests/test_account_erasure.py`, `backend/tests/test_tryon_phase5d_commercial_and_reliability.py`, `backend/tests/test_tryon_phase5e_2_readiness.py`, `backend/tests/test_r2_phase5f2_readiness.py`, `backend/tests/test_tryon_phase5f_genlook.py`, `newproject/flutter_application_1/test/try_on_genlook_compat_test.dart`, `FANSIVIBE_PHASE5F_GENLOOK_INTEGRATION.md`, `CURRENT_STATE.md`.

### 15.3 Phase 5F.5A.1 Verification Results (Zero Genlook HTTP Calls)

- **Isolated Settings & Storage Config:**
  `(cd /tmp && env -i PATH="$PATH" PYTHONPATH=/home/tony/projects/fansivibe_v1_backup/backend /home/tony/projects/fansivibe_v1_backup/backend/.venv/bin/pytest /home/tony/projects/fansivibe_v1_backup/backend/tests/test_settings.py /home/tony/projects/fansivibe_v1_backup/backend/tests/test_storage_config.py -v)` -> **34 passed, 0 failed, 0 skipped** (0.94s).
- **Backend Erasure, VTON, Genlook, R2 & Media Suites (`fansivibe_disposable_test`, `FANSIVIBE_TRYON_PROVIDER=mock`):**
  `cd backend && FANSIVIBE_TRYON_PROVIDER=mock FANSIVIBE_TEST_DATABASE_URL="postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe_disposable_test" .venv/bin/pytest tests/test_account_erasure.py tests/test_delete_account_unit.py tests/test_tryon_phase5f_genlook.py tests/test_tryon_mock_api.py tests/test_tryon_phase5c_e2e.py tests/test_tryon_phase5d_commercial_and_reliability.py tests/test_tryon_phase5e_1_security_hardening.py tests/test_tryon_phase5e_2_readiness.py tests/test_tryon_provider_contract_phase5e.py tests/test_tryon_reliability_and_security.py tests/test_r2_phase5f2_readiness.py tests/test_storage_adapter.py tests/test_storage_di.py tests/test_fake_storage.py tests/test_media_api.py tests/test_media_association_p4.py -v` -> **352 passed, 0 failed, 0 skipped** (21.80s).
- **Flutter Static Analysis & Try-On Suite:**
  `cd newproject/flutter_application_1 && flutter analyze && flutter test test/try_on_genlook_compat_test.dart test/try_on_flow_test.dart test/try_on_phase5d_test.dart` -> `flutter analyze` **0 issues**; `flutter test` **19 passed, 0 failed, 0 skipped**.

### 15.4 Updated Live-Test & Launch Readiness

- **Phase 5F.5B Controlled Live Smoke-Test Readiness:** **`CONDITIONALLY READY — OPERATOR ACTIONS & LEGAL SIGN-OFF REQUIRED.`** All technical/operational blockers from Phase 5F.5A are remediated and verified in mocked/disposable-PG tests (`FANSIVIBE_TRYON_PROVIDER` remains `mock`). Note: running FastAPI (`PID 93731` if still active) must be restarted to load Phase 5F.5A + 5F.5A.1 code and `FANSIVIBE_OPERATOR_API_KEY` before operator `/v1/tryon/health` or live smoke tests.
- **Remaining Non-Technical / Production Blockers:** (1) Operator review & acceptance of Genlook ToS/DPA (`genlook.app/dpa`), (2) verifiable depicted-person consent record for `person.jpg`, (3) explicit operator approval for server switch/restart on `genlook` + max 1 paid smoke test + immediate revert to `mock` (and live verification of `DELETE /customers/{externalUserId}` during/after smoke cleanup), and (4) production Flutter consent copy disclosing Genlook / Parakeet Labs SASU before customer launch.







