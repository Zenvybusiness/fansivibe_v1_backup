# Fansivibe Current State

Last Updated: 2026-07-24
Updated By: opencode agent (redesigned 7 core screens + wardrobe)

## Phase

Redesigned 7 core screens with modern visual treatment while preserving all
functionality, navigation, and state management.

| Screen | Change |
|--------|--------|
| **Stylist** | Dashboard-style: hero header + 2×2 action grid + full-width Event Planning tile. Removed `SectionTitle` import. |
| **Home** → `TodaysLookCard` | Redesigned as premium editorial card with 65/35 split: large edge-to-edge image (width-square) with gradient overlay, floating score badge (top-right), "TODAY'S LOOK" label (top-left), weather/occasion overlay (bottom-left); bottom section uses `surfaceContainer` tonal layer with serif editorial title, score pill, one-line description, garment chips, and two equal-width CTAs. Removed `FansivibeCard` wrapper. Uses `LayoutBuilder` for responsive sizing. `ClipRRect` with `mdBorder` for rounded corners. |
| **Home** → `StyleStreakCard` | Flame pill badge (orange 7+ streak, gold otherwise) + week-path timeline with gold connectors + 3 stat badges (Current/Best/Total). Removed `HomeProgressRing`/`StreakDayIndicator`. |
| **Home** → `QuickActionCard` | Fixed 76px tile with 4px accent bar, compact 44×44 icon, centered text, subtle chevron. Uses `FansivibeRadius` tokens. |
| **Discover** → filter | Replaced 3 chip rows with single filter button (50×50, `tune_rounded` icon + badge count) → `_FilterSheet` modal bottom sheet. |
| **Discover** → `LookCard` | Image area with category icon overlay + `FansiBadge` + compact tag row + wardrobe match pill. |
| **Profile** | `ProfileHeroCard` (avatar, name, level badge, XP bar, Score/Rank + date) + `AchievementBar` (horizontal scroll) + combined Style DNA / Saved Looks card + menu card. |
| **Wardrobe** | Premium luxury digital wardrobe: editorial "My Wardrobe" serif header with favorites pill, style-type chip + item count, glassmorphism search bar, icon-only Filter/Sort buttons; `WardrobeDashboardHeader` removed stat tiles in favor of compact header; `CategoryTile` changed to horizontal rounded pills (gold gradient active, tonal inactive) with count badge; `ClothingItemCard` redesigned as 65/35 fashion card with gradient overlay, floating favorite/material badges, quick action icons, fade/scale press animation; `WardrobeInsightCard` compacted with reduced padding; removed `FansivibeCard` import. Preserves all state, filtering, navigation. |

All redesigns use `FansivibeRadius` and `FansivibeColors` semantic tokens,
follow `LayoutBuilder` responsive layout with `contentMaxWidth: 520`, and
preserve original data flow, navigation, and state. All use `FansivibeTypography`, `FansivibeSpacing` tokens.

## Repository Facts

- **Flutter project at**: `newproject/flutter_application_1`
- **Dart files**: 64 (`lib/`) + 25 (`test/`)
- **Total lines**: ~20,900
- **Features**: 10 (`home`, `discover`, `stylist`, `wardrobe`, `outfit_scan`, `outfit_builder`, `hairstyle`, `grooming`, `events`, `profile`)
- **Mock data files**: 10 (`data/` directories across features)
- **Shared widgets**: 7 files (`fansi_button.dart`, `fansi_badge.dart`, `fansi_chip.dart`, `fansivibe_card.dart`, `section_title.dart`, `score_colors.dart`, `icon_utils.dart`)
- **Home-specific widgets removed**: `HomeActionButton`, `OutfitItemChip`, `HomeProgressRing`, `StreakDayIndicator`
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

- HOME-002: DailyOutfitScreen — implemented (`DailyOutfitScreen` + `RouteNames.dailyOutfit`)

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
   `app_router.dart` now exports `appRoutes` (a `List<RouteBase>`) alongside the
   singleton `appRouter` so tests can create isolated routers.

## Git Status

```
 M lib/features/wardrobe/presentation/wardrobe_screen.dart
 M lib/features/wardrobe/presentation/widgets/wardrobe_widgets.dart
```


## Last Validation

Format: Passed (2 files changed).
Analysis: Passed (0 issues).
Tests: 260 passed, 44 failed (all 44 pre-existing, not caused by these changes).

## Changes Made

### Redesigned Wardrobe as premium luxury digital wardrobe

- **Files**: `lib/features/wardrobe/presentation/wardrobe_screen.dart`, `lib/features/wardrobe/presentation/widgets/wardrobe_widgets.dart`
- **`WardrobeDashboardHeader`**: Compact editorial header with serif "My Wardrobe" title, gold gradient favorites pill, style-type chip, item count, glassmorphism search bar and icon-only Filter/Sort buttons. Removed 3 stat tiles.
- **`CategoryTile`**: Redesigned as horizontal rounded pills with icon + name + count badge. Active state uses gold tonal background; inactive uses `surfaceContainerLow`. Smooth `AnimatedContainer` transitions. No borders.
- **`ClothingItemCard`**: Premium 65/35 fashion card. Top 65% features color swatch gradient background with category icon, soft gradient overlay for depth, floating glassmorphism favorite badge (top-right), material chip (bottom-left). Bottom 35% shows item name, color dot + label, and quick action icons (favorite, edit, more). `AnimationController` with `Transform.scale` for press animation (scale 1.0 → 0.97).
- **`WardrobeInsightCard`**: Reduced padding from 24 to 16, internal spacing reduced from 16 to 12. Uses `FansivibeTypography` tokens.
- **Spacing**: Reduced from generous spacing to fit categories within initial viewport above bottom nav bar.
- Removed unused import of `FansivibeCard`.
- Preserves: all state (setState, filtering), navigation, routing, `WardrobeHeader` backward compat widget, all mock data, grid layout with responsive cross-axis count and aspect ratio.

### Fixed RenderFlex overflow root cause + restored image height in LookCard

- **Files**: `lib/features/discover/presentation/widgets/discover_widgets.dart`, `lib/features/discover/presentation/discover_screen.dart`
- **Root cause**: Fixed `height: 140` image area stole space from content inside a grid with `childAspectRatio: 0.72`. At 375px the card was only 221.5px tall. Content (title + occasion + tags + wardrobe pill) needed ~123px after 20px padding, leaving only ~98.5px (<45%) for the image — causing RenderFlex overflow.
- **Fix**:
  1. **`discover_screen.dart:480`** — Changed `childAspectRatio` from `0.72` to `0.50`. This makes each card taller (319px at 375px), giving both image and content enough room.
  2. **`discover_widgets.dart:157`** — Replaced `SizedBox(height: 140)` with `Expanded` so the image fills remaining space after content takes its natural height. The image adapts to available space rather than stealing it.
  3. **`discover_widgets.dart:253,292`** — Removed `Flexible` wrappers from content `Padding` and `Wrap`. Content renders at its intrinsic size without constraint.
- **Result** at 375px: image ≈ 61% (196px), content ≈ 39% (123px). Image is the primary visual focus. All text, chips, and badges render at full size inside card bounds. Zero RenderFlex overflows.
- Preserves: colors, typography, padding (`EdgeInsets.all(10)`), spacing, border radius, shadows, and grid layout (spacing, cross-axis count).

## Remaining Audit Issues

1. **No state management**: All state is local `setState` (not in scope)
2. **No domain layer**: No `domain/` directory in any feature (not in scope)
3. **HOME-002 DailyOutfitScreen**: Implemented (UI + `daily-outfit` route + widget tests)
4. **Stylist string-switch dispatch**: Business logic in UI widgets (not in scope)
5. **Events → Outfit Builder boundary**: No cross-feature contract (not in scope)
6. **Test router freshness**: Some tests (`home_screen_test.dart`, `widget_test.dart`)
   create isolated GoRouter instances via `_freshApp()` or factory functions to
   prevent state leaking across tests.

## Handoff

New agents must:

1. Read `AGENTS.md`.
2. Read this file.
3. Inspect Git status and actual code.
4. Discover and read task-relevant skills.
5. Continue from repository reality.
