# Fansivibe — Stage 2 P0-4 Phase 2 Final Technical Review

**Audit Date:** 2026-11-01  
**Audit Target:** Stage 2 P0-4 Phase 2 Implementation (Backend Upload Authorization, Durable Idempotency & Atomic Distributed Rate Limiting)  
**Audit Scope:** Read-only inspection of implementation report, Alembic Migration 0033, schemas, routers, application service, ORM models, configuration/settings, storage port/adapter, and media API & concurrency test suites.  
**Review Verdict:** **ACCEPTED WITH NON-BLOCKING FINDINGS**

---

## 1. Executive Audit Summary

A rigorous, independent, code-level technical review of the Stage 2 P0-4 Phase 2 implementation was conducted across all committed and staged artifacts.

The implementation successfully achieves the core requirements for Phase 2:
1. **Authenticated Media Upload Authorization (`POST /v1/media/uploads`):** Caller identity is strictly bound to the verified Bearer JWT session via `get_current_user_id` (enforcing OW-1 caller scoping). Guests and unauthenticated callers are rejected with HTTP 401. Input boundaries are strictly validated and normalized (1 byte – 2 MB, MIME whitelist `image/webp` primary and `image/jpeg` fallback, purpose restricted to `wardrobe_item`, sanitized filename).
2. **Provider-Neutral Storage Signing:** Integrates cleanly with `ObjectStoragePort` via dependency injection (`get_storage_adapter`), minting short-lived SigV4 presigned PUT URLs (15-min / 900s TTL) directed to user-scoped staging paths (`staging/users/{user_id}/wardrobe/{upload_id}.{ext}`).
3. **Durable Idempotency & Conflict Detection (RFC 9440):** Backed by PostgreSQL table `media_upload_authorizations` with composite primary key `(user_id, idempotency_key)`. Parameter alterations under the same key immediately raise HTTP 409 `IDEMPOTENCY_CONFLICT`. Identical replays successfully recover the existing `uploadId` and mint fresh presigned URLs without consuming new rate-limit slots.
4. **PostgreSQL Advisory Lock Atomic Rate Limiting:** Serializes concurrent requests for the same user via transaction-scoped `pg_advisory_xact_lock` using a 64-bit signed integer derived from the user identity, enforcing a strict ceiling of 30 new authorizations per rolling 60-second window. Automatic lock release on `COMMIT`/`ROLLBACK` eliminates lock leakage risks on crashes.
5. **Database Migration 0033 Safety:** Strictly additive schema creation (`media_upload_authorizations` and 2 indexes) with clean downgrade paths. Verified that shared development (`fansivibe`) and test (`fansivibe_test`) databases were untouched and remain at revision `0032`.
6. **Zero Phase 3 or Flutter Intrusion:** Verified that no Phase 3 logic (transcoding, Pillow decoding, upload completion, canonical promotion) and zero Flutter mobile code were touched.

Alongside these strengths, the audit identified **7 specific findings** (1 High, 1 Medium, 5 Low) regarding HMAC secret rotation key-ring resolution, advisory lock transaction hold times in concurrent duplicate retries, documentation vs. code namespace divergence, database clock vs. application clock drift, unbounded retention deletion, and test coverage gaps. None of these findings block the completion of Phase 2, but they represent concrete technical debt and operational risks that must be addressed prior to production traffic.

---

## 2. In-Depth Evaluation of the 12 Critical Areas

### 2.1 HMAC Fingerprint Generation and Historical-Key Retry Behavior
- **Fingerprint Construction:** `compute_canonical_request_fingerprint` binds strictly to non-volatile fields (`client_sha256`, `content_type`, `filename`, `purpose`, `size_bytes`, `user_id`). Volatile fields (timestamps, presigned URLs, nonces) are properly omitted.
- **Verification:** Inflight retries verify against the stored authorization's `key_version` column.
- **Key-Ring Defect (Finding 1 - High):** In `Settings.effective_media_upload_key_ring`, configuring `MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS` automatically hardcodes the key identifier in the dictionary as `"kver_previous"`. When an existing authorization created under an active key (e.g. `kver_1`) is retried after rotation, `_verify_existing_fingerprint` queries `self._key_ring.get(existing.key_version)` (which looks for `"kver_1"`). Because `"kver_1"` is not present in the ring, the lookup returns `None`, causing identical retries to fail with HTTP 409 `IDEMPOTENCY_CONFLICT`. (Workaround: configuring `MEDIA_UPLOAD_KEY_RING` with full JSON mappings avoids this bug).

### 2.2 Idempotency Under Concurrent Requests and Across Application Instances
- **Cross-Worker Synchronization:** By taking a transaction-scoped advisory lock before querying the rate limit and inserting the authorization, multiple Uvicorn workers and multi-host container instances are serialized per user.
- **Step 9 Double-Check:** When worker B unblocks after worker A commits, worker B queries `media_upload_authorizations` in step 9, detects the row committed by worker A (under PostgreSQL's default `READ COMMITTED` isolation level), validates the fingerprint, and returns the existing slot.
- **RFC 9440 Compliance:** Different parameters under the same idempotency key raise HTTP 409 `IDEMPOTENCY_CONFLICT` both on fast-path (step 5) and locked-path (step 9).

### 2.3 PostgreSQL Advisory-Lock Key Derivation and Transaction Boundaries
- **Key Derivation:** `get_media_upload_lock_key(user_id)` generates a signed 64-bit integer using `int.from_bytes(digest[:8], byteorder="big", signed=True)`. This maps directly to PostgreSQL `bigint` without overflow.
- **Namespace Discrepancy (Finding 3 - Low):** The implementation report states the lock key is derived from `"fansivibe:media_upload:" + str(user_id)`, but the actual codebase in `media.py` line 145 uses `"media_upload_rate_limit:" + str(user_id)`.
- **Transaction Hold Time in Duplicate Branch (Finding 2 - Medium):** In step 9, when an existing record is detected under the advisory lock, the code awaits `_storage.generate_presigned_put_url` and returns directly without committing or rolling back `self._db`. Consequently, the advisory lock remains held across the external network call to object storage until FastAPI's `get_db` teardown runs `db.close()`, causing unnecessary lock contention for the user.

### 2.4 Rolling 60-Second Rate-Limit Correctness
- **Rate Limit Ceiling:** Enforces `recent_count >= 30` over `created_at >= one_min_ago`.
- **Index Alignment:** The query leverages the composite index `ix_media_upload_authorizations_user_rate` on `(user_id, created_at)`.
- **Clock Source Drift (Finding 4 - Low):** The implementation report claims the window query uses PostgreSQL server time (`created_at >= NOW() - INTERVAL '60s'`). The actual implementation uses Python application time (`now = datetime.now(timezone.utc)` and `one_min_ago = now - timedelta(seconds=60)`). Across multi-worker or multi-host deployments, clock skew across application servers can lead to slight window calculation inconsistencies.

### 2.5 Retry-After Calculation and Lock-Timeout Behavior
- **Standard Headers:** HTTP 429 responses correctly set the `Retry-After` header via `register_error_handlers` in `errors.py`.
- **Ceiling Throttling:** Rejections due to exceeding 30 req/min return `Retry-After: 60`.
- **Contention Timeout:** Advisory lock timeout (`SET LOCAL lock_timeout = '3s'`) catches `OperationalError` and maps to HTTP 429 with `Retry-After: 5`.
- **Error String Matching (Finding 7 - Low):** The exception handler checks `if "lock_timeout" in error_str or "canceling statement due to lock timeout" in error_str:`. While functional, inspecting `exc.orig.pgcode == '55P03'` (PostgreSQL `lock_not_available`) would be more robust against localized error messages.

### 2.6 Presigned URL Signing Failure and Recovery
- **Ordering Guarantee:** The database transaction commits the authorization record (step 13) BEFORE calling `generate_presigned_put_url` (step 14).
- **Signing Failure Semantics:** If storage signing fails after the DB commit, the API raises HTTP 500 `STORAGE_SIGNING_ERROR` with `details: {"upload_id": "..."}`.
- **Client Recovery:** When the client retries with the same `Idempotency-Key` and parameters, step 4/6 recovers the persisted authorization and successfully mints a fresh presigned URL without consuming another rate-limit slot.

### 2.7 Expiration and Authorization-Record Pruning
- **Dual Expiration Design:** Presigned PUT URLs expire in 15 minutes (`expiresInSeconds: 900`). The database authorization record expires in 24 hours (`IDEMPOTENCY_RETENTION_HOURS = 24`) to ensure durable idempotency replays throughout the client upload lifecycle.
- **Unbounded Pruning (Finding 5 - Low):** `prune_expired_authorizations` issues an unbatched `DELETE FROM media_upload_authorizations WHERE expires_at < cutoff`. In high-throughput production environments, unbatched deletion of expired records can create large table locks and WAL spikes.

### 2.8 Migration 0033 Constraints, Indexes, Parent Revision, Upgrade and Downgrade
- **Lineage:** Single-head linear parentage (`0032 -> 0033`).
- **DDL Correctness:** Defines composite primary key `(user_id, idempotency_key)`, unique constraint `uq_media_upload_authorizations_upload_id` on `upload_id`, and foreign key `users(id) ON DELETE CASCADE`.
- **Indexes:** Includes `(user_id, created_at)` for sliding-window rate limit count queries and `(expires_at)` for pruning sweeps.
- **Downgrade:** Cleanly drops indexes and table in symmetric reverse order.
- **Shared DB Protection:** Confirmed via live query that neither `fansivibe` nor `fansivibe_test` was migrated; both remain strictly at revision `0032`.

### 2.9 OW-1 Ownership and Guest Isolation
- **Authentication Seam:** Mandatory `user_id = Depends(get_current_user_id)`. Rejects unauthenticated requests with HTTP 401.
- **Guest Restriction:** Guests have no access to `POST /v1/media/uploads`. Guest biometric/appearance data remains strictly excluded.
- **Staging Isolation:** Object storage key is strictly namespaced as `staging/users/{user_id}/wardrobe/{upload_id}.{ext}`.
- **Cross-User Idempotency:** The composite primary key namespaces `idempotency_key` per user. Different users submitting the identical idempotency key receive separate authorizations, separate upload IDs, and isolated staging keys.

### 2.10 Secret, Signature, and Presigned URL Leakage Through Logs or Errors
- **Settings Security:** `media_upload_hmac_secret`, `media_upload_hmac_secret_previous`, and `media_upload_key_ring` are declared with `repr=False` in `Settings`.
- **Error Sanitization:** `_sanitize_message` in `storage.py` and `_sanitize_log_message` in `errors.py` scrub AWS signatures, credentials, tokens, and database passwords from logs and responses.
- **Database Sanitization:** Presigned URLs and client secrets are never persisted in the database.

### 2.11 Compatibility with Existing Storage Abstraction
- **Port Conformance:** `AuthorizeMediaUpload` depends exclusively on the domain port `ObjectStoragePort`.
- **Adapter Conformance:** `CloudflareR2StorageAdapter` and `FakeStorageAdapter` implement all methods of `ObjectStoragePort`.
- **Dependency Injection:** Seamlessly resolved via FastAPI dependency `get_storage_adapter`.

### 2.12 Test Evidence Analysis Against Implementation Report Claims
- **Claimed 43 Tests:** 41 tests pass in default environments; 2 multi-session PostgreSQL concurrency tests require `FANSIVIBE_TEST_DATABASE_URL` and skip cleanly when unset.
- **Lock Contention Coverage (Finding 6 - Low):** The implementation report claims lock contention timeouts return HTTP 429 with `Retry-After: 5`, but `test_media_api.py` has no unit test asserting this code path.
- **Rotation Test Masking:** `test_key_rotation_preserves_inflight_retry` passed a manual dictionary `{"kver_1": ..., "kver_2": ...}`, masking the defect in `effective_media_upload_key_ring` where `MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS` defaults to `"kver_previous"`.

---

## 3. Detailed Audit Findings

### Finding 1: Historical Key Resolution Defect in `MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS`
- **Severity:** High
- **Exact File & Function:** `backend/app/config/settings.py` (`Settings.effective_media_upload_key_ring`, lines 273–286)
- **Technical Explanation:**  
  When an authorization is created, its active key identifier is stored in `media_upload_authorizations.key_version` (e.g. `"kver_1"`). During key rotation, if an operator configures:
  ```bash
  MEDIA_UPLOAD_ACTIVE_KEY_ID="kver_2"
  MEDIA_UPLOAD_HMAC_SECRET="<secret_2>"
  MEDIA_UPLOAD_HMAC_SECRET_PREVIOUS="<secret_1>"
  ```
  `Settings.effective_media_upload_key_ring` builds the key ring as:
  ```python
  if self.media_upload_hmac_secret_previous:
      prev_id = "kver_previous"
      if prev_id not in ring:
          ring[prev_id] = self.media_upload_hmac_secret_previous
  ```
  This maps the predecessor secret to `"kver_previous"` instead of its original key ID (`"kver_1"`). When a client retries an inflight upload originally signed under `"kver_1"`, `_verify_existing_fingerprint` executes `self._key_ring.get(existing.key_version)` (`ring.get("kver_1")`), which returns `None`. Consequently, verification fails, and the application raises an erroneous HTTP 409 `IDEMPOTENCY_CONFLICT`.
- **Reproduction / Test Evidence:**  
  In `backend/tests/test_media_api.py`, `test_key_rotation_preserves_inflight_retry` bypassed `effective_media_upload_key_ring` by manually passing `key_ring={"kver_1": ..., "kver_2": ...}` directly to the use case. If the test is updated to load `key_ring` via `Settings(media_upload_active_key_id="kver_2", media_upload_hmac_secret="...", media_upload_hmac_secret_previous="...").effective_media_upload_key_ring`, verification fails.
- **Recommended Correction:**  
  Add an optional configuration field `media_upload_previous_key_id: Optional[str] = Field(default=None, alias="MEDIA_UPLOAD_PREVIOUS_KEY_ID")` to `Settings`, and populate the ring using `prev_id = self.media_upload_previous_key_id or "kver_previous"`. Document that structured rotation should prefer `MEDIA_UPLOAD_KEY_RING='{"kver_1":"...","kver_2":"..."}'`.

---

### Finding 2: PostgreSQL Advisory Lock Held Across Asynchronous Storage Signing in Step 9
- **Severity:** Medium
- **Exact File & Function:** `backend/app/application/media.py` (`AuthorizeMediaUpload.execute`, lines 305–337)
- **Technical Explanation:**  
  In step 9, when a concurrent identical request unblocks after the primary request commits, it detects `locked_existing is not None`. After verifying the fingerprint, it calls:
  ```python
  upload_url = await self._storage.generate_presigned_put_url(...)
  return { ... }
  ```
  The code directly returns without committing or rolling back `self._db`. Because `pg_advisory_xact_lock` is transaction-scoped, the advisory lock remains held during the asynchronous network/thread call to object storage and until the entire FastAPI request finishes and triggers `db.close()`. In contrast, the new-authorization path (line 371) explicitly commits the transaction BEFORE calling `generate_presigned_put_url`.
- **Reproduction / Test Evidence:**  
  Code inspection of lines 305–337 reveals that no `self._db.commit()` or `self._db.rollback()` is issued before `await self._storage.generate_presigned_put_url(...)`.
- **Recommended Correction:**  
  Once `locked_existing` is retrieved and verified in step 9, immediately release the advisory lock by calling `self._db.rollback()` (or `self._db.commit()`) before awaiting `_storage.generate_presigned_put_url`.

---

### Finding 3: Advisory Lock Namespace Divergence Between Report and Implementation
- **Severity:** Low
- **Exact File & Function:** `backend/app/application/media.py` (`get_media_upload_lock_key`, line 145) vs `STAGE2_P0_4_PHASE2_IMPLEMENTATION_REPORT.md` (lines 20, 108)
- **Technical Explanation:**  
  The implementation report explicitly claims and documents in Section 1 and Section 6 that the advisory lock key is derived from:
  `hashlib.sha256(f"fansivibe:media_upload:{str(user_id)}".encode("utf-8"))`.
  However, line 145 of `backend/app/application/media.py` implements:
  `hashlib.sha256(f"media_upload_rate_limit:{user_id}".encode("utf-8"))`.
  While `"media_upload_rate_limit:"` is functionally unique and safe from internal lock collisions, the code does not match the documented namespace contract.
- **Reproduction / Test Evidence:**  
  Direct comparison between line 108 of `STAGE2_P0_4_PHASE2_IMPLEMENTATION_REPORT.md` and line 145 of `backend/app/application/media.py`.
- **Recommended Correction:**  
  Reconcile the namespace string in `get_media_upload_lock_key` to match the agreed standard or update the implementation report.

---

### Finding 4: Clock Source Drift in Rolling 60-Second Window Calculation
- **Severity:** Low
- **Exact File & Function:** `backend/app/application/media.py` (`AuthorizeMediaUpload.execute`, lines 340–346)
- **Technical Explanation:**  
  The implementation report states that rate limit window accounting is "Based on authoritative database timestamps (`created_at >= NOW() - INTERVAL '60s'`)". In the actual implementation, the window threshold is computed in Python using `now = datetime.now(timezone.utc)` and `one_min_ago = now - timedelta(seconds=60)`. In a distributed deployment with multiple container instances (e.g. `backend-primary` and `backend-canary`), any NTP clock skew between hosts will cause rate limits to evaluate against host-local clocks rather than the database server's central clock.
- **Reproduction / Test Evidence:**  
  Line 340 of `media.py`: `one_min_ago = now - timedelta(seconds=60)`.
- **Recommended Correction:**  
  When running against PostgreSQL (`is_postgres=True`), construct the filter using `MediaUploadAuthorization.created_at >= (func.now() - text("INTERVAL '60 seconds'"))`.

---

### Finding 5: Unbounded Retention Pruning Deletion
- **Severity:** Low
- **Exact File & Function:** `backend/app/application/media.py` (`prune_expired_authorizations`, lines 149–161)
- **Technical Explanation:**  
  `prune_expired_authorizations` executes an unbatched `DELETE FROM media_upload_authorizations WHERE expires_at < cutoff`. While advertised in report summaries as "bounded retention pruning", this query lacks a `LIMIT` or batch chunking loop. In high-traffic deployments with millions of accumulated records, running an unbatched delete will lock large index sections and generate heavy WAL spikes. (Compare with `backend/app/application/youtube_retention.py`, which implements bounded batch chunking).
- **Reproduction / Test Evidence:**  
  Line 155 of `media.py`: `stmt = delete(MediaUploadAuthorization).where(MediaUploadAuthorization.expires_at < cutoff)`.
- **Recommended Correction:**  
  Add `batch_size: int = 1000` and loop using a bounded subquery (`WHERE (user_id, idempotency_key) IN (SELECT user_id, idempotency_key ... LIMIT :batch_size)`) until `result.rowcount < batch_size`.

---

### Finding 6: Missing Unit Test Coverage for Lock Contention Timeout (`Retry-After: 5`)
- **Severity:** Low
- **Exact File & Function:** `backend/tests/test_media_api.py`
- **Technical Explanation:**  
  The implementation report documents that lock contention timeouts trigger HTTP 429 with `Retry-After: 5`. However, there is no unit test in `test_media_api.py` simulating or asserting this code path. Additionally, `get_media_upload_lock_key` is imported in `test_media_api.py` line 45 but never asserted in any test.
- **Reproduction / Test Evidence:**  
  Grep search across `backend/tests/test_media_api.py` reveals only one `Retry-After` assertion (for `60`), and zero tests provoking `OperationalError("canceling statement due to lock timeout")`.
- **Recommended Correction:**  
  Add a targeted unit test mocking `db.execute` raising `OperationalError("canceling statement due to lock timeout")` to assert that HTTP 429 is raised with `Retry-After: 5`.

---

### Finding 7: Fragile String Matching for PostgreSQL Lock Timeout
- **Severity:** Low
- **Exact File & Function:** `backend/app/application/media.py` (`AuthorizeMediaUpload.execute`, lines 376–377)
- **Technical Explanation:**  
  Lock timeout translation checks `if "lock_timeout" in error_str or "canceling statement due to lock timeout" in error_str:`. While functional in English-locale environments, PostgreSQL error messages localized via `LC_MESSAGES` will not match these English substrings, causing lock timeouts to be improperly classified as 500 `DATABASE_FAILURE`.
- **Reproduction / Test Evidence:**  
  Code inspection of lines 376–377 in `media.py`.
- **Recommended Correction:**  
  Inspect the underlying driver SQLSTATE code `55P03` (e.g. `getattr(exc.orig, 'sqlstate', None) == '55P03'` or `getattr(exc.orig, 'pgcode', None) == '55P03'`) before falling back to substring matching.

---

## 4. Final Review Verdict & Recommendation

### Verdict: **ACCEPTED WITH NON-BLOCKING FINDINGS**

### Justification:
The core architecture of Stage 2 P0-4 Phase 2 is sound, fully functional, and adheres to all security and system boundaries:
1. The upload authorization endpoint enforces strict Bearer JWT session resolution, OW-1 caller scoping, MIME/size limits, and input sanitization.
2. The durable PostgreSQL idempotency ledger satisfies RFC 9440 conflict detection and identical retry slot recovery.
3. PostgreSQL transaction-scoped advisory locking eliminates multi-worker TOCTOU concurrency race conditions for distributed rate limiting.
4. Presigned PUT URLs are short-lived, provider-neutral, and never persisted to the database.
5. Migration 0033 is strictly additive and clean, and shared databases were verified untouched at revision `0032`.
6. Phase 3, Flutter mobile code, and cloud provisioning were strictly excluded.

The findings identified in this review represent non-blocking edge cases, maintenance improvements, and configuration handling nuances. They do not prevent acceptance of the Phase 2 milestone, but should be addressed during subsequent deployment readiness hardening.
