# Core User Journey Audit

## Current State Analysis

This audit maps the actual user journeys in the REAL Fansivibe repository and classifies mismatches against the product principles. No screens, routing, backend, or database was modified.

---

## 1. First-Launch Flow

**Path:** `SplashScreen` → `EntryScreen` → `VibeSelectScreen` → `CameraPermissionScreen` → `PhotoCaptureScreen` → `AiAnalysisScreen` → `YourAnalysisScreen` → `AccountCreationScreen` → `HomeScreen`

**Timing breakdown:**
- Splash: 1.8s auto-navigate to Entry
- Entry: Animation 1.2s, then user interaction required
- Vibe Select: User must choose a style vibe before proceeding
- Camera Permission: User must allow camera or choose gallery
- Photo Capture: User must capture or skip photo
- AI Analysis: ~3s animation, then auto-navigate to analysis results
- Your Analysis: Results screen with score, insights, save CTA
- Account Creation: Required to save progress

**Key observation:** The first meaningful value (analysis results) arrives after ~8-10 screen transitions and significant user interaction. This is a P0 block against principle A (first useful value should arrive quickly).

---

## 2. Onboarding Flow

**Path:** Same as first-launch flow above. The onboarding is the complete first-time user journey.

**Screens:**
1. Splash — brand introduction, auto-advances
2. Entry — primary CTA "Analyze My Style" or "Explore Without Scanning"
3. Vibe Select — choose style direction (6 options), or skip
4. Camera Permission — allow camera, choose gallery, or skip
5. Photo Capture — take photo or skip
6. AI Analysis — animated analysis processing
7. Your Analysis — results with score, insights, save CTA
8. Account Creation — email, password, name required or "Maybe Later"

**Note:** The onboarding and first-launch are identical because there is no distinction — every new user goes through the complete flow.

---

## 3. Scan Flow

**Path:** `HomeScreen` → `_handleQuickAction(scan_outfit)` → `OutfitScanScreen` → `OutfitProcessingScreen` → `OutfitAnalysisScreen`

**Details:**
- From Home, user taps "Scan My Outfit"
- Outfit scan screen: camera interface with guide
- Processing screen: shows processing animation
- Analysis screen: results (currently mock data)

**Issue:** The scan flow is disconnected from the onboarding flow. A user who completed onboarding and got hairstyle/grooming analysis cannot seamlessly transition to outfit scanning — the home quick actions treat them as separate workflows.

**Classification:** P2 — improvement opportunity, not blocking.

---

## 4. Hairstyle Flow

**Path:** `Hairstyle` route (from stylist bottom nav) → `FaceScanScreen` → `_handleScan` → `FaceProcessingScreen` → `HairstyleResultScreen`

**User interaction:**
- Face scan screen: checks lighting, distance, alignment (mock checks)
- User taps "Scan Face"
- Pushes to hairstyle processing (animation only, no real processing)
- Result screen: face shape, skin tone, style DNA, top recommendation
- Actions: "Try Another" or "Save Style"

**Save flow:** `_saveStyle` → `HairstyleService.saveLook` → backend `POST /v1/looks/saved` with idempotency key.

**Classification:** P1 — The hairstyle result screen uses mock data (`HairstyleAnalysisResult.mock`) when no result is provided. The service is injectable but the default path uses stub data. The "Save Style" CTA appears but saving to a non-existent backend is functionally disconnected.

---

## 5. Grooming Flow

**Path:** `Stylist` bottom nav → `GroomingInputScreen` → user selects face shape/beard style/density/color → `_analyze` → `GroomingProcessingScreen` → `GroomingResultScreen`

**User interaction:**
- Input screen: 4 option groups (face shape, beard style, density, color)
- Must select all 4 before "Analyze Style" is enabled
- Processing screen: animation only
- Result screen: match score, primary beard recommendation, eyewear recommendations, "why it works", specifications, alternatives
- Actions: "Try Another" or "Save Look"

**Save flow:** `_buildActions` → `service.saveGroomingLook` → backend `POST /v1/looks/saved` with idempotency key.

**Classification:** P1 — Same as hairstyle: result screen falls back to mock data. The grooming input screen asks user for features (face shape, beard style, etc.) that the system could potentially infer from a camera scan, conflicting with principle B.

---

## 6. Account/Login Flow

**Path:** `EntryScreen` → `_onSignIn` → `RouteNames.home` OR `AccountCreationScreen`

**Entry screen CTA options:**
- "Analyze My Style" → `vibeSelect` → camera permission → photo capture → analysis → account creation
- "Explore Without Scanning" → `home` directly (with vibe extra)
- "Already have a Fansivibe account? → Sign In" → `RouteNames.home`

**Account Creation Screen:**
- Fields: email, password, name (name is optional)
- CTA: "Create Account"
- Alternatives: "Maybe Later — Save Locally", Google/Apple social sign-in
- On save: `context.goNamed(RouteNames.home, extra: {'onboarding_complete': true, ...})`

**Issue:** Account creation is required to save any progress. The "Maybe Later" option saves locally but the data doesn't persist across app launches (no local storage integration beyond what `shared_preferences` provides). Users who skip account creation start fresh each time.

**Classification:** P0 — Account creation blocks value preservation. Principle C states account creation should preserve/protect value rather than unnecessarily block it. Users who complete analysis but don't create an account lose their results on relaunch.

---

## 7. Home Arrival Flow

**Path:** `HomeScreen` build method, conditional logic:

```dart
bool get _isFirstVisit => onboardingData != null;
bool get _hasAnalysis =>
    onboardingData?.containsKey('onboarding_complete') == true;
String? get _displayName => onboardingData?['display_name'] as String?;
String? get _vibeName => onboardingData?['vibe'] as String?;
```

**Three paths:**

1. **`_isFirstVisit && _hasAnalysis && UserSession.hasSavedWardrobeItem`** → `FirstTimeLightPathHomeScreen` (vibe-aware, analysis pending)
2. **`_isFirstVisit && _hasAnalysis`** → `FirstTimeHomeScreen` (displayName + Style DNA)
3. **`_isFirstVisit`** → `FirstTimeLightPathHomeScreen` (vibe only, no analysis yet)
4. **Else** → regular `HomeScreen` with mock data (TodaysLook, StyleScore, Quick Actions, etc.)

**Issue:** The home arrival logic depends on `onboardingData` map keys being set during account creation. The first-visit screens use extensive mock data (`_mockScore`, `_mockDna`, etc.) regardless of whether the user actually completed analysis. Returning users without `onboarding_data` see completely different content.

**Classification:** P1 — Home should reflect what Fansivibe already knows about the user (principle E), but currently shows generic mock data.

---

## 8. Returning-User Flow

**Path:** Depends on whether `onboardingData` is present in router extras.

**If `onboardingData` present** (returning user who completed onboarding):
- HomeScreen shows FirstTimeHomeScreen or FirstTimeLightPathHomeScreen based on analysis status
- Profile shows saved looks, style DNA, achievements (all mock data)
- Quick actions and tools are the same as new user

**If no `onboardingData`** (brand new or cleared data):
- HomeScreen shows regular HomeScreen with mock data
- No vibe direction, no personalized content

**Continuity issue:** The returning user flow is fragile. It depends on `onboardingData` being correctly passed through the GoRouter configuration. If the router state is lost or the app is reinstalled, the user starts completely over with no memory of previous interactions.

**Classification:** P2 — The flow attempts continuity but is not robust. Principle H states returning users should see continuity rather than starting over, but the current implementation requires perfect router state management.

---

## 9. Saved-Look Flow

**Path:** `ProfileScreen` → `_handleMenuAction(saved_looks)` → `SavedLooksScreen`

**SavedLooksScreen:**
- Shows count: `${looks.length} Saved Looks`
- Descriptor: "Your curated style collection"
- List of `SavedLookCard` widgets with hero transition, image, badge (score), title, subtitle (date), footer (items)

**Save mechanism:**
- Hairstyle: `HairstyleResultScreen._saveStyle` → `svc.saveLook(recommendation, title)` → `POST /v1/looks/saved`
- Grooming: `GroomingResultScreen._buildActions` → `service.saveGroomingLook(recommendation, title)` → `POST /v1/looks/saved`

**Issue:** Saved looks are stored in mock data (`ProfileMockData.savedLooks`) and have no persistent backend connection in the default code path. The backend API `POST /v1/looks/saved` exists and is correctly wired, but the default `HairstyleService` and `GroomingService` use in-memory storage.

**Classification:** P2 — The API exists and is correctly structured, but mock data blocks the journey. The saved-look hero cards and collection UI are visually complete but functionally disconnected from persistence.

---

## 10. Persistence/Memory Behavior

**Current mechanism:**
- `UserSession.hasSavedWardrobeItem` — static boolean, no persistence across launches
- `onboardingData` — passed via GoRouter extras, lost on app restart
- Backend: `POST /v1/looks/saved` with idempotency key, `GET /v1/users/me` for profile, `GET /v1/analysis/runs` for history
- No local storage integration for analysis results, vibe preferences, or capability state

**What is persisted (backend):**
- Saved looks with idempotency keys
- User profiles via `GET /v1/users/me`
- Analysis run history via `GET /v1/analysis/runs`
- Learning signals via `SaveRecommendation` use case

**What is NOT persisted (frontend):**
- Vibe selection (StyleVibe)
- Hairstyle/ grooming analysis results
- Style scores, DNA, capabilities across sessions
- Capability unlock state

**Classification:** P2 — Missing local persistence layer means users lose their state on app restart. The backend has the APIs but the frontend doesn't connect them to a persistent user session.

---

## Summary of Mismatches vs. Product Principles

| Principle | Classification | Issue |
|-----------|---------------|-------|
| A. First useful value should arrive quickly | P0 | Onboarding takes 8+ screen transitions before any value appears |
| B. Don't ask user for info system can infer | P1 | Grooming input asks for face shape/beard features that could be inferred from scan |
| C. Account creation should preserve value | P0 | "Create Account" blocks; "Maybe Later" doesn't preserve across launches |
| D. First successful recommendation feels like achievement | P1 | Recommendations presented as insights, not achievements |
| E. Home reflects what Fansivibe knows | P1 | Home shows mock data regardless of user's actual analysis |
| F. Saved actions become user memory | P2 | Saved looks are mock data, no persistence across sessions |
| G. Capability progression reflects understanding | P2 | Capability grid uses mock active/inactive state, not user data |
| H. Returning users see continuity | P1 | Continuity depends on fragile router state; lost on restart |

---

## Existing Reusable Components

| Component | Feature | Purpose |
|-----------|---------|---------|
| `fansi_button.dart` | shared | Primary/secondary/tertiary button variants |
| `fansi_error_view.dart` | shared | Error state display |
| `fansi_loading_view.dart` | shared | Loading state |
| `fansi_hero_card.dart` | shared | Hero-transition cards (saved looks) |
| `fansi_image_well.dart` | shared | Image display well with icon |
| `fansi_badge.dart` | shared | Score/label badge |
| `user_session.dart` | shared | Session flags (currently static, no persistence) |
| `onboarding_data.dart` | onboarding | OnboardingResult, StyleVibe, AiCapability models |
| `home_mock_data.dart` | home | TodaysLookData, StyleScoreData, QuickActionData, etc. |
| `profile_mock_data.dart` | profile | ProfileData, StylistLevelData, StyleProgressData, etc. |
| `hairstyle_mock_data.dart` | hairstyle | FaceScanCheck, HairstyleRecommendation, HairstyleAnalysisResult |
| `grooming_mock_data.dart` | grooming | GroomingCheck, GroomingRecommendation, GroomingAnalysisResult |

---

## Existing Backend APIs Supporting the Journey

| API | Method | Purpose |
|-----|--------|---------|
| `GET /v1/users/me` | users | Return authenticated user's profile with style profile |
| `POST /v1/analysis/hairstyle` | analysis | Submit hairstyle analysis, return `run_id` (202) |
| `GET /v1/analysis/runs/{run_id}` | analysis | Get analysis run status- `GET /v1/analysis/runs` | analysis | List user's analysis runs |
| `POST /v1/analysis/grooming` | analysis | Submit grooming analysis, return `run_id` (202) |
| `POST /v1/looks/saved` | looks | Save a recommendation with idempotency key; creates `look_saved` signal |
| `GET /v1/analysis/runs` | analysis | Paged run-history summaries |

**Missing APIs:** None identified that would block the desired journey. The backend has the necessary endpoints.

---

## Missing APIs

No backend APIs are missing. All endpoints needed for the core journey exist. The blocking issues are:

1. **Frontend→Backend connection:** Mock data is used by default; services write to in-memory storage
2. **Local persistence:** No local storage layer to cache analysis results between launches
3. **Router state management:** `onboardingData` depends on GoRouter extras being correctly set

---

## Screens Visually Complete but Functionally Disconnected

1. **HairstyleResultScreen** — Full UI with score, recommendations, save CTA; saves to mock service
2. **GroomingResultScreen** — Full UI with score, beard rec, eyewear, specs; saves to mock service
3. **SavedLooksScreen** — Visual hero cards with badge, title, subtitle, items; reads from mock data
4. **FirstTimeHomeScreen** — Polished visual design with mock score/DNA/palette
5. **FirstTimeLightPathHomeScreen** — Light-path variant for users who chose vibe but haven't scanned
6. **ProfileScreen** — Complete profile UI with achievements, style DNA, saved looks; all mock data

---

## Screens That Should NOT Be Changed

1. **SplashScreen** — Brand introduction, correct function
2. **EntryScreen** — Correct entry point with analyze/explore CTA
3. **Router configuration** (`app_router.dart`, `route_names.dart`) — Correct GoRouter setup
4. **Bottom navigation** (`router_shell.dart`) — Correct 5-tab shell
5. **Shared components** (`fansi_*`, `user_session.dart`) — Infrastructure, not UI flow
6. **Backend APIs** — Correctly implemented, should not be modified

---

## Screens Functionally Disconnected but Visually Complete

1. **HairstyleResultScreen** — UI complete, save falls back to mock
2. **GroomingResultScreen** — UI complete, save falls back to mock
3. **FirstTimeHomeScreen** — Visual polish, uses static mock data
4. **FirstTimeLightPathHomeScreen** — Visual polish, uses static mock data
5. **ProfileScreen** — Visual design, reads mock ProfileData
6. **SavedLooksScreen** — Visual hero cards, reads mock looks

These screens are functionally disconnected due to mock data, not due to UI issues. They should be preserved as-is for the audit; the target journey will define how to connect them.