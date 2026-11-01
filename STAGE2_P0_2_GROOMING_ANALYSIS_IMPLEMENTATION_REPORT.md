# Fansivibe Stage 2 — P0-2: Authenticated Grooming Analysis & Profile Repair Implementation Report

**Status:** Completed and Fully Verified  
**Date:** 2026-10-31  
**Scope:** Targeted Defect Repair for Authenticated Grooming Analysis & Profile Grounding  

---

## 1. Root Cause Analysis

Prior to this repair, authenticated users who navigated to Grooming Analysis without a prior face scan received an `HTTP 422 INSUFFICIENT_USER_DATA` error from `POST /v1/analysis/grooming` with `{"error": {"code": "INSUFFICIENT_USER_DATA", "field": "face", "message": "Face profile required for grooming analysis"}}`, even if they had entered valid manual grooming preferences on `GroomingInputScreen`.

Investigation across the full pipeline identified four cascading failure points:
1. **Frontend State Disconnect in GroomingProcessingScreen:** `GroomingProcessingScreen._runAuthenticated()` did not pass the widget's manual input parameters (`faceShape`, `beardStyle`, `beardDensity`, `beardColor`) to `_service.runAnalysis()`.
2. **Premature Mock Fallback in GroomingService:** `GroomingService.runAnalysis()` checked only `_learning?.face?.faceShape`. When a user lacked a prior face scan, it immediately aborted to offline mock content with `No face profile yet. Complete a face scan first.` without ever contacting the backend.
3. **Hardcoded Empty Payload in GroomingClient:** `GroomingClient.submitGroomingAnalysis()` serialized a hardcoded empty JSON object `jsonEncode({})`.
4. **Backend Router & Use Case Rejection:**
   - FastAPI router `POST /v1/analysis/grooming` did not declare a request body parameter and ignored any incoming payload.
   - Application use case `CreateGroomingRun.__call__` queried `user_state.get_style_profile(user_id)` and immediately raised `insufficient_user_data("face", "Face profile required for grooming analysis")` if `face_shape` was missing, ignoring manual user preferences and denying users who only desired facial hair recommendations based on their manual choices.

---

## 2. Before / After Data Flow

### Before Repair
```
[GroomingInputScreen] (User enters face shape, beard style, density, color)
       │
       ▼ (Passes state.extra Map<String, dynamic>)
[GroomingProcessingScreen] (Values received in widget props)
       │
       ▼ (Ignores props; calls _service.runAnalysis() without arguments)
[GroomingService] (Checks _learning?.face?.faceShape -> null)
       │
       ├─► (Frontend Abort) Sets _usedMockResult = true, returns GroomingAnalysisResult.mock
       │
       ▼ (If service bypassed)
[GroomingClient.submitGroomingAnalysis] (Sends hardcoded `{}` to backend)
       │
       ▼
[FastAPI /v1/analysis/grooming] (No body parameter; payload ignored)
       │
       ▼
[CreateGroomingRun] (Checks user_state.get_style_profile(user_id).get('face_shape'))
       │
       ▼
[HTTP 422 INSUFFICIENT_USER_DATA ("Face profile required for grooming analysis")]
```

### After Repair
```
[GroomingInputScreen] (User enters face shape, beard style, density, color)
       │
       ▼ (Passes state.extra Map<String, dynamic> via RouteNames.groomingProcessing)
[GroomingProcessingScreen] (Extracts form values, passes to _service.runAnalysis(...))
       │
       ▼
[GroomingService] (Resolves effectiveFaceShape: confirmed profile > manual input;
       │           permits analysis if either face shape or manual preferences are present)
       ▼
[GroomingClient.submitGroomingAnalysis] (Serializes {face_shape, beard_style, beard_density, beard_color})
       │
       ▼
[FastAPI /v1/analysis/grooming] (Accepts Optional[CreateGroomingRunRequest] in body)
       │
       ▼
[CreateGroomingRun]
       │
       ├─► Evaluates server profile attributes vs request manual inputs
       ├─► Confirmed server profile strictly outranks request manual inputs (prevents overwrite)
       ├─► Unmeasured attributes safely take request manual inputs
       ├─► Minimum input validation: accepts if either face_shape OR (beard_style/density/color) present
       ├─► Unknown face shape remains None (0.0 boost, needs_more_data=True; NO fabrication)
       ├─► Maps manual beard styles to canonical look IDs (_BEARD_STYLE_LOOK_MAP)
       ├─► Delegates exclusively to canonical grooming_rules.recommend_grooming(...)
       │
       ▼ (200 OK with run_id, polled to completion)
[GroomingProcessingScreen] (Receives GroomingAnalysisResult.fromRunResult(...))
       │
       ▼
[GroomingResultScreen] (Renders grounded recommendations with dynamic match score and why-it-works reasons)
```

---

## 3. Exact Manual Input Contract

The contract supports both camelCase and snake_case representations seamlessly:

### JSON Payload Schema (`CreateGroomingRunRequest`)
```json
{
  "face_shape": "square",
  "beard_style": "full_beard",
  "beard_density": "dense",
  "beard_color": "black",
  "skin_tone": "warm",
  "body_type": "athletic",
  "style_type": "classic"
}
```

| Field Name (snake_case) | Field Name (camelCase) | Type | Meaning / Mapping |
|:---|:---|:---|:---|
| `face_shape` | `faceShape` | `Optional[str]` | Optional face shape (`oval`, `round`, `square`, `heart`, `diamond`, `oblong`). If omitted, remains `None` without defaulting to oval. |
| `beard_style` | `beardStyle` | `Optional[str]` | Desired beard style chip (`full_beard`, `stubble`, `goatee`, `circle_beard`, `van_dyke`, `moustache`, `clean_shaven`). Mapped to canonical catalog look IDs via `_BEARD_STYLE_LOOK_MAP`. |
| `beard_density` | `beardDensity` | `Optional[str]` | Desired beard density (`light`, `medium`, `dense`). Grounding preference. |
| `beard_color` | `beardColor` | `Optional[str]` | Desired beard color (`black`, `dark_brown`, `light_brown`, `blonde`, `red`, `grey`, `white`). Grounding preference. |
| `skin_tone` | `skinTone` | `Optional[str]` | Optional personal skin tone. |
| `body_type` | `bodyType` | `Optional[str]` | Optional body proportions. |
| `style_type` | `styleType` | `Optional[str]` | Optional overall aesthetic preference. |

---

## 4. Backend Validation Changes

1. **`backend/app/api/schemas/analysis.py`:**
   - Authored `CreateGroomingRunRequest` Pydantic model with snake_case and camelCase field aliases.
   - Added helper properties `resolved_face_shape`, `resolved_beard_style`, `resolved_beard_density`, and `resolved_beard_color` that gracefully coalesce either naming format.
2. **`backend/app/api/routers/analysis.py`:**
   - Updated route handler `create_grooming_run` to accept `payload: Optional[CreateGroomingRunRequest] = Body(default=None)`.
   - Forwarded `manual_inputs=payload` to the `CreateGroomingRun` application service.
3. **`backend/app/application/analysis.py`:**
   - Updated `CreateGroomingRun.__call__` to accept `manual_inputs: Optional[CreateGroomingRunRequest] = None`.
   - Evaluated server profile attributes alongside request manual inputs:
     ```python
     server_face = (profile.get("face_shape") or "").strip()
     manual_face = (manual_inputs.resolved_face_shape or "").strip() if manual_inputs else ""
     effective_face = server_face if server_face else (manual_face if manual_face else None)
     ```
   - Enforced minimum valid input requirements:
     A grooming run requires **either** an available face shape (from server profile or request) **or** manual grooming preferences (`beard_style`, `beard_density`, or `beard_color`).
     If neither is present, it fails closed with `422 INSUFFICIENT_USER_DATA ("Grooming preferences or face profile required")`.
   - Mapped frontend chip beard styles to canonical catalog look IDs:
     - `full_beard` -> `full_beard`
     - `stubble` -> `classic_stubble`
     - `goatee` -> `structured_goatee`
     - `circle_beard` -> `structured_goatee`
     - `van_dyke` -> `goatee_with_mustache`
     - `moustache` -> `goatee_with_mustache`
   - Canonical Grooming Delegation:
     Grooming recommendations continue to be delegated exclusively to `grooming_rules.recommend_grooming(self.knowledge, appearance, preferences)`. No secondary recommendation engine was introduced.
   - When face shape is unmeasured (`effective_face is None`), canonical rules assign `0.0` face boost and set `needs_more_data = True`. No face shape is fabricated.

---

## 5. Flutter Changes

1. **`lib/app/router/app_router.dart`:**
   - Hardened `RouteNames.groomingProcessing` argument extraction: safely maps `state.extra` when present without unsafe casts.
2. **`lib/features/grooming/data/grooming_client.dart`:**
   - Extended `submitGroomingAnalysis` to accept optional `faceShape`, `beardStyle`, `beardDensity`, and `beardColor`.
   - Serialized manual grooming preferences into the JSON request body.
   - Added `_lastSubmitError` to capture typed backend 422 error messages for truthful display.
3. **`lib/features/grooming/data/grooming_models.dart`:**
   - Extended `GroomingAnalysisResult.fromRunResult` and `fromSnapshot` to accept optional `requestFaceShape`, `requestBeardStyle`, `requestBeardDensity`, and `requestBeardColor`.
   - Resolved `beardStyle` by prioritizing canonical recommendations when available, falling back to request-specified preferences rather than dropping user input.
4. **`lib/features/grooming/data/grooming_service.dart`:**
   - Updated `runAnalysis` and `runEphemeralAnalysis` to accept manual grooming inputs.
   - Enforced precedence: confirmed face profile from `LearningRepository` outranks manual input; unmeasured profile falls back to manual input.
   - Set `_analysisError` honestly when API fails, avoiding false mock successes.
5. **`lib/features/grooming/presentation/grooming_processing_screen.dart`:**
   - Passed widget form values (`faceShape`, `beardStyle`, `beardDensity`, `beardColor`) to `_service.runAnalysis(...)`.
   - Replaced fragile `Navigator.of(context).pop()` with safe `_leaveProcessing(context)` to prevent route stack crashes.
   - Handled empty form state by showing an honest SnackBar warning and returning to the input screen.
   - Implemented `retry()` method that preserves the active idempotency key and original request context.

---

## 6. Profile Integrity Protections

1. **No Profile Pollution:** `CreateGroomingRun` creates an `analysis_runs` record for audit and result polling. It does not write manual temporary preferences to `user_state.style_profile`.
2. **Authority Precedence:** Confirmed server profile attributes always outrank client-supplied manual inputs (`server_face if server_face else manual_face`).
3. **Zero Face Shape Fabrication:** When face shape is missing from both the stored profile and the request, it is kept as `None`. Canonical rules flag `needs_more_data = True` and award `0.0` face boost. Oval is never fabricated.
4. **Domain Separation:** Grooming preferences remain strictly isolated to the grooming domain and are never mixed with wardrobe or garment attributes.
5. **Guest Boundary Preservation (D10 Option A):** Unauthenticated guest turns execute ephemeral analysis via `POST /v1/analysis/grooming/ephemeral` with zero database writes, zero synthetic guest UUIDs, and zero guest appearance persistence.

---

## 7. Test Commands and Exact Results

### Backend Pytest Suite
**Command:**
```bash
.venv/bin/pytest tests/test_authenticated_grooming_repair.py tests/test_grooming_engine.py tests/test_analysis_use_case.py tests/test_c10_analysis_idempotency.py tests/test_assistant_canonical_delegation.py
```
**Results:**
```
================== 128 passed, 3 skipped, 1 warning in 0.82s ===================
```
- `tests/test_authenticated_grooming_repair.py`: 8 passed
  1. `test_1_valid_manual_input_without_face_shape`: PASSED
  2. `test_2_valid_input_with_existing_face_shape_profile`: PASSED
  3. `test_3_missing_required_manual_inputs_rejects_honestly`: PASSED
  4. `test_4_unknown_face_shape_is_not_fabricated`: PASSED
  5. `test_5_confirmed_profile_values_are_protected`: PASSED
  6. `test_6_canonical_grooming_recommendation_delegation_active`: PASSED
  7. `test_7_guest_appearance_persistence_remains_prohibited`: PASSED
  8. `test_8_camel_case_schema_interoperability`: PASSED

### Flutter Test Suite
**Command:**
```bash
flutter test test/authenticated_grooming_repair_test.dart test/grooming_input_screen_test.dart test/grooming_processing_screen_test.dart test/grooming_client_test.dart test/grooming_service_test.dart test/data_consistency_regression_test.dart
```
**Results:**
```
00:03 +38: All tests passed!
```
- `test/authenticated_grooming_repair_test.dart`: 8/8 passed
  1. `1. manual grooming inputs survive navigation`: PASSED
  2. `2. processing screen forwards actual inputs to service and client`: PASSED
  3. `3. authenticated user without face scan receives valid recommendations when inputs are sufficient`: PASSED
  4. `4. empty or genuinely insufficient input produces an honest validation state`: PASSED
  5. `5. API failures are handled correctly without fake success`: PASSED
  6. `6. retry preserves the original request context`: PASSED
  7. `7. existing face-scan grooming flow remains functional`: PASSED
  8. `8. guest authentication boundaries remain intact`: PASSED
- `test/grooming_input_screen_test.dart`: 8/8 passed
- `test/grooming_processing_screen_test.dart`: 8/8 passed
- `test/grooming_client_test.dart`: 6/6 passed
- `test/grooming_service_test.dart`: 4/4 passed
- `test/data_consistency_regression_test.dart`: 4/4 passed

### Flutter Static Analysis
**Command:**
```bash
flutter analyze
```
**Results:**
```
Analyzing flutter_application_1...                              
No issues found! (ran in 2.4s)
```

### Git Diff Check
**Command:**
```bash
git diff --check
```
**Results:**
```
(Exit code 0, clean, zero errors)
```

---

## 8. Remaining Limitations

1. **Per-Stage Processing Progress:** The grooming processing screen animates stages sequentially based on timer estimates rather than real-time WebSocket stage events from the backend run worker.
2. **Look Detail Grooming Actions:** Grooming recommendations provide rich styling tips, eyewear pairings, and maintenance guidelines, but do not yet link directly to product purchase slots for grooming tools.

---

## 9. Git Preservation Confirmation

All pre-existing tracked and untracked repository changes have been preserved intact:
- No `git reset`, `git clean`, `git checkout`, `git stash`, `git commit`, or `git push` commands were executed.
- All 62 modified files and 37 untracked files from prior stages remain untouched and intact.
- Baseline diff statistics and working tree status were confirmed before and after implementation.
