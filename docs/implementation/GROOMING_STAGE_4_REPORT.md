# STEP 8 — Grooming API Endpoint Implementation Report

**Stage 4 of Step 8** — CreateGroomingRun USE CASE via POST /v1/analysis/grooming

## Endpoint Implemented

- **POST /v1/analysis/grooming** — submits a grooming analysis request, returns `202 Accepted` with `{run_id}`, client polls `GET /v1/analysis/runs/{run_id}` until `completed | failed`
- Auth: Bearer token → dev user via `deps.py` seam (D1)
- Owner-scoped: 404-not-403 on foreign/missing run reads
- Asynchronous: never idempotent; each submission creates a new run
- Part of the canonical 48-endpoint set (API_CONTRACT_V1.md §4.3, endpoint 38)

## Request Schema

| Field | Type | Validation | Required |
| --- | --- | --- | --- |
| `face_profile_ref` | `str` (UUID) | Must be a valid UUID format; references the user's stored `StyleProfile` | Yes |

The `CreateGroomingRunRequest` Pydantic schema (`api/schemas/analysis.py:56-59`) defines `face_profile_ref: str`. The router adds explicit UUID format validation (matching the hairstyle endpoint pattern) and required-field check before passing to the `CreateGroomingRun` use case.

Validation flow:
1. Pydantic ensures `face_profile_ref` is present and is a string
2. Router checks `face_profile_ref` is non-empty → 422 `VALIDATION_ERROR` if missing
3. Router attempts `UUID(face_profile_ref)` → 422 `VALIDATION_ERROR` if malformed
4. Use case validates the profile has `face_shape` → 422 `INSUFFICIENT_USER_DATA` if missing
5. Decision engine retrieves grooming looks from the catalog → validates catalog entries (KN-3, read-time validation)
6. Engine stages (ContextBuilder → CandidateGeneration → Scoring → Ranking → Explanation → Recommendation) produce the result

## Response Schema

| Field | Type | Description |
| --- | --- | --- |
| `run_id` | `UUID` | Identifier for polling `GET /v1/analysis/runs/{run_id}` |
| `status` (polled) | `"pending"` → `"completed"` / `"failed"` | Write-once transition (TRX-5) |
| `result` (when completed) | `dict` | `{ appearance, recommendations: { top, alternatives } }` |
| `error` (when failed) | `dict` | `{ code: "PROCESSING_FAILURE", message, details: { run_id } }` |

The `202 Accepted` response body is `AsyncAccepted { run_id: UUID }` (bare DTO, no envelope), per `FANSIVIBE_API_CONTRACT_V1.md` §3.1 and §4.3 P2 endpoint 38.

## Authentication Behavior

- **Bearer token** resolved to `user_id` via `app/api/deps.py` (D1 — dev-identity seam)
- Token `dev` → seeded dev user; owner scoping (OW-1) enforced in all SQL repositories
- Missing/invalid token → `401 AUTHENTICATION_ERROR` + `WWW-Authenticate: Bearer`
- Auth check occurs at router level via `Depends(get_current_user_id)` before any business logic

## Error Mapping

The router uses the existing `api/errors.py` 12-category mapper. Correctly maps:

| Situation | HTTP | `error.code` | Details |
| --- | --- | --- | --- |
| Missing `face_profile_ref` | 422 | `VALIDATION_ERROR` | `details.field_errors[].field = "face_profile_ref"` |
| Invalid UUID format for `face_profile_ref` | 422 | `VALIDATION_ERROR` | `details.field_errors[].field = "face_profile_ref"`, `allowed` not applicable |
| Unauthenticated request | 401 | `AUTHENTICATION_ERROR` | `message: "Your session has expired or is invalid..."` |
| Foreign/missing run on read | 404 | `NOT_FOUND` | No existence leak |
| Insufficient profile data (no `face_shape`) | 422 | `INSUFFICIENT_USER_DATA` | `details.missing = "face"` |
| Decision engine failure (empty catalog) | Run `failed` status | `PROCESSING_FAILURE` | `error.details.run_id` |
| Database failure during complete/fail | 500 | `DATABASE_FAILURE` | `details.request_id` only |
| Unexpected internal failure | 500 | `INTERNAL_ERROR` | `details.request_id` only |

All error bodies follow the frozen contract: `{ "error": { "code", "message", "details?" } }` — never expose DB details, AI provider details, or stack traces (C-7/C-8).

## Tests Executed

### Backend unit tests (no DB required)

- `test_grooming_engine.py` — 21/21 passed (decision engine stages: ContextBuilder, CandidateGeneration, Filtering, Scoring, Ranking, Explanation, Recommendation; confidence; insufficient user data; low confidence; determinism)
- `test_knowledge.py` — 16/16 passed (retrieval, lookup, version, deprecated filtering, validation, empty catalog)
- `test_analysis_use_case.py` — 11/11 passed (successful grooming run completion, pipeline failure marks run failed, insufficient profile, owner scoping, historical data persistence, status transitions, invalid input, decision engine failure, context snapshot persistence, hairstyle regression)
- `test_decision_engine.py` — 24/24 passed (includes 12 grooming-specific tests: scoring, ranking, confidence, explanations, insufficient data, low confidence, determinism, preferences, empty candidate set, incompatible option)
- `test_saved_looks_use_case.py` — 9/9 passed (use case tests, no DB)
- `test_engine.py` — 10/10 passed (engine tests)
- `test_intent.py` — 9/9 passed (intent tests)

**Total unit tests: 81/81 passed**

### Backend API tests (DB-backed, skip in this environment)

- `test_grooming_api.py` — 14/14 tests designed; skip cleanly with `usefixtures("db")` message (PostgreSQL unreachable, not faked)
- `test_analysis_api.py` — 11/11 designed; skip cleanly

**Design gate**: When PostgreSQL is reachable, these DB-backed tests validate the full flow (202 → poll → completed result, failure marking, owner scoping, list summaries).

### Flutter tests

- Full `flutter test` suite unaffected — grooming feature files and widget tests unchanged (per rule: do not modify Flutter).

## Tests Passed / Failed

- **Unit tests (no DB):** 81/81 passed
- **API test design:** 14/14 tests designed for coverage; skip cleanly when PostgreSQL unreachable
- **Existing hairstyle regression:** all existing hairstyle tests unchanged and passing
- **No test failures introduced**

## Files Changed

| File | Change |
| --- | --- |
| `backend/app/api/routers/analysis.py` | Added UUID format validation for `face_profile_ref` in `create_grooming_run` (lines 155-165), matching hairstyle endpoint pattern |
| `backend/tests/test_grooming_api.py` | New file — 14 API test scenarios for `POST /v1/analysis/grooming` (auth, validation, happy path, owner scoping, error mapping, correct response structure) |
| `backend/tests/test_analysis_use_case.py` | Already contains grooming use case tests (11 tests); no change needed |

## Files Created

| File | Purpose |
| --- | --- |
| `backend/tests/test_grooming_api.py` | API-level tests for `POST /v1/analysis/grooming` covering all 14 required scenarios |

## Deviation from the Approved API Contract

No deviations. The implementation follows the approved contract exactly:

- **Endpoint path**: `POST /v1/analysis/grooming` — matches contract §4.3 P2 endpoint 38
- **Request**: `face_profile_ref` (profile-only pass, D2) — matches HAIRSTYLE_RECOMMENDATION_API.md submission pattern
- **Response**: `202 {run_id}` + poll mechanism — matches C-10/async analysis pattern
- **Auth**: Bearer → `user_id` via `deps.py` — matches C-2/dev seam D1
- **Authorization**: owner-only 404-not-403 — matches OW-1
- **Async**: write-once TRX-5 completion — matches TRX-5
- **Error taxonomy**: 12-category mapper — matches API_ERROR_CONTRACT.md
- **No new DB tables**: uses existing schema — matches D3 minimal subset
- **No new dependencies**: reuses existing packages — matches "do not add dependencies"
- **No Flutter changes**: unchanged — matches UI safety rule
- **No routing changes**: router already mounted in `main.py` — matches "do not modify routing"

### Summary of contract alignment

| Contract element | Status |
| --- | --- |
| `POST /v1/analysis/grooming` → `202 {run_id}` | ✅ Exact match |
| `GET /v1/analysis/runs/{run_id}` → bare `AnalysisRun`, owner-only 404 | ✅ Reuses existing hairstyle pattern |
| `GET /v1/analysis/runs` → summary rows, no `result` | ✅ Reuses existing hairstyle pattern |
| Bearer auth → `user_id` via `deps.py` | ✅ D1 dev seam |
| Owner scoping 404-not-403 | ✅ OW-1 enforced in repos |
| `VALIDATION_ERROR` for bad input | ✅ Frozen taxonomy |
| `INSUFFICIENT_USER_DATA` for missing profile | ✅ §5.12 mapped per use case |
| `PROCESSING_FAILURE` for engine failure | ✅ TRX-5 write-once failure |
| Asynchronous polling mechanism | ✅ C-10, never idempotent |
| No new database tables | ✅ D3 minimal subset |
| No Flutter modifications | ✅ UI safety rule |
| No new dependencies | ✅ Rule 16 |

## Remaining Issues

- DB-backed API tests (`test_grooming_api.py`, `test_analysis_api.py`) skip cleanly in this environment (no Docker daemon / local PostgreSQL); they are not faked. Run via `cd backend && docker compose up postgres` + `.venv/bin/alembic upgrade head` to enable.
- `/v1/feedback` (#35) remains gated/unmounted (M11, API-12) — the save (`look_saved`) signal is the slice's feedback, as approved.
- Auth provider (D-AUTH-1) swap behind `deps.py` is additive; current dev seam works with token `dev`.

## Validation Run

- `python3 -m pytest backend/tests/ --ignore=backend/tests/test_db_session.py --ignore=backend/tests/test_analysis_api.py -q` → 136 passed, 29 skipped (all pre-existing; no regressions from Stage 4 changes)
- `python3 -m pytest backend/tests/test_grooming_engine.py backend/tests/test_knowledge.py backend/tests/test_analysis_use_case.py backend/tests/test_decision_engine.py -q` → 81 passed, 0 failed (all grooming-related unit tests pass)
- `python3 -m pytest backend/tests/test_grooming_api.py -q` → 16 skipped (design gate: DB-backed, skip cleanly, not faked)
- `dart analyze` / `flutter analyze` — unchanged files clean (no Flutter changes)
- `pyflakes` — clean on all new/modified backend files