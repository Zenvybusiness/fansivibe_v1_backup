# REAL Appearance Scan Audit

**Repository:** fansivibe_v1_backup
**Stage:** STEP 10 — Audit only
**Date:** 2026-08-15
**Rule:** DO NOT modify application code, database, API contracts, dependencies, AI models, or UI.

---

## 1. Current Flutter Scan Architecture

### 1.1 Scan Screen Flow

| Screen | Purpose | Key Behaviors |
|---|---|---|
| `OutfitScanScreen` | Camera UI — capture outfit image | Camera preview, capture button, switches camera, handles permission/errors. On capture, pushes `/scan-outfit/processing` with local image path. |
| `OutfitProcessingScreen` | Mock processing UI | 5 fixed stages (detecting → proportions → colors → style_dna → recommendations) driven by timers, not real processing. On completion, navigates to `/scan-outfit/analysis`. |
| `OutfitAnalysisScreen` | Analysis results UI | Displays mock `OutfitAnalysisData.mock` — predetermined sections, detected items, scores. Actions: Save (to wardrobe) and Generate Look. |

### 1.2 Image Handling

- **Capture:** `CameraController.takePicture()` from the `camera` package saves to a temporary local path.
- **Passing between screens:** Image path (`String?`) passed via GoRouter `extra` parameter through the chain:
  `OutfitScanScreen` → `OutfitProcessingScreen` → `OutfitAnalysisScreen`
- **Backend transmission:** **NOT sent** to backend. The capture flow deliberately does not upload the image.
- **Temporary storage:** Camera package's default temp path; no explicit cleanup logic observed.

### 1.3 Mock / Simulated Behavior

- Processing stages are `ProcessingStage.mockStages` with hardcoded durations (milliseconds).
- Analysis data is `OutfitAnalysisData.mock` — fully predetermined, no image-derived content.
- "AI Analysis Active" badge shown in camera preview is a UI label, not indicative of real AI.
- Rescan / Share buttons show SnackBars: "Gallery coming soon", "Share coming soon".

### 1.4 Camera & Permissions

- Uses `camera` package with `CameraController`.
- Handles: available cameras, selected resolution (`medium`), format (JPEG), camera switching, permission denied/unavailable/error states.
- Test mode shortcut: if in widget test mode, skips camera and navigates directly to processing.

### 1.5 Routing

- `RouteNames.scanOutfit` → `OutfitScanScreen`
- `RouteNames.scanProcessing` → `OutfitProcessingScreen` (receives `capturedImagePath` extra)
- `RouteNames.scanAnalysis` → `OutfitAnalysisScreen` (receives `capturedImagePath` extra)

---

## 2. Current Backend Scan Architecture

### 2.1 Analysis API Endpoints

| Endpoint | Method | Purpose | Image Handling |
|---|---|---|---|
| `POST /v1/analysis/hairstyle` | async, profile-only | Creates hairstyle run from face profile ref, returns `run_id` | **Rejects images** — raises validation error "image upload is not available in this version" (MS10.3 sealed) |
| `GET /v1/analysis/runs/{run_id}` | read one run | Owner-only, returns `AnalysisRun` schema | No image handling |
| `GET /v1/analysis/runs` | list runs | Paged summaries, no `result`/`error` | No image handling |
| `POST /v1/analysis/grooming` | profile-only | Creates grooming run from face profile ref, returns `run_id` | **Rejects images** — same validation as hairstyle |

### 2.2 Analysis Run Model

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | UUID | FK to users |
| `run_type` | str | e.g. "hairstyle", "grooming" |
| `status` | str | 'pending', 'completed', 'failed' |
| `engine_version` | str | e.g. "rules-v1" |
| `input_media` | Optional[dict] | JSONB — currently `None` for profile-only passes |
| `result` | Optional[dict] | JSONB — hairstyle/grooming result snapshot |
| `error` | Optional[dict] | JSONB — failure details |
| `created_at` | datetime | |
| `completed_at` | Optional[datetime] | |

### 2.3 Image/Upload Policy (MS10.3)

- The backend explicitly **does not accept images** for hairstyle/grooming analysis.
- Images are not stored, not processed, not uploaded.
- The hairstyle endpoint requires `faceProfileRef` (a face shape UUID from user profile) and `image` is explicitly rejected.
- This is a deliberate design decision documented as "media pipeline is sealed".

### 2.4 Decision Engine (Rules-Based)

- `app/domain/services/analysis_rules.py` — deterministic, rules-first engine.
- Stages: ContextBuilder → CandidateGeneration → Filtering → Scoring → Ranking → Explanation → Recommendation.
- Uses `AppearanceProfile` value object: `faceShape`, `skinTone`, `bodyType`, `styleType`, `sourceRunId`.
- Confidence derived deterministically: 50% data completeness + 50% top-pick decisiveness.
- `needs_more_data` honestly signals sparse profile, never fabricates.
- No image analysis capability — operates entirely on profile-supplied face attributes.

### 2.5 AI / Model Layer

| Capability | Classification |
|---|---|
| Rules-based hairstyle decision engine | **REAL** — deterministic, documented |
| Rules-based grooming decision engine | **REAL** — deterministic, documented |
| LLM enrichment (Ollama, optional) | **REAL** — only for assistant chat reply text, never structure/scores |
| Image analysis / appearance extraction from photos | **NOT IMPLEMENTED** — no model, no API, explicit refusal |
| Face shape detection from images | **NOT IMPLEMENTED** — only from user profile |

### 2.6 Appearance Data Persistence

- `AppearanceProfile` dataclass exists in domain layer but is populated from `user_state.style_profile` (face_shape, skin_tone, body_type, style_type), NOT from image analysis.
- No image-derived appearance data is persisted.
- `analysis_runs.result` can contain a snapshot of `AppearanceProfile.to_snapshot()` but this is only from profile-based runs, not image-based.

---

## 3. Current Database Support

### 3.1 Relevant Tables

| Table | Columns relevant to appearance |
|---|---|
| `users` | id, auth_provider, auth_subject, display_name |
| `user_state` | style_profile (JSONB) — contains `face_shape`, `skin_tone`, `body_type`, `style_type` as sparse keys |
| `analysis_runs` | input_media (JSONB, currently None for profile runs), result (JSONB, appearance snapshot), status, run_type |
| `style_profile` | No separate table — embedded in `user_state` as JSONB |

### 3.2 What Exists

- `user_state.style_profile` can store: `face_shape`, `skin_tone`, `body_type`, `style_type` as optional JSONB keys.
- `analysis_runs` can store `input_media` and `result` as JSONB.
- `AppearanceProfile` value object defines the structured appearance schema: `faceShape`, `skinTone`, `bodyType`, `styleType`, `sourceRunId`.
- No images stored in database.
- No image URLs or references in `analysis_runs.input_media` for current flows.

### 3.3 Gaps

- No column/separate table for image references or media hashes.
- No pipeline to populate `appearance` fields from captured images.
- `input_media` is currently unused/None in profile-only passes.

---

## 4. Current AI/Model Support

| Capability | Classification |
|---|---|
| Rules-based hairstyle engine | **REAL** — `app/domain/services/analysis_rules.py`, deterministic stages |
| Rules-based grooming engine | **REAL** — `app/domain/services/analysis_rules.py`, deterministic stages |
| LLM enrichment (Ollama) | **REAL** — optional, only rewrites assistant reply text, never structure |
| Image appearance analysis | **NOT IMPLEMENTED** — no model, no adapter, explicit backend refusal |
| Face shape detection from images | **NOT IMPLEMENTED** — only from user profile via `style_profile` |
| Confidence derivation | **REAL** — deterministic formula (completeness × decisiveness) |

### 4.1 Inputs / Outputs

- **Hairstyle engine input:** `AppearanceProfile` (from user profile), `HairstylePreferences`, `KnowledgeSource` (catalog).
- **Hairstyle engine output:** `HairstyleResult` with `appearance`, `top`, `alternatives`, `confidence` (float [0,1]), `needs_more_data` (bool).
- **Grooming engine input/output:** Same structure, grooming-specific catalog and boosts.

### 4.2 Failure Behavior

- Engine raises `KnowledgeError` if catalog empty after filtering.
- Pipeline exceptions → run marked `failed` in DB, never stuck `pending`.
- LLM unavailability → falls back to deterministic rules text; structured contract unchanged.

### 4.3 Dependencies

- `app/data/catalog.py` — hairstyle/grooming look catalog (deterministic, offline-safe).
- `app/domain/ports/external.KnowledgeSource` — port for catalog access.
- No FFI, no external AI services in the scan pipeline.

---

## 5. Current Image/Media Handling

### 5.1 Flutter Side

- Camera captures → temporary local file path (camera package).
- Path passed via GoRouter extras between screens.
- No network upload attempt.
- No image compression, resizing, or format conversion observed beyond camera package defaults.
- No cached/permanent storage observed.

### 5.2 Backend Side

- No image upload endpoint for scan flow.
- `POST /v1/analysis/hairstyle` explicitly rejects `UploadFile` with validation error.
- No media/picture endpoints observed.
- `analysis_runs.input_media` column exists as JSONB but is `None` for profile-only passes.

### 5.3 Privacy / Safety

- Images are **not** logged, stored, or transmitted in current flow.
- No permanent image retention observed.
- No private image URLs exposed.
- Gaps: if image upload were added, would need ownership, deletion, and access control infrastructure.

---

## 6. Current Authentication / Ownership

- **Dev seam only:** `app/api/deps.py` — Bearer token must match `DEV_TOKEN` env var, maps to seeded dev user.
- Owner scoping enforced in `AnalysisRunRepository` methods (`get_for_user`, `list_for_user`, `create`, `complete`, `fail`).
- All analysis runs are owner-scoped; cross-user access returns 404 (OW-1).
- No real auth provider integrated; D-AUTH-1 placeholder approved (D1).

---

## 7. Current Privacy Behavior

- Images: not captured → not stored → not transmitted. Privacy impact: minimal.
- Analysis runs: owner-scoped, 404 on cross-user access.
- No image data in DB.
- No raw image data in logs.
- Gaps identified: should image-based scanning be added later, would need:
  - Image ownership attachment to user runs
  - Secure deletion on run cancellation
  - Access control beyond owner-scoping
  - Temporary image storage with expiration

---

## 8. Existing Reusable Components

### 8.1 Flutter

| Component | Location | Reused For |
|---|---|---|
| `CameraPreviewPlaceholder` | `outfit_scan_widgets.dart:6` | Camera UI fallback states |
| `CheckIndicator` | `outfit_scan_widgets.dart:93` | Lighting/framing/posture status |
| `ProcessingStageIndicator` | `outfit_scan_widgets.dart:137` | Processing stage visualization |
| `AnalysisSectionCard` | `outfit_scan_widgets.dart:203` | Analysis section display |
| `DetectedItemChip` | `outfit_scan_widgets.dart:299` | Detected clothing item chip |
| `OutfitScanScreen` | `outfit_scan_screen.dart:12` | Camera capture UI |
| `OutfitProcessingScreen` | `outfit_processing_screen.dart:10` | Mock processing timer UI |
| `OutfitAnalysisScreen` | `outfit_analysis_screen.dart:9` | Analysis results UI |

### 8.2 Backend

| Component | Location | Reused For |
|---|---|---|
| `AnalysisRunRepositorySQL` | `infrastructure/db/repositories.py` | Analysis run CRUD |
| `AnalysisRunRecord` / `AnalysisRunSummary` | `domain/ports/repositories.py` | Data transfer schemas |
| `CreateHairstyleRun` / `CreateGroomingRun` | `application/analysis.py` | Use cases for run creation |
| `AppearanceProfile` | `domain/value_objects.py:66` | Appearance data structure |
| `HairstyleResult` / `GroomingResult` | `domain/value_objects.py:80/126` | Engine output snapshots |
| `CatalogKnowledgeSource` | `infrastructure/external/knowledge.py` | Deterministic look catalog |
| ` CatalogKnowledgeSource.build_knowledge_source()` | `infrastructure/external/knowledge.py:174` | Factory adapter |

### 8.3 Cross-Layer

| Pattern | Location |
|---|---|
| Repository pattern | `domain/ports/repositories.py` + `infrastructure/db/repositories.py` |
| Use case / application layer | `application/analysis.py` |
| Value objects shared between backend and Flutter | `app/models/schemas.py` + `domain/value_objects.py` |
| GoRouter declarative routing | `app/router/app_router.dart` |

---

## 9. Existing Reusable APIs

- `POST /v1/analysis/hairstyle` — profile-only, returns `run_id` asynchronously.
- `GET /v1/analysis/runs/{run_id}` — read run status/result.
- `GET /v1/analysis/runs` — paged history.
- `POST /v1/analysis/grooming` — profile-only, returns `run_id` asynchronously.
- All endpoints enforce owner scoping and reject image uploads.

---

## 10. Existing Analysis-Run Infrastructure

- `analysis_runs` table with full lifecycle: create → pending → completed/failed.
- `AnalysisRunRepository` protocol with `create`, `get_for_user`, `list_for_user`, `complete`, `fail`.
- `AnalysisRunRecord` / `AnalysisRunSummary` dataclasses for serialization.
- 202 `AsyncAccepted` response for async run creation.
- Run completion writes `result` (AppearanceProfile.to_snapshot()) and `completed_at`.
- Run failure writes `error` and marks status `failed`.
- **Critical constraint:** current hairstyle/grooming endpoints are profile-only; images are explicitly rejected (MS10.3).

---

## 11. Missing Capabilities

| Capability | Status |
|---|---|
| Capture image from camera | **EXISTS** (Flutter camera package) |
| Select image from gallery | **MISSING** — "Gallery coming soon" Snackbar |
| Upload image to backend | **MISSING** — backend explicitly rejects images |
| Process image to extract appearance attributes | **MISSING** — no model, no adapter |
| Create analysis run from image capture | **MISSING** |
| Persist appearance profile derived from image | **MISSING** |
| AI/model for face/appearance analysis from photos | **MISSING** |
| Image storage in database | **MISSING** |
| Polling for async analysis completion | **PARTIAL** — mock timers only |
| Real analysis run navigation from image | **MISSING** |

---

## 12. Mock/Placeholder Capabilities

| Component | Classification |
|---|---|
| Processing stage timers (`ProcessingStage.mockStages`) | **MOCK** — deterministic timers, no real processing |
| Analysis data (`OutfitAnalysisData.mock`) | **MOCK** — fully predetermined, hardcoded |
| Camera test mode shortcut | **MOCK** — skips camera in widget tests |
| Backend hairstyle/grooming endpoints | **PARTIAL** — profile-only, explicitly reject images |
| `AnalysisRun.result` population | **PARTIAL** — only from profile-based runs, not images |
| Decision engine confidence formula | **REAL** — deterministic, measurable |

---

## 13. Risks

1. **Image upload without backend support:** If Flutter attempts to upload images to an endpoint that rejects them, errors will occur.
2. **Mock data perceived as real:** Screens display `OutfitAnalysisData.mock` as if it were derived from the captured image, potentially misleading users.
3. **Broken navigation chain:** Image path passed via GoRouter extras could become null if routing changes.
4. **Privacy regression:** Adding image upload without corresponding ownership/deletion infrastructure creates data retention risks.
5. **Test fragility:** Camera-dependent tests have test-mode shortcuts that may not reflect real-user behavior.
6. **Pipeline gap:** No path from "captured image" → "appearance analysis" → "persisted profile" exists in current architecture.

---

## 14. Recommended Minimal Architecture (Current State)

```
USER
  ↓
CAPTURE IMAGE (camera) → local temp path
  ↓
STORE PATH temporarily via GoRouter extras
  ↓
NAVIGATE: scan-outfit → processing (mock) → analysis (mock)
  ↓
NO BACKEND INTERACTION for image-based scan
  ↓
RECOMMENDATION from mock data (OutfitAnalysisData.mock)
```

**Key constraint:** The current architecture is designed as a profile-based system (face shape from user profile), not an image-based system. Adding image capability requires:

1. Backend image upload endpoint (or reworking the profile-only hairstyle/grooming endpoints)
2. Image processing model/adaptor (not implemented)
3. Appearance profile persistence from images
4. New API schemas and routing for image-based analysis runs

**Do not implement.** This audit is read-only.

---