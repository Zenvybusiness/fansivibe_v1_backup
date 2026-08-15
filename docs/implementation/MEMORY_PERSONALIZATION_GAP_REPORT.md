# MEMORY + PERSONALIZATION GAP REPORT

## Overview

This report documents all gaps identified during the STEP 11 audit, classified by severity (P0/P1/P2/P3), with recommended implementation order, required changes, and risk assessments.

The current system is classified as **LEVEL 1 — UNDERSTOOD** (verified appearance information only), with personalization not yet flowing from memory to recommendations. The progression target is LEVEL 4 — PERSONALIZED, where recommendations use multiple reliable user signals.

---

## P0 — Gaps That Block Meaningful Personalization

### G-P0-1: Learning Signals Emitted but Not Consumed

| Field | Details |
|---|---|
| **Current Behavior** | `look_saved` and `analysis_updated` signals are stored in `learning_signals` table and `UserModel.signals` but the decision engine's 7-stage pipeline completely ignores them. Scoring only uses appearance + `preferredLookIds` from preferences. |
| **Desired Behavior** | Decision engine stages 3-4 consume signal history: preference boost from saved look history, behavior-based scoring that recognizes user interaction patterns. |
| **Source/File** | `backend/app/domain/services/analysis_rules.py:score_candidates()` and `learning_signal` repository |
| **Backend Impact** | Modify `score_candidates` to add bonus if look ID appears in user's saved look history (from `saved_looks` table joined with `learning_signals`). Add new signal type consumption path. |
| **Database Impact** | None directly; existing `learning_signals` table already has required columns. May add index on `signal_type, user_id, occurred_at` for signal history queries. |
| **API Impact** | None — signals already stored; no new endpoints needed for P0. |
| **UI/UX Impact** | None directly; memory summary (P0-G-P0-3) will surface that signals are being consumed. |
| **Tests Required** | Unit test: `score_candidates` with saved look history boost produces different scores than without. Integration test: save look → verify recommendation score changes. |
| **Risk** | LOW. Backward compatible: if no saved looks, behavior is identical to current. Only adds boost when signal history exists. |

### G-P0-2: Preferences Not Persisted Across Sessions

| Field | Details |
|---|---|
| **Current Behavior** | Preferences screen stores selections in UI state only; on app restart or navigation away, preferences are lost. `UserModel.preferredOccasions` may be empty on first launch. |
| **Desired Behavior** | Preferences persisted to `user_state.preferences` JSONB (backend) and `UserModel.preferredOccasions` (frontend LocalStore); restored on app startup from last known state. |
| **Source/File** | `features/profile/presentation/preferences_screen.dart`, `learning_service.dart`, `local_store.dart` |
| **Backend Impact** | Extend `user_state.preferences` write path in application use cases; ensure `GET /v1/users/me` returns `preferred_occasions` in saved state. |
| **Database Impact** | None — `user_state.preferences` JSONB column already exists. Data migration not required (new data written to existing column). |
| **API Impact** | `GET /v1/users/me` already returns `preferences` map; ensure `preferred_occasions` key is present and populated. |
| **UI/UX Impact** | Preferences screen changes now survive app restart; user sees persisted selections on return. |
| **Tests Required** | Widget test: update preference, quit app, restart, verify preference persists. Unit test: LocalStore round-trip of UserModel with preferences. |
| **Risk** | LOW. Existing preferences data structure unchanged; only adds persistence pathway. |

### G-P0-3: No "What Fansivibe Knows" User-Facing Summary

| Field | Details |
|---|---|
| **Current Behavior** | Users cannot view what the system has learned about them. No memory summary anywhere in the app. |
| **Desired Behavior** | Profile screen includes "Memory" section showing: verified appearance (with AI-inferred labeling), saved looks count, preferred occasions (with source labeling), and behavior patterns. |
| **Source/File** | `features/profile/presentation/profile_screen.dart`, `features/profile/presentation/widgets/profile_widgets.dart` |
| **Backend Impact** | Extend `GET /v1/users/me` response with `memorySummary` field, or add new endpoint `GET /v1/users/memory`. Field contains: `appearanceVerified` (bool), `savedLooksCount` (int), `preferredOccasions` (List<String>), `appearanceConfidence` (float 0-1). |
| **Database Impact** | None — `GET /v1/users/me` already queries `user_state`; add computed fields to response mapper or DTO. |
| **API Impact** | Extend `ProfileView` schema (or add `memorySummary` field) in `api/schemas/users.py`; ensure serialization includes new fields. |
| **UI/UX Impact** | Prominent "What I know about you" section on profile; users can understand what Fansivibe remembers. Tapping items could show more detail or correction flows. |
| **Tests Required** | Widget test: profile screen renders memory summary with correct data. Unit test: memory summary fields populated from user_state. |
| **Risk** | LOW. Additive UI change; existing profile data unchanged. No breaking API changes if new field is optional. |

---

## P1 — Gaps That Significantly Reduce Personalization Quality

### G-P1-1: Backend Decision Engine Does Not Use Saved Looks for Scoring

| Field | Details |
|---|---|
| **Current Behavior** | `score_candidates` only checks `preferredLookIds` from `user_state.preferences` for +0.03 boost. Actual saved look history (from `saved_looks` table or `UserModel.savedLooks`) is not considered. |
| **Desired Behavior** | Backend `score_candidates` includes +0.03 boost if look ID appears in user's saved looks history (from `saved_looks` table or `UserModel.savedLooks`), in addition to existing `preferredLookIds` check. |
| **Source/File** | `backend/app/domain/services/analysis_rules.py:score_candidates()` |
| **Backend Impact** | Modify scoring function to query saved look history (via repository or direct SQL) and apply boost. Must distinguish from `preferredLookIds` (which are explicit user preferences) from saved look history (derived behavior). |
| **Database Impact** | May add repository method `getSavedLookIds(user_id) → List<String>` on `SavedLookRepositorySQL`. Existing `saved_looks` table provides the data. |
| **API Impact** | None — scoring is internal to decision engine; no API contract changes. |
| **UI/UX Impact** | Recommendations may change subtly (some looks get slight boost) once backend personalization active. |
| **Tests Required** | Unit test: score_candidates with saved look in history gets +0.03 boost; test that preferredLookIds and savedLooks boost are independent. |
| **Risk** | LOW. Boost is additive (+0.03) and cumulative with preferredLookIds boost. If no saved looks, behavior identical to current. |

### G-P1-2: Discover Personalization Limited to Screen-Side Adjustments

| Field | Details |
|---|---|
| **Current Behavior** | Discover screen applies +10 occasion match, +5 style tag match, -20 saved look downgrade as compensatory adjustments on top of backend recommendations that have no personalization. Backend engine produces unsorted, unpersonalized recommendations. |
| **Desired Behavior** | Backend engine produces personally scored recommendations; Discover screen aligns with backend output rather than applying compensatory adjustments. Compensatory -20 saved look downgrade reduced or removed once backend handles it. |
| **Source/File** | `features/discover/presentation/discover_screen.dart:_personalizeLooks()`, `analysis_rules.py` |
| **Backend Impact** | See G-P1-1; once saved looks boost is added, Discover screen can remove or adjust its -20 compensatory downgrade. |
| **Database Impact** | None beyond G-P1-1. |
| **API Impact** | None. |
| **UI/UX Impact** | Discover "For You" tab recommendations change; saved look handling may look different initially as backend takes over personalization. |
| **Tests Required** | Integration test: backend personalization active → Discover screen shows consistent personalization without compensatory adjustments. Widget test: Discover screen personalization behavior with mock data. |
| **Risk** | MEDIUM. Changing the Discover personalization logic may change visible recommendation order; must ensure no regression in look discovery functionality. |

### G-P1-3: Style Score Does Not Reflect Learned Behavior

| Field | Details |
|---|---|
| **Current Behavior** | Style score = 60 + wardrobe items (max +20) + saved looks (2pt each, max +20). Saved looks contribution is capped and does not incorporate signal history or frequency. |
| **Desired Behavior** | Style score incorporates signal history weight; repeated interactions (saves, analysis updates) increase score influence smoothly. Score reflects accumulated user engagement. |
| **Source/File** | `learning_service.dart:styleScore`, `learning_service.dart UserModel` |
| **Backend Impact** | None — style score is Flutter-side calculation. |
| **Database Impact** | None. |
| **API Impact** | None. |
| **UI/UX Impact** | Style score on Home screen better reflects user's engagement history; may increase or decrease depending on saved look count and wardrobe size. |
| **Tests Required** | Widget test: StyleScoreCard displays correct score based on wardrobe + saved looks. Unit test: styleScore calculation with various wardrobe/savedLooks combinations. |
| **Risk** | LOW. Formula change only; existing data produces different but valid scores. Capping remains same max +20 for saved looks. |

### G-P1-4: No Feedback Loop for Incorrect Recommendations

| Field | Details |
|---|---|
| **Current Behavior** | Users can save likes (look_saved signal) but cannot indicate "not interested" or "dislike". No mechanism to exclude looks beyond explicit `preferredLookIds` / `excludedLookIds`. |
| **Desired Behavior** | System supports "pass" or "not interested" action on recommendations; emits `look_passed` learning signal; signal history expands `excludedLookIds` for future filtering. |
| **Source/File** | `features/discover/presentation/discover_screen.dart` (recommendation card interaction), `backend/app/domain/services/analysis_rules.py`, `backend/app/application/saved_looks.py` |
| **Backend Impact** | Add `look_passed` signal type to `signal_types` enum; add repository method to filter candidates by look_passed history; potentially add `POST /v1/looks/passed` endpoint or reuse save pathway. |
| **Database Impact** | Add `signal_type='look_passed'` to `signal_types` table via Alembic migration; add `look_passed` handling in `learning_signals` insert pathway. |
| **API Impact** | Add `POST /v1/looks/passed` endpoint or extend existing save workflow; or add "pass" button on recommendation cards that emits signal. |
| **UI/UX Impact** | Recommendation cards have "Pass"/"Not Interested" option alongside "Save" option. |
| **Tests Required** | Unit test: `look_passed` signal emitted on pass action. Integration test: pass action excludes look from future recommendations. Unit test: `excludedLookIds` expanded from look_passed history. |
| **Risk** | MEDIUM. New "pass" action changes user interaction model; must ensure backward compatibility with existing save-only flow. |

---

## P2 — Useful Future Improvements

### G-P2-1: Recommendation History Not Visible to Users

| Field | Details |
|---|---|
| **Current Behavior** | No UI shows past recommendations or why they were shown. Users have no visibility into what Fansivibe has recommended before. |
| **Desired Behavior** | "Recommendation history" section in Profile or Discover showing last N recommendations with match reasons, confidence scores, and match explanations. |
| **Source/File** | `features/profile/presentation/profile_screen.dart`, `features/discover/presentation/discover_screen.dart` |
| **Backend Impact** | Add recommendation history to `GET /v1/users/me` response or new endpoint `GET /v1/recommendations/history`. Each entry includes: run_id, look_id, match_score, confidence, match_reasons, viewed_at. |
| **Database Impact** | May require new table `recommendation_history` or reuse `learning_signals` + `saved_looks` with type discriminator. Or simply query recent analysis runs + saved looks with timestamps. |
| **API Impact** | New endpoint or extended response field. |
| **UI/UX Impact** | Profile screen gets "Recommendation History" section; user can scroll through past recommendations. |
| **Tests Required** | Widget test: recommendation history section renders with mock data. Integration test: history populated after multiple analysis runs and saves. |
| **Risk** | LOW. Additive UI feature; no existing functionality removed. Data may be sparse initially. |

### G-P2-2: Appearance Profile Correction Flow

| Field | Details |
|---|---|
| **Current Behavior** | No mechanism to update faceShape/skinTone/bodyType if analysis was wrong. Profile shows appearance data but no edit path. |
| **Desired Behavior** | Profile screen allows correction of appearance attributes; correction emits `style_updated` learning signal; may trigger re-analysis if underlying data changed. |
| **Source/File** | `features/profile/presentation/profile_screen.dart`, `features/profile/presentation/screens/ai_analysis_screen.dart` |
| **Backend Impact** | Add PATCH or PUT endpoint for profile appearance update, or new analysis trigger pathway. Validation of new appearance values against vocabulary. |
| **Database Impact** | `user_state.style_profile` JSONB update; version increment for optimistic locking. |
| **API Impact** | Add `PATCH /v1/users/me/appearance` or extend existing profile update endpoint. |
| **UI/UX Impact** | Profile appearance edit controls; user can correct face shape, skin tone, etc. |
| **Tests Required** | Widget test: profile appearance correction flow. Unit test: appearance update validation. Integration test: `style_updated` signal emitted after correction. |
| **Risk** | MEDIUM. Changing appearance profile can cascade to many recommendations; must ensure data validity and user intent. |

### G-P2-3: Context-Aware Recommendations

| Field | Details |
|---|---|
| **Current Behavior** | No contextual factors (time, event, season) influence recommendations beyond `preferred_occasions` which is not actively consumed. |
| **Desired Behavior** | Optional occasion context from preferences influences recommendation scoring; future: time-of-day, seasonal style signals. |
| **Source/File** | `user_state.preferences` handling, `decision_context.completeness` |
| **Backend Impact** | Enhance `DecisionContext` with optional `occasion` field; scoring boost if occasion matches look's occasion metadata. |
| **Database Impact** | Extend `user_state.preferences` JSONB to include occasion metadata; no new table required. |
| **API Impact** | Ensure `preferred_occasions` passed through API response; already present in `ProfileView`. |
| **UI/UX Impact** | Minor; preferences screen already has occasion focus selection. |
| **Tests Required** | Unit test: scoring with occasion match boost. Integration test: preferred occasions affect recommendation order. |
| **Risk** | LOW. Optional field; existing behavior unchanged if not set. |

### G-P2-4: Signal-Weighted Confidence Adjustment

| Field | Details |
|---|---|
| **Current Behavior** | Confidence = 50% data completeness + 50% top-pick decisiveness only; no adjustment based on signal reliability or history. |
| **Desired Behavior** | Confidence modulated by signal reliability: frequent savers get higher confidence, sparse profiles get lower than completeness-only would suggest. |
| **Source/File** | `backend/app/domain/services/analysis_rules.py:derive_confidence()` |
| **Backend Impact** | Modify `derive_confidence` to accept signal history parameter; compute reliability weight from saved look frequency, signal density, interaction recency. |
| **Database Impact** | None — signal history already in `learning_signals` table. |
| **API Impact** | Confidence field already in `AnalysisRun` result; no new API field needed. |
| **UI/UX Impact** | Confidence displayed on recommendation cards may change; may appear higher/lower based on user's interaction history. |
| **Tests Required** | Unit test: `derive_confidence` with signal history produces different value than without. Integration test: frequent saver gets higher confidence than sparse profile with same completeness. |
| **Risk** | LOW. Confidence already in [0,1]; new weighting only adjusts within range. Backward compatible when no signal history exists. |

### G-P2-5: Cross-Feature Preference Synchronization Verification

| Field | Details |
|---|---|
| **Current Behavior** | Preferences changed in one feature not reflected in others. LearningService singleton exists but verification of consistency across features not enforced. |
| **Desired Behavior** | All features use same user model; preference changes propagate reliably across all features (home, discover, grooming, assistant). |
| **Source/File** | `learning_service.dart` singleton pattern, all feature APIs that read UserModel |
| **Backend Impact** | None — LocalStore persistence is single source; verify no feature bypasses LearningService. |
| **Database Impact** | None. |
| **API Impact** | None. |
| **UI/UX Impact** | Users experience consistent preferences across all screens. |
| **Tests Required** | Integration test: change preference in one feature → verify reflected in another. Widget tests across multiple feature screens. |
| **Risk** | LOW. Mostly verification and documentation; if inconsistency found, minor fix to ensure all features go through LearningService. |

---

## P3 — Long-Term Enhancements

### G-P3-1: Preference Drift Detection

| Field | Details |
|---|---|
| **Current Behavior** | No detection if user's stated preferences change over time (e.g., previously saved looks no longer match user taste). |
| **Desired Behavior** | System detects preference drift (e.g., saved look history no longer matches preferredOccasions) and flags for review. |
| **Source/File** | `learning_signals` temporal analysis, `user_state.preferences` versioning |
| **Backend Impact** | Add `preference_version` or `drift_flag` to `user_state`; add periodic analysis job that compares signal history against current preferences; emits `style_updated` or `occasion_preferred` signal if drift detected. |
| **Database Impact** | Add `preference_version` column to `user_state` or `preference_drift` table. |
| **API Impact** | New field in `GET /v1/users/me` response or drift status endpoint. |
| **UI/UX Impact** | Profile shows preference drift warning; user can review and update. |
| **Tests Required** | Integration test: drift detection after preference changes. Unit test: drift analysis job runs correctly. |
| **Risk** | LOW-MEDIUM. Background job; no immediate user impact. Drift detection logic must be conservative to avoid false positives. |

### G-P3-2: Cross-Feature Preference Synchronization

| Field | Details |
|---|---|
| **Current Behavior** | LearningService singleton exists; but verification that all features reliably read from same model state. Potential for divergence if feature bypasses singleton. |
| **Desired Behavior** | Explicit guarantee that all features read user model through LearningService singleton; any preference change propagates to all features. |
| **Source/File** | `learning_service.dart` singleton, all feature APIs |
| **Backend Impact** | None — already singleton pattern. Verification only; may add assertions or tests. |
| **Database Impact** | None. |
| **API Impact** | None. |
| **UI/UX Impact** | Users experience consistent preferences; no more "I set this in grooming but it didn't show up in discover". |
| **Tests Required** | Integration test: preference change in one feature → verified in all others. |
| **Risk** | LOW. Mostly test-verification; if divergence found, fix is routing all reads through LearningService. |

### G-P3-3: Adaptive Confidence Over Time

| Field | Details |
|---|---|
| **Current Behavior** | Confidence recalculated only on new analysis runs; no adaptation based on accumulated signal history. |
| **Desired Behavior** | Confidence adapts based on accumulated signal history; stable users get higher baseline confidence even with sparse recent profiles. |
| **Source/File** | `derive_confidence` in `analysis_rules.py` |
| **Backend Impact** | Enhance confidence derivation to weight by signal history length, frequency, recency. |
| **Database Impact** | None beyond existing signal history. |
| **API Impact** | None. |
| **UI/UX Impact** | Confidence scores on recommendations may shift over time for same user; more stable for frequent users. |
| **Tests Required** | Unit test: confidence adapts over signal history simulated timeline. Integration test: long-lived user profile confidence stabilizes. |
| **Risk** | LOW. Confidence stays in [0,1]; adaptation smooths rather than abruptly changes. |

### G-P3-4: Natural Language Preference Input

| Field | Details |
|---|---|
| **Current Behavior** | Preferences only via curated vocabulary: `preferred_occasions` with allowed values ['work', 'office', 'date', 'party', 'travel']. No other preference input modes. |
| **Desired Behavior** | Optional natural language preference input processed into structured preferences; backward compatible with existing vocab. |
| **Source/File** | `assistant_service.dart`, `backend/app/application/analysis.py`, preferences screen UI |
| **Backend Impact** | NLP pipeline to extract preference intentions from user text; map to structured `preferred_occasions` or extend vocab. |
| **Database Impact** | May extend `preferred_occasions` vocab or add new preference category field. |
| **API Impact** | Assistant chat may return structured preference updates; no core API change. |
| **UI/UX Impact** | Assistant can accept "I prefer night-out events over work events" and update user model. |
| **Tests Required** | Unit test: NLP preference extraction. Integration test: assistant updates preferences from natural language. |
| **Risk** | MEDIUM. NLP introduces ambiguity; must be strict about allowed domains and fall back to current vocab gracefully. |

### G-P3-5: Provenance-Rich Memory Summary

| Field | Details |
|---|---|
| **Current Behavior** | Memory summary (if P0-G-P0-3 implemented) would label everything similarly without distinguishing source. |
| **Desired Behavior** | Memory summary distinguishes: user-stated (explicit), AI-inferred (from analysis), user-saved, system-derived (from signals) with confidence levels and timestamps. |
| **Source/File** | Profile memory section, `GET /v1/users/me` response enrichment |
| **Backend Impact** | Enrich `memorySummary` or new endpoint field with source attribution per data point. |
| **Database Impact** | May need to store source attribution metadata alongside existing data (e.g., `preferences.source` flag, `style_profile.sourceRunId` already tracks analysis origin). |
| **API Impact** | Extended response fields. |
| **UI/UX Impact** | Users can understand why Fansivibe knows what it knows; can correct or provide feedback on inferred data. |
| **Tests Required** | Widget test: memory summary shows source attribution. Unit test: source flags correctly set per data origin. |
| **Risk** | LOW. Additive labeling; no data change. Users may be surprised by attribution but it's educational. |

---

## Recommended Implementation Order

### Phase 1 — P0 Wins (Weeks 1-2)
1. **G-P0-2**: Persist preferences across sessions (LocalStore + backend write path)
2. **G-P0-3**: Add memory summary to profile screen (UI only, API enrichment optional)
3. **G-P0-1**: Consume look_saved signals in decision engine scoring (backend rules change)

### Phase 2 — P1 Gains (Weeks 3-4)
4. **G-P1-1**: Include saved looks in backend scoring boost
5. **G-P1-4**: Add "pass/not interested" mechanism with look_passed signal
6. **G-P1-2**: Align Discover personalization with backend output (remove compensatory adjustments)

### Phase 3 — P2 Refinements (Weeks 5-6)
7. **G-P2-1**: Recommendation history UI section
8. **G-P2-4**: Signal-weighted confidence adjustment
9. **G-P2-3**: Context-aware recommendations with occasion boost

### Phase 4 — P3 Polish (Weeks 7-8)
10. **G-P3-1**: Preference drift detection job
11. **G-P3-3**: Adaptive confidence over time
12. **G-P3-4**: Natural language preference input (optional, assistant-integrated)
13. **G-P3-2**: Cross-feature preference synchronization verification
14. **G-P3-5**: Provenance-rich memory source attribution

---

## Required UI Changes

| ID | Area | Change | P-Level |
|---|---|---|---|
| UI-P0-1 | Profile screen | Add "Memory" section showing what Fansivibe remembers (appearance verified, saved looks count, preferred occasions with source labeling) | P0 |
| UI-P0-2 | Preferences screen | Persist changes to LocalStore; show saved indicator on successful persistence | P0 |
| UI-P1-1 | Recommendation cards | Add "Pass"/"Not Interested" button alongside Save | P1 |
| UI-P1-2 | Discover screen | Remove or adjust compensatory -20 saved look downgrade once backend personalization active | P1 |
| UI-P0-3 | Profile screen | Source attribution labeling on memory summary items (AI-inferred vs user-stated vs user-saved) | P0/P3 |
| UI-P2-1 | Profile screen | "Recommendation History" section showing past recommendations with match reasons | P2 |
| UI-P3-1 | Profile screen | Preference drift warning indicator (long-term) | P3 |
| UI-P3-2 | Assistant screen | Natural language preference input field/command | P4 (included in P3) |

---

## Required Backend Changes

| ID | Area | Change | P-Level |
|---|---|---|---|
| BE-P0-1 | `analysis_rules.py:score_candidates()` | Add preference boost from saved look history (not just preferredLookIds) | P0 |
| BE-P0-2 | `analysis_rules.py:derive_confidence()` | Optionally accept signal history for reliability weighting | P2 |
| BE-P0-3 | `saved_looks.py` / repositories | Add `getSavedLookIds(user_id) → List<String>` repository method | P0 |
| BE-P0-4 | API schemas | Enrich `ProfileView`/`GET /v1/users/me` response with memory summary fields | P0 |
| BE-P0-5 | `analysis_rules.py` | Add `look_passed` signal type consumption in filtering/staging | P1 |
| BE-P1-1 | `signal_types` enum | Add `look_passed` if not already present (verify existing types) | P1 |
| BE-P1-2 | Database migration | Add `look_passed` to `signal_types` table if needed; add `preference_version` column for drift detection (P3) | P1/P3 |
| BE-P1-3 | API endpoints | Add `POST /v1/looks/passed` or extend save workflow; add profile appearance update endpoint (P2) | P1/P2 |
| BE-P2-1 | API / database | Recommendation history endpoint + storage (optional table or learning_signals extension) | P2 |
| BE-P3-1 | Background job | Preference drift detection job (runs periodically, compares signal history vs preferences) | P3 |
| BE-P3-2 | Confidence derivation | Enhance `derive_confidence` with signal reliability weight | P2/P3 |

---

## Required Database Changes

| ID | Table/Column | Change | P-Level |
|---|---|---|---|
| DB-P0-1 | `user_state` JSONB | No new column; existing `preferences` field used for persistence; `style_profile` already exists | P0 |
| DB-P0-2 | `learning_signals` | No new columns; existing `signal_type, label, context, occurred_at` sufficient; add index on `user_id, signal_type` for signal history queries | P0 |
| DB-P0-3 | `user_state` | May add `preference_version` column for drift detection (P3) | P3 |
| DB-P1-1 | `signal_types` | Add `look_passed` enum value if consuming P1-G-P1-4 | P1 |
| DB-P1-2 | `saved_looks` | No new columns; existing `look_id, user_id, title, snapshot, idempotency_key, created_at` sufficient | P0/P1 |
| DB-P2-1 | New or extended table | `recommendation_history` optional: `run_id, user_id, look_id, match_score, confidence, match_reasons, viewed_at, viewed_at` | P2 |
| DB-P3-1 | `user_state` | `preference_version` column for drift detection | P3 |

---

## Required API Changes

| ID | Endpoint | Change | P-Level |
|---|---|---|---|
| API-P0-1 | `GET /v1/users/me` | Extend response with `memorySummary` field: `appearanceVerified`, `savedLooksCount`, `preferredOccasions`, `appearanceConfidence` | P0 |
| API-P0-2 | `GET /v1/users/me` | Ensure `preferred_occasions` present in `preferences` map (may already be) | P0 |
| API-P1-1 | `POST /v1/looks/passed` | New endpoint: emit `look_passed` learning signal with context {"source_context", "look_id"} | P1 |
| API-P1-2 | `PATCH /v1/users/me/appearance` | New endpoint: update faceShape/skinTone/bodyType/styleType with validation | P2 |
| API-P2-1 | `GET /v1/recommendations/history` | New endpoint: recent recommendations with match reasons and confidence | P2 |
| API-P3-1 | `GET /v1/users/me/memory` | Alternative endpoint for memory summary if not extending users.me | P3 |

---

## Required Tests

| ID | Test Type | Scope | Related Gap |
|---|---|---|---|
| T-P0-1 | Unit | `score_candidates` with saved look history boost | G-P0-1, G-P1-1 |
| T-P0-2 | Unit | `derive_confidence` with/without signal history | G-P2-4 |
| T-P0-3 | Widget | Profile screen memory summary renders correctly | G-P0-3 |
| T-P0-4 | Widget | Preferences screen persistence round-trip | G-P0-2 |
| T-P1-1 | Unit | `look_passed` signal emission on pass action | G-P1-4 |
| T-P1-2 | Integration | Pass action excludes look from future recommendations | G-P1-4 |
| T-P1-3 | Unit | `excludedLookIds` expanded from look_passed history | G-P1-4 |
| T-P2-1 | Widget | Recommendation history section renders with mock data | G-P2-1 |
| T-P2-2 | Integration | History populated after multiple analysis runs and saves | G-P2-1 |
| T-P2-3 | Unit | Scoring with occasion match boost | G-P2-3 |
| T-P2-4 | Integration | Preferred occasions affect recommendation order | G-P2-3 |
| T-P3-1 | Integration | Drift detection job runs and flags correctly | G-P3-1 |
| T-P3-2 | Unit | Confidence adapts over simulated signal history | G-P3-3 |
| T-P3-3 | Widget | Memory summary shows source attribution (P3-G-P3-5) | G-P3-5 |
| T-P3-4 | Integration | Preference change in one feature → reflected in all others | G-P3-2 |

---

## Risk Summary

| Risk Area | Severity | Mitigation |
|---|---|---|
| **Appearance profile drift** (P3-G-P3-1) | MEDIUM | Conservative drift detection; user review before any changes; no automatic profile mutation |
| **Signal history growth** (unbounded learning_signals) | LOW | Append-only design already in place; periodic archival considered if needed |
| **Preference contradiction** (user-stated vs derived) | MEDIUM | Explicit labeling never treat inference as user preference; UI distinguishes sources |
| **Backend scoring changes altering recommendations** | LOW | Boosts are additive (+0.03) and cumulative; backward compatible when no history exists |
| **UI/UX confusion from memory summary** | LOW | Clear source attribution labels; users can opt into/out of memory features |
| **Cross-feature preference divergence** | LOW | Enforce all features read through LearningService singleton; integration tests verify |
| **Database migration risks** | LOW | All changes use existing columns/types; new columns optional with defaults; Alembic migrations tested offline |

---

## Summary

### Current State Classification: **LEVEL 1 — UNDERSTOOD**
- Verified appearance information available from analysis runs
- User preferences stored but not persisted or consumed
- Saved looks tracked but not used for scoring
- Learning signals emitted but not consumed by decision engine
- Personalization is screen-side compensatory, not engine-driven

### Target State Classification: **LEVEL 4 — PERSONALIZED**
- Recommendations use multiple reliable user signals (appearance + preferences + behavior)
- Style score reflects learned behavior
- Users can view what Fansivibe knows about them
- Preferences persist across sessions
- Learning signals flow through to recommendation personalization

### Critical Path to Level 4:
1. P0-G-P0-1: Consume look_saved signals in decision engine (enables basic signal-based personalization)
2. P0-G-P0-2: Persist preferences (ensures user-stated preferences survive sessions)
3. P1-G-P1-1: Include saved looks in scoring (elevates personalization from basic to personalized)
4. P1-G-P1-4: Add pass mechanism (creates feedback loop for continuous improvement)

### Total Estimated Effort:
- **Backend**: ~3 person-weeks (signals consumption, preference persistence, API enrichment)
- **Flutter/Frontend**: ~2 person-weeks (profile memory section, preferences persistence, recommendation pass)
- **Database**: ~1 person-week (indexes, optional columns, migration)
- **Tests**: ~1 person-week (unit, widget, integration across all gaps)
- **Total**: ~7 person-weeks for P0+P1 baseline; additional ~3 person-weeks for P2+P3 enhancements