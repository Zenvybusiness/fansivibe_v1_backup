# Fansivibe — Stage 2 P0-4 Phase 3.1
# Final Canonical Crash Recovery and Integrity Audit

- **Date:** 2026-11-01
- **Target:** Stage 2 P0-4 Phase 3.1 Canonical Crash Recovery (`backend/app/application/media.py:740-821`, `backend/tests/test_media_lifecycle_remediation.py:328-546`)
- **Audit Type:** Read-Only Technical Architecture & Recovery Integrity Audit
- **Status:** **CORRECTIONS REQUIRED**

---

### Executive Summary

A comprehensive, read-only implementation audit of the Stage 2 P0-4 Phase 3.1 canonical crash-recovery path (Finding F-02 remediation) was performed. The audit analyzed the crash-recovery mechanism invoked when canonical R2 publication succeeds but the subsequent PostgreSQL database commit fails.

Phase 3.1 successfully eliminated the original defect where a `NULL` `canonical_key` in PostgreSQL prevented crash recovery on retry. It implemented deterministic server-side canonical key derivation (`users/{user_id}/wardrobe/{upload_id}/canonical.webp`), zero-trust magic byte validation, and reuse of existing canonical objects without re-transcoding.

However, deep code and failure-mode analysis revealed **several recovery integrity and validation vulnerabilities**:

1. **Unconditional Hash Acceptance When Metadata Is Missing:** When recovering an uncommitted upload, `auth.canonical_sha256` in the database is `NULL`. The implementation compares the actual canonical SHA-256 against `canonical_meta.custom_metadata.get("sha256")`. If R2 metadata is missing, stripped, or unsupported, `sha_matches` is initialized to `True` ([line 771](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L771)). Consequently, any WebP file present at the key is adopted without independent cryptographic verification.
2. **Bypass of Client Assertion and Staging Validation:** The crash-recovery check (Step 7) runs **before** staging object inspection (Step 8) and client-asserted SHA-256 verification (Step 10). If a client supplies `client_assertion_sha256` in `UploadCompleteRequest`, Step 7 completely ignores it. If an orphaned or stale canonical object exists, the service adopts it and silently deletes the staging object without verifying that the staging payload was authentic or consistent.
3. **Unsafe Fallback Dimensions on Corrupt WebP:** If PIL fails to decode dimensions from the canonical bytes during recovery (`Image.open` throws an exception), the code falls back to hardcoded dimensions `1920, 1440` ([line 791](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L791)) and proceeds to publish the record, rather than rejecting the corrupt object and falling back to re-transcoding.
4. **Stale Worker Commits During Recovery:** Recovery adopts the canonical object and calls `_finalize_published_record`, which lacks lease ownership fencing. If the recovery attempt took longer than 15 seconds, a stale worker can finalize the publication even if another worker has taken over.

**Audit Recommendation:** **CORRECTIONS REQUIRED**.

---

### Section 1: Detailed Code Path Tracing of Crash Recovery

The crash-recovery workflow executes in [CompleteMediaUpload.execute](file:///home/tony/projects/fansivibe_v1_backup/backend/app/application/media.py#L740-L821) immediately following lease acquisition:

```
[Lease Acquired & Committed]
             │
             ▼
[Step 7: Crash Recovery Check]
  1. Key Derivation:
     expected_canonical_key = auth.canonical_key or get_canonical_object_key(user_id, upload_id)
     (users/{user_id}/wardrobe/{upload_id}/canonical.webp)
             │
  2. Storage Metadata Inspection:
     canonical_meta = await storage.get_object_metadata(expected_canonical_key)
     If canonical_meta is None -> Fall through to Step 8 (Fresh Transcoding)
             │
  3. Ownership & Bounds Validation:
     - is_owner_match = expected_canonical_key.startswith("users/{user_id}/wardrobe/{upload_id}/")
     - meta_user == str(user_id) (if meta_user present)
     - meta_upload == str(upload_id) (if meta_upload present)
     - is_type_valid = (canonical_meta.content_type == "image/webp")
     - is_size_valid = (0 < canonical_meta.size_bytes <= 2MB)
     If not valid -> Log warning & Fall through to Step 8
             │
  4. Byte Stream & Hash Verification:
     canonical_bytes = await storage.read_object(expected_canonical_key, max_bytes=2MB)
     actual_canonical_sha256 = sha256(canonical_bytes).hexdigest()
     is_valid_webp = (len >= 12 and bytes[:4] == b"RIFF" and bytes[8:12] == b"WEBP")
     sha_matches = True
     if meta_sha256:
         sha_matches = compare_digest(actual_canonical_sha256, meta_sha256)
     elif auth.canonical_sha256:
         sha_matches = compare_digest(actual_canonical_sha256, auth.canonical_sha256)
             │
  5. Dimension Extraction:
     width = auth.canonical_width, height = auth.canonical_height
     If not (width and height):
         Try Image.open(BytesIO(canonical_bytes)).size
         Except Exception -> width, height = 1920, 1440  <-- BUG: Unsafe fallback!
             │
  6. Finalize Publication & Early Return:
     await _finalize_published_record(...)
     - UPDATE media_upload_authorizations SET status='published', canonical_key=..., canonical_sha256=...
     - delete_object(staging_key)
     - return ready response
     (BYPASSES Steps 8-13 entirely!)
```

---

### Section 2: Verification of Recovery Integrity Criteria

#### 2.1 Exact Deterministic Object Key Derivation
- **Implementation:** `get_canonical_object_key(user_id: UUID, upload_id: UUID) -> str`
  `return f"users/{str(user_id)}/wardrobe/{str(upload_id)}/canonical.webp"`
- **Analysis:**
  - Evaluated at line 742: `auth.canonical_key or get_canonical_object_key(user_id, upload_id)`.
  - The derivation is strictly deterministic.
  - Derived solely from authenticated caller (`user_id` from JWT session) and route parameter `upload_id` (verified under OW-1 in step 2: `user_id == user_id, upload_id == upload_id`).
  - Never influenced by client request bodies or custom headers.
- **Verdict:** **PASS (Sound)**.

#### 2.2 Authenticated User and Upload Ownership Checks
- **Implementation:**
  - Key path prefix check: `expected_canonical_key.startswith(f"users/{str(user_id)}/wardrobe/{str(upload_id)}/")`
  - Custom metadata inspection:
    `if meta_user is not None and meta_user != str(user_id): is_owner_match = False`
    `if meta_upload is not None and meta_upload != str(upload_id): is_owner_match = False`
- **Analysis:**
  - Guarantees canonical objects residing in foreign user directories cannot be adopted.
  - Tested in `test_crash_recovery_rejects_unrelated_foreign_canonical_object` ([test lines 458-495](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation.py#L458-L495)).
- **Verdict:** **PASS (Sound)**.

#### 2.3 Actual Canonical Object Byte Verification
- **Implementation:**
  - Reads actual object bytes: `canonical_bytes = await self._storage.read_object(expected_canonical_key, max_bytes=2 * 1024 * 1024)`.
  - Magic byte verification: `is_valid_webp = (len(canonical_bytes) >= 12 and canonical_bytes[:4] == b"RIFF" and canonical_bytes[8:12] == b"WEBP")`.
- **Analysis:**
  - Accurately rejects empty objects, HTML error pages, and corrupted byte streams.
  - Tested in `test_crash_recovery_rejects_corrupted_canonical_bytes_and_falls_back` ([test lines 412-456](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation.py#L412-L456)).
- **Verdict:** **PASS (Sound)**.

#### 2.4 SHA-256 Comparison Against Independent Server Evidence
- **Implementation:**
  ```python
  actual_canonical_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
  sha_matches = True
  if meta_sha256:
      sha_matches = hmac.compare_digest(
          actual_canonical_sha256.lower(), meta_sha256.strip().lower()
      )
  elif auth.canonical_sha256:
      sha_matches = hmac.compare_digest(
          actual_canonical_sha256.lower(), auth.canonical_sha256.strip().lower()
      )
  ```
- **Critical Flaw:**
  1. In a genuine crash recovery (DB commit failed on attempt 1), `auth.canonical_sha256` in PostgreSQL is `NULL`.
  2. The only comparison target is `meta_sha256` from R2 object metadata.
  3. If R2 metadata is missing, stripped, or omitted by the storage client, `meta_sha256` is `None`.
  4. `sha_matches` remains `True`!
  5. The check `if (is_valid_webp or sha_matches) and sha_matches:` evaluates to `True`.
  6. The system adopts the object **without any cryptographic verification against independent server evidence**.
- **Evidence Classification:**
  - **Client Assertions:** Ignored during Step 7.
  - **Persisted Authorization Data:** `auth.canonical_sha256` is `NULL` during recovery.
  - **Server-Side Evidence:** Storage metadata is self-attested by the storage object itself, not independent of the storage layer.
- **Verdict:** **FAIL (Vulnerability R-01)**.

#### 2.5 Behavior When Staging and Canonical Objects Disagree
- **Implementation:**
  - Step 7 executes at lines 740-808.
  - Step 8 (staging metadata inspection) and Step 10 (client assertion check) are located at lines 823-897.
  - If Step 7 successfully adopts the canonical object, it **immediately returns** at line 808.
- **Analysis of Discrepancies:**
  - If a user uploaded a new staging image, or if the staging object in R2 was modified, Step 7 does not inspect the staging object.
  - If the client included `client_assertion_sha256` in the `POST /complete` request body to verify their upload, Step 7 completely skips client assertion verification.
  - The canonical object is adopted and the staging object is deleted (`delete_object(staging_key)`) without ever confirming that the canonical object actually matches the staging object's contents or the caller's asserted checksum.
- **Verdict:** **FAIL (Vulnerability R-02)**.

#### 2.6 Dimension Extraction and Malformed WebP Handling
- **Implementation:**
  ```python
  width = auth.canonical_width
  height = auth.canonical_height
  if not (width and height):
      try:
          import io
          from PIL import Image
          with Image.open(io.BytesIO(canonical_bytes)) as img:
              width, height = img.size
      except Exception:
          width, height = 1920, 1440
  ```
- **Critical Flaw:**
  - If a file starts with `RIFF...WEBP` but has truncated or malformed chunks, PIL `Image.open` raises `UnidentifiedImageError` or `IOError`.
  - Instead of rejecting the corrupt object and falling back to re-transcoding the staging object, the `except Exception:` block silently catches the error and assigns fake dimensions `width = 1920, height = 1440`.
  - The corrupt WebP is then committed to PostgreSQL as `status = "published"` with invalid metadata.
- **Verdict:** **FAIL (Vulnerability R-03)**.

---

### Section 3: Test Coverage Gap Analysis

| Scenario | Tested in Existing Suite? | Existing Test Reference | Coverage Status & Deficiencies |
| :--- | :--- | :--- | :--- |
| **Publication succeeds, DB fails, clean recovery** | **YES** | `test_canonical_publication_succeeds_but_db_commit_fails_recovery` ([line 335](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation.py#L335)) | Accurately proves that transcoder is not re-invoked when canonical object is valid. |
| **Corrupted canonical bytes reject and fallback** | **YES** | `test_crash_recovery_rejects_corrupted_canonical_bytes_and_falls_back` ([line 412](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation.py#L412)) | Proves corrupt bytes trigger fallback to re-transcode. |
| **Foreign canonical object rejection** | **YES** | `test_crash_recovery_rejects_unrelated_foreign_canonical_object` ([line 458](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation.py#L458)) | Proves foreign `user_id` metadata triggers fallback. |
| **Canonical does not exist** | **YES** | `test_crash_recovery_when_canonical_object_does_not_exist` ([line 497](file:///home/tony/projects/fansivibe_v1_backup/backend/tests/test_media_lifecycle_remediation.py#L497)) | Standard fallback verified. |
| **Missing / untrusted R2 metadata** | **NO** | None | **Zero coverage.** Tests always inject `custom_metadata` with `"sha256"`. Behavior with empty metadata is untested. |
| **Staging missing or inconsistent** | **NO** | None | **Zero coverage.** Tests always populate staging object with valid JPEG bytes before testing canonical recovery. |
| **Client assertion provided on recovery retry** | **NO** | None | **Zero coverage.** Tests invoke `execute(user_id, upload_id)` without `client_assertion_sha256`. |
| **PIL Image.open failure on malformed WebP** | **NO** | None | **Zero coverage.** Fallback to `1920, 1440` is completely untested. |

---

### Section 4: Findings Matrix

| Finding ID | Severity | Affected Code Path | Concrete Evidence | Production Impact | Recommended Correction |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **R-01** | **HIGH** | `backend/app/application/media.py:771-780` | `sha_matches = True` is initialized as default. If `meta_sha256` is `None` and `auth.canonical_sha256` is `None`, `sha_matches` remains `True`. | If R2 custom metadata is stripped or missing, any WebP file at that path is adopted without cryptographic hash verification. | Fail-closed: require `meta_sha256` or `auth.canonical_sha256`. If neither is present, do not adopt; fall back to safe re-transcoding. |
| **R-02** | **HIGH** | `backend/app/application/media.py:740-808` | Step 7 adopts canonical object and returns before Step 10 checks `client_assertion_sha256`. | If a caller provides a checksum assertion, the service can adopt a stale/mismatched canonical object and delete staging without verification. | Validate `client_assertion_sha256` against staging/canonical metadata before completing recovery in Step 7. |
| **R-03** | **MEDIUM** | `backend/app/application/media.py:785-792` | `except Exception: width, height = 1920, 1440` catches PIL decode failures and fabricates dimensions. | Corrupted WebP objects that pass the 12-byte header check are marked published with fake dimensions instead of falling back to clean transcoding. | If `Image.open` fails during recovery, log a warning and fall back to fresh transcoding of the staging object. |
| **R-04** | **MEDIUM** | `backend/app/application/media.py:797-806` | Step 7 calls `_finalize_published_record` without fencing on lease ownership token. | A slow recovery process can commit after its lease has expired, colliding with a concurrent worker. | Pass the active `lease_token` to `_finalize_published_record` and enforce conditional update on ownership. |

---

### Section 5: Audit Recommendation

**CORRECTIONS REQUIRED**

Phase 3.1 canonical crash recovery significantly improves upon Phase 3.0 by deterministically generating canonical paths and reusing valid canonical objects. However, because it fails open when R2 metadata is missing (`sha_matches = True`), bypasses client-asserted checksum validation, and assigns dummy dimensions on corrupt images, it cannot be accepted without targeted corrections (R-01 through R-04).
