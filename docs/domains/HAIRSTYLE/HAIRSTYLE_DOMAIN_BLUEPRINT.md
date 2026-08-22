/mo# Fansivibe — Hairstyle Domain Blueprint

> **EXTRACTION (documentation only).** Describes the Hairstyle domain as it
> actually exists in the repository — concepts, entities, flows, contracts,
> and markers — reconciled against the product contract and the current truth.
> No code, DB, API, Flutter, UI, or test changes. Conflicts are documented,
> never silently resolved.

> **Source of truth:** the real repository
> (`newproject/flutter_application_1` + `backend/`), the accepted product
> contract (`docs/product/CORE_USER_JOURNEY_TARGET.md`,
> `docs/product/STEP_9_CORE_USER_JOURNEY_REPORT.md`, `PROJECT_CONTEXT.md`),
> the API/DB/domain contracts, and the current-truth ledger in `CURRENT_STATE.md`
> (git HEAD `b83de46`, working tree clean).

> **Marker legend:** `UNKNOWN` (not determinable), `UNTESTED` (no automated
> coverage found), `HYPOTHESIS` (plausible, not verified), `NOT LIVE-VERIFIED`
> (code path exists but not run against a live backend), `IMPLEMENTED /
> EXECUTION UNVERIFIED` (present in code; runtime behavior not live-verified).

---

## 1. Domain identity

| Attribute | Value |
| --- | --- |
| **Domain** | Hairstyle — personalized hairstyle recommendation from a face scan |
| **Owner** | `features/hairstyle/` (Flutter) + analysis/looks API surface (backend) |
| **Screens** | HAIR-001 FaceScanScreen → HAIR-002 FaceProcessingScreen → HAIR-003 HairstyleResultScreen → HAIR-004 HairstyleDetailsScreen (`docs/SCREEN_MAP.md`) |
| **Routes** | `hairstyle`, `hairstyle-processing`, `hairstyle-result`, `hairstyle-details` (`lib/app/router/route_names.dart`) |
| **Primary entry** | Stylist bottom-nav tile and Home quick actions → `FaceScanScreen` |
| **Backend endpoints** | #37 `POST /v1/analysis/hairstyle`, #39 `GET /v1/analysis/runs/{run_id}`, #40 `GET /v1/analysis/runs`, #23 `POST /v1/looks/saved` |

### 1.1 Product contract (highest authority)

**Current Truth (as accepted):** face scan → personalized hairstyle
recommendation with confidence score + grounded explanation → informed
decision → saved to profile.

- **SUPPORTED (implemented + tested):** face scan input; personalized
  hairstyle recommendation with match score and grounded reasons; confidence
  derived deterministically by the decision engine; save to profile with
  `Idempotency-Key` (TRX-3 all-or-nothing).
- **HYPOTHESIZED (product intent, not yet live-verified):** that the presented
  recommendation drives an *informed decision* (the decision UX exists on the
  result screen) and that saved styles persist into the profile in a way users
  actually rely on.
- **Out of scope / no claim:** no claim about real-world salon/barber outcomes;
  the hairstyle recommendation is AI/derived output, never truth (BAR-0).

---

## 2. Verified reality check

The following facts were verified against source (not just docs).

| Fact | Evidence |
| --- | --- |
| **Flow works end-to-end** at code level (Flutter → FastAPI → PostgreSQL → Decision Engine → Result → Save → `look_saved` signal) | `CURRENT_STATE.md` STEP 7 final validation; `FANSIVIBE_MVP_AUDIT.md` (KEEP) |
| **Submit is NOT idempotent** — every submission returns `202 + run_id`; each is a new run | `analysis_rules`/`analysis.py`; `HAIRSTYLE_RECOMMENDATION_API.md` §4.2 "never idempotent"; `CURRENT_STATE.md` item 21 |
| **Save IS idempotent (TRX-3)** — `saved_looks` INSERT + `look_saved` signal commit together; `Idempotency-Key` replay returns original save; conflicting replay → 409 | `backend/app/application/saved_looks.py`; `TRANSACTION_BOUNDARIES.md` TRX-3; `CURRENT_STATE.md` |
| **Decision engine = 7 stages** (Context → CandidateGen → Filter → Score → Rank → Explain → Recommend), per-task composition, deterministic rules-first (DE-0) | `backend/app/domain/services/analysis_rules.py`; `DECISION_ENGINE_ARCHITECTURE.md` |
| **4 hairstyle looks** in the catalog with stable codes + validated `scoreSeed` | `backend/app/data/catalog.py` `HAIRSTYLE_LOOKS`; `knowledge.py` `_validate_entry`; 4 mock recommendations mirror the catalog |
| **Confidence is derived, deterministic, run-level** = 0.5·completeness + 0.5·decisiveness, in [0,1]; `needs_more_data` signals sparse profile | `analysis_rules.py` `derive_confidence`; `value_objects.py` `HairstyleResult` |
| **Mock gate on analytics** — experiment events are suppressed for mock data (`_emitExperimentEvent` + `fromMock`); backend unavailable → no experiment events | `lib/shared/analytics/analytics_service.dart`; `FANSIVIBE_STAGE_11_9_ANALYTICS_IMPLEMENTATION_REPORT.md` |
| **Cold-start bug fixed** — `LearningService.setFace` previously had no call sites (40% of pilot scenarios fell to mock); now called in `FaceProcessingScreen._start()` | `FANSIVIBE_STAGE_11_13_FIX_CYCLE_REPORT.md`; commit `0ec42c0`; `face_processing_screen.dart` |
| **Auth = Bearer dev seam** — `deps.py` maps `Bearer dev` → seeded dev user (`dev-user`), D-AUTH-1 (Medium, 0.7) | `backend/app/api/deps.py`; `CURRENT_STATE.md` |
| **OW-1 404-not-403** — foreign/missing run → 404 | `app/application/analysis.py` `GetAnalysisRun`; `app/api/routers/analysis.py` |
| **65/35 card rule = OBSERVATION** — `FansiHeroCard` (image ~65% / content ~35%) is the implemented card family, per MVP audit | `lib/shared/components/fansi_hero_card.dart`; `FANSIVIBE_MVP_AUDIT.md` |

---

## 3. Core concepts and entities

### 3.1 Frontend value objects (`lib/features/hairstyle/data/`)

| Concept | File | Notes |
| --- | --- | --- |
| `FaceScanCheck` | `hairstyle_mock_data.dart` | `mockChecks`: lighting (pass), distance (pass), alignment (fail) — static mock, not live detection. |
| `HairstyleProcessingStage` | `hairstyle_mock_data.dart` | 5 mock stages (detecting, shape, tone, style_dna, recommendations) — cosmetic progress UI. |
| `HairstyleRecommendation` | `hairstyle_mock_data.dart` | id/name/description/matchScore/reasons/stylingTips/maintenance/bestFor (+ icon). Mirrors wire DTO. |
| `HairstyleAnalysisResult` | `hairstyle_mock_data.dart` | faceShape/skinTone/styleDna + top + alternatives; `mock` constant; `fromRunResult`. |
| `AnalysisRun` / `AnalysisRunPage` / `SavedLook` / `hairstyleResultFromRun` | `hairstyle_models.dart` | typed wire models; `isCompleted`/`isFailed`; bare summaries (no result/error). |

### 3.2 Frontend services

| Concept | File | Behavior |
| --- | --- | --- |
| `HairstyleClient` | `hairstyle_client.dart` | HTTP; `ASSISTANT_BASE_URL` default `http://localhost:8000`; `FANSIVIBE_DEV_TOKEN` default `dev`; submit/poll/get/list/save; **null-on-failure** (graceful offline fallback). |
| `HairstyleService` | `hairstyle_service.dart` | Orchestrates `runAnalysis` (submit → poll → result or mock fallback), `listRuns`, `saveLook`; `_devFaceProfileRef` `00000000-0000-0000-0000-000000000001`; `attachLearning`; `analysisError` state; test hooks. |
| `AnalyticsService` (shared) | `lib/shared/analytics/analytics_service.dart` | Six experiment events; non-blocking; `fromMock` gate; `experimentMode` flag. |

### 3.3 On-device learning (personalization memory)

| Concept | File | Notes |
| --- | --- | --- |
| `WardrobeEntry`, `FaceProfile`, `LearningSignal`, `UserModel` | `lib/features/learning/data/models.dart` | On-device user model; `FaceProfile` (faceShape/skinTone/bodyType/styleType); JSON persistence via `LocalStore`. |
| `LearningService` | `lib/features/learning/domain/learning_service.dart` | Singleton; `defaultWardrobe` (24 items mirroring backend catalog); `setFace`, `addSavedLook`, `recordSignal`; `styleScore` = 60 + wardrobe.clamp(0,20) + savedLooks·2.clamp(0,20). |
| `LearningRepository` | `lib/features/learning/learning_repository.dart` | Port; `LearningService` implements it. |

### 3.4 Backend domain (pure, BA-3)

| Concept | File | Notes |
| --- | --- | --- |
| `HairstyleRecommendation`, `GroomingRecommendation`, `HairstylePreferences`, `AppearanceProfile`, `HairstyleResult`, `GroomingResult` | `backend/app/domain/value_objects.py` | Frozen dataclasses mirroring wire DTOs + mock data; `to_snapshot()`. |
| Decision engine (7 stages) | `backend/app/domain/services/analysis_rules.py` | `build_context` → `generate_candidates` → `filter_candidates` → `score_candidates` → `rank_candidates` → `build_explanations` → `recommend_hairstyle`; `derive_confidence`; face-shape boosts `_BOOSTS`; `_PREFERENCE_BOOST` 0.03; `_DECISIVE_GAP` 0.1. |
| `PersonalizationContext` / `assemble_personalization_context` | same file | appearance (style_profile), explicit prefs (preferred_occasions), saved looks; missing → None, never fabricated (AI-0). |

### 3.5 Backend knowledge & catalog

| Concept | File | Notes |
| --- | --- | --- |
| `CatalogKnowledgeSource` | `backend/app/infrastructure/external/knowledge.py` | Implements `KnowledgeSource` port; `retrieve_hairstyle_looks` (KN-3 deprecated filter); read-time validation; `knowledge_version`. |
| `HAIRSTYLE_LOOKS` (4), `GROOMING_LOOKS` (4), `WARDROBE` (24) | `backend/app/data/catalog.py` | `KNOWLEDGE_VERSION = "1.1"`; scoreSeed; stable `code` ids (PR-3); mirrors Flutter mock ids. |

### 3.6 Backend application layer

| Concept | File | Notes |
| --- | --- | --- |
| `CreateHairstyleRun` (UC-25/26) | `backend/app/application/analysis.py` | Profile-only pass (D2); reads `style_profile`; without face → `INSUFFICIENT_USER_DATA` (422) — never fabricates; failure → honest `failed` run (PROCESSING_FAILURE). |
| `CreateOutfitRun` (UC-44) | same | Image-based pass (S-1); TRX-6 updates `style_profile` + `analysis_updated` signal. |
| `CreateGroomingRun` | same | Profile-only pass. |
| `GetAnalysisRun` / `ListAnalysisRuns` | same | Owner-only reads; 404-not-403; summaries carry no `result`. |
| `SaveRecommendation` (UC-15) | `backend/app/application/saved_looks.py` | TRX-3 all-or-nothing; `_SOURCE_CONTEXTS = {hairstyle, grooming}`; idempotent replay / 409; `source_run_id` from snapshot. |
| `enrich_hairstyle_result` | `backend/app/application/enrichment.py` | LLM wording-only additive enrichment (BA-8, AI-0). |

### 3.7 Backend API surface

| Concept | File | Notes |
| --- | --- | --- |
| Routers | `backend/app/api/routers/analysis.py`, `looks.py` | #37/#39/#40/#44 and #23 mounted; auth + owner scoping; error handlers registered. |
| Schemas | `backend/app/api/schemas/analysis.py`, `saved_looks.py` | `AsyncAccepted` (202 run_id), `AnalysisRun` bare, `AnalysisRunSummary` no result/error, `SaveLookRequest`/`SavedLook`. |
| Auth seam | `backend/app/api/deps.py` | D-AUTH-1 placeholder; `Bearer <dev_token>` → seeded dev user; invalid → 401. |
| Errors | `backend/app/api/errors.py` | 401/404/409/422/500 wire `{error: {code, message, details?}}`. |
| Repositories | `backend/app/infrastructure/db/repositories.py` | `AnalysisRunRepositorySQL`, `SavedLookRepositorySQL`, `UserStateRepositorySQL`, `LearningSignalRepositorySQL`; `get_style_profile`/`update_style_profile` (TRX-6). |

---

## 4. Flows

### 4.1 Face scan → recommendation → save (end-to-end)

```
Stylist / Home → HAIR-001 FaceScanScreen
  ├─ checks: FaceScanCheck.mockChecks (static; alignment always failing)
  ├─ tap "Scan Face" → emit appearance_scan_started → push HAIR-002
HAIR-002 FaceProcessingScreen (owns HairstyleService + attachLearning)
  ├─ runAnalysis():
  │    faceShape present? ──no──► mock fallback (HairstyleAnalysisResult.mock)
  │         └─yes─► POST /v1/analysis/hairstyle (faceProfileRef) → 202 run_id
  │                   └─ poll GET /v1/analysis/runs/{run_id}
  │                        ├─ completed → hairstyleResultFromRun(run)
  │                        ├─ failed    → analysisError set; result stays mock
  │                        └─ unreachable → mock
  │    emit appearance_scan_completed (runStatus/pollAttempts)
  ├─ setFace(FaceProfile from result)  ← cold-start fix (0ec42c0)
  └─ navigate HAIR-003 (replaceNamed, extra: result; guarded by _navigated)
HAIR-003 HairstyleResultScreen
  ├─ real result → emit recommendations_viewed + explanation_viewed
  ├─ mock result → NO experiment events (mock gate)
  ├─ "Save Style" → emit recommendation_selected(save) → saveLook()
  │    └─ HairstyleClient.saveLook (Idempotency-Key, snapshot) → 201
  │         ├─ success → snackbar + emit recommendation_saved(success)
  │         └─ failure → snackbar "Could not save"
  ├─ "Try Another" → emit recommendation_selected(dismiss) → back to hairstyle
  └─ card tap → HAIR-004 HairstyleDetailsScreen
HAIR-004 HairstyleDetailsScreen
  ├─ shows % match, description, reasons, styling tips, maintenance, best-for
  └─ "Try This Style" → saveLook (same flow as result screen)
```

### 4.2 Backend run lifecycle

```
POST /v1/analysis/hairstyle  (auth; faceProfileRef XOR image)
  → CreateHairstyleRun
  → style_profile present? no → 422 INSUFFICIENT_USER_DATA (never fabricate)
  → run_id = runs.create(run_type=hairstyle, status=pending)
  → recommend_hairstyle(knowledge, appearance) [+ enrich wording]
  → success: runs.complete(status=completed, result=to_snapshot())
  → failure: runs.fail(status=failed, error=PROCESSING_FAILURE {run_id})
GET /v1/analysis/runs/{run_id}  → owner-only; 404-not-403; bare AnalysisRun
GET /v1/analysis/runs           → paged summaries (no result/error)
POST /v1/looks/saved             → SaveRecommendation (TRX-3, Idempotency-Key)
```

### 4.3 Save transaction (TRX-3)

```
SaveRecommendation:
  validate source_context ∈ {hairstyle, grooming}
  look_id known in knowledge? no → 404 NOT_FOUND
  existing by idempotency? → same payload: replay (created=False) / else 409
  INSERT saved_looks + INSERT learning_signals(look_saved) in one commit
  on error → rollback → 500 DATABASE_FAILURE
```

---

## 5. Contracts

### 5.1 Product / journey contract

- **Supported:** face scan → personalized hairstyle recommendation (match score +
  grounded reasons + deterministic confidence) → informed decision → save to
  profile.
- **Hypothesized (NOT live-verified):** informed decision → saved → profile
  continuity for the hairstyle path specifically (save conversion unmeasurable
  in the n=5 pilot — 0 saves observed, no users instructed to save;
  `FANSIVIBE_STAGE_11_11_INTERNAL_PILOT_REPORT.md`).

### 5.2 API contract (hairstyle surface)

| Endpoint | Method | Request | Response | Notes |
| --- | --- | --- | --- | --- |
| `/v1/analysis/hairstyle` | POST | multipart `faceProfileRef` (or image) | `202 {run_id}` | NOT idempotent; new run each time |
| `/v1/analysis/runs/{run_id}` | GET | — | 200 `AnalysisRun` | owner-only; 404-not-403 |
| `/v1/analysis/runs` | GET | page/page_size | 200 paged summaries | no result/error (PR-5) |
| `/v1/looks/saved` | POST | `SaveLookRequest` + `Idempotency-Key` | `201 SavedLook` | TRX-3; replay/409 |

All protected (Bearer); errors `{error:{code,message,details?}}`.

### 5.3 Analytics contract (six approved experiment events)

| Event | Emitted from | Mock-gated? |
| --- | --- | --- |
| `appearance_scan_started` | `FaceScanScreen._handleScan` | no (real scan initiation) |
| `appearance_scan_completed` | `HairstyleService.runAnalysis` | no (run status; mock path reports run status) |
| `recommendations_viewed` | `HairstyleResultScreen` | **yes** (`isMock`) |
| `explanation_viewed` | `HairstyleResultScreen` | **yes** (`isMock`) |
| `recommendation_selected` | `HairstyleResultScreen` (save/dismiss) | no |
| `recommendation_saved` | `HairstyleResultScreen` save flow | no |

Verified: mock fallback → **no** experiment events
(`FANSIVIBE_STAGE_11_9_ANALYTICS_IMPLEMENTATION_REPORT.md` §4; tests).

### 5.4 Database contract (relevant tables)

Per `docs/database/TABLE_DEFINITIONS.md` + live migrations (`backend/alembic/`):
`users`, `user_state` (`style_profile` JSONB), `looks` (catalog), `run_types`,
`signal_types`, `analysis_runs` (run_type/status/result/error/engine_version,
write-once TRX-5), `saved_looks` (snapshot, idempotency_key, source_run_id),
`learning_signals`. Migration head `0004`. Note: `TABLE_DEFINITIONS.md` describes
23 logical tables (design); the live schema migration implements the actual
subset used by the endpoints.

---

## 6. Decisions and constraints that bind this domain

| Decision/constraint | Source | Status |
| --- | --- | --- |
| AI output is never truth (BAR-0); recommendation = value object; no `Recommendation` table | `HAIRSTYLE_RECOMMENDATION_API.md` §1; `DECISION_ENGINE_ARCHITECTURE.md` | IMPLEMENTED |
| Deterministic rules-first; AI enriches wording only (BA-8, AI-0) | `analysis_rules.py`; `DECISION_ENGINE_ARCHITECTURE.md` | IMPLEMENTED |
| Never fabricate profile inputs (AI-0); `INSUFFICIENT_USER_DATA` instead | `app/application/analysis.py` | IMPLEMENTED |
| D-AUTH-1 dev auth seam (Medium, 0.7) | `deps.py`; `CURRENT_STATE.md` | IMPLEMENTED (placeholder) |
| OW-1 owner scoping, 404-not-403 | repositories + `GetAnalysisRun` | IMPLEMENTED |
| Save idempotent (TRX-3), submit never idempotent | `saved_looks.py`; contract | IMPLEMENTED |
| Knowledge never hardcoded (BA-11); catalog = approved seed (K9.1), versioned (KN-1) | `catalog.py`, `knowledge.py` | IMPLEMENTED |
| Post-mortem/pilot: hairstyle is primary experiment path; grooming postponed | `FANSIVIBE_MVP_AUDIT.md` | IMPLEMENTED |
| `/v1/feedback` (#35) gated/unmounted; save (`look_saved`) is the slice's feedback | `CURRENT_STATE.md`; contract | IMPLEMENTED (save as feedback) |

---

## 7. Marker status by component

| Component | Marker |
| --- | --- |
| Hairstyle decision engine (7 stages) | IMPLEMENTED (deterministic; unit-tested) |
| Knowledge catalog (4 looks, validation, KN-3) | IMPLEMENTED (16 knowledge tests) |
| Save TRX-3 + idempotency | IMPLEMENTED (9 unit tests; live DB tests skip — no PostgreSQL here) |
| Analysis run lifecycle (submit/poll/get/list) | IMPLEMENTED / EXECUTION UNVERIFIED (live DB-backed tests skip) |
| Flutter → backend integration | IMPLEMENTED / NOT LIVE-VERIFIED (default path; mock fallback on unreachable server) |
| Face scan checks (lighting/distance/alignment) | UNTESTED for real detection — static `mockChecks` (alignment always fails) |
| Cold-start `setFace` fix | IMPLEMENTED (commit `0ec42c0`) |
| Analytics six events + mock gate | IMPLEMENTED (39 hairstyle tests; full suite green at Stage 11.9) |
| Pilot conversion hypothesis (≥10% save) | HYPOTHESIS / NOT LIVE-VERIFIED (n=5 internal; not statistically significant) |
| 65/35 card rule | OBSERVATION (implemented card family; no explicit % doc in DESIGN_SYSTEM) |
| Real salon/barber outcome | NOT CLAIMED (out of scope) |

---

## 8. Summary

The Hairstyle domain is **implemented end-to-end at the code level**: the input
path (face scan → profile), the decision engine (7-stage deterministic pipeline
with derived confidence), the catalog (4 validated looks), the async run
lifecycle, the save flow (TRX-3, idempotent), and experiment analytics (six
events, mock-gated) are all present and unit-tested. The product contract's
SUPPORTED half (input + personalized recommendation) is realized; the
HYPOTHESIZED half (informed decision → durable save continuity) is implemented
in code but **not live-verified** — the n=5 internal pilot measured no saves and
was not statistically significant. No claim is made about real-world outcome.

Key open items for any downstream work (extraction only — none fixed here):
real face-detection checks vs. the static mock, live DB-backed endpoint
verification (PostgreSQL not available in this environment), and a statistically
valid real-user experiment to test the save-conversion hypothesis.
