# Fansivibe Current State

Last Updated: 2026-08-05
Updated By: opencode agent

## Changes Made — Nav Bar: Icon + Label Glow Only (no background pill)

Task: in the bottom `NavigationBar`, only the selected icon and its label
should glow on tab switch — the tinted background indicator pill must not.

- `lib/app/router/router_shell.dart` — `indicatorColor` changed from
  `theme.colorScheme.primaryContainer` to `Colors.transparent` (removes the
  background glow pill). Destinations now use a new `_GlowingIcon` widget that
  renders the icon glyph as `Text` (MaterialIcons font) with a gold glow
  (`Shadow` blur 8 + 16, `FansivibeColors.primary` at 0.75/0.4 alpha) on the
  `selectedIcon` only; unselected icons keep the muted `secondary` color.
- `lib/shared/theme/fansivibe_theme.dart` — nav bar `indicatorColor` set to
  `Colors.transparent`; `labelTextStyle` now resolves per state: selected label
  gets the gold `primary` color with glow shadows (blur 6 + 12); unselected
  keeps muted `secondary`. `iconTheme` unchanged.
- Nothing else changed — navigation, labels, ordering, behavior all intact.

**Validation**
- `dart format`: passed
- `flutter analyze`: 0 errors, 7 pre-existing infos (all in untouched files)
- `flutter test`: **331 passed, 0 failed**

## Changes Made — Sticky "Add Item to Wardrobe" Button

`lib/features/wardrobe/presentation/wardrobe_screen.dart` — the "Add Item to
Wardrobe" button now stays pinned to the bottom of the screen while the
wardrobe list scrolls. Moved from the end of the scroll content into a
`Scaffold.bottomNavigationBar` (`SafeArea` + `Container` + `Center(heightFactor: 1)`
+ `ConstrainedBox(maxWidth)`) so it reuses the same `FansiButton.primary` and
matches the responsive 520px content width on wide screens. The button no longer
sits at the bottom of the list.

Bug fixed during validation: the initial `Center` (no `heightFactor`) expanded to
the full available height (520px), collapsing the scroll viewport to zero height
and making the whole list non-tappable — added `heightFactor: 1` to shrink-wrap
the bar.

**Tests:** `test/wardrobe_screen_test.dart` — 3 tests that tapped content now
positioned under the sticky bar (Tops category tile, View Analysis, first grid
item) were switched from `scrollUntilVisible` to `ensureVisible` before tapping.

**Validation**
- `dart format`: passed
- `flutter analyze` (wardrobe screen + test): 0 issues
- `flutter test`: **331 passed, 0 failed**

## Changes Made — Chat Bot (Assistant) Bug Fixes

Task: fix chat bot issues. No failing tests existed; the fixes target real
runtime/logic bugs found by review.

1. **Dispose crash guard** (`assistant/domain/assistant_service.dart`):
   Navigating away while a reply was in-flight disposed the owned service,
   then `send()`'s continuation called `notifyListeners()` on a disposed
   `ChangeNotifier` → debug assertion (`A ChangeNotifier was used after being
   disposed`). Added `_disposed` flag, `_safeNotify()`, and an early return
   after the await; `dispose()` now marks it before closing the HTTP client.
2. **Offline per-occasion outfit cards** (`assistant/data/offline_assistant.dart`):
   `_outfit()` reused `OutfitRecommendation.mock` for every occasion, so "date"
   produced the *Date Night Refined* title but listed the office components
   (Navy Blazer etc.) under it. Replaced with a `_LookCard` per-occasion map
   mirroring `backend/app/data/catalog.py` (office/date/party/travel/casual
   each with matching items + score). Dropped the now-unused
   `outfit_builder_mock_data.dart` import.
3. **Offline `thanks` intent** (`offline_assistant.dart`): "thanks"/"thank"/
   "thx" fell through to `_help()` offline while the backend returned
   `INTENT_THANKS`. Added a thanks branch for online/offline parity.
4. **Chat navigation crash (the reported bug)** (`assistant/presentation/assistant_screen.dart`):
   Tapping the bot's "Open"/navigation button from the assistant (pushed on
   top of the shell) used `context.pushNamed(...)`. Because the target routes
   live inside the `StatefulShellRoute`, go_router duplicated the shell page
   key → `'!keyReservation.contains(key)'` assertion → red error screen / crash.
   Reproduced with a shell→FAB→assistant→navigate widget test; confirmed for
   every target (wardrobe, discover, stylist, profile, today, hairstyle,
   grooming, build-outfit, home). Fixed by using `context.goNamed(...)`, which
   replaces the navigation stack and reuses the shell page — no key duplication.
   Verified all 9 targets navigate with zero exceptions.

**New tests:** `test/offline_assistant_test.dart` (8 cases — greeting, thanks,
office/date/party/travel card contents, ambiguous-outfit clarification) and a
regression test in `test/assistant_screen_test.dart` asserting shell-mounted
chat navigation no longer throws.

**Validation**
- `dart format`: passed
- `flutter analyze`: 0 errors, 7 pre-existing infos (all in untouched files)
- `flutter test`: **331 passed, 0 failed** (was 324; +8 offline assistant tests
  +1 navigation regression test)
- backend `pytest`: **19 passed, 0 failed**

## Changes Made — RenderFlex Overflow Hardening (all screens)

Eliminated all `RenderFlex overflowed` layout errors across every screen at
small viewport + large text scale. Verified with a temporary smoke harness
(41 screens, 320x480, DPR 1.0, text scale 1.5, 6x300px scrolls, asserts no
layout exception) that iterated failures down to 0 before being removed.

Patterns applied (keep for future screens):
- Row children → `Flexible` + `maxLines: 1` + `TextOverflow.ellipsis`.
- Fixed-height cards → content wrapped in `Expanded`; inner text `Flexible`.
- Non-flex siblings of a `Row` are measured with unbounded width — wrap the
  widget itself in `Flexible` (e.g. `home_widgets.dart` streak pill, which
  overflowed 88px because its own `Flexible` never received bounded width).
- Do NOT put `Flexible`/`Expanded` inside a `FittedBox` (unbounded-width
  layout error); prefer `FittedBox(fit: scaleDown)` around fixed-height
  content Columns without flex children.
- Icon+label pills / tags → keep label in `Flexible`.
- Long inline rows (profile stats, progress, list tiles, plan cards,
  eyebrow/eyewear recommendation headers) → wrap text in `Flexible`.

Screens touched:
- `onboarding/`: `your_analysis_screen.dart` (score FittedBox + subtitle
  Row), `account_creation_screen.dart` (social buttons + "or continue with"
  divider), `ai_capability_icon.dart`, `color_palette_display.dart`
  (horizontal scroll for swatches)
- `home/`: `home_widgets.dart` (streak pill + quick action + style score),
  `daily_outfit_screen.dart` (component/alternative cards, CTA)
- `discover/`: `discover_widgets.dart` (LookCard bottom content)
- `outfit_scan/`: `outfit_scan_widgets.dart` (category text now `Flexible`)
- `outfit_builder/`: `outfit_generation_screen.dart` (preference chips
  Row→Wrap), `outfit_builder_widgets.dart`
- `grooming/` + `hairstyle/`: result screens (profile rows, eyebrow
  recommendation header)
- `profile/`: `profile_widgets.dart` (level, stats, progress, achievements,
  saved-look tiles), `subscription_screen.dart` (plan card)
- `events/`: `event_details_screen.dart` (`_infoRow` in `Expanded`)
- `wardrobe/`: widgets, add/with category, item details
- `shared/components/fansi_chip.dart`

Note: a temporary `test/_screen_smoke_test.dart` was used to drive this and
has been deleted after success. Mock data labels (e.g. "Casual"/"Regular")
vs lowercase option ids was a smoke-only concern, not a product bug.

**Validation**
- `flutter analyze`: 0 errors, 7 pre-existing infos (untouched files)
- `flutter test`: **324 passed, 0 failed**

## Changes Made — Learning Signals Wired Into Other Surfaces

Phase 2 of the gradual-learning engine: the model now "learns" from real
user actions across the app, not just the wardrobe and assistant.

- `add_event_screen.dart` — adding an event records `addPreferredOccasion`
  with the chosen `EventType.name` (Casual / Formal / Business / Date Night /
  Party / Travel / Workout / Other).
- `look_details_screen.dart` — `Save Look` records `addSavedLook(look.title)`.
- `daily_outfit_screen.dart` — `Save Look` records `addSavedLook` with the
  Today's Look title (`DailyOutfitData.mock.title`).
- `outfit_analysis_screen.dart` — `Generate Look` ("Look saved to wardrobe")
  records `addSavedLook` with the analysis title.

Each surface calls `LearningService.instance` (the existing cross-feature
pattern from `wardrobe_screen.dart`). `LocalStore` already swallows
persistence errors, so the writes degrade gracefully in headless tests.

**New test:** `look_details_screen_test.dart` — "records a learning signal
when saving a look" verifies `savedLooks` and the `look_saved` signal.

**Validation**
- `flutter analyze`: 0 errors, 7 pre-existing infos (untouched files)
- `flutter test`: **324 passed, 0 failed**

## Changes Made — AI Assistant, Learning Engine & Backend

Task: Fansivibe's "own AI" — server-side FastAPI orchestration (Ollama,
default `llama3.1:8b`) + Flutter chat surface + gradual-learning engine
(on-device user model, evolving wardrobe, grounded recommendations), with
offline rules fallback for low-end devices.

### Backend (`backend/`, new FastAPI service)
- `app/main.py` — `/health` + `/v1/assistant/chat` (async, wraps engine)
- `app/ai/engine.py` — own orchestration: intent → tools → dialogue → typed reply
- `app/ai/intent.py` — deterministic rules classifier + occasion detector
- `app/ai/tools.py` — recommendation tools grounded in user context (wardrobe)
- `app/ai/llm_backend.py` — optional Ollama enrichment (server-side only,
  never on client); engine falls back to rules when unavailable
- `app/data/catalog.py` — mock catalog mirroring Flutter mocks
- `app/models/schemas.py` — `AssistantReply`, `SuggestionCard`,
  `ClarificationOption`, `NavigationRequest`, `UserContext` (mirrors Flutter DTOs)
- `requirements.txt`, `docker-compose.yml`, `README.md`
- **19 tests passing** (intent, engine routing, clarification policy,
  wardrobe grounding, bare-occasion reply)

### Client — `assistant/` feature
- `data/models.dart` — DTOs mirroring backend schemas
- `data/assistant_client.dart` — HTTP client (`ASSISTANT_BASE_URL` dart-define,
  12s timeout)
- `data/offline_assistant.dart` — deterministic rules fallback (greeting,
  navigate, outfit/occasion, hairstyle, grooming, wardrobe), grounded in
  mock data; bare occasion replies (e.g. "date") resolve to outfit cards
- `domain/assistant_service.dart` — `ChangeNotifier`; attaches LearningService
- `presentation/assistant_screen.dart` — chat UI, injectable service,
  scrollable empty state (overflow-safe), suggestion prompts
- `presentation/assistant_routes.dart` — action → route mapping
- `presentation/widgets/assistant_widgets.dart` — bubbles, SuggestionCardView,
  chips, nav button, typing dots

### Client — `learning/` feature (gradual-learning engine)
- `data/models.dart` — `WardrobeEntry`/`FaceProfile`/`LearningSignal`/`UserModel`
- `data/local_store.dart` — SharedPreferences JSON persistence
- `domain/learning_service.dart` — `ChangeNotifier` singleton, 24-item seeded
  wardrobe, signals, styleScore; `@visibleForTesting resetForTest()`
- `learning_repository.dart` — public contract (architecture decoupled)

### Routing & integration
- `/assistant` GoRoute + `RouteNames.assistant`; `FloatingAssistantButton`
  in `router_shell.dart`; Stylist hero card opens Assistant
- Wardrobe reads from `LearningService.instance.wardrobe` (listener + add)
- Tests: `assistant_screen_test.dart` (6), `learning_service_test.dart`

### Validation
- `flutter analyze`: 0 errors, 7 pre-existing infos (untouched files only)
- `flutter test`: **323 passed, 0 failed**
- backend `pytest`: **19 passed, 0 failed**
- Fixed 3 pre-existing `widget_test.dart` navigation tests broken by the new
  Stylist assistant hero card pushing cards below the fold: switched to
  `tester.ensureVisible` before tapping the Hairstyle / Event Planning /
  Beard / Glasses cards.

## Changes Made — Design Consistency Pass (professional UI/UX)

Full-design audit followed by a token-consistency migration. All changes are
visual-only; no behavior, data, navigation, or text changed.

### 1. Semantic colors enforced (rule violations fixed)
- **Removed forbidden Material blue/purple** (`#2196F3`, `#9C27B0`) →
  `FansivibeColors.accentGold` (informational accent) in `grooming_details_screen.dart`,
  `grooming_result_screen.dart`, `hairstyle_details_screen.dart`,
  `outfit_recommendation_screen.dart`. Per DESIGN.md: "Don't use Material blue."
- **New tokens** in `fansivibe_colors.dart`: `successContainer` (#2E7D32),
  `onSuccessContainer` (#81C784). Replaced all hardcoded event greens in
  `events_widgets.dart` + `event_details_screen.dart`.
- **Raw semantic greens → tokens**: `0xFF4CAF50` → `FansivibeColors.success` in 4
  processing screens (`outfit_processing`, `outfit_generation`, `face_processing`,
  `grooming_processing`).
- Retained deliberate content colors: stylist feature tints, streak flame orange,
  vibe gradients (now shared), garment/palette swatches.

### 2. Radius scale completed + migrated
- Added missing steps to `fansivibe_radius.dart`: `xs` (4), `smd` (12), `base` (16).
- Migrated **all** raw `BorderRadius.circular(...)` (163 spots across ~40 files) to
  tokens: tiny→`xs`, 8→`sm`, 10/12/14→`smd`, 16/20→`base`, 24→`md`, 32→`lg`, 90→`full`.
- Added `fansivibe_radius.dart` imports to 29 files that now use tokens.

### 3. Vibe gradient de-duplicated (single source of truth)
- New `vibeGradientColors` map in `onboarding_data.dart`; both `vibe_select_screen.dart`
  and `first_time_light_path_home_screen.dart` now reference it (removed duplicated
  color pairs + dead `_VibeVisual`/`_VibeMotif` classes).

### 4. No-Line rule applied (tonal layering)
Converted accent-tinted bordered cards on `surface` → tonal `surfaceContainerLow`
lifts (boundary via colour shift, not lines) in grooming, hairstyle, outfit_builder,
outfit_scan, discover, profile, wardrobe, and events screens. Removed drop shadows
from card surfaces (kept brand-tinted glow on the hero in `first_time_home_screen`).
Interactive ghost borders (selection chips, input fields, medallion rings, camera
guides) intentionally preserved per DESIGN.md accessibility rule. `Border.all`
usage: 88 → 58.

**Validation**
- `dart format`: passed
- `flutter analyze`: 0 errors, 7 pre-existing infos (all in untouched files)
- `flutter test`: **311 passed, 0 failed**

**Files changed:** `shared/theme/fansivibe_colors.dart`, `shared/theme/fansivibe_radius.dart`,
`shared/theme/fansivibe_theme.dart` (unchanged), `features/onboarding/data/onboarding_data.dart`,
`features/onboarding/presentation/screens/vibe_select_screen.dart`,
`features/home/presentation/first_time_light_path_home_screen.dart`, plus ~40 screen/widget
files across events, grooming, hairstyle, outfit_builder, outfit_scan, discover, profile,
wardrobe for radius + tonal-layering migration.

## Changes Made — Today's Look Screen Redesign (faithful Digital Atelier)

### Modified: `newproject/flutter_application_1/lib/features/home/presentation/daily_outfit_screen.dart`

Creative redesign of the Today's Look screen to follow `DESIGN.md` (The Digital
Atelier) more strictly. **No functionality, data, navigation, or text strings
changed** — only visual treatment.

**Design changes (per DESIGN.md):**
- **No-Line Rule**: removed every `Border.all(...)`. All separation now via
  tonal layers and glass — no 1px lines anywhere.
- **Glass recipe**: floating elements (back button, score pill, Confidence
  Boost pill) now use the spec'd `surfaceContainerLow` @ 70% + **20px** blur
  (was 8px + borders).
- **Garment-tag chips**: metadata (occasion, weather, AI NOTE, category tabs,
  alt scores) are now solid `surfaceContainerHighest` @ `sm` radius label
  tags.
- **Editorial hero overlap**: large serif "TODAY'S LOOK" headline now overlaps
  an asymmetric outfit photo panel that bleeds off the right edge (photo
  overlaps a display heading per "Do overlap elements").
- **Signature CTA gradient**: "Wear This Look" uses `primary` → `primaryContainer`
  at 135° (gold metallic weight), full radius.
- **Tertiary editorial links**: "See Details" and "Share" converted from
  outlined buttons to gold underlined text links.
- **Section headers**: gold hairline rule + serif title + letter-spaced gold
  subtitle. Editorial label "THE DAILY EDIT" added to the summary.
- **Cards**: tonal `surfaceContainerLow` with `md`/`lg` radius, color-tinted
  gradient image wells, no shadows.

**Validation**
- `dart format`: passed
- `flutter analyze`: 0 errors, 7 pre-existing infos (all in untouched
  `outfit_scan`/`outfit_analysis` files)
- `flutter test`: **311 passed, 0 failed** (all 23 daily_outfit tests green)

## Changes Made — UX/Flow Bug Fixes and Full Test Suite Now Green

Task: fix user-experience/user-flow issues = fix real app bugs + sync stale
tests to the current (onboarding-first, redesigned) UX. Suite went from
**87 failing / 220 passing** to **0 failing / 311 passing**.

**Real app bugs fixed:**
1. `lib/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart`
   — Replace `FansiButton.secondary` inside a `Row` defaulted to `expanded: true`
   → `SizedBox(width: double.infinity)` → "BoxConstraints forces an infinite
   width" crash on the OutfitRecommendationScreen flow. Fixed with
   `expanded: false`. (Other in-Row buttons already used `expanded: false`.)
2. `lib/features/profile/presentation/support_screen.dart` — the contact
   `ListTile` sat inside a `FansivibeCard` (DecoratedBox with a background),
   tripping the "ListTile background color or ink splashes may be invisible"
   debug assertion (crash in debug builds). Wrapped the ListTile in its own
   `Material(color: Colors.transparent)`.

**Test sync to current UX (all stale expectations updated):**
- Introduced `_freshApp()` helper (`FansivibeApp(router: GoRouter(initialLocation:
  '/home', routes: appRoutes))`) so suite-level tests boot directly into the main
  shell instead of the onboarding Entry screen: `test/widget_test.dart`,
  `test/home_screen_test.dart` (pattern already existed in `home_screen_test.dart`).
- Label/icon updates: `'Start Scan'`→`'Scan Face'` (+`Icons.face_retouching_natural`),
  `'Analyze Features'`→`'Analyze Style'`, `'Capture Look'`→`'View Analysis'`
  (+`Icons.dashboard_rounded`), `'Gallery'/'Switch Camera'`→`'Share'/'Rescan'`,
  `'Scan Again'`→`'Save'` + `'Save Look'`→`'Generate Look'` (outfit analysis),
  `'Scan Again'`→`'Try Another'` + `'Save to Profile'`→`'Save Style'`,
  `'Start Over'`→`'Try Another'` + `'Save Recommendation'`→`'Save Look'`,
  `'Save to Profile'`→`'Try This Style'`, `'Save Recommendation'`→`'Try This Look'`,
  `'Build My Outfit'`→`'Build Outfit'` (app bar + button → `findsNWidgets(2)`),
  `'Wear This Look'/'Save Look'`→`'Save Outfit'/'Regenerate'`.
- Discover: `'OCCASION'` section → current `'For You'`/`'Trending'` tabs.
- Home: dropped static `'Monday, January 13'` expectation (date is now dynamic
  via `_formatDate()`); Daily Outfit navigation marker `'Daily Outfit'`→`"TODAY'S LOOK"`;
  Build Outfit marker `findsOneWidget`→`findsNWidgets(2)`.
- SavedLooks scores: `'87'`/`'91'` → `'87%'`/`'91%'` (FansiBadge renders `%`).
- Events: `Icons.add_rounded` now appears twice (app-bar action + "Add event"
  button) → `findsNWidgets(2)` / `.first` for tap.
- Wardrobe: stale `'Categories'` section expectations → `find.byType(CategoryTile)`.
- OutfitAnalysis action test reworked: `'Generate Look'` shows the
  "Look saved to wardrobe" snackbar (replaces the removed "Scan Again pops").

**Validation**
- `dart format`: passed (27 files formatted, 2 changed)
- `flutter analyze`: 0 errors, 7 pre-existing infos (all in untouched files:
  `app_router.dart`, `outfit_analysis_screen.dart`, `outfit_scan_screen.dart`)
- `flutter test`: **311 passed, 0 failed** (was 220/87)

**Files changed:** `lib/features/outfit_builder/presentation/widgets/outfit_builder_widgets.dart`,
`lib/features/profile/presentation/support_screen.dart`, and 15 test files
(`widget_test.dart`, `home_screen_test.dart`, `discover_screen_test.dart`,
`profile_screen_test.dart`, `wardrobe_screen_test.dart`, `outfit_builder_screens_test.dart`,
`outfit_scan_screen_test.dart`, `outfit_analysis_screen_test.dart`,
`hairstyle_result_screen_test.dart`, `hairstyle_details_screen_test.dart`,
`grooming_input_screen_test.dart`, `grooming_result_screen_test.dart`,
`grooming_details_screen_test.dart`, `hairstyle_scan_screen_test.dart`,
`event_screens_test.dart`).

## Changes Made — New-User Home Shows Light-Path Screen After Saving an Item

After a new user completes onboarding (account created) and then saves a
wardrobe item, the Home tab now shows the light-path first-visit screen
(`FirstTimeLightPathHomeScreen`) instead of the score/DNA first-time screen
(`FirstTimeHomeScreen`). Everything else untouched.

**New file:** `lib/shared/utils/user_session.dart`
- `UserSession.hasSavedWardrobeItem` — session-scoped flag (no persistence or
  state management exists in the app; simple shared flag is the existing
  cross-feature contract style).

**Modified:** `lib/features/wardrobe/presentation/wardrobe_screen.dart`
- `_handleAddItem` sets `UserSession.hasSavedWardrobeItem = true` when an item
  is added.

**Modified:** `lib/features/home/presentation/home_screen.dart`
- New branch: `_isFirstVisit && _hasAnalysis && UserSession.hasSavedWardrobeItem`
  → `FirstTimeLightPathHomeScreen` (reuses the exact light-path screen).
- Returning users and light-path first visits are unchanged.

**Validation**
- `flutter analyze lib`: 0 errors, 7 pre-existing infos (all in untouched
  `outfit_scan_screen.dart`)
- `dart format`: passed
- Tests (home + wardrobe + light-path files): 43 passed / 20 failed — identical
  to the pre-change baseline (verified via `git stash`), 0 regressions

## Changes Made — Entry Screen Account Gate Trim

### Modified: `lib/features/onboarding/presentation/screens/entry_screen.dart`

Removed the "Continue as New User" ghost button from the `_AccountGate`. The
gate now shows only the "Sign In" button (full-width) under the "Already have a
Fansivibe account?" prompt. Dropped the now-unused `onNewUser` callback and its
`_onAnalyze` wiring. Nothing else changed — CTAs, routing, and behavior intact.

**Validation**
- `flutter analyze` (entry_screen.dart): 0 issues
- No test references the removed button; no entry_screen_test.dart exists

## Changes Made — Professional Light-Path First-Visit Home

Replaced the placeholder light-path first-visit state (scattered prompt card +
leaked placeholder score) with a dedicated, editorial first-visit screen for new
users who chose "Explore Without Scanning" and picked a style.

**New file:** `lib/features/home/presentation/first_time_light_path_home_screen.dart`

Sections (staggered reveal, 2s, `easeOutCubic`):
1. **Hero header** — gold eyebrow "WELCOME TO FANSIVIBE", serif headline "Your
   style journey begins today.", value line.
2. **Style Direction card** — acknowledges the chosen vibe (serif label,
   description, per-vibe motif icon/gradient). Skip state shows "Open to
   Everything". First time the selected vibe is actually surfaced.
3. **Analysis pending card** — replaces the fake Style Score. Camera ring icon,
   "YOUR ANALYSIS IS WAITING", primary CTA **Analyze My Style** → camera
   permission + tertiary "Explore looks while you wait" → Discover.
4. **Preview look** — "A PREVIEW OF WHAT'S WAITING" editorial look card
   (Modern Minimalist + tags + Try This Look → Daily Outfit).
5. **Tools** — glass tool row (Scan Outfit, Add Wardrobe, Hairstyle Studio,
   Style Tips, Event Styling).
6. **AI quote** — "AI IS READY WHEN YOU ARE" close.

**Modified:** `lib/features/home/presentation/home_screen.dart`
- `HomeScreen` now routes light-path first visits
  (`onboardingData != null && no onboarding_complete`) to the new screen,
  passing the selected `vibe`.
- Removed the now-dead `_lightPathPrompt` and the first-visit branch of
  `_buildQuickActions`.

**Bug fixes (latent overflow, found via new widget tests):**
- Glass tool tiles in both `FirstTimeLightPathHomeScreen` and
  `FirstTimeHomeScreen` overflowed the fixed 100px rail (icon + label).
  Bumped rail to 118px, tightened padding, wrapped label in `Flexible`.
- `CameraPermissionScreen._TrustItem` Row overflowed because text was not in
  `Expanded` — wrapped the trust-statement text in `Expanded` (fixes the light
  path → camera permission destination).

**New tests:** `test/first_time_light_path_home_screen_test.dart` (4 cases —
render, chosen vibe, no-vibe state, Analyze My Style navigation).

**Container restyle (visual only, no content/behavior change):**
- Replaced per-card `boxShadow` + full borders with a shared `_craftedCard`
  treatment: tonal `surfaceContainerLow → surfaceContainer` gradient, a soft
  radial accent glow in a corner, and a hairline gold top edge (design system:
  "depth through surface colour, not shadows/borders").
- New `_medallion` layered-ring icon treatment (soft radial fill + dual
  hairline rings) used for the vibe motif, camera, and AI spark icons.
- Vibe card divider switched gold → muted `outlineVariant`; look badges refined
  to glass chips with hairline gold borders; editorial tags got hairline borders.
- All text, sections, order, navigation, and tests unchanged.

**Validation**
- `dart format`: passed
- `flutter analyze lib`: 0 errors (7 pre-existing infos, none in touched files)
- Tests: **224 passed, 87 failed** (was 220/87 — +4 new passing tests, 0 regressions)

## Changes Made — Onboarding Flow Sequence Polish (navigation only, no UI changes)

Rewired the onboarding journey to a proper navigation stack. All screens and
their UIs are unchanged; only route transitions changed. This restores
back-navigation through the wizard and keeps the stack clean on completion.

| Screen | Before | After |
|--------|--------|-------|
| Entry → VibeSelect | `goNamed` | `pushNamed` (photo + light paths) |
| VibeSelect → CameraPermission | `goNamed` | `pushNamed` (photo path only) |
| VibeSelect → Home (light path) | `goNamed` | `goNamed` (unchanged) |
| CameraPermission → PhotoCapture | `goNamed` | `pushNamed` |
| PhotoCapture → AiAnalysis | `goNamed` | `pushNamed` |
| AiAnalysis → YourAnalysis | `goNamed` | `replaceNamed` (auto-transition, no duplicate stack entry) |
| YourAnalysis → AccountCreation | `goNamed` | `pushNamed` |
| YourAnalysis → Retake | `goNamed` | `pop()` if possible (returns to existing captured photo) |
| Skips / Sign In / Account done → Home | `goNamed` | `goNamed` (unchanged — clears wizard stack) |

**Validation**
- `dart format`: passed
- `flutter analyze` (onboarding): 0 issues
- Tests: 220 passed, 87 failed (same pre-existing baseline)

## Changes Made — Professional Entry Screen Redesign (edit)

### Modified: `lib/features/onboarding/presentation/screens/entry_screen.dart`

Replaced the over-decorated "atelier" treatment with a restrained, professional
first-launch screen. Removed competing decoration (viewfinder corners, aura
gauge, star field, glow orbs, diamond bullets) in favor of one focal point and
clear type hierarchy. All routes/behavior unchanged.

**Design changes:**
- **Wordmark**: clean two-line lockup — serif FANSIVIBE (26px, tracked) over
  gold "APPEARANCE INTELLIGENCE" label. Dropped the pill badge.
- **Mirror focal point** (new): single 148px breathing ring with soft radial
  glow and person glyph — the only decorative element, animated via a subtle
  `_breathController` (0.45→0.85 alpha, 2.8s easeInOut).
- **Headline**: "Your best style, / *discovered by AI.*" — italic gold
  second line; dropped the 3-line manifesto block.
- **Value statement**: one muted line "Look better. Dress smarter. Build
  confidence." in place of diamond bullets + verbose support copy.
- **CTA stack**: `Analyze My Style` (primary) + `Explore Without Scanning`
  (secondary) — now the clear visual anchor.
- **Account gate**: no card — hairline divider + "Already have a Fansivibe
  account?" + two equal ghost pills (`Sign In` / `Continue as New User`).
- **Privacy note**: lock + label retained, switched to `Wrap` to eliminate a
  26px RenderFlex overflow under large text scale.
- Motion: single clean fade+slide `_Reveal` (8–12px) stagger over 1200ms;
  `TickerProviderStateMixin` retained for the two controllers.

### Validation

- `dart format`: passed
- `flutter analyze` (onboarding): 0 issues
- Tests: 220 passed, 87 failed (pre-existing baseline; 0 overflow exceptions, 0 entry failures)

## Changes Made — Creative "Digital Atelier" Entry Screen Redesign

### Modified: `lib/features/onboarding/presentation/screens/entry_screen.dart`

Elevated the first-launch screen into an editorial, art-directed experience while
keeping all routes, behavior, and the value-first + account-gate flow intact.

**Design changes:**
- **Ambient backdrop**: two large radial gold `_GlowOrb`s + 4 scattered `_Star`s
  behind the content, breathing via a looping `_glowController`.
- **Logo badge**: pill tag "AI APPEARANCE INTELLIGENCE" (gold dot) above a large
  serif FANSIVIBE wordmark.
- **Hero visual** (new): a 232px "analysis viewfinder" card with corner brackets
  (`_CornerPainter`), a live gold aura gauge (`_AuraPainter`, 64% arc with a
  pulsing end dot driven by the glow animation), sparkle icons, and a circular
  silhouette avatar — arriving with an `easeOutBack` scale-in.
- **Headline**: serif "Know your **style** *before you dress.*" with "style" in
  italic gold.
- **Manifesto**: three diamond-bulleted lines — Look better. / Dress smarter. /
  Build confidence.
- **Support copy** replaced with AI-powered style/grooming/color line.
- **Account gate**: now a glass `surfaceContainerLow` card (`mdBorder` + hairline
  outline) holding "Do you already have a Fansivibe account?" with `Sign In` /
  `New Here` pill buttons.
- All tokens (`FansivibeColors/Typography/Spacing/Radius`) only; responsive
  `LayoutBuilder` + staggered animations preserved.

**Bug fix**: switched State mixin from `SingleTickerProviderStateMixin` →
`TickerProviderStateMixin` (two controllers now run).

### Validation

- `dart format`: passed
- `flutter analyze` (onboarding): 0 issues
- Tests: 220 passed, 87 failed (same pre-existing baseline, no entry-related failures)

## Changes Made — Value-First Entry Screen & Returning-User Gate

### Modified: `lib/features/onboarding/presentation/screens/entry_screen.dart`

Redesigned the first-launch screen to lead with the value proposition instead of
a generic "Get Started" (already value-led, now a full visual redesign).

**Design changes:**
- **Headline**: "AI-powered Style, Grooming & Appearance Intelligence"
- **Value statements**: "Look better. / Dress smarter. / Build confidence." (gold
  editorial lines) + one-line supporting copy
- **Removed** the old `_HeroIllustration` graphic → minimal text-forward layout
- **Primary CTA**: `Analyze My Style` → photo path (`vibeSelect`, `photoPath: true`)
- **Secondary CTA**: `Explore Without Scanning` → light path (`photoPath: false`) — kept
- **Account gate** (new, replaces old Sign In section): "Do you already have a
  Fansivibe account?" with two side-by-side buttons:
  - `Sign In` → Home (mock, unchanged)
  - `Continue as New User` → photo path (same route as Analyze My Style)
- **Privacy note** retained at bottom; staggered entrance animations, design
  tokens (`FansivibeColors/Typography/Spacing/Radius`), and responsive
  `LayoutBuilder` layout preserved.

**No routing changes** — the gate lives on the Entry screen itself; save step
still routes straight to `AccountCreationScreen`.

### Validation

- `dart format`: passed
- `flutter analyze` (onboarding): 0 issues
- Tests: 220 passed, 87 failed (same pre-existing baseline, no new failures)

## Phase

Implemented the complete onboarding experience as a dedicated feature
(`lib/features/onboarding/`). 9 screens + personalized Home first-visit state,
replacing the single Entry screen placeholder. 2,836 lines of new Flutter code.

Onboarding was designed as a 4-act journey:
- **Act 1: Awakening** — Splash → Entry → Vibe Select
- **Act 2: Trust** — Camera Permission → Photo Capture
- **Act 3: Value** — AI Analysis → Your Analysis (score + DNA + AI Progress)
- **Act 4: Commitment** — Account Creation → Personalized Home

Supports two paths: photo path (9 screens → Home) and light path (4 screens → Home).

Previously redesigned 7 core screens with modern visual treatment while preserving all
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
- **Dart files**: 62 (`lib/`) + 25 (`test/`)
- **Total lines**: ~21,000
- **Features**: 12 (`home`, `discover`, `stylist`, `wardrobe`, `outfit_scan`, `outfit_builder`, `hairstyle`, `grooming`, `events`, `profile`, `assistant`, `learning`)
- **Mock data files**: 10 (`data/` directories across features)
- **Shared widgets**: 8 files (`fansi_button.dart`, `fansi_badge.dart`, `fansi_chip.dart`, `fansivibe_card.dart`, `section_title.dart`, `score_colors.dart`, `icon_utils.dart`, `floating_assistant_button.dart`)
- **Home-specific widgets removed**: `HomeActionButton`, `OutfitItemChip`, `HomeProgressRing`, `StreakDayIndicator`
- **Theme files**: 2 (`fansivibe_colors.dart`, `fansivibe_theme.dart`)
- **Router**: `go_router` 17.2.3 with `StatefulShellRoute.indexedStack`, named routes in `RouteNames`, centralized in `app_router.dart`
- **State management**: mostly local `setState`; `assistant` and `learning` use `ChangeNotifier` services (`LearningService.instance`, `AssistantService`)
- **Domain layer**: present in `assistant/` and `learning/` features only
- **No assets**: No image assets or asset directories configured (fonts bundled in pubspec)

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

All screens from `docs/SCREEN_MAP.md`, plus new onboarding screens:

### Onboarding (ONB-001 through ONB-009)
- ONB-001: SplashScreen (brand reveal, auto-transitions to Entry)
- ONB-002: EntryScreen (enhanced from original ENTRY-001, value prop + photo/light path fork)
- ONB-003: VibeSelectScreen ("Which style feels most like you?" with 6 editorial cards)
- ONB-005: CameraPermissionScreen (trust-building prior to camera access)
- ONB-006: PhotoCaptureScreen (full-screen camera with guided framing)
- ONB-007: AiAnalysisScreen (atmospheric processing with particles + gold arc)
- ONB-008: YourAnalysisScreen (emotional peak: score + DNA + insights + AI Progress)
- ONB-009: AccountCreationScreen (glass inputs, social login, "Save Locally" option)

### Existing screens (updated)
- HOME-001: HomeScreen (now accepts onboarding data; shows Style DNA card, AI Progress section, light-path prompt on first visit)
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

## Route Changes

| Change | Detail |
|--------|--------|
| `initialLocation` | `/entry` (unchanged — splash is entry screen's opening animation) |
| New routes | `/splash`, `/onboarding/vibe`, `/onboarding/camera-permission`, `/onboarding/photo-capture`, `/onboarding/analysis`, `/onboarding/result`, `/onboarding/account` |
| Route names added | `splash`, `vibeSelect`, `cameraPermission`, `photoCapture`, `aiAnalysis`, `yourAnalysis`, `accountCreation` |
| Home screen | Now accepts `Map<String, dynamic>? onboardingData` for first-visit personalization; delegates to `FirstTimeHomeScreen` when onboarding complete |

## Migration Completed (from previous work)

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
 M lib/app/router/app_router.dart
 M lib/app/router/route_names.dart
?? docs/ONBOARDING_UI_SPEC.md
?? lib/features/entry/
?? lib/features/onboarding/
 M lib/features/home/presentation/home_screen.dart
 M ../../CURRENT_STATE.md
```


## Last Validation

Analysis: Passed — 0 issues in home feature; 4 pre-existing infos in `outfit_scan`.
Tests: 217 passed, 87 failed (unchanged — no new failures introduced).

## Changes Made — Onboarding Feature Implementation

### New feature: `lib/features/onboarding/` (2,836 lines, 15 files)

**Data layer** — `data/onboarding_data.dart`:
- `StyleVibe` enum (6 styles with labels and descriptions)
- `AnalysisResult` model (score, silhouette, observations, palette, formality)
- `PaletteSwatch` model (color + label for palette display)
- `AiCapability` model (name, description, active status, unlock hint)
- `OnboardingResult` model (vibe, analysis, display name)
- `allCapabilities` constant (7 AI capabilities: 2 active, 5 locked)

**Shared widgets** — `presentation/widgets/`:
- `GlassContainer` — frosted glass effect with `BackdropFilter`
- `VibeCard` — editorial mood board card with gradient + decorative lines
- `AnimatedScoreCounter` — animated 0→X counter with score-based coloring
- `ColorPaletteDisplay` — horizontal colour swatch row with labels
- `AiCapabilityIcon` — circular capability status (active/locked) with unlock hint
- `AnalysisInsightCard` — editorial insight card with icon + title + body

**Screens** — `presentation/screens/`:

| Screen | Key features |
|--------|-------------|
| ONB-001 SplashScreen | Gold glow radial animation, letter-spacing animation, tap-to-skip, auto-transition |
| ONB-002 EntryScreen | Staggered content reveal (6 animation phases), value prop, photo/light path fork |
| ONB-003 VibeSelectScreen | 6 visual cards in 2×3 grid, spring animations, selection glow, skip option |
| ONB-005 CameraPermissionScreen | Trust illustration + 3 privacy statements, staggered fade-in, gallery/skip options |
| ONB-006 PhotoCaptureScreen | Full-screen camera mockup, silhouette framing guide, Polaroid-develop animation, retake |
| ONB-007 AiAnalysisScreen | Gold particle system (CustomPaint), arc progress, floating terms |
| ONB-008 YourAnalysisScreen | Animated score counter, colour palette display, 3 insight cards, AI Progress carousel |
| ONB-009 AccountCreationScreen | Palette ring avatar, glass-style inputs, Google/Apple sign-in, local save option |

**Routing changes**:
- Added 8 onboarding routes to `app_router.dart` and `route_names.dart`
- `initialLocation` remains `/entry`
- `HomeScreen` now accepts optional `Map<String, dynamic>? onboardingData`
- Old `lib/features/entry/presentation/entry_screen.dart` preserved as fallback

**HomeScreen updates**:
- First visit with photo path: now routes to `FirstTimeHomeScreen` — a full-screen first-time experience
- First visit with light path: shows "Analyze Your Style" prompt card with camera icon
- All existing sections preserved with mock data fallback (subsequent visits)
- Removed unused `_StyleDNACard`, `_AiProgressSection`, `_CompactCapability`, `_DnaAttribute`, `_ColorDot`, `_buildFirstVisitBanner`

## Changes Made — Today's Look Screen Redesign

### Modified: `lib/features/home/presentation/daily_outfit_screen.dart`

Complete redesign as the "Today's Look" flagship experience using the Digital Atelier design system.

**Design changes:**
- Hero outfit section occupying ~68% of viewport with ambient gradient backdrop
- Floating glass chips overlay using `BackdropFilter` blur: TODAY'S LOOK label, AI Match Score (91%), Occasion, Weather, Confidence Boost
- Editorial summary with outfit name (serif), description, and italic AI selection reason
- Horizontal card carousel for outfit breakdown (The Ensemble) with clothing image area, name, color, category
- "Why It Works" section with 4 glass insight cards: Color Harmony, Body Proportions, Style Compatibility, Occasion Suitability
- Alternative looks horizontal carousel with match scores, style names, and "See Details" CTA
- Quick actions: Wear This Look (primary gold), Generate Another Look, Save Look, Share
- Daily Style Tip editorial card with lightbulb icon
- Staggered entrance animations (7 sections, 2.4s total) with `easeOutCubic`
- Responsive layout with tablet-aware sizing
- Respects `disableAnimations` for reduced motion

**Removed sections from old screen:** Score cards (Match/Style), Style DNA card, Wardrobe Context card, "Change Style" actions, component replace buttons.

### Modified: `lib/features/home/data/daily_outfit_mock_data.dart`

Extended with 3 new model classes and mock data:
- `AiInsightData` — title, description, iconName for Why It Works cards
- `AlternativeLookData` — id, name, matchScore, styleName for alternatives carousel
- New fields on `DailyOutfitData`: `aiSelectionReason`, `confidenceBoost`, `aiInsights`, `alternatives`, `dailyStyleTip`

### Validation

- `dart analyze`: 0 issues in home feature
- Tests: 23 passed, 0 failed (all daily_outfit_screen tests rewritten for new UI, added 8 new test cases for new sections)

Skill used: `dart-run-static-analysis`

**Sections** (staggered fade + slide animations, 1.8s total):
1. **Hero Greeting** — "Welcome to Fansivibe", personalized name, success message
2. **Hero Card** — Premium gradient container with large Style Score badge (radial glow), Style DNA label, dominant color palette (5 swatch row), and a one-line AI insight
3. **Today's First Recommendation** — Lifestyle card with image area (AI RECOMMENDED tag), content section (title, description, garment chips, "Why this suits you" explanation, "Try This Look" CTA)
4. **Continue Building Your Style** — Expanded capability list (all 7 from `allCapabilities`): active items show checkmark + gold tint; locked items show lock icon + description + unlock hint CTA pill
5. **Quick Actions** — 4 glass-action cards using `BackdropFilter` blur: Scan Another Look, Add Wardrobe, Explore Hairstyles, Discover Style Tips
6. **AI Insight** — Premium insight card with gold gradient border, AI icon, bold insight statement, body text, "Explore Hairstyles" button

**Navigation actions** — Routes to existing screens via `context.pushNamed`/`goNamed`: `dailyOutfit`, `scanOutfit`, `wardrobe`, `hairstyle`, `discover`

**Design tokens** — Uses `FansivibeColors`, `FansivibeTypography`, `FansivibeSpacing`, `FansivibeRadius` exclusively. No hardcoded visual values. Follows the Digital Atelier design system (no borders, tonal layering, `sm`/`md`/`lg` radius, serif headings, sans-serif body, gold accents).

### Modified file: `lib/features/home/presentation/home_screen.dart` (244 lines, -279)

- Early return to `FirstTimeHomeScreen` when `_isFirstVisit && _hasAnalysis`
- Removed 5 unused private classes (`_StyleDNACard`, `_DnaAttribute`, `_ColorDot`, `_AiProgressSection`, `_CompactCapability`)
- Removed `_buildFirstVisitBanner`
- Simplified conditional rendering for light path vs returning user
- Removed unused `onboarding_data.dart` import

## Changes Made — UI Polish & Fixes Round

### Fonts Bundled
- Downloaded and registered **Noto Serif** (variable) and **Inter** (variable) fonts
- Font files at `assets/fonts/NotoSerif-Variable.ttf` and `assets/fonts/Inter-Variable.ttf`
- Updated `pubspec.yaml` with font declarations
- Updated `fansivibe_typography.dart` to use bundled fonts as defaults (was falling back to system serif/sans-serif)

### Hardcoded Colors Replaced
- Replaced all `Color(0xFF4CAF50)` → `FansivibeColors.success` (17 files)
- Replaced all `Color(0xFFFF9800)` → `FansivibeColors.warning` (4 files)
- Replaced all `Color(0xFFF44336)` → `FansivibeColors.error` (4 files)
- Updated `score_colors.dart` utility to use semantic tokens
- Files affected: `profile_widgets.dart`, `look_details_widgets.dart`, `outfit_generation_screen.dart`, `home_widgets.dart`, `outfit_scan_widgets.dart`, `outfit_analysis_screen.dart`, `outfit_processing_screen.dart`, `face_processing_screen.dart`, `hairstyle_details_screen.dart`, `hairstyle_widgets.dart`, `hairstyle_result_screen.dart`, `outfit_recommendation_screen.dart`, `grooming_details_screen.dart`, `grooming_processing_screen.dart`, `grooming_widgets.dart`, `grooming_result_screen.dart`

### Dead Code Removed
- Deleted `lib/app/main_shell.dart` (unused — router uses `router_shell.dart`)
- Deleted `lib/features/entry/` (duplicate pre-onboarding EntryScreen — onboarding version is active)

### Router Error Handling
- Replaced all `const SizedBox()` blank-screen returns (9 occurrences) with `_missingDataScreen()` / `_missingDataScreenWithText()` using `FansiErrorView`
- Files affected: `app_router.dart` (look-details, outfit-generation, hairstyle-details, grooming screens, event-details, wardrobe-add-item, wardrobe-item-details)

### FansivibeCard API Cleanup
- Removed deprecated `borderColor` parameter from `FansivibeCard` (was already documented as "NOT rendered")
- Updated callers: `home_widgets.dart` removed borderColor, `subscription_screen.dart` replaced with `variant` parameter
- Added `CardVariant.high` usage for popular subscription plan

## Remaining Audit Issues

1. **No state management**: All state is local `setState` (not in scope)
2. **No domain layer**: No `domain/` directory in any feature (not in scope)
3. **Stylist string-switch dispatch**: Business logic in UI widgets (not in scope)
4. **Events → Outfit Builder boundary**: No cross-feature contract (not in scope)
5. **Failing tests**: Resolved — suite is fully green (311 passed, 0 failed).
6. **Mock data**: All onboarding analysis data is currently hardcoded mock values.
    Needs real AI integration.
7. **Photo capture**: Camera/gallery functionality is simulated (placeholder UI).
    Needs platform channel integration.
8. **Splash routing**: Splash screen route exists but initialLocation is `/entry` to
    maintain test compatibility.
9. **Naming inconsistency**: `FansiButton` vs `FansivibeCard` prefix mismatch (deferred).
10. **Mega-widget files**: `home_widgets.dart` (1,277 lines) and others still need splitting (deferred).
11. **AI integration**: Backend chat runs rules-only unless Ollama is running
    locally (LLM enrichment is optional server-side). No auth on `/v1/assistant/chat` yet.

## Handoff

New agents must:

1. Read `AGENTS.md`.
2. Read this file.
3. Inspect Git status and actual code.
4. Discover and read task-relevant skills.
5. Continue from repository reality.
