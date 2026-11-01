# Fansivibe — Stage 2 P0-4 Phase 3.3
# R2 Publication Fencing & Stale-Worker Risk Matrix

- **Date:** 2026-11-01
- **Target Subsystem:** Media Upload Completion & Canonical Publication Pipeline
- **Audit Type:** Technical Risk & Distributed Systems Analysis
- **Audit Verdict:** **CORRECTIONS REQUIRED**

---

### Executive Overview

This risk matrix details the specific failure modes, concurrency vulnerabilities, and boundary failures identified during the Phase 3.3 audit of the Cloudflare R2 publication pipeline in [CompleteMediaUpload](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L582-L1370) and [CloudflareR2StorageAdapter](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L64-L383).

Each finding includes its severity classification, exact source code references, concrete reproduction sequence, production impact, and recommended remediation.

---

### Summary Risk Matrix

| Finding ID | Title | Severity | Impact Surface | Probability | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **F-01** | Deterministic Canonical Key Allows Stale Overwrites | **CRITICAL** | Data Integrity & Consistency | HIGH (under high load/network jitter) | **CORRECTIONS REQUIRED** |
| **F-02** | `asyncio.to_thread` Leaks In-Flight Network Requests Across Cancellation | **CRITICAL** | Resource Isolation & Storage State | HIGH (on timeouts) | **CORRECTIONS REQUIRED** |
| **F-03** | Fencing Token Protects PostgreSQL but Leaves Storage Unfenced | **HIGH** | Distributed Consistency | MEDIUM | **CORRECTIONS REQUIRED** |
| **F-04** | Unfenced Staging Deletion on Image Validation / Transcode Failures | **HIGH** | Reliability & Concurrent Retries | MEDIUM | **CORRECTIONS REQUIRED** |
| **F-05** | Test Suite Masks Thread-Pool Continuation via Coroutine Sleep Double | **MEDIUM** | Test Fidelity & Quality Assurance | ALWAYS (in test suite) | **CORRECTIONS REQUIRED** |

---

### Detailed Finding Reports

#### Finding F-01: Deterministic Canonical Key Allows Stale Overwrites

- **Severity:** **CRITICAL**
- **Affected Files & Lines:**
  - [backend/app/application/media.py:565-573](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L565-L573) (`get_canonical_object_key`)
  - [backend/app/application/media.py:1247-1261](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1247-L1261) (`_execute_pipeline` Step 13)
  - [backend/app/infrastructure/external/storage.py:346-377](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L346-L377) (`CloudflareR2StorageAdapter.put_object`)
- **Vulnerability Description:**
  The canonical object storage key is derived deterministically from the upload ID:
  `users/{user_id}/wardrobe/{upload_id}/canonical.webp`.
  Every processing worker or attempt targeting the same upload writes to this identical key.
  Because Cloudflare R2 and AWS S3 apply unconditional Last-Write-Wins (LWW) semantics to standard `PutObject` calls, any delayed, stale, or cancelled worker that finishes writing will overwrite whatever object currently resides at that key.
- **Reproduction Sequence:**
  1. Worker A claims lease with `lease_token_A`.
  2. Worker A transcodes the image and calls `_storage.put_object(canonical_key, data_A)`.
  3. Worker A's network interface experiences TCP retransmissions or throttling to Cloudflare R2.
  4. 30 seconds elapse. Worker A's heartbeat stalls. Worker A's lease expires in PostgreSQL.
  5. Worker B handles an incoming retry or recovery request for the same `upload_id`.
  6. Worker B claims the expired lease with `lease_token_B`.
  7. Worker B transcodes the staging payload and successfully uploads `data_B` to `canonical_key`.
  8. Worker B commits publication in PostgreSQL: `status = 'published'`, `canonical_sha256 = sha256(data_B)`.
  9. Worker B completes successfully and returns HTTP 200 with `contentHash = sha256(data_B)`.
  10. Worker A's delayed HTTP PUT to Cloudflare R2 finally completes!
  11. Cloudflare R2 replaces the object at `canonical_key` with `data_A`.
  12. Worker A attempts `_finalize_published_record(lease_token=lease_token_A)`. The database query matches 0 rows and raises 409 `LEASE_LOST`.
- **Production Impact:**
  - **Data Desynchronization:** PostgreSQL permanently records Worker B's SHA-256 hash and image dimensions (`width`, `height`), but Cloudflare R2 physically stores Worker A's binary payload.
  - **Downstream Image Failure:** When Flutter or downstream AI services download the image from the canonical URL, checksum verification fails or image dimensions do not match the database metadata.
  - **Silent Reversion:** If Worker A and Worker B generated slightly different encodings or orientation adjustments, the user's wardrobe image is silently corrupted or reverted.
- **Recommended Correction:**
  Implement immutable, attempt-specific keys:
  `users/{user_id}/wardrobe/{upload_id}/attempts/{lease_token}.webp`.
  In `_finalize_published_record`, persist the exact key corresponding to the winning `lease_token`. This makes overwriting impossible because each attempt writes to an isolated, non-overlapping path.

---

#### Finding F-02: `asyncio.to_thread` Leaks In-Flight Network Requests Across Cancellation

- **Severity:** **CRITICAL**
- **Affected Files & Lines:**
  - [backend/app/infrastructure/external/storage.py:353-366](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L353-L366) (`put_object`)
  - [backend/app/application/media.py:891-926](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L891-L926) (`execute` timeout handling)
- **Vulnerability Description:**
  In `CloudflareR2StorageAdapter`, synchronous S3 network operations are run in a thread via `asyncio.to_thread(_put)`.
  When `CompleteMediaUpload.execute` times out at 25.0 seconds, `asyncio.wait_for` raises `asyncio.TimeoutError` and cancels the coroutine.
  However, Python OS threads executing blocking socket I/O cannot be cancelled. The background thread in `ThreadPoolExecutor` continues executing `self._client.put_object(**params)` until completion, error, or socket timeout.
  Coroutines unwinding after cancellation provide **zero guarantee** that the underlying network write has stopped.
- **Reproduction Sequence:**
  1. Worker A begins canonical publication: `await self._storage.put_object(...)`.
  2. Boto3 creates an HTTP connection and begins streaming bytes in a `ThreadPoolExecutor` worker thread.
  3. The 25.0s `pipeline_timeout_seconds` deadline expires.
  4. `asyncio.wait_for` cancels `_execute_pipeline`.
  5. Worker A's coroutine unwinds to `except asyncio.TimeoutError:`, executes `_record_retryable_status`, resets `status = 'authorized'`, and raises HTTP 504.
  6. The client receives 504 and immediately retries the request.
  7. Worker B claims the lease and begins processing the retry.
  8. Meanwhile, Worker A's background thread continues running in Python's thread pool and sends the PUT request to Cloudflare R2.
  9. Worker A's late write hits Cloudflare R2 after Worker B has claimed the lease and possibly after Worker B published.
- **Production Impact:**
  - **Phantom Network Writes:** Uncontrolled background writes continue consuming network bandwidth and mutating cloud storage after a request was marked timed out or failed.
  - **Race Condition Amplification:** A timed-out worker behaves exactly like a rogue stale worker, overwriting successor publications.
- **Recommended Correction:**
  1. Enforce immutable attempt-specific keys so late background writes cannot touch canonical objects.
  2. Configure aggressive socket-level timeouts on the Boto3 client (`read_timeout=10.0s`, `connect_timeout=3.0s`) to ensure background threads fail quickly if network stalls occur.

---

#### Finding F-03: Fencing Token Protects PostgreSQL but Leaves Storage Unfenced

- **Severity:** **HIGH**
- **Affected Files & Lines:**
  - [backend/app/application/media.py:1247-1335](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1247-L1335) (`_execute_pipeline` Steps 13 & 14)
- **Vulnerability Description:**
  The `processing_lease_token` mechanism implemented in Phase 3.2 provides strict serialized fencing inside PostgreSQL transactions.
  However, there is no coordination or mutual exclusion between PostgreSQL and Cloudflare R2.
  Before invoking `_storage.put_object`, Worker A performs extensive work (staging metadata check, 2MB byte read, hash verification, MIME cross-check, and 1–5 seconds of child subprocess transcoding).
  Worker A does not perform any pre-PUT fencing check before calling `_storage.put_object`.
  Even if it did, once the PUT is dispatched over TCP, PostgreSQL fencing cannot revoke or prevent the R2 mutation.
- **Reproduction Sequence:**
  1. Worker A claims lease in PostgreSQL.
  2. Worker A transcodes the image.
  3. Worker A's heartbeat task fails due to temporary database connection pool exhaustion.
  4. 30 seconds pass; Worker A's lease expires in PostgreSQL.
  5. Worker A begins `put_object(canonical_key, data)`.
  6. Worker B claims the lease in PostgreSQL.
  7. Worker A's `put_object` writes to R2.
  8. Worker A calls `_finalize_published_record`: PostgreSQL rejects the update because `processing_lease_token` does not match.
  9. PostgreSQL is protected, but R2 object storage was mutated without authorization.
- **Production Impact:**
  - **Partial Distributed Transaction Failure:** External side effects occur without corresponding database commit.
  - **Orphan Object Leaks:** Untracked objects or corrupted payloads remain in Cloudflare R2.
- **Recommended Correction:**
  1. Adopt immutable attempt-specific keys so uncommitted writes are harmless isolated files.
  2. Add an explicit `renew_lease` pre-flight check immediately before initiating the storage upload. If `renew_lease` returns `False`, abort immediately before initiating the S3 upload.

---

#### Finding F-04: Unfenced Staging Deletion on Image Validation / Transcode Failures

- **Severity:** **HIGH**
- **Affected Files & Lines:**
  - [backend/app/application/media.py:1116-1120](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1116-L1120) (empty object)
  - [backend/app/application/media.py:1128-1132](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1128-L1132) (object too large)
  - [backend/app/application/media.py:1143-1147](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1143-L1147) (payload bounds)
  - [backend/app/application/media.py:1161-1165](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1161-L1165) (checksum mismatch)
  - [backend/app/application/media.py:1174-1178](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1174-L1178) (invalid signature)
  - [backend/app/application/media.py:1188-1192](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1188-L1192) (non-JPEG/WebP)
  - [backend/app/application/media.py:1200-1204](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1200-L1204) (MIME mismatch WebP)
  - [backend/app/application/media.py:1211-1215](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1211-L1215) (MIME mismatch JPEG)
  - [backend/app/application/media.py:1226-1230](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1226-L1230) (ImageValidationError)
  - [backend/app/application/media.py:1236-1240](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1236-L1240) (MemoryLimitExceededError)
- **Vulnerability Description:**
  In `_finalize_published_record` ([media.py:1333](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1333)), staging deletion is correctly gated by `res.rowcount > 0` (only deleting staging if publication committed).
  However, in **all ten failure branches** in `_execute_pipeline`, `self._record_failure(...)` is invoked, but its boolean return value is ignored:
  ```python
  self._record_failure(upload_id, lease_token, "CHECKSUM_MISMATCH")
  try:
      await self._storage.delete_object(staging_key)  # Unconditional deletion!
  except Exception:
      pass
  ```
  If Worker A's lease expired and Worker B claimed ownership, Worker A will execute `delete_object(staging_key)` despite `_record_failure` returning `False`.
- **Reproduction Sequence:**
  1. Worker A claims lease for `upload_id`.
  2. Worker A experiences a temporary hang during reading staging bytes.
  3. Worker A's lease expires; Worker B claims the lease.
  4. Worker A resumes, encounters a transient socket checksum mismatch or corruption, and enters a failure block.
  5. Worker A calls `_record_failure(upload_id, lease_token_A, ...)`, which affects 0 rows in PostgreSQL.
  6. Worker A proceeds directly to `await self._storage.delete_object(staging_key)`.
  7. Cloudflare R2 deletes the staging object.
  8. Worker B, which was actively downloading or reading the staging object, fails with `StorageNotFoundError` or `STAGING_OBJECT_NOT_FOUND`.
- **Production Impact:**
  - Legitimate uploads undergoing recovery or retries fail catastrophically because their staging bytes are deleted by a defunct worker.
- **Recommended Correction:**
  Refactor all failure branches to enforce fencing ownership:
  ```python
  still_owner = self._record_failure(upload_id, lease_token, reason)
  if still_owner:
      try:
          await self._storage.delete_object(staging_key)
      except Exception:
          pass
  ```

---

#### Finding F-05: Test Suite Masks Thread-Pool Continuation via Coroutine Sleep Double

- **Severity:** **MEDIUM**
- **Affected Files & Lines:**
  - [backend/tests/test_media_lifecycle_remediation_p32.py:420-450](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation_p32.py#L420-L450) (`test_cancellation_during_r2_publication_reverts_lease`)
  - [backend/tests/fakes/fake_storage.py:74-88](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/fakes/fake_storage.py#L74-L88)
- **Vulnerability Description:**
  In `test_cancellation_during_r2_publication_reverts_lease`, simulated delay is implemented as:
  ```python
  class HangingPutStorage(FakeStorageAdapter):
      async def put_object(self, key, data, content_type="application/octet-stream", custom_metadata=None):
          await asyncio.sleep(10.0)
          return await super().put_object(key, data, content_type, custom_metadata)
  ```
  When the test executes `task.cancel()`, Python's event loop immediately cancels the `asyncio.sleep(10.0)` coroutine. Execution unwinds before `super().put_object` is ever reached.
  In production `CloudflareR2StorageAdapter`, `put_object` calls `await asyncio.to_thread(_put)` where `_put` executes inside a thread. Cancellation of the coroutine does NOT cancel the thread or the S3 write.
- **Production Impact:**
  - False positive test results: the test suite asserts that cancellation prevents publication, but in real Cloudflare R2 deployments, the write continues and lands in R2.
- **Recommended Correction:**
  Create an integration test harness that uses a threaded storage stub (running a real worker thread with `time.sleep`) to test true thread-continuation semantics and prove that attempt-specific keys neutralize late writes.

---

### Phase 3.4 Remediation Roadmap

```
┌────────────────────────────────────────────────────────────────────────┐
│                        PHASE 3.4 REMEDIATION PLAN                      │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Immutable Attempt Keys:                                             │
│    - Format: users/{user_id}/wardrobe/{upload_id}/attempts/{token}.webp│
│    - R2 put_object writes strictly to attempt key                      │
│    - DB _finalize_published_record persists blessed attempt key        │
├────────────────────────────────────────────────────────────────────────┤
│ 2. Pre-PUT Fencing Gate:                                               │
│    - Check renew_lease(upload_id, lease_token) immediately prior to   │
│      invoking _storage.put_object                                      │
├────────────────────────────────────────────────────────────────────────┤
│ 3. Fenced Staging Deletion:                                            │
│    - In all 10 failure blocks, execute delete_object(staging_key) ONLY │
│      if _record_failure returned True                                  │
├────────────────────────────────────────────────────────────────────────┤
│ 4. S3 Socket Timeout Tuning:                                           │
│    - Set S3 connect_timeout=3.0s and read_timeout=10.0s                │
│      to prevent runaway background threads                             │
├────────────────────────────────────────────────────────────────────────┤
│ 5. Automated Concurrency & Thread-Leak Test Suite:                     │
│    - Test threaded late-writes completing after lease loss             │
│    - Assert PostgreSQL hash matches R2 object hash under concurrency   │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Audit Conclusion & Verdict

- **Overall Verdict:** **CORRECTIONS REQUIRED**
- Phase 3.2 is **not safe for production deployment** in multi-worker or distributed cluster topologies until the storage boundary is fenced using immutable attempt-specific keys and fenced staging deletion.
