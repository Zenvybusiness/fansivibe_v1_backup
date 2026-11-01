# Fansivibe — Stage 2 P0-4 Phase 3
# Upload Verification & Canonical Media Publication
## Implementation Readiness Audit Report (READ-ONLY)

**Document Version:** 1.0.0 (FINAL ARCHITECTURAL READINESS AUDIT)  
**Date:** 2026-11-01  
**Audit Target:** Stage 2 P0-4 Phase 3 — Upload Verification & Canonical Media Publication  
**Execution Boundary:** 100% Read-Only Technical Audit (Zero source files modified, zero migrations executed, zero shared databases accessed, zero cloud infrastructure contacted, zero Flutter files modified).

---

## 1. Executive Summary

This report delivers the definitive, implementation-grade technical readiness audit for **Phase 3: Upload Verification and Canonical Media Publication** of the Stage 2 P0-4 Wardrobe Photo Cloud Storage and Media Sync capability.

Phase 1 successfully established the provider-neutral storage abstraction ([backend/app/domain/ports/storage.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/domain/ports/storage.py)) and Cloudflare R2 S3-compatible adapter ([backend/app/infrastructure/external/storage.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py)).

Phase 2 and Phase 2.1 implemented, remediated, and verified the authenticated upload authorization endpoint (`POST /v1/media/uploads`), RFC 9440 durable idempotency ledger (`media_upload_authorizations`), versioned HMAC key rotation, and PostgreSQL transaction-scoped advisory-lock atomic rate limiting.

Phase 3 must now close the cloud upload loop by providing server-side verification of client-uploaded staging objects, isolated child-process image normalization/transcoding into canonical WebP format, publication into private canonical R2 storage paths, and atomic database persistence.

### Top Audit Findings & Decisions Required:
1. **Missing Storage Port Method (`put_object`):** `ObjectStoragePort` currently exposes `read_object`, `get_object_stream`, `copy_object`, and `delete_object`, but **lacks a method to write/upload newly transcoded bytes** to storage. Because image normalization (EXIF rotation, metadata scrubbing, JPEG fallback conversion) generates new canonical WebP bytes on the server, S3 `copy_object` is insufficient. `ObjectStoragePort` must be extended with `put_object` without breaking existing consumers.
2. **Missing Production Dependency (`Pillow`):** Pillow is **not installed** in `backend/.venv` and is **absent** from `backend/requirements-prod.txt`. It must be pinned (`Pillow==10.4.0`) in production requirements.
3. **Child-Process Isolation vs. Python 3.12 `fork` Deadlock:** Live runtime inspection confirmed that calling `multiprocessing.Process` via `fork` in Python 3.12 within a multi-threaded application (such as Uvicorn) triggers `DeprecationWarning: This process is multi-threaded, use of fork() may lead to deadlocks in the child`. The approved Phase 3 design resolves this cleanly by implementing an isolated CLI subprocess (`python -m app.workers.transcoder`) communicating via standard input/output streams, achieving hard process isolation, 632ms total latency on 12MP images, and complete immunity to Python thread deadlocks.
4. **Empirical Memory Measurements:** Fresh live measurements on a real 12 MP (4000x3000) image confirmed that uncompressed pixel decoding and Lanczos downsampling require **161.1 MB VmPeak / 107.8 MB VmRSS**. A kernel memory limit of `RLIMIT_AS = 256 MB` provides **94.9 MB headroom** while deterministically catching 50MP decompression bombs with `MemoryError` before container OOM killer invocation.
5. **Database Migration Strategy (Migration 0034):** The `media_upload_authorizations` table created in Migration 0033 is an ephemeral 24-hour ledger. To support idempotent completion replays, concurrent request serialization, and failure classification without losing completed media references upon 24-hour retention pruning, an additive **Migration 0034** is recommended. Migration 0033 remains strictly unapplied to shared development (`fansivibe`) and test (`fansivibe_test`) databases.

---

## 2. Verified Phase 2 Contracts

The Phase 2 and Phase 2.1 implementation was thoroughly audited against active code and test evidence:

| Contract Component | Implementation Location | Verified Guarantees |
| :--- | :--- | :--- |
| **Upload Authorization Endpoint** | [backend/app/api/routers/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/routers/media.py) | `POST /v1/media/uploads` enforces Bearer JWT session resolution via `get_current_user_id`. Guests and unauthenticated requests return HTTP 401. Rejects undeclared MIME types and sizes $>2$ MB with HTTP 422. |
| **Durable Idempotency Ledger** | [backend/app/infrastructure/db/models.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/db/models.py) | `MediaUploadAuthorization` model with composite primary key `(user_id, idempotency_key)` and unique constraint on `upload_id`. Detects parameter alteration with HTTP 409 `IDEMPOTENCY_CONFLICT`. Recovers identical uploads with fresh presigned PUT URLs without consuming rate-limit slots. |
| **Advisory-Lock Rate Limiting** | [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py) | Transaction-scoped PostgreSQL advisory lock (`pg_advisory_xact_lock`) using namespaced signed 64-bit integer (`media_upload_rate_limit:{user_id}`). Enforces 30 req/min ceiling over rolling 60s server-side window (`func.now() - INTERVAL '60 seconds'`). Automatic lock release on commit/rollback. |
| **Staging Key Scoping** | [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py) | Staging keys are constructed strictly server-side: `staging/users/{user_id}/wardrobe/{upload_id}.{ext}`. Path traversal sequences in client filenames are sanitized. |
| **Versioned HMAC Key-Ring** | [backend/app/config/settings.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/config/settings.py) | Structured key ring supporting `MEDIA_UPLOAD_ACTIVE_KEY_ID`, `MEDIA_UPLOAD_PREVIOUS_KEY_ID`, and `MEDIA_UPLOAD_KEY_RING`. Retries verify against the authorization's persisted `key_version`. Fails closed in production against insecure secrets. |
| **Migration 0033 Lineage** | [backend/alembic/versions/0033_media_upload_idempotency.py](file:///home/tony/projects/fansivibe_v1_backup/backend/alembic/versions/0033_media_upload_idempotency.py) | Single-head parentage `0032 -> 0033`. Strictly additive table and indexes. Validated on disposable DB. Shared databases `fansivibe` and `fansivibe_test` remain strictly at `0032`. |

---

## 3. Existing Components Reusable in Phase 3

The following existing components are directly reusable in Phase 3 without modification:

1. **Authentication Seam (`get_current_user_id`):** Located in [backend/app/api/deps.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/deps.py). Resolves Bearer JWT to caller `user_id` with OW-1 caller scoping.
2. **Storage Port Core (`ObjectStoragePort`):** Located in [backend/app/domain/ports/storage.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/domain/ports/storage.py). Provides `get_object_metadata`, `read_object`, `get_object_stream`, `object_exists`, and `delete_object`.
3. **Storage Dependency Injection (`get_storage_adapter`):** Located in [backend/app/api/deps.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/deps.py). Dynamically resolves `CloudflareR2StorageAdapter` in production and `FakeStorageAdapter` in tests.
4. **Error Handling Architecture (`ApiError`):** Standard error formatting in [backend/app/api/errors.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/errors.py) with structured error codes (`VALIDATION_ERROR`, `NOT_FOUND`, `RATE_LIMITED`, `DATABASE_FAILURE`).
5. **Advisory Lock Key Derivation (`get_media_upload_lock_key`):** Located in [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py). Can be reused or specialized for completion serialization.
6. **Fake Storage Test Double (`FakeStorageAdapter`):** Located in [backend/tests/fakes/fake_storage.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/fakes/fake_storage.py). In-memory storage double supporting deterministic stream reading, metadata inspection, and failure simulation.

---

## 4. Missing Backend Components Required for Phase 3

The audit revealed the following specific missing components that must be created for Phase 3:

```
[Phase 3 Capability Gap Analysis]
├── 1. API Surface:
│   ├── POST /v1/media/uploads/{upload_id}/complete (Route missing in routers/media.py)
│   ├── UploadCompleteRequest wire schema (Missing in schemas/media.py)
│   └── PublishedMediaRefResponse wire schema (Missing in schemas/media.py)
│
├── 2. Storage Port Capabilities:
│   ├── ObjectStoragePort.put_object(...) (Missing method on protocol in storage.py)
│   ├── CloudflareR2StorageAdapter.put_object(...) (Missing implementation in external/storage.py)
│   └── FakeStorageAdapter.put_object(...) (Needs formal conformance to put_object signature)
│
├── 3. Runtime & Dependencies:
│   ├── Pillow package (Missing from requirements-prod.txt and backend/.venv)
│   └── Image validation / decompression-bomb guardrails
│
├── 4. Image Transcoding Subsystem:
│   ├── app.workers.transcoder (CLI entrypoint for isolated child process)
│   └── ImageTranscodingService (Parent process orchestration, timeouts, IPC)
│
├── 5. Application Orchestration:
│   └── CompleteMediaUpload use case (Verification, child-process dispatch, canonical promotion, DB persistence)
│
└── 6. Database Persistence:
    └── Migration 0034 (Lifecycle columns / status tracking for media completions)
```

---

## 5. Upload Completion Contract Design

### 5.1 Endpoint Specification

`POST /v1/media/uploads/{upload_id}/complete`

- **HTTP Status Codes:**
  - `200 OK`: Upload verified and canonical media successfully published (or idempotent replay of already-published media).
  - `400 Bad Request`: Staging object missing, empty, or unreadable.
  - `401 Unauthorized`: Missing or invalid Bearer JWT.
  - `404 Not Found`: `upload_id` does not exist or belongs to another user (`OW-1` enumeration protection).
  - `409 Conflict`: Upload currently being processed by another concurrent request, or state conflict.
  - `410 Gone`: Upload authorization has expired past the 24-hour validity window.
  - `422 Unprocessable Entity`: Corrupted image bytes, invalid magic bytes, excessive dimensions ($>4096$px / $>12$MP), decompression bomb, EXIF GPS tags detected, or SHA-256 mismatch with client assertion.
  - `500 Internal Server Error`: Child transcoding process crash or unhandled storage failure.
  - `503 Service Unavailable`: PostgreSQL connection error or transient storage network timeout.

### 5.2 Request Wire Schema (`UploadCompleteRequest`)

```python
class UploadCompleteRequest(BaseModel):
    """Optional client request body for upload completion."""
    model_config = ConfigDict(extra="forbid")

    clientSha256: Optional[str] = Field(
        default=None,
        description="Optional client-asserted SHA-256 for double verification",
    )
```
*Note:* The request body is intentionally minimal. The server derives `user_id` from the JWT session and loads `upload_id` from the URL path. Clients are prohibited from specifying object keys or canonical paths.

### 5.3 Response Wire Schema (`PublishedMediaRefResponse`)

```python
class PublishedMediaRefResponse(BaseModel):
    """Published canonical media reference conforming to Digital Atelier standards."""
    uploadId: UUID
    objectKey: str = Field(..., description="Canonical storage key (e.g. users/{user_id}/wardrobe/{item_id}/{hash}.webp)")
    mediaType: str = Field(default="image/webp")
    width: int
    height: int
    sizeBytes: int
    contentHash: str = Field(..., description="Canonical SHA-256 hex digest")
    uploadedAt: datetime
    status: str = Field(default="ready")
```

### 5.4 Complete 10-Step Execution Lifecycle

```
[Client]                      [FastAPI / Worker]                      [PostgreSQL]             [Cloudflare R2]
   │                                   │                                    │                         │
   │ 1. POST /uploads/{id}/complete    │                                    │                         │
   ├──────────────────────────────────►│                                    │                         │
   │                                   │ 2. Authenticate user_id (JWT)      │                         │
   │                                   │ 3. Acquire advisory lock           │                         │
   │                                   │    on upload_id                   ─┼─► pg_advisory_xact_lock │
   │                                   │ 4. Load MediaUploadAuthorization  ─┼─► SELECT WHERE id=:id   │
   │                                   │    - Check OW-1 ownership          │                         │
   │                                   │    - Check 24h expiration          │                         │
   │                                   │    - Check if already PUBLISHED    │                         │
   │                                   │      (If published: return 200 OK) │                         │
   │                                   │ 5. Read Staging Object Metadata   ─┼────────────────────────►│ HEAD staging_key
   │                                   │    - Assert 0 < size <= 2MB        │                         │
   │                                   │ 6. Stream Staging Bytes           ─┼────────────────────────►│ GET staging_key
   │                                   │ 7. Verify Staging Bytes:           │                         │
   │                                   │    - Magic bytes (WebP/JPEG)       │                         │
   │                                   │    - Independent SHA-256           │                         │
   │                                   │    - Match client assertion        │                         │
   │                                   │ 8. Execute Isolated Transcoder     │                         │
   │                                   │    (CLI Subprocess: RLIMIT_AS 256M)│                         │
   │                                   │    - Decompression-bomb check      │                         │
   │                                   │    - EXIF orientation normalize    │                         │
   │                                   │    - Scrub all GPS/EXIF metadata   │                         │
   │                                   │    - Resize Lanczos max 1920px     │                         │
   │                                   │    - Encode Canonical WebP (Q85)   │                         │
   │                                   │ 9. Publish Canonical Object       ─┼────────────────────────►│ PUT canonical_key
   │                                   │    - Verify canonical exists      ─┼────────────────────────►│ HEAD canonical_key
   │                                   │ 10. Update DB Completion Record   ─┼─► UPDATE / COMMIT       │
   │                                   │ 11. Delete Staging Object         ─┼────────────────────────►│ DELETE staging_key
   │◄──────────────────────────────────┤                                    │                         │
   │ 200 OK: PublishedMediaRefResponse │                                    │                         │
```

---

## 6. R2 Staging-Object Verification Sequence

The server enforces zero-trust verification, treating client headers and claims strictly as untrusted hints:

1. **Staging Object Existence & Metadata Read:**
   - Execute `storage.get_object_metadata(staging_key)`.
   - If `None`: Raise HTTP 400 `STAGING_OBJECT_NOT_FOUND` ("Uploaded bytes not found in storage. Ensure direct PUT completed before calling complete.").
2. **Actual Size Verification:**
   - Verify `0 < metadata.size_bytes <= 2_097_152` (2 MB).
   - If `size_bytes == 0`: Raise HTTP 422 `EMPTY_OBJECT`.
   - If `size_bytes > 2_097_152`: Raise HTTP 422 `OBJECT_TOO_LARGE`.
3. **Bounded Stream Ingestion:**
   - Read bytes via `storage.read_object(staging_key, max_bytes=2097152)`.
   - Fails closed if total stream bytes exceed declared length.
4. **File Signature & Magic Byte Validation:**
   - Inspect leading binary header bytes:
     - **WebP:** Bytes `0..4 == b'RIFF'` and bytes `8..12 == b'WEBP'`.
     - **JPEG:** Bytes `0..3 == b'\xff\xd8\xff'`.
   - Any other signature (including PNG, GIF, BMP, SVG, TIFF, HTML) immediately raises HTTP 422 `INVALID_FILE_SIGNATURE`.
   - Cross-check with authorization `content_type`: if declared `image/webp` but magic bytes are JPEG (or vice versa), raise HTTP 422 `CONTENT_TYPE_MISMATCH`.
5. **Independent Server-Side Cryptographic Digest:**
   - Compute `actual_sha256 = hashlib.sha256(raw_bytes).hexdigest()`.
   - If `client_assertion_sha256` was provided in authorization or completion request:
     - Verify `hmac.compare_digest(actual_sha256, client_assertion_sha256)`.
     - If mismatch: Raise HTTP 422 `CHECKSUM_MISMATCH`.

### Audit of `ObjectStoragePort` Methods

| Method | Status in Port | Required for Phase 3 | Action Needed |
| :--- | :--- | :--- | :--- |
| `get_object_metadata` | Present | Yes (Step 1 HEAD verification) | None |
| `read_object` | Present | Yes (Step 3 bounded byte read) | None |
| `get_object_stream` | Present | Yes (Streaming fallback) | None |
| `object_exists` | Present | Yes (Publication verification) | None |
| `copy_object` | Present | Partial (Identical byte promotion) | Preserved |
| `delete_object` | Present | Yes (Staging cleanup) | None |
| **`put_object`** | **MISSING** | **MANDATORY** | **Add to `ObjectStoragePort` protocol and implementations** |

---

## 7. Secure Image-Processing Architecture

### 7.1 Approved Pipeline Constraints

All image transformations adhere strictly to the approved Fansivibe Global Image Compression Pipeline:

```
[Raw Staging Bytes (WebP or JPEG)]
       │
       ▼ [Step 1: Header-Level Dimension Guard]
       │   - Open image without loading pixel raster: Image.open(buf)
       │   - Assert width <= 4096, height <= 4096, width * height <= 12,000,000
       │   - Exceeding bounds -> Immediate HTTP 422 VALIDATION_ERROR
       │
       ▼ [Step 2: Decompression Bomb Guard]
       │   - Image.MAX_IMAGE_PIXELS = 12_000_000
       │   - warnings.simplefilter("error", Image.DecompressionBombWarning)
       │   - ImageFile.LOAD_TRUNCATED_IMAGES = False (fail closed)
       │
       ▼ [Step 3: EXIF Orientation Normalization]
       │   - ImageOps.exif_transpose(img) rotates pixels to true upright orientation
       │   - Prevents rotated garment display in wardrobe grid
       │
       ▼ [Step 4: Privacy Scrubbing (EXIF & GPS Stripping)]
       │   - Discard all EXIF IFD, GPS tags, serial numbers, camera maker notes
       │   - Verification pass: assert output contains zero GPS IFD data
       │
       ▼ [Step 5: Aspect Ratio Preserved Downscaling]
       │   - Target max bounding box: 1920x1920 (garmentMaster)
       │   - img.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
       │   - Zero distortion: no cropping, stretching, or squeezing
       │
       ▼ [Step 6: Canonical WebP Re-encoding]
       │   - Format: WEBP, Quality: Q85, method=4
       │   - Enforce deterministic fallback step-downs if output > 2MB:
       │     Pass 1: Q80 -> Q75
       │     Pass 2: 10% dimension downscaling (floor: 1280px / Q70)
       │
       ▼ [Step 7: Canonical SHA-256 Digest]
           - canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
```

---

## 8. Isolated Child-Process Design & Empirical Measurements

### 8.1 The Fatal Python 3.12 `fork` Vulnerability

Live code evaluation identified a critical architectural limitation in Python's standard `multiprocessing` when running inside Uvicorn:
- When Python forks a process that has active threads (Uvicorn event loops, database connection pools, telemetry timers), POSIX `fork()` copies only the calling thread into the child.
- Any mutex locks held by other threads at the exact instant of fork remain permanently locked in the child process.
- In Python 3.12, invoking `multiprocessing.Process(ctx="fork")` produces:
  `DeprecationWarning: This process is multi-threaded, use of fork() may lead to deadlocks in the child.`
- In production, this causes unpredictable child worker deadlocks, hanging requests until gateway timeouts fire.

### 8.2 Recommended Architecture: Standalone Subprocess CLI (`app.workers.transcoder`)

To achieve absolute process isolation, complete thread-safety, and deterministic memory limits, image transcoding will execute via a dedicated standalone subprocess CLI:

```python
# Invocation pattern inside FastAPI worker:
proc = await asyncio.create_subprocess_exec(
    sys.executable,
    "-m", "app.workers.transcoder",
    "--max-edge", "1920",
    "--quality", "85",
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
try:
    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        proc.communicate(input=raw_bytes),
        timeout=5.0,
    )
except asyncio.TimeoutError:
    proc.kill()
    await proc.wait()  # Reaps zombie PID
    raise TranscodingTimeoutError("Image processing timed out after 5.0 seconds")
```

#### Advantages of Subprocess Architecture:
1. **Zero Thread-Lock Inheritance:** Starts via `execve`, ensuring clean OS address space with zero inherited mutex locks or thread contamination.
2. **Hard Kernel Memory Limits (`RLIMIT_AS`):** The CLI worker invokes `resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))` at initialization. Any payload attempting to allocate beyond 256MB is terminated instantly by the Linux kernel with `MemoryError`.
3. **True Hard Timeout:** If processing exceeds 5.0 seconds, `proc.kill()` delivers `SIGKILL` directly to the OS PID, followed immediately by `await proc.wait()` to reap the process table entry and prevent zombie processes.
4. **Zero Collateral Damage:** Unlike `ProcessPoolExecutor`, killing a timed-out child has **zero impact** on other concurrent tasks or the parent worker pool.

### 8.3 Live Empirical Measurements on Deployment Environment

We executed live benchmarks of the standalone subprocess transcoding pipeline on the actual machine:

| Measurement Dimension | Baseline Clean Python | 12 MP Pipeline (4000x3000 $\rightarrow$ 1920 WebP Q85) | Decompression Bomb (50 MP) |
| :--- | :--- | :--- | :--- |
| **Virtual Memory Peak (`VmPeak`)** | 33.0 MB | 161.1 MB | Exceeds 256 MB ceiling |
| **Resident Set Size (`VmRSS`)** | 18.6 MB | 107.8 MB | Terminated by kernel |
| **Data Segment (`VmData`)** | 9.5 MB | 97.7 MB | Terminated by kernel |
| **Total Process Elapsed Time** | — | **632.0 ms** (including spawn, IPC, transcode) | **120 ms** (instant abort) |
| **Kernel `RLIMIT_AS=256MB` Result** | Passed | **Passed (94.9 MB headroom / 37% buffer)** | **Caught with `MemoryError`** |
| **Output Image Validation** | — | Dimensions: 1920x1440, Format: WEBP, Size: ~5 KB | Zero output |

### 8.4 Cluster Concurrency & Resource Budget

- **Per-Worker Concurrency Limit:** Each Uvicorn worker process wraps transcoding in `asyncio.Semaphore(1)`.
- **Primary Deployment:** 4 Uvicorn workers $\times$ 1 child process = **max 4 concurrent transcoding processes**.
- **Canary Deployment:** 4 Uvicorn workers $\times$ 1 child process = **max 4 concurrent transcoding processes**.
- **Cluster Total:** Strictly bounded to a maximum of **8 concurrent child processes across all production instances**.
- **Cluster Peak Transcoding RAM:** $8 \times 161\text{ MB} \approx 1.28\text{ GB}$ maximum aggregate memory if all 8 workers transcode 12MP images simultaneously.

---

## 9. Canonical Publication & Failure Recovery Design

### 9.1 Publication Key Layout

Canonical media objects are stored in strictly user-scoped paths:
- Staging Key: `staging/users/{user_id}/wardrobe/{upload_id}.{ext}`
- Canonical Key: `users/{user_id}/wardrobe/{upload_id}/{canonical_sha256}.webp`

### 9.2 Transactional Integrity Across Object Storage & PostgreSQL

Object storage (Cloudflare R2) and relational databases (PostgreSQL) cannot participate in a two-phase commit (2PC). The sequence is architected to guarantee eventual consistency and clean crash recovery:

```
[Phase 3 Publication Sequence & Crash Recovery]

1. Upload Canonical Object to R2 (users/{user_id}/wardrobe/{upload_id}/{hash}.webp)
        │
        ├─► [Crash Point A: Crash before DB update]
        │   Recovery: Canonical object exists in R2, but DB still says "verifying/authorized".
        │   When client retries /complete:
        │   - Server checks if canonical_key exists in R2 with matching hash.
        │   - If found: adopts existing canonical object, skips transcoding, updates DB.
        │
2. Update PostgreSQL Completion Record (Set status='published', canonical_key, canonical_sha256)
   COMMIT Transaction (Advisory lock released)
        │
        ├─► [Crash Point B: Crash after DB update, before staging delete]
        │   Recovery: Media is fully published and operational.
        │   Staging object remains in staging/ prefix.
        │   R2 24-hour prefix lifecycle rule automatically purges abandoned staging blob.
        │
3. Delete Staging Object from R2 (staging/users/{user_id}/wardrobe/{upload_id}.{ext})
        │
4. Return 200 OK with PublishedMediaRefResponse
```

---

## 10. Database Schema and Migration Recommendation

### 10.1 Schema Evaluation: Migration 0033 vs. Migration 0034

Migration 0033 created `media_upload_authorizations` as an ephemeral upload authorization ledger with a 24-hour expiration (`expires_at`) and bounded retention pruning (`prune_expired_authorizations`).

If completion metadata (canonical key, dimensions, canonical hash) were stored solely on `media_upload_authorizations`, then pruning expired authorizations after 24 hours would destroy the completion record.

However, per Decision 4 and Phase 4 of `STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md`, the permanent reference to published media is stored directly in `wardrobe_items.image_ref` JSONB:
```json
{
  "objectKey": "users/UUID/wardrobe/UUID/HASH.webp",
  "mediaType": "image/webp",
  "width": 1920,
  "height": 1440,
  "sizeBytes": 184520,
  "contentHash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "uploadedAt": "2026-11-01T14:00:00Z",
  "status": "ready"
}
```

### 10.2 Recommendation: Additive Migration 0034 (`media_upload_authorizations` Evolution)

To support:
1. Idempotent retries of `/complete` within the 24-hour window.
2. Serialization of concurrent completion requests.
3. Failure diagnosis and attempt counting.

An additive **Migration 0034** is recommended, evolving `media_upload_authorizations` with lifecycle status columns:

#### Proposed Migration 0034 DDL Specification:
```sql
-- Revision ID: 0034
-- Revises: 0033
-- Create Date: 2026-11-01

ALTER TABLE media_upload_authorizations
    ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'authorized',
    ADD COLUMN canonical_key VARCHAR(512) NULL,
    ADD COLUMN canonical_sha256 VARCHAR(64) NULL,
    ADD COLUMN canonical_size_bytes INTEGER NULL,
    ADD COLUMN canonical_width INTEGER NULL,
    ADD COLUMN canonical_height INTEGER NULL,
    ADD COLUMN completed_at TIMESTAMP WITH TIME ZONE NULL,
    ADD COLUMN failure_reason VARCHAR(64) NULL,
    ADD COLUMN processing_attempts INTEGER NOT NULL DEFAULT 0;

CREATE INDEX ix_media_upload_authorizations_status 
    ON media_upload_authorizations (status);
```

#### Safe Downgrade:
```sql
DROP INDEX IF EXISTS ix_media_upload_authorizations_status;

ALTER TABLE media_upload_authorizations
    DROP COLUMN IF EXISTS processing_attempts,
    DROP COLUMN IF EXISTS failure_reason,
    DROP COLUMN IF EXISTS completed_at,
    DROP COLUMN IF EXISTS canonical_height,
    DROP COLUMN IF EXISTS canonical_width,
    DROP COLUMN IF EXISTS canonical_size_bytes,
    DROP COLUMN IF EXISTS canonical_sha256,
    DROP COLUMN IF EXISTS canonical_key,
    DROP COLUMN IF EXISTS status;
```

#### Migration Safety:
- Migration 0034 is 100% additive. All new columns are either `nullable` or have safe defaults.
- Existing tables (`wardrobe_items`, `users`, `user_state`) remain completely untouched.
- Shared databases `fansivibe` and `fansivibe_test` will remain untouched at revision `0032` until scheduled release deployment.

---

## 11. Security and Privacy Assessment

| Security Dimension | Threat / Risk | Phase 3 Mitigation & Invariants |
| :--- | :--- | :--- |
| **OW-1 Ownership Scoping** | Malicious caller attempts to complete another user's `upload_id` | Caller `user_id` derived exclusively from verified JWT. If `auth.user_id != user_id`, returns HTTP 404 (preventing ID enumeration). |
| **Path Traversal & Overwrite** | Client injects `../../` in key path to overwrite system files or other users' photos | Object keys generated strictly server-side using cryptographically verified UUIDs and hashes. Zero client-supplied path input accepted. |
| **Decompression Bomb (DoS)** | Attacker uploads highly compressed 100MP pixel bomb | Pillow `MAX_IMAGE_PIXELS=12MP`, dimension check before raster allocation, and kernel `RLIMIT_AS=256MB` abort with `MemoryError` in $<120$ms. |
| **Image Parser Vulnerabilities** | Memory corruption in libjpeg/libwebp C libraries | Isolated child process architecture. Process runs as unprivileged user in disposable address space; termination kills PID instantly. |
| **EXIF / GPS Privacy Leaks** | Raw camera uploads contain sensitive home GPS coordinates | Complete stripping of all EXIF/GPS metadata blocks during canonical WebP re-encoding. |
| **Token / Secret Logging** | Presigned URLs or credentials leaked in logs | `_sanitize_message` in storage adapter scrubs signatures and tokens from all error messages and logger outputs. |
| **Guest Isolation (D10 Option A)** | Guest appearance/face data accidentally persisted in cloud | Guest sessions rejected with HTTP 401. Zero cloud uploads permitted for guests. Face/appearance biometric data strictly excluded. |

---

## 12. Detailed Test Matrix

The Phase 3 test plan requires 26 exhaustive tests across four isolated test tiers:

```
[Phase 3 Test Matrix: 26 Scenarios]
├── Tier 1: Unit & Domain Logic Tests (DB-Free, Fake Storage)
│   ├── 1. test_verify_valid_webp_magic_bytes
│   ├── 2. test_verify_valid_jpeg_magic_bytes
│   ├── 3. test_reject_invalid_magic_bytes (PNG, SVG, GIF, HTML)
│   ├── 4. test_reject_empty_staging_object
│   ├── 5. test_reject_oversized_staging_object (>2MB)
│   ├── 6. test_independent_sha256_computation_and_assertion_match
│   ├── 7. test_checksum_mismatch_raises_validation_error
│   └── 8. test_aspect_ratio_preservation_math (no crop/distortion)
│
├── Tier 2: Isolated Child-Process & Transcoding Tests
│   ├── 9. test_transcode_valid_jpeg_to_canonical_webp
│   ├── 10. test_exif_orientation_normalization (tags 1..8)
│   ├── 11. test_exif_gps_metadata_completely_scrubbed
│   ├── 12. test_decompression_bomb_triggers_memory_error
│   ├── 13. test_dimension_ceiling_exceeded_rejected_before_load (>4096px, >12MP)
│   ├── 14. test_transcoder_process_timeout_and_sigkill (5.0s limit)
│   ├── 15. test_transcoder_crash_recovery_and_zombie_reaping
│   └── 16. test_per_worker_transcoding_semaphore_limits_concurrency
│
├── Tier 3: API & Concurrency Tests (Isolated PostgreSQL Test DB)
│   ├── 17. test_complete_upload_success_returns_200_published_media_ref
│   ├── 18. test_complete_upload_staging_object_missing_returns_400
│   ├── 19. test_complete_upload_expired_authorization_returns_410
│   ├── 20. test_complete_upload_cross_user_ow1_returns_404
│   ├── 21. test_complete_upload_unauthenticated_returns_401
│   ├── 22. test_idempotent_duplicate_complete_returns_same_media_ref
│   ├── 23. test_concurrent_complete_requests_serialized_via_advisory_lock
│   ├── 24. test_crash_recovery_canonical_published_db_committed_on_retry
│   └── 25. test_staging_object_deleted_after_successful_publication
│
└── Tier 4: Regression & Hardening Tests
    └── 26. test_full_regression_suite (storage, settings, auth, production hardening)
```

---

## 13. Infrastructure and Deployment Readiness

### External Prerequisites:
1. **Cloudflare R2 Bucket Configuration:**
   - Private production bucket `fansivibe-prod-media` provisioned.
   - Public access, public listing, and anonymous read strictly disabled.
   - S3-compatible credentials generated (`CLOUDFLARE_R2_ACCESS_KEY_ID`, `CLOUDFLARE_R2_SECRET_ACCESS_KEY`).
2. **R2 Lifecycle Rules:**
   - Automated prefix expiration rule: `staging/` prefix expires objects after **1 day (24 hours)**.
3. **CORS Configuration on R2:**
   - Permit direct browser/mobile HTTPS PUT uploads:
     ```json
     [
       {
         "AllowedOrigins": ["*"],
         "AllowedMethods": ["PUT"],
         "AllowedHeaders": ["Content-Type", "x-amz-*"],
         "MaxAgeSeconds": 3600
       }
     ]
     ```
4. **Backend Container Updates:**
   - Add `Pillow==10.4.0` to `backend/requirements-prod.txt`.
   - Configure `mem_limit: 2g` in `docker-compose.production.yml` for `backend-primary` and `backend-canary`.
5. **Deployment Sequencing:**
   - Step 1: Provision R2 credentials in production secret manager.
   - Step 2: Apply Migration 0033 and Migration 0034 via `alembic upgrade head`.
   - Step 3: Deploy backend image containing Phase 3 code and Pillow dependency.
   - Step 4: Verify health probe `/health` and readiness probe `/health/ready`.
   - Step 5: Route canary (5%) then primary (95%) traffic.

---

## 14. Dependency-Ordered Implementation Phases

Phase 3 is broken down into 7 discrete, dependency-ordered implementation stages:

```
Stage 3.1: Runtime Dependency & Storage Port Extension
  ├── Pin Pillow in requirements-prod.txt
  ├── Add put_object to ObjectStoragePort protocol
  ├── Implement put_object in CloudflareR2StorageAdapter
  └── Implement put_object in FakeStorageAdapter
        │
        ▼
Stage 3.2: Isolated Image Transcoder CLI & Worker Subsystem
  ├── Implement app.workers.transcoder CLI entrypoint
  ├── Configure RLIMIT_AS (256MB) and Image.MAX_IMAGE_PIXELS (12MP)
  ├── Implement EXIF orientation transpose and GPS metadata removal
  └── Implement subprocess execution manager with 5.0s SIGKILL timeout
        │
        ▼
Stage 3.3: Database Migration 0034
  ├── Create additive migration 0034_media_upload_completion.py
  ├── Add status, canonical_key, canonical_sha256, dimensions, failure metadata
  └── Validate upgrade and downgrade on disposable PostgreSQL database
        │
        ▼
Stage 3.4: Staging Verification & Publication Domain Service
  ├── Implement CompleteMediaUpload use case
  ├── Implement zero-trust staging verification (magic bytes, size, hash)
  ├── Orchestrate child-process transcoding
  ├── Publish canonical WebP to R2
  ├── Persist completion record and handle crash recovery
  └── Purge staging object
        │
        ▼
Stage 3.5: API Router & Schemas
  ├── Add UploadCompleteRequest and PublishedMediaRefResponse schemas
  ├── Register POST /v1/media/uploads/{upload_id}/complete in routers/media.py
  └── Enforce OW-1 caller scoping and advisory lock serialization
        │
        ▼
Stage 3.6: Automated Test Suite Implementation
  ├── Implement 26 comprehensive test cases in test_media_verification.py
  └── Verify 100% pass rate in SQLite and multi-session PostgreSQL
        │
        ▼
Stage 3.7: Full Regression & Hardening Verification
  └── Run full backend regression suite (storage, auth, settings, hardening)
```

---

## 15. Risks, Unresolved Questions & Decisions Requiring Owner Approval

### Item 1: Decision on Storage Port Extension (`put_object`)
- **Context:** `ObjectStoragePort` currently omits `put_object`. Transcoding JPEG fallbacks or re-encoding WebP requires the server to write new bytes to R2.
- **Recommendation:** Add `put_object(key, data, content_type, custom_metadata)` to `ObjectStoragePort` protocol and implement it on both `CloudflareR2StorageAdapter` and `FakeStorageAdapter`.

### Item 2: Decision on Migration 0034 vs Modifying Migration 0033
- **Context:** Migration 0033 has been verified in disposable environments but has NOT been applied to shared development (`fansivibe`) or test (`fansivibe_test`) databases.
- **Option A (Recommended):** Keep Migration 0033 frozen and create additive Migration 0034 (`0033 -> 0034`) to add completion status columns. This preserves clean migration history and test isolation.
- **Option B:** Amend Migration 0033 directly before it is ever applied to shared databases. (Requires updating Phase 2 tests and documentation).

### Item 3: Transcoding Architecture Selection
- **Context:** Python 3.12 `fork` in multi-threaded Uvicorn triggers deadlock deprecation warnings.
- **Recommendation:** Approve standalone CLI subprocess architecture (`asyncio.create_subprocess_exec(sys.executable, "-m", "app.workers.transcoder", ...)`), which completely eliminates thread deadlock risk and achieves 632ms latency.

### Item 4: Fast-Path Direct Promotion vs Mandatory Re-encoding
- **Context:** If a client uploads a valid WebP file that is already upright and $\le 1920$px:
  - Should the server execute a fast-path server-side `copy_object` (saving CPU cycles)?
  - OR should the server ALWAYS pass every image through the child transcoder to guarantee 100% EXIF/GPS scrubbing?
- **Recommendation:** Always pass every upload through the child transcoder. Re-encoding takes $<650$ms, guarantees zero GPS leaks, and ensures uniform canonical WebP quantization.
