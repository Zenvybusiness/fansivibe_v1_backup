# STEP 9 — Core User Journey Integration Report

## Executive Summary

This report documents the audit, target flow, and gap analysis for the Fansivibe core user journey. The goal was to connect existing features into a coherent user journey without building new features, redesigning the application, or migrating architecture.

**Key Finding:** The backend APIs and UI infrastructure are largely in place. The blocking issues are entirely frontend: mock data usage, missing local persistence, and fragile router state management. No backend changes are required.

---

## 1. Current User Journey

### 1.1 First-Launch Flow
- **Path:** `SplashScreen` → `EntryScreen` → `VibeSelectScreen` → `CameraPermissionScreen` → `PhotoCaptureScreen` → `AiAnalysisScreen` → `YourAnalysisScreen` → `AccountCreationScreen` → `HomeScreen`
- **Timing:** ~8-10 screen transitions before any meaningful value appears
- **P0 Issue:** First useful value arrives too late (principle A)

### 1.2 Onboarding Flow
- Identical to first-launch flow — no distinction between new user and returning user
- 8 screens total, all users must complete them
- Account creation required to save any progress

### 1.3 Scan Flow
- **Path:** `HomeScreen` → `OutfitScanScreen` → `OutfitProcessingScreen` → `OutfitAnalysisScreen`
- Disconnected from onboarding/hair/grooming workflows
- Users who completed hairstyle/grooming analysis cannot seamlessly transition to outfit scanning

### 1.4 Hairstyle Flow
- **Path:** `Stylist` bottom nav → `FaceScanScreen` → `FaceProcessingScreen` → `HairstyleResultScreen`
- Save flow: `HairstyleService.saveLook` → `POST /v1/looks/saved` with idempotency key
- **P1 Issue:** Result screen uses mock data by default; saving functionally disconnected from backend in default path

### 1.5 Grooming Flow
- **Path:** `Stylist` bottom nav → `GroomingInputScreen` → user selects 4 features → `GroomingProcessingScreen` → `GroomingResultScreen`
- Save flow: `GroomingService.saveGroomingLook` → `POST /v1/looks/saved` with idempotency key
- **P1 Issue:** Input asks user for features (face shape, beard style) that system could infer from scan (violates principle B); result falls back to mock data

### 1.6 Account/Login Flow
- **Path:** `EntryScreen` → (account creation or sign in) → `HomeScreen`
- "Maybe Later — Save Locally" option exists but data doesn't persist across launches
- **P0 Issue:** Account creation blocks value preservation; users who skip start fresh each time

### 1.7 Home Arrival Flow
- Conditional logic based on `onboardingData` map keys
- 4 distinct paths based on visit status and analysis state
- **P1 Issue:** Home shows generic mock data regardless of user's actual analysis; returning users without `onboarding_data` see completely different content

### 1.8 Returning-User Flow
- Depends on `onboardingData` being correctly passed through GoRouter extras
- **P2 Issue:** Fragile — lost on app restart; user starts completely over
- Principle H (returning users see continuity) not satisfied

### 1.9 Saved-Look Flow
- **Path:** `ProfileScreen` → `SavedLooksScreen`
- Reads from `ProfileMockData.savedLooks` (6 hardcoded entries)
- Backend API `POST /v1/looks/saved` exists and is correctly wired
- **P2 Issue:** Mock data blocks persistence; UI visually complete but functionally disconnected

### 1.10 Persistence/Memory Behavior
- **Frontend:** `UserSession.hasSavedWardrobeItem` (static boolean, no persistence), `onboardingData` (lost on app restart)
- **Backend:** Saved looks with idempotency keys, user profiles, analysis run history, learning signals
- **Missing:** Local storage for analysis results, vibe preferences, capability state across sessions

### 1.11 Capability Analysis
- **Current:** `allCapabilities` list with 7 capabilities, most marked `active: false` with mock unlock hints
- **What exists:** Face Analysis (active), Color Analysis (active), Hairstyle Profile, Wardrobe Intelligence, Grooming Profile, Event Styling, Shopping Assistant (all inactive)
- **Data required for progress:** User's actual analysis results, saved looks, vibe selection — none are currently connected persistently

### 1.12 Trust Progression Analysis
- **Current state:** Users lose continuity on restart; recommendations feel generic; account creation creates friction; saved looks don't persist
- **Trust points where users lose confidence:** Onboarding friction (P0), mock data disconnect (P1/P2), fragile router state (P1), no memory across sessions (P2)

---

## 2. Target User Journey

### PATH A — New User Seeking Personalized Help
```
Welcome
↓
Get Started (Scan or Explore)
↓
Intent Recognized
↓
Scan / relevant action
↓
AI analysis (minimal user input)
↓
First useful insight (face shape, color palette)
↓
Recommendation displayed
↓
Save (optional, low-friction)
↓
Account persistence option (default: "Continue Without Account")
↓
Personalized Home (reflects user's actual data)
```

### PATH B — New User Who Wants to Explore
```
Welcome
↓
Explore (no scan required)
↓
Knowledge/discovery (vibe selection optional)
↓
First insight (from vibe or prior context)
↓
Personalization opportunity (vibe tunes content)
↓
Scan when ready
```

### PATH C — Returning User
```
Launch
↓
Restore session/profile (recognized)
↓
Personalized Home (reflects previous state)
↓
Continue from previous context
↓
New recommendation / scan / wardrobe / learning
```

**Key Target Behaviors:**
- First useful value arrives within 3-5 seconds of photo capture (or instantly for explore path)
- Account creation never blocks value — "Continue Without Account" is default
- Home reflects what Fansivibe already knows about the user
- Saved actions become user memory (persist across sessions)
- Returning users see continuity, not starting over
- Capability progression reflects actual user interactions, not generic XP

---

## 3. Gap Analysis

| # | Gap | Classification | Screen/File | Backend/API | DB Change | UI Change | Test Impact | Risk |
|---|-----|---------------|-------------|-------------|---------|---------|-------------|------|
| 1 | **Onboarding takes 8+ transitions before any value** | P0 | EntryScreen, VibeSelectScreen, CameraPermissionScreen, PhotoCaptureScreen, AiAnalysisScreen, YourAnalysisScreen, AccountCreationScreen | None (frontend only) | No | Yes — reduce screen count, add insight before account prompt | Low — UI reorganization only |
| 2 | **Account creation blocks value preservation** | P0 | AccountCreationScreen, EntryScreen _onSignIn | `POST /v1/looks/saved` exists but requires auth; `GET /v1/users/me` exists | No | Yes — add "Continue Without Account" default; local persistence layer | Low — flow reorganization |
| 3 | **Grooming input asks user for inferable data** | P1 | GroomingInputScreen (4 option groups: face shape, beard style, density, color) | None — UI-only issue; backend doesn't require these fields | No | Yes — make vibe selection optional; infer from scan when available | Low — UI reflow |
| 4 | **Home shows mock data regardless of user's actual analysis** | P1 | HomeScreen build method, FirstTimeHomeScreen, FirstTimeLightPathHomeScreen | `GET /v1/users/me` returns profile; `GET /v1/analysis/runs` returns history; `POST /v1/looks/saved` exists | No | Yes — connect Home to backend data; replace mock data with actual user data | Medium — data connectivity |
| 5 | **Returning user continuity depends on fragile router state** | P1 | Router extras (`onboardingData`), GoRouter configuration | None directly; depends on correct state propagation | No | Yes — add local persistence for session state; robust router state management | Medium — state management |
| 6 | **Saved looks are mock data, no persistence across sessions** | P2 | SavedLooksScreen, ProfileScreen, HairstyleResultScreen._saveStyle, GroomingResultScreen._buildActions | `POST /v1/looks/saved` exists and works; `GET /v1/users/me` returns profile | May need — connect frontend save to backend; ensure local cache syncs | Yes — integrate saved look persistence; hero cards already exist | Low — backend already works |
| 7 | **Capability grid uses mock active/inactive state** | P2 | `_buildCapabilityGrid` in FirstTimeHomeScreen, allCapabilities list | Depends on user's actual interactions; backend capable | No | Yes — replace mock state with actual user data from analysis/saved looks | Low — data source change |
| 8 | **No local persistence for analysis results between launches** | P2 | UserSession, onboardingData routing, all feature services | Backend APIs exist for data; missing local cache layer | Yes — add local storage (shared_preferences or similar) for: analysis results, vibe selection, saved looks, capability state | Medium — new local storage layer |
| 9 | **Scan flow disconnected from onboarding/hair/grooming** | P2 | HomeScreen _handleQuickAction, OutfitScanScreen | None — workflow separation; backend same | No | Yes — unify scan flow; shared scanning component | Low — workflow reorganization |
| 10 | **Vibe selection required before scanning (violates principle B)** | P1 | EntryScreen _onAnalyze → vibeSelect → camera permission; GroomingInputScreen | Vibe is optional preference; backend doesn't require it before scan | No | Yes — make vibe selection optional; allow scan first, infer direction later | Low — flow make optional |

**P0 Issues (3):** Onboarding friction, account creation blocking value, first useful value timing
**P1 Issues (4):** Grooming inferable data, mock data in home, returning user continuity, vibe selection requirement
**P2 Issues (3):** Saved look persistence, capability grid mock state, local persistence layer, scan flow disconnection

---

## 4. Required Changes

### 4.1 Required Backend Changes
**None.** All necessary endpoints exist:
- `GET /v1/users/me` — returns user profile with style profile
- `POST /v1/analysis/hairstyle` — submits hairstyle analysis, returns `run_id` (202)
- `POST /v1/analysis/grooming` — submits grooming analysis, returns `run_id` (202)
- `GET /v1/analysis/runs/{run_id}` — gets analysis run results
- `GET /v1/analysis/runs` — lists paged run history summaries
- `POST /v1/looks/saved` — saves recommendation with idempotency key; creates `look_saved` signal

### 4.2 Required Database Changes
**None.** Database schemas are complete:
- `users` table with `display_name`, `style_profile` (JSONB)
- `analysis_runs` table with run status, results
- `saved_looks` table with idempotency keys
- `learning_signals` table (written as side effect of save look)

### 4.3 Required UI Changes
**Minimal and targeted — preserve existing design system:**

1. **EntryScreen:** Make vibe selection optional; add "Continue Without Account" default after first insight (P0, P1)
2. **HomeScreen:** Connect to backend data instead of mock data; display user's actual insights, vibe, saved looks (P1, P2)
3. **FirstTimeHomeScreen / FirstTimeLightPathHomeScreen:** Replace mock data (`_mockScore`, `_mockDna`, `_mockPalette`) with actual user data from backend (P1)
4. **GroomingInputScreen:** Make vibe selection optional; don't require all 4 features before analyze (P1)
5. **HairstyleResultScreen / GroomingResultScreen:** Ensure save flows connect to backend when service is available (P2)
6. **SavedLooksScreen:** Connect to backend `GET /v1/users/me` for real saved looks; keep hero card UI (P2)
7. **UserSession:** Add local persistence for `hasSavedWardrobeItem` and session state (P2)
8. **Onboarding Data routing:** Make `onboardingData` robust across app restarts via local storage (P1)

### 4.4 Required Local Persistence Layer
Add local storage for:
- Analysis results (hairstyle/grooming/outfit) — cache between launches
- Vibe selection (StyleVibe) — persist user's chosen direction
- Saved looks — cache locally, sync with backend
- Capability state — track what user has unlocked
- User profile basics (display name, onboarding complete flag)

Use `shared_preferences` or equivalent Dart local storage solution.

### 4.5 Router State Management
- Ensure `onboardingData` is preserved across app launches
- Add fallback logic when `onboardingData` is missing/invalid
- Make returning user detection robust (not dependent on perfect router state)

---

## 5. Recommended Implementation Order

### Phase 1 — P0 Fixes (Value Delivery & Account Friction) *[2 weeks]*
1. EntryScreen: Make vibe selection optional; add "Continue Without Account" default after first insight
2. HomeScreen: Replace mock data with actual user data from backend where available
3. UserSession: Add local persistence for saved wardrobe item flag
4. Fix first-valuable-timing: show insight before account creation prompt

### Phase 2 — P1 Fixes (Continuity & Mock Data) *[3 weeks]*
5. Connect HomeScreen to backend data (`GET /v1/users/me`, `GET /v1/analysis/runs`, `POST /v1/looks/saved`)
6. Replace mock data in FirstTimeHomeScreen and FirstTimeLightPathHomeScreen with actual user data
7. Make GroomingInputScreen features optional; infer from scan when possible
8. Router state management: preserve onboardingData across launches via local storage

### Phase 3 — P2 Fixes (Persistence & Memory) *[3 weeks]*
9. Add local storage layer for: analysis results, vibe selection, saved looks, capability state
10. Connect SavedLooksScreen to backend saved looks via `GET /v1/users/me`
11. Update capability grid to reflect actual user interactions
12. Ensure Hairstyle/Grooming save flows connect to backend correctly

### Phase 4 — Validation & Refinement *[2 weeks]*
13. Run existing tests; verify no regressions
14. Verify returning user flow: launch app, see previous state, continue seamlessly
15. Verify first-user flow: scan → insight → home → save → relaunch preserves state
16. Conduct user testing on the new journey flow

---

## 6. Existing Architecture Reuse

The following existing architecture can be leveraged without modification:

- **GoRouter** — route definitions are correct; only need to pass correct extras
- **Design System** — `fansi_*` components, color tokens, typography, spacing — all preserved
- **Bottom Navigation** — 5-tab shell (Home, Discover, Stylist, Wardrobe, Profile) — no changes needed
- **Backend APIs** — all necessary endpoints exist and are correctly implemented
- **Hairstyle/Grooming Services** — injectable, support learning repository attachment; default path uses mock but can be wired to backend
- **Saved Look Hero Cards** — `FansiHeroCard` already designed; just needs real data connection
- **Onboarding Models** — `OnboardingResult`, `StyleVibe`, `AiCapability`, `HairstyleAnalysisResult`, `GroomingAnalysisResult` — already defined
- **Learning Signal Infrastructure** — `look_saved` signal automatically generated by `POST /v1/looks/saved`

**Should NOT be changed:**
- SplashScreen, EntryScreen CTA structure (keep "Analyze My Style" / "Explore Without Scanning")
- Router configuration (app_router.dart, route_names.dart)
- Bottom navigation (router_shell.dart)
- Shared components (fansi_*, user_session.dart infrastructure)
- Backend APIs

---

## 7. Test Impact Analysis

**Existing tests to verify:**
- Hairstyle save flow with idempotency key
- Grooming save flow with idempotency key
- Profile screen renders saved looks
- Home screen conditional logic
- Onboarding flow navigation

**New test coverage needed:**
- EntryScreen: vibe selection optional; "Continue Without Account" default
- HomeScreen: backend data connectivity (mock vs real)
- FirstTimeHomeScreen: actual user data display
- Returning user flow: app launch → restore state → home reflects previous data
- Local persistence: save/retrieve analysis results, vibe, saved looks across launches
- Saved looks: backend connectivity; idempotency key handling

**Risk mitigation:**
- All changes are frontend-only; backend unchanged
- Mock data preserved as fallback; new data path is additive
- Incremental changes — can roll back per screen/component
- Existing UI visually complete; changes connect existing pieces

---

## 8. Conclusion

The core Usersivibe user journey can be connected into a coherent experience without building new features or migrating architecture. The backend APIs and UI infrastructure are largely in place. The blocking issues are:

1. **Frontend→Backend connection:** Mock data used by default across multiple screens
2. **Local persistence:** No local storage layer for caching between launches
3. **Router state management:** `onboardingData` fragile across app restarts

These are all addressable with targeted frontend changes that:
- Preserve the existing design system and visual structure
- Add local persistence for session state
- Connect existing backend APIs to UI screens
- Make optional features (vibe selection) truly optional
- Add "Continue Without Account" as the default path

The recommended implementation order progresses from P0 (blocking value delivery) through P1 (major UX problems) to P2 (meaningful improvements), with each phase building on the previous one.