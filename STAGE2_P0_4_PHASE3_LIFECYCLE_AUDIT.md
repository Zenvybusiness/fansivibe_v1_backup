# Fansivibe — Stage 2 P0-4 Phase 3
# Final Lifecycle Audit Before Phase 4
## Backend Upload Verification & Canonical Media Publication Audit Report

**Document Version:** 1.0.0 (FINAL LIFECYCLE AUDIT REPORT)  
**Date:** 2026-11-01  
**Target:** `STAGE2-P0-4-PHASE-3: Upload Verification & Canonical Media Publication`  
**Execution Boundary:** 100% Read-Only Technical Audit (Zero source files modified, zero migrations created/executed, zero shared databases touched, zero cloud calls made, zero Flutter files modified).

---

## 1. Executive Summary

This report presents a thorough, evidence-based technical audit of the completed **Phase 3 implementation** of Stage 2 P0-4 (`Wardrobe Photo Cloud Storage & Media Sync`) prior to authorizing Phase 4.

The audit examined the runtime contracts, transactional boundaries, fault tolerances, and lifecycle states across:
- [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py)
- [backend/app/infrastructure/db/models.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/db/models.py)
- [backend/app/workers/transcoder.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/workers/transcoder.py)
- [backend/app/domain/ports/storage.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/domain/ports/storage.py)
- [backend/app/infrastructure/external/storage.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/external/storage.py)
- [backend/app/api/routers/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/routers/media.py)
- [backend/app/api/schemas/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/schemas/media.py)
- [backend/alembic/versions/0033_media_upload_idempotency.py](file:///home/tony/projects/fansivibe_v1_backup/backend/alembic/versions/0033_media_upload_idempotency.py)
- [backend/alembic/versions/0034_media_upload_completion.py](file:///home/tony/projects/fansivibe_v1_backup/backend/alembic/versions/0034_media_upload_completion.py)
- [backend/tests/test_media_verification.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_verification.py)
- [backend/tests/test_media_api.py](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_api.py)

The core mechanics of Phase 3 (storage port extension, standalone child-process CLI transcoding with 256MB kernel limit, EXIF orientation correction, GPS/metadata stripping, Lanczos downscaling, WebP Q85 encoding, magic-byte inspection, SHA-256 verification, and OW-1 caller scoping) are structurally sound and verified. 

However, this lifecycle audit identified **critical architectural disconnects** between the ephemeral upload authorization ledger, the 24-hour retention pruning job, crash recovery ordering, and the future Phase 4 wardrobe item association model.

---

## 2. Answers to Critical Lifecycle Questions

### Question 1: After canonical publication, what durable database record identifies the media?
**Answer:**  
The **only** database record identifying the published media at the conclusion of Phase 3 is the row in `media_upload_authorizations` (`[models.py:L1657-1710](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/db/models.py#L1657-L1710)`), where `status = 'published'` and canonical metadata columns (`canonical_key`, `canonical_sha256`, `canonical_size_bytes`, `canonical_width`, `canonical_height`, `completed_at`) are populated by `CompleteMediaUpload._finalize_published_record` (`[media.py:L864-880](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L864-L880)`).

There is **no dedicated media entity table** (e.g. `media_assets` or `wardrobe_photos`). The media reference is not yet connected to any row in `wardrobe_items` because wardrobe item association occurs in a separate, subsequent API call (`POST /v1/wardrobe/items` or `PATCH /v1/wardrobe/items/{id}`) belonging to Phase 4.

---

### Question 2: Can that media still be recovered after the authorization row is pruned?
**Answer:**  
**NO.** If the authorization row is pruned before the client associates the media with a wardrobe item, the media **cannot be recovered** from the database.

**Evidence:**
In `[media.py:L186-204](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L186-L204)`, `prune_expired_authorizations` deletes rows where `expires_at < cutoff` without filtering by `status`:
```python
stmt = (
    select(MediaUploadAuthorization.upload_id)
    .where(MediaUploadAuthorization.expires_at < cutoff)
    .limit(batch_size)
)
```
When `_finalize_published_record` runs, it updates `status = 'published'` but **does not extend `expires_at`** (which was initialized to `created_at + 24 hours` in `[media.py:L476](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L476)`). Once 24 hours elapse, the pruning sweep permanently purges the `media_upload_authorizations` row.

Once pruned:
- `POST /v1/media/uploads/{upload_id}/complete` returns HTTP 404 `NOT_FOUND`.
- No database record links `upload_id` or `user_id` to `canonical_key`.
- The canonical WebP blob remains orphaned in Cloudflare R2 at `users/{user_id}/wardrobe/{upload_id}/{canonical_sha256}.webp` with zero database index.

*(Note: If the client already associated the media with a wardrobe item prior to pruning, the metadata is preserved within `wardrobe_items.image_ref` JSONB, but the underlying authorization record is gone).*

---

### Question 3: What happens if the application crashes after canonical R2 publication but before the database commit?
**Answer:**  
If the worker crashes immediately after Cloudflare R2 `put_object` (`[media.py:L821-830](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L821-L830)`) but before `self._db.commit()` in `_finalize_published_record` (`[media.py:L880](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L880)`):

1. **Database State:** The database row retains `status = 'processing'` (from Step 6, `[media.py:L646](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L646)`). Crucially, `canonical_key` and `canonical_sha256` are **NULL** in PostgreSQL because they are only written in Step 14.
2. **Storage State:** The canonical WebP object exists in R2 at `users/{user_id}/wardrobe/{upload_id}/{canonical_sha256}.webp`. The staging object in `staging/users/{user_id}/wardrobe/{upload_id}.{ext}` is **not deleted** (deletion occurs only after the DB commit at `[media.py:L893](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L893)`).
3. **Retry Behavior:** When the client retries `POST /v1/media/uploads/{upload_id}/complete`:
   - Step 7's crash recovery check (`[media.py:L651-666](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L651-L666)`) checks `if existing_canonical_key and existing_canonical_sha256:`. Because the database row still has `canonical_key = NULL`, **Step 7 evaluates to False and does not fire!**
   - The retry proceeds to Step 8: re-verifies staging metadata, re-downloads staging bytes, re-runs child process transcoding, and executes `put_object` to the exact same canonical key (overwriting it idempotently).
   - Step 14 commits `status = 'published'` and deletes the staging object.
   - **Conclusion:** The retry recovers successfully, but the intended Step 7 fast-path is bypassed due to uncommitted `canonical_key`.

---

### Question 4: What happens if the database commit succeeds but staging deletion fails?
**Answer:**  
The failure is **completely non-blocking**, and the published media remains **100% operational**.

**Evidence:**
In `[media.py:L891-896](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L891-L896)`:
```python
# Deterministic deletion of staging object (non-blocking on failure)
try:
    await self._storage.delete_object(staging_key)
except Exception as exc:
    logger.warning("Failed to delete staging object %s: %s", staging_key, exc)

return {
    "uploadId": upload_id,
    "objectKey": canonical_key,
    ...
    "status": "ready",
}
```
1. Staging deletion occurs strictly *after* `self._db.commit()`.
2. Any `delete_object` exception is caught, logged as a warning, and swallowed.
3. The endpoint returns HTTP 200 `PublishedMediaRefResponse`.
4. The abandoned staging object left in R2 is automatically purged after 24 hours by Cloudflare R2's prefix lifecycle rule targeting `staging/`.

---

### Question 5: Can an authenticated user associate a published media reference with the wrong wardrobe item?
**Answer:**  
**YES.** An authenticated user can associate a published media reference with *any* of their own wardrobe items, even if it contradicts the garment's metadata (e.g., associating a shoe photo with a shirt item), or associate the exact same media reference with multiple wardrobe items.

Furthermore, because `AddWardrobeItem` and `UpdateWardrobeItem` in `[wardrobe.py:L153-174, L249-281](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/wardrobe.py#L153-L174)` accept an untyped dictionary `image_ref: dict | None` without validating the contents against `media_upload_authorizations`, a user could technically supply an `imageRef` payload pointing to **another user's published `objectKey`** (`users/{other_user}/...`). 

While the other user's photo would fail to generate a presigned GET URL in Phase 8 (due to `OW-1` prefix validation in `get_media_url`), the database row in `wardrobe_items` would still accept and store the incorrect foreign reference.

---

### Question 6: Does the system independently validate ownership during future wardrobe association?
**Answer:**  
**NO. Not currently.**

**Evidence:**
Inspection of `backend/app/application/wardrobe.py` (`AddWardrobeItem` and `UpdateWardrobeItem`):
- `AddWardrobeItem.__call__` receives `image_ref: dict | None = None`. It validates `name` length, category/color/material vocabularies, but performs **zero validation** on `image_ref`.
- It directly passes `image_ref` to `WardrobeItemRepositorySQL.create()`, which stores it into `wardrobe_items.image_ref` JSONB (`[models.py:L456](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/db/models.py#L456)`).
- It does **not** check whether `image_ref["objectKey"]` begins with `users/{user_id}/`.
- It does **not** verify that `image_ref["uploadId"]` was granted to the caller.
- It does **not** verify that the upload has `status == 'published'`.

This validation is deferred to **Phase 4** in the project roadmap (`STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md` Phase 4), but constitutes a critical security prerequisite for Phase 4 implementation.

---

### Question 7: Can a published media reference survive application restart and authorization expiry?
**Answer:**  
**It depends on whether it has been associated with a wardrobe item:**

1. **If associated with a wardrobe item (`wardrobe_items.image_ref`):**
   - **Application Restart:** Survives completely (stored in persistent PostgreSQL `wardrobe_items` table).
   - **Authorization Expiry:** Survives completely. `wardrobe_items` has no foreign key constraint to `media_upload_authorizations`. When the authorization row is pruned after 24 hours, `wardrobe_items.image_ref` retains the canonical `objectKey`, `contentHash`, dimensions, and timestamp.
2. **If NOT yet associated with a wardrobe item (draft/in-flight):**
   - **Application Restart:** Survives (stored in `media_upload_authorizations`).
   - **Authorization Expiry:** **FAILS.** After 24 hours, `prune_expired_authorizations` deletes the row. The media reference is permanently lost from the database.

---

### Question 8: Are orphaned canonical objects discoverable and recoverable?
**Answer:**  
- **From Database:** **NO.** Once a `media_upload_authorizations` row is pruned or if a commit failed, the database has zero knowledge that the canonical object exists.
- **From Storage:** **PARTIALLY DISCOVERABLE, BUT UNRECOVERABLE BY APPLICATION.**
  Canonical objects are saved at:
  `users/{user_id}/wardrobe/{upload_id}/{canonical_sha256}.webp`
  Storage administrators can discover them using S3 `ListObjectsV2` under the `users/{user_id}/wardrobe/` prefix.
  However, the application currently possesses **no reconciliation job, background worker, or API** to match R2 objects against `wardrobe_items.image_ref`. Phase 13 ("Staging Cleanup & Orphan Reconciliation") is scheduled later in the roadmap. Until Phase 13 is built, unreferenced canonical objects remain dead storage.

---

### Question 9: Can repeated completion requests safely return the same stable media identity?
**Answer:**  
**YES, within the 24-hour authorization retention window.**

**Evidence:**
In `[media.py:L616-630](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L616-L630)`:
```python
# 4. Check if already PUBLISHED (Idempotent replay)
if auth.status == "published":
    published_res = {
        "uploadId": auth.upload_id,
        "objectKey": auth.canonical_key,
        "mediaType": "image/webp",
        "width": auth.canonical_width,
        "height": auth.canonical_height,
        "sizeBytes": auth.canonical_size_bytes,
        "contentHash": auth.canonical_sha256,
        "uploadedAt": auth.completed_at or now,
        "status": "ready",
    }
    self._db.rollback()
    return published_res
```
Subsequent requests within 24 hours take this immediate fast-path:
- Returns HTTP 200 with the identical `PublishedMediaRefResponse`.
- Does not re-read storage.
- Does not re-spawn child transcoder processes.
- Does not duplicate canonical keys or mutate the database.

*(After 24 hours, the request returns HTTP 410 `UPLOAD_EXPIRED`, or HTTP 404 `NOT_FOUND` once pruned).*

---

### Question 10: Does the current design require a separate durable media metadata table, or can the existing model safely support Phase 4?
**Answer:**  
The existing model (`media_upload_authorizations` + `wardrobe_items.image_ref` JSONB) **can safely support Phase 4 without an additional table**, **PROVIDED THAT** the lifecycle flaws in `prune_expired_authorizations` and `CompleteMediaUpload` are resolved.

#### Evaluation of Options:

| Architecture Option | Schema Changes | Pros | Cons / Risks |
| :--- | :--- | :--- | :--- |
| **Option A: Existing Model (`image_ref` JSONB)** *(Recommended)* | Zero new tables (preserve Migration 0034) | 100% aligned with DEC-004 and Phase 4 spec; zero JOIN overhead on wardrobe item fetch; PR-8 database invariant preserved; minimal code changes. | Requires fixing `prune_expired_authorizations` to prevent deleting published rows before association; requires Phase 4 to strictly validate `image_ref` ownership against `media_upload_authorizations`. |
| **Option B: Separate Durable Table (`media_assets`)** | New table + Alembic migration | Fully decouples upload authorization from durable asset inventory; enables relational foreign keys from wardrobe items; clean reconciliation. | Violates zero-migration rule before release; requires foreign key migrations on `wardrobe_items`; adds join complexity and migration risk to Phase 4. |

**Conclusion on Model:**  
A separate durable table is **not strictly required** if Option A is hardened. Option A is the approved architectural path in `STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md`.

---

## 3. Detailed Audit Findings

```
[Phase 3 Lifecycle Audit Findings]
├── Finding 1: Published Records Destroyed by 24h Authorization Pruning  [HIGH]
├── Finding 2: False Crash Recovery Fast-Path in CompleteMediaUpload     [MEDIUM]
├── Finding 3: Premature Advisory Lock Release Exposes Active Processing [MEDIUM]
├── Finding 4: Wardrobe Association Lacks Ownership & Status Validation  [MEDIUM]
├── Finding 5: Permanent Lockout After 5 Worker Crashes (409 Conflict)   [LOW]
└── Finding 6: Orphaned Canonical Blobs Accumulate Without Reconciliation [LOW]
```

---

### Finding 1: Published Records Destroyed by 24-Hour Authorization Pruning
- **Severity:** **HIGH**
- **Exact File and Function:**  
  [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py) in `prune_expired_authorizations` (lines 186–215) and `_finalize_published_record` (lines 863–880).
- **Evidence:**  
  In `prune_expired_authorizations`:
  ```python
  stmt = (
      select(MediaUploadAuthorization.upload_id)
      .where(MediaUploadAuthorization.expires_at < cutoff)
      .limit(batch_size)
  )
  batch_ids = list(db.execute(stmt).scalars().all())
  del_stmt = delete(MediaUploadAuthorization).where(
      MediaUploadAuthorization.upload_id.in_(batch_ids)
  )
  ```
  `expires_at` is set to `now + 24 hours` when the row is created. When the upload completes and is published, `_finalize_published_record` sets `status = 'published'` but leaves `expires_at` unchanged.
- **Failure Scenario:**  
  A user completes an upload in the mobile app. The media is transcoded and published to R2. The mobile client holds the `PublishedMediaRefResponse`. If the user does not finalize adding the wardrobe item within 24 hours (e.g. app in background, offline drafting, battery died), the pruning job deletes the `media_upload_authorizations` row. When the client finally submits `POST /v1/wardrobe/items`, validation against the authorization table fails (404), and the canonical object in R2 is permanently orphaned.
- **Recommended Correction:**  
  Update `prune_expired_authorizations` to filter strictly on non-published authorizations:
  ```python
  stmt = (
      select(MediaUploadAuthorization.upload_id)
      .where(
          MediaUploadAuthorization.expires_at < cutoff,
          MediaUploadAuthorization.status.in_(["authorized", "failed", "expired"]),
      )
      .limit(batch_size)
  )
  ```
  For `published` authorizations, retain them until linked to a wardrobe item or allow a 7-day retention grace period.

---

### Finding 2: False Crash Recovery Fast-Path in CompleteMediaUpload
- **Severity:** **MEDIUM**
- **Exact File and Function:**  
  [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py) in `CompleteMediaUpload.execute` (lines 644–666 and 818–849).
- **Evidence:**  
  Step 7 attempts crash recovery:
  ```python
  existing_canonical_key = auth.canonical_key
  existing_canonical_sha256 = auth.canonical_sha256
  if existing_canonical_key and existing_canonical_sha256:
      canonical_meta = await self._storage.get_object_metadata(existing_canonical_key)
      if canonical_meta is not None:
          return await self._finalize_published_record(...)
  ```
  However, `auth.canonical_key` and `auth.canonical_sha256` are only written to the database inside `_finalize_published_record` (Step 14). If the server crashes between Step 13 (`put_object`) and Step 14 (`self._db.commit`), `auth.canonical_key` in the database is `NULL`.
- **Failure Scenario:**  
  On crash after R2 `put_object`, retry fails the `if existing_canonical_key:` check. The retry redundantly re-downloads the staging image, re-transcodes it, and re-uploads to R2. While the deterministic key ensures eventual consistency, the fast-path recovery is bypassed.
- **Recommended Correction:**  
  Compute `canonical_key` deterministically in memory and persist it along with `status = 'processing'` in Step 6 prior to calling R2 `put_object`, OR compute the expected key in Step 7 and check `storage.get_object_metadata`.

---

### Finding 3: Premature Advisory Lock Release Exposes Active Processing Window to Race Conditions
- **Severity:** **MEDIUM**
- **Exact File and Function:**  
  [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py) in `CompleteMediaUpload.execute` (lines 633–648).
- **Evidence:**  
  In Step 6, `self._db.commit()` commits `status = "processing"` and releases the transaction-scoped advisory lock (`pg_advisory_xact_lock`) before initiating R2 network I/O and child-process transcoding.  
  Step 5 only raises `409 CONFLICT` if `auth.processing_attempts >= 5`:
  ```python
  if auth.status == "processing" and auth.processing_attempts >= 5:
      raise ApiError(status_code=409, code="CONFLICT", ...)
  ```
- **Failure Scenario:**  
  If a client sends duplicate concurrent `/complete` requests (e.g. rapid double tap or network retry), Request 1 commits Step 6 and starts transcoding (which takes ~630ms). Request 2 arrives 50ms later, acquires the advisory lock, sees `status == 'processing'` and `attempts == 1` ($< 5$), and also proceeds to Step 6. Both requests spawn concurrent child transcoder processes, consuming double the server memory and racing to write to R2.
- **Recommended Correction:**  
  In Step 5, if `auth.status == "processing"`, check whether `auth.processing_started_at` was within the last 15 seconds. If so, return HTTP 409 `CONFLICT` ("Upload is actively being processed by another worker") or hold a session-level advisory lock (`pg_advisory_lock`) across the operation with safe release in a `finally:` block.

---

### Finding 4: Wardrobe Association Lacks Ownership & Publication Validation (Phase 4 Blocker)
- **Severity:** **MEDIUM (Phase 4 Implementation Gate)**
- **Exact File and Function:**  
  [backend/app/application/wardrobe.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/wardrobe.py) in `AddWardrobeItem.__call__` (lines 153–174) and `UpdateWardrobeItem.__call__` (lines 249–281); [backend/app/api/schemas/wardrobe.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/schemas/wardrobe.py) (lines 24, 41).
- **Evidence:**  
  `AddWardrobeItem` and `UpdateWardrobeItem` accept `image_ref: dict | None` without verifying:
  1. That `image_ref["objectKey"]` begins with `users/{user_id}/wardrobe/`.
  2. That the `uploadId` is valid, published, and owned by `user_id`.
  3. That the payload conforms to `PublishedMediaRefResponse`.
- **Failure Scenario:**  
  A caller can attach arbitrary unvalidated JSON or another user's `objectKey` to their wardrobe item. While Phase 8 media URL signing may prevent downloading foreign images, the wardrobe item record is corrupted in the database.
- **Recommended Correction:**  
  As the very first step of Phase 4, introduce a `validate_media_ref_ownership` domain check in `AddWardrobeItem` and `UpdateWardrobeItem` that validates the `imageRef` payload against `media_upload_authorizations` (`WHERE user_id = :user_id AND upload_id = :upload_id AND status = 'published'`).

---

### Finding 5: Permanent Lockout After 5 Processing Failures Without Retry Reset
- **Severity:** **LOW**
- **Exact File and Function:**  
  [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py) in `CompleteMediaUpload.execute` (lines 633–639) and `_record_retryable_status` (lines 921–930).
- **Evidence:**  
  If worker processes crash due to host-level issues (container restart, power cut, out-of-band SIGKILL), `_record_retryable_status` is never invoked. `status` remains `'processing'`. Each user retry increments `processing_attempts`. Once `processing_attempts` hits 5, line 633 permanently blocks the user with HTTP 409 `CONFLICT`.
- **Failure Scenario:**  
  A user encountering transient infrastructure crashes during upload completion is permanently locked out after 5 attempts and cannot publish their wardrobe image.
- **Recommended Correction:**  
  Add a timestamp check: if `status == 'processing'` and the attempt occurred $> 60$ seconds ago, permit the retry and log a warning.

---

### Finding 6: Orphaned Canonical Blobs Accumulate Without Storage Reconciliation
- **Severity:** **LOW**
- **Exact File and Function:**  
  Cloudflare R2 storage bucket layout and [backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py).
- **Evidence:**  
  Cloudflare R2 lifecycle rules automatically delete `staging/` prefix objects after 24 hours. However, canonical objects under `users/` have no expiration rule (as they are production assets). If an upload completes but is never attached to a wardrobe item, the canonical WebP sits in R2 indefinitely.
- **Failure Scenario:**  
  Abandoned client uploads gradually cause storage bloat and billing cost without any mechanism to discover or delete them.
- **Recommended Correction:**  
  Ensure Phase 13 ("Staging Cleanup & Orphan Reconciliation") is scheduled prior to public production release, scanning R2 objects against `wardrobe_items.image_ref`.

---

## 4. Lifecycle Audit Summary Table

| Finding ID | Dimension | Severity | Target File & Function | Status / Gate Impact |
| :--- | :--- | :--- | :--- | :--- |
| **F-01** | Authorization Retention Pruning | **HIGH** | `app/application/media.py`: `prune_expired_authorizations` | **BLOCKING FOR PHASE 4** (Destroys published records) |
| **F-02** | Crash Recovery Ordering | **MEDIUM** | `app/application/media.py`: `CompleteMediaUpload.execute` | Non-blocking (Idempotent re-transcode succeeds) |
| **F-03** | Concurrency Advisory Lock | **MEDIUM** | `app/application/media.py`: `CompleteMediaUpload.execute` | Non-blocking (Mitigated by worker semaphore=1) |
| **F-04** | Wardrobe Media Association | **MEDIUM** | `app/application/wardrobe.py`: `AddWardrobeItem` | **PREREQUISITE FOR PHASE 4** |
| **F-05** | Attempt Counter Lockout | **LOW** | `app/application/media.py`: `CompleteMediaUpload.execute` | Non-blocking |
| **F-06** | Orphaned R2 Reconciliation | **LOW** | Cloudflare R2 / Lifecycle | Non-blocking (Phase 13 scope) |

---

## 5. Audit Conclusion

Based on the evidence from active code, schema definitions, test suites, and database lifecycle tracing:

### **CORRECTIONS REQUIRED**

#### Specific Conditions to Clear Before Starting Phase 4:

1. **Fix `prune_expired_authorizations` (Finding F-01):**  
   Update `prune_expired_authorizations` in `[backend/app/application/media.py](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py)` so that it does **NOT** prune rows with `status = 'published'`, ensuring published completion records remain durable and available for Phase 4 wardrobe item association.
2. **Phase 4 Specification Requirement (Finding F-04):**  
   Formally mandate that Phase 4 (`AddWardrobeItem` and `UpdateWardrobeItem`) include independent ownership validation verifying that `image_ref["uploadId"]` exists, is owned by `user_id`, and has `status == 'published'`.

Once these corrections are acknowledged and planned, the Phase 3 backend upload verification and publication subsystem is structurally ready to support Phase 4.
