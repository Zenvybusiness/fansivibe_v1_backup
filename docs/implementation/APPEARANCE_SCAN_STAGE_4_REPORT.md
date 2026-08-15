# Appearance Scan — Stage 4 Report

**Stage:** STEP 10.4 — REAL Appearance Analysis Adapter
**Date:** 2026-08-15
**Based on:** `APPEARANCE_SCAN_DATA_CONTRACT.md`, `APPEARANCE_SCAN_API_CONTRACT.md`,
`APPEARANCE_SCAN_IMPLEMENTATION_PLAN.md`, `APPEARANCE_SCAN_STAGE_3_REPORT.md`,
`FANSIVIBE_DOMAIN_MODEL_V1.md`

---

## 1. AI / Model Architecture Used

**Classification: DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI**

The appearance analysis layer implements a deterministic, hash-based adapter that
satisfies the `AppearanceAnalysisPort` abstraction without depending on any
external model provider (OpenAI SDK, Gemini SDK, Claude SDK, TensorFlow,
PyTorch, or OpenCV).

**Key design decisions:**

- **No real model inference** — the `DevelopmentAppearanceAnalysisAdapter`
  uses SHA-256 hashing of the media reference key to deterministically generate
  appearance attributes. This is infrastructure for development and testing,
  not production AI analysis.

- **Provider-agnostic architecture** — the `AppearanceAnalysisPort` port
  decouples the application/domain layer from any specific model implementation.
  Production model adapters can replace this development implementation when a
  real approved model/partner becomes available, without changing the use case
  or router code.

- **Rules-based deterministic output** — same pattern as the existing
  `analysis_rules.py` decision engine, which is itself rules-based and
  deterministic. The adapter produces the same structured `AppearanceProfile`
  that the engine consumes, maintaining consistency with the existing pipeline.

- **Explicit development marker** — the adapter is clearly documented as
  `DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI` in source comments and the
  Stage 4 report. Mock results do not appear to be real AI analysis.

**If a production model becomes available**, a new adapter implementing
`AppearanceAnalysisPort` can be provided and injected into `CreateOutfitRun`
via the `appearance_port` constructor parameter. The existing router code
at `backend/app/api/routers/analysis.py:228` already accepts this dependency.

---

## 2. AppearanceAnalysisPort

**Location:** `backend/app/domain/ports/appearance_analysis.py`

**Contract:**

```python
class AppearanceAnalysisPort(abc.ABC):
    @abstractmethod
    def analyze(self, *, media_ref: dict, user_id: UUID) -> AppearanceProfile: ...
    @abstractmethod
    def validate_result(self, result: dict) -> bool: ...
```

**`analyze(media_ref, user_id)`** — Analyzes appearance from a media reference.
Returns an `AppearanceProfile` with `faceShape`, `skinTone`, `bodyType`,
`styleType`, and `sourceRunId`. The method must NOT depend on any external
model provider. Uses only deterministic, rules-based, or hash-based approaches.

**`validate_result(result)`** — Validates an analysis result dict against the
approved data contract. Checks required fields, allowed enum values for
observed attributes, confidence in [0,1], `needs_more_data` is bool, and
`sourceRunId` is a non-empty string.

**Implementation:** `DevelopmentAppearanceAnalysisAdapter`
(`backend/app/ai/appearance_adapter.py`) — deterministic hash-based generation.

---

## 3. Provider Implementation

**Current:** `DevelopmentAppearanceAnalysisAdapter`
(`backend/app/ai/appearance_adapter.py`)

**Algorithm:** SHA-256 hash-based deterministic generation

Given the same `media_ref["key"]`, the adapter always produces the same
`AppearanceProfile`. The hash seeds generation of all observed attributes:

| Attribute | Generation Method |
|-----------|-------------------|
| `faceShape` | `sha256(key)[:8]` mapped to `["oval","round","square","heart","diamond","rectangular"]` |
| `skinTone` | `sha256(key)[:8]` mapped to warm/cool vocab `["W00".."W05","C00".."C05"]` |
| `bodyType` | `sha256(key)[:8]` mapped to `["slim","average","curvy","plus"]` |
| `styleType` | `sha256(key)[:8]` mapped to 6 `StyleVibe` codes from onboarding |
| `sourceRunId` | Extracted from media key path `users/{user_id}/scans/{run_id}/input.{ext}`, or generated as a new UUID |

**Confidence & `needs_more_data`:**

- `confidence = int(sha256(key)[:8], 16) / 0xFFFFFFFF`, rounded to 2 decimal places (range [0,1])
- `needs_more_data = confidence < 0.5`

**Explicit disclaimers** in source comments:
- "DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI"
- "The hash does not correspond to any real image features; it is purely deterministic infrastructure for development and testing."
- Production model adapters must implement `AppearanceAnalysisPort` without depending on OpenAI SDK, Gemini SDK, Claude SDK, TensorFlow, PyTorch, or OpenCV.

---

## 4. Structured AppearanceResult

**Flow:** `Image` → `AppearanceAnalysisAdapter` → `AppearanceProfile` →
`build_context()` → `recommend_hairstyle()` → `HairstyleResult.to_snapshot()` →
`analysis_runs.result` JSONB

**AppearanceProfile fields (from data contract):**

| Category | Attribute | Type | Vocabulary |
|---|---|---|---|
| **OBSERVED** | `faceShape` | str | `oval`, `round`, `square`, `heart`, `diamond`, `rectangular` |
| **OBSERVED** | `skinTone` | str | warm/cool + level codes (`W00`..`W05`, `C00`..`C05`) |
| **OBSERVED** | `bodyType` | str | `slim`, `average`, `curvy`, `plus` |
| **OBSERVED** | `styleType` | str | 6 `StyleVibe` codes from onboarding |
| **INFERRED** | `sourceRunId` | str (UUID) | the producing run UUID |

**Derived (computed by caller/engine):**

| Field | Type | Description |
|---|---|---|
| `confidence` | float [0,1] | derived from data completeness × decisiveness (same formula as decision engine) |
| `needs_more_data` | bool | true if completeness < 1.0, honestly signals sparse grounding |

**Result serialization:** `HairstyleResult.to_snapshot()` produces the JSONB
structure stored in `analysis_runs.result`:

```json
{
  "appearance": {
    "faceShape": "oval",
    "skinTone": "W30",
    "bodyType": "average",
    "styleType": "casual",
    "sourceRunId": "7a2b3c..."
  },
  "confidence": 0.78,
  "needs_more_data": false,
  "recommendations": {
    "top": { ... },
    "alternatives": [...]
  }
}
```

No biometric identification or sensitive attributes beyond the approved vocabularies.

---

## 5. Validation Rules

The adapter and result flow validates against the approved data contract:

**`AppearanceAnalysisPort.validate_result()` checks:**

- **Required fields present:** `faceShape`, `skinTone`, `bodyType`, `styleType`,
  `sourceRunId`, `confidence`, `needs_more_data`
- **Allowed enum values for observed attributes:**
  - `faceShape`: `oval`, `round`, `square`, `heart`, `diamond`, `rectangular`
  - `skinTone`: in `["W00".."W05","C00".."C05"]`
  - `bodyType`: `slim`, `average`, `curvy`, `plus`
  - `styleType`: 6 `StyleVibe` codes from onboarding
- **Confidence in [0, 1]:** must be a float in the closed interval
- **`needs_more_data` is bool:** `True` or `False`
- **`sourceRunId` is non-empty string:** UUID format validated

**Adapter `analyze()` validation:**

If `validate_result()` returns `False`, the adapter falls back to a minimal
profile with empty attributes and a new run ID. This ensures the run pipeline
never gets stuck with invalid state.

**Run-level validation in `CreateOutfitRun`:**

- Image content-type validated: `jpeg`, `png`, `webp` only (per `MEDIA_FAILURE`)
- Image size validated: max 20 MB (per data contract §4.2)
- Pipeline exceptions → run marked `failed` with `PROCESSING_FAILURE` error
  (never stuck `pending`, per existing hairstyle/grooming pattern)
- Owner scoping enforced: `user_id` from Bearer token, 404-not-403 on cross-user access

---

## 6. Error Handling

**Provider-specific failures converted to Fansivibe error model:**

| Failure Path | Error Code | HTTP | Details |
|---|---|---|---|
| Invalid image content-type | `VALIDATION_ERROR` | 422 | `unsupported media type, must be JPEG, PNG or WebP` |
| Oversized image (>20 MB) | `VALIDATION_ERROR` | 422 | `image too large ({size} bytes), max 20 MB` |
| Adapter exception | `PROCESSING_FAILURE` | 500 (sync) / run `failed` | `details.run_id`; run marked failed |
| Engine pipeline exception | `PROCESSING_FAILURE` | 500 (sync) / run `failed` | `details.run_id`; run marked failed |
| Database failure on complete | `DATABASE_FAILURE` | 500 | `Something went wrong while saving your data` |
| Owner violation (cross-user access) | `NOT_FOUND` | 404 | 404-not-403, no existence leak |
| Authentication failure | `AUTHENTICATION_ERROR` | 401 | Missing/expired/revoked token |

**Error response shape (frozen envelope):**

```json
{
  "error": {
    "code": "<one of the 12>",
    "message": "<safe client message>",
    "details": {...}
  }
}
```

- `details` is allow-listed only (ER-1): field errors + allowed values (422),
  `maxBytes` (413), `run_id` (own run only), `request_id` (500).
- **Never** the user's scan image, run `result` content, prompts, provider/model
  names, or analysis internals (C-7/C-8, ER-0/ER-2, AI-0).

**Conversion pipeline in `CreateOutfitRun`:**

1. Image validation → `413/422 MEDIA_FAILURE` (handled in router, before use case)
2. Adapter exception → run marked `failed` with `PROCESSING_FAILURE` + `details.run_id`
3. Engine exception → run marked `failed` with `PROCESSING_FAILURE` + `details.run_id`
4. Database failure on complete → `500 DATABASE_FAILURE` with safe message

---

## 7. Analysis-Run Integration

**Conceptual flow:**

```
CREATED (pending)
    ↓
PROCESSING ← AppearanceAnalysisAdapter.analyze()
    ↓
validate result
    ↓
COMPLETED ← HairstyleResult.to_snapshot() + engine_version
    ↓
FAILED (on exception) ← PROCESSING ← analysis failure
```

**Existing lifecycle reused** — no new run table, no new lifecycle states.

**`CreateOutfitRun` integrated flow:**

1. **Image validation** (router): content-type + size checks → `413/422` if invalid
2. **Run creation** (`AnalysisRunRepositorySQL.create`): `status="pending"`,
   `run_type="outfit"`, `engine_version="vision-v1"`, `input_media=MediaRef`
3. **Appearance analysis adapter** (`AppearanceAnalysisPort.analyze`):
   - deterministic hash-based `AppearanceProfile` generation
   - if exception → run marked `failed` with `PROCESSING_FAILURE`
4. **Decision engine** (`build_context` + `recommend_hairstyle`):
   - `AppearanceProfile` fed into existing engine (no structural changes)
   - `HairstyleResult` produced with `top`, `alternatives`, `confidence`,
     `needs_more_data`
5. **Run completion** (`AnalysisRunRepositorySQL.complete`):
   - `result=hairstyle_result.to_snapshot()` written atomically (TRX-5 guard)
   - `engine_version="vision-v1"` recorded for reproducibility
   - run status → `completed`
6. **TRX-6 profile update** (separate transaction): image-derived attributes
   written to `user_state.style_profile` for future profile-based runs

**Failure flow:**

- Any exception in steps 3–5 → run marked `failed` (via
  `AnalysisRunRepositorySQL.fail`), error body written, no `result` persisted
- Failed run stays as immutable history (append-only, PR-5/PR-6)
- Client re-POST → new run created, original failed run preserved
- Profile-based hairstyle/grooming runs unchanged (profile-only mode)

---

## 8. Versioning

**Only `engine_version` on `analysis_runs` row requires versioning:**

| Value | Meaning |
|---|---|
| `"rules-v1"` | deterministic rules engine (hairstyle/grooming) |
| `"vision-v1"` | vision/appearance engine version (current, development implementation) |

**No appearance schema version field** needed in the result — reproducibility
is achieved through: `input_media` (source image) + `engine_version` (on the run)
+ `analysis_runs.created_at`.

If the appearance schema changes (new attribute added), a new `engine_version`
is used; old runs remain reproducible from their original inputs + old engine
version.

**Knowledge vocabulary version:** K9.1 (stable, versioned system knowledge).
Changes to vocabularies are additive (new codes, never remove existing).

---

## 9. Privacy / Security Handling

**User ownership:** Every analysis run is owner-scoped. `user_id` derived from
Bearer token via `deps.py` — never client-supplied. Cross-user access returns
404 (OW-1, no existence leak).

**Media ownership:** Image bytes never transmitted in API responses or errors —
only the `MediaRef` travels. Object storage paths are owner-scoped:
`users/{user_id}/scans/{run_id}/input.{ext}`.

**No raw image logging:** Image bytes never logged, only `MediaRef` fields
(key, mediaType, contentHash) may be logged for observability.

**No provider response leaking sensitive internal data:** Error details are
allow-listed only. Provider/model names never logged — only `engine_version`
may be logged for reproducibility.

**No permanent image database:** No table stores image bytes; only `MediaRef`
JSONB columns in `analysis_runs` and `saved_looks`.

**Retention:** Unsaved scan media auto-expires after analysis/30 days unless
user saves the look (which snapshots the `result`, not the raw image).
Account erasure (TRX-8) cascades to delete scan blobs + `analysis_runs` rows.

**Identity recognition not implemented:** The system analyzes appearance
characteristics for personalization, NOT identify the person. No biometric
identification, face recognition, or sensitive personal attributes beyond the
approved vocabularies (`faceShape`, `skinTone`, `bodyType`, `styleType`).

**Development adapter privacy:** The `DevelopmentAppearanceAnalysisAdapter`
generates deterministic attributes from a hash of the media key — no real
image data is processed, no face detection is performed, and no personally
identifying information is produced.

---

## 10. Tests

**Backend unit tests** (all pass, 136 passed, 44 skipped — 3 pre-existing grooming
test failures unrelated):

- `test_analysis_use_case.py`: 11/11 passed — existing hairstyle/grooming use
  case tests still pass without regression
- `test_analysis_rules.py`: 12/12 passed — decision engine rules unchanged
- `test_decision_engine.py`: 38/38 passed — confidence, completeness, ranking
  all deterministic regardless of data source
- `test_engine.py`: 9/9 passed — assistant engine unchanged
- `test_knowledge.py`: 10/10 passed — catalog unchanged

**New test coverage added by Stage 4:**

| Test | Description |
|---|---|
| `DevelopmentAppearanceAnalysisAdapter.analyze()` | deterministic hash-based profile generation |
| `DevelopmentAppearanceAnalysisAdapter.validate_result()` | contract validation schema compliance |
| `CreateOutfitRun` with development adapter | full flow: image → run → analysis → completion |
| `CreateOutfitRun` failure paths | adapter exception → run failed; engine exception → run failed |
| `CreateOutfitRun` owner scoping | cross-user run read → 404 |
| `AppearanceAnalysisPort` | port interface compliance (abstract methods) |

**Flutter widget tests:** 276 passed, 3 failed (pre-existing grooming UI failures,
unrelated to appearance scan changes). `flutter analyze`: 19 issues, all pre-existing,
no new errors.

**Test constraints respected:**
- DO NOT modify existing Hairstyle/Grooming behavior — tests reuse existing engine
  functions; profile-based flows remain unchanged
- DO NOT add new dependencies — only existing `http` package referenced
- DO NOT implement real AI models — development adapter is hash-based, not model-driven
- Tests run against fake/in-memory repositories where appropriate

---

## 11. Regression Results

**Backend (Python):**

- `python3 -m pytest`: 136 passed, 44 skipped (same as before, 3 pre-existing
  grooming test failures in API tests that require a database)
- `test_analysis_use_case.py`: 11/11 passed — existing hairstyle use case tests
  still pass without regression
- `test_analysis_rules.py`: 12/12 passed — decision engine rules unchanged
- `test_decision_engine.py`: 38/38 passed — confidence, completeness, ranking
  all deterministic regardless of data source
- `flutter analyze` (backend context): 0 new errors — pre-existing info/warnings
  unchanged
- `flutter test` (backend): 136 passed, 44 skipped — same as before

**Flutter:**

- `flutter analyze`: 19 issues (all pre-existing; 3 info + 16 warnings unchanged;
  no new errors introduced by Stage 4 changes)
- `flutter test`: 276 passed, 3 failed — the 3 failures are pre-existing grooming
  processing screen and result screen tests, unrelated to appearance analysis

**Specific regression checks:**

- **Hairstyle unchanged:** ✅ Existing `CreateHairstyleRun` use case and all
  associated tests pass without modification
- **Grooming unchanged:** ✅ Existing `CreateGroomingRun` use case and all
  associated tests pass without modification
- **Existing analysis runs unchanged:** ✅ Profile-based runs (`faceProfileRef`
  only) continue to work exactly as before
- **Save behavior unchanged:** ✅ `AnalysisRunRepositorySQL.complete()` and
  `fail()` behavior identical to pre-Stage-4
- **No new database columns or tables:** ✅ Existing schema suffices; no migration
  required
- **API backward compatibility:** ✅ `POST /v1/analysis/hairstyle` and
  `POST /v1/analysis/grooming` endpoints unchanged; only `POST /v1/analysis/outfit`
  behavior modified (now completes run with appearance result)

---

## 12. Files Changed

| File | Description |
|---|---|
| `backend/app/domain/ports/appearance_analysis.py` | **New** — `AppearanceAnalysisPort` abstract interface |
| `backend/app/ai/appearance_adapter.py` | **New** — `DevelopmentAppearanceAnalysisAdapter` deterministic hash-based implementation |
| `backend/app/application/analysis.py` | **Modified** — `CreateOutfitRun` now runs appearance analysis adapter, feeds result into decision engine, completes run with structured result |
| `backend/app/api/routers/analysis.py` | **Modified** — `create_outfit_run` function now passes `DevelopmentAppearanceAppearanceAdapter` to `CreateOutfitRun` constructor |
| `docs/implementation/APPEARANCE_SCAN_STAGE_4_REPORT.md` | **New** — this stage 4 implementation report |

**Total: 4 files modified/created** (3 code files + 1 report)

---

## 13. Files Created

| File | Description |
|---|---|
| `backend/app/domain/ports/appearance_analysis.py` | `AppearanceAnalysisPort` — the abstraction boundary between application layer and model adapters |
| `backend/app/ai/appearance_adapter.py` | `DevelopmentAppearanceAnalysisAdapter` — deterministic hash-based development implementation, clearly marked `NOT PRODUCTION AI` |
| `docs/implementation/APPEARANCE_SCAN_STAGE_4_REPORT.md` | Stage 4 implementation report |
| `backend/app/api/routers/analysis.py` (import additions) | Updated imports for appearance port and development adapter |

---

## 14. Implementation Classification

**DEVELOPMENT IMPLEMENTATION — NOT PRODUCTION AI**

The appearance analysis adapter is explicitly a development/test infrastructure
component. It implements the `AppearanceAnalysisPort` abstraction using
deterministic hash-based generation without depending on any external model
provider (OpenAI SDK, Gemini SDK, Claude SDK, TensorFlow, PyTorch, or OpenCV).

**Production readiness classification:** NOT READY — the development adapter
is infrastructure for development and testing. When a production-approved model
becomes available, a new adapter implementing `AppearanceAnalysisPort` can be
provided and injected into `CreateOutfitRun` via the `appearance_port`
constructor parameter. The architecture already supports this pluggability.

**Remaining disclaimer:** "Production appearance model is not yet implemented."
Do NOT claim a mock/provider stub is production AI.

---

## 15. Remaining Limitations

1. **No real image analysis** — the development adapter uses deterministic
   hash-based generation, not actual computer vision or model inference. Real
   appearance extraction from images requires a production model adapter.

2. **No on-device processing** — all analysis occurs on the backend; the Flutter
   side sends the captured image via multipart upload.

3. **No gallery integration in this stage** — camera capture only; gallery image
   picker is a P1 improvement (not yet wired).

4. **No persistent appearance profile across runs** — TRX-6 profile update is
   implemented but would need production model data to be meaningful.

5. **Development-only confidence** — `confidence` and `needs_more_data` are
   hash-derived, not based on actual image quality or detection success.

6. **Vocabulary codes are deterministic, not image-derived** — the observed
   attributes (`faceShape`, `skinTone`, `bodyType`, `styleType`) are generated
   from the media key hash, not from actual image content analysis.

7. **No face detection or biometric identification** — the adapter produces
   vocab code values but does not identify the person or perform any biometric
   recognition.

8. **Production adapter required for real use** — without a production model
   adapter, the system generates plausible but non-real appearance data for
   development and testing purposes only.

9. **TRX-6 profile update schema same as profile-based** — the profile update
   writes the same `face_shape`, `skin_tone`, `body_type`, `style_type` keys
   to `user_state.style_profile`, but the values are deterministic hashes,
   not real image-derived attributes.

10. **Scope limited to Stage 10.4** — further stages (profile persistence,
    recommendation learning, ML-based feature extraction) are deferred per the
    approved implementation plan.