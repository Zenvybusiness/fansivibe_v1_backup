# REAL Appearance Scan Implementation Plan

**Repository:** fansivibe_v1_backup
**Stage:** STEP 10 — Implementation plan design only
**Date:** 2026-08-15
**Rule:** DO NOT modify application code, database, API contracts, dependencies, AI models, or UI. This plan is DESIGN ONLY.

---

## Overview

This implementation plan contains ordered stages that design the minimum changes required to support the REAL Appearance Scan pipeline, from image capture through to persisted appearance profile and recommendation. All stages reuse existing infrastructure wherever possible. No code is implemented yet — this is a design plan.

### Pipeline Summary

```
USER
  ↓
CAPTURE IMAGE (camera/gallery)
  ↓
UPLOAD (multipart → backend)
  ↓
CREATE ANALYSIS RUN (POST /v1/analysis/outfit)
  ↓
PROCESS IMAGE (backend: upload-then-insert → MediaRef → pending run)
  ↓
APPEARANCE ANALYSIS (engine: AppearanceProfile from result)
  ↓
STRUCTURED RESULT (analysis_runs.result JSONB)
  ↓
PERSIST APPEARANCE PROFILE (user_state.style_profile via TRX-6)
  ↓
DECISION ENGINE (recommend_hairstyle / recommend_grooming)
  ↓
RECOMMENDATION (SuggestionCard UI)
```

---

## Stage A — Database/Data Model

### A.1 Files Likely Affected

- **`backend/app/infrastructure/db/models.py`** — SQLAlchemy model definitions (read-only; no changes expected)
- **`backend/app/infrastructure/db/repositories.py`** — Repository implementations (existing `AnalysisRunRepositorySQL`; minor method additions if needed)
- **`docs/database/TABLE_DEFINITIONS.md`** — Design reference only (no SQL written)

### A.2 Existing Code to Reuse

| Component | Purpose |
|---|---|
| `AnalysisRuns` model | Already has `id`, `user_id`, `run_type`, `status`, `engine_version`, `input_media` (jsonb), `result` (jsonb), `created_at`, `completed_at` columns |
| `UserState` model | Already has `style_profile` (jsonb) with `face_shape`, `skin_tone`, `body_type`, `style_type`, `source_run_id` keys |
| `AnalysisRunRepositorySQL.create()` | Creates run with `status="pending"`, `input_media` — no changes needed |
| `AnalysisRunRepositorySQL.complete()` | Writes `result` + `completed_at` via `func.complete_analysis_run()` — no changes needed |
| `AnalysisRunRepositorySQL.fail()` | Marks run `failed` with `error` body — no changes needed |
| `UserStateRepositorySQL.get_style_profile()` | Reads current profile — no changes needed |

### A.3 New Code Required

No new database tables or columns are required. The existing schema safely represents all required information:

1. **`analysis_runs.result` (jsonb)** — Accepts `AppearanceProfile.to_snapshot()` which includes `faceShape`, `skinTone`, `bodyType`, `styleType`, `sourceRunId`, plus `confidence`, `needs_more_data`, and recommendation data. No migration needed.

2. **`analysis_runs.input_media` (jsonb)** — Already accepts `MediaRef` structure (key, mediaType, sizeBytes, contentHash, etc.). No migration needed.

3. **`user_state.style_profile` (jsonb)** — Already stores `face_shape`, `skin_tone`, `body_type`, `style_type`, `source_run_id`. No migration needed.

4. **`run_types` vocabulary** — Already includes `outfit`/`hairstyle`/`grooming` (and reserved `face`). No migration needed.

5. **`status` CHECK constraint** — Already enforces `pending`/`completed`/`failed`. No migration needed.

### A.4 Tests

- Verify that `analysis_runs.result` can store the `AppearanceProfile` snapshot structure (unit round-trip).
- Verify that `analysis_runs.input_media` can store a `MediaRef` (unit round-trip).
- Verify that `user_state.style_profile` can store the four appearance attributes + `source_run_id`.
- No new migration tests required — existing schema is sufficient.

### A.5 Dependencies

- None — existing PostgreSQL schema is sufficient.

### A.6 Risks

- **Low risk** — no schema changes required; existing columns already accept the required data shapes.
- **Mitigation** — verify via unit round-trip that the JSONB structures serialize/deserialize correctly for the new data.

### A.7 Rollback Strategy

- No migration was applied, so no rollback needed.
- If a migration were attempted, revert by dropping any added columns (but none are needed).

---

## Stage B — Media Handling

### B.1 Files Likely Affected

- **`backend/app/api/routers/analysis.py`** — Existing analysis router; may add `POST /v1/analysis/outfit` endpoint.
- **`backend/app/api/schemas/analysis.py`** — Existing schemas; may add request/response models for image upload.
- **`backend/app/infrastructure/db/repositories.py`** — Existing repository; `input_media` already accepts jsonb.
- **Flutter side** — `outfit_scan_screen.dart`, `outfit_processing_screen.dart` (existing camera capture UI).

### B.2 Existing Code to Reuse

| Component | Purpose |
|---|---|
| `POST /v1/analysis/hairstyle` | Existing endpoint; extended to accept `image` part (multipart) in addition to `faceProfileRef`. |
| `POST /v1/analysis/grooming` | Existing endpoint; accepts options JSON (no image needed). |
| `AnalysisRunRepositorySQL.create()` | Creates run with `status="pending"` and `input_media=None` (profile-only) or `input_media=MediaRef` (image-based). |
| `func.complete_analysis_run()` | Server-side function that writes `result` + `engine_version` on completion (TRX-5). |
| `func.fail_analysis_run()` | Server-side function that marks run `failed` with `error` body (TRX-5). |
| `MediaRef` value object | Already defined in `backend/app/models/schemas.py` / `TABLE_DEFINITIONS.md` — `MediaRef { objectKey, mediaType, width?, height?, sizeBytes, contentHash, isGenerated, uploadedAt }`. |
| Object storage bucket | `users/{user_id}/scans/{run_id}/` — existing path structure (MEDIA_STORAGE_DESIGN.md). |
| Inline multipart transport | `API-36` — `multipart/form-data` with `image` part is the accepted transport for analysis submissions. |

### B.3 New Code Required

1. **Extend `POST /v1/analysis/hairstyle`** to accept `multipart/form-data` with `image` part (required for image-based pass) + optional `faceProfileRef` (for profile-only pass).
   - Validate `image` content-type/size pre-run → `413/422 MEDIA_FAILURE`.
   - Perform **upload-then-insert** (TRX-1): blob → object storage → `MediaRef` → `analysis_runs.input_media`.
   - Create run with `run_type="hairstyle"` (or `"outfit"` for new outfit endpoint).

2. **New `POST /v1/analysis/outfit` endpoint** (or extend existing hairstyle endpoint):
   - `multipart/form-data` with required `image` part.
   - Optional `faceProfileRef` for profile-only mode.
   - Returns `202 {run_id}`.

3. **Backend upload-then-insert flow** (TRX-1):
   - Accept uploaded image bytes from Flutter.
   - Store blob in object storage at `users/{user_id}/scans/{run_id}/input.{ext}`.
   - Construct `MediaRef` value object with `key`, `mediaType`, `sizeBytes`, `contentHash`.
   - Write `MediaRef` to `analysis_runs.input_media` jsonb column.
   - Create `analysis_run` row with `status="pending"`.

4. **Flutter upload mechanism**:
   - `multipart/form-data` POST with `image` part containing the captured file bytes.
   - May use `http` package for multipart upload.
   - Handle upload progress, cancellation, and error states.

### B.4 Tests

- Upload valid image → `202 {run_id}` with `input_media` populated as `MediaRef`.
- Upload invalid content-type → `413/422 MEDIA_FAILURE`.
- Upload oversized image → `413/422 MEDIA_FAILURE` (`details.maxBytes`).
- Profile-only pass (no image, with `faceProfileRef`) → run created with `input_media=null`.
- Upload-then-insert: `MediaRef` stored correctly in `analysis_runs.input_media` (unit round-trip).
- Object storage path is owner-scoped: `users/{user_id}/scans/{run_id}/input.{ext}`.

### B.5 Dependencies

- **`http` package** (if not already a dependency) — for Flutter multipart upload. Check `pubspec.yaml` first.
- **Object storage** — already configured in the repository (M16 bucket path structure). No new dependencies.

### B.6 Risks

- **Medium risk** — adding multipart image upload to an endpoint that currently rejects images. Must ensure backward compatibility with profile-only mode (`faceProfileRef` without image).
- **Mitigation** — the endpoint accepts both modes: `image` alone (image-based), `faceProfileRef` alone (profile-only), rejects if both present. Validation errors clearly signal the issue.

### B.7 Rollback Strategy

- If the `POST /v1/analysis/outfit` or extended `POST /v1/analysis/hairstyle` endpoint causes issues, it can be gated behind the same seals as other M12/M16 endpoints (D-AUTH-1, MS10.3). The existing `POST /v1/analysis/hairstyle` profile-only mode remains functional.
- Rollback: disable the new `image` part handling; the endpoint reverts to profile-only mode as before.

---

## Stage C — API

### C.1 Files Likely Affected

- **`backend/app/api/routers/analysis.py`** — Existing analysis router; add `POST /v1/analysis/outfit` and extend `POST /v1/analysis/hairstyle`.
- **`backend/app/api/schemas/analysis.py`** — Existing schemas; add `CreateOutfitScanRequest`, `CreateHairstyleScanRequest` models.
- **`backend/app/api/errors.py`** — Existing errors; ensure all required error codes are defined (MEDIA_FAILURE, VALIDATION_ERROR, etc.).
- **`CURRENT_STATE.md`** — Update to reflect design completion.

### C.2 Existing Code to Reuse

| Component | Purpose |
|---|---|
| `AnalysisRun` DTO (bare, no envelope) | Already defined in `schemas/analysis.py` — `run_id`, `run_type`, `status`, `created_at`, `completed_at`, `engine_version`, `input_media`, `result`, `error`. |
| `AsyncAccepted` | Already defined — `202 Accepted` + `{run_id}` (no envelope). |
| `AnalysisRunRecord` / `AnalysisRunSummary` | Already defined in `repositories.py` — for serialization. |
| Error taxonomy (12 categories) | Already frozen in `API_ERROR_CONTRACT.md` / `FANSIVIBE_API_CONTRACT_V1.md`. |
| Auth dependency (`deps.py`) | Already resolves `user_id` from Bearer token; OW-1 enforcement. |
| `API-11` (idempotency) | Analysis submissions are never idempotent — each call creates a new run. |
| `API-10` (OW-1, 404-not-403) | Owner scoping on all user-owned endpoints. |
| `API-5` (Bearer auth) | Already established for protected endpoints. |
| `API-41/42` (async 202 + run_id + poll) | Already the pattern for analysis submissions. |
| `API-36` (multipart `image` part) | Already the accepted transport for analysis submissions with image. |

### C.3 New Code Required

1. **`POST /v1/analysis/outfit` endpoint** in `backend/app/api/routers/analysis.py`:
   - Method: `POST`
   - Path: `/v1/analysis/outfit`
   - Auth: Bearer → `user_id` via `deps.py`
   - Request: `multipart/form-data` with `image` (required) + optional `faceProfileRef`
   - Response: `202 Accepted` — `{run_id}`
   - Errors: `401`, `413/422 MEDIA_FAILURE`, `422 VALIDATION_ERROR`, `503 EXTERNAL_SERVICE_FAILURE`, `429 RATE_LIMITED`

2. **Extend `POST /v1/analysis/hairstyle` endpoint** in `backend/app/api/routers/analysis.py`:
   - Add `multipart/form-data` support with `image` part (required for image-based pass).
   - Add `faceProfileRef?` part (optional; profile-only pass).
   - Validate mutual exclusivity: reject if both `image` and `faceProfileRef` present.
   - Existing profile-only mode (`faceProfileRef` only) remains functional.

3. **Schema additions in `backend/app/api/schemas/analysis.py`**:
   - `CreateOutfitScanRequest` — multipart request body for outfit scan.
     - `image`: required file
     - `faceProfileRef?`: optional UUID
   - `CreateHairstyleScanRequest` — multipart request body for hairstyle scan.
     - `image`: required file (for image-based pass)
     - `faceProfileRef?`: optional UUID (for profile-only pass)
   - Keep existing `CreateGroomingScanRequest` (JSON body with `options`).

4. **Error code ensuring** — verify `MEDIA_FAILURE`, `VALIDATION_ERROR`, `AUTHENTICATION_ERROR`, `NOT_FOUND`, `EXTERNAL_SERVICE_FAILURE`, `PROCESSING_FAILURE`, `RATE_LIMITED` are all defined in `backend/app/api/errors.py` with correct HTTP status codes and safe client messages.

### C.4 Tests

- `POST /v1/analysis/outfit` with valid image → `202 {run_id}`.
- `POST /v1/analysis/outfit` with invalid content-type → `413/422 MEDIA_FAILURE`.
- `POST /v1/analysis/outfit` with oversized image → `413/422 MEDIA_FAILURE`.
- `POST /v1/analysis/outfit` with missing image → `422 VALIDATION_ERROR`.
- `POST /v1/analysis/outfit` with `faceProfileRef` only (profile-only) → `202 {run_id}`, `input_media=null`.
- `POST /v1/analysis/outfit` with both `image` and `faceProfileRef` → `422 VALIDATION_ERROR`.
- `POST /v1/analysis/hairstyle` with image + `faceProfileRef` → `422 VALIDATION_ERROR` (mutual exclusivity).
- `POST /v1/analysis/hairstyle` with `faceProfileRef` only → existing profile-only behavior (no regression).
- `GET /v1/analysis/runs/{run_id}` owner-scoped (404 for wrong user).
- `GET /v1/analysis/runs` lists only user's runs, optional `?run_type=` filter.
- Polling: pending → completed → returns `result`; pending → failed → returns `error`.

### C.5 Dependencies

- No new backend dependencies — all required infrastructure exists.
- Flutter: verify `http` package is available in `pubspec.yaml` for multipart upload. If not, add it (but this risks violating "DO NOT ADD DEPENDENCIES" — check first).

### C.6 Risks

- **Medium risk** — adding a new endpoint `POST /v1/analysis/outfit` while existing hairstyle/grooming endpoints are profile-only and explicitly reject images (MS10.3). Must ensure the new endpoint does not break existing profile-only flows.
- **Mitigation** — the new endpoint is separate (`/outfit` vs `/hairstyle`/`/grooming`). The existing endpoints are extended (hairstyle adds image support) rather than changed. Profile-only mode via `faceProfileRef` on hairstyle endpoint remains unchanged.

### C.7 Rollback Strategy

- If the new endpoint or extension causes issues, gate it behind D-AUTH-1 + MS10.3 (same as other M12/M16 endpoints). Until then, keep existing profile-only endpoints unchanged.
- Rollback: the `POST /v1/analysis/outfit` endpoint is not mounted until the auth/media seams land; the existing `POST /v1/analysis/hairstyle`/profile-only mode remains fully functional.

---

## Stage D — Analysis Adapter

### D.1 Files Likely Affected

- **`backend/app/application/analysis.py`** — Existing use cases (`CreateHairstyleRun`, `CreateGroomingRun`, `GetAnalysisRun`, `ListAnalysisRuns`); add `CreateOutfitRun` use case.
- **`backend/app/domain/services/analysis_rules.py`** — Existing decision engine; no changes needed (reused-as-is).
- **`backend/app/domain/services/grooming_rules.py`** — Existing grooming engine; no changes needed.
- **`backend/app/domain/value_objects.py`** — Existing `AppearanceProfile`, `HairstyleResult`, `GroomingResult`; no changes needed.

### D.2 Existing Code to Reuse

| Component | Purpose |
|---|---|
| `CreateHairstyleRun` use case | Creates hairstyle run from profile-only pass; extended to accept image-derived `AppearanceProfile` from result snapshot. |
| `CreateGroomingRun` use case | Creates grooming run from options JSON; no image needed. |
| `GetAnalysisRun` use case | Reads one run owner-scoped. |
| `ListAnalysisRuns` use case | Lists user's runs. |
| `recommend_hairstyle()` function | Full decision engine pipeline — reused-as-is; accepts `AppearanceProfile` as input. |
| `recommend_grooming()` function | Full grooming decision engine pipeline — reused-as-is; accepts `AppearanceProfile` as input. |
| `AppearanceProfile` value object | Same structure; data source changes from `user_state.style_profile` to `analysis_runs.result` appearance snapshot. |
| `HairstyleResult.to_snapshot()` / `GroomingResult.to_snapshot()` | Serializes result to dict for `analysis_runs.jsonb` storage. |
| `func.complete_analysis_run()` | Server-side TRX-5 guarded completion — writes `result` + `engine_version` once. |
| `func.fail_analysis_run()` | Server-side TRX-5 guarded failure — marks run `failed` with `error` body. |

### D.3 New Code Required

1. **Add `CreateOutfitRun` use case** in `backend/app/application/analysis.py`:
   - Similar pattern to `CreateHairstyleRun` but accepts image input.
   - **Step 1**: Validate `image` content-type/size → `413/422 MEDIA_FAILURE` if invalid.
   - **Step 2**: Perform upload-then-insert (TRX-1): blob → object storage → `MediaRef` → `analysis_runs.input_media`.
   - **Step 3**: Create `analysis_run` row: `user_id`, `run_type="outfit"`, `status="pending"`, `engine_version="vision-v1"`, `input_media=<MediaRef>`.
   - **Step 4**: After job completes (background), extract `AppearanceProfile` from the analysis result:
     - `faceShape`, `skinTone`, `bodyType`, `styleType` from `result.appearance`
     - `sourceRunId` = the run's own `run_id`
     - `confidence`, `needs_more_data` from engine output
   - **Step 5**: Feed `AppearanceProfile` into `build_context()` → `recommend_hairstyle()` → `HairstyleResult`.
   - **Step 6**: Complete the run via `AnalysisRunRepositorySQL.complete()` with `result=HairstyleResult.to_snapshot()`.
   - **Step 7**: TRX-6: Apply face attributes to `user_state.style_profile` (separate transaction).
   - **Step 8**: Emit learning signal `analysis_updated`.

2. **Wire image-derived `AppearanceProfile` into existing engine**:
   - The engine (`recommend_hairstyle()`) accepts `AppearanceProfile` as its first parameter — no structural change needed.
   - The only change is the **data source**: instead of reading from `user_state.style_profile`, read from the completed `analysis_runs.result` appearance snapshot.
   - Example wiring:
     ```python
     # After run completion, result contains appearance snapshot:
     appearance = AppearanceProfile(
         faceShape=result["appearance"]["faceShape"],
         skinTone=result["appearance"]["skinTone"] or "",
         bodyType=result["appearance"]["bodyType"] or "",
         styleType=result["appearance"]["styleType"] or "",
         sourceRunId=str(run_id),
     )
     context = build_context(appearance=appearance, knowledge_version=run.engine_version)
     result = recommend_hairstyle(knowledge, appearance)  # engine reused-as-is
     ```

### D.4 Tests

- `CreateOutfitRun` use case creates run with `status=pending` and `input_media=MediaRef`.
- Use case extracts `AppearanceProfile` from result snapshot and feeds into engine.
- Engine produces `HairstyleResult` with correct `appearance`, `top`, `alternatives`, `confidence`, `needs_more_data`.
- Run completed via TRX-5 writes `result` + `engine_version` atomically.
- TRX-6 updates `user_state.style_profile` with image-derived attributes + `source_run_id`.
- Learning signal `analysis_updated` emitted after profile update.
- Profile-based hairstyle scan (no image, with `faceProfileRef`) still works without regression — engine still accepts `AppearanceProfile` from profile.

### D.5 Dependencies

- Existing dependencies — no new packages required.
- The `build_context()`, `recommend_hairstyle()`, and `recommend_grooming()` functions are reused-as-is.

### D.6 Risks

- **Low risk** — the engine itself requires no changes; only the use case wiring changes (data source from profile to image result).
- **Mitigation** — thorough unit tests verifying the wiring: image result → `AppearanceProfile` → engine → `HairstyleResult` → run completion → TRX-6 profile update.

### D.7 Rollback Strategy

- If the use case wiring causes issues, revert the data source: read `AppearanceProfile` from `user_state.style_profile` as before. The engine and all other code paths remain unchanged since they already accept `AppearanceProfile` from that source.
- The image-derived path is an additional branch; the profile-derived path remains the fallback.

---

## Stage E — Appearance Persistence

### E.1 Files Likely Affected

- **`backend/app/application/analysis.py`** — TRX-6 profile projection update (already in `CreateHairstyleRun` pattern; extend for appearance scan).
- **`backend/app/infrastructure/db/repositories.py`** — Existing `UserStateRepositorySQL`; `get_style_profile()` already reads jsonb.
- **`backend/app/domain/services/analysis_rules.py`** — No changes; engine reused-as-is.

### E.2 Existing Code to Reuse

| Component | Purpose |
|---|---|
| `TRX-6` (profile projection update) | Already implemented in `CreateHairstyleRun` — applies face analysis attributes to `user_state.style_profile` via `PATCH /v1/users.me` with `sourceRunId`. |
| `UserStateRepositorySQL.get_style_profile()` | Reads current `style_profile` jsonb — no changes needed. |
| `AnalysisRunRepositorySQL.complete()` | Writes `result` + `completed_at` via TRX-5 — no changes needed. |
| `AppearanceProfile` value object | Same structure; data source changes. |
| `LearningSignalRepositorySQL.insert_look_saved()` | Emits `analysis_updated` signal — already used by `CreateHairstyleRun`. |

### E.3 New Code Required

1. **TRX-6 for Appearance Scan** — after the analysis run completes and the engine produces recommendations:
   ```python
   # Apply image-derived appearance attributes to current profile
   self._user_state.update_style_profile(
       user_id=user_id,
       face_shape=appearance.faceShape,
       skin_tone=appearance.skinTone,
       body_type=appearance.bodyType,
       style_type=appearance.styleType,
       source_run_id=str(run_id),  # provenance to the producing run
   )
   ```
   - This is the **same pattern** as `CreateHairstyleRun.TRX-6` but the attributes come from the image-derived `AppearanceProfile` instead of from a profile-only pass.

2. **Learning signal emission** after profile update:
   ```python
   self._learning_signal.insert_look_saved(
       user_id=user_id,
       label="analysis_updated",
       context={"run_id": str(run_id), "run_type": "outfit"},
   )
   ```

### E.4 Tests

- After `CreateOutfitRun` completion, `user_state.style_profile` contains `face_shape`, `skin_tone`, `body_type`, `style_type`, `source_run_id`.
- `source_run_id` in profile links to the producing `analysis_run.run_id`.
- Subsequent profile-based hairstyle scan (using stored profile) works without image — engine reads from `style_profile` as before.
- Learning signal `analysis_updated` appears in `learning_signals` table for the user.
- Profile update is a separate transaction from run completion (TRX-6 guarantee: run row untouched if profile update fails).

### E.5 Dependencies

- Existing dependencies — no new packages.
- The `PATCH /v1/users/me` pattern for profile update already exists (R-2 in profile onboarding API).

### E.6 Risks

- **Low risk** — TRX-6 profile update pattern already exists for hairstyle runs; extending it to appearance scans is analogous.
- **Mitigation** — verify that the profile update does not overwrite existing profile values unnecessarily; only update the four appearance attributes + `source_run_id` (latest-wins semantics).

### E.7 Rollback Strategy

- If TRX-6 profile update fails, the run row remains completed with `result` — the run is immutable history. The profile simply retains its previous values (or the values from a prior run's TRX-6).
- Rollback: do not update `user_state.style_profile`; the run result is still persisted, and the profile is unchanged. A subsequent run's TRX-6 can update the profile.

---

## Stage F — Decision Engine Integration

### F.1 Files Likely Affected

- **`backend/app/application/analysis.py`** — Use case wiring (already designed in Stage D).
- **`backend/app/domain/services/analysis_rules.py`** — No changes; engine reused-as-is.
- **`backend/app/domain/services/grooming_rules.py`** — No changes; engine reused-as-is.
- **`backend/app/domain/value_objects.py`** — No changes; `AppearanceProfile`, `HairstyleResult`, `GroomingResult` same.

### F.2 Existing Code to Reuse

| Component | Purpose |
|---|---|
| `build_context()` | Takes `AppearanceProfile` + optional `HairstylePreferences` + `knowledge_version` — identical for image-derived or profile-derived data. |
| `generate_candidates()` | Retrieves catalog looks from `KnowledgeSource` port — same. |
| `filter_candidates()` | Hard exclusion via `excludedLookIds` — same. |
| `score_candidates()` | Weighted signal composition (seed + face_boost + preference_boost) — same. |
| `rank_candidates()` | Score-descending order, stable tie-breaking — same. |
| `build_explanations()` | Grounded reasons from catalog — same. |
| `derive_confidence()` | 50% completeness + 50% decisiveness — same deterministic formula. |
| `recommend_hairstyle()` | Full orchestrator — same function signature; accepts `AppearanceProfile`. |
| `recommend_grooming()` | Full orchestrator — same function signature; accepts `AppearanceProfile`. |
| `AppearanceProfile` value object | Same 5 fields (`faceShape`, `skinTone`, `bodyType`, `styleType`, `sourceRunId`) — only the data source changes. |

### F.3 New Code Required

**No new code required in the engine.** The integration is entirely in the use case layer:

1. **After analysis run completion**, extract `AppearanceProfile` from `analysis_runs.result` appearance snapshot.
2. **Pass to existing engine functions** — `build_context()`, `recommend_hairstyle()`, or `recommend_grooming()`.
3. **Engine produces `HairstyleResult`/`GroomingResult`** — same output schema as profile-based flows.
4. **Result serialized via `to_snapshot()`** and written to `analysis_runs.result` via TRX-5.
5. **TRX-6** applies the `AppearanceProfile` to `user_state.style_profile`.
6. **Learning signal** emitted.

The engine functions do not need to know whether the `AppearanceProfile` came from an image or a profile — they accept the same value object type.

### F.4 Tests

- Image-derived `AppearanceProfile` fed into `build_context()` → same output as profile-derived.
- `recommend_hairstyle(knowledge, image_appearance)` produces `HairstyleResult` with identical schema to `recommend_hairstyle(knowledge, profile_appearance)`.
- `recommend_grooming(knowledge, image_appearance)` produces `GroomingResult` with identical schema.
- Confidence derivation: `derive_confidence(context, ranked)` same formula (50% completeness + 50% decisiveness) regardless of data source.
- `needs_more_data` flag: same semantics (completeness < 1.0) regardless of data source.
- Engine output (`HairstyleResult`/`GroomingResult`) serialized to `analysis_runs.result` via `to_snapshot()` — round-trip test.

### F.5 Dependencies

- Existing dependencies only — no new packages.
- The engine is completely reused; only the use case wiring changes.

### F.6 Risks

- **Very low risk** — the engine is designed to accept `AppearanceProfile` from any source; the domain model explicitly states that appearance attributes are AI-generated content accepted into the current-profile projection. The engine has no knowledge of the data source.

### F.7 Rollback Strategy

- If integration issues arise, revert the data source: read `AppearanceProfile` from `user_state.style_profile` as before. The engine and all output remain identical since the value object type is the same.
- The profile-based path is the fallback; the image-derived path is an additional branch.

---

## Stage G — Flutter Integration

### G.1 Files Likely Affected

- **`newproject/flutter_application_1/lib/screens/outfit_scan_screen.dart`** — Existing camera capture UI; add gallery picker alternative.
- **`newproject/flutter_application_1/lib/screens/outfit_processing_screen.dart`** — Existing processing UI; replace mock timers with real polling.
- **`newproject/flutter_application_1/lib/screens/outfit_analysis_screen.dart`** — Existing analysis results UI; display real appearance data + recommendations.
- **`newproject/flutter_application_1/lib/widgets/outfit_scan_widgets.dart`** — Existing widget library; may need minor adjustments.
- **`newproject/flutter_application_1/lib/features/analysis/`** — New or adapted analysis client/service.
- **`pubspec.yaml`** — Verify `http` package availability for multipart upload.

### G.2 Existing Code to Reuse

| Component | Purpose |
|---|---|
| `OutfitScanScreen` | Camera capture UI — `CameraController.takePicture()` saves to temp path; navigate to processing. |
| `OutfitProcessingScreen` | Processing UI — can replace mock timers with polling for run completion. |
| `OutfitAnalysisScreen` | Analysis results UI — can display real `AppearanceProfile` fields + recommendations instead of mock data. |
| `CameraPreviewPlaceholder`, `CheckIndicator`, `ProcessingStageIndicator`, `AnalysisSectionCard`, `DetectedItemChip` | Existing widgets — reuse for layout; no structural changes needed. |
| GoRouter routing | Existing `RouteNames.scanOutfit`, `RouteNames.scanProcessing`, `RouteNames.scanAnalysis` — can add new route for results. |
| `GoRouter extras` | Image path passed via extras between screens — can change to `run_id` after upload. |
| `image_picker` package | If already a dependency, use for gallery alternative. Check `pubspec.yaml`. |
| `http` package | For multipart upload to `POST /v1/analysis/outfit` — if already a dependency. |

### G.3 New Code Required

1. **Flutter upload flow**:
   - After capture, instead of passing image path via GoRouter extras, upload image to backend:
     ```dart
     // multipart form upload
     var request = http.MultipartRequest(
       'POST', Uri.parse('$baseUrl/v1/analysis/outfit'),
     );
     request.files.add(await http.MultipartFile.fromPath(
       'image', capturedImagePath,
     ));
     var response = await request.send();
     var runId = jsonDecode(await response.stream.bytes)['run_id'];
     ```
   - Navigate to processing screen with `run_id` extra.

2. **Replace mock processing timers with real polling**:
   - `OutfitProcessingScreen` polls `GET /v1/analysis/runs/{run_id}` until `status ∈ {completed, failed}`.
   - Show `pending` state initially; show `completed` with result or `failed` with error.
   - Display progress indicator during polling.

3. **Display real appearance data in analysis screen**:
   - From `AnalysisRun.result`: extract `AppearanceProfile` (faceShape/skinTone/bodyType/styleType).
   - Show confidence and `needs_more_data` flag.
   - Show recommendations from `result.recommendations` (top + alternatives).
   - Replace `OutfitAnalysisData.mock` with real data from the run.

4. **New route for analysis results**:
   - Add `RouteNames.scanAnalysis` → new screen or adapt existing to accept `run_id` instead of `capturedImagePath`.
   - Or reuse existing navigation chain with modified extras.

5. **Error handling UI**:
   - Upload failure → Snackbar + retry.
   - Analysis failure → Snackbar + retry (new scan).
   - Invalid image format → validation error display.

### G.4 Tests

- Camera capture → upload → `202 {run_id}` → poll → `completed` with result → display appearance profile fields → show recommendations.
- Camera capture → upload → `413/422 MEDIA_FAILURE` → Snackbar + retry.
- Polling loop: pending → completed/failed UI transitions.
- Gallery picker alternative → same upload → run → result path as camera capture.
- Failure states: upload error, analysis error, timeout handling.
- Result screen displays real `AppearanceProfile` data (not mock) + real recommendations (not `OutfitAnalysisData.mock`).

### G.5 Dependencies

- **`http` package** — for Flutter multipart upload. Check `pubspec.yaml`. If not present, add it (this is a potential "new dependency" risk — verify first).
- **`image_picker` package** — if gallery picker is required (P1 improvement). Check `pubspec.yaml`.
- No other new dependencies — all other infrastructure (GoRouter, camera, routing) already exists.

### G.6 Risks

- **Medium risk** — the Flutter side currently has mock processing timers and mock analysis data. Replacing these with real API polling and real data requires careful UI changes that preserve the existing screen layouts and design tokens.
- **Mitigation** — reuse existing widgets (`AnalysisSectionCard`, `DetectedItemChip`) for the real data display; only the data source changes. The 65/35 card visual proportion is preserved.

### G.7 Rollback Strategy

- If Flutter changes cause UI issues, revert the processing screen to mock timers and the analysis screen to mock data. The backend API changes remain; only the Flutter presentation is reverted.
- The backend is fully functional; the Flutter side can be iteratively improved without breaking the API.

---

## Stage H — End-to-End Validation

### H.1 Files Likely Affected

- **All stages** — integration test suite.
- **`newproject/flutter_application_1/test/`** — Flutter widget/tests.
- **`backend/tests/`** — Python unit/tests.

### H.2 Integration Test Scenarios

| Scenario | Steps | Expected Outcome |
|---|---|---|
| **Happy path: Image → Run → Analysis → Profile → Recommendation** | 1. Capture image from camera<br>2. Upload → `POST /v1/analysis/outfit` → `202 {run_id}`<br>3. Poll `GET /v1/analysis/runs/{run_id}` → `status=completed`<br>4. Read result → `AppearanceProfile` (faceShape/skinTone/bodyType/styleType) + `confidence` + `needs_more_data`<br>5. Show recommendations (top + alternatives)<br>6. Verify `user_state.style_profile` updated with TRX-6 (face_shape, skin_tone, body_type, style_type, source_run_id) | End-to-end flow works from capture to persisted profile and recommendations. |
| **Profile-only pass: faceProfileRef → recommendations** | 1. Skip capture; use stored FaceProfile via `faceProfileRef`<br>2. `POST /v1/analysis/hairstyle` with `faceProfileRef` only<br>3. Poll → `completed` → recommendations from stored profile (no image attributes)<br>4. `user_state.style_profile` updated via TRX-6 (if face attributes produced) | Profile-only mode still works; image not required for recommendation pass. |
| **Failure: Invalid image format** | 1. Capture image with unsupported format<br>2. `POST /v1/analysis/outfit` → `413/422 MEDIA_FAILURE`<br>3. Snackbar shown; retry option available | Upload validation works; user can retry with correct format. |
| **Failure: No face detected** | 1. Capture poor-quality image (dark, obscured face)<br>2. `POST /v1/analysis/outfit` → run → `failed` status<br>3. Poll → `error` body, no `result`<br>4. UI shows failure + retry (new scan) | Detection failure handled gracefully; failed run stays as history. |
| **Retry flow: Failed run re-submission** | 1. Run fails → client re-POST → new run created<br>2. Original failed run stays `failed` with `error` body, immutable<br>3. New run follows happy path → `completed` → result + profile update | Failed run is auditable history; retry creates distinct new run. |
| **Media auto-expire: Unsaved scan** | 1. Run created, user does NOT save the look<br>2. Wait for retention window (background job)<br>3. Scan media auto-expires from object storage<br>4. `analysis_run` row remains (append-only)<br>5. User can re-scan → new run | Unsaved media auto-expires; run history preserved. User can re-scan. |
| **Media retention: Saved look** | 1. Run created, user saves the look via `POST /v1/looks/today/save`<br>2. `result` snapshot persisted in `saved_looks.snapshot`<br>3. Scan media may still auto-expire independently<br>4. The saved look retains the appearance profile snapshot | Saved look retains profile snapshot independently of scan media expiry. |
| **Cross-user ownership** | 1. User A creates a run<br>2. User B tries `GET /v1/analysis/runs/{run_id}` → `404` (not owned)<br>3. User B tries `POST /v1/analysis/outfit` → `401` (auth) or run scoped to A | Owner scoping (OW-1) works; cross-user access → 404, never 403. |
| **Profile persistence across runs** | 1. User completes appearance scan → `style_profile` updated<br>2. User completes another appearance scan (new run)<br>3. `style_profile` updated with latest-wins (TRX-6)<br>4. Subsequent profile-based hairstyle scan works using stored profile | Profile evolves across runs; profile-based scans don't need images. |

### H.3 Backend Unit Tests

| Test | Description |
|---|---|
| `CreateOutfitRun` use case | Creates run with image → `input_media=MediaRef`, `status=pending`. |
| AppearanceProfile extraction | Extract `AppearanceProfile` from `analysis_runs.result` snapshot → correct fields. |
| Engine wiring | `recommend_hairstyle(knowledge, appearance_from_image)` → `HairstyleResult` with correct schema. |
| TRX-5 completion | Run completed → `result` + `engine_version` written atomically; run row immutable. |
| TRX-6 profile update | Profile updated with image-derived attributes + `source_run_id`; separate from TRX-5. |
| Learning signal | `analysis_updated` signal emitted after profile update. |
| Failure paths | Invalid image → `413/422 MEDIA_FAILURE`; pipeline exception → run marked `failed`. |
| Polling | Pending → completed/failed reads correct. |

### H.3 Flutter Widget Tests

| Test | Description |
|---|---|
| Capture and upload | Camera capture → multipart upload → `202 {run_id}`. |
| Polling loop | Poll `GET /analysis/runs/{run_id}` → status transitions. |
| Result display | Completed run result → `AppearanceProfile` fields rendered; recommendations rendered. |
| Failure states | Upload error → Snackbar; analysis failure → Snackbar + retry. |
| Gallery picker | Image picked from gallery → same upload path → run → result. |

### H.4 Test Constraints (per strict rules)

- **DO NOT modify application code** — tests are design-only specification; actual implementation tests would run against the real backend, but this plan is design-only.
- **DO NOT modify database** — test data uses existing schema.
- **DO NOT add dependencies** — use existing test infrastructure where possible.
- **DO NOT implement AI models** — tests mock the analysis pipeline.
- **DO NOT modify existing Hairstyle/Grooming behavior** — tests reuse existing engine functions; profile-based flows remain unchanged.

### H.5 Validation Run Checklist

- [ ] Data contract: all appearance attributes (faceShape, skinTone, bodyType, styleType, sourceRunId, confidence, needs_more_data) correctly separated into Observed/Inferred/User-Provided/Derived.
- [ ] Database: existing schema suffices; no new tables/columns needed.
- [ ] Media: upload-then-insert flow (TRX-1) produces `MediaRef` in `input_media`; object storage path owner-scoped.
- [ ] API: `POST /v1/analysis/outfit` (new) + extended `POST /v1/analysis/hairstyle` + polling/result retrieval (`GET /analysis/runs/{run_id}`) all documented and functional.
- [ ] Result: `analysis_runs.result` JSONB contains `AppearanceProfile` snapshot + confidence + needs_more_data + recommendations.
- [ ] Decision engine: `AppearanceProfile` from result fed into existing `recommend_hairstyle()`/`recommend_grooming()` — no engine changes needed.
- [ ] Profile persistence: TRX-6 updates `user_state.style_profile` with image-derived attributes + `source_run_id`; separate from run completion.
- [ ] Versioning: only `engine_version` on `analysis_runs`; no version field on appearance schema or result.
- [ ] Error: all paths documented (invalid image, unsupported format, upload failure, auth failure, unauthorized media, analysis failure, timeout, model unavailable, malformed result, persistence failure, run not found).
- [ ] Security: user ownership (OW-1, 404-not-403); image bytes never logged/echoed; HTTPS only; retention auto-expire; no permanent image database.
- [ ] Tests: backend unit tests, Flutter widget tests, integration scenarios all defined.

---

## Summary of All Stages

| Stage | Key Deliverable | Risk | Rollback |
|---|---|---|---|
| **A — Database** | No new tables; existing schema suffices | Low | N/A (no migration) |
| **B — Media** | Upload-then-insert flow; `MediaRef` in `input_media`; object storage | Medium | Gate behind D-AUTH-1/MS10.3; revert to profile-only |
| **C — API** | `POST /v1/analysis/outfit` + extended `POST /v1/analysis/hairstyle` + polling/result | Medium | Gate behind auth/seams; existing endpoints unchanged |
| **D — Analysis Adapter** | Use case wiring; `AppearanceProfile` from result into engine | Low | Revert data source to `user_state.style_profile` |
| **E — Appearance Persistence** | TRX-6 profile update with image-derived attributes | Low | Do not update profile; run result still persisted |
| **F — Decision Engine** | No engine changes; reuse-as-is; data source change only | Very low | Revert data source; engine identical |
| **G — Flutter** | Upload flow; real polling; real appearance data + recommendations | Medium | Revert to mock timers + mock data |
| **H — E2E Validation** | Integration test scenarios | Medium | Iterative fixes; backend fully functional |

**All stages reuse existing infrastructure.** No new tables, no new dependencies (except potentially `http` package for Flutter multipart, which should already exist), no code deletions, no database changes, no UI redesigns, no AI model implementation. The plan is entirely design-phase specification.