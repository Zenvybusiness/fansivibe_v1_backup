# REAL Appearance Scan — Target Pipeline

**Repository:** fansivibe_v1_backup
**Stage:** STEP 10 — Target architecture definition only
**Date:** 2026-08-15
**Rule:** DO NOT modify application code, database, API contracts, dependencies, AI models, or UI.

---

## Pipeline Overview

```
USER
  ↓
CAPTURE IMAGE
  ↓
UPLOAD / MEDIA HANDLING
  ↓
CREATE ANALYSIS RUN
  ↓
PROCESS IMAGE
  ↓
APPEARANCE ANALYSIS
  ↓
STRUCTURED RESULT
  ↓
PERSIST APPEARANCE PROFILE
  ↓
DECISION ENGINE
  ↓
RECOMMENDATION
  ↓
RESULT UI
```

Each stage is classified as: **EXISTS** (already in repo), **PARTIAL** (partially implemented, incomplete), **MISSING** (not implemented), or **MOCK** (simulated/placeholder).

---

## Stage 1: USER

| Aspect | Description |
|---|---|
| **Existing implementation** | Onboarding flow with `vibe_select_screen.dart`, `photo_capture_screen.dart`, `ai_analysis_screen.dart`, `your_analysis_screen.dart`. User enters the app and selects appearance scanning path. |
| **Required change** | None for this stage — already functional. |
| **Data input** | User intent to scan appearance. |
| **Data output** | User proceeds to camera screen or profile setup. |
| **Owner layer** | Presentation (Flutter screens). |
| **API boundary** | GoRouter navigation (`/onboarding/photo-capture` → `/scan-outfit`). |
| **Persistence requirement** | None. |
| **Test requirement** | Existing widget tests for onboarding screens. |

**Classification: EXISTS**

---

## Stage 2: CAPTURE IMAGE

| Aspect | Description |
|---|---|
| **Existing implementation** | `OutfitScanScreen` with `CameraController` (camera package). `takePicture()` captures JPEG to temp local path. Test mode shortcut navigates directly to processing. |
| **Required change** | Verify camera permissions at app startup; add gallery/image picker selection as alternative to camera capture. |
| **Data input** | User triggers capture from `OutfitScanScreen`. |
| **Data output** | `String?` — local file path of captured image (e.g. `/data/local/tmp/path.jpg`). May be `null` on failure. |
| **Owner layer** | Presentation (`OutfitScanScreen._handleCapture`), data (`camera` package). |
| **API boundary** | Flutter-only; no backend API at this stage. |
| **Persistence requirement** | Temporary local file only. No DB persistence. |
| **Test requirement** | Existing `outfit_scan_screen_test.dart` tests capture navigation; test mode skips camera. |

**Classification: EXISTS (camera capture), PARTIAL (no gallery picker)**

**P1 improvement:** Add `image_picker` alternative to capture from gallery.

---

## Stage 3: UPLOAD / MEDIA HANDLING

| Aspect | Description |
|---|---|
| **Existing implementation** | Image path passed via GoRouter `extra` through processing → analysis screens. **No upload attempted** — backend `POST /v1/analysis/hairstyle` explicitly rejects images (validation error "image upload is not available in this version"). |
| **Required change** | Build backend image upload endpoint; add Flutter upload mechanism; update backend validation to accept images for analysis runs. |
| **Data input** | Local image path (from capture) or image bytes. |
| **Data output** | `analysis_runs.input_media` stored as JSONB (metadata: path, size, mime type, hash); or `error` if upload fails. |
| **Owner layer** | Flutter: `OutfitProcessingScreen`, `OutfitAnalysisScreen`. Backend: `app/api/routers/analysis.py`, `app/application/analysis.py`. |
| **API boundary** | `POST /v1/analysis/outfit` (new) or extend existing analysis endpoints to accept `UploadFile`. Current: `POST /v1/analysis/hairstyle` rejects images. |
| **Persistence requirement** | Store image reference (path/hash) in `analysis_runs.input_media` JSONB. |
| **Test requirement** | Integration test: capture → upload → run creation. Mock upload for unit tests. |

**Classification: MISSING (no upload mechanism exists)**

**P0 blocker:** Backend must accept image uploads before Flutter can send them. Current backend explicitly rejects images.

**P1 improvement:** Add `multipart/form-data` upload endpoint that stores image metadata and triggers async processing.

**P2 future improvement:** Image preprocessing (resize, format conversion) before upload.

---

## Stage 4: CREATE ANALYSIS RUN

| Aspect | Description |
|---|---|
| **Existing implementation** | `POST /v1/analysis/hairstyle` and `POST /v1/analysis/grooming` create runs, but these are **profile-only passes** — they require `faceProfileRef` and reject images. No "outfit/image-based" run creation endpoint exists. |
| **Required change** | New use case / endpoint: `POST /v1/analysis/outfit` that accepts image upload, creates `analysis_run` with `run_type="outfit"`, `input_media` populated, status `pending`. |
| **Data input** | Image file/metadata + optional `faceProfileRef` (may be omitted for image-based) + `user_id` from auth. |
| **Data output** | `run_id` (UUID), returned as `202 AsyncAccepted`. Run created with status `pending`. |
| **Owner layer** | Backend: `app/application/analysis.py` (new use case: `CreateOutfitRun`). Routers: `app/api/routers/analysis.py` (new endpoint). |
| **API boundary** | `POST /v1/analysis/outfit` → `202 {run_id}`. Request: `image` (UploadFile) + optional `faceProfileRef`. Response: `AsyncAccepted`. |
| **Persistence requirement** | `analysis_runs` row created: `user_id`, `run_type="outfit"`, `status="pending"`, `engine_version="vision-v1"`, `input_media` = `{path, size, mime, hash}`. |
| **Test requirement** | Unit test: use case creates run with image input. Integration test: upload image → run created with pending status. |

**Classification: MISSING (no image-based run creation)**

**P0 blocker:** No `CreateOutfitRun` use case or `POST /v1/analysis/outfit` endpoint exists. Backend must be extended.

**P1 improvement:** Add use case that creates run with image input_media, similar pattern to `CreateHairstyleRun` but accepting image instead of rejecting it.

**P2 future improvement:** Support optional `faceProfileRef` alongside image for hybrid profile+image runs.

---

## Stage 5: PROCESS IMAGE

| Aspect | Description |
|---|---|
| **Existing implementation** | **MOCK** — `OutfitProcessingScreen` uses `ProcessingStage.mockStages` with fixed timers (milliseconds). No real image processing. No backend processing service. |
| **Required change** | Build async image processing pipeline: Flutter uploads image → backend receives image → runs AI model (or rules-based engine) → returns analysis result. |
| **Data input** | `input_media` from `analysis_runs` (image path/metadata). |
| **Data output** | `analysis_runs.result` populated with structured appearance analysis (face shape, hair characteristics, etc.) + `completed_at` set. |
| **Owner layer** | Backend: `app/domain/services/analysis_rules.py` (extend for image input), or new `app/ai/vision.py` adapter. Flutter: none (backend handles processing). |
| **API boundary** | Backend internal: use case completes run with result. No new HTTP endpoint needed if processing is internal to run completion. |
| **Persistence requirement** | `analysis_runs.complete()` writes `result` JSONB and `completed_at`. Result schema: `AppearanceProfile` + decision engine output. |
| **Test requirement** | Unit test: use case completes run with image-derived result. Integration test: upload → process → run marked completed. |

**Classification: MOCK (processing screen is simulated timers)**

**P0 blocker:** No image processing pipeline exists — neither Flutter upload nor backend AI model.

**P1 improvement:** Replace mock timers with real processing flow. Backend: integrate image analysis model or rules-based adaptation. Flutter: replace processing UI with polling for run completion.

**P2 future improvement:** On-device preliminary analysis (lightweight features) before upload.

---

## Stage 6: APPEARANCE ANALYSIS

| Aspect | Description |
|---|---|
| **Existing implementation** | **MISSING** — No code that extracts appearance attributes from images. The decision engine (`analysis_rules.py`) operates on `AppearanceProfile` populated from `user_state.style_profile`, not from images. |
| **Required change** | Implement image → appearance attributes pipeline: computer vision model or rules-based extraction of: face shape, skin tone, hair characteristics (length, texture, color), facial hair presence. |
| **Data input** | Image file (from `analysis_runs.input_media`). |
| **Data output** | `AppearanceProfile` with: `faceShape`, `skinTone`, `bodyType`, `styleType` populated from image data. Also hair-specific attributes if relevant. |
| **Owner layer** | Backend: new `app/ai/vision/` adapter or extend `app/domain/services/`. |
| **API boundary** | Internal: `AppearanceProfile` value object populated with image-derived data. |
| **Persistence requirement** | `AppearanceProfile` stored in `analysis_runs.result` via `to_snapshot()`, and/or in `user_state.style_profile` for future runs. |
| **Test requirement** | Unit test: image input → `AppearanceProfile` output. Regression test: existing profile-based runs unchanged. |

**Classification: MISSING (no image → appearance extraction)**

**P0 blocker:** No model or rules code exists to extract appearance from images. Backend cannot populate `AppearanceProfile` from images.

**P1 improvement:** Implement rules-based appearance extraction from basic image features (if model not available), or integrate a lightweight FFI/CV model. Must only use attributes already supported by the domain model (face shape, skin tone, body type, style type — per the audit's constraint "DO NOT invent medical/biometric attributes").

**P2 future improvement:** ML-based face/appearance feature extraction.

---

## Stage 7: STRUCTURED RESULT

| Aspect | Description |
|---|---|
| **Existing implementation** | **EXISTS (rules-based)** — `HairstyleResult` and `GroomingResult` value objects in `domain/value_objects.py` define the structured result schema. `to_snapshot()` method serializes to dict for DB storage. The decision engine produces these from `AppearanceProfile` + catalog. |
| **Required change** | Extend result schema to also carry image-derived appearance data. The `AppearanceProfile` within `HairstyleResult`/`GroomingResult` must be populated from image analysis (Stage 6 output), not just from user profile. |
| **Data input** | `AppearanceProfile` from Stage 6 (image-derived). |
| **Data output** | `HairstyleResult` or `GroomingResult` with: `appearance.faceShape` etc. populated, `top`/alternatives recommendations, `confidence` (derived), `needs_more_data` (if sparse). `to_snapshot()` for DB `result` column. |
| **Owner layer** | Backend: `app/domain/services/analysis_rules.py` (already produces `HairstyleResult`/`GroomingResult`). Value objects: `app/domain/value_objects.py` (already defined). |
| **API boundary** | `analysis_runs.result` JSONB = `HairstyleResult.to_snapshot()` or `GroomingResult.to_snapshot()`. API schemas: `app/api/schemas/analysis.py` (`AnalysisRun.result` already has `Optional[dict]`). |
| **Persistence requirement** | `analysis_runs.result` written by `complete_analysis_run` SQL function or repository `complete()` method. |
| **Test requirement** | Unit test: result snapshot round-trip (profile-derived). Unit test: result snapshot round-trip (image-derived, once Stage 6 is built). |

**Classification: PARTIAL (result schema exists, but populated from profile not images)**

**P1 improvement:** Once Stage 6 produces image-derived `AppearanceProfile`, the existing `HairstyleResult`/`GroomingResult` will automatically work — no schema change needed, just data population change.

**P2 future improvement:** Add additional fields to result (e.g., `color_palette`, `style_notes`) if domain expands.

---

## Stage 8: PERSIST APPEARANCE PROFILE

| Aspect | Description |
|---|---|
| **Existing implementation** | `AppearanceProfile` value object in `domain/value_objects.py:66` defines the schema. `user_state.style_profile` JSONB stores `face_shape`, `skin_tone`, `body_type`, `style_type` as sparse keys. `analysis_runs.result` JSONB stores snapshot via `to_snapshot()`. |
| **Required change** | Ensure `AppearanceProfile` is persisted both: (a) in `analysis_runs.result` (already works via `to_snapshot()`), and (b) in `user_state.style_profile` for future run grounding (so subsequent runs don't suffer `INSUFFICIENT_USER_DATA`). |
| **Data input** | `AppearanceProfile` from Stage 7 (image-derived or profile-derived). |
| **Data output** | `user_state.style_profile` updated with `face_shape`, `skin_tone`, `body_type`, `style_type` keys. `analysis_runs.result` updated with full snapshot. |
| **Owner layer** | Backend: `app/application/analysis.py` (use cases `CreateHairstyleRun`/`CreateGroomingRun` already populate `AppearanceProfile` from `style_profile`). Also `app/infrastructure/db/repositories.py` for `UserStateRepository`. |
| **API boundary** | `GET /v1/users/me` returns `UserProfileRecord` with `style_profile` containing appearance keys. `POST /v1/analysis/...` use cases populate profile from result. |
| **Persistence requirement** | SQL: `UPDATE user_state SET style_profile = ... WHERE user_id = ...`. `analysis_runs.result` already handled by `complete()`. |
| **Test requirement** | Unit test: style_profile updated after image-based run. Unit test: analysis_run.result populated after image-based run. |

**Classification: PARTIAL (profile exists but sparse; image → profile persistence not wired)**

**P0 blocker:** No code persists `AppearanceProfile` from image analysis to `user_state.style_profile`. Future runs would still hit `INSUFFICIENT_USER_DATA`.

**P1 improvement:** After Stage 6 produces image-derived `AppearanceProfile`, add use case step to write it to `user_state.style_profile`. This enables subsequent profile-based runs without needing images.

**P2 future improvement:** Automatic profile merging (image-derived + existing profile preferences).

---

## Stage 9: DECISION ENGINE

| Aspect | Description |
|---|---|
| **Existing implementation** | **REAL** — Rules-based decision engine in `app/domain/services/analysis_rules.py`. Full pipeline: ContextBuilder → CandidateGeneration → Filtering → Scoring → Ranking → Explanation → Recommendation. Deterministic confidence derivation (`derive_confidence`). Uses `KnowledgeSource` (catalog). |
| **Required change** | Wire image-derived `AppearanceProfile` (Stage 6) into the engine instead of/alongside profile-derived profile. The engine itself requires no structural change — it accepts `AppearanceProfile` as input. The change is in the use case that feeds it. |
| **Data input** | `AppearanceProfile` (from Stage 6: image-derived). `HairstylePreferences` / `DecisionContext` optional. `KnowledgeSource` (catalog). |
| **Data output** | `HairstyleResult` or `GroomingResult` with recommendations, confidence, `needs_more_data`. |
| **Owner layer** | Backend: `app/application/analysis.py` (`CreateHairstyleRun`/`CreateGroomingRun` use cases). The engine functions (`recommend_hairstyle`/`recommend_grooming`) are reuse-as-is. |
| **API boundary** | Input: `AppearanceProfile` in use case call. Output: `HairstyleResult`/`GroomingResult` with `to_snapshot()` for DB storage. |
| **Persistence requirement** | Result written to `analysis_runs.result` via `complete()`. No additional persistence needed beyond existing. |
| **Test requirement** | Existing unit tests for `recommend_hairstyle`/`recommend_grooming` (test_decision_engine.py, test_grooming_engine.py). Add tests with image-derived `AppearanceProfile`. |

**Classification: EXISTS (engine rules-based, deterministic)**

**P1 improvement:** Route image-derived `AppearanceProfile` through existing engine — no engine changes needed, just use case wiring.

**P2 future improvement:** Add preference-based filtering using user's saved look preferences (already supported by engine).

---

## Stage 10: RECOMMENDATION

| Aspect | Description |
|---|---|
| **Existing implementation** | **EXISTS (rules-based cards)** — `SuggestionCard` in `models/schemas.py` and `catalog.py`. Assistant engine (`engine.py`) produces cards from `HairstyleResult`/`GroomingResult`. Flutter UI widgets: `outfit_scan_widgets.dart` `DetectedItemChip`, `AnalysisSectionCard`, etc. |
| **Required change** | Feed image-derived recommendations through existing card/UI pipeline. The recommendation data flow (result → engine → cards → UI) is already wired for profile-derived data; just change the input source. |
| **Data input** | `HairstyleResult`/`GroomingResult` from Stage 9 (engine output). |
| **Data output** | Structured cards: title, subtitle, score, items, action. Displayed in `OutfitAnalysisScreen` or new result screen. |
| **Owner layer** | Backend: `app/data/catalog.py` (look catalog), `app/ai/engine.py` (assistant orchestration). Flutter: `outfit_analysis_screen.dart`, `outfit_scan_widgets.dart`, `assistant_screen.dart`. |
| **API boundary** | Backend: `HairstyleResult`/`GroomingResult` → serialized JSON. Flutter: `SuggestionCard` model in `app/models/schemas.dart` mirror. |
| **Persistence requirement** | None — recommendations are ephemeral UI display. May be saved to wardrobe via `LearningService.instance.addSavedLook()`. |
| **Test requirement** | Existing widget tests for analysis screens. Assistant test for card generation. |

**Classification: EXISTS (card UI pipeline already built)**

**P1 improvement:** Route engine output through existing UI — no UI changes needed, just input source change (image-derived vs profile-derived `AppearanceProfile`).

**P2 future improvement:** Learn from user acceptance of recommendations (learning_signals integration).

---

## P0 Blockers (must resolve before any image-based scan can work)

1. **Backend image upload endpoint** — Current `POST /v1/analysis/hairstyle` explicitly rejects images. New endpoint `POST /v1/analysis/outfit` needed that accepts `UploadFile`, stores `input_media`, and triggers async processing.
2. **Image → Appearance extraction model/rules** — No code exists to convert a captured image into `AppearanceProfile` (face shape, skin tone, etc.). Must implement before Stage 6.
3. **Analysis run creation from image** — No use case creates `analysis_run` with `run_type="outfit"` and populated `input_media`. Must implement Stage 4.

## P1 Improvements (should improve once P0 resolved)

1. Replace `OutfitProcessingScreen` mock timers with real polling for analysis run completion.
2. Persist image-derived `AppearanceProfile` to `user_state.style_profile` for future profile-based runs.
3. Add gallery/image picker alternative to camera capture in `OutfitScanScreen`.
4. Add `faceProfileRef` optional support alongside image in new outfit analysis endpoint.

## P2 Future Improvements (nice-to-have after P0+P1)

1. On-device preliminary feature extraction before upload (reduce bandwidth).
2. ML-based face/appearance feature extraction for more accurate profiles.
3. User preference learning from accepted/rejected recommendations.
4. Cross-run appearance trend tracking (historical `appearance` evolution per user).
5. LLM enrichment of recommendation rationale (currently optional, structure-preserving only).

---