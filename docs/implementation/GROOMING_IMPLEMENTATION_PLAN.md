# STEP 8 — First Production Vertical Slice: Grooming Recommendation

> **Implementation plan only. No code is written by this document.** This plan
> is the result of inspecting the real Fansivibe repository
> (`backend/` + `newproject/flutter_application_1/`) against the STEP 2–7
> accepted designs. It lists every file that will change or be created, the
> reusable code, the required dependencies, the risks, the tests to add, the
> documented conflicts (rule 16), and the **incremental implementation order
> with a validation gate after every stage**.

> **Status: PLANNED — awaiting decision confirmation on the gating items in §5.**

---

## 1. Purpose and scope

Implement **one complete production flow** for grooming recommendations:

```
Flutter → FastAPI → PostgreSQL → Knowledge → Decision Engine → AI (where available)
       → Recommendation → FastAPI → Flutter → Save → Feedback
```

Mapping onto the canonical API contract (`FANSIVIBE_API_CONTRACT_V1.md` §4):

| Contract endpoint | UC | Role in the slice |
| --- | --- | --- |
| `POST /v1/analysis/grooming` (#38) | UC-27 | Submit a grooming analysis request → `202 {run_id}` (async, never idempotent). |
| `GET /v1/analysis/runs/{run_id}` (#39) | — | Poll until `completed | failed`; the completed `result` is the recommendation set (top + alternatives + appearance). |
| `GET /v1/analysis/runs` (#40) | — | Run-history summary list (summary rows, no `result`). |
| `POST /v1/looks/saved` (#23) | UC-15 | **Save** — freeze the immutable `SavedLook` snapshot + `look_saved` signal (TRX-3). **Feedback**: the save action *is* the slice's feedback signal (FEEDBACK_LEARNING_API §3: SAVE is the only fully supported feedback action today); `POST /v1/feedback` (#35) stays **gated / not mounted** (M11). |
| `GET /v1/users/me` (#6) | UC-6 | Profile context read used by the engine (referenced; not re-implemented in this slice unless required). |

The **Decision Engine** runs rules-first (DE-0). AI enrichment is additive and text-only via the existing Ollama seam (`app/ai/llm_backend.py`) — structure, scores, and ranking never come from the LLM.

---

## 2. Source of truth (grounding)

Read for this plan:

- `CURRENT_STATE.md` (STEP 7 COMPLETE — ready for Step 8).
- STEP 2: `docs/architecture/ACTION_API_INVENTORY.md` (actions 21/22),
  `FEATURE_INVENTORY.md`, `SCREEN_DATA_INVENTORY.md`.
- STEP 3: `docs/architecture/FANSIVIBE_DOMAIN_MODEL_V1.md` (E4 `SavedLook`,
  E5 `Look`, E6 `AnalysisRun`, E7 `LearningSignal`).
- STEP 4: `docs/database/TABLE_DEFINITIONS.md` (`users`, `user_state`,
  `analysis_runs`, `saved_looks`, `learning_signals`, `looks`, vocab tables),
  `docs/database/TRANSACTION_BOUNDARIES.md` (TRX-3, TRX-5, TRX-6),
  `docs/database/HISTORY_AND_VERSIONING.md` (§5.7/5.8/5.9).
- STEP 5: `docs/backend/FASTAPI_ARCHITECTURE_V1.md`, `APPLICATION_USE_CASES.md`
  (UC-27), `DECISION_ENGINE_ARCHITECTURE.md` (stages 5–8),
  `KNOWLEDGE_ARCHITECTURE.md` (K9.1, KN-1), `AI_INTEGRATION_ARCHITECTURE.md`
  (`AIProvider` seam, AI-0/AI-5), `BACKGROUND_JOB_ARCHITECTURE.md` (in-process
  run, TRX-5 write-once), `BACKEND_FOLDER_STRUCTURE.md`.
- STEP 6: `docs/api/FANSIVIBE_API_CONTRACT_V1.md` (canonical), `docs/api/
  HAIRSTYLE_RECOMMENDATION_API.md` (§4.2/4.3/5), `docs/api/APPEARANCE_API.md`,
  `docs/api/FEEDBACK_LEARNING_API.md`, `docs/api/PAGINATION_FILTERING.md`,
  `docs/api/API_ERROR_CONTRACT.md` (12-category taxonomy), `docs/api/
  API_RESPONSE_CONVENTIONS.md`, `docs/api/API_SECURITY_REVIEW.md`.
- Real repo: `backend/app/{main.py,models/schemas.py,ai/*,data/catalog.py}`,
  `backend/tests/*`, `backend/requirements.txt`, `backend/docker-compose.yml`;
  `newproject/flutter_application_1/lib/features/hairstyle/**`,
  `lib/features/assistant/**` (HTTP client pattern),
  `lib/app/router/app_router.dart`, `test/hairstyle_*_test.dart`.

---

## 3. What exists today (verified snapshot)

### Backend — `backend/`

- **Two routes only**: `GET /health`, `POST /v1/assistant/chat`
  (`app/main.py:18,23`). Assistant DTOs frozen in `app/models/schemas.py`.
- Assistant rules engine: `app/ai/engine.py` (dialogue policy),
  `app/ai/intent.py`, `app/ai/tools.py` (`recommend_hairstyle` uses a simple
  face-shape switch → 2 `SuggestionCard`s), `app/ai/llm_backend.py` (optional
  Ollama text enrichment, degrades gracefully).
- Knowledge seed: `app/data/catalog.py` — mirrors Flutter mock data; currently
  only 2 hairstyles as `SuggestionCard`s (`TEXTURED_QUIFF`, `CLASSIC_POMPADOUR`).
- **No PostgreSQL, no SQLAlchemy, no asyncpg/psycopg, no Alembic, no `.env`,
  no DB container** (`docker-compose.yml` only runs Ollama). The DB layer does
  not exist yet.
- Tests: 19 passing (`tests/test_engine.py`, `tests/test_intent.py`).

### Flutter — `newproject/flutter_application_1/`

- Grooming feature is **mock-driven**:
  - `data/grooming_mock_data.dart` — `GroomingRecommendation` (id/name/description/matchScore/reasons/beardLength/cheekLine/eyewearFrame/eyewearRecommendation/stylingTips/maintenance/bestFor) and `GroomingAnalysisResult` (faceShape/beardStyle/beardDensity/beardColor/topRecommendation/alternatives), mock pipeline with 5 processing stages, 6 beard style options, 6 density options, 6 color options — the wire DTO must mirror this.
  - `presentation/grooming_input_screen.dart` — 4-option selector (face shape, beard style, density, color) → push to processing with route extras.
  - `presentation/grooming_processing_screen.dart` — **fake timers** play the 5 mock `GroomingProcessingStage`s, then `context.replaceNamed(groomingResult)`.
  - `presentation/grooming_result_screen.dart` — renders `GroomingAnalysisResult.mock`; "Save Look" → snackbar only; "Try Another" → route home.
  - `presentation/grooming_details_screen.dart` — renders a passed-in `GroomingRecommendation`; "Try This Look" → snackbar only.
  - `presentation/widgets/grooming_widgets.dart` — `GroomingOptionChip`, `GroomingOptionSection`, `GroomingStageIndicator`, `GroomingRecommendationCard` (score bands, specs, reasons, maintenance, eyewear).
- Routing (go_router, untouched): `/grooming/input/processing/result/details` (`app_router.dart:266-298`); details receives the recommendation via `state.extra`.
- HTTP pattern to reuse: `features/assistant/data/assistant_client.dart` (base URL via `--dart-define=ASSISTANT_BASE_URL`, `http` package, timeout, returns `null` on failure → offline fallback) + `domain/assistant_service.dart` (ChangeNotifier orchestration).
- Tests: 4 grooming test files (input, processing, result, details screen tests).

---

## 4. Documented conflicts (rule 16 — before changing code)

These are conflicts between the accepted architecture/contract and what STEP 8
requires. Each is documented here; **the resolutions require confirmation in §5
before stage 0/1 implementation**.

### C-1 — Analysis endpoints are contractually "NOT mounted" (API-12 gating)

`HAIRSTYLE_RECOMMENDATION_API.md` §8.1/8.2 and `FANSIVIBE_API_CONTRACT_V1.md`
§3.4 mark the M12 analysis surface (`POST /v1/analysis/hairstyle`,
`GET /v1/analysis/runs/{run_id}`, `GET /v1/analysis/runs`) as **not mounted**
until **D-AUTH-1** (auth provider) + **MS10.3** (media seal) + a real analysis
pipeline land. STEP 8 explicitly implements this surface as the first
production slice. **STEP 8 therefore IS the milestone that mounts these
endpoints** — a deliberate, task-mandated deviation from "stay unmounted".
Resolution needed: the auth and media seams (C-2, C-3). This is not a wire or
DTO change; it is a mounting decision.

### C-2 — No auth exists anywhere (D-AUTH-1 still open)

The contract requires Bearer auth + owner-only (OW-1, 404-not-403) on
endpoints #38/#39/#40/#23. The real app and backend have **no auth**. Per
FASTAPI_ARCHITECTURE_V1 §19/M1, `deps.py` is a stub until D-AUTH-1. Resolution
proposed: a **dev-identity seam** — `deps.py` resolves a bearer token to a
seeded/dev `user_id` (documented placeholder for D-AUTH-1, owner scoping still
enforced). See §5.D1.

### C-3 — Media seal (MS10.3) blocks face-image submission

`POST /v1/analysis/grooming` takes `faceProfileRef` (profile-only pass). The M16
media pipeline is sealed until MS10.3, and the Flutter grooming input screen has
no real image capture today. Resolution proposed: the first slice uses the
**profile-only pass (`faceProfileRef`)** — the recommendation re-rank path
(contract §5.7 H-7, "regenerate" form) — grounded on the stored
`user_state.style_profile`; face-image upload is **additive** and stays behind
MS10.3. This preserves honesty (no fake 200, no fabricated face analysis) and the
contract's shapes. See §5.D2.

### C-4 — Backend has no database infrastructure

STEP 4 defines a PostgreSQL schema; STEP 5 M3 defines the migrations milestone;
none of it exists in `backend/`. The vertical slice cannot reach PostgreSQL
without adding the DB layer. Resolution proposed: add SQLAlchemy 2.0 + a
PostgreSQL driver + Alembic + a Postgres service in `docker-compose.yml`, and
create the **minimal table subset** the slice needs (exact STEP 4 shapes). See
§5.D3.

### C-5 — Feedback surface is feature-gated (M11)

`POST /v1/feedback` (#35) is gated on an accepted feedback UI and is **not**
mounted. Resolution: the slice's "Feedback" = the **`look_saved` learning
signal** written by the save transaction (TRX-3) — the documented feedback
action for this flow (FEEDBACK_LEARNING_API §3, F-4). `/v1/feedback` remains
unmounted. No deviation from the contract.

### C-6 — Target folder structure vs. current flat backend layout

FASTAPI_ARCHITECTURE_V1 §19 (M1) migrates `app/ai|data|models` into
`app/{api,application,domain,infrastructure}`. That is a separate migration
milestone and **out of scope for STEP 8** (rule 1/8: do not rewrite the
backend). Resolution: build the **new** slice in the target structure
(`app/api/…`, `app/application/…`, `app/domain/…`, `app/infrastructure/…`)
alongside the untouched assistant code; the assistant keeps using its current
paths until M1.

### C-7 — Feedback/save wiring vs. unrelated screens

The profile "Saved Looks" screen (`saved_looks_screen.dart`) reads
`ProfileMockData.savedLooks`. Wiring it to the real saved-look list is an
**unrelated screen** — out of scope (rule 7/9). The slice saves to the backend
and confirms via snackbar, exactly as the screen does today.

### C-8 — Grooming mock data vs. production wire shapes

The grooming mock data (`grooming_mock_data.dart`) has a different DTO shape
than the hairstyle mock data. The production wire must mirror the hairstyle
recommendation contract (§4.3 HAIRSTYLE_RECOMMENDATION_API.md) adapted for
grooming vocabulary, not the current mock shapes. The mock data will be
replaced by fromJson/toJson models that mirror the API contract.

---

## 5. Decisions to confirm before implementation

| # | Decision | Recommended resolution | Why |
|---|---|---|---|
| **D1** | **Auth seam (C-2)** | Dev-identity bearer seam in `deps.py`: token → seeded dev `user_id`; owner scoping (404-not-403) fully enforced. | Unblocks mounting #38/#39/#40/#23 now; D-AUTH-1 lands later as an additive swap behind the same `deps.py`. No contract change. |
| **D2** | **Face-image vs profile-only (C-3)** | First slice uses **profile-only pass (`faceProfileRef`)** over stored `user_state.style_profile`; image upload deferred behind MS10.3. | Honest (no fake analysis), matches contract §5.7 re-rank path, keeps M16 sealed, no Flutter camera changes needed. |
| **D3** | **Database layer (C-4)** | SQLAlchemy 2.0 + `psycopg[binary]` + Alembic; Postgres service added to `docker-compose.yml`; minimal STEP-4 table subset (see §8.2). | Aligns with architecture M3; the slice's flow explicitly requires PostgreSQL. `Alembic-vs-SQL` is the documented M3 open item — Alembic recommended. |
| **D4** | **AI enrichment scope** | Rules-only engine is the deliverable; optional Ollama **text-wording** enrichment of `description`/reasons reuses `llm_backend.py` (never structure/scores). | DE-0 + AI-0 honesty; AI "where available" = the existing seam. |
| **D5** | **Save UI behavior** | "Save Look" / "Try This Look" POST `#23` with an `Idempotency-Key`; on success keep the existing snackbar confirmation. | Minimal UI change (button action only), preserves design (rule: UI safety). |

All five follow the accepted contracts. Any alternative resolution changes the
slice's scope; confirm before stage 0/1.

---

## 6. The slice architecture (end-to-end)

```
Flutter GroomingFlow (input → processing → result → details)
   │  POST /v1/analysis/grooming  {faceProfileRef}            (profile-only, D2)
   ▼
api/routers/analysis.py  ── deps.py (dev seam, D1) → user_id
   │  UC-27 (application/grooming.py)
   ▼
GroomingRunRepository (infrastructure/db)     INSERT grooming_runs (pending)   [TRX-5 start]
   │
DecisionEngine (domain/services/grooming_rules.py — stage order)
   │  ContextBuilder(catalog: looks + user_state.style_profile)
   │  → CandidateGeneration(grooming catalog options)
   │  → Scoring(face-shape switch, deterministic weights)
   │  → Ranking(top + alternatives)
   │  → Explanation(grounded reasons from catalog)
   │  → Recommendation(GroomingRecommendation DTO)          [rules-first, DE-0]
   │  optional LLM wording enrichment via llm_backend seam   [D4]
   ▼
guarded completion UPDATE grooming_runs SET status='completed', result=…   [TRX-5 write-once]
   │  TRX-6: user_state.style_profile ← latest face attributes (from stored profile; no-op today, D2)
   ▼
Flutter polls GET /v1/analysis/runs/{run_id} → 200 {run_id,status,result{appearance,recommendations{top,alternatives}}}
   ▼
Flutter result/details screens render fetched data (reuse GroomingRecommendation widgets)
   ▼
Flutter "Save" → POST /v1/looks/saved {lookId,title,sourceContext:"grooming",snapshot} + Idempotency-Key
   │  UC-15 (application/saved_looks.py)
   ▼
TRX-3 true transaction: INSERT saved_looks (immutable snapshot) + INSERT learning_signals(look_saved)
   ▼
FEEDBACK: the save signal is the slice's feedback; POST /v1/feedback stays gated (C-5)
```

**Endpoints mounted in this slice:** `#38`, `#39`, `#40`, `#23`.
**Endpoints intentionally NOT mounted:** `#35` (feedback, gated), M16 media (sealed),
`#6` `GET /v1/users/me` (referenced only).

---

## 7. Incremental implementation order (validate after every stage)

### Stage 0 — Infrastructure: PostgreSQL access (D3)

- Add `sqlalchemy>=2.0`, `psycopg[binary]`, `alembic` to `backend/requirements.txt`.
- Add a `postgres` service to `backend/docker-compose.yml` (env: DB name/user/pass, port 5432).
- Create `backend/app/infrastructure/db/` — engine/session factory + `Base` + dependency. Alembic scaffolding (`alembic.ini`, `env.py`, `migrations/versions/`).
- **Validation gate:** `.venv/bin/python -m pytest -q` — existing 19 tests still green (no app code touched); Postgres container boots.

### Stage 1 — Backend: knowledge catalog (M5 subset, K9.1)

- Extend `app/data/catalog.py` (or seed `app/infrastructure/external/knowledge.py`) with the full grooming catalog mirroring `grooming_mock_data.dart` (id = `looks.code`, name, description, matchScore seed, reasons, eyewearFrame, eyewearRecommendation, stylingTips, maintenance, bestFor) — keep existing hairstyle catalog shapes intact so the assistant surface is unchanged.
- Alembic migration: create **knowledge tables** `looks`, `run_types`, `signal_types` + seed `looks` rows + `run_types('grooming')` + `signal_types('look_saved')` (exact STEP-4 shapes).
- **Validation gate:** migration applies to a fresh DB; a seed re-run is idempotent; existing 19 tests green.

### Stage 2 — Backend: decision engine (M6 domain, rules-first)

- `app/domain/` (pure Python, no FastAPI/SQLAlchemy/HTTP — BA-3): typed value objects mirroring the wire (`GroomingRecommendation`, `AppearanceProfile`), and `app/domain/services/grooming_rules.py` implementing **ContextBuilder → CandidateGeneration → Scoring → Ranking → Explanation → Recommendation** for grooming only (per-task composition, no empty framework). Scores from the seeded catalog constants; face-shape switch mirrors `tools.recommend_hairstyle`; reasons grounded in catalog text (never invented).
- **Validation gate:** new unit tests for the engine stages (see §11); 19 existing tests green.

### Stage 3 — Backend: analysis run API (M12, UC-27)

- `app/domain/ports/` (repositories, `KnowledgeSource` port) + `app/infrastructure/db/repositories.py` (`GroomingRunRepository` with the guarded write-once completion, `UserStateRepository` read).
- `app/application/grooming.py` — `CreateGroomingRun` + `GetAnalysisRun` + `ListAnalysisRuns` use cases (TRX-5 boundary).
- `app/api/deps.py` (dev seam, D1), `app/api/errors.py` (12-category mapper), `app/api/schemas/analysis.py` (the canonical `AnalysisRun` DTO incl. `input_media?` per ¶7.I-1), `app/api/routers/analysis.py` (`POST /v1/analysis/grooming` → `202 {run_id}`; `GET /v1/analysis/runs/{run_id}` → bare `AnalysisRun`, owner-only 404; `GET /v1/analysis/runs` → `{items,page,page_size,total}` summary, no `result`). In-process synchronous completion (BJ-1, no Celery).
- Mount routers in `main.py`. `POST /v1/assistant/chat` + `/health` untouched.
- **Validation gate:** new pytest API tests (202/200/404/422 shapes, write-once guard, owner scoping); existing 19 green; `dart format`/`flutter analyze` on the unchanged app still clean.

### Stage 4 — Backend: save + feedback signal (M7, UC-15)

- `app/infrastructure/db/repositories.py` — `SavedLookRepository` + `LearningSignalRepository`.
- `app/application/saved_looks.py` — `SaveRecommendation` use case.
- `app/api/schemas/saved_looks.py` + `app/api/routers/looks.py` (`POST /v1/looks/saved` → `201 SavedLook`, **`Idempotency-Key` required**, TRX-3: saved_looks INSERT + learning_signals `look_saved` INSERT commit together; `source_run_id` SET NULL provenance when the producing run is named).
- **Validation gate:** pytest for TRX-3 (both rows or neither), idempotency (replay returns original), 404 look/409 duplicate/422; existing 19 green.

### Stage 5 — Backend: AI enrichment (D4, additive)

- Optional text-wording enrichment of `description`/reason bullets via the
  `llm_backend.py` seam, degraded path preserved (`details.degraded` boolean
  only on the wire — no provider internals, C-8). Runs only when Ollama is
  reachable; never changes structure/scores (BA-8, AI-0).
- **Validation gate:** engine tests prove rules-only output is identical when
  the LLM is disabled; existing 19 green.

### Stage 6 — Flutter: data layer

- `lib/features/grooming/data/grooming_models.dart` — wire DTOs
  (`AnalysisRun`, `GroomingRecommendation` fromJson — mirroring the contract
  §4.3 fields + `matchScore`), per the `flutter-implement-json-serialization` skill.
- `lib/features/grooming/data/grooming_client.dart` — mirrors
  `assistant_client.dart` (same base URL convention, `http`, timeout, safe
  failure): `submitGroomingAnalysis(faceProfileRef)`, `getAnalysisRun(id)`,
  `listRuns()`, `saveLook(...)` with `Idempotency-Key`.
- `lib/features/grooming/domain/grooming_service.dart` — ChangeNotifier
  orchestrator (submit → poll loop → expose result; save). Optional offline
  fallback mirroring `offline_assistant.dart` (deterministic mock result) so
  the app never breaks offline.
- **Validation gate:** `flutter analyze` clean; new unit tests for
  models/client/service; all 30+ existing test files still pass.

### Stage 7 — Flutter: wire the grooming flow (UI-safety-compliant)

- `grooming_input_screen.dart` — replace the manual selector + push with the
  **real submit → poll** flow; retain the 4-option UI; on result received,
  populate the screening data and navigate to processing/result; accept the
  result via `state.extra` (router passes it; minimal additive router edit,
  fall back to mock when absent so navigation/tests survive).
- `grooming_processing_screen.dart` — replace the fake timer with the real
  **submit → poll** flow (visual stage indicators retained; stages advance on
  real status transitions, not fake durations); on failure show the existing
  error/retry affordances (reuse `FansiErrorView`/`FansiLoadingView`).
- `grooming_result_screen.dart` — render the fetched
  `GroomingAnalysisResult` instead of `GroomingAnalysisResult.mock`; "Save
  Look" → `service.saveLook(...)` (keep snackbar confirmation). Accept the
  result via `state.extra` (router passes it; fall back to mock when absent
  so navigation/tests survive).
- `grooming_details_screen.dart` — "Try This Look" → `service.saveLook(...)`.
- `app_router.dart` — only the additive extra-passing for `groomingResult`
  (rule 4: no routing replacement; global navigation untouched).
- **No changes** to unrelated screens, widgets, theme tokens, card proportions,
  65/35 card rule, or Digital Atelier visual language.
- **Validation gate:** `flutter analyze` clean; updated + new grooming widget
  tests (see §11); full `flutter test` passes.

### Stage 8 — Save + feedback verification, end-to-end

- Manual E2E: backend up + Postgres up + app → grooming flow → result → save →
  verify `saved_looks` row + `learning_signals` row; run history list shows the
  completed run.
- **Validation gate:** backend pytest + `flutter test` all green; `git status`
  reviewed; `CURRENT_STATE.md` updated.

---

## 8. Files

### 8.1 Files that will be changed

**Backend**

| File | Change |
| --- | --- |
| `backend/requirements.txt` | add `sqlalchemy`, `psycopg[binary]`, `alembic` (D3) |
| `backend/docker-compose.yml` | add `postgres` service (D3) |
| `backend/app/main.py` | mount analysis + looks routers (live routes untouched) |
| `backend/app/data/catalog.py` | extend grooming catalog to full 6-option sets (Stage 1) |

**Flutter**

| File | Change |
| --- | --- |
| `lib/features/grooming/presentation/grooming_input_screen.dart` | wire to real submit/poll flow; retain UI |
| `lib/features/grooming/presentation/grooming_processing_screen.dart` | real submit/poll instead of fake timers |
| `lib/features/grooming/presentation/grooming_result_screen.dart` | render fetched result; wire Save Look |
| `lib/features/grooming/presentation/grooming_details_screen.dart` | wire Try This Look (save) |
| `lib/app/router/app_router.dart` | additive: pass fetched result via `state.extra` to `groomingResult` |

### 8.2 Files that will be created

**Backend**

| File | Layer | Purpose |
| --- | --- | --- |
| `app/infrastructure/db/__init__.py`, `session.py` | infra | engine/session factory, `Base` |
| `app/infrastructure/db/repositories.py` | infra | `GroomingRunRepository` (write-once guard), `SavedLookRepository`, `LearningSignalRepository`, `UserStateRepository` read |
| `app/domain/ports/repositories.py`, `app/domain/ports/external.py` | domain | repository + `KnowledgeSource`/`AIProvider` ports |
| `app/domain/value_objects.py` | domain | `GroomingRecommendation`, `AppearanceProfile`, snapshot value objects (mirror wire) |
| `app/domain/services/grooming_rules.py` | domain | the grooming decision-engine stages (rules-first) |
| `app/application/grooming.py` | application | UC-27 use case: Create/Get/List grooming runs |
| `app/api/deps.py` | api | dev-identity auth seam (D1) |
| `app/api/errors.py` | api | 12-category error mapper |
| `app/api/schemas/analysis.py` | api | `AnalysisRun` (canonical incl. `input_media?`), `AsyncAccepted`, summary DTO |
| `app/api/schemas/saved_looks.py` | api | `SaveLookRequest`, `SavedLook` |
| `app/api/routers/analysis.py`, `app/api/routers/looks.py` | api | `#38/#39/#40`, `#23` |
| `alembic.ini`, `alembic/env.py`, `migrations/versions/0001_*.py` | infra | STEP-4 schema for the slice |
| `backend/tests/test_grooming_api.py`, `test_grooming_rules.py`, `test_saved_looks.py`, `test_db_session.py` | tests | see §11 |

**Flutter**

| File | Purpose |
| --- | --- |
| `lib/features/grooming/data/grooming_models.dart` | wire DTOs (`AnalysisRun`, recommendation fromJson/toJson) |
| `lib/features/grooming/data/grooming_client.dart` | HTTP client (mirrors `assistant_client.dart`) |
| `lib/features/grooming/domain/grooming_service.dart` | submit/poll/save orchestration (ChangeNotifier) |
| `lib/features/grooming/data/grooming_offline.dart` | deterministic offline fallback (optional, mirrors `offline_assistant.dart`) |
| `test/grooming_models_test.dart`, `test/grooming_client_test.dart`, `test/grooming_service_test.dart` | see §11 |

### 8.3 Reusable code (do not duplicate)

- Backend: `app/data/catalog.py` (knowledge seed; grooming look content + stable codes), `app/ai/llm_backend.py` (AI seam, `is_available()`/`enrich_reply`, degrade-safe), `app/ai/tools.py:recommend_hairstyle` (face-shape scoring seed), `app/ai/intent.py` (unchanged), `app/models/schemas.py` (untouched; assistant DTOs frozen).
- Flutter: `assistant_client.dart` (client pattern incl. base-URL define), `offline_assistant.dart` + `assistant_service.dart` (service pattern), `grooming_mock_data.dart` (the grooming catalog the wire mirrors — will be replaced by models), `grooming_widgets.dart` (`GroomingOptionChip`, `GroomingOptionSection`, `GroomingStageIndicator`, `GroomingRecommendationCard`), `FansiHeroCard`/`FansiImageWell`/`FansiBadge`/`FansiButton` (65/35 card), `FansiErrorView`/`FansiLoadingView`, theme tokens (Digital Atelier), go_router extras pattern already used by details/grooming.

---

## 9. Dependencies

| Dependency | Where | Justification | Alternative considered |
| --- | --- | --- | --- |
| `sqlalchemy>=2.0` | backend | STEP-4 PostgreSQL layer (M3) | raw `psycopg` SQL (more code, no ORM safety) |
| `psycopg[binary]` | backend | PostgreSQL driver | `asyncpg` (async; larger change to the sync engine) |
| `alembic` | backend | schema migrations (M3) | hand-written SQL scripts (not versioned) |
| `postgres:16` (docker-compose service) | dev env | the slice's PostgreSQL | none — flow requires PostgreSQL |
| None added to Flutter | — | `http` + `go_router` + `ChangeNotifier` already cover the slice | no new state-management or networking package |

**Explicitly NOT added:** new Flutter packages (rule 10), Celery/Redis/queue
(BJ-1), an AI SDK (BA-8/AI-0), any auth provider SDK (D-AUTH-1 stays a seam).

---

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| **DB-layer addition is the biggest infra change** — new deps + container + migrations could destabilize the working backend. | Keep it additive behind `infrastructure/db/`; assistant code untouched; 19-test gate at every stage; migration only creates new tables. |
| **Contract gating (C-1/C-2/C-3)** — mounting analysis before D-AUTH-1/MS10.3 is a documented deviation. | Confirm D1/D2 (§5); the dev seam + profile-only pass keep it honest (no fake 200); real auth/media swap in additively. |
| **Result screen refactor may break existing widget tests** (`grooming_result_screen_test.dart` asserts on `GroomingAnalysisResult.mock`). | Router extra falls back to the mock when no result is provided; update tests to pump with a fetched result while preserving their assertions. |
| **Write-once correctness (TRX-5)** — double completion or failed-result overwrite would corrupt history. | Guarded `UPDATE … WHERE status='pending'` + `INSERT/SELECT`-only DB grants (PR-5), tested. |
| **LLM never changes structure** — prompt injection into reasons would violate honesty. | LLM enriches wording only; reasons come from the catalog; C-8 no-internals on the wire; `details.degraded`. |
| **Owner scoping (OW-1)** — another user's `run_id` must 404, not 403/200. | Repository queries always carry `user_id`; 404-not-403 enforced and tested. |
| **UI safety** — risk of redesigning the grooming screens. | Only the data source + button actions change; widgets/tokens/cards/navigation untouched; existing tests preserved. |
| **Save idempotency** — double-tap creates duplicate saved looks. | `Idempotency-Key` client-generated per save + server replay (TRX-3). |

---

## 11. Tests to add

**Backend (`pytest`)**

1. `test_grooming_rules.py` — engine: candidates from catalog; scoring by face
   shape (round/square → pompadour-first); ranking order (top + alternatives);
   explanation reasons grounded in catalog (never invented); rules-only output
   is stable with LLM disabled.
2. `test_grooming_api.py` — `POST /v1/analysis/grooming` → 202 `{run_id}`;
   `GET /v1/analysis/runs/{run_id}` pending → completed `result` shape
   (`appearance` + `recommendations{top,alternatives}`); failed path; malformed
   UUID → 422; foreign/nonexistent run → 404; list returns summary rows with no
   `result`; write-once guard (second completion rejected).
3. `test_saved_looks.py` — TRX-3: saved_looks + `look_saved` signal commit
   together; `Idempotency-Key` replay returns the original; invalid `lookId` →
   404/422; duplicate → 409; title bounds.
4. `test_db_session.py` — session factory, migration idempotency, knowledge
   seed idempotency, PR-5 read-only grants for history tables.
5. Existing `tests/test_engine.py` + `tests/test_intent.py` must stay green
   (unchanged behavior).

**Flutter (`flutter test`)**

1. `test/grooming_models_test.dart` — `AnalysisRun`/recommendation
   fromJson/toJson round-trip against the contract example (§4.3).
2. `test/grooming_client_test.dart` — submit returns run_id on 202; poll maps
   200 pending/completed/failed; non-200/network failure → null (offline path).
3. `test/grooming_service_test.dart` — submit→poll→result sequence; save sends
   `Idempotency-Key`; failure falls back to offline/mock.
4. Update `test/grooming_processing_screen_test.dart` — processing uses real
   poll flow (mock the service); `test/grooming_result_screen_test.dart` —
   renders a fetched result and save calls the service; `test/grooming_details_
   screen_test.dart` — save wiring.
5. All 30+ existing test files must stay green (rules 8/9).

---

## 12. Out of scope (explicitly not implemented here)

- No changes to the assistant contract or its DTOs (F-13), wardrobe, discover,
  events, onboarding, profile screens.
- No `POST /v1/feedback` (gated M11), no M16 media pipeline, no `GET
  /v1/users/me` route (referenced only).
- No face-image upload (deferred behind MS10.3, D2).
- No full 8-stage engine framework — only the grooming task's stages (no
  empty architecture layers, per the over-engineering audit).
- No M1 folder migration of the assistant code (C-6).
- No saved-looks list screen rewire (C-7).
- No subscription/learning-summary/discover features.

---

## 13. Report

**Inspection performed:** real repo (`backend/app/**`, `backend/tests/**`,
`newproject/flutter_application_1/lib/features/grooming/**`, assistant data
layer, router, tests) + STEP 2–7 docs (domain model, table definitions,
architecture, API contract + grooming module contract). **No code changed.**

**Validation run:** none needed — plan-only; no `pytest`/`flutter test`
executed because no code was modified.

**Remaining:** confirm D1–D5 (§5), then implement Stage 0 → 8 with the gate
after every stage; update `CURRENT_STATE.md` after each meaningful stage and
add a `DECISIONS.md` entry for the accepted mounting decision (C-1/D1/D2) once
confirmed.