# REAL Appearance Scan API Contract

**Repository:** fansivibe_v1_backup
**Stage:** STEP 10 — API contract design only
**Date:** 2026-08-15
**Rule:** DO NOT modify application code, database, API contracts, dependencies, AI models, or UI.

---

## STEP 5 — API CONTRACT

Design the minimum API required for the REAL Appearance Scan. Prefer existing endpoints and patterns. Determine whether the current API can support the required operations, and document new endpoints if genuinely required.

### 5.1 Existing Endpoints — Reused

All existing analysis endpoints are reused with extensions, not replaced:

| Endpoint | Method | Purpose | Reuse Notes |
|---|---|---|---|
| `GET /v1/analysis/runs/{run_id}` | auth | Read one run | Reads appearance scan run status/result; owner-scoped (OW-1, 404-not-403) |
| `GET /v1/analysis/runs` | auth | List runs | Lists user's appearance scan history; optional `?run_type=` filter |
| `POST /v1/analysis/hairstyle` | auth | Create hairstyle run | **Extended** to accept image + produce appearance attributes (faceShape/skinTone/bodyType/styleType) in result; profile-only mode via `faceProfileRef` |
| `POST /v1/analysis/grooming` | auth | Create grooming run | Accepts options JSON (no image needed); recommendations only, no profile projection |
| `POST /v1/auth/*` | public/auth | Auth | Required for owner scoping; token → `user_id` via `deps.py` |

### 5.2 New Endpoint — Genuinely Required

| Field | Specification |
|---|---|
| **METHOD** | `POST` |
| **PATH** | `/v1/analysis/outfit` |
| **AUTHENTICATION** | Bearer token → `user_id` via `deps.py` (auth-required) |
| **REQUEST** | `multipart/form-data`:
  - `image` (required): file — the captured appearance photo
  - `faceProfileRef?` (optional): UUID — run a recommendation-only pass over the stored FaceProfile (profile-only mode, no new face attributes)
  - [typed context fields] (optional) — per catalog §12.11, finalized at M2/P2 implementation |
| **RESPONSE** | `202 Accepted` — `{ "run_id": "UUID" }` (AsyncAccepted, no envelope) |
| **ERRORS** | `401` (AUTHENTICATION_ERROR), `413/422 MEDIA_FAILURE` (image too large/unsupported), `422 VALIDATION_ERROR` (no image, invalid faceProfileRef), `503 EXTERNAL_SERVICE_FAILURE` (provider), `429 RATE_LIMITED` |
| **OWNERSHIP** | `user_id` from auth token; owner-scoped (OW-1); 404-not-403 on run read/detail |
| **IDEMPOTENCY** | **Never idempotent** — each submission creates a new run (API-11/§11: analysis submissions are never idempotent). A retry is a new submission. |
| **STATUS CODES** | `202` (accepted, poll), `401` (auth), `404` (not found/account gone), `413` (payload too large), `422` (validation), `429` (rate limited), `503` (external service) |

### 5.3 API Contract — Image Submission (S-1 — Create Outfit Scan)

```
POST /v1/analysis/outfit
Content-Type: multipart/form-data

Request body parameters:
- image: <file> (required; outfit/capture photo; the evidence for analysis)
  - Content-Type: image/jpeg, image/png, or image/webp
  - Size: pre-checked against maxBytes limit (e.g. ≤ 20 MB vision input)
  - If content-type unsupported → 413/422 MEDIA_FAILURE (details.maxBytes)
  - If image missing → 422 VALIDATION_ERROR (details: field_errors)
- faceProfileRef?: <UUID> (optional; profile-only pass over stored FaceProfile)
  - If present and image absent → profile-only pass (no new face attributes)
  - If present and image present → 422 VALIDATION_ERROR (image and faceProfileRef mutually exclusive per catalog §12.11)
- [typed context fields] (optional) — per catalog §12.11, finalized at M2/P2

Response: 202 Accepted — { "run_id": "7a2b3c..." }
```

**Backend behavior on S-1:**

1. Validate `image` content-type/size pre-run → `413/422 MEDIA_FAILURE` if invalid.
2. Perform **upload-then-insert** (TRX-1): blob → object storage (`users/{user_id}/scans/{run_id}/input.{ext}`) → `MediaRef` → `analysis_runs.input_media`.
3. Create `analysis_run` row:
   - `user_id` from auth token
   - `run_type = "outfit"`
   - `status = "pending"`
   - `engine_version = "vision-v1"` (or `"rules-v1"` if using rules engine for appearance)
   - `input_media = {key, mediaType, ...}` (MediaRef)
4. Return `202 {run_id}`.

### 5.4 API Contract — Hairstyle with Image (S-2 — Create Face → Hairstyle Scan)

The existing `POST /v1/analysis/hairstyle` is extended to accept an `image` part in addition to the optional `faceProfileRef`:

```
POST /v1/analysis/hairstyle
Content-Type: multipart/form-data

Request body parameters:
- image: <file> (required for image-based pass; mutually exclusive with faceProfileRef)
  - Same content-type/size validation as S-1
  - If image + faceProfileRef both present → 422 VALIDATION_ERROR
- faceProfileRef?: <UUID> (optional; profile-only pass over stored FaceProfile)
  - If present and image absent → recommendation pass over already-stored current profile (no new face attributes)
  - If present → `result.appearance` may be populated from stored profile, not from image

Response: 202 Accepted — { "run_id": "..." }
```

**Two modes of operation:**

- **With image** (image-based pass): The run does face analysis → appearance attributes (faceShape/skinTone/bodyType/styleType) → hairstyle recommendations in one async run. Completion applies attributes to `styleProfile` via TRX-6.
- **Without image, with faceProfileRef** (profile-only pass): Recommendation pass over already-stored current profile. Same endpoint, different input. No new face attributes produced; `result.appearance` may be omitted or populated from existing profile.

### 5.5 API Contract — Grooming (S-3 — Create Grooming Scan)

```
POST /v1/analysis/grooming
Content-Type: application/json

Request body parameters:
{
  "options": {
    "faceShape": "oval",         // from the grooming input vocabulary (GroomingOption vocab codes)
    "beardStyle": "full_beard",  // from the grooming input vocabulary
    "density": "medium",         // from the grooming input vocabulary
    "color": "dark_brown"        // from the grooming input vocabulary
  }
}

- Every option must be a valid GroomingOption vocab code (K9.1); unknown/absent code → 422 with allowed values in details.
- `options` object required; missing → 422.

Response: 202 Accepted — { "run_id": "..." }
```

- No image required — grooming options are user preferences (vocab ids only).
- Result carries recommendations only (no profile projection change by default).
- Same async pattern: `202 {run_id}` → poll `GET /v1/analysis/runs/{run_id}`.

### 5.6 API Contract — Polling and Result Retrieval (S-5 / S-6)

```
GET /v1/analysis/runs/{run_id}
```

- **While `pending`**: returns `{run_id, run_type, status, created_at}` — no `result`, no `error`.
- **When `completed`**: returns full `AnalysisRun` DTO with `result` (immutable snapshot) + `engine_version`.
- **When `failed`**: returns `{run_id, run_type, status, created_at, completed_at, error}` — no `result`.

```
GET /v1/analysis/runs
```

- **List runs** for the authenticated user, paged, with optional `?run_type=` filter (valid run_types codes: `outfit`, `hairstyle`, `grooming`).
- **Summary rows** omit `result`/`error` (PR-5, no history detail leak).
- Query params: `?run_type=&sort=created_at&page=&page_size=` (default page=1, page_size=20, max=100).

### 5.7 API Contract — Error Reference for Appearance Scan Surface

| `error.code` | HTTP | When | Notes |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | bad image / no face detected (S-1/S-2); invalid grooming option (S-3); bad UUID/filter (S-5/S-9); derived-without-run (R-2) | field errors + allowed values in `details` |
| `MEDIA_FAILURE` | 413/422 | image too large / unsupported content-type (S-1/S-2, S-4) | `details.maxBytes`; pre-run check |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | run not owned / never existed; account gone | 404-not-403, no existence leak |
| `EXTERNAL_SERVICE_FAILURE` | 502/503 | AI provider/submission failure; object storage | C-8: no provider internals |
| `PROCESSING_FAILURE` | 500 (sync) / run `failed` | analysis pipeline failure (after 1 automatic retry) | `details.run_id`; the run is a historical failure |
| `RATE_LIMITED` | 429 | any endpoint | + `Retry-After` |
| `INSUFFICIENT_USER_DATA` | 422 | decision needs more user data (profile-only pass without face attributes) | `details.missing` |

### 5.8 Auth, Ownership, and Privacy

| Requirement | Endpoints |
|---|---|
| **Auth** (Bearer → `user_id`) | `POST /v1/analysis/outfit`, `POST /v1/analysis/hairstyle`, `POST /v1/analysis/grooming`, `GET /v1/analysis/runs/{run_id}`, `GET /v1/analysis/runs` |
| **Public** | none in this surface |
| **Authorization** | **owner-only (OW-1)** with **404-not-403**: every run is scoped to the caller's `user_id`; another user's `run_id` → `404` |
| **Face/outfit media** | **CRITICAL-sensitivity** appearance data: HTTPS only, owner-only, never cached on shared storage, image bytes never logged/echoed (MS10.3, ER-4) — only `MediaRef` travels |

### 5.9 The Analysis Lifecycle (No New Endpoint)

The full scan lifecycle uses existing endpoints; no new endpoint is needed beyond `POST /v1/analysis/outfit`:

```
S-1/S-2 submit image (multipart) ──202 {run_id}──►  S-5 poll ──► completed
    │ (blob → object storage TRX-1; run pending)      │          │ result snapshot (immutable, engine_version)
    │                                                  │          ▼
    │                                        S-6 result  ◄── S-9 history list (all scans, ?run_type=)
    ▼                                          + current profile only for face: TRX-6 → styleProfile
S-3 grooming (options JSON) ──202 {run_id}──► S-5 poll ──► recommendations only (no projection)
S-7 retry failed: auto 1x (transient) → still failed?  client re-POST → NEW run (failed run stays history)
S-8 delete: runs append-only (no DELETE); unsaved scan media auto-expires (retention job); erasure only (TRX-8)
```

---

## STEP 6 — APPEARANCE RESULT CONTRACT

Define the structured result returned after analysis, separating Analysis Result from Persisted User Profile from Recommendation Input.

### 6.1 Analysis Result (from analysis run completion)

The `analysis_runs.result` JSONB contains the **Analysis Result** — the immutable snapshot written at completion (TRX-5).

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
    "top": {
      "id": "leather-jacket-formal",
      "name": "Leather Jacket Formal",
      "description": "A classic leather jacket for formal occasions",
      "matchScore": 0.92,
      "reasons": ["Strong face shape match", "Formal style vibe"],
      "stylingTips": "Keep accessories minimal",
      "maintenance": "Wipe clean regularly",
      "bestFor": "Daily wear"
    },
    "alternatives": [
      {
        "id": "cotton-blazer-business",
        "name": "Cotton Blazer Business",
        "description": "A crisp cotton blazer",
        "matchScore": 0.78,
        "reasons": ["Good color harmony"],
        "stylingTips": "Pair with a white shirt",
        "maintenance": "Dry clean only",
        "bestFor": "Work environment"
      }
    ]
  }
}
```

### 6.2 Analysis Result — Field Details

| Field | Type | Nullable | Description |
|---|---|---|---|
| `appearance.faceShape` | str | nullable | Vocab code: `oval`, `round`, `square`, `heart`, `diamond`, `rectangular` |
| `appearance.skinTone` | str | nullable | Vocab code (warm/cool + level) |
| `appearance.bodyType` | str | nullable | Vocab code: `slim`, `average`, `curvy`, `plus` |
| `appearance.styleType` | str | nullable | `StyleVibe` code (6 values from onboarding) |
| `appearance.sourceRunId` | str (UUID) | nullable | The `run_id` that produced these attributes — provenance |
| `confidence` | float [0,1] | not nullable | Deterministic: 50% completeness + 50% top-pick decisiveness |
| `needs_more_data` | bool | not nullable | True if completeness < 1.0; honestly signals sparse profile |
| `recommendations.top` | dict | not nullable | Single best recommendation snapshot |
| `recommendations.alternatives` | list[dict] | nullable | Alternate recommendations (may be `[]`) |

### 6.3 Persisted User Profile (separate from result)

The **Persisted User Profile** is `user_state.style_profile` — the current face profile projection. Updated at completion via TRX-6 (separate transaction from run completion).

```json
{
  "face_shape": "oval",
  "skin_tone": "W30",
  "body_type": "average",
  "style_type": "casual",
  "source_run_id": "7a2b3c..."
}
```

- **Distinct from `analysis_runs.result`**: The profile is **mutable** (latest-wins acceptance), the run result is **immutable** (never overwritten).
- **`source_run_id`** in the profile links to the producing run — enables "retake analysis" = new run, never mutation of old.
- **Written by TRX-6** after the run is completed (TRX-5). The profile may be edited later via `PATCH /v1/users/me` (R-2), but derived fields require `sourceRunId`.

### 6.4 Recommendation Input (from result)

The **Recommendation Input** is the `HairstyleResult` or `GroomingResult` extracted from the `analysis_runs.result`. It feeds the decision engine and card UI.

```json
// Extracted from result.recommendations
{
  "top": {
    "id": "leather-jacket-formal",
    "name": "Leather Jacket Formal",
    "description": "A classic leather jacket for formal occasions",
    "matchScore": 0.92,
    "reasons": ["Strong face shape match", "Formal style vibe"],
    "stylingTips": "Keep accessories minimal",
    "maintenance": "Wipe clean regularly",
    "bestFor": "Daily wear"
  },
  "alternatives": [...],
  "confidence": 0.78,
  "needs_more_data": false
}
```

- **Flow**: `analysis_runs.result` → extract `recommendations` + `confidence` → `recommend_hairstyle()` or `recommend_grooming()` engine → `HairstyleResult`/`GroomingResult` → `SuggestionCard` UI.
- **Do not expose** internal model implementation details (engine version, raw signals) through the public API — only the serialized snapshot.

### 6.5 Versioning

- **`engine_version`** on the `analysis_run` row (e.g. `"vision-v1"`, `"rules-v1"`). This is the only version field — it provides reproducibility trace (PR-6).
- **No appearance schema version field** needed in the result — the `engine_version` on the run suffices for reproducibility.
- If the appearance schema changes, a new `engine_version` is used; old runs remain reproducible from `input_media` + `engine_version`.

### 6.6 Provenance / Source

Every `analysis_runs.result` carries:

- `appearance.sourceRunId` → the producing `run_id`
- `analysis_runs.engine_version` → the model/engine version
- `analysis_runs.created_at` → when the run was submitted

This enables full reproducibility: given the same inputs + engine version, the result can be re-derived.

### 6.7 Nullable Behavior

- **`appearance.*` fields**: nullable — if the image analysis fails to detect an attribute, the field is omitted (not set to `null` string; the key may be absent).
- **`confidence`**: always present (computed deterministically, minimum 0.0).
- **`needs_more_data`**: always present (computed deterministically).
- **`recommendations.top`**: always present (even if the catalog has only one look).
- **`recommendations.alternatives`**: may be `[]` (empty list) if only one candidate remains after filtering.

### 6.8 Model/Knowledge Version

- The `analysis_runs.engine_version` field serves as the model/knowledge version.
- Currently: `"rules-v1"` (deterministic rules engine) or `"vision-v1"` (if an FFI/Vision model is integrated).
- This version is exposed in the `AnalysisRun` DTO and echoed in poll/result reads — enables clients to know which model produced the result.

---

## STEP 7 — DECISION ENGINE INTEGRATION

Define how the appearance result becomes Decision Engine context.

### 7.1 Target Pipeline

```
Appearance Analysis
    ↓
Structured Appearance Data (AppearanceProfile)
    ↓
Context Builder
    ↓
Existing Decision Engine
    ↓
Recommendation
```

### 7.2 Wiring the Appearance Result

1. **After analysis run completion**, `analysis_runs.result` contains the `AppearanceProfile` snapshot + confidence + needs_more_data + recommendations.

2. **Extract the `AppearanceProfile`** from the result:
   ```python
   appearance = AppearanceProfile(
       faceShape=result["appearance"]["faceShape"],
       skinTone=result["appearance"]["skinTone"] or "",
       bodyType=result["appearance"]["bodyType"] or "",
       styleType=result["appearance"]["styleType"] or "",
       sourceRunId=result["appearance"]["sourceRunId"],
   )
   ```

3. **Feed into Context Builder** (existing function `build_context()`):
   ```python
   context = build_context(
       appearance=appearance,
       knowledge_version=run.engine_version,
   )
   ```

4. **Pass to decision engine** (existing `recommend_hairstyle()` or `recommend_grooming()`):
   ```python
   result = recommend_hairstyle(knowledge, appearance, preferences)
   # Returns HairstyleResult with top/alternatives/confidence/needs_more_data
   ```

5. **The engine itself requires NO structural change** — it accepts `AppearanceProfile` as input, exactly as the profile-based flows do. The only change is the **source of the `AppearanceProfile`** — image-derived instead of profile-derived.

### 7.3 Where the Integration Happens

The integration occurs in the **application use case** layer, not in the engine:

- **`CreateHairstyleRun`** (or new `CreateOutfitRun`) is the use case that wires the image-derived `AppearanceProfile` into the engine.
- The **engine functions** (`recommend_hairstyle`, `recommend_grooming`) are **reused-as-is** — no changes to `analysis_rules.py` or `grooming_rules.py`.
- The `AppearanceProfile` value object is the same; only the data population changes (from `user_state.style_profile` to the image-derived result snapshot).

### 7.4 Decision Engine Reuse

| Engine Component | Reused? | Notes |
|---|---|---|
| `ContextBuilder` | ✓ | Identical — takes `AppearanceProfile` + optional `HairstylePreferences` |
| `CandidateGeneration` | ✓ | Same `KnowledgeSource` port (catalog) |
| `Filtering` | ✓ | Same hard exclusion rules (excludedLookIds) |
| `Scoring` | ✓ | Same weighted signal composition (seed + face_boost + preference_boost) |
| `Ranking` | ✓ | Same score-descending order, stable tie-breaking |
| `Explanation` | ✓ | Same grounded reasons from catalog |
| `Recommendation` | ✓ | Same `HairstyleResult`/`GroomingResult` output type |
| `derive_confidence` | ✓ | Same deterministic formula (50% completeness + 50% decisiveness) |

### 7.5 What Changes vs What Stays

- **Changes**: The `AppearanceProfile` data source — instead of reading from `user_state.style_profile`, read from the completed `analysis_runs.result` appearance snapshot.
- **Stays identical**: The entire decision engine pipeline, confidence formula, result schema, and recommendation cards.

### 7.6 Profile Projection Update (TRX-6)

After the run completes and the engine produces recommendations, TRX-6 applies the face attributes to the current profile:

```sql
-- TRX-6: Update user_state.style_profile with image-derived attributes
UPDATE user_state 
SET style_profile = jsonb_build_object(
    'face_shape', result.appearance.faceShape,
    'skin_tone', result.appearance.skinTone,
    'body_type', result.appearance.bodyType,
    'style_type', result.appearance.styleType,
    'source_run_id', run_id
)
WHERE user_id = :user_id;
```

This is a **separate transaction** from TRX-5 (run completion). The run row is untouched — it remains immutable history. The profile is the "current state" that may be overridden by a newer run's TRX-6.

### 7.7 Learning Signal

TRX-6 also emits a learning signal:
```python
self._learning_signal.insert_look_saved(
    user_id=user_id,
    label="analysis_updated",
    context={"run_id": str(run_id), "run_type": run.run_type},
)
```
This signals that the profile was updated from an analysis run — feeds the derived score/streak records.

---

## STEP 8 — VERSIONING

### 8.1 Appearance Schema

- **No version field** on the `AppearanceProfile` value object or in the `analysis_runs.result` JSONB.
- **Reproducibility** is achieved through: `input_media` (source image) + `engine_version` (on the run) + `analysis_runs.created_at`.
- If the appearance schema changes (new attribute added), a new `engine_version` is used; old runs remain reproducible from their original inputs + old engine version.

### 8.2 Analysis Result

- **No version field** on the result snapshot itself.
- **`engine_version` on the `analysis_run` row** serves as the model version for reproducibility.
- The result is immutable — once written, it is never overwritten. A new run produces a new result with potentially a new `engine_version`.

### 8.3 Model

- **`engine_version`** on `analysis_runs` is the model version.
- Currently: `"rules-v1"` (deterministic rules engine) or `"vision-v1"` (if vision model integrated).
- This is the only version field — it is exposed in the `AnalysisRun` DTO and echoed in poll/result reads.

### 8.4 Knowledge

- **No knowledge version field** required in the appearance result.
- Vocabulary codes (`faceShape`, `skinTone`, `bodyType`, `styleType`) are from the K9.1 knowledge layer — stable, versioned system knowledge. Changes to vocabularies are additive (new codes, never remove existing).

### 8.5 Recommendation Context

- **No version field** on recommendations — they are regenerated from the run result on each read.
- The `engine_version` on the run provides the provenance for why recommendations were generated with a particular model version.

### 8.6 Versioning Conclusion

- **Only `engine_version`** on `analysis_runs` requires versioning — all other fields are derived reproducibly from inputs + engine version.
- No unnecessary version fields are introduced.

---

## STEP 9 — ERROR CONTRACT

Define behavior for all failure paths, using the existing Fansivibe API error architecture.

### 9.1 Error Taxonomy (12 categories, frozen)

| `error.code` | HTTP | When | Details |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | bad image / no face detected (S-1/S-2); invalid grooming option (S-3); bad UUID/filter (S-5/S-9); derived-without-run (R-2) | field errors + allowed values in `details` |
| `MEDIA_FAILURE` | 413/422 | image too large / unsupported content-type (S-1/S-2, S-4) | `details.maxBytes`; pre-run check |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | run not owned / never existed; account gone | 404-not-403, no existence leak |
| `EXTERNAL_SERVICE_FAILURE` | 502/503 | AI provider/submission failure; object storage | C-8: no provider internals |
| `PROCESSING_FAILURE` | 500 (sync) / run `failed` | analysis pipeline failure (after 1 automatic retry) | `details.run_id`; the run is historical failure |
| `RATE_LIMITED` | 429 | any endpoint | + `Retry-After` |
| `INSUFFICIENT_USER_DATA` | 422 | decision needs more user data (profile-only pass without face attributes) | `details.missing` |

### 9.2 Specific Error Paths for Appearance Scan

| Path | Endpoint | Error Code | HTTP | Details |
|---|---|---|---|---|
| **Invalid image** | `POST /v1/analysis/outfit` | `MEDIA_FAILURE` | 413/422 | `image` missing, wrong content-type, or `sizeBytes > maxBytes` |
| **Unsupported format** | `POST /v1/analysis/outfit` | `MEDIA_FAILURE` | 413/422 | Content-type not in allow-list: `image/jpeg`, `image/png`, `image/webp` |
| **Upload failure** | `POST /v1/analysis/outfit` (TRX-1) | `MEDIA_FAILURE` | 413/422/503 | Blob upload to object storage failed; `details.kind` |
| **Authentication failure** | All scan endpoints | `AUTHENTICATION_ERROR` | 401 | Missing/expired/revoked token; `WWW-Authenticate: Bearer` |
| **Unauthorized media** | `GET /v1/analysis/runs/{run_id}` | `NOT_FOUND` | 404 | run_id not belonging to caller (or never existed) — 404-not-403 |
| **Analysis failure** | `POST /v1/analysis/outfit` (job failure) | `PROCESSING_FAILURE` | 500 (sync) / run `failed` | Transient failure after 1 automatic retry; run marked `failed` |
| **Timeout** | `POST /v1/analysis/outfit` (job timeout) | `EXTERNAL_SERVICE_FAILURE` | 502/503 | AI provider timeout; `details.run_id` |
| **Model unavailable** | `POST /v1/analysis/outfit` | `EXTERNAL_SERVICE_FAILURE` | 502/503 | Vision model / rules engine unavailable; fallback to rules-v1 |
| **Malformed model result** | `analysis_runs.complete()` | `DATABASE_FAILURE` | 500 | Result serialization failure; `details.request_id` only |
| **Run not found** | `GET /v1/analysis/runs/{run_id}` | `NOT_FOUND` | 404 | run_id does not exist or not owned by caller |

### 9.3 Error Response Shape

All errors follow the frozen envelope:
```json
{
  "error": {
    "code": "<one of the 12>",
    "message": "<safe client message>",
    "details": {...}
  }
}
```

- `details` is **allow-listed only** (ER-1): field errors + allowed values (422), `maxBytes` (413), `run_id` (own run only), `request_id` (500).
- **Never** the user's scan image, run `result` content, prompts, provider/model names, or analysis internals (C-7/C-8, ER-0/ER-2, AI-0).

### 9.4 Failure Behavior Summary

| Failure Path | Run Status | Result Written? | Error in DB? | Client Visible |
|---|---|---|---|---|
| Transient failure (timeout/5xx) | `failed` (after 1 retry) | No | Yes (`error` body) | `503` on poll, or automatic retry then `failed` |
| No face detected / no clothing | `failed` (immediate) | No | Yes | `422 VALIDATION_ERROR` on submit; run marked `failed` |
| Invalid image format/size | `failed` (immediate) | No | Yes | `413/422 MEDIA_FAILURE` on submit |
| Pipeline exception | `failed` (immediate) | No | Yes | `500`/`503`; run marked `failed` |
| Success | `completed` | Yes (immutable) | No | `200` with `result` + `engine_version` |

### 9.5 Run Not Found / Ownership

- `GET /v1/analysis/runs/{run_id}` where `run_id` does not exist or belongs to another user → **404** (never 403, no existence leak, OW-1).
- The `run_id` is treated as owner-scoped only — no public existence hint.

### 9.6 Polling Failure Paths

| Poll Scenario | Response | Action |
|---|---|---|
| Run still `pending` | `{run_id, run_type, status, created_at}` | Client retries poll |
| Run `completed` | Full `AnalysisRun` with `result` + `engine_version` | Client reads result |
| Run `failed` | `{run_id, run_type, status, created_at, completed_at, error}` | Client shows failure UI + retry option |
| Malformed `run_id` | `422 VALIDATION_ERROR` | Client fixes run_id |

---

## STEP 10 — SECURITY / PRIVACY

Define behavior (design only; do not implement yet).

### 10.1 User Ownership

- Every `analysis_run` is **owner-scoped**: `user_id` FK → `users.id`, enforced via `404-not-403` (OW-1).
- The `user_id` is derived from the **Bearer token** via `deps.py` — never client-supplied.
- Cross-user access returns `404` (no existence leak).

### 10.2 Image Access

- **Image bytes** are never transmitted in API responses or errors — only the `MediaRef` travels (MS10.3, ER-4).
- **Object storage paths** are owner-scoped: `users/{user_id}/scans/{run_id}/input.{ext}`.
- Images are **HTTPS only**; no mixed content.
- **No raw image URLs** are exposed in any response envelope.

### 10.3 Retention Expectations

- **Unsaved scan media auto-expires** — face scans expire after analysis unless saved; outfit scans e.g. after 30 days unless attached to a saved look (`STORAGE_INVENTORY.md` §1.2/§1.3).
- **Retention is a background job** — not a user-facing delete call.
- If the user **saves the look** (via `POST /v1/looks/today/save` or saved look surface), the `result` snapshot is persisted in `saved_looks.snapshot`; the raw scan image may still auto-expire unless separately saved.
- **Account erasure** (TRX-8) cascades to delete scan blobs + `analysis_runs` rows.

### 10.4 Deletion Behavior

- **No user-facing DELETE endpoint** for analysis runs (append-only history, PR-5/PR-6).
- **No user-facing DELETE endpoint** for scan media — auto-expire by retention job.
- **`DELETE /v1/users/me`** (account erasure) triggers cascade: delete `analysis_runs` rows + sweep object storage blobs.
- **M16 media deletion** (when unsealed) supports logical tombstone + async byte sweep.

### 10.5 Authentication

- **Bearer tokens** issued by `POST /v1/auth/*` (D-AUTH-1 placeholder today → `DEV_TOKEN` in dev).
- Missing/invalid/expired/revoked → `401 AUTHENTICATION_ERROR` + `WWW-Authenticate: Bearer`.
- Protected endpoints (all scan endpoints) require valid token; public endpoints (`GET /health`, `GET /knowledge/*`, `POST /v1/assistant/chat`) are unauthenticated today.

### 10.6 Authorization

- **Owner-only (OW-1)**: every user-owned endpoint scopes to the caller's `user_id`.
- **404-not-403**: a `run_id` that is not yours (or never existed) returns `404`, never `403` and never an existence hint.
- **No admin paths** for scan operations — all gated by owner scoping.

### 10.7 Logging Restrictions

- **Image bytes never logged** — only `MediaRef` fields (key, mediaType, contentHash) may be logged for observability, never the raw bytes.
- **Run `result` content never logged** — only the fact of completion/failure, never the structured appearance data.
- **Provider/model names never logged** — only `engine_version` may be logged for reproducibility.
- **`details` in errors** is allow-listed only: never SQL, prompts, stack traces, tokens, provider/model names, or user content (ER-0/ER-2).

### 10.8 Privacy by Design

- **Minimal data retention**: scan images stored only as `MediaRef` reference + metadata; raw bytes auto-expire.
- **User control**: user can save the appearance result as a `SavedLook` (which snapshots the profile, not the raw image). Unsaved scans auto-expire.
- **No permanent image database**: no table stores image bytes; only `MediaRef` JSONB columns in `analysis_runs` and `saved_looks`.
- **Provenance tracked**: `sourceRunId` + `engine_version` enable reproducibility without retaining sensitive data indefinitely.

---

## STEP 11 — TEST CONTRACT

Define tests required for the Appearance Scan data and API contract.

### 11.1 Backend Tests

| Test Category | Required Tests |
|---|---|
| **Upload** | - `POST /v1/analysis/outfit` with valid image → `202 {run_id}`<br>- `POST /v1/analysis/outfit` with invalid content-type → `413/422 MEDIA_FAILURE`<br>- `POST /v1/analysis/outfit` with oversized image → `413/422 MEDIA_FAILURE` |
| **Run creation** | - `POST /v1/analysis/outfit` creates run with `status=pending`<br>- Run is owner-scoped (404 for wrong user)<br>- `input_media` stored as `MediaRef` in `analysis_runs` |
| **Ownership** | - `GET /v1/analysis/runs/{run_id}` returns run only for owner<br>- `GET /v1/analysis/runs` lists only user's runs<br>- Cross-user run read → `404` |
| **Analysis result** | - Completed run returns `result` with `AppearanceProfile` snapshot<br>- Completed run includes `confidence` and `needs_more_data`<br>- Failed run returns `error` but no `result` |
| **Polling** | - `GET /v1/analysis/runs/{run_id}` while `pending` → no `result`/no `error`<br>- Poll until `completed` → returns full `AnalysisRun`<br>- Poll until `failed` → returns `error`, no `result` |
| **Failure paths** | - Invalid image → `413/422 MEDIA_FAILURE`<br>- No face detected → `422 VALIDATION_ERROR`<br>- Pipeline exception → run marked `failed`<br>- Retry creates new run, failed run stays immutable |
| **Idempotency** | - Second submission creates new run (never idempotent)<br>- Failed run re-submission → distinct new run history |

### 11.2 Flutter Tests

| Test Category | Required Tests |
|---|---|
| **Capture** | - Camera capture produces valid image file<br>- Gallery picker alternative works<br>- Test mode shortcut navigates directly to processing |
| **Upload** | - Upload starts from capture path<br>- `multipart/form-data` with `image` part<br>- Upload progress/cancellation handling |
| **Processing** | - Polling for run status from Flutter<br>- UI shows `pending` → `completed`/`failed` transition<br>- Timeout handling (user cancels/navigates away) |
| **Result** | - Display `AppearanceProfile` fields from completed run result<br>- Show recommendations from engine output<br>- Show `needs_more_data` when profile sparse |
| **Failure states** | - Upload failure → Snackbar + retry<br>- Analysis failure → Snackbar + retry new scan<br>- Invalid image format → validation error UI |
| **Polling** | - Polling loop with exponential backoff<br>- Handle `401` auth expiration during poll<br>- Handle `404` run not found |

### 11.3 Integration Tests

| Test Scenario | Description |
|---|---|
| **Image → run → analysis → profile → recommendation** | 1. Capture image from camera<br>2. Upload → `POST /v1/analysis/outfit` → `202 {run_id}`<br>3. Poll `GET /v1/analysis/runs/{run_id}` → `completed`<br>4. Read `result` → `AppearanceProfile` + recommendations<br>5. Profile updated via TRX-6 (check `user_state.style_profile`)<br>6. Engine produces recommendations → `SuggestionCard` UI |
| **Profile persistence** | - After appearance scan, `user_state.style_profile` has `face_shape`, `skin_tone`, `body_type`, `style_type`, `source_run_id`<br>- Subsequent profile-based hairstyle scan works without image (uses stored profile)<br>- `source_runId` provenance links back to the original scan |
| **Retry flow** | - Failed run stays as history (immutable)<br>- Client re-POST → new run created<br>- Original failed run remains with `error` body, no `result` |
| **Media auto-expire** | - Unsaved scan media auto-expires after retention window<br>- User-saved look retains the `result` snapshot independently |
| **End-to-end with gallery** | - Image picked from gallery → same upload → run → result path as camera capture |

### 11.4 Test Data Factories

| Factory | Fields |
|---|---|
| `AnalysisRunRecord` | `id`, `user_id`, `run_type`, `status`, `engine_version`, `input_media`, `result`, `created_at`, `completed_at`, `error` |
| `AppearanceProfile` | `faceShape`, `skinTone`, `bodyType`, `styleType`, `sourceRunId` |
| `MediaRef` | `key`, `mediaType`, `sizeBytes`, `contentHash`, `isGenerated`, `uploadedAt` |
| `HairstyleResult` | `appearance`, `top`, `alternatives`, `confidence`, `needs_more_data` |
| `GroomingResult` | `appearance`, `top`, `alternatives`, `confidence`, `needs_more_data` |

### 11.5 Test Constraints (per strict rules)

- **DO NOT modify application code** — tests are design-only specification
- **DO NOT modify database** — test data uses existing schema
- **DO NOT add dependencies** — use existing test infrastructure
- **DO NOT implement AI models** — tests mock the analysis pipeline
- **DO NOT modify existing Hairstyle/Grooming behavior** — tests reuse existing engine functions