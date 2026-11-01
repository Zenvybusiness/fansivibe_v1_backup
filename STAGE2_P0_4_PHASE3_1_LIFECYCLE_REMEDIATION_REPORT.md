# Fansivibe — Stage 2 P0-4 Phase 3.1
# Published Media Lifecycle Reliability Remediation Report
## Technical Audit Remediation & Concurrency Coordination

- **Date:** 2026-11-01
- **Status:** REMEDIATED & VERIFIED
- **Phase Target:** Stage 2 P0-4 Phase 3.1 (Published Media Lifecycle Reliability Remediation)
- **Scope Restriction:** Strictly Phase 3 lifecycle remediation. Zero Phase 4 implementation (no wardrobe association code or schema additions). Zero Flutter modifications. Zero live cloud calls. Zero shared database migrations.

---

### Executive Summary

Following the Phase 3 lifecycle audit (`STAGE2_P0_4_PHASE3_LIFECYCLE_AUDIT.md`), four critical lifecycle defects were authorized for remediation:
1. **F-01 (High):** Authorization pruning deleted published media authorization records after 24 hours.
2. **F-02 (High):** Crash recovery failed to adopt an existing canonical R2 object if the previous attempt succeeded in R2 but PostgreSQL failed before persisting `canonical_key`.
3. **F-03 (High) & F-05 (Medium):** Premature advisory lock release allowed concurrent completion requests to start duplicate transcoding pipelines; worker crashes caused permanent lockouts or uncoordinated duplicate processing.

Additionally, two architectural requirements from the audit were formally codified:
- **F-04 (High):** Codified 10 mandatory Gate 1 security rules for Phase 4 wardrobe association into `STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md`.
- **F-06 (Low):** Codified 9 operational orphan canonical object reconciliation rules for Phase 13 into `STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md` as a pre-public-release operational gate.

All code modifications, additive Alembic Migration 0035, and new comprehensive test suites have been implemented and verified. All 21 targeted remediation tests in `tests/test_media_lifecycle_remediation.py` passed (100%), all 84 existing media verification and API tests passed (100%), and 61 storage tests passed (100%). Shared databases (`fansivibe` and `fansivibe_test`) remain strictly protected at revision `0032`.

---

### Section 1: Findings and Resolutions Matrix

| Finding | Severity | Description | Remediation Implemented | Verification Status |
| :--- | :--- | :--- | :--- | :--- |
| **F-01** | High | Published authorization records deleted after 24h by `prune_expired_authorizations`. | Updated pruning query to filter `status != 'published'` (published records preserved indefinitely) and filter active leases `not_(status == 'processing' and processing_lease_expires_at >= cutoff)`. Bounded deletion preserved; canonical R2 objects never deleted. | **IMPLEMENTED & TESTED** (7 unit tests passing) |
| **F-02** | High | Canonical crash recovery failed when DB commit failed after R2 upload because `canonical_key` was NULL on retry. | Implemented deterministic server-side canonical key derivation (`users/{user_id}/wardrobe/{upload_id}/canonical.webp`). On retry, checks for existing canonical object in storage, validates ownership prefix, size, magic bytes, and SHA-256 against server evidence. Adopts valid object without re-transcoding. | **IMPLEMENTED & TESTED** (5 unit & failure-injection tests passing) |
| **F-03 & F-05** | High / Medium | Concurrent requests ran duplicate transcoding; worker crash created permanent lockout. | Implemented durable 15-second PostgreSQL processing lease via Migration 0035 (`processing_started_at`, `processing_lease_expires_at`). Atomic lease claim, DB server-time lease expiry check (`SELECT now()`), HTTP 409 Conflict with `Retry-After: 5` on contention, safe lease cleanup on success/failure/cancellation, and 5-attempt limit with 60s cooldown recovery. | **IMPLEMENTED & TESTED** (9 multi-session PostgreSQL tests passing) |
| **F-04** | High | Wardrobe association could blindly trust client `image_ref`. | Documented 10 mandatory Gate 1 security validation rules in `STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md`. No Phase 4 code written. | **DOCUMENTED & RATIFIED** (Phase 4 Gate 1) |
| **F-06** | Low | Orphaned canonical storage objects without DB records. | Documented 9 operational reconciliation requirements in `STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md`. Classified as pre-public-release operational gate. | **DOCUMENTED & RATIFIED** (Phase 13 Gate) |

---

### Section 2: Exact Functions and Files Changed

1. **`backend/alembic/versions/0035_media_upload_lease.py` (New):**
   - Chained from `0034_media_upload_completion`.
   - Adds `processing_started_at` (`DateTime(timezone=True)`, nullable) and `processing_lease_expires_at` (`DateTime(timezone=True)`, nullable).
   - Adds composite index `ix_media_upload_authorizations_lease` on `(status, processing_lease_expires_at)`.
   - Provides symmetric `upgrade()` and `downgrade()`.

2. **`backend/app/infrastructure/db/models.py`:**
   - Updated `MediaUploadAuthorization`:
     - Added `processing_started_at: Mapped[Optional[datetime]]`
     - Added `processing_lease_expires_at: Mapped[Optional[datetime]]`
     - Added `Index("ix_media_upload_authorizations_lease", "status", "processing_lease_expires_at")` to `__table_args__`.

3. **`backend/app/application/media.py`:**
   - **`get_canonical_object_key(user_id: UUID, upload_id: UUID) -> str`:** Added deterministic canonical key generator (`users/{user_id}/wardrobe/{upload_id}/canonical.webp`).
   - **`prune_expired_authorizations`:**
     - Added condition `MediaUploadAuthorization.status != "published"` to preserve published records indefinitely.
     - Added lease protection: excludes records where `status == "processing"` and `processing_lease_expires_at >= cutoff`.
     - Preserved bounded batch deletions and non-deletion of storage objects.
   - **`CompleteMediaUpload.execute`:**
     - *Early Idempotency Check:* Checks `auth.status == "published"` *before* the 24-hour upload expiration check, ensuring completed uploads can be replayed indefinitely regardless of original authorization age.
     - *Durable Lease Claim:* Inspects active lease using PostgreSQL server time (`SELECT now()`); if an active lease exists (`status == "processing"` and `lease_expires_at > db_now`), raises HTTP 409 Conflict with `Retry-After: 5`.
     - *Attempt Limit & Cooldown:* If `processing_attempts >= 5`, checks elapsed time since `processing_started_at`. If >= 60 seconds, resets counter to 1 with warning log (preventing permanent lockout); otherwise raises 409 with `Retry-After: 60`.
     - *Atomic State Transition:* Sets `status = "processing"`, `processing_started_at = db_now`, `processing_lease_expires_at = db_now + 15s`, increments `processing_attempts`, commits to PostgreSQL, and releases advisory lock *before* external I/O.
     - *Canonical Crash Recovery Check:* Uses `auth.canonical_key or get_canonical_object_key(user_id, upload_id)`. Verifies object existence, user prefix, WebP magic bytes, size bounds ($0 < \text{size} \le 2\text{MB}$), and matches SHA-256 against server-calculated digest. If valid, finalizes DB record and deletes staging object without re-transcoding.
     - *Safe Lease Cleanup:* Wrapped in `try...finally`: clears `processing_lease_expires_at = None` on success (`_finalize_published_record`), terminal failure (`_record_failure`), retryable failure (`_record_retryable_status`), and unhandled exception / task cancellation.

4. **`STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md`:**
   - Updated **Phase 4: Wardrobe Integration** with **Mandatory Gate 1** (10 security rules for `AddWardrobeItem` and `UpdateWardrobeItem`).
   - Updated **Phase 13: Operations & Hardening** with **Pre-Public-Release Operational Gate** (9 orphan reconciliation rules).

5. **`backend/tests/test_media_api.py` & `backend/tests/test_media_verification.py`:**
   - Updated migration head and chain assertions to include `0035`.
   - Updated crash recovery test to exercise deterministic key scoping and server validation.

6. **`backend/tests/test_media_lifecycle_remediation.py` (New):**
   - Created 21 exhaustive tests specifically verifying F-01, F-02, F-03, and F-05.

---

### Section 3: Published-Record Retention Behavior (F-01)

- **Audit Defect:** `prune_expired_authorizations` previously pruned all records where `expires_at < cutoff` without checking status, deleting published records after 24 hours.
- **Remediation Invariant:**
  - Published records (`status == 'published'`) are explicitly excluded from pruning:
    ```python
    delete_stmt = (
        delete(MediaUploadAuthorization)
        .where(
            MediaUploadAuthorization.upload_id.in_(subquery),
            MediaUploadAuthorization.status != "published",
        )
    )
    ```
  - Records under active processing (`status == 'processing'` and `processing_lease_expires_at >= cutoff`) are likewise protected from deletion.
  - Expired authorized, failed, and expired records continue to be pruned in bounded batches (default 1,000 per commit).
  - Pruning never touches Cloudflare R2 storage objects (canonical media is preserved).
  - Published authorization records remain retained indefinitely until Phase 4 associates them into `wardrobe_items.image_ref`.

---

### Section 4: Canonical Crash Recovery Evidence (F-02)

- **Audit Defect:** If canonical WebP upload succeeded in R2 but the PostgreSQL commit failed, a retry saw `canonical_key = NULL`. The previous code only checked `if auth.canonical_key:`, bypassing recovery and re-transcoding or failing.
- **Remediation Implementation:**
  1. The canonical key is deterministically derived as:
     `canonical_key = auth.canonical_key or get_canonical_object_key(user_id, upload_id)`
     (`users/{user_id}/wardrobe/{upload_id}/canonical.webp`).
  2. The service checks `await self._storage.get_object_metadata(canonical_key)`.
  3. If metadata exists, the service enforces zero-trust validation:
     - User ownership: key must start with `users/{user_id}/`.
     - Size bound: $0 < \text{size} \le 2\text{MB}$.
     - Server byte inspection: reads object bytes, verifies WebP magic bytes (`RIFF...WEBP`), and calculates SHA-256 digest.
     - Integrity match: if `auth.canonical_sha256` was recorded, verifies SHA-256 match; if staging object exists, verifies digest matches valid transcode result.
  4. If valid, the service bypasses re-transcoding, commits the published record to PostgreSQL, deletes the staging object, and returns HTTP 200.
  5. If the canonical object is missing, corrupted, or foreign, the service safely proceeds with fresh transcoding.

---

### Section 5: Durable Processing Lease Design (F-03 & F-05)

- **Audit Defect:** The per-upload advisory lock was released before transcoding started. Multiple concurrent completion requests could enter the transcoding pipeline simultaneously. If a worker crashed during transcoding, `status` remained `processing` with no timeout, permanently locking out retries.
- **Durable Lease Implementation:**
  - **Schema:** Migration 0035 added `processing_started_at` and `processing_lease_expires_at` to `media_upload_authorizations`.
  - **Lease Duration:** 15 seconds initial lease.
  - **Server Time Source:** Active lease checks query PostgreSQL server time (`SELECT now()`), eliminating container clock skew.
  - **Concurrency Control:**
    - Worker A claims lease in a short DB transaction:
      ```python
      auth.status = "processing"
      auth.processing_started_at = db_now
      auth.processing_lease_expires_at = db_now + timedelta(seconds=15)
      auth.processing_attempts += 1
      db.commit()
      ```
    - Worker B encountering `status == 'processing'` and `processing_lease_expires_at > db_now` raises HTTP 409 `CONFLICT` ("Upload is currently being processed by another worker") with `Retry-After: 5`.
  - **Crash Recovery & Cooldown:**
    - If a worker crashes, the lease expires after 15 seconds.
    - Subsequent requests inspect `processing_lease_expires_at <= db_now`. If expired, the request is permitted to reclaim the lease.
    - If `processing_attempts >= 5`, the service checks if at least 60 seconds have elapsed since `processing_started_at`. If so, it resets `processing_attempts = 1` and logs a recovery warning, allowing safe worker recovery without permanent lockouts.
  - **Lease Cleanup:**
    - On publication: `processing_lease_expires_at = None`.
    - On terminal failure: `processing_lease_expires_at = None`, `status = 'failed'`.
    - On retryable failure / exception / cancellation: `processing_lease_expires_at = None`, `status = 'authorized'`.

---

### Section 6: Independent PostgreSQL Concurrency Results

Tests executed against disposable PostgreSQL database `fansivibe_disposable_phase3_1_test` using genuine multi-session threads:
- **Two Concurrent Requests (`test_two_concurrent_completion_requests_exactly_one_claims_lease`):**
  - Thread 1 and Thread 2 hit `CompleteMediaUpload` simultaneously.
  - Result: Exactly 1 thread successfully claimed the lease; the other thread received HTTP 409 Conflict with `Retry-After: 5`. PASSED.
- **Ten Concurrent Requests (`test_ten_concurrent_completion_requests_no_duplicate_processing`):**
  - 10 threads hit `CompleteMediaUpload` simultaneously.
  - Result: Exactly 1 thread acquired the lease; 9 threads received HTTP 409 Conflict. Zero duplicate processing attempts. PASSED.
- **Lease Expiry Permits Worker Recovery (`test_lease_expiry_permits_worker_recovery`):**
  - Record left in `processing` with expired lease (`expires_at = db_now - 10s`).
  - Result: New worker safely claimed lease and progressed. PASSED.
- **Crashed Worker Leaves Recoverable State (`test_crashed_worker_leaves_recoverable_state`):**
  - Worker simulated crash (aborted without clearing lease).
  - Result: After 15s expiry, retry safely reclaimed upload. PASSED.
- **Published Idempotency Across Workers (`test_published_completion_remains_idempotent_across_workers`):**
  - Replaying completion on published upload across different workers returns identical ready response without acquiring leases. PASSED.

---

### Section 7: Migration Details and Shared Database Protection

- **Migration Revision Chain:** `0032 -> 0033 -> 0034 -> 0035`.
  - `0035_media_upload_lease.py`: adds `processing_started_at`, `processing_lease_expires_at`, index `ix_media_upload_authorizations_lease`.
- **Single Linear Head:** `alembic heads` confirms exactly `['0035']`.
- **Upgrade and Downgrade:** Tested `upgrade(0035) -> downgrade(0034) -> upgrade(0035)` with zero errors.
- **Shared Database Protection:**
  - Both shared databases `fansivibe` and `fansivibe_test` were verified via PostgreSQL query:
    - `fansivibe`: `alembic_version = [('0032',)]`, `media_upload tables = []`.
    - `fansivibe_test`: `alembic_version = [('0032',)]`, `media_upload tables = []`.
  - Disposable database `fansivibe_disposable_phase3_1_test` was created for isolation testing and subsequently dropped. Zero disposable databases remain.

---

### Section 8: Failure-Injection Test Results

From `tests/test_media_lifecycle_remediation.py`:
1. **DB Commit Failure After R2 Publication:**
   - Injected DB failure during initial publication commit.
   - Retry triggered canonical crash recovery, verified server-side evidence, adopted existing canonical object, committed DB row, and deleted staging object. PASSED.
2. **Corrupted Canonical Bytes in Storage:**
   - Injected corrupted bytes into storage canonical key.
   - Crash recovery detected invalid magic bytes / SHA-256 mismatch, rejected adoption, and fell back to transcoding valid staging object. PASSED.
3. **Foreign / Unrelated Canonical Object:**
   - Injected object under foreign user prefix.
   - Crash recovery rejected foreign object and fell back safely. PASSED.
4. **Missing Canonical Object on Retry:**
   - Injected missing canonical object.
   - Crash recovery safely proceeded with transcoding. PASSED.
5. **Idempotent Replay After 24-Hour Expiration:**
   - Tested published record where `expires_at` was 48 hours in the past.
   - Verification proved published status bypasses expiration check and returns stable 200 response. PASSED.

---

### Section 9: F-04 Phase 4 Security Requirements (Mandatory Gate 1)

Documented in `STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md`:
Before `AddWardrobeItem` or `UpdateWardrobeItem` accepts an `image_ref`, the backend must enforce:
1. Parse typed media reference (`PublishedMediaRefResponse` or UUID).
2. Resolve the referenced record in `media_upload_authorizations`.
3. Enforce authenticated caller owns the media (`user_id == caller_id`).
4. Confirm `status == 'published'`.
5. Confirm canonical metadata (`canonical_key`, `canonical_sha256`, dimensions, size) is present.
6. Reject staging keys (`staging/...`).
7. Reject arbitrary object keys.
8. Reject another user's media reference.
9. Reject nonexistent or unpublished media.
10. Prevent references to unrelated object namespaces.

---

### Section 10: F-06 Phase 13 Release Gate (Orphan Reconciliation)

Documented in `STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md`:
1. Discover unreferenced canonical objects under `users/` prefix in R2.
2. Compare object metadata against `media_upload_authorizations` and `wardrobe_items`.
3. Identify objects without valid DB references.
4. Identify published DB records whose R2 object is missing.
5. Apply safe grace period (minimum 48 hours) before deletion.
6. Fail-closed: never delete objects if DB query temporarily fails.
7. Record structured reconciliation audit logs.
8. Provide `--dry-run` CLI mode.
9. Require cryptographic ownership verification prior to deletion.

---

### Section 11: Git Status & Strict Boundaries

- **Modified Files in Repository:**
  - `backend/alembic/versions/0035_media_upload_lease.py` (New)
  - `backend/app/infrastructure/db/models.py` (Modified)
  - `backend/app/application/media.py` (Modified)
  - `backend/tests/test_media_api.py` (Modified)
  - `backend/tests/test_media_verification.py` (Modified)
  - `backend/tests/test_media_lifecycle_remediation.py` (New)
  - `STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md` (Modified)
- **Pre-existing Modifications Preserved:** All 87 modified and 61 untracked files strictly preserved.
- **Boundaries:** Zero Flutter code modified. Zero Phase 4 code implemented. Zero shared database migrations applied. Zero cloud network calls executed.

---

### Section 12: Remaining Limitations & Next Steps

1. **Phase 4 Implementation Pending:** Wardrobe item creation (`POST /v1/wardrobe/items`) currently does not associate `image_ref` into `wardrobe_items`. Phase 4 must implement this using the Gate 1 security rules.
2. **Cloudflare R2 Live Testing:** Validated using `FakeStorageAdapter` and unit tests with mocked boto3 clients; live R2 execution remains gated on live cloud credentials.
3. **Multi-Pod Cluster Concurrency:** Validated with multi-threaded independent PostgreSQL sessions on local PostgreSQL; live multi-pod Kubernetes verification remains an operational staging test.
