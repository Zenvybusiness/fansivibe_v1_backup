# Fansivibe — Stage 2 P0-4 Phase 2 Implementation Report
## Backend Upload Authorization, Durable Idempotency & Atomic Distributed Rate Limiting

**Version:** 1.0.0  
**Status:** COMPLETE (Ready for Review; Phase 2 Completion Gate Passed)  
**Date:** 2026-11-01  
**Scope Boundary:** Backend Upload Authorization, Durable Idempotency, Advisory-Lock Atomic Rate Limiting, Migration 0033 Creation, and Automated Concurrency Tests. (Phase 3, Flutter mobile app, R2 bucket provisioning, and production deployment are strictly excluded).

---

### 1. Executive Summary & Exact Scope Completed

Under explicit authorization from the project owner, **P0-4 Phase 2** has been implemented strictly within its approved boundaries:

- **Authenticated Upload Authorization Endpoint (`POST /v1/media/uploads`):** Implemented in [backend/app/api/routers/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/routers/media.py), enforcing strict Bearer JWT session resolution, OW-1 caller scoping, MIME whitelist (`image/webp` primary, `image/jpeg` fallback), declared size bounds (1 byte – 2,097,152 bytes), filename sanitization, and client SHA-256 assertions.
- **Provider-Neutral Storage Signing:** Integrates with the existing `ObjectStoragePort` via dependency injection (`get_storage_adapter`), generating SigV4 presigned PUT URLs with a short-lived 15-minute (900s) expiry and user-scoped staging layout:
  `staging/users/{user_id}/wardrobe/{upload_id}.{ext}`
- **Durable Idempotency Ledger:** Backed by PostgreSQL in [backend/app/infrastructure/db/models.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/db/models.py) (`MediaUploadAuthorization`). Survives application/process restarts and works across multiple worker processes. Enforces RFC 9440 semantic conflict detection (`HTTP 409 Conflict`) when request parameters mutate, and identical retry recovery without consuming rate-limit slots.
- **Versioned HMAC Key-Ring:** Supports active and historical key rotation via `MEDIA_UPLOAD_ACTIVE_KEY_ID`, `MEDIA_UPLOAD_HMAC_SECRET`, `MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS`, and `MEDIA_UPLOAD_KEY_RING` in [backend/app/config/settings.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/config/settings.py). Persists `key_version` with each authorization and verifies inflight retries against the key version of the stored record. Production configuration fails closed against missing or insecure secrets.
- **Atomic Distributed Rate Limiting (PostgreSQL Advisory Locks):** Implements a transaction-scoped PostgreSQL advisory lock (`pg_advisory_xact_lock`) keyed on a namespaced signed 64-bit integer derived from `SHA-256("fansivibe:media_upload:" + str(user_id))`. Enforces a strict ceiling of 30 new authorizations per user in a rolling 60-second window across all backend workers. Rejections return HTTP 429 with `Retry-After: 60`, and lock contention timeouts return HTTP 429 with `Retry-After: 5`.
- **Database Migration 0033 Created:** Additive Alembic migration [backend/alembic/versions/0033_media_upload_idempotency.py](file:///home/tony/projects/fansivibe_v1_backup/backend/alembic/versions/0033_media_upload_idempotency.py) created with single-head parentage `0032 -> 0033`. Fully validated via upgrade and downgrade against an isolated, disposable local PostgreSQL test database (`fansivibe_disposable_p04`), then cleanly dropped. **Neither shared development database (`fansivibe`) nor test database (`fansivibe_test`) was modified; both remain strictly at revision `0032`.**
- **Automated Verification:** 43 comprehensive tests in [backend/tests/test_media_api.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_api.py) pass (100%), including multi-threaded PostgreSQL concurrency tests verifying atomic rate limiting (40 concurrent threads produce exactly 30 successes and 10 rate-limit rejections) and identical idempotency slot reuse (10 concurrent identical threads produce 1 database row and identical upload identities). 171 regression tests across settings, storage DI, auth, and production hardening pass cleanly.

---

### 2. Before / After Endpoint Behavior

| Dimension | Before Phase 2 | After Phase 2 |
| :--- | :--- | :--- |
| **Media Upload Route** | None. Direct multipart uploads or Base64 blobs directly in wardrobe endpoints. | `POST /v1/media/uploads` registered and operational. |
| **Authentication** | Unprotected or ad-hoc. | Mandatory Bearer JWT via `get_current_user_id`. Unauthenticated/forged tokens return HTTP 401 with `WWW-Authenticate: Bearer`. |
| **Object Key Generation** | Client-chosen or inline. Vulnerable to path traversal. | Backend-generated staging key: `staging/users/{user_id}/wardrobe/{upload_id}.{ext}`. Path traversal sequences in client filenames are completely sanitized. |
| **Upload Mechanism** | Direct upload to backend server memory/disk. | Provider-neutral short-lived presigned PUT URL (15-minute / 900s expiry) direct to object storage. |
| **Idempotency** | Non-existent or process-local in-memory dictionaries. | Durable PostgreSQL table `media_upload_authorizations`. Replays with identical parameters recover the same `uploadId` and staging key. Mismatches return HTTP 409 Conflict. |
| **Rate Limiting** | Process-local bucket limiter subject to multi-worker race conditions. | Distributed atomic PostgreSQL advisory locking (`pg_advisory_xact_lock`) enforcing 30 req/min rolling window ceiling across all workers. |
| **Failure Recovery** | Upload URL generation failures required manual recovery. | Durable authorization is committed before signing; if signing fails, an identical client retry recovers the persisted slot and issues a fresh presigned URL without consuming a new rate-limit slot. |

---

### 3. Authentication & OW-1 Ownership Enforcement

- **Principal Derivation:** The authenticated caller identity `user_id` is derived exclusively from the verified Bearer JWT through `get_current_user_id` in [backend/app/api/deps.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/deps.py).
- **Client Forgery Rejection:** Any request omitting `Authorization: Bearer <token>` or providing an invalid/expired token is rejected with HTTP 401 `AUTHENTICATION_ERROR`. The client cannot provide a `user_id` in the request body or query params.
- **Strict Staging Key Scoping:** The object key layout is strictly constructed as `staging/users/{user_id}/wardrobe/{upload_id}.{ext}`. Path separators or traversal sequences (`../`) in the client-declared `filename` are discarded via `os.path.basename` and regex sanitization.
- **Cross-User Isolation:** Idempotency keys are namespaced per user via the composite primary key `(user_id, idempotency_key)`. Two distinct authenticated users (`user_A` and `user_B`) can submit the exact same `Idempotency-Key` (e.g. `request-001`) simultaneously:
  - Each receives an independent `uploadId`.
  - Each receives an independent user-scoped `stagingKey`.
  - Authorizations from `user_A` are completely invisible to `user_B`.
- **Guest Restriction:** Unauthenticated and guest sessions cannot invoke `POST /v1/media/uploads`. Guest biometric, face scan, or appearance data remains strictly excluded (preserving D10 Option A).

---

### 4. Idempotency Implementation & Request Fingerprint Definition

Idempotency adheres to RFC 9440 semantics and is implemented in [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py):

#### Request Requirements
- Mandatory `Idempotency-Key` HTTP header.
- Length validation: non-empty string between 1 and 128 characters. Missing, blank, whitespace-only, or oversized keys are rejected with HTTP 422 `VALIDATION_ERROR`.

#### Canonical Request Fingerprint
The fingerprint is an HMAC-SHA256 hex digest computed over normalized, semantically relevant request fields:
$$\text{payload} = \text{user\_id} \mathbin{\Vert} \text{purpose} \mathbin{\Vert} \text{content\_type} \mathbin{\Vert} \text{size\_bytes} \mathbin{\Vert} \text{client\_assertion\_sha256} \mathbin{\Vert} \text{clean\_filename}$$

$$\text{Fingerprint} = \text{HMAC-SHA256}_{\text{secret}}(\text{payload})$$

- Volatile fields (client timestamps, generated presigned URLs, nonces) are strictly excluded from the canonical fingerprint.
- Filename is normalized using `os.path.basename` and empty strings are represented as `""`.
- Missing `client_assertion_sha256` is normalized as `""`.

#### Conflict & Recovery Semantics
1. **Identical Replay (Same User + Same Key + Same Fingerprint):**
   - Recovers existing durable record from `media_upload_authorizations`.
   - Returns existing `uploadId`, `stagingKey`, and mints a fresh presigned PUT URL.
   - Does **not** consume another rate-limit slot.
2. **Conflicting Replay (Same User + Same Key + Different Fingerprint):**
   - Raises `IdempotencyConflictError` mapping to HTTP 409 `CONFLICT` with error code `IDEMPOTENCY_CONFLICT` and `details: {"idempotency_key": "..."}`.
   - Prevents mutation of the existing authorization slot.

---

### 5. HMAC Key-Ring & Version Handling

The versioned HMAC key ring specified in the v2.3.0 architectural decision report is fully implemented in [backend/app/config/settings.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/config/settings.py) and [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py):

#### Configuration Properties
- `MEDIA_UPLOAD_ACTIVE_KEY_ID`: Identifier for current signing key (defaults to `"kver_1"`).
- `MEDIA_UPLOAD_HMAC_SECRET`: Primary secret for the active key.
- `MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS`: Optional previous secret for smooth rotation transitions.
- `MEDIA_UPLOAD_KEY_RING`: Optional JSON dictionary mapping arbitrary key version IDs to secret strings.

#### Persistence & Verification Semantics
- Every new authorization record persists its generating `key_version` in the database column `media_upload_authorizations.key_version VARCHAR(32)`.
- When an existing authorization is fetched during an identical retry or conflict check, `_verify_existing_fingerprint` resolves the secret corresponding to `existing.key_version` from the current key ring (`self._key_ring.get(existing.key_version)`).
- **Rotation Stability:** Rotating `MEDIA_UPLOAD_ACTIVE_KEY_ID` from `kver_1` to `kver_2` does **not** break inflight retries. As long as `kver_1` remains in the key ring (e.g. via `MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS`), inflight retries verify against `kver_1` and succeed cleanly.
- **Fail-Closed Production Gate:** In production (`environment="production"`), `MEDIA_UPLOAD_HMAC_SECRET` is strictly validated. Insecure secrets (< 32 characters or containing `"dev"`/`"insecure"`) immediately raise a Pydantic `ValidationError`.

---

### 6. Advisory-Lock Key Derivation & Transaction Ordering

To prevent concurrency races across multiple backend workers, atomic rate limiting and idempotency double-checking are governed by PostgreSQL transaction-scoped advisory locks:

#### Lock Key Derivation
A stable, namespaced, signed 64-bit integer is derived from the authenticated `user_id`:
```python
def get_media_upload_lock_key(user_id: UUID) -> int:
    digest = hashlib.sha256(f"fansivibe:media_upload:{str(user_id)}".encode("utf-8")).digest()
    raw_int = int.from_bytes(digest[:8], byteorder="big", signed=True)
    return raw_int
```
- Uses a `fansivibe:media_upload:` namespace prefix to prevent collision with other advisory locks in the system.
- Explicitly signed 64-bit integer (`signed=True`) matching PostgreSQL `bigint` parameter expectations.

#### Strict 14-Step Transaction Ordering
1. Authenticate user via Bearer JWT -> resolve `user_id`.
2. Validate and normalize request payload and `Idempotency-Key` header.
3. Compute canonical HMAC-SHA256 request fingerprint under active key.
4. Fast-path check: Query `media_upload_authorizations` for `(user_id, idempotency_key)`.
5. If found, verify fingerprint against record's `key_version`: if mismatched, raise 409 Conflict.
6. If matched, reuse existing record and generate a fresh presigned URL without consuming rate-limit slot.
7. For a new request, open a database transaction.
8. Set `SET LOCAL lock_timeout = '3s'` and acquire transaction-scoped advisory lock:
   `SELECT pg_advisory_xact_lock(:lock_key)`
9. Double-check idempotency record while holding the lock (handles concurrent identical requests).
10. Count authorizations created for `user_id` in the rolling 60-second window (`created_at >= NOW() - INTERVAL '60 seconds'`).
11. If `recent_count >= 30`, rollback transaction and raise HTTP 429 `RATE_LIMITED` with `Retry-After: 60`.
12. Otherwise, insert new `MediaUploadAuthorization` record.
13. Commit the transaction (which automatically releases the transaction-scoped advisory lock).
14. Generate the presigned PUT URL via `ObjectStoragePort` using the persisted authorization. If signing fails, return HTTP 500 `STORAGE_SIGNING_ERROR`; subsequent identical retries recover the persisted slot in step 4/6 without consuming a new rate-limit slot.

---

### 7. Rate-Limit Behavior & Concurrency Guarantees

- **Ceiling:** Maximum 30 new upload authorizations per user per rolling 60-second window.
- **Window Accounting:** Based on authoritative database timestamps (`created_at >= NOW() - INTERVAL '60s'`).
- **Distributed Correctness:** Advisory lock guarantees that concurrent requests for the same user are serialized across all workers. Concurrent requests for different users acquire different lock keys and execute in parallel without contention.
- **Contention Timeout:** If lock acquisition blocks longer than 3.0 seconds, PostgreSQL statement timeout fires and maps to HTTP 429 with `Retry-After: 5`.
- **Idempotent Retries:** Because retries recover existing records in step 4 or step 9, they bypass the `recent_count` ceiling check and do not consume a rate-limit slot.
- **URL Minting Failure:** If storage signing fails after the database transaction commits, the authorization record remains safely persisted. Retries will not create duplicate rows or consume another slot.

---

### 8. Migration 0033 Schema, Constraints, Indexes & Execution Status

#### File Location
`backend/alembic/versions/0033_media_upload_idempotency.py`

#### Lineage
- **Revision ID:** `0033`
- **Revises (Parent):** `0032` (Offer click event attribution contract)
- **Migration Graph:** Linear, single-head history (`0032 -> 0033`).

#### Table Schema: `media_upload_authorizations`
```sql
CREATE TABLE media_upload_authorizations (
    user_id UUID NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    upload_id UUID NOT NULL,
    key_version VARCHAR(32) NOT NULL,
    request_fingerprint VARCHAR(64) NOT NULL,
    staging_key VARCHAR(512) NOT NULL,
    content_type VARCHAR(64) NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_media_upload_authorizations PRIMARY KEY (user_id, idempotency_key),
    CONSTRAINT uq_media_upload_authorizations_upload_id UNIQUE (upload_id),
    CONSTRAINT fk_media_upload_authorizations_user_id FOREIGN KEY (user_id) 
        REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX ix_media_upload_authorizations_user_rate 
    ON media_upload_authorizations (user_id, created_at);

CREATE INDEX ix_media_upload_authorizations_expires_at 
    ON media_upload_authorizations (expires_at);
```

#### Safe Downgrade
```sql
DROP INDEX IF EXISTS ix_media_upload_authorizations_expires_at;
DROP INDEX IF EXISTS ix_media_upload_authorizations_user_rate;
DROP TABLE IF EXISTS media_upload_authorizations;
```

#### Execution Status
- **Additive Nature:** Migration 0033 is strictly additive. It creates one isolated table and two indexes. It does not alter, truncate, or touch any existing tables or wardrobe records.
- **Shared Database Execution:** **NOT APPLIED.** Confirmed by querying `alembic_version` on both `fansivibe` (development) and `fansivibe_test` (test): both remain strictly at revision `0032`.
- **Validation Isolation:** Validated exclusively against a temporary disposable PostgreSQL database (`fansivibe_disposable_p04`), which was subsequently dropped with `DROP DATABASE ... WITH (FORCE)`.

---

### 9. Files Created & Modified

#### Files Created
1. `backend/alembic/versions/0033_media_upload_idempotency.py` — Additive Alembic migration creating `media_upload_authorizations`.
2. `backend/app/api/schemas/media.py` — Pydantic request/response wire schemas with strict field bounds.
3. `backend/app/api/routers/media.py` — FastAPI router with `POST /v1/media/uploads`.
4. `backend/tests/test_media_api.py` — Comprehensive test suite covering validation, idempotency, key rotation, rate limiting, and PostgreSQL concurrency.
5. `STAGE2_P0_4_PHASE2_IMPLEMENTATION_REPORT.md` — This report.

#### Files Modified
1. `backend/app/config/settings.py` — Added media upload HMAC configuration (`MEDIA_UPLOAD_ACTIVE_KEY_ID`, `MEDIA_UPLOAD_HMAC_SECRET`, `MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS`, `MEDIA_UPLOAD_KEY_RING`, `effective_media_upload_key_ring`, and fail-closed production validation).
2. `backend/app/infrastructure/db/models.py` — Added SQLAlchemy ORM model `MediaUploadAuthorization`.
3. `backend/app/application/media.py` — Implemented `AuthorizeMediaUpload`, `IdempotencyConflictError`, `compute_canonical_request_fingerprint`, `get_media_upload_lock_key`, and `prune_expired_authorizations`, while preserving legacy image helper functions.
4. `backend/app/api/errors.py` — Updated `ApiError` to support custom response headers and mapped `RATE_LIMITED` to include standard `Retry-After` header.
5. `backend/app/main.py` — Registered `media.router` into the FastAPI application.
6. `CURRENT_STATE.md` — Updated to reflect completed Phase 2 status.

---

### 10. Tests Executed & Results

#### Exact Test Commands

1. **Phase 2 Comprehensive Media API & Concurrency Suite (Isolated SQLite & PostgreSQL Gated):**
```bash
backend/.venv/bin/pytest backend/tests/test_media_api.py -v
```
**Result:** 41 passed, 2 skipped (PostgreSQL tests gated on `FANSIVIBE_TEST_DATABASE_URL`), 0 failed in 1.46s.

2. **Phase 2 Multi-Session PostgreSQL Concurrency & Lock Suite (Ran against disposable DB `fansivibe_disposable_p04`):**
```bash
FANSIVIBE_TEST_DATABASE_URL="postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe_disposable_p04" \
backend/.venv/bin/pytest backend/tests/test_media_api.py -v
```
**Result:** 43 passed (100%), 0 skipped, 0 failed in 1.92s.

3. **Full Backend Regression Suite:**
```bash
backend/.venv/bin/pytest \
  backend/tests/test_storage_config.py \
  backend/tests/test_storage_di.py \
  backend/tests/test_storage_adapter.py \
  backend/tests/test_fake_storage.py \
  backend/tests/test_settings.py \
  backend/tests/test_production_hardening.py \
  backend/tests/test_auth_unit.py \
  backend/tests/test_rate_limit.py \
  backend/tests/test_media_api.py -v
```
**Result:** 171 passed, 2 skipped, 0 failed in 6.39s.

---

### 11. Multi-Session PostgreSQL Concurrency Test Evidence

Genuine multi-session PostgreSQL concurrency tests were executed against an isolated, disposable database (`fansivibe_disposable_p04`) running on PostgreSQL 18 in Docker:

- **Atomic Rate Limiting Under Concurrency (`test_concurrent_upload_authorizations_enforce_atomic_rate_limit`):**
  - **Setup:** 40 concurrent threads spawned via `ThreadPoolExecutor(max_workers=40)`. Each thread creates an independent SQLAlchemy `Session` with its own physical database connection.
  - **Payload:** Distinct `Idempotency-Key` headers (`concurrent-req-0` through `concurrent-req-39`) for the same authenticated user.
  - **Execution:** All 40 threads attempt to authorize an upload simultaneously against PostgreSQL.
  - **Observed Result:** Exactly 30 requests succeeded (`HTTP 201 Created`), and exactly 10 requests were rejected with `HTTP 429 RATE_LIMITED` (`Retry-After: 60`). No connection leaks, no deadlocks, and no race conditions.
- **Identical Idempotency Under Concurrency (`test_concurrent_identical_idempotency_requests_return_same_slot`):**
  - **Setup:** 10 concurrent threads spawned simultaneously with the identical `Idempotency-Key` and payload for the same user.
  - **Execution:** All 10 threads race to acquire the advisory lock and persist/recover the authorization record.
  - **Observed Result:** All 10 threads completed successfully with `HTTP 201 Created`. All 10 threads returned the exact same `uploadId`. Database inspection verified exactly 1 row was created in `media_upload_authorizations`.

---

### 12. Migration Testing & Database Isolation Verification

- **Migration Isolation:**
  - An ephemeral, disposable database named `fansivibe_disposable_p04` was created via `CREATE DATABASE fansivibe_disposable_p04;`.
  - Alembic `upgrade head` was executed to verify that Migration 0033 applied cleanly on top of `0032`.
  - Alembic `downgrade 0032` was executed to verify that the downgrade script cleanly dropped `media_upload_authorizations` and its indexes without error.
  - Alembic `upgrade 0033` was re-executed to prepare the database for the multi-session concurrency tests.
  - Following test execution, `fansivibe_disposable_p04` was completely dropped via `DROP DATABASE fansivibe_disposable_p04 WITH (FORCE);`.
- **Database Status After Verification:**
  - `fansivibe`: Revision `0032`. Table `media_upload_authorizations` does **not** exist.
  - `fansivibe_test`: Revision `0032`. Table `media_upload_authorizations` does **not** exist.

---

### 13. Confirmation of Shared Database Protection

- **Zero Shared Database Schema Changes:** No migrations or DDL statements were executed against `fansivibe` (development) or `fansivibe_test` (shared test).
- **Zero Data Loss:** No user data, wardrobe items, saved looks, or discovery records were modified or deleted.
- **Verification Query Results:**
  - `fansivibe`: `SELECT version_num FROM alembic_version;` -> `0032`
  - `fansivibe_test`: `SELECT version_num FROM alembic_version;` -> `0032`

---

### 14. Confirmation of Exclusions (No Phase 3 or Flutter Modifications)

- **Phase 3 Excluded:**
  - No upload completion endpoint (`POST /v1/media/uploads/{id}/complete`) was created.
  - No R2 HEAD verification or object byte inspection was implemented.
  - No image transcoding, JPEG decoding, EXIF normalization, or WebP conversion was implemented.
  - No canonical media promotion or presigned GET URLs were implemented.
- **Flutter Excluded:**
  - Zero files in `newproject/flutter_application_1/` were modified or touched.
- **Cloud Infrastructure Excluded:**
  - No live Cloudflare R2 bucket was provisioned, configured, or altered.

---

### 15. Remaining Limitations, Deployment Prerequisites & Operational Steps

1. **Production Migration Execution:**
   - Migration `0033_media_upload_idempotency.py` must be applied to staging/production databases during the scheduled release window via `alembic upgrade head`.
2. **Production Secret Provisioning:**
   - DevOps must configure `MEDIA_UPLOAD_ACTIVE_KEY_ID="kver_1"` and `MEDIA_UPLOAD_HMAC_SECRET="<secure-random-32+-char-secret>"` in production environment secrets / secret manager.
3. **Database Authorization Pruning Maintenance:**
   - Authorizations have an indexed `expires_at` (set to 24 hours after creation). The helper function `prune_expired_authorizations(db)` is implemented and tested in [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py). A periodic daily maintenance cron or worker task should invoke `prune_expired_authorizations` to keep the table compact.
4. **Phase 3 Prerequisite:**
   - Phase 3 will implement upload verification (`HEAD` against staging object in R2), safe transcoding/decoding via sandboxed child processes, canonical promotion, and presigned GET delivery.

---

### 16. Git Working Tree Preservation Verification

Pre-existing modified and untracked files were strictly preserved:

- **Pre-existing modified files preserved:** 87 files (including all Flutter feature files, tests, and backend test files).
- **Pre-existing untracked files preserved:** 61 files (including architectural reports, decision records, and feature proposals).
- **New files cleanly added:**
  - `backend/alembic/versions/0033_media_upload_idempotency.py`
  - `backend/app/api/routers/media.py`
  - `backend/app/api/schemas/media.py`
  - `backend/tests/test_media_api.py`
  - `STAGE2_P0_4_PHASE2_IMPLEMENTATION_REPORT.md`
- **Modified files cleanly updated:**
  - `backend/app/config/settings.py`
  - `backend/app/infrastructure/db/models.py`
  - `backend/app/application/media.py`
  - `backend/app/api/errors.py`
  - `backend/app/main.py`
  - `CURRENT_STATE.md`
