# Fansivibe — Stage 2 P0-4 Phase 3.3
# Cloudflare R2 Publication Fencing & Stale-Worker Safety Audit

- **Date:** 2026-11-01
- **Target Components:**
  - Application Service: [CompleteMediaUpload](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L582-L1370)
  - Storage Infrastructure: [CloudflareR2StorageAdapter](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L64-L383)
  - Storage Contracts: [ObjectStoragePort](file:///home/tony/projects/fansivibe_v1_backup/backend/app/domain/ports/storage.py#L86-L276)
  - Database Ledger: [MediaUploadAuthorization](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/db/models.py#L1657-L1726)
  - Database Migrations: [0035_media_upload_lease.py](file:///home/tony/projects/fansivibe_v1_backup/backend/alembic/versions/0035_media_upload_lease.py) and [0036_media_upload_lease_token.py](file:///home/tony/projects/fansivibe_v1_backup/backend/alembic/versions/0036_media_upload_lease_token.py)
  - Test Harnesses: [test_media_lifecycle_remediation_p32.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation_p32.py) and [test_storage_adapter.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_storage_adapter.py)
- **Audit Type:** Strictly Read-Only Architecture, Concurrency, and Distributed Systems Audit
- **Audit Verdict:** **CORRECTIONS REQUIRED**

---

### Executive Summary

A rigorous, strictly read-only technical audit was conducted on the boundary between PostgreSQL durable lease fencing and external Cloudflare R2 object-storage side effects implemented in Phase 3.2.

The objective was to determine whether a stale or timed-out worker can modify, overwrite, or corrupt the canonical R2 object after losing its PostgreSQL lease.

While Phase 3.2 successfully introduced the `processing_lease_token` UUID and ensured that PostgreSQL row transitions are strictly fenced, **the storage layer boundary remains completely unfenced and vulnerable to silent data corruption, ETag/hash desynchronization, and phantom overwrites**.

#### Key Findings

1. **Deterministic Canonical Key Allows Phantom Overwrites (Finding F-01 — CRITICAL):**
   The canonical R2 key is derived deterministically as `users/{user_id}/wardrobe/{upload_id}/canonical.webp` across all processing attempts ([media.py:565-573](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L565-L573)). All workers write unconditionally to this exact same key via S3 `PutObject` ([storage.py:353-365](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L353-L365)). S3 and Cloudflare R2 apply Last-Write-Wins (LWW) semantics without conditional write headers (`If-None-Match`).
2. **`asyncio.to_thread` Leaks In-Flight Network Requests Across Cancellation (Finding F-02 — CRITICAL):**
   When `CompleteMediaUpload.execute` hits its top-level timeout (`self._pipeline_timeout_seconds = 25.0s`), `asyncio.wait_for` raises `asyncio.TimeoutError` and cancels the coroutine. However, `put_object` delegates blocking S3 network I/O to a background thread via `asyncio.to_thread(_put)` ([storage.py:365](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L365)). In Python, running OS threads **cannot be cancelled or interrupted**. The background thread continues to stream data over TCP and successfully finishes the S3 PUT against Cloudflare R2 long after the coroutine has aborted and the lease was released.
3. **PostgreSQL Fencing Cannot Fence Remote HTTP Sockets (Finding F-03 — HIGH):**
   The database fencing token (`processing_lease_token`) protects only PostgreSQL rows. Once an HTTP PUT packet is sent to Cloudflare R2, PostgreSQL has zero visibility or control over R2 state. If Worker A's lease expires during a slow upload and Worker B claims ownership, transcodes, and publishes, Worker A's delayed PUT will complete moments later and **silently overwrite Worker B's published canonical object in R2**. Worker A's subsequent DB finalization will abort with `LEASE_LOST` (409), but R2 remains mutated with Worker A's payload, while PostgreSQL permanently records Worker B's hash and dimensions.
4. **Unfenced Staging Deletion on Validation Errors (Finding F-04 — HIGH):**
   On every image validation or transcoding failure in `_execute_pipeline` ([media.py:1116, 1128, 1143, 1161, 1174, 1188, 1200, 1211, 1226, 1236](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1116-L1236)), the service calls `self._record_failure(upload_id, lease_token, ...)`. The code **completely ignores the boolean return value** (`still_owner`) and immediately executes `await self._storage.delete_object(staging_key)`. A stale worker that lost its lease will delete the staging object while a successor worker is actively reading or transcoding it.
5. **False Confidence from In-Memory Coroutine Test Double (Finding F-05 — MEDIUM):**
   Existing tests in [test_media_lifecycle_remediation_p32.py:420-450](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation_p32.py#L420-L450) simulate cancellation using a custom `HangingPutStorage` subclass that calls `await asyncio.sleep(10.0)`. Cancelling an `asyncio.sleep` coroutine immediately aborts the coroutine before `super().put_object` is called. This masks the reality of production `CloudflareR2StorageAdapter`, where Boto3 socket I/O executes in an uninterruptible OS thread.

---

### Section 1: Canonical Object Key and Write Semantics

#### 1.1 Canonical Key Derivation

In [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L565-L573):

```python
def get_canonical_object_key(user_id: UUID, upload_id: UUID) -> str:
    """Derive deterministic canonical WebP storage key from user ID and upload ID (Stage 2 P0-4 Phase 3.1).

    Guarantees:
    - Derived strictly from authenticated owner and upload ID.
    - Never derived from arbitrary client input.
    - Matches OW-1 namespacing and .webp canonical format.
    """
    return f"users/{str(user_id)}/wardrobe/{str(upload_id)}/canonical.webp"
```

In [backend/app/application/media.py:1247-1261](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1247-L1261):

```python
# Step 13: Publish canonical WebP object to private storage
canonical_key = get_canonical_object_key(user_id, upload_id)
try:
    await self._storage.put_object(
        key=canonical_key,
        data=transcode_result.canonical_bytes,
        content_type="image/webp",
        custom_metadata={
            "user_id": str(user_id),
            "upload_id": str(upload_id),
            "sha256": transcode_result.canonical_sha256,
            "width": str(transcode_result.width),
            "height": str(transcode_result.height),
            "source_sha256": actual_sha256,
        },
    )
```

#### 1.2 Storage Operation Semantics

In [backend/app/infrastructure/external/storage.py:346-377](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L346-L377):

```python
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
        return StorageObjectMetadata(...)
```

#### 1.3 Audit Findings on Storage Semantics

| Question | Assessment | Evidence in Code |
| :--- | :--- | :--- |
| **Is the key deterministic per upload, or unique per processing attempt?** | **Deterministic per upload.** | Key is hardcoded to `.../canonical.webp`. It does not include `processing_lease_token`, attempt counter, or timestamp ([media.py:573](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L573)). |
| **Can two workers write to the same key?** | **YES.** | Any worker processing the same `upload_id` issues a PUT to the exact same key: `users/{user_id}/wardrobe/{upload_id}/canonical.webp`. |
| **Does the R2 adapter use unconditional PUT or conditional creation?** | **Unconditional PUT.** | `_client.put_object(**params)` is invoked without conditional headers such as `If-None-Match: "*"` ([storage.py:362](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L362)). |
| **Does a later PUT replace an existing object?** | **YES.** | Standard S3/R2 semantics apply: an unconditional PUT immediately replaces the existing object and updates its ETag. |
| **Does the adapter expose version IDs, ETags, or conditional-write semantics?** | **NO.** | `ObjectStoragePort.put_object` takes no condition parameters; `VersionId` is ignored; ETag is returned in metadata but never used for concurrency gating ([storage.py:346](file:///home/tony/projects/fansivibe_v1_backup/backend/app/domain/ports/storage.py#L246-L271)). |
| **Can a stale worker's delayed request overwrite a newer worker's publication?** | **YES.** | A stale worker whose PUT request is delayed in flight will overwrite the object in R2 even after another worker successfully claimed ownership and published. |

---

### Section 2: Cancellation and Background-Thread Behavior

#### 2.1 Trace of Operations Through `asyncio.to_thread`

Every storage operation in `CloudflareR2StorageAdapter` delegates synchronous Boto3 client calls to a thread via `asyncio.to_thread`:

1. `generate_presigned_put_url`: `asyncio.to_thread(_generate)` ([storage.py:177](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L177))
2. `generate_presigned_get_url`: `asyncio.to_thread(_generate)` ([storage.py:205](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L205))
3. `get_object_stream`: `asyncio.to_thread(_get)` and `asyncio.to_thread(body.read, chunk_size)` ([storage.py:220, 231](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L220))
4. `get_object_metadata`: `asyncio.to_thread(_head)` ([storage.py:279](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L279))
5. `delete_object`: `asyncio.to_thread(_delete)` ([storage.py:305](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L305))
6. `copy_object`: `asyncio.to_thread(_copy)` ([storage.py:334](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L334))
7. `put_object`: `asyncio.to_thread(_put)` ([storage.py:365](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L365))

#### 2.2 Mechanism of Thread Persistence Upon Coroutine Cancellation

When a task awaiting `asyncio.to_thread` is cancelled (via `asyncio.wait_for` timeout or task cancellation):

1. `asyncio.to_thread` creates a `concurrent.futures.Future` and submits the target callable to Python's default `ThreadPoolExecutor`.
2. When the coroutine receives a cancellation signal (`CancelledError`):
   - The `asyncio` event loop detaches from the `Future`.
   - The coroutine unwinds immediately and enters exception handlers.
3. **The underlying OS worker thread continues executing**.
   - In Python and POSIX, there is no thread interruption signal for threads blocked in synchronous C extensions or socket I/O (`urllib3` / `OpenSSL`).
   - The thread running `_put` continues streaming bytes to the TCP socket connected to the Cloudflare R2 endpoint.
   - Cloudflare R2 receives the complete HTTP PUT, commits the object to NVMe storage, and sends back an `HTTP/1.1 200 OK` response with ETag.
   - The thread receives the response, sets the result on the detached `Future`, and returns to the thread pool.
4. **Conclusion:** Cancellation of the Python coroutine **provides zero guarantee** that the external side effect will not occur. The S3 PUT request **will complete** if the network socket remains healthy.

---

### Section 3: Fencing-Token Coverage & Boundary Analysis

#### 3.1 Audited Fencing Checks

In [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py), `processing_lease_token` is checked in 4 places:

1. `renew_lease` ([media.py:625, 637](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L625)):
   `WHERE upload_id = :upload_id AND processing_lease_token = :lease_token AND status = 'processing'`
2. `_record_failure` ([media.py:660](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L660)):
   `WHERE upload_id == upload_id AND processing_lease_token == lease_token`
3. `_record_retryable_status` ([media.py:687](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L687)):
   `WHERE upload_id == upload_id AND processing_lease_token == lease_token AND status == 'processing'`
4. `_finalize_published_record` ([media.py:1317](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1317)):
   `WHERE user_id == user_id AND upload_id == upload_id AND processing_lease_token == lease_token AND status == 'processing'`

#### 3.2 Analysis of Pre-PUT and Post-PUT Coverage

```
[Worker A Pipeline Execution]
  │
  ├─ 1. Advisory Lock Claim & DB Commit (Lease Token A generated & persisted)
  ├─ 2. Advisory Lock Released
  ├─ 3. [Heartbeat Task Active]
  │
  ├─ 4. Inspect & Read Staging Key (External S3 Read)
  ├─ 5. Child Subprocess Transcoding (1-5 seconds)
  │
  ├─ [NO FENCING CHECK HERE]  <-- GAP: Worker does not check lease immediately before PUT!
  │
  ├─ 6. Storage put_object(canonical_key) Begins (Dispatched to ThreadPool)
  │      │
  │      │◄─── Network stall / GC pause occurs here.
  │      │◄─── Heartbeat fails; Lease expires in DB (t > 30s).
  │      │◄─── Worker B claims Lease Token B, transcodes, publishes, commits DB!
  │      │
  │      └─── Thread completes HTTP PUT to Cloudflare R2! (OVERWRITES CANONICAL OBJECT)
  │
  └─ 7. _finalize_published_record(lease_token=Token A)
         │
         ▼
     [DB Check Fails]: rowcount == 0 -> Raises LEASE_LOST (409)
```

#### 3.3 Domain Boundary Breakdown

- **Domain A: PostgreSQL State Protection (PROTECTED):**
  PostgreSQL rows are strictly protected by `processing_lease_token = :lease_token`. A stale worker cannot commit `status = 'published'`, cannot clear an active worker's lease, and cannot record failure.
- **Domain B: Cloudflare R2 Object Mutation Protection (UNPROTECTED):**
  Cloudflare R2 is an external system with no integration with PostgreSQL lease tokens. Because `canonical_key` is identical across attempts, an in-flight PUT from a stale worker writes directly to `canonical.webp`, corrupting the canonical object in R2.
- **Domain C: Cleanup of Stale Objects (PARTIALLY BROKEN):**
  In all image validation failure paths ([media.py:1116-1240](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1116-L1240)), `self._record_failure` is called, but its return value (`still_owner`) is **never checked**. The worker proceeds unconditionally to call `await self._storage.delete_object(staging_key)`. If Worker A lost its lease, it will delete `staging_key` while Worker B is attempting to process it.

---

### Section 4: Crash and Race Sequences

#### Sequence A: Worker A begins canonical PUT, loses lease, Worker B publishes, then Worker A's PUT completes.

- **Trace:**
  1. Worker A claims lease with `token_A`.
  2. Worker A transcodes and issues `await self._storage.put_object(canonical_key, data_A)`.
  3. Worker A's thread encounters network latency to Cloudflare R2.
  4. 30 seconds elapse; Worker A's heartbeat fails or is blocked; lease expires in PostgreSQL.
  5. Worker B claims the expired lease with `token_B`.
  6. Worker B reads staging, transcodes (`data_B`), and calls `await self._storage.put_object(canonical_key, data_B)`.
  7. Worker B's PUT finishes; R2 contains `data_B`.
  8. Worker B executes `_finalize_published_record(lease_token=token_B)`: PostgreSQL row updated to `status='published'`, `canonical_sha256=sha256(data_B)`. Worker B commits and returns 200 OK.
  9. Now, Worker A's delayed PUT completes in R2! It unconditionally overwrites `canonical_key` with `data_A`.
  10. Worker A attempts `_finalize_published_record(lease_token=token_A)`: rowcount is 0; Worker A raises 409 `LEASE_LOST`.
- **Outcome:** PostgreSQL holds Worker B's metadata (`canonical_sha256`), but R2 holds Worker A's binary bytes (`data_A`). Downstream consumers fetching the canonical URL will download `data_A`, causing checksum verification failures, broken image dimensions, or stale image versions.
- **Verdict:** **UNSAFE (Silent R2 Object Overwrite / Hash Desynchronization)**.

#### Sequence B: Worker A times out during R2 publication, Worker B retries, and Worker A's network request completes late.

- **Trace:**
  1. Worker A begins `put_object(canonical_key, data_A)` via `asyncio.to_thread(_put)`.
  2. Total pipeline execution hits `pipeline_timeout_seconds` (25.0s).
  3. `asyncio.wait_for` raises `asyncio.TimeoutError`.
  4. Worker A's coroutine unwinds, executes `_record_retryable_status(upload_id, token_A)`, resets `status = 'authorized'`, and returns HTTP 504.
  5. The underlying thread running `_put` continues executing in the background.
  6. The client immediately retries; Worker B claims the lease with `token_B`.
  7. Worker B transcodes and writes `data_B` to `canonical_key`.
  8. Worker B finalizes in DB with `token_B`.
  9. Worker A's background thread finishes its HTTP PUT to R2, overwriting `data_B` with `data_A`.
- **Verdict:** **UNSAFE (Background Thread Leak / Phantom Overwrite)**.

#### Sequence C: Worker A publishes an object but loses ownership before final database commit.

- **Trace:**
  1. Worker A claims lease with `token_A`.
  2. Worker A transcodes and successfully writes `canonical_key` to R2.
  3. Before Worker A can commit to PostgreSQL, Worker A's database connection drops, or the 30s lease expires.
  4. Worker B claims the lease with `token_B`.
  5. Worker B enters Step 7 (Crash Recovery Check, [media.py:956-1079](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L956-L1079)).
  6. Worker B finds the canonical object in R2, verifies size, verifies `RIFF...WEBP` magic bytes, matches `trusted_sha` against `canonical_meta.custom_metadata["sha256"]`, decodes dimensions with PIL, verifies staging consistency, and adopts the canonical object.
  7. Worker B finalizes in DB with `token_B`.
- **Verdict:** **SAFE (Gracefully recovered by Phase 3.2 fail-closed Crash Recovery)**. Note: This safety holds only because Worker B arrived *after* Worker A finished writing, and Worker A did not issue subsequent writes.

#### Sequence D: Worker A's stale cleanup deletes or modifies an object published by Worker B.

- **Trace (Modification):**
  As proven in Sequence A and B, Worker A's delayed PUT will overwrite `canonical_key` published by Worker B.
- **Trace (Canonical Deletion):**
  `CompleteMediaUpload` contains **zero** calls to `delete_object(canonical_key)`. Worker A never deletes `canonical_key`.
- **Trace (Staging Deletion):**
  If Worker A stalls, loses its lease to Worker B, and subsequently encounters an image validation error or decode failure, Worker A enters lines 1116-1240:
  ```python
  self._record_failure(upload_id, lease_token, "CORRUPT_IMAGE")  # Returns False (0 rows updated)
  try:
      await self._storage.delete_object(staging_key)  # UNCONDITIONAL DELETION!
  except Exception:
      pass
  ```
  Worker A deletes `staging_key` while Worker B is actively reading it! Worker B fails with `STAGING_OBJECT_NOT_FOUND` (400) or `StorageNotFoundError`.
- **Verdict:**
  - Canonical Object Modification: **UNSAFE**.
  - Canonical Object Deletion: **SAFE** (no code deletes canonical keys).
  - Staging Object Deletion: **UNSAFE** (unfenced deletion on validation failure).

#### Sequence E: Two valid workers attempt recovery or publication concurrently.

- **Trace:**
  1. Worker A and Worker B receive concurrent completion requests for the same `upload_id`.
  2. Both attempt to acquire PostgreSQL advisory lock: `SELECT pg_advisory_xact_lock(:lock_key)`.
  3. Worker A acquires the lock; Worker B waits up to 3 seconds.
  4. Worker A claims the lease in PostgreSQL: `status = 'processing'`, `processing_lease_expires_at = db_now + 30s`.
  5. Worker A commits the transaction and releases the advisory lock ([media.py:865](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L865)).
  6. Worker B acquires the advisory lock, reads `auth`, and executes lines 805-824:
     `auth.status == 'processing'` and `processing_lease_expires_at > db_now`.
  7. Worker B raises HTTP 409 Conflict with `Retry-After: 5` and aborts.
- **Verdict:**
  - Within Valid Lease: **SAFE (Serialized by advisory lock during claim, then rejected by active lease check)**.
  - Across Expired Lease (Worker Stalled): **UNSAFE (Both workers can execute concurrent S3 PUTs to the same canonical key)**.

---

### Section 5: Architecture Recommendation — Immutable Attempt-Specific Keys

To achieve true distributed fencing between PostgreSQL and Cloudflare R2, the storage key must be **immutable and unique per processing attempt**.

#### 5.1 Proposed Attempt-Key Architecture

Instead of a static key, the key is parameterized by the worker's unique `lease_token`:

```
users/{user_id}/wardrobe/{upload_id}/attempts/{lease_token}.webp
```

#### 5.2 Evaluation of Attempt-Key Properties

1. **Prevention of Stale Overwrites:**
   - Worker A writes exclusively to `attempts/{token_A}.webp`.
   - Worker B writes exclusively to `attempts/{token_B}.webp`.
   - Even if Worker A's background thread executes hours later, its write lands on its own attempt key and **cannot touch or overwrite Worker B's object**.
2. **Atomic Linearization Point in PostgreSQL:**
   - In `_finalize_published_record`:
     ```python
     stmt = (
         update(MediaUploadAuthorization)
         .where(
             MediaUploadAuthorization.upload_id == upload_id,
             MediaUploadAuthorization.processing_lease_token == lease_token,
             MediaUploadAuthorization.status == "processing",
         )
         .values(
             status="published",
             canonical_key=f"users/{user_id}/wardrobe/{upload_id}/attempts/{lease_token}.webp",
             canonical_sha256=canonical_sha256,
             canonical_size_bytes=size_bytes,
             canonical_width=width,
             canonical_height=height,
             completed_at=completed_at,
             processing_lease_token=None,
             processing_lease_expires_at=None,
         )
     )
     ```
   - Only the winning worker holding the valid `processing_lease_token` in PostgreSQL can commit.
   - The database row points permanently to the exact key written by that winning attempt.
3. **Idempotent Published Replay:**
   - When a client or subsequent worker calls `CompleteMediaUpload.execute`:
     `if auth.status == "published": return {"objectKey": auth.canonical_key, ...}`
   - The caller always receives the blessed `canonical_key` recorded in PostgreSQL.
4. **Identification of Abandoned Attempt Objects:**
   - Any object in R2 under `users/{user_id}/wardrobe/{upload_id}/attempts/` whose key does **not** match `auth.canonical_key` is an abandoned attempt object.
5. **Safe Cleanup Without Deleting Active Objects:**
   - Background orphan cleanup cron queries PostgreSQL:
     `SELECT canonical_key FROM media_upload_authorizations WHERE upload_id = :upload_id AND status = 'published'`
   - The cleaner only deletes keys where `key != auth.canonical_key`.
   - Because `lease_token` is a UUIDv4, name collision is mathematically impossible.
6. **Is a Stable Canonical Key Necessary?**
   - **NO.**
   - In Fansivibe architecture, wardrobe items and media consumers store the `objectKey` string returned by the completion endpoint (or resolved from `media_upload_authorizations.canonical_key`).
   - Image retrieval generates presigned GET URLs from the stored `objectKey`.
   - No external client or service guesses or hardcodes the key path `.../canonical.webp`.

---

### Section 6: Test Coverage Analysis

#### 6.1 Review of Existing Test Harnesses

| Test File | Relevant Tests | Reality vs Simulation Gaps |
| :--- | :--- | :--- |
| `test_media_lifecycle_remediation_p32.py` | `test_cancellation_during_r2_publication_reverts_lease` ([L420-L450](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation_p32.py#L420-L450)) | Uses `HangingPutStorage` with `await asyncio.sleep(10.0)`. Cancelling coroutine aborts sleep; `super().put_object` is never invoked. Does not test thread continuation or S3 network writes. |
| `test_media_lifecycle_remediation_p32.py` | `test_worker_a_tries_to_publish_after_losing_ownership` ([L244-L292](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation_p32.py#L244-L292)) | Tests only the DB query failure in `_finalize_published_record`. Does not assert whether storage bytes were overwritten. |
| `test_storage_adapter.py` | `test_streaming_read_and_close` ([L380-L403](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_storage_adapter.py#L380-L403)) | Tests body closure during streaming read cancellation. Contains zero tests for `put_object` cancellation or thread pool behavior. |
| `test_fake_storage.py` | `test_put_object_and_read` ([L50-L75](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_fake_storage.py#L50-L75)) | Pure dictionary operations. No thread pool, no network socket, no S3 concurrency semantics. |

#### 6.2 Test Gap Verdict

There are **zero automated tests** verifying:
1. Real `ThreadPoolExecutor` / `asyncio.to_thread` persistence across coroutine cancellation during an S3 PUT.
2. In-flight storage write completing after lease loss and overwriting another worker's canonical object.
3. Checksum desynchronization between PostgreSQL `canonical_sha256` and R2 object bytes.
4. Validation failure in Worker A deleting `staging_key` while Worker B is actively processing.

---

### Final Audit Summary & Verdict

Phase 3.2 established rock-solid PostgreSQL state machine fencing via `processing_lease_token`. However, because **Cloudflare R2 object storage operations are external, asynchronous, uninterruptible, and directed at a shared static key**, the system is vulnerable to silent canonical object corruption by stale workers.

- **Verdict:** **CORRECTIONS REQUIRED**
- **Action Plan:** Proceed to Phase 3.4 to implement immutable attempt keys (`.../attempts/{lease_token}.webp`), fence staging deletion on validation failures, and add thread-leak integration tests.
