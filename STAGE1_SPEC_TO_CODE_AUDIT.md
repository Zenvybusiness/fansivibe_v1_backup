# Fansivibe Stage 1 — Specification-to-Code Audit

**Document Type:** Authoritative Specification-to-Code Traceability and Gap Audit  
**Date:** 2026-10-31  
**Repository:** `/home/tony/projects/fansivibe_v1_backup`  
**Authoritative Committed Baseline:** Commit `97f6ded99d3f3e67b477616380320058cd396f48` (`main`)  
**Working Tree State:** Clean (verified via `git status --short`)  
**Verification Method:** Strict static code, schema, and documentation inspection. No live database connections, no pytest execution, no Flutter test/analyze execution, and no live AI provider calls.

---

## 1. Executive Summary

This audit establishes the definitive, evidence-backed baseline of Stage 1 across the Fansivibe Flutter client, FastAPI backend, domain services, Alembic migrations, and relational persistence.

A crucial repository milestone was achieved in commit `97f6ded` (incorporating Tasks STAGE1-BATCH-1, STAGE1-BATCH-2, and STAGE1-BATCH-3.1). Specifically:
1. **Outfit Scan now performs real garment evaluation**: Both `CreateOutfitRun` (authenticated) and `EphemeralOutfitAnalysis` (guest) sequentially execute `AppearanceAnalysisPort` and `GarmentAnalysisPort`. The Flutter client (`outfit_analysis_screen.dart`) now renders real garment visual attributes and handles typed branch failures (`garment_error`, `appearance_error`). Older audit claims stating Outfit Scan never invokes garment analysis are now outdated.
2. **Truth containment was established**: Empty appearance attributes (`skinTone`, `styleDna`) are hidden in `hairstyle_result_screen.dart`, false progress claims ("Analyzing skin tone", "Applying Style DNA") were replaced or muted in primary paths, `rectangle` was canonicalized to `rectangular` across scoring rules, and post-auth snackbar copy no longer falsely claims discarded local progress was kept.
3. **Guest preview cache semantics were hardened**: `hasCachedOutfitPreview()` requires a renderable outfit snapshot, preventing malformed or error-only stashes from reporting a valid cache.

However, fundamental architectural limitations persist:
- **No principled person model**: There is no dedicated Person entity or observation ledger. User attributes reside in a loosely structured JSONB blob (`user_state.style_profile`).
- **Authority split**: Flutter profile and onboarding screens read and write client-local storage (`LocalStorage`, `LearningService`), while the backend exposes a `ProfileView.styleProfile` that Flutter never consumes.
- **Data loss in guest-to-authenticated conversion**: `GuestDataMigration` migrates wardrobe items and preferred occasions, but explicitly discards face/appearance attributes, style type, and analysis blobs without user disclosure.
- **Concurrency & provenance gaps**: `UserStateRepositorySQL.update_style_profile` merges non-empty fields via PostgreSQL `||` without checking or incrementing `user_state.version`, creating a last-writer-wins hazard and overwriting the object-level `source_run_id`.
- **Diverging AI paths**: `backend/app/ai/tools.py` contains hardcoded mini-tools with an `oval` face-shape fallback that bypass the deterministic Decision Engine in `backend/app/domain/services/analysis_rules.py`.

---

## 2. Specification Inventory & Missing Specifications

### 2.1 Audited Specification Inventory

| Document Path | Document Title & Type | Status in Repository | Relevance to Stage 1 |
|---|---|---|---|
| `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` | Requirements-to-Code Traceability Matrix | Static Audit (dated 2026-10-24, baseline `741493d`) | Contains 21 target requirements (R-S1-1 through R-X-2) across 6 subjects and 4 capabilities. |
| `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` | AI Stylist Product-Contract Specification | Formal Specification (dated 2026-09-27) | Defines 10 core AI Stylist contracts: C-01 through C-10. |
| `PHASE_1_STEP2_OWNER_DECISIONS.md` | Owner Decisions on AI Stylist Contracts | Founder Decisions Document (dated 2026-09-27) | Records owner approvals (C-01, C-02 Option B, C-03, C-04 Option A, C-05, C-08, C-10 Option B) and pending items (C-06, C-07, C-09). |
| `PHASE_1_FINAL_INTEGRATION_AUDIT.md` | AI Stylist C-01 → C-10 Integration Audit | Prior Audit (dated 2026-09-27) | Traced Flutter → API → Use Case → Domain → DB integration flow. |
| `PHASE_1A_P0_CORRECTNESS_AND_CONTRACT_AUDIT.md` | P0 Correctness and Contract Audit | Prior Audit (dated 2026-09-26) | Foundational P0 defect catalog across auth, wardrobe, and scoring. |
| `docs/backend/KNOWLEDGE_ARCHITECTURE.md` | Knowledge Architecture | Backend Architecture Guide | Separates curated style knowledge (`CatalogKnowledgeSource`) from user data. |
| `docs/backend/DECISION_ENGINE_ARCHITECTURE.md` | Decision Engine Architecture | Backend Architecture Guide | Defines the 9-stage decision pipeline (Context → Candidates → Filter → Score → Rank → Explain → Recommend → Feedback). |
| `docs/architecture/AI_DOMAIN_MODEL.md` | AI Domain Model | Architecture Specification | Defines value objects: `AppearanceProfile`, `GarmentProfile`, `AnalysisSnapshot`. |
| `docs/architecture/DOMAIN_STATE_AND_HISTORY.md` | Domain State and History | Architecture Specification | Defines entity state versus event ledger boundaries. |
| `docs/architecture/DOMAIN_ENTITIES.md` | Domain Entities Specification | Architecture Specification | Defines `User`, `UserState`, `WardrobeItem`, `Look`, `UserEvent`. |
| `docs/api/PROFILE_ONBOARDING_API.md` | API Contract: Profile, Preferences & Onboarding | API Design Draft (Step 6) | Proposes profile sync operations; partially implemented. |
| `DECISIONS.md` | Repository Accepted Decisions Ledger | Authoritative Decisions | Formal repository invariant records (DEC-001 through DEC-032). |
| `CURRENT_STATE.md` | Current Engineering State | Task & Batch Ledger | Authoritative record of completed tasks through STAGE1-BATCH-3.1. |

### 2.2 Missing or Unapproved Specifications

The repository does **not** contain approved, formal specifications for the following core areas:
1. **Track A — Fashion / Style Knowledge Specification**: No formal document specifies fashion theory rules, seasonal color palettes, or garment harmony taxonomies beyond what is embedded in static Python dictionaries in `backend/app/data/catalog.py`.
2. **Track B — Decision and Recommendation Logic Specification**: No approved document defines scoring thresholds, weight calibration, candidate generation bounds, or diversity algorithms beyond the implementation docstrings in `analysis_rules.py`.
3. **Person Model Specification**: No specification defines the dynamic ontology of a person, physical attribute measurement standards, confidence calibration, or privacy classification.
4. **Conflict Resolution Rules**: No specification defines how to resolve contradictions between user self-reports, vision inferences, or conflicting multi-image scans.
5. **Freshness and Revalidation Policy**: No specification defines the validity lifetime (TTL), decay rate, or revalidation triggers for physical attributes (e.g. hair length changes, body weight shifts).
6. **Provisional Reasoning Algorithm**: No formal specification exists for how reasoning operates under incomplete data, beyond ad-hoc completeness checks (`completeness < 1.0`).

---

## 3. Requirement-by-Requirement Classification Matrix

### Primary Classification Key
- **A — IMPLEMENTED**: Fully implemented in code, schema, and UI, backed by test coverage.
- **B — PARTIALLY IMPLEMENTED**: Substantially implemented, but missing critical attributes, UI presentation, or end-to-end integration.
- **C — NOT IMPLEMENTED**: Absent in both backend and frontend.
- **D — IMPLEMENTED DIFFERENTLY**: Implemented using an alternative architecture or heuristic that diverges from the target specification.
- **E — NEEDS VERIFICATION**: Static inspection insufficient to establish runtime behavior.

---

### Requirement Catalog

#### R-S1-1: Real Appearance Observation and Attribute Identification
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Capabilities claiming appearance analysis use real observation models and clearly identify which attributes were measured.
- **Actual Implementation**: Hairstyle scan calls `VisionAppearanceAnalysisAdapter.analyze`, which measures only `face_shape` and explicitly sets `skin_tone`, `body_type`, and `style_type` to empty strings (`vision_appearance_adapter.py:229-236`). Outfit scan calls both appearance and garment adapters.
- **Exact Code Paths & Symbols**:
  - `backend/app/infrastructure/external/vision_appearance_adapter.py::VisionAppearanceAnalysisAdapter.analyze`
  - `backend/app/application/analysis.py::CreateHairstyleImageRun.__call__`
  - `newproject/flutter_application_1/lib/features/hairstyle/presentation/hairstyle_result_screen.dart:223-247`
- **Existing Test Evidence**:
  - `backend/tests/test_analysis_use_case.py::test_hairstyle_analysis_run_success`
  - `backend/tests/test_vision_appearance_adapter.py`
  - `newproject/flutter_application_1/test/hairstyle_result_screen_test.dart`
- **What Tests Verify**: Confirms adapter returns `face_shape`, run transitions to completed, and UI renders face shape.
- **Missing Behavior**: Real computer vision measurement of skin tone, body type, and style type; honest labels across all screens when attributes are omitted.
- **Dependencies & Affected User Journeys**: Affects Onboarding Photo Scan and Hairstyle Scan.
- **Confidence**: High.

#### R-S1-2: Outfit Scan Garment Observation
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: Outfit Scan must invoke garment analysis and surface detected clothing items.
- **Actual Implementation**: Implemented in commit `97f6ded` (Batch 2). `CreateOutfitRun` injects `GarmentAnalysisPort` and calls `self._garment_port.analyze(...)` in parallel with appearance analysis (`analysis.py:328-335`). `EphemeralOutfitAnalysis` also calls `self._garment_port.analyze(...)` (`analysis.py:1087-1094`). `outfit_analysis_screen.dart:826-919` renders `_buildGarmentDetails` when garment data is present.
- **Exact Code Paths & Symbols**:
  - `backend/app/application/analysis.py::CreateOutfitRun.__call__` (lines 328–340)
  - `backend/app/application/analysis.py::EphemeralOutfitAnalysis.__call__` (lines 1087–1094)
  - `newproject/flutter_application_1/lib/features/outfit_scan/presentation/outfit_analysis_screen.dart::_buildOutfitObservationsSection`
- **Existing Test Evidence**:
  - `backend/tests/test_analysis_use_case.py::test_outfit_run_invokes_both_ports`
  - `backend/tests/test_ephemeral_analysis.py::test_ephemeral_outfit_analysis_success`
  - `newproject/flutter_application_1/test/outfit_analysis_screen_test.dart`
- **What Tests Verify**: Confirms `CreateOutfitRun` and `EphemeralOutfitAnalysis` call garment analyzer, write garment snapshot, and Flutter renders garment details.
- **Missing Behavior**: Garment observations are not persisted into a durable person model; garment confidence is not surfaced as an independent score.
- **Dependencies & Affected User Journeys**: Outfit Scan and Initial Guest Scan.
- **Confidence**: High.

#### R-S1-3: Honest Handling of Unmeasured Appearance Fields
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Appearance fields not measured are hidden, labeled "Not measured", or removed.
- **Actual Implementation**: In `hairstyle_result_screen.dart:229-247`, empty `skinTone` and `styleDna` rows are hidden (`if (result.skinTone.trim().isNotEmpty)`). In `outfit_analysis_screen.dart:880-915`, missing garment data shows an honest unavailable note. However, `profile_screen.dart:358-382` falls back to `LocalStorage.userProfile` or mock values, masking absence.
- **Exact Code Paths & Symbols**:
  - `newproject/flutter_application_1/lib/features/hairstyle/presentation/hairstyle_result_screen.dart:229-247`
  - `newproject/flutter_application_1/lib/features/outfit_scan/presentation/outfit_analysis_screen.dart:880-915`
  - `newproject/flutter_application_1/lib/features/profile/presentation/profile_screen.dart:358-382`
- **Existing Test Evidence**:
  - `newproject/flutter_application_1/test/hairstyle_result_screen_test.dart`
  - `newproject/flutter_application_1/test/outfit_analysis_screen_test.dart`
- **What Tests Verify**: Verifies empty skin tone/style rows do not render on Hairstyle Result screen.
- **Missing Behavior**: Profile screen still displays unmeasured attributes using local mock defaults; no explicit "Not measured" badge across all profile surfaces.
- **Dependencies & Affected User Journeys**: Hairstyle Result, Outfit Analysis, User Profile.
- **Confidence**: High.

#### R-S2-1: Goal / Desired Change Model
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **C (NOT IMPLEMENTED)**
- **Expected Behavior**: Application captures user goals / desired change, or explicitly declares goals out of scope for Stage 1.
- **Actual Implementation**: No Goal entity, schema, database table, or profile field exists in the repository. In `PHASE_1_STEP2_OWNER_DECISIONS.md`, D5 (goals scope) is marked as PENDING founder decision.
- **Exact Code Paths & Symbols**:
  - `backend/app/infrastructure/db/models.py` (no goal table)
  - `docs/architecture/AI_DOMAIN_MODEL.md` (no goal entity)
- **Existing Test Evidence**: None (feature absent).
- **What Tests Verify**: N/A.
- **Missing Behavior**: Formal product decision on whether goals belong in Stage 1; if in scope, a persistent goal entity, repository, and recommendation conditioning.
- **Dependencies & Affected User Journeys**: Affects all recommendation journeys claiming goal orientation.
- **Confidence**: High.

#### R-S2-2: Mood and Occasion Request Scoping
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Per-request mood and occasion are treated as transient request context, never presented as durable personal goals.
- **Actual Implementation**: Backend treats mood as request-scoped context (`GenerateOutfitRequest.mood` in `schemas/outfits.py`). It is never persisted to `user_state.style_profile`. However, Outfit Builder UI includes marketing copy ("Applying Style DNA") that implies personal goal evaluation.
- **Exact Code Paths & Symbols**:
  - `backend/app/api/schemas/outfits.py::GenerateOutfitRequest`
  - `backend/app/application/outfits.py::GenerateOutfit.derive_with_reason`
  - `backend/app/domain/services/analysis_rules.py:1445-1478`
- **Existing Test Evidence**:
  - `backend/tests/test_c02_fit.py`
  - `backend/tests/test_outfits_api.py`
- **What Tests Verify**: Confirms mood enters candidate evaluation as context/explanation without modifying persistent user state.
- **Missing Behavior**: Removal of misleading UI copy in Outfit Builder that conflates per-request mood with persistent style goals.
- **Dependencies & Affected User Journeys**: Outfit Builder generation.
- **Confidence**: High.

#### R-S3-1: Preference and Style Identity Grounding
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Recommendations claiming personalization consume stored preferences and style identity.
- **Actual Implementation**: Outfit Builder consumes `preferred_occasions` and request-scoped `colorPalette` and `fit` (C-02). Discover For You consumes `preferred_occasions` and `saved_looks`. But Hairstyle image scan does NOT consume preferences or saved looks (`analysis.py:553`), and Outfit Builder does NOT read `style_profile`.
- **Exact Code Paths & Symbols**:
  - `backend/app/application/outfits.py:479-516`
  - `backend/app/domain/services/analysis_rules.py:1445-1478`
  - `backend/app/application/analysis.py:551-554`
- **Existing Test Evidence**:
  - `backend/tests/test_c02_palette.py`
  - `backend/tests/test_c02_fit.py`
  - `backend/tests/test_c03_preferred_item_ids.py`
- **What Tests Verify**: Asserts preference boosts (+5 palette, +5 fit, +5 preferred items) affect candidate scoring.
- **Missing Behavior**: Hairstyle image path does not consume preference signals; Outfit Builder does not read `style_profile`.
- **Dependencies & Affected User Journeys**: Outfit Builder, Hairstyle Scan.
- **Confidence**: High.

#### R-S3-2: Style Identity Grounding vs Fallbacks
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **C (NOT IMPLEMENTED)**
- **Expected Behavior**: Style identity is grounded in stored or declared values, never defaulted from absence.
- **Actual Implementation**: Vision adapter forces `style_type = ""` (`vision_appearance_adapter.py:235`). Flutter profile falls back to local storage or mock presets (`profile_screen.dart:372`). In `analysis_rules.py:168`, missing face shape in scoring helpers falls back to `"oval"`.
- **Exact Code Paths & Symbols**:
  - `backend/app/infrastructure/external/vision_appearance_adapter.py:235`
  - `backend/app/domain/services/analysis_rules.py:168`
  - `newproject/flutter_application_1/lib/features/profile/presentation/profile_screen.dart:372-375`
- **Existing Test Evidence**: None validating grounded style identity.
- **What Tests Verify**: N/A.
- **Missing Behavior**: Elimination of hidden `oval` fallback; authoritative declaration of style identity.
- **Dependencies & Affected User Journeys**: Hairstyle recommendations, Profile screen.
- **Confidence**: High.

#### R-S3-3: Consistent Feedback and Saved Look Learning Loop
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Saved looks and feedback events consistently influence future recommendations across all capabilities.
- **Actual Implementation**: Outfit Builder consumes saved looks (preferred items) and feedback events (likes +4.0/+2.0, dislikes -4.0/-2.0 via `build_feedback_context`). Discover For You applies a +0.03 boost for saved looks. However, Hairstyle image analysis does not consume saved looks or feedback. Look details screen lacks feedback controls (`look_details_screen.dart:17`).
- **Exact Code Paths & Symbols**:
  - `backend/app/application/outfits.py:503-516`
  - `backend/app/domain/services/analysis_rules.py:1231-1278`
  - `newproject/flutter_application_1/lib/features/saved_looks/presentation/saved_looks_screen.dart:332-333`
- **Existing Test Evidence**:
  - `backend/tests/test_p2s1_feedback_personalization.py`
  - `backend/tests/test_m11_feedback_api.py`
- **What Tests Verify**: Confirms like/dislike events shift candidate scores by expected deltas.
- **Missing Behavior**: Feedback consumption in Hairstyle/Grooming; feedback controls on initial generation and look details.
- **Dependencies & Affected User Journeys**: Saved Looks, Outfit Builder, Hairstyle Result.
- **Confidence**: High.

#### R-S4-1: Event Context Pass-Through and Labeling
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: When generating an outfit for an event, event context is passed to the backend or explicitly labeled display-only.
- **Actual Implementation**: Navigating from an event (`event_list_screen.dart:109-117`) passes `occasion` to `POST /v1/outfits/generate`. Event ID, title, date, and location are display-only in Flutter (`build_outfit_screen.dart:59-80`, `app_router.dart:269-304`) and are not sent to the backend.
- **Exact Code Paths & Symbols**:
  - `newproject/flutter_application_1/lib/features/events/presentation/event_list_screen.dart:109-117`
  - `newproject/flutter_application_1/lib/app/router/app_router.dart:269-304`
  - `backend/app/api/schemas/outfits.py::GenerateOutfitRequest`
- **Existing Test Evidence**:
  - `backend/tests/test_m8c_event_outfit_api.py`
  - `newproject/flutter_application_1/test/event_screens_test.dart`
- **What Tests Verify**: Verifies event route passes occasion into Outfit Builder.
- **Missing Behavior**: Passing event date/location to backend or labeling UI as occasion-only.
- **Dependencies & Affected User Journeys**: Events → Outfit Builder flow.
- **Confidence**: High.

#### R-S4-2: Weather and Constraint Absence Honesty
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: Weather, location, budget, and comfort are not implied unless a real provider exists.
- **Actual Implementation**: Fansivibe has no weather provider by design (`today.py:29-30` explicitly documents no weather integration). Today's Look UI has no weather card or weather claims. Budget and mobility constraints are not presented to users.
- **Exact Code Paths & Symbols**:
  - `backend/app/application/today.py:29-30`
  - `newproject/flutter_application_1/lib/features/home/presentation/home_screen.dart`
- **Existing Test Evidence**:
  - `backend/tests/test_m9_today_look_api.py`
  - `newproject/flutter_application_1/test/daily_outfit_screen_test.dart`
- **What Tests Verify**: Confirms Today's Look functions correctly without weather input.
- **Missing Behavior**: None (honest absence maintained).
- **Dependencies & Affected User Journeys**: Home / Today's Look.
- **Confidence**: High.

#### R-S4-3: Event Preference Consistency
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Event creation and recommendation context are consistent about what is remembered.
- **Actual Implementation**: In `events.py:114-129`, creating an event with an occasion adds that occasion to `user_state.preferences["preferred_occasions"]` (R36). Today's Look consumes the nearest event occasion (`today.py:160-171`). However, Outfit Builder does not disclose that preferences were modified by calendar events.
- **Exact Code Paths & Symbols**:
  - `backend/app/application/events.py:114-129`
  - `backend/app/application/today.py:160-171`
- **Existing Test Evidence**:
  - `backend/tests/test_m8a_events_foundation.py`
  - `backend/tests/test_m8b_events_api.py`
- **What Tests Verify**: Confirms event creation updates `preferred_occasions` in `user_state`.
- **Missing Behavior**: Explaining event-derived preference additions in recommendation explanations.
- **Dependencies & Affected User Journeys**: Event creation, Today's Look.
- **Confidence**: High.

#### R-S5-1: Provenance Preservation and Observation/Inference Separation
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Every result preserves provenance and distinguishes observation from inference.
- **Actual Implementation**: `analysis_runs` records `input_media` (SHA-256 hash), `knowledge_version`, `engine_version`, and `idempotency_key`. However, `user_state.style_profile` flattens all attributes under a single `source_run_id`, losing per-attribute provenance. The UI does not distinguish direct observations from catalog inferences.
- **Exact Code Paths & Symbols**:
  - `backend/app/application/analysis.py:250-287`
  - `backend/app/infrastructure/db/repositories.py:265-306`
- **Existing Test Evidence**:
  - `backend/tests/test_analysis_use_case.py`
  - `backend/tests/test_c09_style_profile_merge.py`
- **What Tests Verify**: Verifies `source_run_id` is updated on style profile merge.
- **Missing Behavior**: Field-level provenance in `style_profile`; UI distinction between observation and inference.
- **Dependencies & Affected User Journeys**: Analysis runs, Profile display.
- **Confidence**: High.

#### R-S5-2: Confidence Definition and Calibration
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **D (IMPLEMENTED DIFFERENTLY)**
- **Expected Behavior**: Confidence reflects calibrated model certainty.
- **Actual Implementation**: In `analysis_rules.py:378-393`, hairstyle confidence is computed as `0.5 * completeness + 0.5 * decisiveness` (completeness is fraction of 4 attributes present; decisiveness is score gap between top 2 picks). It is an evidence-completeness and ranking decisiveness heuristic, NOT a computer vision probability.
- **Exact Code Paths & Symbols**:
  - `backend/app/domain/services/analysis_rules.py:378-393`
  - `backend/app/domain/services/analysis_rules.py:226-243`
- **Existing Test Evidence**:
  - `backend/tests/test_analysis_rules.py:test_confidence_calculation`
- **What Tests Verify**: Confirms formula produces expected 0.0–1.0 float based on field count and score delta.
- **Missing Behavior**: User-facing disclosure that confidence represents evidence completeness rather than vision accuracy.
- **Dependencies & Affected User Journeys**: Hairstyle Scan, Outfit Scan.
- **Confidence**: High.

#### R-S5-3: Consistent Surfacing of Uncertainty Primitives
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: `needs_more_data`, `needs_review`, and confidence are surfaced consistently on all result surfaces.
- **Actual Implementation**: Backend emits `needs_more_data` in hairstyle results (`analysis_rules.py:461-462`) and `needs_review` in garment results (`value_objects.py:102-117`). In `outfit_analysis_screen.dart`, confidence is rendered for appearance. However, `hairstyle_mock_data.dart:128-148` drops `confidence` and `needs_more_data` during JSON parsing, so Hairstyle Result screen never surfaces them.
- **Exact Code Paths & Symbols**:
  - `backend/app/domain/services/analysis_rules.py:461-462`
  - `newproject/flutter_application_1/lib/features/hairstyle/data/hairstyle_mock_data.dart:128-148`
  - `newproject/flutter_application_1/lib/features/outfit_scan/presentation/outfit_analysis_screen.dart:404-431`
- **Existing Test Evidence**:
  - `backend/tests/test_garment_analysis.py`
  - `newproject/flutter_application_1/test/hairstyle_result_screen_test.dart`
- **What Tests Verify**: Confirms backend returns `needs_more_data` and Flutter deserializes result.
- **Missing Behavior**: Parsing and surfacing `confidence` and `needs_more_data` in Flutter Hairstyle Result.
- **Dependencies & Affected User Journeys**: Hairstyle Result Screen.
- **Confidence**: High.

#### R-S6-1: Shared Person Model Authority and Read/Write Path
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Shared person model has one declared authority for each field and a documented read/write path.
- **Actual Implementation**: Backend `user_state.style_profile` is the intended server authority and is exposed via `GET /v1/users/me` (`ProfileView.styleProfile`). However, Flutter `ProfileScreen` reads local storage (`LocalStorage.userProfile`) and `LearningService.instance.face`, never calling `GET /v1/users/me`. Two parallel authorities exist.
- **Exact Code Paths & Symbols**:
  - `backend/app/api/routers/users.py:96-109`
  - `newproject/flutter_application_1/lib/features/profile/presentation/profile_screen.dart:358-375`
- **Existing Test Evidence**:
  - `backend/tests/test_get_profile.py`
  - `newproject/flutter_application_1/test/profile_screen_test.dart`
- **What Tests Verify**: Confirms backend returns profile view with style profile, and Flutter renders local values.
- **Missing Behavior**: Flutter profile screen hydration from `GET /v1/users/me`.
- **Dependencies & Affected User Journeys**: Profile Screen, Onboarding.
- **Confidence**: High.

#### R-S6-2: Non-Erasure in Partial Updates
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: Updating one attribute does not erase previously stored attributes.
- **Actual Implementation**: `UserStateRepositorySQL.update_style_profile` in `repositories.py:265-306` uses PostgreSQL JSONB concatenation (`coalesce(style_profile, '{}'::jsonb) || cast(patch, JSONB)`). Only non-empty strings are included in the patch dict. Empty strings and nulls are filtered out. Existing keys survive.
- **Exact Code Paths & Symbols**:
  - `backend/app/infrastructure/db/repositories.py::UserStateRepositorySQL.update_style_profile`
- **Existing Test Evidence**:
  - `backend/tests/test_c09_style_profile_merge.py::test_a_existing_non_empty_fields_survive_incoming_empty_strings`
  - `backend/tests/test_c09_style_profile_merge.py::test_c_existing_unrelated_jsonb_keys_survive`
- **What Tests Verify**: Verifies SQL emission and roundtrip merge preserving existing attributes.
- **Missing Behavior**: None (merge semantics verified).
- **Dependencies & Affected User Journeys**: Style profile updates from analysis runs.
- **Confidence**: High.

#### R-S6-3: Explicit Guest-to-Authenticated Migration Scope
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Guest migration preserves or explicitly drops each data class with clear user disclosure.
- **Actual Implementation**: `GuestDataMigration` in `guest_data_migration.dart:47-57` migrates wardrobe items and preferred occasions. It explicitly excludes face profile, learning signals, saved-look titles, style type, and analysis blobs. However, the UI does not explicitly disclose to the user that their face scan / preview will not migrate.
- **Exact Code Paths & Symbols**:
  - `newproject/flutter_application_1/lib/features/auth/data/guest_data_migration.dart:44-78`
  - `newproject/flutter_application_1/lib/features/auth/presentation/post_auth_flow.dart:140-181`
- **Existing Test Evidence**:
  - `newproject/flutter_application_1/test/guest_auth_conversion_test.dart`
- **What Tests Verify**: Verifies wardrobe and preferred occasions upload to server, while non-transferable data stays local.
- **Missing Behavior**: User-facing disclosure of excluded data classes during guest sign-in.
- **Dependencies & Affected User Journeys**: Post-authentication onboarding flow.
- **Confidence**: High.

#### R-S6-4: Provenance and Versioning for Recommendation Shifts
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Model exposes provenance and versioning to explain why recommendations change.
- **Actual Implementation**: `analysis_runs` stores history and timestamps. `user_state` has a `version` column and `updated_at`. `SavedLook` records `source_run_id`. But `user_state.style_profile` does not track historical attribute changes or reasons for updates. Recommendations cannot be diffed against prior person-model versions.
- **Exact Code Paths & Symbols**:
  - `backend/app/infrastructure/db/models.py:118-132`
  - `backend/app/infrastructure/db/repositories.py:265-306`
- **Existing Test Evidence**:
  - `backend/tests/test_analysis_use_case.py`
- **What Tests Verify**: Confirms `source_run_id` is recorded on analysis runs and saved looks.
- **Missing Behavior**: Attribute-level change history; incrementing `user_state.version` on profile updates.
- **Dependencies & Affected User Journeys**: User profile, recommendations.
- **Confidence**: High.

#### R-S6-5: Account Deletion and Privacy Alignment
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Account deletion removes user data in compliance with privacy claims, with in-app UI access.
- **Actual Implementation**: Backend implements `DELETE /v1/users/me` with full foreign-key cascade (`DeleteAccount` in `backend/app/application/auth.py:228-246`). However, Flutter has no account deletion button in settings/profile. Camera permission copy states photos are not stored, which is true for raw bytes, but derived attributes are persisted.
- **Exact Code Paths & Symbols**:
  - `backend/app/api/routers/users.py:130-151`
  - `backend/app/application/auth.py:228-246`
  - `newproject/flutter_application_1/lib/features/profile/presentation/profile_screen.dart`
- **Existing Test Evidence**:
  - `backend/tests/test_account_erasure.py`
  - `backend/tests/test_delete_account_unit.py`
- **What Tests Verify**: Verifies database cascade deletion across user rows and foreign keys.
- **Missing Behavior**: Flutter in-app Delete Account UI; privacy copy clarifying raw images vs derived features.
- **Dependencies & Affected User Journeys**: Profile/Settings, Account Management.
- **Confidence**: High.

#### R-X-1: Truthful Progress Labels and Pipeline Claims
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Progress indicators and labels only describe actual pipeline stages that execute.
- **Actual Implementation**: In Batch 1 (`STAGE1-BATCH-1`), false progress copy "Analyzing skin tone" and "Applying Style DNA" was corrected in hairstyle processing copy, Outfit Builder processing label was fixed, and post-auth copy was refined. However, Outfit Builder progress still references style DNA stages in some mock files (`outfit_builder_mock_data.dart:139-142`).
- **Exact Code Paths & Symbols**:
  - `newproject/flutter_application_1/lib/features/hairstyle/data/hairstyle_mock_data.dart:39-61`
  - `newproject/flutter_application_1/lib/features/outfit_builder/data/outfit_builder_mock_data.dart:139-142`
- **Existing Test Evidence**:
  - `newproject/flutter_application_1/test/hairstyle_processing_screen_test.dart`
- **What Tests Verify**: Confirms processing stages match corrected copy.
- **Missing Behavior**: Complete elimination of mock pipeline stages across all capabilities.
- **Dependencies & Affected User Journeys**: Outfit Builder generation, Hairstyle processing.
- **Confidence**: High.

#### R-X-2: Capability-Specific Observation Isolation
- **Source**: `FANSIVIBE_STAGE1_TRACEABILITY_MATRIX.md` §3.3
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: Capability-specific observations do not silently become shared person facts without a declared contract.
- **Actual Implementation**: Outfit Scan writes `face_shape` to `user_state.style_profile` (`analysis.py:391-398`). Garment observations are not written to `style_profile`. Hairstyle writes `face_shape`. But there is no declared projection schema or validation separating capability-local observations from global person truths.
- **Exact Code Paths & Symbols**:
  - `backend/app/application/analysis.py:387-399`
  - `backend/app/infrastructure/db/repositories.py:265-306`
- **Existing Test Evidence**:
  - `backend/tests/test_analysis_use_case.py`
- **What Tests Verify**: Confirms style profile update execution.
- **Missing Behavior**: Formal projection contract specifying which capabilities have authority to update which person model attributes.
- **Dependencies & Affected User Journeys**: Outfit Scan, Hairstyle Scan.
- **Confidence**: High.

---

### Phase 1 AI Stylist Contracts (C-01 through C-10)

#### C-01: Guest / Authenticated Identity Architecture
- **Source**: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` §Contract C-01
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: Guests browse local wardrobe and feeds; server AI surfaces gated; point-of-action sign-in prompts; pending auth intent recorded; zero 401s on initial load.
- **Actual Implementation**: Fully implemented and locked. Unauthenticated users access local wardrobe, discover feeds, and ephemeral analysis previews. Server AI endpoints (`/outfits/generate`, durable `/analysis/*`, `/looks/saved`) require JWT token. Point-of-action prompts route to sign-in (`promptGuestSignIn`). `PendingAuthIntent` records route and action.
- **Exact Code Paths & Symbols**:
  - `newproject/flutter_application_1/lib/shared/utils/guest_mode.dart:21-64`
  - `backend/app/api/deps.py::get_current_user_id`
- **Existing Test Evidence**:
  - `newproject/flutter_application_1/test/guest_preview_test.dart`
  - `newproject/flutter_application_1/test/guest_auth_conversion_test.dart`
  - `newproject/flutter_application_1/test/guest_phase2_test.dart`
- **What Tests Verify**: Confirms guest mode blocks server writes, triggers sign-in prompt, and preserves pending intent.
- **Missing Behavior**: None for Phase 1 contract scope.
- **Dependencies & Affected User Journeys**: Entire guest onboarding and browsing journey.
- **Confidence**: High.

#### C-02: Mood / Fit / Color Palette
- **Source**: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` §Contract C-02 & `PHASE_1_STEP2_OWNER_DECISIONS.md`
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: Palette provides deterministic +5 soft signal; Fit provides deterministic +5 soft signal when `fit_confidence >= 0.6`; Mood is context/explanation-only. Compatibility budget rebalanced to 70.
- **Actual Implementation**: Fully implemented. Palette provides +5 soft bonus based on color harmony (`C-02-P`). Fit provides +5 soft bonus when `fit_confidence >= 0.6` (`C-02-F`), with `fit` and `fit_confidence` persisted on `wardrobe_items` (migration `0023`). Mood is context/explanation-only (`C-02-M`). Full score formula clamped in [0, 100].
- **Exact Code Paths & Symbols**:
  - `backend/app/domain/services/analysis_rules.py:1445-1478`
  - `backend/alembic/versions/0023_wardrobe_fit_columns.py`
  - `backend/app/infrastructure/db/models.py::WardrobeItems`
- **Existing Test Evidence**:
  - `backend/tests/test_c02_palette.py`
  - `backend/tests/test_c02_fit.py`
- **What Tests Verify**: Confirms palette +5 bonus, fit +5 bonus with >=0.6 confidence gating, and mood neutrality.
- **Missing Behavior**: None for C-02 locked scope.
- **Dependencies & Affected User Journeys**: Outfit Builder generation.
- **Confidence**: High.

#### C-03: Preferred Item IDs Recommendation Influence
- **Source**: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` §Contract C-03 & `PHASE_1_STEP2_OWNER_DECISIONS.md`
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: Explicit user-selected wardrobe item UUIDs sent in `POST /v1/outfits/generate` provide a +5/cap-15 soft score boost.
- **Actual Implementation**: Implemented in `schemas/outfits.py:GenerateOutfitRequest` (`preferredItemIds: Optional[list[UUID]] = None`), `application/outfits.py:GenerateOutfit.derive_with_reason`, and `analysis_rules.py:score_outfit_candidate`.
- **Exact Code Paths & Symbols**:
  - `backend/app/api/schemas/outfits.py:27`
  - `backend/app/application/outfits.py:392`
  - `backend/app/domain/services/analysis_rules.py:1145-1170`
- **Existing Test Evidence**:
  - `backend/tests/test_c03_preferred_item_ids.py`
- **What Tests Verify**: Confirms explicit item IDs provide +5 per item (capped at +15), while unknown/foreign IDs degrade safely to 0 without 404.
- **Missing Behavior**: None for C-03 scope.
- **Dependencies & Affected User Journeys**: Outfit Builder with preferred items.
- **Confidence**: High.

#### C-04: Scan → Generate ("Build with this item")
- **Source**: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` §Contract C-04 & `PHASE_1_STEP2_OWNER_DECISIONS.md`
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: After saving a scanned garment to wardrobe, user can tap "Build with this item" to launch Outfit Builder with that item preselected.
- **Actual Implementation**: Implemented in Flutter: saving a garment returns a wardrobe item UUID, which is passed as `preferredItemId` route extra to Outfit Builder (`outfit_generation_screen.dart`), which then passes it in `preferredItemIds` to `POST /v1/outfits/generate`.
- **Exact Code Paths & Symbols**:
  - `newproject/flutter_application_1/lib/features/wardrobe/presentation/add_wardrobe_item_screen.dart:450-480`
  - `newproject/flutter_application_1/lib/features/outfit_builder/presentation/outfit_generation_screen.dart:74-89`
- **Existing Test Evidence**:
  - `newproject/flutter_application_1/test/outfit_builder_screens_test.dart`
  - `newproject/flutter_application_1/test/wardrobe_garment_flow_test.dart`
- **What Tests Verify**: Confirms "Build with this item" routes to generation screen with preselected wardrobe ID.
- **Missing Behavior**: Ephemeral/unsaved scan-to-generate was explicitly excluded from Option A.
- **Dependencies & Affected User Journeys**: Garment Scan → Wardrobe → Outfit Builder.
- **Confidence**: High.

#### C-05: Feedback Semantics (Save, Like, Dislike, Wear)
- **Source**: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` §Contract C-05 & `PHASE_1_STEP2_OWNER_DECISIONS.md`
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: Save provides discovery boost; Like provides +4.0/+2.0 positive evidence; Dislike provides -4.0/-2.0 negative evidence; Wear provides +2.0/+1.0 behavioral evidence.
- **Actual Implementation**: Implemented in `analysis_rules.py:candidate_feedback_points` and `candidate_wear_points` reading `build_feedback_context` from `feedback_events` and `wardrobe_wear_groups`. Bounded net feedback range [-6.0, +6.0].
- **Exact Code Paths & Symbols**:
  - `backend/app/domain/services/analysis_rules.py:1362-1443`
  - `backend/app/application/outfits.py:503-516`
- **Existing Test Evidence**:
  - `backend/tests/test_p2s1_feedback_personalization.py`
  - `backend/tests/test_m11_feedback_api.py`
- **What Tests Verify**: Confirms like/dislike/wear shift candidate scores within approved bounds.
- **Missing Behavior**: Skip event definition deferred; feedback consumption in Hairstyle/Grooming deferred.
- **Dependencies & Affected User Journeys**: Saved looks reactions, Outfit Builder generation.
- **Confidence**: High.

#### C-06: Garment AI Attributes Persistence and Scoring
- **Source**: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` §Contract C-06 & `PHASE_1_STEP2_OWNER_DECISIONS.md`
- **Primary Status**: **B (PARTIALLY IMPLEMENTED)**
- **Expected Behavior**: 7 vision attributes (category, color, material, pattern, style, fit, confidence) captured; category/color/material/fit scored; pattern/style preserved in sidecar.
- **Actual Implementation**: Migration `0023` added `fit` and `fit_confidence` columns to `wardrobe_items`. Category, color, material, and fit are scored. Pattern and style are preserved in `image_ref` JSONB sidecar. However, owner decision on formal scoring weights for pattern and style remains PENDING (D-06).
- **Exact Code Paths & Symbols**:
  - `backend/alembic/versions/0023_wardrobe_fit_columns.py`
  - `backend/app/infrastructure/db/models.py:410-430`
  - `backend/app/application/wardrobe.py:140-180`
- **Existing Test Evidence**:
  - `backend/tests/test_c02_fit.py`
  - `backend/tests/test_garment_analysis.py`
- **What Tests Verify**: Verifies fit and fit_confidence persist in DB and influence scoring when confidence >= 0.6.
- **Missing Behavior**: Final owner decision and scoring implementation for pattern and style attributes.
- **Dependencies & Affected User Journeys**: Garment Scan, Wardrobe Item creation.
- **Confidence**: High.

#### C-07: item_added Learning Signal Emission
- **Source**: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` §Contract C-07 & `PHASE_1_STEP2_OWNER_DECISIONS.md`
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: When a wardrobe item is added, an `item_added` signal is emitted to `learning_signals`.
- **Actual Implementation**: Migration `0024_item_added_signal_type.py` seeded `'item_added'` into `signal_types`. `AddWardrobeItem` use case in `backend/app/application/wardrobe.py:127-145` emits `item_added` via `learning_signal.insert_look_saved` post-commit.
- **Exact Code Paths & Symbols**:
  - `backend/alembic/versions/0024_item_added_signal_type.py`
  - `backend/app/application/wardrobe.py:127-145`
  - `backend/app/infrastructure/db/repositories.py:2700-2720`
- **Existing Test Evidence**:
  - `backend/tests/test_c07_item_added.py::test_item_added_emitted_on_wardrobe_creation`
- **What Tests Verify**: Confirms migration seeded signal type and use case inserts `item_added` row.
- **Missing Behavior**: None (migration and writer verified).
- **Dependencies & Affected User Journeys**: Wardrobe item creation.
- **Confidence**: High.

#### C-08: analysisCached / analysisResult Storage Integrity
- **Source**: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` §Contract C-08 & `PHASE_1_STEP2_OWNER_DECISIONS.md`
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: `analysisCached` reflects local photo-captured milestone; non-authoritative local blob setter deprecated; dead setters removed.
- **Actual Implementation**: Implemented in Step 1 and locked. `LocalStorage.analysisResult` setter marked `@Deprecated`. `analysisCached` semantics clarified as photo-captured flag. In STAGE1-BATCH-3.1, `hasCachedOutfitPreview()` was added so cache reporting requires a renderable outfit snapshot.
- **Exact Code Paths & Symbols**:
  - `newproject/flutter_application_1/lib/shared/utils/local_storage.dart:86-98`
  - `newproject/flutter_application_1/lib/shared/utils/guest_mode.dart:220-228`
- **Existing Test Evidence**:
  - `newproject/flutter_application_1/test/c08_onboarding_photo_captured_test.dart`
  - `newproject/flutter_application_1/test/guest_preview_test.dart`
- **What Tests Verify**: Confirms `analysisCached` requires renderable preview, and deprecated setters do not cause warnings.
- **Missing Behavior**: None for C-08 scope.
- **Dependencies & Affected User Journeys**: Onboarding photo capture and guest preview.
- **Confidence**: High.

#### C-09: Style Profile Merging Semantics
- **Source**: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` §Contract C-09 & `PHASE_1_STEP2_OWNER_DECISIONS.md`
- **Primary Status**: **D (IMPLEMENTED DIFFERENTLY)**
- **Expected Behavior**: Owner decision was PENDING between REPLACE, MERGE, CAS/versioning, or MERGE + CAS.
- **Actual Implementation**: Implemented as MERGE via PostgreSQL `||` operator in `UserStateRepositorySQL.update_style_profile` (`repositories.py:265-306`). Non-empty strings replace old values; empty strings do not erase. However, this was implemented WITHOUT versioning or CAS (`user_state.version` is not checked or incremented), meaning concurrent updates can overwrite without conflict detection, and owner disposition remains formally PENDING in `PHASE_1_STEP2_OWNER_DECISIONS.md`.
- **Exact Code Paths & Symbols**:
  - `backend/app/infrastructure/db/repositories.py::UserStateRepositorySQL.update_style_profile`
  - `backend/app/application/analysis.py:391-398`
  - `backend/app/application/analysis.py:585-592`
- **Existing Test Evidence**:
  - `backend/tests/test_c09_style_profile_merge.py` (10 tests passing)
- **What Tests Verify**: Verifies JSONB merge SQL emission, non-empty attribute preservation, and `source_run_id` update.
- **Missing Behavior**: Owner decision formal resolution; compare-and-swap (CAS) concurrency control; per-attribute provenance.
- **Dependencies & Affected User Journeys**: Style profile updates from analysis runs.
- **Confidence**: High.

#### C-10: Analysis Idempotency
- **Source**: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md` §Contract C-10 & `PHASE_1_STEP2_OWNER_DECISIONS.md`
- **Primary Status**: **A (IMPLEMENTED)**
- **Expected Behavior**: Analysis endpoints accept `Idempotency-Key` header; replaying same key with identical payload returns existing run; conflicting payload raises 409 Conflict.
- **Actual Implementation**: Fully implemented in Option B. Migration `0025_analysis_runs_idempotency.py` added `idempotency_key` column and unique constraint `uq_analysis_runs_idempotency` on `(user_id, idempotency_key)`. All 4 analysis use cases (`CreateOutfitRun`, `CreateHairstyleImageRun`, `CreateGroomingImageRun`, `CreateGarmentRun`) accept idempotency key, query `get_by_idempotency`, and handle replays/conflicts. Flutter clients generate and transmit `Idempotency-Key: UUIDv4`.
- **Exact Code Paths & Symbols**:
  - `backend/alembic/versions/0025_analysis_runs_idempotency.py`
  - `backend/app/application/analysis.py:264-302`
  - `backend/app/api/routers/analysis.py`
- **Existing Test Evidence**:
  - `backend/tests/test_c10_analysis_idempotency.py`
  - `newproject/flutter_application_1/test/c10_analysis_idempotency_test.dart`
- **What Tests Verify**: Confirms replayed keys return existing run without re-running vision adapters; payload mismatches return 409 Conflict.
- **Missing Behavior**: None (fully implemented and verified).
- **Dependencies & Affected User Journeys**: All 4 analysis submit flows.
- **Confidence**: High.

---

### Reconciliation & Status Totals

| Status Code | Status Meaning | Count (R-Requirements) | Count (C-Contracts) | Total Count | Percentage |
|---|---|---|---|---|---|
| **A** | IMPLEMENTED | 3 | 8 | **11** | 35.5% |
| **B** | PARTIALLY IMPLEMENTED | 15 | 1 | **16** | 51.6% |
| **C** | NOT IMPLEMENTED | 2 | 0 | **2** | 6.5% |
| **D** | IMPLEMENTED DIFFERENTLY | 1 | 1 | **2** | 6.5% |
| **E** | NEEDS VERIFICATION | 0 | 0 | **0** | 0.0% |
| **TOTAL** | | **21** | **10** | **31** | **100.0%** |

---

## 4. Answers to the 14 Critical Architectural Questions

### 1. Does Fansivibe have a real person model or only a conventional user profile?
**Answer: Fansivibe has a conventional user profile with a flexible JSONB column (`user_state.style_profile`), NOT a comprehensive or principled person model.**  
*Evidence:* In `backend/app/infrastructure/db/models.py:118-132`, user state is represented by `user_state` with JSONB columns `style_profile`, `preferences`, and `flags`. The `style_profile` stores at most 5 keys: `face_shape`, `skin_tone`, `body_type`, `style_type`, and `source_run_id`. There is no dedicated Person entity, no observation ledger, no attribute confidence/confirmation status, and no revalidation lifecycle. In Flutter (`profile_screen.dart:358-375`), the profile reads device-local storage and `LearningService`, ignoring the backend schema.

### 2. Where are physical attributes, style preferences and restrictions stored?
**Answer: Physical attributes reside in `user_state.style_profile` JSONB (backend) and `LocalStorage.userProfile` (Flutter); preferences reside in `user_state.preferences` JSONB; restrictions are NOT stored anywhere.**  
*Evidence:*
- Physical attributes: Stored in `user_state.style_profile` (`face_shape`, `skin_tone`, `body_type`, `style_type`). In practice, only `face_shape` is populated; others are forced empty (`vision_appearance_adapter.py:235`).
- Style preferences: Stored in `user_state.preferences["preferred_occasions"]`. Request-scoped preferences (mood, fit, palette) are sent as transient DTOs (`GenerateOutfitRequest` in `schemas/outfits.py`).
- Restrictions: Zero tables or columns exist for dietary, physical, modesty, fabric/allergy, or budget restrictions.

### 3. Does the application maintain persistent knowledge about a person?
**Answer: Yes, but persistence is fragmented across independent silos, and guest knowledge is lost upon sign-in.**  
*Evidence:* Authenticated users have persistent server-side records across `user_state` (appearance & preferred occasions), `wardrobe_items` (garments, fit, wear dates), `saved_looks` (favorite looks), `user_events` (calendar), `analysis_runs` (run history), `feedback_events` (likes/dislikes), and `wardrobe_wear_groups` (wear history). However, guest onboarding analysis is never persisted server-side, and `GuestDataMigration` explicitly excludes face/appearance data from migration.

### 4. Does it preserve provenance and distinguish explicit facts from inferences?
**Answer: Provenance is preserved at the analysis run level, but NOT at the person-attribute level; explicit facts and inferences are conflated.**  
*Evidence:* `analysis_runs` preserves input image hash, engine version, and knowledge version. However, `user_state.style_profile` contains a single `source_run_id` for the entire object. A subsequent partial update overwrites `source_run_id`, destroying provenance for surviving fields. Within `style_profile`, there is no flag indicating whether an attribute was explicitly chosen by the user or inferred by an AI vision adapter.

### 5. Can information from different sessions be combined safely?
**Answer: No. Field merging prevents data erasure, but lack of concurrency control creates a last-writer-wins race condition.**  
*Evidence:* `UserStateRepositorySQL.update_style_profile` (`repositories.py:265-306`) merges non-empty attributes using PostgreSQL `||`, ensuring that a face-only scan does not erase existing body or skin tone data. However, there is no compare-and-swap (CAS) check. Although `user_state.version` exists in the schema (`models.py:130`), `update_style_profile` does not check or increment it. Concurrent analysis runs execute blind overwrites.

### 6. Is conflict resolution implemented?
**Answer: No. Conflict resolution is entirely unhandled; the latest non-empty string silently overwrites previous data.**  
*Evidence:* In `test_c09_style_profile_merge.py::test_b_incoming_non_empty_field_replaces_old_value`, when a new run produces `face_shape="oval"`, it unconditionally overwrites `face_shape="round"`. There is no confidence comparison, recency decay, user confirmation prompt, or multi-observation consensus algorithm.

### 7. Is attribute freshness tracked?
**Answer: No. Person attributes have no freshness timestamps, TTLs, or decay tracking.**  
*Evidence:* `user_state.updated_at` records the timestamp of the row's latest write, but individual attributes in `style_profile` have no independent timestamps. Once a face shape is written, it remains permanently valid with no indication of age.

### 8. Can outdated information trigger revalidation?
**Answer: No. There is no revalidation policy, background worker, or trigger for stale data.**  
*Evidence:* Code inspection of `backend/app/application/` and scheduled jobs reveals zero revalidation logic for user attributes. A face shape captured years ago is treated with identical authority to one captured today.

### 9. Is fashion knowledge separated from recommendation logic?
**Answer: Substantially separated in the primary domain engine, but compromised by hardcoded bypasses in the AI assistant tools.**  
*Evidence:*
- Primary engine: `CatalogKnowledgeSource` (`infrastructure/external/knowledge.py`) implements `KnowledgeSource` port (`domain/ports/external.py`), serving curated styles from `backend/app/data/catalog.py`. `analysis_rules.py` implements pure domain scoring and ranking.
- Architecture bypass: `backend/app/ai/tools.py` hardcodes recommendation rules directly against catalog constants (`catalog.CASUAL_LOOK`, `catalog.REFINED_OFFICE`, `catalog.OCCASION_TO_LOOK`), completely bypassing the decision engine pipeline.

### 10. Are recommendations filtered and ranked deterministically?
**Answer: Yes. The recommendation engine enforces strict deterministic filtering and multi-stage tie-breaking.**  
*Evidence:* In `backend/app/domain/services/analysis_rules.py`:
- `rank_outfit_candidates` sorts deterministically by:
  1. Score descending (`-c.score`)
  2. Number of selected items descending (`-len(candidate_item_ids(c))`)
  3. Canonical selected item IDs ascending (lexical tie-break: `candidate_item_ids(c)`)
- `select_best_outfit_candidate` selects `ranked[0]`.
- Scoring weights in `compose_candidate_score` clamp all terms to deterministic bounds. Randomness or timestamp ordering is forbidden.

### 11. Can reasoning handle incomplete information?
**Answer: Partially and honestly in primary analysis, but degrades to hardcoded defaults in helper tools.**  
*Evidence:*
- Primary analysis: When face shape is missing, `CreateHairstyleImageRun` fails honestly with `AppearanceAnalysisError("no_face_detected")`. When garment analysis fails, `CreateOutfitRun` records a typed `garment_error` and returns partial results.
- Bypasses: In `analysis_rules.py:168` and `backend/app/ai/tools.py:36`, missing face shape silently falls back to `"oval"`. In Flutter, `hairstyle_mock_data.dart` drops `needs_more_data` and `confidence`.

### 12. Does feedback influence future recommendations?
**Answer: Yes for Outfit Builder; No for Hairstyle Scan and AI Assistant.**  
*Evidence:*
- Outfit Builder: `build_feedback_context` reads `feedback_events` (likes and dislikes on saved looks) and `wardrobe_wear_groups`. `candidate_feedback_points` awards +4.0/+2.0 for liked items and -4.0/-2.0 for disliked items; `candidate_wear_points` awards +2.0/+1.0 for worn items.
- Hairstyle: Hairstyle recommendations do NOT consume feedback.
- `learning_signals`: The `learning_signals` table stores event rows (`look_saved`, `analysis_updated`, `outfit_selected`, `item_added`), but is write-only and never read by recommendation algorithms.

### 13. Does one shared person model serve hairstyle, outfit and wardrobe decisions?
**Answer: No. Decisions are served from fragmented, capability-specific data silos.**  
*Evidence:*
- Hairstyle recommendations read `AppearanceProfile.faceShape`.
- Outfit recommendations read `wardrobe_items`, `preferences["preferred_occasions"]`, and feedback context, completely ignoring `style_profile`.
- Today's Look reads nearest event occasion and wardrobe, parsing a separate `styleDna` projection.
- Flutter Profile reads local storage and `LearningService`, ignoring the backend profile.

### 14. Are guest and authenticated user flows handled consistently?
**Answer: No. Guest flows are local-first with ephemeral server processing; authenticated flows are database-backed; conversion discards appearance data.**  
*Evidence:* Guest onboarding uses `POST /v1/analysis/outfit/ephemeral` and stashes snapshots in Flutter device memory. "Save My Progress" only records a `PendingAuthIntent` with route `/home`; it does not post or persist the analysis. When the guest signs in, `GuestDataMigration` migrates wardrobe items and preferred occasions, but explicitly discards the face profile, style type, and analysis preview.

---

## 5. Scope and Audit Limitations

1. **Static Inspection Only**: This audit is based entirely on static source code, schemas, and test file analysis at baseline `97f6ded`. No tests were executed, and no live database or network connections were established.
2. **AI Provider Quality**: This audit evaluates code contracts, routing, and data structures; it does not evaluate the visual accuracy of Ollama vision models or LLM prompt generation quality.
3. **Environment & Runtime Configurations**: Adapter selection in production environments depends on runtime configuration (`Settings`); static inspection verifies default code paths and structural implementations.

---
*End of Stage 1 Specification-to-Code Audit.*
