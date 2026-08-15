# MEMORY + PERSONALIZATION AUDIT

## STEP 1 — EXISTING MEMORY INSPECTION

### Backend: Data Sources

| Table/Model | Persisted | Temporary | Mock | Derived | Not Implemented |
|---|---|---|---|---|---|
| `users` | Yes | No | No | No | No |
| `user_state` (style_profile, preferences, flags) | Yes | No | No | Yes (JSONB derived) | No |
| `analysis_runs` | Yes | No | No | Yes (result JSONB) | No |
| `saved_looks` | Yes | No | No | Yes (snapshot JSONB) | No |
| `learning_signals` | Yes | No | No | Yes (append-only log) | No |
| `looks` (catalog) | Yes | No | No | No | No |
| `run_types` | Yes | No | No | No | No |
| `signal_types` | Yes | No | No | No | No |

### Flutter: Data Sources

| Storage/Feature | Persisted | Temporary | Mock | Derived | Not Implemented |
|---|---|---|---|---|---|
| `UserModel` (via LocalStore / shared_preferences) | Yes | No | Yes (mock data on first launch) | Yes (from analysis results) | No |
| `LearningService.savedLooks` | Yes | No | Yes (6 mock items) | Yes | No |
| `LearningService.preferredOccasions` | Yes | No | Yes (empty by default) | Yes | No |
| `LearningService.face` | Yes | No | Yes (null on first launch) | Yes | No |
| Style Score calculation | Derived | No | Yes (mock: 84) | Yes | No |
| `DiscoverScreen._personalizedLooks` | No | Yes | Yes (rebuilt every render) | Derived | No |

### Cross-Feature: Learning Signals

| Signal Type | Source | Stored | Consumed |
|---|---|---|---|
| `look_saved` | `SaveRecommendation` use case, `CreateOutfitRun` TRX-6 | Yes (`learning_signals` table + UserModel) | Not consumed by decision engine |
| `analysis_updated` | `CreateOutfitRun` TRX-6 | Yes | Not consumed by decision engine |
| `item_added` | Wardrobe interactions | Yes | Not consumed |
| `style_updated` | Style type change | Yes | Not consumed |
| `occasion_preferred` | Preferences screen | Partially (UI only) | Not consumed |
| `assistant_message` | Assistant chat | Yes | Not consumed |
| `suggestion_opened` | Discover screen | Yes | Not consumed |
| `assistant_navigation` | Assistant navigation | Yes | Not consumed |

---

## STEP 2 — MEMORY CATEGORIES EXISTING

### Identity
- **Status: PARTIALLY supported**
- `users` table has `display_name`, `auth_provider`, `auth_subject`
- Flutter `UserModel` has `displayName` from onboarding
- **Gap**: No centralized identity profile beyond basic account info

### Appearance
- **Status: FUNCTIONAL (verified)**
- `user_state.style_profile` stores `faceShape`, `skinTone`, `bodyType`, `styleType` from analysis runs
- Backend decision engine uses appearance profile for scoring boosts
- Flutter `UserModel.face` stores FaceProfile from analysis
- **Gap**: Appearance data only updated on new analysis runs; not incrementally updated

### Preferences
- **Status: PARTIALLY supported**
- `user_state.preferences` (JSONB) stores `preferred_occasions` (camelCase wire format)
- Flutter `UserModel.preferredOccasions` exists but preferences screen stores selections only in UI state, not persisted
- Decision engine applies +0.03 preference boost if look ID in `preferredLookIds`
- **Gap**: Preferences screen changes not persisted to backend or local store

### Behavior
- **Status: FUNCTIONAL (partial)**
- `saved_looks` table: user-saved recommendations with idempotency key
- Flutter `UserModel.savedLooks` maintains list of saved look titles
- Decision engine filters excluded looks and boosts preferred looks
- **Gap**: Learning signals emitted on save but not consumed by recommendation pipeline

### History
- **Status: FUNCTIONAL**
- `analysis_runs` table: append-only history of all analysis runs
- Flutter `LearningService.signals` accumulates interaction history
- **Gap**: Run history readable via API but not displayed in UI; signals not visualized

### Context
- **Status: BASIC**
- Decision engine `DecisionContext` includes `completeness` (fraction of non-empty appearance signals)
- Style score incorporates wardrobe and saved looks count
- **Gap**: Limited contextual awareness (no time-of-day, event, or location context)

---

## STEP 3 — SOURCE OF TRUTH ANALYSIS

### Where items originate and are stored:

| Item | Origin | Stored Where | Owner | Changeable | Inferred/Explicit | Confidence | Timestamp/Version |
|---|---|---|---|---|---|---|---|
| `users.display_name` | User onboarding | `users` table | User | Yes (profile edit) | Explicit | N/A | `updated_at` |
| `user_state.style_profile.faceShape` | Backend analysis | `user_state` JSONB | System | Yes (new analysis) | AI Inferred | Per-run confidence | `analysis_runs.created_at` |
| `user_state.style_profile.skinTone` | Backend analysis | `user_state` JSONB | System | Yes (new analysis) | AI Inferred | Per-run confidence | `analysis_runs.created_at` |
| `user_state.style_profile.bodyType` | Backend analysis | `user_state` JSONB | System | Yes (new analysis) | AI Inferred | Per-run confidence | `analysis_runs.created_at` |
| `user_state.style_profile.styleType` | Backend analysis | `user_state` JSONB | System | Yes (new analysis) | AI Inferred | Per-run confidence | `analysis_runs.created_at` |
| `user_state.preferences.preferred_occasions` | User preferences UI | `user_state` JSONB | User | Yes (preferences screen) | Explicit (user-stated) | N/A | `user_state.version` |
| `saved_looks.look_id` | User save action | `saved_looks` table | User | Yes (save/unsave) | User Saved | N/A | `saved_looks.created_at` |
| `learning_signals.label` | Save/analysis events | `learning_signals` table | System | Append-only (never mutates) | System Derived | N/A | `learning_signals.occurred_at` |
| `UserModel.savedLooks` | Across features | LocalStore (shared_preferences) | User | Yes (per-feature save) | User Saved | N/A | LocalStore modification time |
| `UserModel.preferredOccasions` | Preferences screen | LocalStore (shared_preferences) | User | Partially (UI only) | Explicit (user-stated) | N/A | LocalStore modification time |

### Distinctions:

- **USER SAID IT**: `preferred_occasions` (user-stated), `saved_looks.title` (user-named), `preferences` UI selections
- **AI INFERRED IT**: `style_profile` attributes (faceShape, skinTone, bodyType, styleType from analysis)
- **USER SAVED IT**: `saved_looks` rows, learning_signals look_saved entries
- **SYSTEM DERIVED IT**: `user_state.version`, confidence scores, completeness percentages, style score calculations

---

## STEP 4 — EXISTING LEARNING SIGNALS INSPECTION

### Current Signals and Producers:

| Signal | Producer | Consumed By | Influence on Recommendations |
|---|---|---|---|
| `look_saved` | `SaveRecommendation` (UC-15), `CreateOutfitRun` TRX-6 | Decision Engine (filtering/staging 3-4) | None currently; signals stored but not used in scoring |
| `analysis_updated` | `CreateOutfitRun` TRX-6 | None | None |
| `item_added` | Wardrobe feature | None | None |
| `style_updated` | Style type change | None | None |
| `occasion_preferred` | Preferences screen (UI only) | None | None |
| `assistant_message` | AssistantService | None | None |
| `suggestion_opened` | Discover screen | None | None |
| `assistant_navigation` | AssistantService | None | None |

### Signal Flow Analysis:

```
User Interaction
    ↓
Feature processes interaction
    ↓
Learning signal emitted (append-only learning_signals table)
    ↓
Signal stored in UserModel (LocalStore)
    ↓
Decision Engine does NOT consume signals
    ↓
Recommendations continue without personalization from signals
```

### Key Observations:

1. **9 learning signal types** are tracked but **none are consumed** by the decision engine for recommendation personalization
2. **`look_saved` signal** is the most significant: emitted on save, stored in both `learning_signals` table and `UserModel.savedLooks`, but the decision engine's scoring only checks `preferredLookIds`/`excludedLookIds` from `preferences`, not actual saved look history
3. **Signal append-only design** (PR-5) ensures historical record is preserved but creates no backward mutation
4. **TRX-6** (outfit analysis) emits `look_saved` with `label="analysis_updated"` and context `{"run_id", "run_type": "outfit"}`, linking image analysis to signal history
5. **No signal-based reranking** exists; the 7-stage pipeline is deterministic based on appearance + preferences only

### Current Personalization Flow:

```
User
  ↓
Profile (users.me → user_state)
  ↓
Appearance (style_profile from analysis_runs)
  ↓
Preferences (preferred_occasions from user_state.preferences)
  ↓
Saved Looks (saved_looks titles from UserModel)
  ↓
Learning Signals (logged but NOT consumed)
  ↓
Decision Engine (only uses: appearance + excludedLookIds + preferredLookIds)
  ↓
Recommendations (no signal-based adaptation)
```

### Classification:
**NONE** — The current system does not use learning signals to influence recommendations. Signals are logged for observability/history only.

---

## STEP 5 — PERSONALIZATION MATURITY CLASSIFICATION

### Tracing the personalization pipeline:

```
User
  ↓
Profile: GET /v1/users/me returns styleProfile + preferences + version
  ↓
Appearance: user_state.style_profile (faceShape/skinTone/bodyType/styleType)
  ↓
Preferences: user_state.preferences.preferred_occasions (camelCase map)
  ↓
Saved Looks: UserModel.savedLooks + saved_looks table
  ↓
Learning Signals: learning_signals table + UserModel.signals (append-only, NOT consumed)
  ↓
ContextBuilder (build_context): assembles appearance + preferences + completeness
  ↓
Decision Engine (7-stage pipeline)
    Stage 1: Context ✓
    Stage 2: Candidates from catalog ✓
    Stage 3: Filtering by excludedLookIds ✓
    Stage 4: Scoring: seed + face_shape_boost + preference_boost ✓
    Stage 5: Ranking by score ✓
    Stage 6: Explanation from catalog ✓
    Stage 7: Recommendation with confidence + needs_more_data ✓
  ↓
Flutter: Discover screen personalization (+10 occasion, +5 style, -20 saved look downgrade)
  ↓
Result: BASIC personalization
```

### Classification: **BASIC**

**Rationale:**
- Verified appearance information is available (from analysis runs)
- User preferences are stored but not actively consumed in the backend decision engine
- Saved looks are tracked but not used for recommendation scoring in the backend
- Discover screen has some personalization (+10/-20 adjustments) but backend engine does not use saved looks or learning signals
- Learning signals are emitted but not consumed anywhere in the pipeline
- Confidence is derived from data completeness + decisiveness, but does not adapt recommendations over time

The system has the **components** for personalization (appearance data, preferences storage, saved looks, learning signals) but **does not connect** them to the recommendation decision engine in a meaningful way.

---

## STEP 6 — HOME PERSONALIZATION STATUS

### What Home Currently Shows

| Component | REAL | MOCK | STATIC | PERSONALIZED |
|---|---|---|---|---|
| Style Score | Yes (computed) | No | No | Partially (60 + wardrobe + saved looks) |
| Style DNA | Yes (from user model) | No | No | Yes (styleType from analysis) |
| Today's Look | Yes (TodaysLookData.mock) | Yes (mock data) | Yes (always same) | No (no user-specific selection) |
| AI Insights | Yes (wardrobe insights) | Partially | No | Limited (wardrobe gaps only) |
| Recommendations | Yes (Discover integration) | Partially | Yes (mock looks) | Partially (Discover personalization) |
| Saved Looks | Yes (ProfileMockData 6 items) | Yes (mock) | Yes (static 6 items) | Yes (from UserModel, displayed) |
| Progress | Yes (style score trend) | No | No | Yes (score history) |
| Quick Actions | Yes (Scan, Build, Change) | No | No | No |
| Empty States | Yes (onboarding not complete) | No | Yes (first launch) | No |

### Key Findings:

- **Style Score** is partially personalized: 60 base + wardrobe items (1pt each, max +20) + saved looks (2pt each, max +20)
- **Today's Look** is entirely mock/static; no connection to user's appearance profile or preferences
- **Recommendations** on Home connect to Discover personalization (+10 occasion, +5 style, -20 saved look downgrade) but the home screen itself doesn't adapt based on what Fansivibe knows about the user
- **AI Insights** are wardrobe-focused, not appearance-focused
- **No** "As you know me" indicators or memory references on Home
- **Style DNA** is displayed but not meaningfully connected to recommendations

### What Home Gets Right:
- Style score progression reflects user activity (wardrobe items + saved looks)
- Saved looks from UserModel are displayed
- Quick actions are relevant to the feature set

### What Home Misses:
- No explicit "Fansivibe remembers me" messaging
- Today's Look has no personalization beyond mock data
- No connection between appearance profile and shown content
- No preference-based filtering or ordering
- No history of what Fansivibe has learned about the user

---

## STEP 7 — MEMORY USER EXPERIENCE AUDIT

### Can users currently:

| Capability | Status | Notes |
|---|---|---|
| View saved looks | Yes | Saved Looks screen shows 6 mock items; UserModel.savedShows also exists |
| Understand appearance profile | Partially | Profile screen shows style DNA; requires analysis run completion |
| Understand preferences | Partially | Preferences screen exists but changes not persisted; user model stores preferredOccasions |
| See recommendation history | No | No UI shows analysis run history or saved look provenance |
| Correct incorrect information | Limited | Profile screen allows navigation to preferences but no actual edit flow |
| Update user-provided preferences | No | Preferences screen UI exists but no persistence to backend or local store |

### Memory UX Gaps:

1. **No "What I know about you" summary** — users cannot see what Fansivibe has learned
2. **No correction mechanism** — if appearance profile is wrong, no easy way to update it
3. **Preferences not persisted** — changes in the preferences screen are lost on app restart
4. **No recommendation history** — users cannot see why certain recommendations were shown
5. **Saved looks disconnected** — saved in one feature not visible/accessible from others transparently

### Where UI/UX Changes Will Eventually Be Required:
- Memory summary screen (what Fansivibe knows)
- Profile corrections (appearance, preferences)
- Recommendation history/feedback
- Saved looks cross-feature visibility

---

## STEP 8 — PRIVACY + CONTROL STATUS

### Current Gaps:

| Area | Status | Concern |
|---|---|---|
| **Ownership** | Partial | `user_id` scopes all user tables (OW-1); backend enforces owner-only reads |
| **Authentication** | Accepted | Bearer token auth with dev seam (D-AUTH-1); `/v1/users/me` owner-only |
| **Access Control** | Functional | 404-not-403 on every user-owned endpoint; SQL repos enforce ownership |
| **Deletion** | Not Implemented | No API or UI for deleting analysis runs, saved looks, or learning signals |
| **Correction** | Not Implemented | No way to update appearance profile or preferences through UI |
| **Inferred vs User-Provided** | Not Distinguished | `style_profile` attributes presented as facts; no labeling as AI-inferred |
| **Data Retention** | Append-Only | `analysis_runs` and `learning_signals` never deleted; `saved_looks` immutable per TRX-3 |

### Inferred vs User-Provided Distinction:

- **Never silently treat an inference as a user preference** — Currently, the system does not make this error, but also does not distinguish. Appearance profile attributes are AI-inferred but displayed without any indication of how they were obtained.
- **Preferences** (`preferred_occasions`) are explicitly user-stated but not persisted, creating a gap where user input has no lasting effect.

### Data Sensitivity:

- Appearance data (face shape, skin tone, body type) is privacy-sensitive
- Saved looks may reveal user taste preferences
- Learning signals accumulate detailed interaction history
- All of the above are `user_id`-scoped with ownership enforcement, but no user-facing control surfaces exist

---

## STEP 9 — TARGET MEMORY MODEL (CONCEPTUAL)

```
USER
 ↓
PROFILE
   ↓
     ├─ identity: display_name, auth info
     └─ settings: flags, version
 ↓
APPEARANCE MEMORY
   ↓
     ├─ verified: faceShape, skinTone, bodyType, styleType (from analysis runs)
     ├─ history: all analysis_runs with results and confidence
     └─ provenance: source_run_id links saved_looks → analysis_runs
 ↓
PREFERENCE MEMORY
   ↓
     ├─ explicit: preferred_occasions (user-stated)
     ├─ derived: excludedLookIds, preferredLookIds (from saved look interactions)
     └─ history: learning_signals with labels and context
 ↓
BEHAVIOR MEMORY
   ↓
     ├─ saved_looks: user-saved recommendations (title, look_id, snapshot, created_at)
     ├─ interaction history: wardrobe additions, screen visits, saves
     └─ signal timeline: learning_signals.occurred_at ordering
 ↓
HISTORY
   ↓
     ├─ analysis_runs: append-only with status, result, error, created_at
     ├─ saved_looks: complete history of all saves with idempotency keys
     └─ learning_signals: full interaction log (signal_type, label, context, occurred_at)
 ↓
PERSONALIZATION CONTEXT
   ↓
     ├─ appearance: current verified profile + completeness score
     ├─ preferences: explicit + derived preferences
     ├─ behavior: saved looks count, interaction patterns
     └─ history: recent analysis runs, saved signals
 ↓
DECISION ENGINE
   ↓
     ├─ uses all above as input to 7-stage pipeline
     ├─ scores with: seed + face_shape_boost + preference_boost
     ├─ confidences: 50% completeness × 50% decisiveness
     └─ recommends with: confidence + needs_more_data flags
```

**Key Principles:**
- User-stated preferences explicitly distinguished from AI-inferred appearance
- Full history retained but clearly labeled (said vs inferred vs saved vs derived)
- Version tracking on all mutable state (`user_state.version`, `learning_signals` append-only)
- Provenance: saved_looks.source_run_id → analysis_runs.id for traceability
- Auditability: users can view what is remembered and why

---

## STEP 10 — PERSONALIZATION MATURITY PROGRESSION

### Current State: **LEVEL 1 — UNDERSTOOD**

Fansivibe has verified appearance information from analysis runs, but personalization does not yet flow from memory to recommendations.

### Progression Target:

| Level | Description | Required Changes |
|---|---|---|
| **LEVEL 0 — UNKNOWN** | Fansivibe knows almost nothing | Baseline; no analysis completed |
| **LEVEL 1 — UNDERSTOOD** | Verified appearance information | Currently here; appearance profile from analysis runs |
| **LEVEL 2 — PREFERENCES** | Explicit user preferences | Persist preferences screen changes; consume preferredOccasions in decision engine |
| **LEVEL 3 — BEHAVIOR** | Learns from supported user actions (saves) | Consume look_saved signals; rerank based on saved look history; display "remembered" indicators |
| **LEVEL 4 — PERSONALIZED** | Multiple reliable user signals | Preference boost + saved look boost + appearance boost all active in scoring |
| **LEVEL 5 — ADAPTIVE** | Recommendations evolve over time | Confidence-weighted adaptation; signal decay for stale behavior; preference drift detection |

**Important**: These are conceptual maturity stages, NOT gamification levels. Do NOT display them as XP, badges, or scores.

---

## STEP 11 — GAP ANALYSIS

### P0 — Blocks Meaningful Personalization

| Gap | Current Behavior | Desired Behavior | Source/File |
|---|---|---|---|
| **G-P0-1**: Learning signals emitted but not consumed | `look_saved` and `analysis_updated` signals stored in `learning_signals` table and UserModel but decision engine ignores them entirely | Decision engine stages 3-4 consume signal history: preference boost from saved looks, behavior-based scoring | `backend/app/domain/services/analysis_rules.py:score_candidates` |
| **G-P0-2**: Preferences not persisted across sessions | Preferences screen stores selections in UI state only; on app restart, preferences are lost | Preferences persisted to `user_state.preferences` (JSONB) and `UserModel.preferredOccasions`; restored on startup | `features/profile/presentation/preferences_screen.dart` + `learning_service.dart` |
| **G-P0-3**: No "what Fansivibe knows" user-facing summary | Users cannot view what the system has learned about them | Profile screen includes "Memory" section showing verified appearance, saved looks count, preferred occasions with clear labeling of source (AI-inferred vs user-stated) | `features/profile/presentation/profile_screen.dart` |

### P1 — Significantly Reduces Personalization Quality

| Gap | Current Behavior | Desired Behavior | Source/File |
|---|---|---|---|
| **G-P1-1**: Backend decision engine does not use saved looks for scoring | `preference_boost` only checks `preferredLookIds` from `user_state.preferences`, not actual saved look history | Backend `score_candidates` includes +0.03 boost if look ID appears in user's saved looks history (from `saved_looks` table or `UserModel.savedLooks`) | `backend/app/domain/services/analysis_rules.py` |
| **G-P1-2**: Discover personalization limited to screen-side adjustments | Discover screen applies +10/-20 adjustments but backend engine produces unsorted recommendations | Backend engine produces personally scored recommendations; Discover screen aligns with backend output rather than applying compensatory adjustments | `backend/app/domain/services/analysis_rules.dart` (if Flutter-side) or API contract |
| **G-P1-3**: Style score does not reflect learned behavior | Style score = 60 + wardrobe items + (saved looks × 2 capped at 20) but saved looks contribution capped; no behavior-based adaptation | Style score incorporates signal history weight; repeated interactions increase score influence smoothly | `learning_service.dart` styleScore calculation + `analysis_rules.py` scoring |
| **G-P1-4**: No feedback loop for incorrect recommendations | Users cannot indicate "not interested" beyond saving; no dislike/exclusion mechanism beyond explicit preferredLookIds | System supports learning from skipped/passed looks; excludedLookIds expanded from signal history; optional "pass" action emits learning signal | `backend/app/domain/services/analysis_rules.py` + `features/profile/presentation/saved_looks_screen.dart` |

### P2 — Useful Future Improvement

| Gap | Current Behavior | Desired Behavior | Source/File |
|---|---|---|---|
| **G-P2-1**: Recommendation history not visible to users | No UI shows past recommendations or why they were shown | "Recommendation history" section in Profile or Discover showing last N recommendations with match reasons and confidence | `features/discover/presentation/discover_screen.dart` |
| **G-P2-2**: Appearance profile correction flow | No mechanism to update faceShape/skinTone if analysis was wrong | Profile screen allows correction of appearance attributes; correction emits `style_updated` learning signal; triggers re-analysis if needed | `features/profile/presentation/profile_screen.dart` + `backend/app/application/analysis.py` |
| **G-P2-3**: Context-aware recommendations | No contextual factors (time, event, season) influence recommendations | Optional occasion context from preferences; future: time-of-day, seasonal style signals | `user_state.preferences` extension + `decision_context.completeness` enhancement |
| **G-P2-4**: Signal-based confidence adjustment | Confidence = 50% completeness + 50% decisiveness only; no signal weight adjustment | Confidence modulated by signal reliability: frequent savers get higher confidence, sparse profiles get lower | `backend/app/domain/services/analysis_rules.py:derive_confidence` |

### P3 — Long-Term Enhancement

| Gap | Current Behavior | Desired Behavior | Source/File |
|---|---|---|---|
| **G-P3-1**: Preference drift detection | No detection if user's stated preferences change over time | System detects preference drift (e.g., previously saved looks no longer matched) and flags for review | `learning_signals` temporal analysis + `user_state.preferences` versioning |
| **G-P3-2**: Cross-feature preference synchronization | Preferences changed in one feature (e.g., grooming) not reflected in others (e.g., discover) | Shared LearningService singleton ensures all features use same user model; preference changes propagate across features | `learning_service.dart` singleton pattern already exists; verify consistency |
| **G-P3-3**: Adaptive confidence over time | Confidence recalculated only on new analysis runs | Confidence adapts based on accumulated signal history; stable users get higher baseline confidence | `derive_confidence` enhancement with signal history parameter |
| **G-P3-4**: Natural language preference input | Preferences only via curated vocabulary (occasions) | Optional natural language preference input processed into structured preferences; backward compatible with existing vocab | `assistant_service.dart` + `backend/app/application/analysis.py` |
| **G-P3-5**: Provenance-rich memory summary | Current summary would label everything as "system derived" | Memory summary distinguishes: user-stated, AI-inferred from analysis, user-saved, system-derived with confidence levels | Profile memory section design |

### Recommended Implementation Order:

1. **P0-G-P0-3**: Persist preferences; add memory summary to profile (quick win, no backend changes beyond what exists)
2. **P0-G-P0-1**: Consume look_saved signals in decision engine scoring (backend rules change)
3. **P1-G-P1-1**: Include saved looks in backend scoring boost (rules engine modification)
4. **P1-G-P1-4**: Add "pass/dislike" mechanism with signal emission (backend + UI)
5. **P2-G-P2-1**: Recommendation history UI (frontend only, reuses existing data)
6. **P2-G-P2-4**: Signal-weighted confidence (backend confidence derivation)
7. **P3-G-P3-2**: Cross-feature preference synchronization verify (architecture review)
8. **P3-G-P3-1**: Preference drift detection (long-term signal analysis)

### Required Changes Summary:

**Backend Changes:**
- Modify `score_candidates` in `analysis_rules.py` to add preference boost from saved look history (not just `preferredLookIds`)
- Add `pass_look` use case that emits learning signal with `signal_type='look_passed'`
- Enhance `derive_confidence` to incorporate signal history reliability
- Add memory summary API endpoint or extend `/v1/users/me` with memory fields

**Database Changes:**
- None required for P0/P1 (signals already stored, preferences already JSONB)
- Add `signal_type='look_passed'` to `signal_types` enum migration if P1-G-P1-4
- Consider adding `preference_version` column to `user_state` for drift detection (P3)

**API Changes:**
- Extend `GET /v1/users/me` response with `memorySummary` field (P0-G-P0-3)
- Add `POST /v1/looks/passed` endpoint or reuse save pathway with signal type (P1-G-P1-4)
- Enhance learning signals endpoint if adding new signal types

**UI/UX Changes:**
- Profile screen: add "Memory" section showing what Fansivibe remembers (P0-G-P0-3)
- Preferences screen: persist changes to local store and backend (P0-G-P0-2)
- Discover screen: reduce compensatory adjustments once backend personalization is active (P1-G-P1-2)
- Add "pass" action on recommendation cards (P1-G-P1-4)

**Tests Required:**
- Unit tests for `score_candidates` with saved look history boost (P0-G-P0-1, P1-G-P1-1)
- Unit tests for `derive_confidence` with signal history (P2-G-P2-4)
- Widget tests for profile memory section (P0-G-P0-3)
- Integration tests for preference persistence flow (P0-G-P0-2)
- Saved looks pass signal test (P1-G-P1-4)