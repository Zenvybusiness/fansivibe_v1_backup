# Fansivibe — Stage 2 P0-4 Phase 3.4
# Cloudflare R2 Publication Fencing & Stale-Worker Safety Implementation Report

- **Date:** 2026-11-01
- **Status:** **COMPLETE & VERIFIED**
- **Target Components:**
  - Application Service: [CompleteMediaUpload](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py)
  - Key Derivation: [get_attempt_object_key](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py), [get_canonical_object_key](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py)
  - Storage Infrastructure: [CloudflareR2StorageAdapter](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py)
  - Database Ledger: [MediaUploadAuthorization](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/db/models.py)
  - Adversarial Test Suite: [test_media_publication_fencing_p34.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_publication_fencing_p34.py)
- **Predecessor Audits:**
  - [STAGE2_P0_4_PHASE3_3_R2_PUBLICATION_FENCING_AUDIT.md](file:///home/tony/projects/fansivibe_v1_backup/STAGE2_P0_4_PHASE3_3_R2_PUBLICATION_FENCING_AUDIT.md)
  - [STAGE2_P0_4_PHASE3_3_R2_PUBLICATION_RISK_MATRIX.md](file:///home/tony/projects/fansivibe_v1_backup/STAGE2_P0_4_PHASE3_3_R2_PUBLICATION_RISK_MATRIX.md)

---

### Executive Summary

In the Phase 3.3 audit, a critical boundary mismatch was identified between PostgreSQL durable lease fencing and external Cloudflare R2 object storage side effects:
1. **Deterministic Shared Key (F-01):** The canonical R2 key was derived as `users/{user_id}/wardrobe/{upload_id}/canonical.webp` across all attempts, causing unconditional Last-Write-Wins (LWW) S3 PUT overwrites by delayed or stale workers.
2. **`asyncio.to_thread` Network Leak (F-02):** S3 network I/O executed inside Python OS threads cannot be cancelled when an `asyncio.wait_for` timeout expires; in-flight writes continue in the background and overwrite canonical objects.
3. **Unfenced Remote Sockets (F-03):** PostgreSQL fencing tokens did not protect remote HTTP sockets once an S3 PUT was in flight.
4. **Unfenced Staging Deletion (F-04):** In 10 image validation failure blocks, `_record_failure` was called but its return value was ignored, causing defunct workers to unconditionally delete shared staging objects while active retry workers were downloading them.

Phase 3.4 resolves all four vulnerabilities by establishing **immutable attempt-specific object keys**, **conditional PostgreSQL linearizing finalization**, **pre-PUT fencing gates**, and **strictly fenced staging deletion**.

---

### Workstream 1 — Immutable Attempt-Specific Object Keys

#### 1.1 Attempt Key Specification
All new media publications write strictly to an immutable attempt-specific object key parameterized by the unique UUIDv4 lease token:

```
users/{user_id}/wardrobe/{upload_id}/attempts/{lease_token}.webp
```

Implemented in `backend/app/application/media.py`:
```python
def get_attempt_object_key(user_id: UUID, upload_id: UUID, lease_token: UUID) -> str:
    """Derive immutable attempt-specific WebP storage key from user ID, upload ID, and lease token (Stage 2 P0-4 Phase 3.4).

    Format: users/{user_id}/wardrobe/{upload_id}/attempts/{lease_token}.webp

    Guarantees:
    - Derived strictly from authenticated owner, upload ID, and lease token.
    - Never derived from arbitrary client input.
    - Path components validated and normalized as UUID strings (preventing traversal).
    - Immutable across processing attempts: different attempts write to distinct non-overlapping keys.
    """
    u_str = str(UUID(str(user_id)))
    up_str = str(UUID(str(upload_id)))
    tok_str = str(UUID(str(lease_token)))
    return f"users/{u_str}/wardrobe/{up_str}/attempts/{tok_str}.webp"
```

#### 1.2 Backwards Compatibility & Legacy Preservation
To preserve zero disruption for previously published records and historical references:
- `get_canonical_object_key(user_id, upload_id, lease_token=None)` preserves legacy behavior when `lease_token is None`, returning `users/{user_id}/wardrobe/{upload_id}/canonical.webp`. When `lease_token` is provided, it delegates directly to `get_attempt_object_key`.
- Previously published records stored in PostgreSQL with `canonical_key = .../canonical.webp` are never migrated or rewritten. Idempotent replay returns the exact stored key.

---

### Workstream 2 — Conditional PostgreSQL Finalization

The database transaction in `_finalize_published_record` is the single authoritative linearization point in the distributed system.

#### 2.1 Atomic Conditional Update
```python
stmt = (
    update(MediaUploadAuthorization)
    .where(
        MediaUploadAuthorization.user_id == user_id,
        MediaUploadAuthorization.upload_id == upload_id,
        MediaUploadAuthorization.processing_lease_token == lease_token,
        MediaUploadAuthorization.status == "processing",
    )
    .values(
        status="published",
        canonical_key=canonical_key,  # Persists the exact attempt key
        canonical_sha256=canonical_sha256,
        canonical_size_bytes=size_bytes,
        canonical_width=width,
        canonical_height=height,
        completed_at=completed_at,
        processing_lease_expires_at=None,
        processing_lease_token=None,
    )
)
res = self._db.execute(stmt)
if (res.rowcount or 0) == 0:
    self._db.rollback()
    logger.warning("Upload %s finalization aborted: lease token %s lost ownership", upload_id, lease_token)
    raise ApiError(status_code=409, code="LEASE_LOST", message="Processing lease ownership was lost before publication could be finalized.")
self._db.commit()
```

#### 2.2 Guarantees
1. If Worker A's lease expires and Worker B commits publication with `lease_token_B`, Worker A's subsequent `_finalize_published_record` matches zero rows.
2. Worker A's transaction immediately rolls back and raises 409 `LEASE_LOST`.
3. Worker A's write to `attempts/{token_A}.webp` remains completely isolated and does not touch Worker B's `attempts/{token_B}.webp` or the PostgreSQL reference.

---

### Workstream 3 — External Write and Cancellation Safety

#### 3.1 Pre-PUT Fencing Gate
Before initiating the external S3 upload to Cloudflare R2, the worker executes a synchronous pre-flight lease renewal check:
```python
# Step 13: Publish immutable attempt WebP object to private storage
still_holding_lease = self.renew_lease(upload_id, lease_token, extend_seconds=self._lease_seconds)
if not still_holding_lease:
    logger.warning("Upload %s: pre-PUT fencing check failed; lease ownership lost for token %s. Aborting before storage write.", upload_id, lease_token)
    raise ApiError(status_code=409, code="LEASE_LOST", message="Processing lease ownership was lost before storage write could begin.")
```
If transcoding or inspection took long enough that the worker lost lease ownership, the pipeline aborts immediately without sending a single byte over the wire to Cloudflare R2.

#### 3.2 Thread-Pool Continuation Safety
If a coroutine awaiting `_storage.put_object` times out at `pipeline_timeout_seconds=25.0s`:
- The coroutine unwinds, executes `_record_retryable_status`, and returns HTTP 504.
- The underlying OS thread executing Boto3 socket I/O continues to completion in Python's `ThreadPoolExecutor`.
- **Safety Guarantee:** Because the thread writes strictly to its attempt-specific key `.../attempts/{token_A}.webp`, it can never overwrite another worker's object at `.../attempts/{token_B}.webp`.

#### 3.3 Boto3 Socket Timeout Hardening
In `backend/app/infrastructure/external/storage.py`, `CloudflareR2StorageAdapter` defaults were tightened from 5.0s connect / 15.0s read to:
- `connect_timeout_s = 3.0`
- `read_timeout_s = 10.0`
Ensuring background worker threads fail and terminate quickly if network stalls occur.

---

### Workstream 4 — Staging Object Deletion Safety

Every failure and deletion branch in the media completion pipeline was audited and fenced.

#### 4.1 Fenced Staging Deletion Across All Failure Paths
In all 10 image validation and decoding failure blocks in `_execute_pipeline`:
1. `staging_meta.size_bytes <= 0` (`EMPTY_OBJECT`)
2. `staging_meta.size_bytes > 2 * 1024 * 1024` (`OBJECT_TOO_LARGE`)
3. `StoragePayloadError` during stream read (`OBJECT_TOO_LARGE`)
4. Client checksum assertion mismatch (`CHECKSUM_MISMATCH`)
5. Payload under 12 bytes (`INVALID_FILE_SIGNATURE`)
6. Magic bytes match neither JPEG nor WebP (`INVALID_FILE_SIGNATURE`)
7. Authorized WebP payload signature mismatch (`CONTENT_TYPE_MISMATCH`)
8. Authorized JPEG payload signature mismatch (`CONTENT_TYPE_MISMATCH`)
9. Transcoder validation error (`ImageValidationError`)
10. Decompression bomb ceiling exceeded (`MemoryLimitExceededError`)

The code now checks the return value of `_record_failure`:
```python
still_owner = self._record_failure(upload_id, lease_token, "REASON")
if still_owner:
    try:
        await self._storage.delete_object(staging_key)
    except Exception:
        pass
```
If a worker lost its lease (`res.rowcount == 0`), `still_owner` is `False`, and the worker **never touches the staging object**.

#### 4.2 Publication Finalization Staging Deletion
In `_finalize_published_record`:
- Staging deletion is executed **only after** PostgreSQL conditional update succeeds and commits (`res.rowcount > 0` and `db.commit()`).
- If staging deletion fails due to storage timeout or network glitch, the exception is caught and logged. The published database record is preserved, returning HTTP 200 with the published media reference. The existing staging bucket lifecycle policy cleans up any residual staging bytes.

#### 4.3 Crash-After-Commit Replay Cleanup
If a crash occurs after PostgreSQL commits `status = 'published'` but before staging deletion completes, subsequent client replay enters Step 3 (`if auth.status == "published"`):
- Step 3 attempts `await self._storage.delete_object(auth.staging_key)` (safely non-blocking).
- Returns the published reference immediately.

---

### Workstream 5 — Crash Recovery and Backwards Compatibility

#### 5.1 Multi-Candidate Inspection
In Step 7 of `_execute_pipeline`, crash recovery builds an ordered list of candidate keys to inspect:
1. `existing_canonical_key`: already persisted in DB row.
2. `previous_attempt_key`: `users/{user_id}/wardrobe/{upload_id}/attempts/{previous_lease_token}.webp` (from the predecessor attempt that crashed before DB commit).
3. `legacy_canonical_key`: `users/{user_id}/wardrobe/{upload_id}/canonical.webp` (for pre-Phase-3.4 legacy records).
4. `cur_attempt_key`: `users/{user_id}/wardrobe/{upload_id}/attempts/{lease_token}.webp` (for in-process retry).

#### 5.2 Strict Fail-Closed Verification
For any candidate found in storage:
- **Path Verification:** Scoped under `users/{user_id}/wardrobe/{upload_id}/` and ending with `.webp`.
- **Metadata Ownership:** `user_id` and `upload_id` match authenticated caller; if an attempt key, `lease_token` in metadata matches key token.
- **Trusted SHA Evidence:** Requires trusted server-side SHA evidence (`canonical_sha256` or custom metadata `sha256`).
- **Binary Integrity:** Reads byte stream, calculates independent SHA-256, verifies `RIFF....WEBP` magic bytes.
- **Image Decoding:** Decodes with PIL `Image.open(io.BytesIO(canonical_bytes))`, verifies format is `WEBP` and dimensions > 0 (never fabricating fake dimensions).
- **Staging Consistency:** If staging object is present, verifies that candidate `source_sha256` matches staging SHA-256 and client assertion.
- **Adoption:** If and only if all checks pass, adopts the candidate key and finalizes publication under the winning worker's lease token.
- **Fallback:** If any check fails, falls back cleanly to isolated transcoding and writes a fresh attempt object.

---

### Workstream 6 — Orphan Safety & Phase 13 Reconciliation Contract

Although Phase 13 orphan reconciliation is out of scope for implementation in this phase, the Phase 3.4 architecture establishes all data and contracts required for safe automated reconciliation:

#### 6.1 Attempt Object Custom Metadata
Every attempt object uploaded to Cloudflare R2 includes structured metadata:
- `user_id`: Authenticated user UUID string.
- `upload_id`: Media upload authorization UUID string.
- `lease_token`: Worker attempt lease token UUID string.
- `sha256`: Transcoded WebP SHA-256 digest.
- `width`: Canonical image pixel width.
- `height`: Canonical image pixel height.
- `source_sha256`: Pre-transcoded staging SHA-256 digest.

#### 6.2 Reconciliation Rules for Phase 13 Cleaner
1. **Query Authority:** Query PostgreSQL for the authoritative publication reference:
   `SELECT canonical_key FROM media_upload_authorizations WHERE upload_id = :upload_id AND status = 'published'`
2. **Winning Object Invariant:** An object whose key equals `auth.canonical_key` is the **winning attempt** and must **NEVER** be deleted.
3. **Orphan Identification:** Any object under `users/{user_id}/wardrobe/{upload_id}/attempts/` whose key does NOT match `auth.canonical_key` is an abandoned attempt object.
4. **Grace Period:** An orphan attempt object may only be deleted if its storage `LastModified` timestamp is older than the lease expiry cooldown grace period (>= 2 hours).
5. **Fail-Closed:** If the database query fails or returns zero rows for an unconfirmed upload, the reconciliation worker must fail closed and skip deletion.
6. **Dry-Run Mode:** The cleaner must support dry-run auditing before issuing destructive S3 `DeleteObjects` calls.

---

### Workstream 7 — Adversarial & Concurrency Test Verification

A dedicated adversarial test suite was authored in [backend/tests/test_media_publication_fencing_p34.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_publication_fencing_p34.py), providing 100% passing coverage for all 15 scenarios:

| Test ID | Test Method | Scenario Description | Result |
| :--- | :--- | :--- | :--- |
| **P34-01** | `test_attempt_key_derivation_format_and_security` | Key format matches `users/.../attempts/{token}.webp`; path traversal rejected. | **PASSED** |
| **P34-02** | `test_legacy_canonical_key_compatibility` | Legacy key helper returns `canonical.webp` when token is None; attempt key when provided. | **PASSED** |
| **P34-03** | `test_worker_a_and_b_cross_attempt_isolation_sequence` | Worker A delayed write lands on attempt key A after Worker B publishes key B; Worker B bytes and DB reference intact. | **PASSED** |
| **P34-04** | `test_worker_a_attempts_finalization_after_losing_ownership` | Worker A calling `_finalize_published_record` with stale token raises 409 `LEASE_LOST`. | **PASSED** |
| **P34-05** | `test_worker_a_validation_failure_preserves_staging_after_losing_ownership` | Stale Worker A encountering validation failure does NOT delete staging data because `_record_failure` returns `False`. | **PASSED** |
| **P34-06** | `test_worker_b_successfully_finalizes_and_deletes_staging` | Winning Worker B publishes attempt key and deletes staging data. | **PASSED** |
| **P34-07** | `test_staging_deletion_failure_preserves_published_record` | Storage deletion failure during cleanup preserves published DB record and returns 200 OK. | **PASSED** |
| **P34-08** | `test_crash_after_attempt_put_before_database_commit` | Worker A crashes after PUT; Worker B crash recovery verifies and adopts attempt key A. | **PASSED** |
| **P34-09** | `test_crash_after_database_commit_before_staging_deletion` | Worker crashes after DB commit; client retry cleans up staging and returns 200 OK. | **PASSED** |
| **P34-10** | `test_recovery_of_existing_published_legacy_canonical_key` | Legacy record with `canonical.webp` replayed cleanly without key migration. | **PASSED** |
| **P34-11** | `test_two_concurrent_attempts_with_different_fencing_tokens` | Concurrent request during active lease is rejected with 409 Conflict (`Retry-After: 5`). | **PASSED** |
| **P34-12** | `test_abandoned_attempt_object_not_treated_as_published` | Uncommitted attempt object in R2 is not treated as published without DB commit. | **PASSED** |
| **P34-13** | `test_orphan_cleanup_never_deletes_winning_attempt_key` | Cleaner deletes non-winning attempt keys while preserving the winning canonical key. | **PASSED** |
| **P34-14** | `test_threaded_delayed_put_completes_after_coroutine_cancellation` | **Physical OS Thread Simulation:** Worker A blocking OS thread continues after coroutine cancellation; Worker B publishes key B; Worker A late write lands on key A without corrupting key B. | **PASSED** |
| **P34-15** | `test_pre_put_fencing_gate_aborts_when_lease_expired_before_put` | Lease ownership lost during transcoding causes pre-PUT check to fail with 409 `LEASE_LOST` before storage write. | **PASSED** |

---

### Workstream 8 — Regression & Hardening Verification

#### 8.1 Test Suites Executed
1. **Adversarial Publication Fencing Suite (`test_media_publication_fencing_p34.py`):**
   15 / 15 passed (100%).
2. **Storage Adapter & Fake Suite (`test_storage_adapter.py`, `test_fake_storage.py`):**
   38 / 38 passed (100%).
3. **Media Lifecycle Remediation Suites (`test_media_lifecycle_remediation_p32.py`, `test_media_lifecycle_remediation.py`):**
   31 passed, 9 skipped (PostgreSQL-gated), 0 failed.
4. **Media Verification Suite (`test_media_verification.py`):**
   27 passed, 1 skipped, 0 failed.
5. **Media Authorization & Concurrency API Suite (`test_media_api.py`):**
   56 passed, 2 skipped, 0 failed.
6. **Production Hardening, Settings, and Storage DI Suites (`test_production_hardening.py`, `test_storage_config.py`, `test_storage_di.py`):**
   57 passed, 0 failed.

**Total Media & Storage Regression Pass Count:**
- **224 passed**, 12 skipped (PostgreSQL concurrency tests requiring live DB URL), 0 failed.

#### 8.2 Code Quality & Static Checks
- `git diff --check`: 100% clean (zero whitespace or CRLF errors).
- `python -m py_compile app/application/media.py app/infrastructure/external/storage.py`: 100% clean.
- Shared databases `fansivibe` and `fansivibe_test` verified untouched at revision 0032.
- Alembic migration chain single linear head strictly maintained at revision 0036.

---

### Acceptance Criteria Verification

| Criterion | Requirement | Verification Evidence | Status |
| :--- | :--- | :--- | :--- |
| **Immutable Attempt Keys** | Format: `.../attempts/{lease_token}.webp` | Tested in `test_attempt_key_derivation_format_and_security` | **PASS** |
| **Cross-Attempt Isolation** | Stale worker write cannot overwrite winning attempt | Tested in `test_worker_a_and_b_cross_attempt_isolation_sequence` | **PASS** |
| **Winning Attempt Selection** | Only current lease owner can finalize publication | Tested in `test_worker_a_attempts_finalization_after_losing_ownership` | **PASS** |
| **Fenced Staging Deletion** | Stale workers cannot delete shared staging data | Tested in `test_worker_a_validation_failure_preserves_staging_after_losing_ownership` | **PASS** |
| **Legacy Compatibility** | Existing `canonical.webp` records remain valid without rewrites | Tested in `test_recovery_of_existing_published_legacy_canonical_key` | **PASS** |
| **Thread-Pool Safety** | External writes completing after cancellation are isolated | Tested in `test_threaded_delayed_put_completes_after_coroutine_cancellation` | **PASS** |
| **Boundary Discipline** | Shared DB untouched; zero Flutter or Phase 4 code | Verified via `git status` and test assertions | **PASS** |
