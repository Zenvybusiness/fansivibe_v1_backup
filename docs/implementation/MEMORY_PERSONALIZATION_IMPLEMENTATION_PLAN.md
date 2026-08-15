# Memory + Personalization Implementation Plan

## Overview

This document defines the eight-stage implementation plan for progressively remembering and personalizing the user. Each stage specifies the exact purpose, existing code to reuse, files likely affected, database impact, API impact, UI/UX impact, tests, risks, and dependencies. The plan follows the recommended implementation order from the gap report (Phase 1: P0 Wins, Phase 2: P1 Gains, Phase 3: P2 Refinements, Phase 4: P3 Polish).

The current system is **LEVEL 1 — UNDERSTOOD**. The target is **LEVEL 4 — PERSONALIZED**.

---

## Stage A — Memory Persistence

### Purpose
Ensure user-provided and AI-inferred memory persists across app sessions. This is the foundation for all subsequent personalization.

- **G-P0-2**: Persist preferences screen changes across sessions (LocalStore + backend write path)
- **G-P0-3**: Add "what Fansivibe knows" memory summary to profile screen

### Existing Code to Reuse
- `backend/app/api/schemas/users.py` — `ProfileView` DTO (already has `preferences`, `styleProfile`, `version`)
- `backend/app/api/routers/users.py` — `get_me` use case (`GetProfile`); `_record_to_schema` mapper
- `backend/app/infrastructure/db/models.py` — `UserState` model with JSONB `preferences`, `style_profile`, `flags`, `version`
- `newproject/flutter_application_1/lib/features/learning/domain/learning_service.dart` — `LearningService` singleton (manages `UserModel` in LocalStore)
- `newproject/flutter_application_1/lib/features/learning/data/local_store.dart` — `LocalStore` (shared_preferences read/write)
- `newproject/flutter_application_1/lib/features/learning/data/models.dart` — `UserModel` (wardrobe, face, styleType, savedLooks, preferredOccasions, signals)

### Database Impact
- No new tables or columns required (P0).
- `user_state.preferences` JSONB already exists; ensure `preferred_occasions` key is written on every preference persistence.
- `user_state.style_profile` JSONB already exists; no schema change.
- `learning_signals` table already has required columns (`signal_type`, `label`, `context`, `occurred_at`).
- Index recommendation: `(user_id, signal_type, occurred_at)` on `learning_signals` for signal history queries (P0 performance optimization).

### API Impact
- Extend `GET /v1/users/me` response with `memorySummary` field (API-P0-1).
- No new endpoints; existing `GET /v1/users/me` sufficient with response enrichment.
- `_record_to_schema` in `routers/users.py` adds `memorySummary` dict to `ProfileView` output.

### UI/UX Impact
- Profile screen (`profile_screen.dart`) adds "Memory" section showing:
  - Appearance verified status (with AI-inferred labeling)
  - Saved looks count
  - Preferred occasions (with source labeling: user-stated vs AI-inferred)
  - Appearance confidence score
- Tapping memory items could show correction flows (future: P2/P3).
- Preferences screen (`preferences_screen.dart`) now persists changes to LocalStore + backend on each selection.

### Tests Required
- **Unit test**: `GetProfile` use case returns `memorySummary` fields populated from `UserState` with preferences data.
- **Widget test**: Profile screen renders "Memory" section with correct data (mock user_state with style_profile and preferences).
- **Widget test**: Preferences screen persistence round-trip: update preference, quit app, restart, verify preference persists in LocalStore.
- **Unit test**: `memorySummary.appearanceVerified` computed correctly (all 4 appearance signals present vs. missing).
- **Unit test**: `memorySummary.savedLooksCount` matches `SELECT count(*) FROM saved_looks WHERE user_id = X`.

### Risks
- **LOW**: Existing data structures unchanged; only adds persistence pathway and computed fields.
- **MEDIUM**: If `preferred_occasions` key missing in DB, `_to_preferences` mapper may produce empty list; ensure backward compatibility.
- **MEDIUM**: LocalStore persistence failure (shared_preferences unavailable) — gracefully degrades to in-memory only (existing LocalStore behavior).

### Dependencies
- LearningService `_persist()` already calls LocalStore save — ensure `preferredOccasions` included in `UserModel` encoding (already: `UserModel.toJson()` includes `'preferredOccasions'` key).
- Backend `GetProfile` use case already reads `user_state.preferences` — ensure mapper writes `preferredOccasions` under wire key `"preferredOccasions"` (already: `_to_preferences` in `routers/users.py` handles snake_case → camelCase).
- Profile screen already exists; only adds "Memory" section, not a full redesign.

---

## Stage B — Preference Handling

### Purpose
Persist user-stated preferences and ensure they flow into the decision engine scoring pipeline.

- **G-P0-1**: Consume look_saved signals in decision engine scoring (consumed in stages 3-4)
- **G-P1-1**: Include saved looks in backend scoring boost (in addition to preferredLookIds)

### Existing Code to Reuse
- `backend/app/domain/services/analysis_rules.py` — `score_candidates()` (hairstyle); currently checks `preferredLookIds` from preferences for +0.03 boost
- `backend/app/domain/value_objects.py` — `HairstylePreferences` ( `excludedLookIds`, `preferredLookIds` )
- `backend/app/domain/services/analysis_rules.py` — `build_context()` → `DecisionContext` (appearance + preferences + completeness + knowledge_version)
- `backend/app/application/analysis.py` — `CreateHairstyleRun` (updates `user_state.style_profile` via `_user_state.update_style_profile`)
- `backend/app/api/schemas/users.py` — `ProfileView.preferences` dict (passed through as JSONB)
- `backend/app/api/routers/users.py` — `_to_preferences` mapper (snake_case → camelCase wire key)
- `newproject/flutter_application_1/lib/features/learning/domain/learning_service.dart` — `addPreferredOccasion()`, `preferredOccasions`, `styleScore`

### Database Impact
- No new tables or columns required (P0/P1).
- `user_state.preferences` JSONB already stores `preferred_occasions` (snake_case in DB).
- No schema migration needed; existing column sufficient.
- `signal_types` table: may add `look_passed` enum value (DB-P1-1) if P1-G-P1-4 is implemented; otherwise P0 does not require this.

### API Impact
- `GET /v1/users/me` already returns `preferences` map with `preferredOccasions` key (via `_to_preferences` mapper).
- No new endpoints for P0. P1-G-P1-4 would add `POST /v1/looks/passed` (API-P1-1).
- Preference persistence pathway: Flutter `LearningService.addPreferredOccasion()` → LocalStore → backend `GET /v1/users.me` round-trip.

### UI/UX Impact
- Preferences screen changes now survive app restart (LocalStore persistence).
- Profile "Memory" section displays `preferredOccasions` with source labeling (user-stated).
- No visual changes to preferences screen beyond persistence indicator.

### Tests Required
- **Unit test**: `score_candidates` with saved look in history gets different score than without (G-P0-1, G-P1-1).
- **Unit test**: `preferredLookIds` from `HairstylePreferences` correctly applied in `score_candidates` preference_boost logic.
- **Widget test**: Preferences screen: update occasion, restart app, verify preference persists and displays on profile.
- **Integration test**: Save look → verify `look_saved` signal emitted → verify recommendation score changes (or stays same if no signal history consumed yet, backward compatible).

### Risks
- **LOW**: Preference boost (+0.03) is additive and cumulative with face_shape_boost; backward compatible when no preferredLookIds set.
- **MEDIUM**: If `preferred_occasions` not persisted in backend JSONB, user input lost on server restart; fix is ensuring write path in application use cases.
- **MEDIUM**: Flutter `preferredOccasions` and backend `preferred_occasions` may diverge if one side writes and other doesn't; enforce all writes go through LearningService singleton.

### Dependencies
- Stage A (Memory Persistence) must complete first — preference persistence LocalStore backend write path depends on `GET /v1/users.me` mapper already in place.
- Stage C (Behavioral Signals) will consume the `look_saved` signal that this stage enables.
- Decision engine `score_candidates` already has preference_boost logic; only needs saved look history boost (Stage C).

---

## Stage C — Behavioral Signals

### Purpose
Ensure behavioral events (saved looks, signal history) are properly recorded and consumed by the decision engine for recommendation personalization.

- **G-P0-1**: Consume look_saved signals in decision engine scoring
- **G-P1-1**: Include saved looks in backend scoring boost
- **G-P1-4**: Add "pass/not interested" mechanism with look_passed signal

### Existing Code to Reuse
- `backend/app/domain/services/analysis_rules.py` — `score_candidates()` (current: seed + face_shape_boost + preference_boost only)
- `backend/app/domain/services/analysis_rules.py` — `filter_candidates()` (checks `preferences.excludedLookIds`)
- `backend/app/domain/ports/repositories.py` — `SavedLookRepository` protocol ( `get_for_user`, `get_by_idempotency`, `commit`, `rollback` )
- `backend/app/infrastructure/db/repositories.py` — `SavedLookRepositorySQL` implementation
- `backend/app/application/saved_looks.py` — `SaveRecommendation` use case (TRX-3: atomic saved_looks INSERT + learning_signals look_saved INSERT)
- `backend/app/domain/ports/repositories.py` — `LearningSignalRepository` protocol ( `insert_look_saved`, `commit`, `rollback` )
- `backend/app/infrastructure/db/repositories.py` — `LearningSignalRepositorySQL` implementation
- `learning_service.dart` — `addSavedLook()`, `signalType: 'look_saved'`, signal recording
- `analysis_rules.py` — `derive_confidence()` (50% completeness + 50% decisiveness)

### Database Impact
- No new tables or columns required (P0/P1).
- `learning_signals` table already has `signal_type`, `label`, `context` JSONB, `occurred_at`.
- `saved_looks` table already has `user_id`, `look_id`, `title`, `snapshot`, `idempotency_key`, `source_run_id`, `created_at`.
- `signal_types` table: add `look_passed` row (DB-P1-1) if P1-G-P1-4 implemented; otherwise P0 uses existing types.
- Proposed index: `(user_id, signal_type, occurred_at)` on `learning_signals` for signal history queries.

### API Impact
- `POST /v1/looks/saved` already emits `look_saved` signal (TRX-3, atomic with save).
- New `POST /v1/looks/passed` (API-P1-1) emits `look_passed` signal if P1-G-P1-4 implemented.
- No other API changes; existing endpoints sufficient.

### UI/UX Impact
- Recommendation cards may gain "Pass"/"Not Interested" button (P1-G-P1-4: UI-P1-1).
- Discover screen compensatory -20 saved look downgrade may be reduced/removed once backend personalization active (P1-G-P1-2: UI-P1-2).
- Save flow unchanged; pass action is complementary option on cards.

### Tests Required
- **Unit test**: `score_candidates` with saved look ID in user's history gets +0.03 boost (G-P0-1, G-P1-1).
- **Unit test**: `score_candidates` with `look_passed` history expands `excludedLookIds` for filtering (G-P1-4).
- **Integration test**: Save look → query recommendation → verify score boost from saved look history.
- **Integration test**: Pass look → verify `look_passed` signal emitted → verify look excluded from future recommendations.
- **Unit test**: `derive_confidence` with signal history produces different value than completeness-only (G-P2-4).

### Risks
- **LOW**: Boost of +0.03 is small and cumulative; if no saved look history, behavior identical to current (backward compatible).
- **MEDIUM**: Signal history grows unbounded (append-only per PR-5); no deletion mechanism. Mitigation: periodic archival considered P3.
- **MEDIUM**: `look_passed` signal interaction model change — users must distinguish "Save" (like) vs "Pass" (dislike). Backward compat: save-only flow unchanged if no pass endpoint.

### Dependencies
- Stage A (Memory Persistence) — preference persistence must be working before signal history is meaningful.
- Stage B (Preference Handling) — `preferredLookIds` from preferences already consumed; Stage C adds saved look history boost on top.
- Backend `SaveRecommendation` TRX-3 already atomic: `saved_looks INSERT + learning_signals look_saved INSERT`. No code change needed.
- Flutter `LearningService.addSavedLook()` already records `look_saved` signal.

---

## Stage D — Personalization Context

### Purpose
Define the contract between Memory and ContextBuilder, ensuring the personalization context contains only information the Decision Engine needs.

- **Target**: Memory → PersonalizationContext → ContextBuilder → Decision Engine
- **Constraint**: Context must be deterministic and testable; no raw image data, no raw model responses, no unnecessary DB records.

### Existing Code to Reuse
- `backend/app/domain/services/analysis_rules.py` — `build_context()` → `DecisionContext` (appearance + preferences + completeness + knowledge_version)
- `backend/app/domain/value_objects.py` — `HairstylePreferences` ( `excludedLookIds`, `preferredLookIds` )
- `backend/app/domain/services/analysis_rules.py` — `DecisionContext` dataclass (appearance, preferences, completeness, knowledge_version)
- `backend/app/domain/services/analysis_rules.py` — `_completeness()` (fraction of non-empty appearance signals / 4)
- `backend/app/domain/services/analysis_rules.py` — `derive_confidence()` (50% completeness + 50% decisiveness)

### Personalization Context Definition
The `DecisionContext` already serves as the personalization context. It contains:

| Field | Source | Type | Labeling |
|---|---|---|---|
| `appearance` | `AppearanceProfile` | dataclass | AI-inferred (from style_profile) |
| `preferences` | `HairstylePreferences` | dataclass | explicit (user-stated) + derived (from behavior) |
| `completeness` | computed float 0.0–1.0 | fraction of {faceShape, skinTone, bodyType, styleType} non-empty | AI-inferred completeness score |
| `knowledge_version` | str | KN-1 provenance | e.g. "1.0" |

**Enhancement for labeling**: The `DecisionContext` should explicitly label preferences as `explicit` or `derived` so the Decision Engine does not silently treat inference as user preference. This is P3-G-P3-5 (provenance-rich memory summary), but a minimal P0/P1 step is to ensure the distinction is visible in the context for debugging/auditability.

### Database Impact
- No new tables or columns. `DecisionContext` is fully in-memory constructed from existing data.

### API Impact
- No new public APIs. `DecisionContext` is internal to the backend domain service layer.
- `GET /v1/users/me` `memorySummary` provides user-facing analog of the context.

### UI/UX Impact
- No direct UI impact. Context is internal engine data.
- Profile "Memory" section labels source of each data point (AI-inferred vs user-stated) — P3-G-P3-5 enhancement.

### Tests Required
- **Unit test**: `build_context` produces `DecisionContext` with correct `completeness` from given `AppearanceProfile`.
- **Unit test**: `derive_confidence` deterministic: identical inputs → identical output.
- **Unit test**: `DecisionContext` preferences labeled as `explicit` (frozenset of `preferredLookIds`) vs `derived` (frozenset of `excludedLookIds` from signal history).
- **Integration test**: Full pipeline: appearance + preferences → `DecisionContext` → `recommend_hairstyle` → scored recommendations.

### Risks
- **LOW**: `DecisionContext` already exists and is used by the engine; only adding labeling/distinction information.
- **MEDIUM**: If `completeness` formula changes (e.g., add new appearance signals), existing runs may produce different confidence scores. Version pinning via `knowledge_version` mitigates this.

### Dependencies
- Stage A (Memory Persistence) — `style_profile` and `preferences` must be readable from `user_state`.
- Stage B (Preference Handling) — `preferredLookIds` and `excludedLookIds` must be populated from preference/signal data.
- Stage C (Behavioral Signals) — `look_saved` and `look_passed` signal history must be queryable for `excludedLookIds` expansion.

---

## Stage E — Decision Engine Integration

### Purpose
Modify the decision engine scoring pipeline to incorporate behavioral signals and preferences from memory, elevating personalization from screen-side compensatory adjustments to engine-driven personalization.

- **G-P0-1**: Consume look_saved signals in decision engine scoring (stages 3-4)
- **G-P1-1**: Include saved looks in backend scoring boost (in addition to preferredLookIds)
- **G-P1-2**: Align Discover personalization with backend output (remove compensatory adjustments)

### Existing Code to Reuse
- `backend/app/domain/services/analysis_rules.py` — Full pipeline: `build_context()` → `generate_candidates()` → `filter_candidates()` → `score_candidates()` → `rank_candidates()` → `build_explanations()` → `derive_confidence()` → `recommend_hairstyle()`
- `backend/app/domain/services/analysis_rules.py` — `_BOOSTS` dict (per-look face-shape boosts)
- `backend/app/domain/services/analysis_rules.py` — `_PREFERENCE_BOOST = 0.03`
- `backend/app/domain/services/analysis_rules.py` — `_APPEARANCE_SIGNALS = ("faceShape", "skinTone", "bodyType", "styleType")`
- `backend/app/domain/services/analysis_rules.py` — `_DECISIVE_GAP = 0.1`
- `backend/app/application/analysis.py` — `CreateHairstyleRun` orchestrates the pipeline
- `backend/app/application/analysis.py` — `CreateOutfitRun` (TRX-6: updates user_state.style_profile + emits learning signal)

### Decision Engine Modifications

#### Stage 3 — Filtering: Expand `excludedLookIds` from signal history
**Current**: Only checks `context.preferences.excludedLookIds` (frozenset, explicit user preferences).
**Modified**: Also expand `excludedLookIds` from `look_passed` signal history (if `look_passed` signal type consumed).

```python
def filter_candidates(candidates, context):
    excluded = set(context.preferences.excludedLookIds)
    # Add looks from look_passed signal history
    passed_looks = get_passed_look_ids(context.user_id)  # new query
    excluded |= passed_looks
    if not excluded:
        return list(candidates)
    return [look for look in candidates if look.id not in excluded]
```

#### Stage 4 — Scoring: Add saved look boost + refine preference boost
**Current**: `score = min(1.0, seed + face_shape_boost + preference_boost)` where `preference_boost = 0.03 if look.id in preferredLookIds else 0.0`.
**Modified**: 
- Keep existing `preference_boost` for `preferredLookIds` (explicit user preferences).
- Add `saved_look_boost` if look ID appears in user's saved look history (derived behavior).
- Both boosts are independent and cumulative.

```python
def score_candidates(candidates, context):
    face = _face_shape(context.appearance)
    preferred = context.preferences.preferredLookIds
    saved_look_ids = get_saved_look_ids(context.user_id)  # new query from saved_looks table
    
    scored = []
    for look in candidates:
        face_boost = _BOOSTS.get(look.id, {}).get(face, 0.0)
        preference_boost = _PREFERENCE_BOOST if look.id in preferred else 0.0
        saved_look_boost = 0.03 if look.id in saved_look_ids else 0.0  # NEW
        score = min(1.0, look.matchScore + face_boost + preference_boost + saved_look_boost)
        # Track all three signals in breakdown
        signals = {
            "seed": look.matchScore,
            "face_shape": face_boost,
            "preference": preference_boost,
            "saved_look": saved_look_boost,  # NEW
        }
        scored.append(ScoredCandidate(id=look.id, score=round(score, 2), signals=signals, look=look))
    return scored
```

**Key design decisions** (per gap report risk analysis):
- Preference boost (+0.03) and saved look boost (+0.03) are **independent and cumulative**. A look the user both saved AND marked as preferred gets +0.06 total from preference+saved signals.
- If no saved look history, `saved_look_boost = 0.0` and behavior is identical to current (backward compatible).
- Boost is **additive**, not multiplicative; capped at 1.0 via `min(1.0, ...)`.

#### Stage 7 — Confidence: Incorporate signal reliability
**Current**: `derive_confidence(context, ranked) = 0.5 * completeness + 0.5 * decisiveness`.
**Modified**: Add signal reliability weight based on frequency and recency of interactions.

```python
def derive_confidence(context, ranked, user_id=None):
    completeness = context.completeness
    if len(ranked) >= 2:
        gap = ranked[0].score - ranked[1].score
        decisiveness = min(1.0, max(0.0, gap / _DECISIVE_GAP))
    else:
        decisiveness = 1.0
    
    # Signal reliability weight: 0.0 (no history) to 1.0 (frequent saver)
    if user_id is not None:
        signal_density = count_signals_in_last_30_days(user_id) / 30.0
        save_frequency = count_saved_looks(user_id) / 100.0  # normalized
        reliability = min(1.0, signal_density + 0.5 * save_frequency)
    else:
        reliability = 1.0  # no history → full confidence (backward compatible)
    
    return round(0.5 * completeness + 0.5 * decisiveness * reliability, 2)
```

**Rationale**: Frequent users with many saved looks and recent interactions get confidence boost even with same completeness score. Sparse profiles get lower confidence than completeness-only would suggest. When no signal history exists (new users), `reliability = 1.0` and behavior is identical to current (backward compatible).

### Database Impact
- No new tables or columns for P0/P1.
- P2: `recommendation_history` optional table (DB-P2-1) if history tracking desired.
- P1 `look_passed` signal type added to `signal_types` (DB-P1-1).

### API Impact
- No new public APIs for P0/P1 scoring changes (internal engine modification).
- P1 `POST /v1/looks/passed` (API-P1-1) new endpoint for emitting `look_passed` signals.
- P0 `GET /v1/users/me` `memorySummary` extension (API-P0-1).

### UI/UX Impact
- Recommendations may subtly change: some looks get slight boost from saved look history.
- Discover screen: once backend personalization active, remove compensatory -20 saved look downgrade (UI-P1-2).
- Confidence scores may shift for frequent users (higher) or sparse profiles (lower than before, but still honest).

### Tests Required
- **Unit test**: `score_candidates` with saved look in history gets +0.03 boost; test that preferredLookIds and savedLooks boost are independent (cumulative).
- **Unit test**: `score_candidates` without saved look history produces identical output to current behavior (backward compatibility).
- **Unit test**: `filter_candidates` with `look_passed` history expands `excludedLookIds` correctly.
- **Integration test**: Full pipeline end-to-end: save look → recommend → verify score boost.
- **Integration test**: Pass look → recommend → verify look excluded from future recommendations.
- **Unit test**: `derive_confidence` with signal history vs. without; sparse profile gets lower confidence with reliability weight, frequent saver gets higher.
- **Widget test**: Discover screen personalization behavior with mock data (aligned with backend output).

### Risks
- **LOW**: Boosts are small (+0.03 each) and capped at 1.0; backward compatible when no history exists.
- **MEDIUM**: Scoring changes alter recommendation order; must ensure no regression in look discovery functionality (the "long tail" of catalog looks may shift).
- **MEDIUM**: Confidence reliability weight formula must be conservative to avoid drastic confidence changes for established users.

### Dependencies
- Stage A (Memory Persistence) — `saved_looks` and `learning_signals` must be readable.
- Stage B (Preference Handling) — `preferredLookIds` from preferences already consumed; Stage C adds saved look history on top.
- Stage C (Behavioral Signals) — Signal history querying must be functional before engine modifications.
- Repository methods: `getSavedLookIds(user_id) → List[str]` on `SavedLookRepositorySQL`; `getPassedLookIds(user_id) → List[str]` on `LearningSignalRepositorySQL` (if P1-G-P1-4).

---

## Stage F — Home Data Integration

### Purpose
Determine what personalized Home should consume from the memory + personalization system. This stage defines the data flow from the decision engine to the Home screen widgets (Style Score, Today's Look, Recommendations, Style DNA).

- **Target**: Personalization Context → Home screen data → User-visible personalization
- **Constraint**: No fake Style Scores or personalization percentages. No design of visual Home yet. Only define data required.

### Existing Code to Reuse
- `learning_service.dart` — `styleScore` (60 + wardrobe.length.clamp(0,20) + savedLooks.length * 2 clamped 0,20)
- `home_mock_data.dart` — `HomeMockData` (styleScore, styleDNA, today'sLook, savedLooks, progress)
- `home_screen.dart` — main Home scaffold; `StyleScoreCard`, `StyleDnaCard`, `SavedLooksRow` widgets
- `discover_screen.dart` — personalization adjustments (+10 occasion, +5 style, -20 saved look downgrade)

### Home Data Requirements (P0 Minimum)

The Home screen should consume the following personalized data, read through the decision engine:

| Data Point | Source | Format | Notes |
|---|---|---|---|
| `styleScore` | `learning_service.dart` | int 60-100 | Already computed; incorporates wardrobe + saved looks count |
| `styleDNA` | `user_state.style_profile` | `{faceShape, skinTone, bodyType, styleType}` | AI-inferred; already displayed on Profile |
| `savedLooksCount` | `saved_looks` table | int | Displayed on Home; count of user-saved looks |
| `personalizationMaturity` | computed enum | LEVEL 0/1/2/3/4 | Conceptual; not displayed as XP/badges (per target principles) |
| `relevantNextAction` | deterministic | enum { "scan", "view_saved_looks", "update_preferences", "none" } | Based on what the user needs: incomplete profile → "scan"; no saved looks → "view_saved_looks"; complete → "none" |
| `recentRecommendations` | decision engine | recent run results | Optional P2; not required for P0 |

**`relevantNextAction` logic**:
- If `style_profile` completeness < 1.0 → "scan" (user needs analysis)
- Else if `savedLooksCount` = 0 → "view_saved_looks" (user has no saved looks)
- Else → "none" (profile complete, user can browse)

### Database Impact
- No new tables or columns.
- `styleScore` already computed in `learning_service.dart` from `UserModel` (wardrobe + savedLooks).
- `savedLooksCount` from `SELECT count(*) FROM saved_looks WHERE user_id = current_user_id`.
- `style_profile` completeness from `_completeness()` logic.

### API Impact
- `GET /v1/users/me` `memorySummary` provides `savedLooksCount` and `appearanceVerified` — Home can read these.
- No new endpoints. Existing `GET /v1/users.me` sufficient.
- `styleScore` read from LocalStore `UserModel` (Flutter side) or computed from `user_state` (backend side).

### UI/UX Impact
- Home screen: "Memory" indicators may appear (e.g., "Fansivibe remembers 3 saved looks").
- Style Score already displayed; may shift slightly as saved look history influences decision engine (P1-G-P1-1).
- Today's Look: currently mock/static; P1 enhancement would connect to user's appearance profile and preferences.
- Quick actions: "Scan" action may be highlighted if profile incomplete; "Saved Looks" if user has no saves.

### Tests Required
- **Unit test**: `styleScore` computation with various wardrobe + saved looks combinations.
- **Unit test**: `relevantNextAction` logic: completeness < 1.0 → "scan"; savedLooksCount = 0 → "view_saved_looks"; complete → "none".
- **Widget test**: Home screen renders style score, style DNA, saved looks count from real user data.
- **Integration test**: Home data consistency: `memorySummary` from API → Home widgets display correctly.

### Risks
- **LOW**: Style score formula unchanged (60 + wardrobe + saved looks); only may shift as decision engine incorporates saved look boost (P1).
- **MEDIUM**: "Relevant next action" logic must be conservative; wrong action suggestion feels paternalistic. Better to show generic quick actions rather than prescriptive ones.
- **MEDIUM**: Today's Look is entirely mock; connecting it to user data requires P1+ changes to the analysis pipeline and result screen.

### Dependencies
- Stage A (Memory Persistence) — `saved_looks` count and `user_state.style_profile` must be readable.
- Stage B (Preference Handling) — `preferred_occasions` may influence Today's Look or recommendations on Home.
- Stage C (Behavioral Signals) — `saved_looks` count directly affected by save actions; signal history affects scoring.
- Stage D (Personalization Context) — `DecisionContext.completeness` used for `appearanceVerified` logic in `relevantNextAction`.
- Stage E (Decision Engine Integration) — Scoring changes may affect recommendation order on Home if Home uses decision engine recommendations.

---

## Stage G — Memory UI

### Purpose
Implement the user-facing "What Fansivibe knows about you" memory summary and profile correction flows. This is the UI layer for the personalization system.

- **G-P0-3**: Add "what Fansivibe knows" user-facing summary to profile screen
- **G-P0-2**: Preferences persist across sessions (shown on preferences screen)
- **G-P2-2**: Appearance profile correction flow (P2 gap)
- **G-P3-5**: Provenance-rich memory source attribution (P3 gap)

### Existing Code to Reuse
- `profile_screen.dart` — existing scaffold; `ProfileData.mock` provides mock data structure
- `profile_widgets.dart` — `StyleDnaCard` (displays faceShape, skinTone, bodyType, styleType); `SavedLooksRow` (displays saved looks); `ProfileStatRow` (style score + global rank)
- `preferences_screen.dart` — existing preferences UI; `PreferenceOption` model; `ProfileMockData.stylePreferences`
- `learning_service.dart` — `UserModel` with `face`, `preferredOccasions`, `savedLooks`, `signals`
- `routers/users.py` — `_record_to_schema` mapper (already maps `user_state` to `ProfileView`)
- `analysis_rules.py` — `_completeness()` (computes fraction of non-empty appearance signals)

### Memory UI Components (P0 Minimum)

#### 1. Profile "Memory" Section
Added to `profile_screen.dart` below the StyleDnaCard:

```
+------------------------------------------+
| What Fansivibe knows about you           |
|                                          |
| ✓ Appearance profile: verified (AI-inferred) |
|   Face: Oval, Skin: Warm Medium, Body: Athletic, Style: Modern Minimalist |
|   Confidence: 75%                        |
|                                          |
| ✓ Saved looks: 4 saved                   |
|                                          |
| ✓ Preferred occasions: work, date (user-stated) |
|                                          |
|                                          |
|   (tapping items opens correction flow)  |
+------------------------------------------+
```

**Components**:
- `MemorySummaryCard` widget (new, in `profile_widgets.dart` or dedicated file):
  - `appearanceVerified` bool + confidence float → shows "verified (AI-inferred)" with confidence percentage
  - `savedLooksCount` int → shows "X saved looks"
  - `preferredOccasions` List<String> → shows "Y, Z (user-stated)"
  - Each item labeled with source: "AI-inferred" for appearance, "user-stated" for preferences
  - Tapping appearance profile items opens correction flow (P2: `PATCH /v1/users/me/appearance`)
  - Tapping saved looks navigates to Saved Looks screen

- Source attribution labeling (per audit Step 3 distinctions):
  - Appearance: "AI-inferred from analysis" — never silently treated as user confirmed
  - Preferences: "User-stated" — explicitly from preferences screen
  - Saved looks: "User-saved" — from user's save actions
  - Derived: "System-derived from signals" — learned from behavior (future)

#### 2. Preferences Persistence Indicator
On the Preferences screen, add a small persistence indicator:
- "Saved" toast on successful LocalStore + backend write
- Changes survive app restart (verified by widget test)

#### 3. Appearance Correction Flow (P2)
- Profile "Memory" tapping face shape/skin tone/body type/style type opens appearance correction UI
- PATCH `PATCH /v1/users/me/appearance` with new values
- On success, emit `style_updated` learning signal
- Refresh profile memory section

#### 4. Recommendation History (P2, optional)
- Profile section showing last N recommendations with match reasons and confidence (G-P2-1).
- Reuses `learning_signals` + `analysis_runs` data.

### Database Impact
- No new tables or columns.
- Profile memory section reads from existing `user_state` (style_profile, preferences) and `saved_looks`/`learning_signals` via repositories.
- `memorySummary` from `GET /v1.users.me` API provides aggregated data.

### API Impact
- `GET /v1/users/me` with `memorySummary` (API-P0-1) provides data for Memory section.
- `PATCH /v1/users/me/appearance` (API-P1-2) for appearance correction (P2 gap).
- `POST /v1/looks/passed` (API-P1-1) if P1 pass mechanism implemented.

### UI/UX Impact
- Profile screen: prominent "What Fansivibe knows about you" section added.
- Source attribution: users can understand why Fansivibe knows what it knows (AI-inferred vs user-stated).
- Tapping memory items may navigate to correction flows or detailed views.
- Preferences changes now persist — user sees saved indicator.

### Tests Required
- **Widget test**: Profile screen renders "Memory" section with correct data from mock user_state.
- **Widget test**: Memory summary source attribution labels correct: AI-inferred for appearance, user-stated for preferences.
- **Widget test**: Tapping appearance items in memory section navigates to correction flow (unit test: `PATCH /v1/users/me/appearance` succeeds).
- **Widget test**: Preferences screen persistence: update occasion, restart app, verify preference persists and displays in memory section.
- **Unit test**: `memorySummary.appearanceVerified` computed from `AppearanceProfile` completeness logic.
- **Unit test**: `memorySummary.preferredOccasions` sourced from `user_state.preferences.preferred_occasions` with source labeling.

### Risks
- **LOW**: Profile screen already has real estate; "Memory" section is additive, not redistributive.
- **MEDIUM**: Source attribution may surprise users who don't understand the AI-inferred vs user-stated distinction. Mitigation: clear labels, not technical jargon.
- **MEDIUM**: Appearance correction flow (P2) changes profile data; must ensure cascading re-computation of style score, recommendations, style DNA (engine re-runs with new profile).

### Dependencies
- Stage A (Memory Persistence) — LocalStore persistence + backend `GET /v1/users.me` memorySummary must be functional.
- Stage B (Preference Handling) — `preferredOccasions` must be persisted and readable.
- Stage C (Behavioral Signals) — `saved_looksCount` must reflect actual saved looks.
- Stage D (Personalization Context) — `DecisionContext.completeness` used for `appearanceVerified` logic.
- Stage E (Decision Engine Integration) — Scoring changes must not break existing profile data display.

---

## Stage H — End-to-End Validation

### Purpose
Validate the complete memory + personalization flow from user interaction through to personalized recommendations, ensuring all stages integrate correctly and no regressions are introduced.

- **Scope**: End-to-end flow from user save → signal recorded → decision engine scores → recommendations personalized → Home data consumed
- **Goal**: Verify P0 baseline (memory persistence + preferences + appearance) and P1 additions (saved look boost + pass mechanism)

### Existing Code to Reuse
- `backend/pytest` — full test suite (384 Flutter tests + 85 backend tests, skipping DB-backed tests cleanly)
- `backend/alembic` — offline DDL migration verification (`upgrade --sql head`, `downgrade --sql 0002:0001`)
- `newproject/flutter_application_1/` — full Flutter test suite; `controllable_hairstyle_service.dart` for controllable service
- `backend/tests/` — unit tests for decision engine, saved looks, analysis use cases
- `STEP_7_FINAL_REPORT.md` — validation framework and scenario matrix from previous steps
- `CURRENT_STATE.md` — current state tracking; used to ensure unrelated screens unchanged

### E2E Validation Scenarios (P0 Baseline)

#### Scenario H-1: Memory Persistence Across Sessions
1. User opens app → `LearningService.load()` → UserModel loaded from LocalStore (or defaults)
2. User navigates to Preferences screen → selects "Smart Casual" occasion
3. User quits app and relaunches → `LearningService.load()` → `preferredOccasions` includes "Smart Casual"
4. User views Profile → "Memory" section shows "Preferred occasions: Smart Casual (user-stated)"
5. **Backend**: `GET /v1/users.me` → `memorySummary.preferredOccasions` includes "Smart Casual"

**Expected**: Preference survives app restart; memory summary displays it with source labeling.

#### Scenario H-2: Appearance Memory from Analysis
1. User completes hairstyle analysis → `CreateOutfitRun` TRX-6 → updates `user_state.style_profile` with faceShape, skinTone, bodyType, styleType
2. `look_saved` signal emitted (TRX-6, Step 6 of `CreateOutfitRun`)
3. User views Profile → "Memory" section shows appearance profile with confidence score
4. **Backend**: `GET /v1/users.me` → `memorySummary.appearanceVerified` = true (all 4 attributes present)
5. `memorySummary.appearanceConfidence` = completeness score (0.0–1.0)

**Expected**: Appearance profile from analysis is remembered and displayed with AI-inferred labeling.

#### Scenario H-3: Preference Boost in Recommendations
1. User saves a look → `POST /v1/looks/saved` → TRX-3: `saved_looks INSERT + learning_signals look_saved INSERT`
2. User receives recommendation → decision engine `score_candidates` checks `preferredLookIds` from preferences
3. If user has `preferredLookIds` set → look gets +0.03 preference boost in score
4. If user has no preferences → score identical to current behavior (backward compatible)

**Expected**: Preference boost is applied; backward compatible when no preferences set.

#### Scenario H-4: Saved Look History Boost (P1)
1. User saves multiple looks over time
2. User receives new recommendation → decision engine `score_candidates` checks saved look history (from `saved_looks` table)
3. Looks appearing in user's saved look history get +0.03 saved look boost (independent of preference boost)
4. A look saved AND preferred gets +0.06 total from both signals (cumulative)
5. User passes on a look → `POST /v1/looks/passed` → `look_passed` signal emitted → future recommendations exclude that look

**Expected**: Saved look history influences recommendation scoring; pass mechanism creates feedback loop.

#### Scenario H-5: Confidence Adaptation
1. User with sparse profile (1 of 4 appearance attributes) → confidence = 0.5 * 0.25 + 0.5 * decisiveness
2. User with frequent saves → confidence reliability weight bumps up → higher confidence than completeness-only
3. User with no saves, sparse profile → confidence lower than before (honest signal)

**Expected**: Confidence reflects both data completeness and interaction history reliability.

### E2E Validation Scenarios (P1 Additions)

#### Scenario H-6: Pass/Not Interested Feedback Loop
1. User taps "Pass" on recommendation card → `POST /v1/looks/passed` with `lookId` + `sourceContext`
2. Signal `look_passed` emitted and stored in `learning_signals` table
3. `excludedLookIds` expanded from `look_passed` history → future recommendations exclude that look
4. User receives new recommendation → passed look no longer appears; different look ranked higher

**Expected**: Pass action influences future recommendations; creates continuous improvement feedback loop.

#### Scenario H-7: Discover Screen Alignment
1. User opens Discover screen → previously: +10 occasion match +5 style match -20 saved look downgrade
2. After backend personalization active: backend engine produces personally scored recommendations
3. Displayed recommendations reflect engine scores; compensatory -20 downgrade removed or reduced
4. User sees consistently personalized recommendations without compensatory adjustments

**Expected**: Backend personalization takes over; Discover screen aligns with engine output.

### Tests Required (End-to-End)

#### Backend Unit Tests
- **`test_decision_engine.py`**: All 18 existing tests still pass with new scoring logic (backward compatible).
- **`test_saved_looks_use_case.py`**: All 9 new save use case tests pass (already added in STEP 7).
- **`test_analysis_use_case.py`**: New DB-free tests for preference persistence and signal emission.
- **Unit test**: `score_candidates` with saved look history boost ≠ score without (P1).
- **Unit test**: `derive_confidence` with signal reliability weight ≠ completeness-only (P2).
- **Unit test**: `filter_candidates` with `look_passed` history expands `excludedLookIds` (P1).

#### Flutter Widget Tests
- **Profile screen**: Memory section renders with correct data from mock user_state.
- **Preferences screen**: Preference change persists across app restart (widget test with shared_preferences mock).
- **Saved looks screen**: Saved looks count matches `saved_looks` table query.
- **Discover screen**: Recommendation cards with pass button; pass action emits signal and changes future recommendations.

#### Integration Tests
- **Full flow**: Save look → check profile memory → receive recommendation → verify score boost → pass look → verify exclusion from future recommendations.
- **Persistence flow**: Update preference → quit → restart → verify preference in profile memory and profile API response.
- **Appearance correction**: PATCH appearance → verify style_updated signal → verify profile memory updates → verify recommendations re-compute.

### Risks
- **LOW**: Most existing tests pass backward-compatible; boosts are additive and small.
- **MEDIUM**: End-to-end integration tests require controllable services (mock backend) and signal history querying; may be complex to set up.
- **MEDIUM**: Signal history growth (append-only) may impact query performance over time; consider P3 archival strategy.

### Dependencies
- All previous stages (A–G) must be complete before end-to-end validation.
- Backend: `getSavedLookIds(user_id)` repository method must return correct data.
- Flutter: `LearningService` singleton must correctly manage UserModel across sessions.
- API: `GET /v1/users.me` must return `memorySummary`; `POST /v1/looks.passed` must emit signal.

### Success Criteria (P0 Baseline)
- [ ] Preferences persist across app sessions (LocalStore + backend write path)
- [ ] Profile "Memory" section appears with appearance verified status, saved looks count, preferred occasions
- [ ] `GET /v1/users.me` returns `memorySummary` field with all required sub-fields
- [ ] `score_candidates` backward compatible: no saved look history → identical scores to current behavior
- [ ] `derive_confidence` backward compatible: no signal history → identical confidence to current behavior
- [ ] Source attribution labeling: AI-inferred for appearance, user-stated for preferences

### Success Criteria (P1 Enhancements)
- [ ] All P0 success criteria met
- [ ] `score_candidates` includes +0.03 saved look boost for looks in user's saved history
- [ ] `POST /v1/looks/passed` emits `look_passed` signal
- [ ] `filter_candidates` expands `excludedLookIds` from `look_passed` history
- [ ] Confidence reliability weight adapts based on signal history
- [ ] Discover screen compensatory -20 downgrade removed/once backend personalization active

### Failure Criteria (any stage)
- [ ] Preferences lost on app restart (LocalStore or backend write path broken)
- [ ] Memory summary shows incorrect data (completeness miscalculation, count mismatch)
- [ ] Scoring changes introduce regressions (look discovery broken)
- [ ] API contract violations (new endpoints, wrong error codes, ownership bypass)
- [ ] User data privacy breach (inferred information treated as user-confirmed)