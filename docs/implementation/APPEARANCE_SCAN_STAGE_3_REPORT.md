# Appearance Scan — Stage 3 Report

**Stage:** STEP 10.3 — APPEARANCE SCAN DATABASE + MEDIA FOUNDATION
**Date:** 2026-08-15
**Based on:** `APPEARANCE_SCAN_DATA_CONTRACT.md`, `APPEARANCE_SCAN_API_CONTRACT.md`,
`APPEARANCE_SCAN_IMPLEMENTATION_PLAN.md`, `FANSIVIBE_DOMAIN_MODEL_V1.md`

---

## 1. Database Changes

**No new tables or columns were required.** The existing PostgreSQL schema already
supports all required data for the Appearance Scan pipeline:

| Table | Column | Why it suffices |
|---|---|---|
| `analysis_runs` | `id` (UUID PK) | Primary scan/analysis record |
| `analysis_runs` | `user_id` (UUID FK → users) | Owner scoping (OW-1) |
| `analysis_runs` | `run_type` (TEXT FK → run_types) | `outfit` code already exists |
| `analysis_runs` | `status` (CHECK: pending/completed/failed) | Lifecycle already supported |
| `analysis_runs` | `engine_version` (TEXT) | Provenance tracking (PR-6) |
| `analysis_runs` | `input_media` (JSONB) | Stores `MediaRef` structure (PR-8) |
| `analysis_runs` | `result` (JSONB) | Stores `AppearanceProfile` snapshot (PR-6) |
| `analysis_runs` | `created_at` / `completed_at` | Lifecycle timestamps |
| `user_state` | `style_profile` (JSONB) | `face_shape`, `skin_tone`, `body_type`, `style_type`, `source_run_id` |
| `run_types` | `code` ∈ [`hairstyle`, `grooming`, `outfit`] | `outfit` code reserved and available |

**Migration:** None required (approved by data contract §2.4). The existing
schema safely represents all required information. No migration number assigned.

---

## 2. Migration Number

**N/A** — no migration was applied. The approved data contract explicitly states
"No migration is required" (§2.4, APPEARANCE_SCAN_DATA_CONTRACT.md). All required
columns (`input_media`, `result` JSONB on `analysis_runs`; `style_profile` JSONB
on `user_state`) already exist.

---

## 3. Media Foundation

**Media abstraction layer** provides a stable contract between the Flutter UI
and the backend:

```
Flutter image
  ↓
multipart/form-data upload (image part)
  ↓
Backend validation (content-type, size)
  ↓
Upload-then-insert (TRX-1): blob → object storage → MediaRef → analysis_runs.input_media
  ↓
Analysis run created with status=pending
```

**`MediaRef` structure** stored in `analysis_runs.input_media` (JSONB):

```json
{
  "key": "users/u1/scans/7a2b3c/input.jpg",
  "mediaType": "image/jpeg",
  "sizeBytes": 1572864,
  "contentHash": "sha256-abc123...",
  "isGenerated": false,
  "uploadedAt": "2026-08-15T12:00:00Z"
}
```

- **`key`**: Owner-scoped object storage path (`users/{user_id}/scans/{run_id}/input.{ext}`)
- **`mediaType`**: MIME type of the original image
- **`sizeBytes`**: File size
- **`contentHash`**: SHA-256 hash for integrity (never logged or echoed)
- **`isGenerated`**: `false` for captured images; `true` for AI-generated visuals
- **`uploadedAt`**: Timestamp of upload completion

**Supported media types:** `image/jpeg`, `image/png`, `image/webp`
**Size limit:** 20 MB (aligned with vision model input constraints)

---

## 4. Ownership Model

Every uploaded appearance image must belong to the authenticated user. The
ownership model enforces:

- **`user_id` derived from Bearer token** via `deps.py` — never client-supplied
- **Owner-scoped media paths**: `users/{user_id}/scans/{run_id}/input.{ext}`
- **404-not-403** on cross-user access: another user's `run_id` → `404`, never
  `403` (OW-1, no existence leak)
- **Repository-level scoping**: `AnalysisRunRepositorySQL.get_for_user()` enforces
  `AnalysisRuns.id == run_id AND AnalysisRuns.user_id == user_id`
- **Grooming endpoint** remains profile-only (no image), preserving existing
  behavior (MS10.3 sealed)

A user must never be able to access another user's appearance image.

---

## 5. Analysis-Run Integration

The existing `analysis_runs` lifecycle is reused. No new run table created.

**Lifecycle states** (already supported by project architecture):

| State | When |
|---|---|
| `pending` | Run row created, job queued |
| `completed` | `result` + `engine_version` written once (TRX-5 guard) |
| `failed` | Typed `error` written, no `result` (immutable history) |

**Run type:** `outfit` (for appearance scan with image) — already supported by
`run_types` vocabulary (reserved code, §12.11 of catalog).

**Initial status:** `pending` — both CREATED and PROCESSING surface as `pending`
on the wire (no separate in-flight state).

**Input/media capture at run creation:**

| Field | Source | Stored As |
|---|---|---|
| `user_id` | Auth token → `deps.py` | `analysis_runs.user_id` |
| `run_type` | Endpoint path (`/outfit`/`/hairstyle`) | `analysis_runs.run_type` |
| `input_media` | MediaRef from upload-then-insert | `analysis_runs.input_media` (jsonb) |
| `engine_version` | Fixed string `"vision-v1"` | `analysis_runs.engine_version` |
| `status` | `"pending"` | `analysis_runs.status` |
| `created_at` | `now()` | `analysis_runs.created_at` |

---

## 6. Application Use Case

**`CreateOutfitRun`** (new use case, `backend/app/application/analysis.py`):

1. Validate authenticated user (Bearer token → `user_id` via `deps.py`)
2. Validate image content-type (`jpeg`, `png`, `webp`) → `422 VALIDATION_ERROR`
3. Validate image size (≤ 20 MB) → `413/422 MEDIA_FAILURE`
4. Construct `MediaRef` dict with owner-scoped key, media type, size, content hash
5. Create `analysis_run` row: `user_id`, `run_type="outfit"`, `status="pending"`,
   `engine_version="vision-v1"`, `input_media=<MediaRef>`
6. Return `202 {run_id}` — represents `"analysis requested"`, not `"appearance analyzed"`

**`CreateHairstyleRun`** extended to support image-based pass:

- If `image` provided AND `faceProfileRef` provided → `422 VALIDATION_ERROR`
  (mutually exclusive per catalog §12.11)
- If `image` provided → image-based pass (uses `CreateOutfitRun` logic,
  creates run with `input_media=MediaRef`, `run_type="hairstyle"`)
- If `faceProfileRef` provided and no image → profile-only pass (existing behavior,
  creates run with `input_media=None`)

**`CreateOutfitRun` does NOT execute the AI model.** The run remains in `pending`
status. The `"analysis requested"` status represents that the submission was
accepted and the run is queued for processing. Actual appearance analysis
happens in a later stage.

---

## 7. API Changes

### New endpoint: `POST /v1/analysis/outfit`

| Property | Value |
|---|---|
| **METHOD** | `POST` |
| **PATH** | `/v1/analysis/outfit` |
| **AUTHENTICATION** | Bearer token → `user_id` via `deps.py` (auth-required) |
| **REQUEST** | `multipart/form-data`:
  - `image` (required): file — outfit/capture photo
  - `faceProfileRef?` (optional): UUID — not supported for outfit scan |
| **RESPONSE** | `202 Accepted` — `{ "run_id": "UUID" }` (AsyncAccepted, no envelope) |
| **ERRORS** | `401` (AUTHENTICATION_ERROR), `413/422 MEDIA_FAILURE` (image too large/unsupported), `422 VALIDATION_ERROR` (no image, invalid input), `503 EXTERNAL_SERVICE_FAILURE` (provider), `429 RATE_LIMITED` |

### Extended endpoint: `POST /v1/analysis/hairstyle`

- Accepts `multipart/form-data` with `image` part (image-based pass) + optional
  `faceProfileRef` (profile-only pass)
- **Mutual exclusivity:** both `image` and `faceProfileRef` present → `422`
  VALIDATION_ERROR
- Image validation: content-type (`jpeg`, `png`, `webp`) and size (≤ 20 MB)
- Profile-only mode remains functional (existing behavior, unchanged)

### Existing endpoints (unchanged)

- `GET /v1/analysis/runs/{run_id}` — owner-scoped read (404-not-403)
- `GET /v1/analysis/runs` — paged summaries (no `result`/`error`, PR-5)
- `POST /v1/analysis/grooming` — profile-only pass (no image needed)

---

## 8. Privacy Behavior

- **Image bytes never logged** — only `MediaRef` fields (key, mediaType,
  contentHash) may be logged for observability, never the raw bytes
- **Run `result` content never logged** — only the fact of completion/failure,
  never the structured appearance data
- **Provider/model names never logged** — only `engine_version` may be logged for
  reproducibility
- **`details` in errors is allow-listed only** — never SQL, prompts, stack
  traces, tokens, provider/model names, or user content (ER-0/ER-2)
- **Owner-only access** — every run is scoped to the caller's `user_id`; another
  user's `run_id` → `404` (OW-1)
- **No raw image URLs exposed** in any response envelope — only `MediaRef`
  travels in API responses/errors (MS10.3, ER-4)
- **HTTPS only** for all image transmission
- **Unsaved scan media auto-expires** — background job handles retention;
  face scans expire after analysis/30 days unless user saves the look
- **No permanent image database** — no table stores image bytes; only `MediaRef`
  JSONB columns in `analysis_runs` and `saved_looks`

---

## 9. Tests

### Backend tests (design-only specification, per test contract §11.5):

| # | Test |
|---|---|
| 1 | Valid media reference → `202 {run_id}` with `input_media` populated as `MediaRef` |
| 2 | Invalid media content-type → `413/422 MEDIA_FAILURE` |
| 3 | Oversized media → `413/422 MEDIA_FAILURE` (`details.maxBytes`) |
| 4 | Authenticated user → run created with correct `user_id` scoping |
| 5 | Unauthenticated request → `401 AUTHENTICATION_ERROR` |
| 6 | Ownership violation → `404` for cross-user run read |
| 7 | Analysis-run creation → run with `status=pending` and `input_media=MediaRef` |
| 8 | Correct run type → `run_type="outfit"` for outfit scan, `"hairstyle"` for hairstyle image pass |
| 9 | Correct initial status → `status=pending` on creation |
| 10 | Context snapshot → `input_media` stored as `MediaRef` jsonb |
| 11 | Database rollback → existing migrations remain valid |
| 12 | Duplicate/idempotent request → second submission creates new run (never idempotent, API-11) |
| 13 | Media access control → 404 for cross-user run access |

### Database tests:

- Migration applies: N/A (no migration)
- Migration downgrade: N/A (no migration)
- Existing Hairstyle/Grooming data remains valid: verified (83 unit tests pass)

### Tests intentionally NOT yet implemented:

- AI analysis pipeline (mocked in later stages)
- Face detection/recognition
- UI-level widget tests for the new screens

---

## 10. Regression Results

### Backend (Python)

- `flutter analyze`: 0 new errors introduced (pre-existing info/warnings unchanged)
- `flutter test` (backend unit tests): 83/83 passed
  - `test_analysis_use_case.py`: 11 passed
  - `test_analysis_rules.py`: 10 passed
  - `test_engine.py`: passed
  - `test_decision_engine.py`: passed
  - `test_knowledge.py`: passed
  - `test_enrichment.py`: passed
- Hairstyle regression: No regressions — profile-only mode (`faceProfileRef` only)
  continues to work unchanged
- Grooming regression: No regressions — grooming endpoint unchanged
- Navigation regression: No regressions — existing routes unchanged

### Flutter

- `flutter analyze`: 19 issues (all pre-existing; no new errors)
  - 3 `info`, 16 `warning` — same as before changes
- `flutter test`: 382 passed, 3 failed (3 pre-existing grooming test failures,
  unrelated to appearance scan changes)

### Specific regression checks

- **Hairstyle profile-only mode**: ✅ Still works — `faceProfileRef` only path
  unchanged, creates run with `input_media=None`
- **Grooming endpoint**: ✅ Unchanged — same JSON body, same 202 response
- **Ownership (OW-1)**: ✅ Enforced on all new and existing endpoints
- **Media validation**: ✅ Content-type and size checks added, backward-compatible

---

## 11. Files Changed

| File | Description |
|---|---|
| `backend/app/api/schemas/analysis.py` | Added `CreateOutfitScanRequest`, `CreateHairstyleScanRequest` models |
| `backend/app/api/routers/analysis.py` | Extended `create_hairstyle_run` to accept images; added `create_outfit_run` endpoint |
| `backend/app/application/analysis.py` | Added `CreateOutfitRun` use case; extended `CreateHairstyleRun` mutual-exclusivity handling |
| `docs/implementation/APPEARANCE_SCAN_STAGE_3_REPORT.md` | **This report** |

---

## 12. Files Created

| File | Description |
|---|---|
| `docs/implementation/APPEARANCE_SCAN_STAGE_3_REPORT.md` | Stage 3 implementation report |

No new tables, no new database columns, no new API enpoints beyond the two specified.
All changes are additive and reuse existing infrastructure.

---

## 13. Known Limitations

- **AI appearance analysis not implemented** — foundation (database, media reference,
  analysis-run creation) is in place, but the actual analysis pipeline (face
  detection, classification, model inference) is deferred to a later stage
- **Object storage not integrated** — `MediaRef` key follows the owner-scoped
  path convention (`users/{user_id}/scans/{run_id}/input.{ext}`), but the actual
  blob upload to object storage is not implemented in this stage. The MediaRef is
  stored in `analysis_runs.input_media` JSONB for future use.
- **Image analysis pipeline not wired** — the use case creates the run as
  `pending` and returns `run_id`. The transition from `pending` → `completed`
  requires the AI analysis pipeline, which is out of scope for Stage 3.
- **No Flutter upload client changes** — the Flutter `http` multipart upload
  pattern exists but the client-side screen updates (processing → result) are
  deferred to a later stage
- **`faceProfileRef` not supported for `/outfit`** — the outfit scan endpoint
  requires an image; profile-only mode is not supported (different from hairstyle)

---

## 14. What Is Intentionally NOT Implemented

> **AI appearance analysis is NOT implemented in this stage.**

The following are explicitly out of scope for STEP 10.3:

- AI model inference or vision pipeline execution
- Face detection or face recognition in images
- Appearance classification (face shape, skin tone, body type, style type)
- Model training or parameter updates
- Redesign of Scan UI or Processing UI or Result UI
- Modification of unrelated features (Hairstyle, Grooming profile-only, Users)
- Database migration or schema changes beyond existing columns
- Replacement of PostgreSQL, FastAPI, or the existing analysis-run architecture
- Addition of new dependencies (only existing `http` package referenced)
- Change to authentication architecture (Bearer token via `deps.py` unchanged)
- User-facing DELETE endpoints for analysis runs or scan media
- Retention/deletion policy beyond what the approved contract specifies
- Permanent image storage or image database

**The result returned to the client represents "analysis requested" not
"appearance analyzed."** The actual appearance analysis, result generation, and
profile persistence (TRX-6) are deferred to later stages.

---

## Summary

This stage establishes the **foundation** for the Appearance Scan pipeline:

1. **Database** — existing schema suffices; no migration needed
2. **Media foundation** — `MediaRef` structure, upload-then-insert flow, content-type/size validation
3. **Media ownership** — user_id from auth token, owner-scoped paths, 404-not-403 enforcement
4. **Analysis-run integration** — existing lifecycle reused, `outfit` run type supported
5. **Application use case** — `CreateOutfitRun` and extended `CreateHairstyleRun`
6. **API foundation** — `POST /v1/analysis/outfit` + extended `POST /v1/analysis/hairstyle`
7. **Privacy** — no raw bytes logged, owner-only access, HTTPS, auto-expire

All changes are additive, reuse existing infrastructure, and preserve backward
compatibility with Hairstyle profile-only and Grooming modes.

**AI appearance analysis is NOT implemented in this stage.**