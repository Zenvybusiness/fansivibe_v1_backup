# Fansivibe Current State

Last Updated: 2026-07-14
Updated By: opencode agent (pre-integration cleanup)

## Phase

Pre-integration cleanup complete. Shared component extraction, dead code removal,
score/icon centralization, mock data consistency fixes, and basic accessibility
added. All 5 primary screens and 11 sub-flows implemented with mock data.
No backend, AI, camera, authentication, or database integrations.

## Repository Facts

- **Flutter project at**: `newproject/flutter_application_1`
- **Dart files**: 51 (`lib/`) + 23 (`test/`)
- **Total lines**: ~19,981
- **Features**: 10 (`home`, `discover`, `stylist`, `wardrobe`, `outfit_scan`, `outfit_builder`, `hairstyle`, `grooming`, `events`, `profile`)
- **Mock data files**: 9 (`data/` directories across features)
- **Shared widgets**: 4 files (`shared/components/fansivibe_card.dart`, `shared/components/section_title.dart`, `shared/utils/score_colors.dart`, `shared/utils/icon_utils.dart`)
- **Theme files**: 2 (`fansivibe_colors.dart`, `fansivibe_theme.dart`)
- **No router package**: Raw `Navigator.of(context).push(MaterialPageRoute(...))` used everywhere
- **No state management**: All state is local `setState` in widgets
- **No domain layer**: No `domain/` directory in any feature
- **Accessibility**: Basic `Semantics` added to cards, buttons, images, navigation
- **No assets**: No images, fonts, or asset directories configured
- **No router**: SCREEN_MAP.md specifies "Use the existing approved routing approach" but no router is set up

## Implemented Screens

All screens from `docs/SCREEN_MAP.md`:
- MAIN: MainShell (5-tab bottom nav with IndexedStack)
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

## Missing Documented Screens

- HOME-002: DailyOutfitScreen — only SnackBar placeholder
- PROFILE-002: PreferencesScreen — only SnackBar placeholder
- PROFILE-003: SavedLooksScreen — only SnackBar placeholder
- PROFILE-004: SubscriptionScreen — only SnackBar placeholder
- PROFILE-005: SupportScreen — only SnackBar placeholder
- PROFILE-006: SettingsScreen — only SnackBar placeholder

## Cleanup Completed

The following pre-integration audit findings have been addressed:

1. **Cross-feature Profile→Home dependency**: `ProfileScreen` now imports
   `FansivibeCard` and `SectionTitle` from `shared/components/` instead of
   `home_widgets.dart`. `HomeCard` and `HomeSectionTitle` remain as backward-
   compatible typedefs in `home_widgets.dart`.

2. **Shared component extraction**: `FansivibeCard` and `SectionTitle` moved to
   `shared/components/`. `scoreColorFromDouble` and `iconFromName` moved to
   `shared/utils/`.

3. **Dead code removed**: `lib/app/foundation_screen.dart` deleted (confirmed
   unreachable). `DiscoverHeader`, `DiscoverTabs`, `DiscoverEmptyState`,
   `DiscoverLookCardSkeleton`, `DiscoverSearchField` (and private `_ShimmerEffect`,
   `_ShimmerLine`) removed from `discover_widgets.dart` (zero production references).

4. **Score-color centralization**: 3 identical `_scoreColor(double)` methods in
   outfit_builder, hairstyle, and grooming replaced with single
   `scoreColorFromDouble()` from `shared/utils/score_colors.dart`.

5. **Icon resolution centralization**: `AIInsightCard._getIconData`,
   `WardrobeInsightCard._getIconData`, and `CategoryFilterChip._getIconData`
   replaced with `iconFromName()` from `shared/utils/icon_utils.dart`.

6. **Event mock data consistency**: Added `UserEvent.typeById(String)` helper
   to find `EventType` from `mockTypes` by id. Inline `EventType` instances in
   `mockEvents` still use const constructors (identical at runtime); the helper
   enables future migration to reuse mock types.

7. **Basic accessibility**: `Semantics` with `button: true` added to
   `FansivibeCard` (when `onTap` set), `DiscoverCard` (when `onTap` set),
   `QuickActionCard`, `OutfitItemChip`, `DiscoverTabButton`, `DiscoverFilterChip`.
   `Semantics(label:)` on `MatchPercentageBadge` and `SectionTitle` action button.
   `Semantics(image: true)` on placeholder images in `TodaysLookCard` and `LookCard`.

## Validation

- `dart format lib test`: 77 files (3 changed)
- `flutter analyze`: **0 issues**
- `flutter test`: **All 266 tests passed**

## Git Status

```
 M CURRENT_STATE.md
 D lib/app/foundation_screen.dart
 M lib/features/discover/presentation/widgets/discover_widgets.dart
 M lib/features/events/data/event_mock_data.dart
 M lib/features/grooming/presentation/widgets/grooming_widgets.dart
 M lib/features/hairstyle/presentation/widgets/hairstyle_widgets.dart
 M lib/features/home/presentation/widgets/home_widgets.dart
 M lib/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart
 M lib/features/profile/presentation/profile_screen.dart
 M lib/features/wardrobe/presentation/widgets/wardrobe_widgets.dart
 M test/discover_widgets_test.dart
 M test/profile_screen_test.dart
?? lib/shared/components/
?? lib/shared/utils/
```

12 modified, 1 deleted, 2 untracked directories (4 new files in shared/).

## Remaining Audit Issues (Deferred)

1. **No router package**: Raw Navigator used everywhere (not in scope)
2. **No state management**: All state is local `setState` (not in scope)
3. **No domain layer**: No `domain/` directory in any feature (not in scope)
4. **5 missing documented screens**: All SnackBar placeholders (not in scope)
5. **Stylist string-switch dispatch**: Business logic in UI widgets (not in scope)
6. **Events → Outfit Builder boundary**: No cross-feature contract (not in scope)
7. **Outfit Scan score variant**: Uses different thresholds (0.9/0.8/0.7 nullable)
   vs central `scoreColorFromDouble` (0.9/0.7/0.5) — kept separate intentionally
8. **Discover `MatchPercentageBadge`**: Uses integer percentage thresholds
   (90/80/70) — kept separate intentionally
9. **`DiscoverSectionTitle`**: Structurally identical to `SectionTitle` but
   remains in discover_widgets.dart; only used in test file
10. **`WardrobeSectionTitle`**: Simplified variant without action button — kept
    in wardrobe feature for now

## Last Validation

Format: Passed (3 files modified by formatter).
Analysis: Passed (0 issues).
Tests: Passed (266 all passing).

## Handoff

New agents must:

1. Read `AGENTS.md`.
2. Read this file.
3. Inspect Git status and actual code.
4. Discover and read task-relevant skills.
5. Continue from repository reality.
