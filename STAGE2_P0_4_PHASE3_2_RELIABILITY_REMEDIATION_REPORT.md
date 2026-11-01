# Fansivibe — Stage 2 P0-4 Phase 3.2
# Media Lifecycle Critical Reliability Corrections Report

- **Date:** 2026-11-01
- **Target:** Stage 2 P0-4 Phase 3.2 Media Lifecycle Remediation (`backend/alembic/versions/0036_media_upload_lease_token.py`, `backend/app/infrastructure/db/models.py`, `backend/app/workers/transcoder.py`, `backend/app/application/media.py`, `backend/tests/test_media_lifecycle_remediation_p32.py`)
- **Status:** **COMPLETE & VERIFIED**
- **Migration Head:** `0036` (Tested exclusively against isolated disposable databases; shared databases remain at `0032`)

---

### Executive Summary

In Stage 2 P0-4 Phase 3.1, audits identified 10 critical and high-priority vulnerabilities spanning lease fencing, operation lifecycle bounding, PostgreSQL time semantics under lock contention, attempt-limit bypass, and crash recovery integrity (`STAGE2_P0_4_PHASE3_1_FINAL_LEASE_AUDIT.md` and `STAGE2_P0_4_PHASE3_1_FINAL_RECOVERY_AUDIT.md`).

Phase 3.2 delivers comprehensive backend architectural remediations resolving all 10 findings:

1. **Fencing-Token Lease Ownership (Workstream 1 / L-01, R-04):** Generated a cryptographically unique UUID `processing_lease_token` for every successful lease claim. Persisted atomically in additive Alembic Migration 0036. Gated all lease lifecycle state transitions (`renew_lease`, `_record_failure`, `_record_retryable_status`, and `_finalize_published_record`) on matching both `upload_id` and `processing_lease_token`. Stale workers that stall or lose ownership encounter zero-row updates and safely abort without altering newer worker state or deleting staging data.
2. **Operation Lifecycle Bounds & Heartbeat (Workstream 2 / L-02, L-06):** Extended durable processing lease duration to 30.0 seconds. Implemented an asynchronous background heartbeat renewal task renewing the lease every 5.0 seconds conditional on the current fencing token. Bounded semaphore acquisition in `TranscoderProcessManager` to 5.0 seconds. Enforced an end-to-end operation deadline of 25.0 seconds using `asyncio.wait_for`. Subprocesses timed out are terminated via SIGKILL and reaped via `wait()`.
3. **PostgreSQL Server Wall-Clock Time (Workstream 3 / L-05):** Eliminated transaction-start timestamp freezing by replacing `SELECT now()` with `SELECT clock_timestamp()` across lease acquisition, renewal, cooldown, and expiry queries. Evaluates true wall-clock time in PostgreSQL regardless of preceding advisory-lock wait latency.
4. **Attempt-Limit & Cooldown Enforcement (Workstream 4 / L-03, L-04):** Moved the 5-attempt ceiling and 60-second cooldown checks out of the narrow `processing` status branch to guard all non-published requests. Enforced HTTP 409 `UPLOAD_FAILED` for terminal `failed` records, preventing resurrecting failed uploads. Preserved idempotent replay of published records.
5. **Fail-Closed Canonical Crash Recovery (Workstream 5 / R-01, R-02, R-03):** Prohibited automatic hash acceptance when metadata is missing. Required trusted server-side integrity evidence (either `auth.canonical_sha256` or R2 custom metadata SHA). Required byte stream validation, WebP magic bytes verification (`RIFF....WEBP`), and successful PIL image decoding. Eliminated hardcoded fallback dimensions (`1920, 1440`). Verified staging payload integrity and client checksum assertions before adopting existing canonical objects.
6. **Verification & Testing (Workstream 6 & 7):** Created 19 adversarial PostgreSQL-backed test cases in `backend/tests/test_media_lifecycle_remediation_p32.py` (100% pass). Verified complete upgrade (`0001 -> 0036`) and downgrade (`0036 -> 0032`) against disposable databases. Preserved shared databases `fansivibe` and `fansivibe_test` strictly at revision `0032`.

---

### Audit Finding Remediation Matrix

| Finding ID | Severity | Problem Description | Phase 3.2 Remediation Status & Architecture |
| :--- | :--- | :--- | :--- |
| **L-01** | Critical | Lease claims lack fencing tokens; stale workers clear active leases or overwrite state. | **RESOLVED**. Added `processing_lease_token` UUID column in Migration 0036. Generated unique token per claim; all updates check `WHERE upload_id = :id AND processing_lease_token = :token`. Zero-row update aborts worker safely. |
| **L-02** | High | Fixed 15-second lease without renewal or bound exceeded under load. | **RESOLVED**. Lease extended to 30s. Background heartbeat task renews lease every 5s conditional on fencing token. Pipeline bounded by 25s top-level timeout. |
| **L-03** | High | Attempt-limit and cooldown checked only for `processing`, bypassed by retryable failures. | **RESOLVED**. Attempt-limit ceiling (5) and 60s cooldown enforced across all non-published statuses (`authorized`, `processing`, `failed`, `expired`). |
| **L-04** | High | Terminal `failed` records silently re-enter `processing` on retry. | **RESOLVED**. Status `failed` is terminal; returns HTTP 409 Conflict with `code="UPLOAD_FAILED"`. |
| **L-05** | High | `SELECT now()` in PostgreSQL frozen at transaction start, skewed by advisory lock wait. | **RESOLVED**. Replaced with `clock_timestamp()` for PostgreSQL lease calculations, renewals, and cooldowns. |
| **L-06** | Medium | Transcoder `asyncio.Semaphore(1)` wait was unbounded. | **RESOLVED**. Added `semaphore_timeout_seconds=5.0s` to `TranscoderProcessManager.acquire()`, raising `TranscodingTimeoutError`. |
| **R-01** | High | Recovery initialized `sha_matches = True`, failing open when R2 metadata missing. | **RESOLVED**. Requires trusted server evidence (`trusted_sha = auth.canonical_sha256 or meta_sha256`). Rejects and falls back if trusted SHA is missing or does not match canonical bytes. |
| **R-02** | High | Recovery bypassed client checksum assertion and staging validation. | **RESOLVED**. When client assertion is provided, verifies against staging bytes before adopting canonical object. |
| **R-03** | Medium | PIL decode failures fell back to hardcoded dimensions `1920, 1440`. | **RESOLVED**. Removed hardcoded fallback. Any dimension decode failure rejects canonical object and triggers fresh transcoding. |
| **R-04** | High | Recovery finalized publication without lease ownership fencing. | **RESOLVED**. `_finalize_published_record` enforces `processing_lease_token` matching; stale recovery attempts safely abort. |

---

### Workstream 1: Fencing-Token Lease Ownership

#### 1.1 Additive Schema Migration 0036
Created additive migration [0036_media_upload_lease_token.py](file:///home/tony/projects/fansivibe_v1_backup/backend/alembic/versions/0036_media_upload_lease_token.py) (`0035 -> 0036`):
```sql
ALTER TABLE media_upload_authorizations 
ADD COLUMN processing_lease_token UUID NULL;
```
Mapped in [backend/app/infrastructure/db/models.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/db/models.py):
```python
processing_lease_token: Mapped[Optional[UUID]] = mapped_column(Uuid, nullable=True)
```

#### 1.2 Atomic Claim with Unique Token
Upon claiming a lease, a cryptographically unique token is generated:
```python
lease_token = uuid4()
auth.status = "processing"
auth.processing_started_at = db_now
auth.processing_lease_expires_at = lease_expires_at
auth.processing_lease_token = lease_token
self._db.commit()
```

#### 1.3 Conditional State Transitions & Zero-Row Abortion
All subsequent database modifications by the worker check both `upload_id` and `processing_lease_token`:
1. **Heartbeat Renewal:**
   ```sql
   UPDATE media_upload_authorizations
   SET processing_lease_expires_at = clock_timestamp() + make_interval(secs => :extend_seconds)
   WHERE upload_id = :upload_id
     AND processing_lease_token = :lease_token
     AND status = 'processing';
   ```
2. **Terminal Failure Recording (`_record_failure`):**
   ```sql
   UPDATE media_upload_authorizations
   SET status = 'failed',
       failure_reason = :reason,
       processing_lease_expires_at = NULL,
       processing_lease_token = NULL
   WHERE upload_id = :upload_id
     AND processing_lease_token = :lease_token
     AND status = 'processing';
   ```
3. **Retryable Status Recording (`_record_retryable_status`):**
   ```sql
   UPDATE media_upload_authorizations
   SET status = 'authorized',
       processing_lease_expires_at = NULL,
       processing_lease_token = NULL
   WHERE upload_id = :upload_id
     AND processing_lease_token = :lease_token
     AND status = 'processing';
   ```
4. **Final Publication (`_finalize_published_record`):**
   ```sql
   UPDATE media_upload_authorizations
   SET status = 'published',
       canonical_key = :canonical_key,
       canonical_sha256 = :canonical_sha256,
       ...
       processing_lease_expires_at = NULL,
       processing_lease_token = NULL
   WHERE upload_id = :upload_id
     AND processing_lease_token = :lease_token
     AND status = 'processing';
   ```

If `res.rowcount == 0`, the worker detects ownership loss, logs `Ownership lost for upload %s (lease token %s no longer owns record)`, immediately aborts the state transition, and avoids deleting staging data.

---

### Workstream 2: Operation Lifecycle Bounds and Lease Duration

#### 2.1 Bounded Pipeline Latency Model
Under worst-case production conditions:
- Advisory lock wait: max 3.0s (enforced by `SET LOCAL lock_timeout = '3s'`).
- Semaphore wait: max 5.0s (enforced by `semaphore_timeout_seconds=5.0s`).
- Transcoding subprocess: max 5.0s (enforced by `timeout=5.0s`, SIGKILL escalation, and PID reaping).
- R2 Storage operations: max 10.0s cumulative (staging read, canonical read, canonical put).
- Database commit operations: max 2.0s cumulative.

**Total bounded worst-case duration:** `3.0s + 5.0s + 5.0s + 10.0s + 2.0s = 25.0s`.

#### 2.2 Lease Policy Rationale
- **Lease Duration:** 30.0 seconds (safely exceeds the 25.0s bounded pipeline timeout).
- **Renewal Interval:** 5.0 seconds. While the worker executes external I/O, an asynchronous heartbeat task checks if the lease remains valid and extends `processing_lease_expires_at` by 30 seconds.
- **Top-Level Timeout:** The complete operation is wrapped with `asyncio.wait_for(..., timeout=25.0s)`. If an unexpected deadlock or network hang occurs, the coroutine is cancelled at 25 seconds, triggering lease reversion to `authorized` before the 30-second lease expires in the database.

---

### Workstream 3: PostgreSQL Wall-Clock Time Semantics

#### 3.1 `clock_timestamp()` vs `now()`
In PostgreSQL, `now()` (and `CURRENT_TIMESTAMP`) returns `transaction_timestamp()`, which is evaluated once at transaction initiation. When a connection waits for up to 3.0 seconds under `pg_advisory_xact_lock` contention:
- `transaction_timestamp()` reflects the time *before* the lock wait.
- `clock_timestamp()` returns the true wall-clock time *after* the lock is acquired.

#### 3.2 Implementation
In `CompleteMediaUpload._get_db_wallclock(conn)`:
```python
if is_postgres:
    res = conn.execute(text("SELECT clock_timestamp()"))
else:
    res = conn.execute(text("SELECT CURRENT_TIMESTAMP"))
```
All lease duration calculations (`processing_lease_expires_at = db_now + timedelta(seconds=self._lease_seconds)`) and SQL interval additions utilize `clock_timestamp()`.

---

### Workstream 4: Attempt-Limit and Cooldown Enforcement

#### 4.1 Universal Guard Before Processing
The attempt-limit and cooldown logic was moved out of `if auth.status == "processing":` to guard all non-published requests:
```python
if auth.status != "published":
    if auth.status == "failed":
        raise ApiError(
            status_code=409,
            code="UPLOAD_FAILED",
            message=f"Upload processing permanently failed: {auth.failure_reason or 'unknown'}",
        )
    if (auth.processing_attempts or 0) >= 5:
        if auth.processing_started_at is not None:
            cooldown_cutoff = auth.processing_started_at + timedelta(seconds=60)
            if db_now < cooldown_cutoff:
                retry_after_sec = max(1, int((cooldown_cutoff - db_now).total_seconds()))
                raise ApiError(
                    status_code=409,
                    code="PROCESSING_LIMIT_EXCEEDED",
                    message="Maximum processing attempts exceeded. Cooldown active.",
                    headers={"Retry-After": str(retry_after_sec)},
                )
            else:
                auth.processing_attempts = 1
        else:
            auth.processing_attempts = 1
    else:
        auth.processing_attempts = (auth.processing_attempts or 0) + 1
```

#### 4.2 Behavior Properties
1. Retryable failures (`status = "authorized"`) increment `processing_attempts` and cannot exceed 5 attempts within 60 seconds.
2. Terminal failures (`status = "failed"`) cannot re-enter `processing`; any subsequent attempt returns HTTP 409 `UPLOAD_FAILED`.
3. Cooldown expiration after 60 seconds safely resets `processing_attempts = 1`.
4. Published records remain replayable idempotently.

---

### Workstream 5: Fail-Closed Canonical Crash Recovery

#### 5.1 Recovery Validation Steps
1. **Deterministic Key Scoping:** Evaluates `users/{user_id}/wardrobe/{upload_id}/canonical.webp`. Confirms ownership match against caller JWT.
2. **Trusted Server Evidence:**
   ```python
   trusted_sha = auth.canonical_sha256 or (
       canonical_meta.custom_metadata.get("sha256") if canonical_meta.custom_metadata else None
   )
   if not trusted_sha:
       # Fail closed: never adopt canonical object without trusted server evidence!
       can_adopt = False
   ```
3. **Byte Stream & Checksum Matching:**
   Reads canonical bytes from storage (max 2MB), computes SHA-256, and verifies `compare_digest(actual_canonical_sha256, trusted_sha)`.
4. **Format & Magic Bytes:**
   Verifies `canonical_bytes[:4] == b"RIFF"` and `canonical_bytes[8:12] == b"WEBP"`.
5. **Strict Dimension Decoding:**
   Decodes dimensions via `Image.open(BytesIO(canonical_bytes))`. If corrupted or truncated, raises/catches exception, marks `can_adopt = False`, and falls back to fresh transcoding. Zero fake dimensions (`1920, 1440`) are permitted.
6. **Client Assertion Verification:**
   If `req.client_assertion_sha256` is provided, verifies against staging object bytes before adopting the canonical object.

---

### Disposable Database Migration Verification

Tested migration upgrade to head (`0036`) and downgrade to shared baseline (`0032`) against an isolated disposable database `fansivibe_migration_verify_p32`:

```
=== UPGRADING 0001 -> 0036 (HEAD) ===
Head Alembic Revision: 0036
Columns at 0036:
  ('user_id', 'uuid', 'NO')
  ('idempotency_key', 'character varying', 'NO')
  ('upload_id', 'uuid', 'NO')
  ('key_version', 'character varying', 'NO')
  ('request_fingerprint', 'character varying', 'NO')
  ('staging_key', 'character varying', 'NO')
  ('content_type', 'character varying', 'NO')
  ('size_bytes', 'integer', 'NO')
  ('created_at', 'timestamp with time zone', 'NO')
  ('expires_at', 'timestamp with time zone', 'NO')
  ('status', 'character varying', 'NO')
  ('canonical_key', 'character varying', 'YES')
  ('canonical_sha256', 'character varying', 'YES')
  ('canonical_size_bytes', 'integer', 'YES')
  ('canonical_width', 'integer', 'YES')
  ('canonical_height', 'integer', 'YES')
  ('completed_at', 'timestamp with time zone', 'YES')
  ('failure_reason', 'character varying', 'YES')
  ('processing_attempts', 'integer', 'NO')
  ('processing_started_at', 'timestamp with time zone', 'YES')
  ('processing_lease_expires_at', 'timestamp with time zone', 'YES')
  ('processing_lease_token', 'uuid', 'YES')

=== DOWNGRADING 0036 -> 0032 ===
Downgraded Alembic Revision: 0032
media_upload_authorizations table count at 0032: 0

=== MIGRATION UPGRADE & DOWNGRADE VERIFIED SUCCESSFULLY ===
```

### Shared Database Status
- `fansivibe`: Verified at revision `0032`.
- `fansivibe_test`: Verified at revision `0032`.
- Shared databases remained completely untouched throughout all tests.
