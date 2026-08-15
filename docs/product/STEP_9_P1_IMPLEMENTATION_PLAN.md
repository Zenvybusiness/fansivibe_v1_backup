# STEP 9 — P1 Implementation Plan

## P1 Issues to Implement (4 issues identified)

Based on the gap analysis in STEP_9_CORE_USER_JOURNEY_REPORT.md, the following P1 issues require implementation. Note: P0-3 already addressed "Vibe selection required before scanning," leaving 3 P1 issues to implement.

---

### P1-1: Home shows mock data regardless of user's actual analysis

| # | Description |
|---|-------------|
| **Issue** | Home screen and first-time home screens display generic mock data (`_mockScore`, `_mockDna`, `_mockPalette`) regardless of the user's actual analysis results. Home should reflect what Fansivibe already knows about the user (principle E). |
| **Current behavior** | `HomeScreen.build` uses `onboardingData` map keys to determine first-visit path. When onboarding data is present, `FirstTimeHomeScreen` or `FirstTimeLightPathHomeScreen` render with static mock data (`_mockScore`, `_mockDna`, `_mockPalette`). When no onboarding data, `HomeScreen` renders with generic mock data. |
| **Target behavior** | Home screens connect to backend data via `GET /v1/users/me` and `GET /v1/analysis/runs` to display the user's actual insights, style DNA, color palette, and saved looks. Mock data serves only as fallback when backend data is unavailable. |
| **Exact files/components affected** | - `lib/features/home/presentation/screens/home_screen.dart`<br>- `lib/features/home/presentation/screens/first_time_home_screen.dart`<br>- `lib/features/home/presentation/screens/first_time_light_path_home_screen.dart` |
| **Existing code/services that can be reused** | - `GET /v1/users/me` endpoint — returns user profile with style profile<br>- `GET /v1/analysis/runs` endpoint — returns user's analysis run history<br>- `UserSession` and `LocalStorage` — already persisting session state from P0 implementation<br>- `HairstyleService` and `GroomingService` — injectable services that can fetch analysis results<br>- `fansi_*` shared components — reused for data display |
| **UI change required?** | Yes — connect existing UI components to backend data sources instead of using mock data directly. Preserve existing layout, typography, colors, spacing, and card design. |
| **Backend change required?** | No. All necessary endpoints exist (`GET /v1/users/me`, `GET /v1/analysis/runs`). Only frontend connection needed. |
| **Database change required?** | No. Database schemas are complete (`users`, `analysis_runs`, `saved_looks`). |
| **Test impact** | Update existing home screen tests to verify backend data display. Add tests for mock data fallback behavior. |
| **Risk** | Medium — changing data source from mock to backend could affect screen layout if data shapes differ. Mock data preserved as fallback. Incremental change per screen. |

---

### P1-2: Returning user continuity depends on fragile router state

| # | Description |
|---|-------------|
| **Issue** | Returning user flow depends on `onboardingData` being correctly passed through GoRouter extras. If the router state is lost or the app is reinstalled, the user starts completely over with no memory of previous interactions. This violates principle H (returning users should see continuity). |
| **Current behavior** | `onboardingData` is passed via GoRouter extras (`context.goNamed(RouteNames.home, extra: {'onboarding_complete': true, ...})`). On app restart, router extras are lost unless manually persisted. `UserSession.hasSavedWardrobeItem` is a static boolean with no persistence. |
| **Target behavior** | `onboardingData` and key session state are preserved across app launches via local storage. On app launch, the app recognizes returning users and restores their state (analysis results, vibe selection, saved looks) without requiring re-onboarding. Home reflects previous state automatically. |
| **Exact files/components affected** | - `lib/shared/utils/local_storage.dart` — extend persistence coverage<br>- `lib/shared/utils/user_session.dart` — enhance from LocalStorage<br>- `lib/app/app.dart` — ensure LocalStorage initialized on startup<br>- GoRouter configuration — add fallback logic for missing/invalid onboardingData |
| **Existing code/services that can be reused** | - `LocalStorage` class from P0 implementation — already wraps `shared_preferences`<br>- `UserSession` — already updated to use LocalStorage<br>- GoRouter configuration (`app_router.dart`, `route_names.dart`) — only needs fallback logic addition<br>- Existing `onboardingData` model — `OnboardingResult`, `StyleVibe`, etc. |
| **UI change required?** | Minimal — primarily backend data connectivity and state management. UI screens already designed to conditionalize on `onboardingData` presence. |
| **Backend change required?** | No. All necessary endpoints exist. Local storage addition is frontend-only. |
| **Database change required?** | No. Existing database schemas sufficient. Local storage complements backend persistence. |
| **Test impact** | Add tests for local persistence save/retrieve across launches. Add tests for returning user flow: launch → restore state → home reflects previous data. |
| **Risk** | Medium — local storage layer is new code path; must ensure backward compatibility with existing persisted state. Fallback to router extras when local storage empty. |

---

### P1-3: Grooming input asks user for inferable data

| # | Description |
|---|-------------|
| **Issue** | `GroomingInputScreen` requires user to select all 4 feature groups (face shape, beard style, density, color) before "Analyze Style" is enabled. The system could potentially infer these from a camera scan, violating principle B (don't ask user for information the system can reasonably infer). |
| **Current behavior** | `GroomingInputScreen` has 4 option groups that must all be selected before the analyze CTA is enabled. Users must make 4 separate selections, even though the AI could infer face shape, beard style, etc. from a prior scan. |
| **Target behavior** | Vibe selection and grooming features are optional before analysis. User can proceed directly to analysis (camera scan), and the system infers what it can from the photo. If the user previously selected grooming features, those are preserved; otherwise, the system defaults to "Open to Everything" and tunes recommendations after the first analysis. |
| **Exact files/components affected** | - `lib/features/grooming/presentation/screens/grooming_input_screen.dart`<br>- `lib/features/grooming/presentation/screens/grooming_result_screen.dart` |
| **Existing code/services that can be reused** | - `GroomingService` — already injectable, supports learning repository attachment<br>- `VibeSelectScreen` from P0 — made vibe selection optional with `vibeRequired=false`<br>- `HairstyleService` — similar pattern; hair analysis works without pre-selection<br>- `StyleVibe` model — already defined and reused<br>- Camera/photo infrastructure — can provide data for inference |
| **UI change required?** | Yes — make feature selection optional in `GroomingInputScreen`. When all features are unselected, "Analyze" is still enabled with "Open to Everything" default. Preserve existing card design and layout. |
| **Backend change required?** | No. Backend `POST /v1/analysis/grooming` does not require the 4 feature groups as mandatory fields. |
| **Database change required?** | No. Existing schemas sufficient. |
| **Test impact** | Update grooming input screen tests to verify optional selection flow. Add tests for analyze-without-full-selection path. |
| **Risk** | Low — making selections optional is a UI reflow; existing backend API already handles partial data. "Open to Everything" default preserves existing behavior when no features selected. |

---

## Implementation Order

1. **P1-1**: Connect Home screens to backend data (3 screens)
2. **P1-2**: Enhance local persistence for returning user continuity
3. **P1-3**: Make grooming input features optional

Each P1 issue is implemented independently, with verification after each change.