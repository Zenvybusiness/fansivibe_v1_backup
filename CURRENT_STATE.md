# Fansivibe Current State

Last Updated: 2026-07-14
Updated By: opencode agent (profile destination screens)

## Phase

Profile destination screens implemented. 5 documented screens (PreferencesScreen,
SavedLooksScreen, SubscriptionScreen, SupportScreen, SettingsScreen) created with
go_router sub-routes under `/profile`. Profile menu actions now navigate via
`context.pushNamed()` instead of SnackBar. All 25 test files pass (306+ tests).
No backend, AI, camera, authentication, or database integrations.

## Repository Facts

- **Flutter project at**: `newproject/flutter_application_1`
- **Dart files**: 64 (`lib/`) + 25 (`test/`)
- **Total lines**: ~20,800
- **Features**: 10 (`home`, `discover`, `stylist`, `wardrobe`, `outfit_scan`, `outfit_builder`, `hairstyle`, `grooming`, `events`, `profile`)
- **Mock data files**: 10 (`data/` directories across features)
- **Shared widgets**: 4 files (`shared/components/fansivibe_card.dart`, `shared/components/section_title.dart`, `shared/utils/score_colors.dart`, `shared/utils/icon_utils.dart`)
- **Theme files**: 2 (`fansivibe_colors.dart`, `fansivibe_theme.dart`)
- **Router**: `go_router` 17.2.3 with `StatefulShellRoute.indexedStack`, named routes in `RouteNames`, centralized in `app_router.dart`
- **No state management**: All state is local `setState` in widgets
- **No domain layer**: No `domain/` directory in any feature
- **No assets**: No images, fonts, or asset directories configured

## Routing Architecture

- `lib/app/router/route_names.dart` — all route name string constants
- `lib/app/router/app_router.dart` — single `GoRouter` config with `StatefulShellRoute.indexedStack`
- `lib/app/router/router_shell.dart` — `RouterShell` widget wrapping `StatefulNavigationShell`
- `lib/app/app.dart` — uses `MaterialApp.router(routerConfig: appRouter)`
- `lib/app/main_shell.dart` — legacy shell (still present as fallback, not used by router)

5 branches: `/home`, `/discover`, `/stylist`, `/wardrobe`, `/profile`.
Sub-routes nested under `/stylist` and `/wardrobe` for all detail/scan/result screens.

Data passed via `state.extra` as typed objects or `Map<String, String>`.
Route builders null-check `state.extra` to handle GoRouter eager evaluation.

## Implemented Screens

All screens from `docs/SCREEN_MAP.md`:
- MAIN: MainShell (5-tab bottom nav with StatefulShellRoute.indexedStack)
- HOME-001: HomeScreen (greeting, Today's Look, Style Score, Quick Actions, Style Streak, AI Insight)
- DISCOVER-001: DiscoverScreen (search, filters, tabs, grid)
- DISCOVER-002: LookDetailsScreen (match score, reasons, ensemble, alternatives)
- STYLIST-001: StylistScreen (5 action cards)
- WARDROBE-001: WardrobeScreen (categories, item grid, add item)
- WARDROBE-002: AddWardrobeCategoryScreen
- WARDROBE-003: AddWardrobeItemScreen
- WARDROBE-004: WardrobeItemDetailsScreen
- SCAN-001: OutfitScanScreen
- SCAN-002: OutfitProcessingScreen
- SCAN-003: OutfitAnalysisScreen
- OUTFIT-001: BuildOutfitScreen
- OUTFIT-002: OutfitGenerationScreen
- OUTFIT-003: OutfitRecommendationScreen
- HAIR-001: FaceScanScreen
- HAIR-002: FaceProcessingScreen
- HAIR-003: HairstyleResultScreen
- HAIR-004: HairstyleDetailsScreen
- GROOM-001: GroomingInputScreen
- GROOM-002: GroomingProcessingScreen
- GROOM-003: GroomingResultScreen
- GROOM-004: GroomingDetailsScreen
- EVENT-001: EventListScreen
- EVENT-002: AddEventScreen
- EVENT-003: EventDetailsScreen
- PROFILE-001: ProfileScreen
- PROFILE-002: PreferencesScreen (style preferences with selectable option chips)
- PROFILE-003: SavedLooksScreen (list of saved looks with scores and items)
- PROFILE-004: SubscriptionScreen (Free/Premium/Elite plan cards)
- PROFILE-005: SupportScreen (help topics and contact card)
- PROFILE-006: SettingsScreen (toggles for notifications, sound, haptic, etc.)

## Missing Documented Screens

- HOME-002: DailyOutfitScreen — only SnackBar placeholder

## Migration Completed

1. **Router setup**: Added `go_router` 17.2.3 to `pubspec.yaml`. Created
   `lib/app/router/` with `app_router.dart`, `route_names.dart`, `router_shell.dart`.
2. **App entrypoint**: `lib/app/app.dart` switched from `MaterialApp(home: MainShell)`
   to `MaterialApp.router(routerConfig: appRouter)`.
3. **Navigation calls**: All `Navigator.push(MaterialPageRoute(...))` in 20+ screen files
   replaced with `context.pushNamed()`/`context.replaceNamed()`.
4. **Cross-feature imports removed**: `stylist_screen.dart` no longer imports 5 screen
   files; `event_details_screen.dart` no longer imports `build_outfit_screen.dart`.
5. **Test updates**: 7 test files updated to use `MaterialApp.router(routerConfig: ...)`
   wrappers for navigation tests.
6. **Route builder null safety**: All `state.extra as T` casts have null-safety fallbacks
   (returns `const SizedBox()` when extra is null) to handle GoRouter 17 eager evaluation.
7. **Test router freshness**: Navigation tests use factory functions returning fresh
   `GoRouter` instances to prevent state leaking across tests.

## Validation

- `dart format lib test`: 87 files (7 changed)
- `flutter analyze`: **2 warnings** (pre-existing unused imports)
- `flutter test`: **All 306+ tests passed**

## Git Status

```
 M CURRENT_STATE.md
 M lib/app/router/app_router.dart
 M lib/app/router/route_names.dart
 M lib/features/profile/presentation/profile_screen.dart
?? lib/features/profile/data/profile_mocks.dart
?? lib/features/profile/presentation/preferences_screen.dart
?? lib/features/profile/presentation/saved_looks_screen.dart
?? lib/features/profile/presentation/subscription_screen.dart
?? lib/features/profile/presentation/support_screen.dart
?? lib/features/profile/presentation/settings_screen.dart
?? test/profile_screens_test.dart
```

## Remaining Audit Issues

1. **No state management**: All state is local `setState` (not in scope)
2. **No domain layer**: No `domain/` directory in any feature (not in scope)
3. **HOME-002 DailyOutfitScreen**: Still only SnackBar placeholder (not in scope)
4. **Stylist string-switch dispatch**: Business logic in UI widgets (not in scope)
5. **Events → Outfit Builder boundary**: No cross-feature contract (not in scope)
6. **2 pre-existing unused imports**: in `grooming_details_screen.dart` and
   `hairstyle_details_screen.dart`

## Last Validation

Format: Passed (7 files modified by formatter).
Analysis: Passed (2 pre-existing unused_import warnings only).
Tests: Passed (306+ all passing).

## Handoff

New agents must:

1. Read `AGENTS.md`.
2. Read this file.
3. Inspect Git status and actual code.
4. Discover and read task-relevant skills.
5. Continue from repository reality.
