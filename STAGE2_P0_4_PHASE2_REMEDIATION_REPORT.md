# Fansivibe — Stage 2 P0-4 Phase 2.1 Technical Review Remediation Report

**Date:** 2026-11-01  
**Scope:** Stage 2 P0-4 Phase 2.1 Remediation (Backend Upload Authorization, Durable Idempotency & Atomic Distributed Rate Limiting)  
**Status:** **COMPLETED & VERIFIED (ALL 7 FINDINGS RESOLVED)**  
**Target Document:** `STAGE2_P0_4_PHASE2_FINAL_REVIEW.md`

---

## 1. Executive Summary

This remediation sprint addressed all seven findings (1 High, 1 Medium, 5 Low) identified in the independent technical review `STAGE2_P0_4_PHASE2_FINAL_REVIEW.md`.

All remediations were completed within the strict boundaries of Phase 2:
1. **HMAC Historical Key Resolution (Finding 1 - High):** Added `MEDIA_UPLOAD_PREVIOUS_KEY_ID` to `Settings`, paired with `MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS` and JSON `MEDIA_UPLOAD_KEY_RING` string parsing. Fixed key ring mapping so retrying authorizations created under an active predecessor key succeeds seamlessly. Fails closed on missing or insecure secrets.
2. **Advisory Lock Early Release (Finding 2 - Medium):** In `AuthorizeMediaUpload.execute`, both the fast-path (step 6) and locked-duplicate (step 9) paths now explicitly execute `self._db.rollback()` before awaiting asynchronous object storage URL generation (`self._storage.generate_presigned_put_url`). This completely releases the PostgreSQL transaction-scoped advisory lock before any external network I/O.
3. **Stable Lock Namespace (Finding 3 - Low):** Reconciled the advisory lock key namespace to the stable, established value `media_upload_rate_limit:{user_id}`, preventing lock inconsistency across deployed instances. Defined `MEDIA_UPLOAD_LOCK_NAMESPACE = "media_upload_rate_limit"`.
4. **PostgreSQL Server Time Rolling Window (Finding 4 - Low):** Window query now utilizes server-side `MediaUploadAuthorization.created_at >= (func.now() - text("INTERVAL '60 seconds'"))` when running against PostgreSQL, eliminating application host NTP clock drift across container instances while preserving SQLite compatibility for unit tests.
5. **Bounded Authorization Retention Pruning (Finding 5 - Low):** Refactored `prune_expired_authorizations` to delete records in bounded batches (default 1,000 per transaction commit) with support for `max_batches`, avoiding unbounded table locks and WAL spikes on large datasets.
6. **Lock Contention Timeout Coverage (Finding 6 - Low):** Added unit and integration tests proving that advisory lock acquisition timeout maps directly to HTTP 429 with `Retry-After: 5` header and `RATE_LIMITED` error code.
7. **SQLSTATE 55P03 Error Detection (Finding 7 - Low):** Replaced fragile English error string matching with driver-level SQLSTATE inspection (`exc.orig.pgcode == '55P03'` / `exc.orig.sqlstate == '55P03'`) with safe English fallback and 500 `DATABASE_FAILURE` default.

All 58 tests in `backend/tests/test_media_api.py` passed (100%), including genuine multi-session PostgreSQL concurrency tests against an isolated disposable database. The shared databases `fansivibe` and `fansivibe_test` were verified untouched and remain at revision `0032`.

---

## 2. Detailed Findings & Resolutions

### Finding 1: Historical Key Resolution Defect in `MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS` (HIGH)
- **Problem:** `effective_media_upload_key_ring` previously hardcoded the key identifier of `MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS` to `"kver_previous"`. When a request was originally authorized under an active key (e.g. `"kver_1"`), and the active key was rotated to `"kver_2"`, retrying the existing authorization under `"kver_1"` failed verification because `"kver_1"` was not in the key ring, improperly returning HTTP 409 `IDEMPOTENCY_CONFLICT`.
- **Resolution:**
  - Added `media_upload_previous_key_id: Optional[str] = Field(default=None, alias="MEDIA_UPLOAD_PREVIOUS_KEY_ID")` to `Settings`.
  - Updated `effective_media_upload_key_ring` to bind `prev_id = self.media_upload_previous_key_id or "kver_previous"`.
  - Added `@field_validator("media_upload_key_ring", mode="before")` to parse JSON strings from environment variables or configs into `dict[str, str]`.
  - Updated `_validate_production_invariants` to enforce that all secrets in the key ring (including previous secrets) meet production security requirements (>= 32 characters, no "dev" or "insecure").
  - Verified that an authorization created with an ancient/retired key version missing from the ring fails closed with HTTP 409 `IDEMPOTENCY_CONFLICT`.
- **Files Modified:** [settings.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/config/settings.py), [test_media_api.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_api.py).

### Finding 2: Advisory Lock Held Across Storage Signing in Step 9 (MEDIUM)
- **Problem:** When an existing authorization was detected in step 9 under the advisory lock, the code awaited `self._storage.generate_presigned_put_url(...)` without committing or rolling back `self._db`. Because `pg_advisory_xact_lock` is held until transaction termination, the lock was held across external network/thread I/O.
- **Resolution:**
  - Factored out presigned URL minting and response formatting into `_generate_upload_response`.
  - In step 9 (locked existing branch): extracted `locked_existing.upload_id` and `staging_key`, immediately called `self._db.rollback()`, and then called `await self._generate_upload_response(...)`.
  - In step 6 (fast-path existing branch): explicitly called `self._db.rollback()` before awaiting `_generate_upload_response`.
  - Added unit tests verifying `db.rollback()` is executed before `generate_presigned_put_url` is invoked.
- **Files Modified:** [media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py), [test_media_api.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_api.py).

### Finding 3: Advisory Lock Namespace Divergence (LOW)
- **Problem:** The implementation report claimed the namespace was `fansivibe:media_upload:{user_id}`, while the code used `media_upload_rate_limit:{user_id}`.
- **Resolution:**
  - Defined explicit constant `MEDIA_UPLOAD_LOCK_NAMESPACE = "media_upload_rate_limit"`.
  - Reconciled documentation and code to standardize on `"media_upload_rate_limit:"` as the chosen stable namespace, preventing lock collisions across existing deployed versions.
  - Added unit test asserting `MEDIA_UPLOAD_LOCK_NAMESPACE` and 64-bit integer range.
- **Files Modified:** [media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py), [test_media_api.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_api.py).

### Finding 4: Clock Source Drift in Rolling 60-Second Window (LOW)
- **Problem:** Rate limiting evaluated against Python application time (`now - timedelta(seconds=60)`), which could skew across multi-host or multi-worker deployments.
- **Resolution:**
  - When `is_postgres` is True, rate-limit counting uses PostgreSQL server time:
    `MediaUploadAuthorization.created_at >= (func.now() - text("INTERVAL '60 seconds'"))`.
  - Preserved Python fallback filter for SQLite in-memory tests.
  - Added test verifying compilation to PostgreSQL SQL with `now() - INTERVAL '60 seconds'`.
- **Files Modified:** [media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py), [test_media_api.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_api.py).

### Finding 5: Bounded Retention Pruning Deletion (LOW)
- **Problem:** `prune_expired_authorizations` issued an unbatched `DELETE FROM media_upload_authorizations WHERE expires_at < cutoff`.
- **Resolution:**
  - Redesigned `prune_expired_authorizations(db, *, now=None, batch_size=1000, max_batches=None)` to select expired `upload_id` values bounded by `LIMIT batch_size`, delete by ID in chunks, and commit each batch until exhausted or `max_batches` reached.
  - Added tests covering multi-batch execution (batch size 2 on 5 items) and remaining unexpired/unpruned records.
- **Files Modified:** [media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py), [test_media_api.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_api.py).

### Finding 6: Missing Unit Test Coverage for Lock Timeout (`Retry-After: 5`) (LOW)
- **Problem:** No tests verified that lock acquisition timeout mapped to HTTP 429 with `Retry-After: 5`.
- **Resolution:**
  - Added unit tests in `TestConcurrencyAndAdvisoryLocking`:
    - `test_lock_contention_timeout_via_sqlstate_55p03_maps_to_429_retry_after_5`
    - `test_lock_contention_timeout_via_english_string_fallback`
    - `test_endpoint_lock_timeout_returns_http_429_with_retry_after_header`
- **Files Modified:** [test_media_api.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_api.py).

### Finding 7: Fragile String Matching for PostgreSQL Lock Timeout (LOW)
- **Problem:** Timeout translation relied exclusively on English exception substrings (`"lock_timeout"` or `"canceling statement due to lock timeout"`).
- **Resolution:**
  - Added SQLSTATE detection inspecting `exc.orig.pgcode == '55P03'` or `exc.orig.sqlstate == '55P03'` (PostgreSQL `lock_not_available` / lock timeout).
  - Preserved English message fallback for non-PostgreSQL / mock drivers.
  - Wrapped step 4 fast check with identical safe error handling.
  - Added test verifying non-timeout operational errors safely map to HTTP 500 `DATABASE_FAILURE`.
- **Files Modified:** [media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py), [test_media_api.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_api.py).

---

## 3. Exact Files and Functions Changed

| File | Functions / Properties Changed | Purpose |
|---|---|---|
| `backend/app/config/settings.py` | `Settings.media_upload_previous_key_id`<br>`Settings.effective_media_upload_key_ring`<br>`Settings._parse_media_upload_key_ring`<br>`Settings._resolve_aliases`<br>`Settings._validate_production_invariants` | Key rotation previous-ID mapping, JSON key ring parsing, fail-closed validation |
| `backend/app/application/media.py` | `MEDIA_UPLOAD_LOCK_NAMESPACE`<br>`get_media_upload_lock_key`<br>`prune_expired_authorizations`<br>`AuthorizeMediaUpload._generate_upload_response`<br>`AuthorizeMediaUpload.execute` | Advisory lock early release, server-side time, bounded pruning, SQLSTATE 55P03 handling |
| `backend/tests/test_media_api.py` | `TestDurableIdempotency`<br>`TestConfigurationAndSecurity`<br>`TestRateLimitingAndRetention`<br>`TestConcurrencyAndAdvisoryLocking` | Added 15 targeted tests covering all remediated behaviors and edge cases |

---

## 4. Test Verification & Evidence

### 4.1 Media API Suite (`tests/test_media_api.py`)
Executed with `pytest -v`:
- **58 total tests collected: 58 passed (100%), 0 failed, 0 skipped** (when run against PostgreSQL test DB).
- **56 passed, 2 skipped** (in pure SQLite in-memory mode without PostgreSQL).

### 4.2 Genuine PostgreSQL Multi-Session Concurrency Evidence
Executed against isolated disposable database `fansivibe_disposable_remediation_p04`:
1. `test_concurrent_upload_authorizations_enforce_atomic_rate_limit`:
   - 40 simultaneous threads targeting a single user.
   - Result: **Exactly 30 authorizations succeeded (HTTP 201), exactly 10 requests rejected with HTTP 429 (`Retry-After: 60`).**
2. `test_concurrent_identical_idempotency_requests_return_same_slot`:
   - 10 simultaneous threads submitting identical parameters and `Idempotency-Key`.
   - Result: **All 10 succeeded, all received identical `uploadId`, exactly 1 record persisted in PostgreSQL.**

### 4.3 HMAC Key Rotation & Settings Evidence
1. `test_effective_media_upload_key_ring_resolves_previous_key_id`: Passed.
2. `test_key_rotation_preserves_inflight_retry_via_settings`: Passed.
3. `test_json_key_ring_parsing_and_resolution`: Passed.
4. `test_missing_historical_key_fails_safely`: Passed (HTTP 409 `IDEMPOTENCY_CONFLICT`).
5. `test_production_settings_requires_secure_previous_secret`: Passed (`ValidationError`).

### 4.4 Transaction Release & Early Lock Termination Evidence
1. `test_transaction_closed_before_storage_signing_in_retry_path`: Passed. Proved `db.rollback()` was invoked prior to `storage.generate_presigned_put_url`.
2. `test_transaction_closed_before_storage_signing_in_locked_retry_path`: Passed. Proved `db.rollback()` was invoked under step 9 duplicate unblock prior to external URL signing.

### 4.5 Lock Timeout & SQLSTATE 55P03 Evidence
1. `test_lock_contention_timeout_via_sqlstate_55p03_maps_to_429_retry_after_5`: Passed.
2. `test_lock_contention_timeout_via_english_string_fallback`: Passed.
3. `test_non_timeout_operational_error_maps_to_500_database_failure`: Passed.
4. `test_endpoint_lock_timeout_returns_http_429_with_retry_after_header`: Passed.

### 4.6 Bounded Retention Pruning Evidence
1. `test_prune_expired_authorizations_bounded_batches`: Passed (5 records pruned across 3 batches of size 2).
2. `test_prune_expired_authorizations_with_max_batches_and_remaining`: Passed (max_batches=1 pruned 2 records, left 3 expired and 1 active intact).

### 4.7 Full Regression Suites
- Storage adapter & DI suites (`test_storage_adapter.py`, `test_storage_di.py`, `test_storage_config.py`, `test_fake_storage.py`): **54 passed in 1.33s**.
- Settings & canary hardening suites (`test_settings.py`, `test_production_hardening.py`, `test_production_canary.py`): **65 passed in 1.53s**.
- Bytecode compilation: `python -m py_compile` passed clean with 0 warnings or errors.
- Whitespace validation: `git diff --check` passed clean with 0 errors.

---

## 5. Migration Safety and Database Isolation

- **Disposable Database Isolation:** All PostgreSQL integration tests and migration runs were conducted strictly against temporary disposable database `fansivibe_disposable_remediation_p04`.
- **Clean Downgrade Verified:** `alembic downgrade -1` (`0033 -> 0032`) succeeded cleanly on the disposable database prior to dropping.
- **Disposable Database Teardown:** `DROP DATABASE fansivibe_disposable_remediation_p04;` completed successfully.
- **Shared Database Protection Verified:**
  - `fansivibe` (development DB): Version strictly `0032`.
  - `fansivibe_test` (test DB): Version strictly `0032`.
  - Zero shared database migrations were run.

---

## 6. Git Status and Strict Boundaries

### Modified Files (This Task Only):
- `backend/app/config/settings.py`
- `backend/app/application/media.py`
- `backend/tests/test_media_api.py`
- `STAGE2_P0_4_PHASE2_REMEDIATION_REPORT.md` (new report)

### Preserved Files:
- All pre-existing modified files and untracked backend/flutter files strictly preserved.
- Zero Flutter mobile code touched.
- Zero Phase 3 code (transcoding, Pillow decoding, upload completion, canonical promotion) touched.
- Zero Cloudflare R2 cloud API calls made.

---

## 7. Remaining Limitations

1. **Phase 3 Pipeline Dependency:** The presigned upload URL generated by this endpoint provides client-to-staging access. Conversion of staged images into canonical 1080x1440 WebP wardrobe assets and DB records awaits the Phase 3 transcoding and completion endpoint.
2. **PostgreSQL Migration Execution:** Migration 0033 has been verified in disposable environments but has intentionally not been applied to shared development (`fansivibe`) or test (`fansivibe_test`) databases, pending official deployment orchestration.
