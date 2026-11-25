# Fansivibe Phase 5E — RunPod Serverless Preparation Design (No Deployment)

**Date**: 2026-11-25  
**Status**: PREPARATION COMPLETE — DESIGN & CONTRACT COMPATIBILITY ONLY  
**Production Release Gate**: **BLOCKED** pending FASHN Human Parser commercial permission and live Cloudflare R2 provisioning.  
**Non-Deployment Guardrails**: Zero FASHN weights downloaded, zero GPU packages installed, zero Docker images built or published, zero RunPod endpoints created, zero database migrations executed, zero commercial inference enabled.

---

## 1. Existing VTON Architecture Verification

Inspected directly in repository code:

- **Provider Port (`backend/app/domain/ports/tryon_provider.py`)**:
  - `TryOnProvider` protocol (`render(...) -> bytes`), `MockTryOnProvider` (deterministic SVG with baked-in `"TEST DATA — NOT AI TRY-ON"` banner), `CatVTONTryOnProvider` (local research-only subprocess invoking `experiments/vton_catvton/.venv/bin/python cli.py` under Priority 2 `GPUResourceScheduler` lease with Ollama eviction), and `CommercialTryOnProvider` + `CommercialTryOnProviderConfig`.
- **Job Lifecycle & Application Layer (`backend/app/application/tryon.py`)**:
  - `submit_job()`: validates consent (`tryon-v1`), `outfit_source` (`today`, `outfit`, `saved`, `wardrobe`), garment count (`1..8`), OW-1 wardrobe ownership via `wardrobe_repo.get_by_id(user_id, item_id)`, image size (`<= 20 MB`), dimensions (`64x64..4096x4096`), idempotency key + SHA-256 payload fingerprint, daily quota (`tryon_daily_quota_per_user`), and concurrent active job limit (`tryon_max_concurrent_jobs_per_user`).
  - `execute_tryon_inference()`: background worker moving `queued -> processing`, resolving person/garment bytes, invoking provider, checking cancellation before and after storage upload, saving result under `users/{user_id}/tryon/{job_id}/result.<ext>`, and updating DB result (`update_result`) with stale-worker protection.
  - `retry_job()`, `cancel_job()`, `delete_job_and_media()`, `recover_interrupted_jobs()`, and `cleanup_retention_data()`.
- **HTTP Surface (`backend/app/api/routers/tryon.py`, `backend/app/api/schemas/tryon.py`)**:
  - `POST /v1/tryon/jobs` (`202`), `GET /v1/tryon/jobs/{job_id}` (`200`), `GET /v1/tryon/jobs/{job_id}/image` (`200`), `POST /v1/tryon/jobs/{job_id}/retry` (`202`), `POST /v1/tryon/jobs/{job_id}/cancel` (`200`), `DELETE /v1/tryon/jobs/{job_id}` (`204`), `GET /v1/tryon/health` (`200`), `POST /v1/tryon/maintenance/retention-cleanup` (`200`).
- **Persistence (`backend/alembic/versions/0037_tryon_jobs.py`, `0038_tryon_jobs_idempotency_unique.py`, `backend/app/infrastructure/db/models.py`, `repositories.py`, `domain/ports/repositories.py`)**:
  - `tryon_jobs` table (`TryOnJobModel`), `TryOnJobRepositorySQL` (OW-1 `user_id` scoped reads/deletes, stale-worker transition guards in `update_status`, `update_result`, `update_failure`), composite `UniqueConstraint("user_id", "idempotency_key", name="uq_tryon_jobs_user_idempotency")`.
- **Object Storage (`backend/app/domain/ports/storage.py`, `backend/app/infrastructure/external/storage.py`, `backend/tests/fakes/fake_storage.py`)**:
  - `ObjectStoragePort` and `CloudflareR2StorageAdapter` (boto3 S3 SigV4 path-style), `validate_scoped_object_key`, MIME allowlist (`image/jpeg`, `image/png`, `image/webp`, `image/svg+xml`), `_sanitize_message` stripping signatures/credentials, `delete_objects_safe`, `check_health`.
- **Auth & Settings (`backend/app/api/deps.py`, `backend/app/config/settings.py`)**:
  - `get_current_user_id` (JWT Bearer token via `AuthRepositorySQL`, dev token gated by `allow_dev_token=False` in prod).
  - `Settings._validate_production_invariants` blocks `catvton` in `production`, requires R2 in `production`, and fails closed (`503`) if `mock`/`off` is used in `production`.

### Why `CommercialTryOnProvider` Is NOT RunPod-Compatible As-Is

Verified in `backend/app/domain/ports/tryon_provider.py` (lines 415–690):
1. **Synchronous single-POST protocol vs RunPod async queue**: `CommercialTryOnProvider.render()` performs a blocking `POST` to `endpoint_url` expecting `200`/`201` with raw `image/*` bytes or top-level JSON `{"image_base64": ...}`. RunPod Serverless uses `POST /v2/{endpoint_id}/run` (returns `{"id": "<runpod_job_id>", "status": "IN_QUEUE"}`), `GET /v2/{endpoint_id}/status/{job_id}`, `POST /v2/{endpoint_id}/cancel/{job_id}`, and wraps inputs/outputs in `{"input": {...}}` / `{"status": "COMPLETED", "output": {...}}`.
2. **Inline base64 payload limit**: `CommercialTryOnProvider` sends `person_image.data` and `garment_image.data` as base64 in the JSON body. RunPod `/run` rejects JSON payloads above 10 MB (base64 expands a 20 MB person photo to ~26.7 MB, causing HTTP 413). Signed R2 URLs are required.
3. **Health URL mismatch**: `CommercialTryOnProvider.check_health()` calls `endpoint_url.rstrip("/") + "/health"`. Against `.../v2/<id>/run` that produces `.../run/health` instead of `.../v2/<id>/health`.
4. **No RunPod job ID correlation / remote cancel**: `CommercialTryOnProvider` does not receive or track an external `runpod_job_id`, so `POST /v1/tryon/jobs/{id}/cancel` cannot cancel queued RunPod jobs.
5. **Category vocabulary mismatch**: `execute_tryon_inference` passes CatVTON categories (`"upper"`, `"lower"`, `"overall"`) and silently falls back to `"upper"` for `footwear` and `accessories`, whereas FASHN VTON 1.5 uses `"tops"`, `"bottoms"`, and `"one-pieces"`.

---

## 2. RunPod Serverless Integration Contract

**Boundary invariant**: The RunPod worker MUST NOT access PostgreSQL, `tryon_jobs`, user JWTs, or R2 master credentials. FastAPI remains the sole authority for auth, OW-1 ownership, quota, job state, retention, and R2 URL signing.

### 2.1 Configuration & Secrets (Future Phase 5F — Not Enabled Now)

| Variable | Owner | Notes |
|---|---|---|
| `FANSIVIBE_TRYON_PROVIDER` | Backend | Remains `"mock"` in dev; new `"runpod_fashn"` (or `"commercial"` subtype) only after license approval |
| `RUNPOD_API_KEY` | Backend Secret | `repr=False`; sent only in server-to-RunPod `Authorization: Bearer <key>` header; **never** exposed to Flutter |
| `RUNPOD_ENDPOINT_ID` | Backend Config | Target RunPod Serverless endpoint ID (base URL `https://api.runpod.ai/v2/{endpoint_id}`) |
| `RUNPOD_CONNECT_TIMEOUT_S` | Backend Config | Default `10.0` |
| `RUNPOD_REQUEST_TIMEOUT_S` | Backend Config | Per HTTP call timeout (`15.0`s for `/run`, `/status`, `/cancel`) |
| `RUNPOD_EXECUTION_TIMEOUT_S` | Backend Config | Overall job polling deadline (e.g. `120.0`s including cold-start) |
| `RUNPOD_POLL_INTERVAL_S` | Backend Config | Bounded poll interval with backoff (e.g. `1.0s` -> `2.0s` -> `3.0s`) |
| `RUNPOD_SIGNED_URL_TTL_S` | Backend Config | Short-lived input GET / output PUT TTL (`600`s / 10 min) |

### 2.2 End-to-End Execution Flow

```
Flutter ──(POST /v1/tryon/jobs, multipart + Idempotency-Key)──▶ FastAPI
  1. Verify JWT -> user_id (OW-1)
  2. Validate consent, quota, concurrency, image magic bytes + PIL bounds + strip EXIF
  3. Validate garment_id ownership in PostgreSQL wardrobe_items
  4. Persist tryon_jobs row (status="queued")
  5. Upload person image to private R2: users/{user_id}/tryon/{job_id}/person.<ext>
     (MUST succeed before dispatching to RunPod)
  6. Generate short-lived R2 presigned URLs (TTL 600s):
     - person_image_url  (GET users/{user_id}/tryon/{job_id}/person.<ext>)
     - garment_image_url (GET users/{user_id}/wardrobe/{garment_id}/...)
     - result_upload_url (PUT users/{user_id}/tryon/{job_id}/result.jpg)
  7. POST https://api.runpod.ai/v2/{endpoint_id}/run
     Body: {"input": {...}} -> returns {"id": "<runpod_job_id>", "status": "IN_QUEUE"}
  8. FastAPI polls GET .../status/{runpod_job_id}
     - Before each poll: check local DB job.status != "cancelled"
     - If locally cancelled: POST .../cancel/{runpod_job_id}, discard output, delete R2 result if written
  9. On RunPod status == "COMPLETED":
     - Validate worker output schema & R2 object existence/size/magic-bytes (head_object / bounded check)
     - Re-check job.status != "cancelled"
     - Update tryon_jobs -> status="completed", result_media_ref=...
 10. Flutter polls GET /v1/tryon/jobs/{job_id} -> fetches GET /v1/tryon/jobs/{job_id}/image
```

### 2.3 RunPod Request & Response Payloads

**Request (`POST /v2/{endpoint_id}/run`)**:
```json
{
  "input": {
    "job_id": "<tryon_jobs.id UUID>",
    "correlation_id": "<X-Correlation-ID UUID>",
    "idempotency_key": "<sha256(user_id:job_id:retry_count)>",
    "category": "tops | bottoms | one-pieces",
    "seed": "<deterministic_or_job_seed>",
    "person_image_url": "<presigned R2 GET URL, TTL 600s>",
    "garment_image_url": "<presigned R2 GET URL, TTL 600s>",
    "result_upload_url": "<presigned R2 PUT URL, TTL 600s>",
    "result_content_type": "image/jpeg",
    "output_format": "jpeg",
    "max_output_bytes": 10485760
  },
  "policy": {
    "executionTimeout": 90000,
    "ttl": 180000
  }
}
```
*Note*: `result_upload_url` restricts the worker to a single pre-authorized object key (`users/{user_id}/tryon/{job_id}/result.jpg`) with zero R2 API keys in the worker container.

**Success Response (`GET /v2/{endpoint_id}/status/{runpod_job_id}` -> `status: "COMPLETED"`)**:
```json
{
  "id": "<runpod_job_id>",
  "status": "COMPLETED",
  "delayTime": 1420,
  "executionTime": 6850,
  "output": {
    "ok": true,
    "job_id": "<tryon_jobs.id>",
    "correlation_id": "<X-Correlation-ID>",
    "result_uploaded": true,
    "result_content_type": "image/jpeg",
    "result_size_bytes": 248310,
    "result_sha256": "<hex>",
    "result_width": 768,
    "result_height": 1024,
    "telemetry": {
      "cold_start": false,
      "model_load_ms": 0.0,
      "download_ms": 180.4,
      "inference_ms": 6320.1,
      "upload_ms": 210.5,
      "peak_vram_mb": 11420.0
    }
  }
}
```

**Error Response (`output.ok == false` or `status: "FAILED"`)**:
- Structured error code (`INVALID_INPUT_IMAGE`, `IMAGE_DOWNLOAD_FAILED`, `UNSUPPORTED_CATEGORY`, `CUDA_OOM`, `INFERENCE_TIMEOUT`, `OUTPUT_VALIDATION_FAILED`, `UPLOAD_FAILED`) without echoing presigned URLs or image bytes.

### 2.4 Garment Category Mapping

Implemented in `backend/app/domain/ports/tryon_provider.py` (`FASHN_CATEGORY_MAP`, `map_wardrobe_category_to_fashn`):
- `tops`, `outerwear`, `upper`, `shirt`, `blouse`, `sweater`, `jacket`, `coat`, `blazer`, `tee` → **`"tops"`**
- `bottoms`, `lower`, `pants`, `trousers`, `jeans`, `skirts`, `shorts`, `chinos` → **`"bottoms"`**
- `one-pieces`, `dresses`, `dress`, `jumpsuits`, `jumpsuit`, `overall`, `rompers` → **`"one-pieces"`**
- `footwear`, `shoes`, `accessories`, `bags`, `jewelry`, unknown → **fail closed** (`ProviderPayloadError` / HTTP `422`).

### 2.5 Retry, Timeout, Cancellation, Cold-Start, and Scaling Rules

- **Retries**:
  - Transport/submission errors (`408`, `502`, `503`, `504`, `httpx.TimeoutException`) before `runpod_job_id` is assigned may retry with exponential backoff (`max_retries=2`).
  - Once `runpod_job_id` is returned, **never re-submit `/run`** inside the same attempt (prevents duplicate GPU billing). Poll `/status/{runpod_job_id}` until `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`, or `RUNPOD_EXECUTION_TIMEOUT_S` expires.
  - Non-retryable (`400`, `401`, `403`, `422`, `429`, `INVALID_INPUT_IMAGE`, `UNSUPPORTED_CATEGORY`): fail immediately; allow user-initiated `POST /v1/tryon/jobs/{id}/retry` only for eligible failures.
  - Restart recovery (`recover_interrupted_jobs`): orphaned `queued`/`processing` jobs transition to `failed` with `INTERRUPTED_BY_RESTART` and are never automatically re-billed.
- **Cancellation Limitations**:
  - If `job.status == "cancelled"` locally: if `IN_QUEUE`, `POST /cancel/{runpod_job_id}` removes it from RunPod queue before billing GPU time. If `IN_PROGRESS`, RunPod does not guarantee instantaneous mid-kernel termination; FastAPI stops polling, marks `cancelled`, and runs best-effort cleanup on `users/{user_id}/tryon/{job_id}/result.*` so late worker writes never reach the user.
- **Cold-Start & Scaling**:
  - Initial production rollout: `min_workers=0` (scale-to-zero), `max_workers=1`, `concurrency=1` (1 request per GPU worker at a time), `idle_timeout_s=30–60`, `flashboot` disabled or evaluated only after stability benchmarking.
  - Warm worker keeps FASHN VTON 1.5 weights resident in GPU VRAM across jobs; `model_load_ms` is incurred once per cold worker boot.
- **Health Monitoring**:
  - Future RunPod adapter `check_health()` calls `GET https://api.runpod.ai/v2/{endpoint_id}/health` and reports `workers` (`idle`, `ready`, `running`, `throttled`, `unhealthy`) and `jobs` (`inQueue`, `inProgress`) to `GET /v1/tryon/health`.

---

## 3. Proposed Isolated Worker Container Design (Reference Only — Not Built)

### 3.1 Proposed Directory Layout

```text
workers/vton_fashn_runpod/         # Isolated from backend/ (NOT built or deployed in 5E)
├── Dockerfile
├── requirements.lock.txt          # Pinned deps generated & hash-verified in GPU CI when licensed
├── handler.py                     # RunPod serverless entrypoint + warm-worker lifecycle
├── model_loader.py                # Singleton model loader (weights NOT baked until licensed)
├── validators.py                  # Magic bytes, MIME, dimension, decompression-bomb, EXIF checks
├── telemetry.py                   # Structured JSON logger + CUDA VRAM/timing telemetry
└── health.py                      # Worker readiness & GPU availability probe
```

### 3.2 Proposed `Dockerfile` Template

```dockerfile
# Reference template ONLY — do not build until FASHN Human Parser commercial license is approved
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TORCH_HOME=/opt/models/torch \
    HF_HOME=/opt/models/hf

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3-pip libgl1 libglib2.0-0 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 worker && \
    useradd --system --uid 10001 --gid 10001 --create-home worker

WORKDIR /app
COPY requirements.lock.txt .
RUN python3.11 -m pip install --no-cache-dir --require-hashes -r requirements.lock.txt

COPY --chown=worker:worker . /app
USER worker

# Weights are NOT downloaded during build in Phase 5E; future licensed deploy mounts
# a read-only RunPod Network Volume or verified SHA-256 checkpoint bundle at /opt/models.
CMD ["python3.11", "-u", "handler.py"]
```

### 3.3 Pinned Dependency Strategy (`requirements.lock.txt`)

Pin exact versions with hashes (`pip-compile --generate-hashes`) at implementation time (Phase 5F) after license sign-off:
- `runpod==<pinned>` (RunPod serverless SDK)
- `torch==<pinned>+cu124`, `torchvision==<pinned>+cu124`
- `diffusers==<pinned>`, `transformers==<pinned>`, `accelerate==<pinned>`, `safetensors==<pinned>`
- `Pillow==10.4.0` (matches backend security baseline)
- `httpx==0.28.1` (presigned R2 GET download and presigned R2 PUT upload with strict timeouts)
- `fashn-vton` + `fashn-human-parser` (**ONLY after commercial permission is obtained**)

### 3.4 Worker Entrypoint, Warm-Worker Reuse, Validation, Telemetry, Shutdown, Health

- **Model Initialization & Warm-Worker Reuse**:
  - Load FASHN VTON pipeline + FASHN Human Parser once at worker startup into a module-level singleton (`_MODEL_HOLDER`) with `torch.no_grad()` / FP16/BF16, `torch.cuda.synchronize()` after load, and deterministic readiness state (`READY` / `UNHEALTHY`).
  - Never reload weights per request; catch `torch.cuda.OutOfMemoryError`, call `gc.collect()` + `torch.cuda.empty_cache()`, and exit/mark worker unhealthy if VRAM cannot recover.
- **Input Validation (`validators.py`)**:
  - Enforce HTTPS-only presigned URLs, bounded streaming download (`<= 20 MB` person, `<= 15 MB` garment), magic-byte signature verification (JPEG/PNG/WebP), `Image.MAX_IMAGE_PIXELS = 12_000_000` decompression-bomb guard, dimension bounds (`64..4096`), `ImageOps.exif_transpose`, and `img.info = {}` metadata stripping.
  - Validate `category in {"tops", "bottoms", "one-pieces"}`.
- **Output Validation (`validators.py`)**:
  - Verify rendered image is non-empty, passes JPEG/PNG/WebP magic-byte check, has expected RGB channels & dimensions, is `<= max_output_bytes`, and contains zero EXIF metadata.
- **Structured Logs & Privacy (`telemetry.py`)**:
  - Emit single-line JSON logs with `job_id`, `correlation_id`, `status`, `error_code`, and millisecond stage timings.
  - Strict redaction filter: **never** log presigned URL query strings (`X-Amz-Signature`, `X-Amz-Credential`), API keys, raw image bytes, or base64 strings.
- **GPU Telemetry**:
  - Record `torch.cuda.reset_peak_memory_stats()` before inference and `torch.cuda.synchronize()` before capturing `peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 ** 2)`, `download_ms`, `inference_ms`, `upload_ms`, `model_load_ms`, and `cold_start` boolean.
- **Graceful Shutdown**:
  - Register `SIGTERM` / `SIGINT` handlers setting a shutdown flag, draining at most one in-flight job cleanly within RunPod's stop grace window, releasing CUDA cache (`torch.cuda.empty_cache()`), and closing `httpx` clients.
- **Health Checks**:
  - Startup readiness verifies `torch.cuda.is_available()`, expected VRAM floor, and loaded model checksums before calling `runpod.serverless.start(...)`. RunPod control plane monitors worker heartbeats and exposes endpoint `/health` to FastAPI.

---

## 4. Security, Privacy & R2 Readiness Audit

### 4.1 Security & Privacy Gaps Identified in Existing Codebase (Remediated in Phase 5E.1)

1. **Unauthenticated Maintenance Endpoint (`backend/app/api/routers/tryon.py`)**: `POST /v1/tryon/maintenance/retention-cleanup` is now gated by `require_operator_auth` (`X-Operator-Key` header verified via constant-time `hmac.compare_digest` against `FANSIVIBE_OPERATOR_API_KEY`; fails closed with `503` if unset, `401` if missing, `403` if invalid; never accepts user JWTs or dev tokens; excluded from OpenAPI schema and browser CORS `allow_headers`).
   - **Operational Setup**: Set `FANSIVIBE_OPERATOR_API_KEY` to a high-entropy secret (`>= 32` characters in production) in backend deployment secrets (never in Flutter client builds). Schedule cron/systemd timer calls with:
     ```bash
     curl -fsS -X POST "https://<backend-internal-host>/v1/tryon/maintenance/retention-cleanup" \
       -H "X-Operator-Key: ${FANSIVIBE_OPERATOR_API_KEY}"
     ```
2. **`submit_job` Person-Image Validation & Privacy (`backend/app/application/tryon.py`)**: Enforces magic-byte + Pillow format verification (`JPEG`, `PNG`, `WEBP` matching declared `Content-Type`), `Image.MAX_IMAGE_PIXELS = 12_000_000` decompression-bomb guard, `64..4096` dimension bounds, `ImageOps.exif_transpose` orientation preservation, and clean pixel-only re-encoding stripping all EXIF/GPS/XMP/ICC metadata.
3. **In-Memory `_BYTE_CACHE` Retention Leak (`backend/app/application/tryon.py`)**: Person photograph bytes are evicted immediately after `store_person_image_async` persists them to object storage and guaranteed cleared via `finally` across completion, failure, exception, cancellation, and restart recovery.
4. **`ObjectStoragePort.read_object` Size Alignment (`backend/app/application/tryon.py`, `routers/tryon.py`)**: Person and result reads explicitly pass `max_bytes=20 * 1024 * 1024` matching upload bounds.
5. **SQLAlchemy Session Lifecycle in TryOn DI (`backend/app/api/deps.py`, `routers/tryon.py`)**: `get_tryon_repository` and `get_tryon_wardrobe_repository` now yield repositories and reliably close sessions in `finally`, while background inference opens/closes an independent session after request teardown.
6. **Provider Output Format Validation (`backend/app/application/tryon.py`, `routers/tryon.py`, `tryon_provider.py`)**: Validates actual decoded output bytes (`JPEG`, `PNG`, `WEBP`, or `SVG` exclusively for `mock` provider), matches stored key extension and MIME type, and rejects empty/corrupt/unsupported outputs.
7. **Garment Category Fail-Closed Boundary (`backend/app/domain/ports/tryon_provider.py`, `application/tryon.py`)**: `CommercialTryOnProvider`, `CatVTONTryOnProvider`, and `execute_tryon_inference` fail closed (`ProviderPayloadError` / `PAYLOAD_REJECTED`) on unsupported categories such as `footwear` and `accessories`.

### 4.2 Cloudflare R2 Readiness & Unresolved Issues

- **Verified Ready in Code**:
  - `CloudflareR2StorageAdapter` implements `ObjectStoragePort` with S3v4 path-style signing, `validate_scoped_object_key`, MIME allowlist, credential/signature log scrubbing (`_sanitize_message`), idempotent `delete_object`, `delete_objects_safe`, and `check_health` (`head_bucket`).
  - Settings validation enforces `MEDIA_STORAGE_PROVIDER=r2` + required R2 credentials in `production`.
- **Unresolved / Pending Infrastructure Items**:
  1. **Live R2 Credentials & Bucket Provisioning**: `backend/.env` and environment currently run with `MEDIA_STORAGE_PROVIDER=fake`; no live R2 bucket, API token, or `R2_ACCOUNT_ID`/`R2_BUCKET_NAME` is provisioned.
  2. **Private Bucket & Lifecycle Rules**: Bucket must enforce Block Public Access (`r2.dev` public subdomain disabled), server-side bucket lifecycle expiration (defense-in-depth alongside `cleanup_retention_data` 24h/72h TTL), and no browser CORS exposure for `/tryon/` prefixes.
  3. **Upload-Before-Dispatch Durability Race (`backend/app/api/routers/tryon.py`, `application/tryon.py`)**: *(Remediated in Phase 5E.1)* `store_person_image_async` is now awaited and confirmed via `object_exists` before worker dispatch, never swallows storage exceptions, marks jobs failed on storage errors, and `create_confirmed_presigned_input_url` refuses to issue presigned GET URLs before durable storage confirmation.
  4. **Presigned PUT Verification**: Need end-to-end test against real R2 verifying RunPod worker `PUT` with `Content-Type` header matches SigV4 signature and `head_object` + magic-byte validation succeeds.

---

## 5. Cost-Measurement Plan

Do **not** assume RunPod pricing or GPU tier suitability prior to benchmarking. During licensed Phase 5F benchmarking on an isolated staging endpoint:

### 5.1 Metrics to Measure Empirically

1. **GPU Execution Time (`executionTime` / `inference_ms`)**: Per-job active GPU billing duration across candidate GPUs (e.g. L4 24 GB vs A10G 24 GB vs RTX 4090 24 GB) at target resolutions.
2. **Cold-Start Time (`delayTime` on cold worker)**: Container boot + RunPod queue dispatch before inference begins.
3. **Model Loading Time (`model_load_ms`)**: Time to load FASHN VTON 1.5 + FASHN Human Parser into VRAM on cold start.
4. **Worker Idle Time**: Idle keep-alive duration (`idle_timeout_s`) billed after job completion before scale-to-zero.
5. **Input/Output Transfer**: R2 Class A/B API request counts (PUT person, GET person, GET garment, PUT result, HEAD verify, DELETE retention) + egress/ingress bytes (note: R2 has zero egress fees in standard tiers, verify account terms).
6. **Storage Footprint**: Average person + result object KB × retention hours (`24h` person, `72h` result).
7. **Failed Requests & Retries**: Rate of `FAILED` / `TIMED_OUT` / `CANCELLED` jobs and wasted GPU seconds.

### 5.2 Cost Formula & Rollout Configuration

$$\text{Cost per Successful Try-On} = \frac{\sum (\text{Active GPU s} + \text{Idle Tail s} + \text{Failed/Retry GPU s}) \times R_{\text{GPU/s}} + C_{\text{R2 Ops/Storage}}}{N_{\text{successful jobs}}}$$

- **Initial Configuration**: `min_workers=0` (scale-to-zero), `max_workers=1`, `concurrency=1`, `idle_timeout_s=30`. Concurrency > 1 MUST NOT be enabled until peak VRAM under concurrent requests and output non-interference are measured.

---

## 6. Licensing Blocker (Hard Production Release Gate)

- **Status**: **FASHN Human Parser commercial permission is PENDING.**
- **Hard Gate Policy**:
  1. Do **NOT** download FASHN VTON or FASHN Human Parser model weights.
  2. Do **NOT** build or push the RunPod worker Docker image.
  3. Do **NOT** enable commercial inference in staging or production.
  4. Do **NOT** substitute CatVTON (`CC BY-NC-SA 4.0`) for commercial inference; `Settings` continues to reject `catvton` in `production`.
  5. Production remains fail-closed (`503` when `mock`/`off`) until written commercial permission is recorded in `DECISIONS.md` and Phase 5F passes verification.

