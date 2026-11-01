# Fansivibe — Stage 2 P0-4 Phase 3.1
# Final Lease Ownership, Duration, and Attempt-Limit Audit

- **Date:** 2026-11-01
- **Target:** Stage 2 P0-4 Phase 3.1 (`backend/app/application/media.py`, `backend/alembic/versions/0035_media_upload_lease.py`, `backend/tests/test_media_lifecycle_remediation.py`)
- **Audit Type:** Read-Only Technical Architecture & Concurrency Audit
- **Status:** **CORRECTIONS REQUIRED**

---

### Executive Summary

A comprehensive, read-only implementation audit of the Stage 2 P0-4 Phase 3.1 media lifecycle remediation was conducted. The audit focused on the durable processing lease implementation, concurrency safety, distributed worker race conditions, PostgreSQL time semantics, and attempt-limit / cooldown enforcement.

While Phase 3.1 made substantial progress by adding Migration 0035 and introducing a 15-second database lease, our code and transaction tracing revealed **critical distributed concurrency defects** that prevent safe production deployment across multiple Uvicorn workers and multi-pod clusters:

1. **Absence of Lease Ownership Tokens / Fencing:** The lease claim sets `processing_started_at` and `processing_lease_expires_at`, but generates **no unique ownership token or generation ID**. Both `_record_retryable_status` and `_record_failure` clear leases unconditionally based solely on `upload_id`. If Worker A stalls beyond 15 seconds and Worker B claims the expired lease, Worker A's `finally:` block will **clear Worker B's active lease** or overwrite status, enabling uncoordinated concurrent processing by a subsequent Worker C. Furthermore, `_finalize_published_record` allows a stale worker to commit and publish after losing lease ownership.
2. **Fixed 15-Second Lease Without Renewal or Enforced Bound:** The 15-second lease duration is easily exceeded under production load. S3/R2 read timeout is configured to 15.0 seconds with 2 retries; the child transcoder has a 5.0-second timeout but tasks wait on an `asyncio.Semaphore(1)` with **zero queue timeout**; and multiple sequential storage calls (canonical check, canonical read, staging check, staging read, canonical upload) occur inside the lease. There is **no heartbeat or lease renewal mechanism**, and **no top-level `asyncio.wait_for` timeout** enforcing an upper bound safely below 15 seconds.
3. **Attempt-Limit and Cooldown Bypass:** In `CompleteMediaUpload.execute`, the 5-attempt limit and 60-second cooldown check is nested strictly inside `if auth.status == "processing":`. Whenever a worker exits due to any retryable error (e.g. storage error, timeout, staging not found), `_record_retryable_status` transitions `status = "authorized"`. Consequently, all subsequent client retries fall into `else: auth.processing_attempts += 1`, **completely bypassing the 5-attempt ceiling and cooldown**.
4. **Terminal Failure Re-Execution:** If an upload terminally fails (`status = "failed"`), subsequent calls to `CompleteMediaUpload.execute` do not reject the request; instead, they fall through to `else: auth.processing_attempts += 1`, set `status = "processing"`, and attempt to reprocess the deleted payload, mutating `status` back to `"authorized"`.
5. **PostgreSQL `SELECT now()` Transaction Timestamp Freezing:** In PostgreSQL, `now()` evaluates to `transaction_timestamp()`, frozen at the beginning of the transaction. Because the transaction begins with `SET LOCAL lock_timeout = '3s'` followed by `SELECT pg_advisory_xact_lock(:lock_key)`, any lock wait time (up to 3 seconds) causes `db_now` to be in the past, truncating the 15-second lease to 12 seconds or less and distorting cooldown calculations.

**Audit Recommendation:** **CORRECTIONS REQUIRED**.

---

### Section 1: Lease Ownership and Stale-Worker Safety

#### 1.1 Complete Lifecycle Code Tracing

The complete claim, renewal, release, failure, and cancellation paths in [CompleteMediaUpload](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L562-L1096) were traced:

```
[Request Arrives]
       │
       ▼
1. Acquire pg_advisory_xact_lock(upload_id) [lines 607-626]
       │
2. Query db_now = SELECT now() [line 630]
       │
3. Check status == "published" -> Return 200 OK [line 651]
       │
4. Check 24h expiration (expires_at <= db_now) -> Raise 410 [line 668]
       │
5. Check Active Lease [lines 677-727]:
   - If status == "processing":
       - If processing_lease_expires_at > db_now: Raise 409 Conflict (Retry-After: 5)
       - If processing_attempts >= 5: check cooldown -> reset to 1 or Raise 409
       - Else: processing_attempts += 1
   - Else:
       - processing_attempts += 1   <-- BUG: No attempt limit check for non-processing!
       │
6. Claim Lease [lines 731-734]:
   - status = "processing"
   - processing_started_at = db_now
   - processing_lease_expires_at = db_now + 15s
   - db.commit()  <-- Advisory lock released! External I/O begins!
       │
   ┌───┴────────────────────────────────────────┐
   │ EXTERNAL I/O (NO DB LOCK HELD):             │
   │ 7. Canonical Crash Recovery Check           │
   │ 8. Staging Object Metadata Inspection       │
   │ 9. Staging Object Byte Stream Read          │
   │ 10. Checksum Assertion Verification         │
   │ 11. Magic Byte & MIME Cross-Check           │
   │ 12. Child-Process Image Transcoding         │
   │ 13. R2 Canonical Object PUT                 │
   └───┬────────────────────────────────────────┘
       │
   [Execution Branching]:
       ├── Success -> _finalize_published_record [line 996]
       ├── Terminal Error -> _record_failure [line 842, 854, 869, 887, 900, 914, 926, 938, 952, 962, 969]
       └── Transient / Cancel -> _record_retryable_status [line 826, 834, 876, 959, 988, 1011]
```

#### 1.2 Evaluation Against Safety Criteria

| Criterion | Evaluation | Concrete Evidence in Code |
| :--- | :--- | :--- |
| **Unique ownership token or generation ID?** | **NO** | [Migration 0035](file:///home/tony/projects/fansivibe_v1_backup/backend/alembic/versions/0035_media_upload_lease.py#L24-L46) adds only `processing_started_at` and `processing_lease_expires_at`. No `lease_token` (UUID) or monotonic generation number exists on the table or in [media.py:731-734](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L731-L734). |
| **Conditional release on claiming token?** | **NO** | `_record_retryable_status(upload_id)` ([lines 1085-1095](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1085-L1095)) executes `UPDATE ... WHERE upload_id = :upload_id`. It does not compare any token, timestamp, or lease expiration. |
| **Can a stale worker clear another worker's lease?** | **YES** | If Worker A takes > 15s, Worker B claims the lease. When Worker A exits, Worker A's `finally:` block executes `_record_retryable_status(upload_id)`, setting `status = 'authorized'` and `processing_lease_expires_at = None`. This wipes Worker B's active lease. |
| **Can a stale worker publish after losing ownership?** | **YES** | `_finalize_published_record` ([lines 1013-1053](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L1013-L1053)) queries `WHERE user_id == user_id AND upload_id == upload_id` without checking if the lease is still valid or owned by this worker. |
| **Are updates atomic across independent sessions?** | **PARTIAL** | The initial lease claim is serialized by `pg_advisory_xact_lock`, but post-lease operations (release, failure, completion) are separate un-fenced transactions. |

#### 1.3 Concrete Transaction Sequence of the Race Condition

```
TIME    WORKER A (Request 1)                  WORKER B (Request 2)
────    ────────────────────                  ────────────────────
t=0s    Acquires advisory lock
        Claims lease (exp = t+15s)
        Commits & releases advisory lock
        Begins slow R2 read (stalled network)
...
t=15.1s [Lease expires in DB]
t=15.2s                                       Acquires advisory lock
                                              Sees lease_exp (t+15s) <= db_now (t+15.2s)
                                              Claims lease (exp = t+30.2s)
                                              Commits & releases advisory lock
                                              Begins active transcoding
t=15.5s Worker A finishes slow R2 read,
        hits TranscoderTimeoutError or ClientDisconnect!
        Worker A enters finally:
          calls _record_retryable_status(upload_id)
          DB: UPDATE media_upload_authorizations
              SET status = 'authorized',
                  processing_lease_expires_at = NULL
              WHERE upload_id = :upload_id;
          Commits!
        *** WORKER B'S ACTIVE LEASE HAS BEEN WIPED! ***
t=15.6s                                       Worker B is still transcoding...
t=15.7s WORKER C (Request 3 arrives)
        Acquires advisory lock
        Sees status == 'authorized' (lease was cleared by A!)
        Worker C claims new lease!
        Worker C begins transcoding same upload!
        *** DUPLICATE TRANSCODING & SPLIT-BRAIN EXECUTION ***
```

---

### Section 2: Lease Duration, Renewal, and Operation Bounds

#### 2.1 Latency Compounding Breakdown

The 15-second lease duration (`PROCESSING_LEASE_SECONDS = 15`) in [media.py:540](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L540) must cover all operations between step 6 and step 14.

Inspecting [CloudflareR2StorageAdapter](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py#L75-L106):
- `connect_timeout_s`: 5.0 seconds
- `read_timeout_s`: 15.0 seconds
- `max_retries`: 2 attempts (standard mode)
- SDK: Boto3 running in `asyncio.to_thread`

Inspecting [TranscoderProcessManager](file:///home/tony/projects/fansivibe_v1_backup/backend/app/workers/transcoder.py#L41-L140):
- Subprocess timeout: 5.0 seconds (`DEFAULT_TIMEOUT_SECONDS = 5.0`)
- Concurrency limiter: `asyncio.Semaphore(1)` worker-level singleton
- **Queue Wait on Semaphore:** `async with sem:` has **no timeout**. If another upload in the same Uvicorn worker is currently transcoding, task 2 queues behind it for up to 5.0 seconds before its own 5.0-second timer even starts.

#### 2.2 Theoretical vs. Worst-Case Latency Table

| Phase | Operation | Typical Latency | P99 / Degraded Latency | Enforced Sub-Timeout |
| :--- | :--- | :--- | :--- | :--- |
| **Crash Recovery Check** | `get_object_metadata(canonical_key)` | 25ms | 3,000ms | 15s (Boto3 read_timeout) |
| **Staging Metadata** | `get_object_metadata(staging_key)` | 25ms | 3,000ms | 15s (Boto3 read_timeout) |
| **Staging Body Read** | `read_object(staging_key)` (up to 2MB) | 40ms | 5,000ms | 15s (Boto3 read_timeout) |
| **Transcoder Queue** | `async with sem:` (queue wait) | 0ms | 5,000ms | **None (unbounded)** |
| **Transcoder Exec** | Child subprocess CLI transcoding | 250ms | 4,900ms | 5.0s (`wait_for`) |
| **Canonical PUT** | `put_object(canonical_key)` | 60ms | 5,000ms | 15s (Boto3 read_timeout) |
| **Database Commit** | `_finalize_published_record` commit | 5ms | 2,000ms | None |
| **Total Pipeline** | **End-to-End Execution** | **~405ms** | **~27,900ms** | **None** |

#### 2.3 Findings on Lease Duration and Bounds

1. **Lease Expiration During Legitimate Work:** The 15-second lease can expire while a legitimate worker is still actively and correctly processing the upload.
2. **Absence of Renewal / Heartbeat:** There is **no heartbeat task, background renewal coroutine, or explicit lease extension mechanism**. Once claimed at step 6, the lease expiration timestamp is never touched until completion or failure.
3. **Absence of Top-Level Timeout:** There is **no `asyncio.wait_for`** bounding the overall `CompleteMediaUpload.execute` pipeline. While the child transcoder has a 5.0s timeout, the external I/O and semaphore queue wait can accumulate to well over 15 seconds without triggering any internal error.

---

### Section 3: PostgreSQL Server Time Semantics

#### 3.1 `SELECT now()` vs. `SELECT clock_timestamp()`

In [CompleteMediaUpload.execute](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L628-L634):
```python
if is_postgres:
    try:
        db_now = self._db.execute(text("SELECT now()")).scalar()
    except Exception:
        db_now = datetime.now(timezone.utc)
```

In PostgreSQL:
- `now()` / `CURRENT_TIMESTAMP` / `transaction_timestamp()` returns the start time of the **current transaction**. It remains constant and does not advance regardless of how long the transaction runs or how long it waits for locks.
- `clock_timestamp()` returns the actual wall-clock time at the moment the SQL function is executed.

#### 3.2 Impact in Short vs. Long Transactions

1. **Short Transactions with Lock Contention:**
   - At line 609, `self._db.execute(text("SET LOCAL lock_timeout = '3s'"))` opens a transaction.
   - At line 611, `SELECT pg_advisory_xact_lock(:lock_key)` executes.
   - If a concurrent request is completing an operation, this query blocks for up to 2.9 seconds.
   - When the lock is acquired, line 630 runs `SELECT now()`.
   - **PostgreSQL returns the timestamp when `SET LOCAL` was called (2.9 seconds ago)**.
   - The newly claimed lease is calculated as `db_now + timedelta(seconds=15)`, which is actually **only 12.1 seconds in the future**.
   - The effective lease duration is silently shortened by the exact duration of the advisory lock wait.
2. **Reused Sessions / Long Transactions:**
   - If SQLAlchemy's session was opened earlier (e.g. during authentication token verification or earlier service calls within the same unit of work), `SELECT now()` can be tens of seconds old.
   - A lease computed as `db_now + 15s` could be **already expired the instant it is committed**!

#### 3.3 Recommended SQL Expression
All lease evaluations and assignments in PostgreSQL must use server-side `clock_timestamp()` directly:
```sql
UPDATE media_upload_authorizations
SET status = 'processing',
    processing_started_at = clock_timestamp(),
    processing_lease_expires_at = clock_timestamp() + INTERVAL '15 seconds',
    processing_attempts = processing_attempts + 1
WHERE user_id = :user_id AND upload_id = :upload_id
RETURNING processing_lease_expires_at;
```

---

### Section 4: Attempt-Limit and Cooldown Behavior

#### 4.1 State Transition Tracing of `processing_attempts`

In [CompleteMediaUpload.execute](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L677-L734):
```python
# 5. Check if another concurrent request is actively processing under valid lease
if auth.status == "processing":
    lease_active = ...
    if lease_active:
        raise ApiError(409, "CONFLICT", headers={"Retry-After": "5"})

    # Lease has expired (worker crashed or timed out)
    if auth.processing_attempts >= MAX_PROCESSING_ATTEMPTS: # 5
        started_at = auth.processing_started_at
        ...
        if elapsed_s >= PROCESSING_RECOVERY_COOLDOWN_SECONDS: # 60.0s
            auth.processing_attempts = 1
        else:
            raise ApiError(409, "PROCESSING_LIMIT_EXCEEDED", headers={"Retry-After": "60"})
    else:
        auth.processing_attempts += 1
else:
    auth.processing_attempts += 1 # <-- CRITICAL FLAW
```

#### 4.2 Flaws Identified in Attempt-Limit Lifecycle

1. **Attempt Limit Completely Bypassed on Clean Failures:**
   - When an attempt fails with a retryable error (e.g. storage error, timeout, or task cancellation), line 1091 in `_record_retryable_status` sets:
     `rec.status = "authorized"`
   - On the next client attempt, `auth.status` is `"authorized"`, NOT `"processing"`.
   - The entire `if auth.status == "processing":` block is skipped!
   - Execution jumps straight to `else: auth.processing_attempts += 1` at line 726.
   - The attempt limit is **never checked**. A client retrying after transient errors can make 10, 50, or 100 attempts without ever receiving `PROCESSING_LIMIT_EXCEEDED`.
2. **Terminal Failure (`status == "failed"`) Not Enforced:**
   - If an upload fails terminally (e.g. `EMPTY_OBJECT`, `DECOMPRESSION_BOMB`, `CHECKSUM_MISMATCH`), line 1078 sets `rec.status = "failed"`.
   - If the client calls `/complete` again, `CompleteMediaUpload.execute` does **not** check `if auth.status == "failed": raise ApiError(409, "UPLOAD_FAILED")`.
   - Because `auth.status` is not `"published"` and not `"processing"`, it falls into `else: auth.processing_attempts += 1`, resets `auth.status = "processing"`, and attempts to re-transcode the deleted staging file!
   - When staging metadata returns `None`, line 834 calls `self._record_retryable_status(upload_id)`, which resets `status = "authorized"`.
   - **A terminal failure is resurrectable and mutates back into an authorized state.**
3. **Crashed Process Attempt Consumption:**
   - If a process crashes hard (SIGKILL / OOM), it leaves `status = "processing"`.
   - A subsequent request arriving after lease expiry **does** see `status == "processing"` and consumes an attempt (`auth.processing_attempts += 1`).
   - If 5 crashes occur consecutively, the 6th attempt is blocked until 60 seconds have elapsed since `processing_started_at` of attempt 5.
   - However, because clean errors reset status to `"authorized"`, this protection functions **only** for hard unhandled SIGKILL crashes, not for standard runtime errors.

---

### Section 5: Test Coverage Gap Analysis

Evaluation of existing test suites against required concurrency scenarios:

| Scenario | Tested in Existing Suite? | Existing Test Reference | Coverage Status & Deficiencies |
| :--- | :--- | :--- | :--- |
| **Worker A's lease expires and Worker B claims it** | **Partial** | `test_lease_expiry_permits_worker_recovery` ([line 711](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation.py#L711)) | Tests Worker B claiming an expired lease from a dead worker. Does NOT test Worker A still being alive. |
| **Worker A resumes and attempts to clear Worker B's lease** | **NO** | None | **Zero coverage.** If Worker A resumes and calls `_record_retryable_status`, it wipes Worker B's lease in production. |
| **Worker A resumes and attempts to publish after losing ownership** | **NO** | None | **Zero coverage.** `_finalize_published_record` has no fencing check; a stale worker will commit successfully. |
| **Operation exceeds 15 seconds** | **NO** | None | **Zero coverage.** All tests complete in < 150ms. No artificial delay or slow storage simulation exists. |
| **Lease renewal fails because ownership changed** | **NO** | None | **Zero coverage.** No renewal mechanism exists in the codebase. |
| **Long PostgreSQL transactions and server-time semantics** | **NO** | None | **Zero coverage.** Tests execute `SELECT now()` in isolated instant queries. Lock wait clock skew is untested. |
| **Canonical object hash mismatch** | **YES** | `test_crash_recovery_rejects_corrupted_canonical_bytes_and_falls_back` ([line 412](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation.py#L412)) | Tested with corrupt bytes. |
| **Canonical exists but staging missing/inconsistent** | **NO** | None | **Zero coverage.** Existing tests always populate valid staging bytes before running crash recovery. |
| **Repeated worker crashes and cooldown recovery** | **Partial** | `test_five_attempt_limit_and_cooldown_recovery` ([line 871](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation.py#L871)) | Tested by manually executing raw SQL `UPDATE` on timestamps. Does not test actual execution cycles or clean retries. |

---

### Section 6: Findings Matrix

| Finding ID | Severity | Affected Code Path | Concrete Evidence | Production Impact | Recommended Correction |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **L-01** | **CRITICAL** | `backend/app/application/media.py:731-734`, `1013-1053`, `1072-1095` | `_record_retryable_status`, `_record_failure`, and `_finalize_published_record` match solely on `upload_id` with zero lease token / fencing check. | A stalled worker that wakes up clears the active lease of a newer worker, or commits published data after losing ownership. | Add `lease_token` (UUID) to `media_upload_authorizations`. Require `WHERE upload_id = :id AND lease_token = :token` on all state transitions. |
| **L-02** | **HIGH** | `backend/app/application/media.py:540`, `731-734` | Fixed 15s lease duration with no heartbeat/renewal, while storage read timeout is 15s and transcoder queue wait is unbounded. | Legitimate transcoding operations on valid 2MB images under load exceed 15s, triggering false lease expirations and worker collisions. | Add an enforced `asyncio.wait_for` of 12.0s on the entire completion operation, or implement an active lease renewal heartbeat. |
| **L-03** | **HIGH** | `backend/app/application/media.py:677-727`, `1085-1095` | `processing_attempts >= 5` check is only inside `if auth.status == "processing":`. `_record_retryable_status` sets `status = "authorized"`. | Retrying after any transient failure bypasses the 5-attempt ceiling completely, enabling infinite retries and resource exhaustion. | Move the `processing_attempts >= MAX_PROCESSING_ATTEMPTS` check outside the status conditional to govern all non-published requests. |
| **L-04** | **HIGH** | `backend/app/application/media.py:650-675`, `1072-1083` | Missing `if auth.status == "failed": raise ApiError(409, "UPLOAD_FAILED")` check in `CompleteMediaUpload.execute`. | Terminally failed uploads (e.g. decompression bombs, corrupt files) can be replayed by clients and mutated back to `authorized`. | Add explicit validation rejecting completion if `auth.status == "failed"`, returning HTTP 409 `UPLOAD_FAILED`. |
| **L-05** | **MEDIUM** | `backend/app/application/media.py:628-636` | `SELECT now()` binds to transaction start time; advisory lock wait up to 3s makes `db_now` stale. | Calculated lease expiry is shortened by up to 3 seconds, leading to premature expiry at 12s instead of 15s. | Use `SELECT clock_timestamp()` to obtain true PostgreSQL server wall-clock time. |
| **L-06** | **MEDIUM** | `backend/tests/test_media_lifecycle_remediation.py` | Zero tests for concurrent stale workers, operation timeouts, or attempt limits on retryable errors. | Critical concurrency regressions can pass automated test suites undetected. | Add tests explicitly exercising stale worker lease clearance and operation timeout safety. |

---

### Section 7: Audit Recommendation

**CORRECTIONS REQUIRED**

Phase 3.1 cannot be accepted in its current form. While the migration and basic serialization function correctly in sequential and short concurrent scenarios, the absence of **lease ownership tokens (fencing)**, the **unconditional lease wiping by stale workers**, the **unbounded operation duration relative to the 15-second lease**, and the **bypass of the attempt limit on clean retries** are critical reliability and data integrity defects for a multi-worker production service.

Implementation of the recommended corrections (L-01 through L-05) is required before Phase 3.1 can be signed off.
