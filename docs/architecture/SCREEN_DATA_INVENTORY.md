# Fansivibe Screen Data Inventory

> Complete inventory of every screen that **actually exists** in the real Flutter
> app at `newproject/flutter_application_1`. Companion to
> `docs/architecture/FEATURE_INVENTORY.md`.
>
> This documents **what exists** — screens, routes, data flows, states, tests.
> No UI changes, no redesigns, no routing changes are proposed. The
> "Required future backend data" column is the only forward-looking field and
> records, per screen, which currently-mock/ephemeral/local data would need a
> backend to back it once the production DB/service layer is designed.
>
> Last verified: 2026-08-09. All data usage notes verified against source code.

## Legend

| Value | Meaning |
|-------|---------|
| Mock | Hardcoded `static const` data compiled into the app |
| Local | Persisted on-device (SharedPreferences via `features/learning`) |
| Remote | Fetched from the backend via HTTP (only the Assistant does this) |
| Ephemeral | Held in widget state only, lost on restart |
| Route extra | Passed between screens via GoRouter `state.extra` (typed object or `Map`) |

## Cross-cutting facts (applies to every screen)

- **Router:** go_router 17.2.3. Single `GoRouter` (`appRouter`) with
  `initialLocation: '/entry'`; 5-tab `StatefulShellRoute.indexedStack`
  (`/home`, `/discover`, `/stylist`, `/wardrobe`, `/profile`); top-level routes
  for `/splash`, `/entry`, `/onboarding/*`, `/assistant`. Route names centralized
  in `lib/app/router/route_names.dart` (`RouteNames`), route definitions in
  `lib/app/router/app_router.dart`.
- **Missing-data fallback:** routes that consume `state.extra` null-check it and
  render `_missingDataScreen()` (a `FansiErrorView`, "Could not load the requested
  content. Please go back and try again.") or `_missingDataScreenWithText(label)`
  (e.g. "Missing outfit preferences.", "Missing grooming data."). `hairstyle-details`
  instead returns `const SizedBox()` when its extra is null.
- **State management:** local `setState` everywhere except the Assistant
  (`ChangeNotifier`) and Learning (`LearningService.instance` singleton).
- **Learning signals:** several screens write to `LearningService.instance`
  (`addSavedLook`, `addItem`, `addPreferredOccasion`, `recordSignal`); these are
  noted per screen. This is the app's only persistence and cross-feature
  feedback channel today.
- **Tests:** all widget tests live in `newproject/flutter_application_1/test/`.
  Baseline: 342 passing (per CURRENT_STATE.md).

---

# 1. Feature: Onboarding

## 1.1 SplashScreen

- **File path:** `lib/features/onboarding/presentation/screens/splash_screen.dart`
- **Route:** `RouteNames.splash` → `/splash`
- **Entry point:** registered route only; **not navigated to by any lib code**
  (app boots directly at `/entry`). No `state.extra`.
- **Main purpose:** branded wordmark splash; auto-transitions to Entry.
- **Main widgets/components:** `_SplashScreenState` (1 controller, 1800ms), glow
  `Container` (RadialGradient), `AnimatedBuilder`, `Text` "FANSIVIBE".
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `entry`.
- **Widget tests:** none.
- **Dependencies:** shared theme + `route_names.dart` only.

### SplashScreen
→ **User action:** tap anywhere, or wait 1.8s → go to Entry (`goNamed(entry)`).
→ **Data displayed:** static "FANSIVIBE" wordmark with animated letter-spacing/glow.
→ **Data source:** none (static).
→ **Required future backend data:** none (branding only).
→ **Related domain entities:** none.

## 1.2 EntryScreen

- **File path:** `lib/features/onboarding/presentation/screens/entry_screen.dart`
- **Route:** `RouteNames.entry` → `/entry` — the GoRouter `initialLocation`.
- **Entry point:** app launch; target of Splash. No `state.extra`.
- **Main purpose:** first-launch landing; branches into photo path vs. explore
  path, plus returning-user gate.
- **Main widgets/components:** `_Reveal`, `_Wordmark`, `_Mirror`, `_Headline`,
  `_ValueStatement`, `_PrimaryCTA`, `_SecondaryCTA`, `_AccountGate`,
  `_GateButton`, `_PrivacyNote`, shared `FansiButton.primary/secondary`.
- **Loading / Empty / Error states:** none (staggered entrance animation only).
- **Navigation destinations:** `vibe-select` (extra `{'photoPath': bool}`), `home`.
- **Widget tests:** none directly; tests boot past it (`/home`).
- **Dependencies:** shared only.

### EntryScreen
→ **User action:** "Analyze My Style" → `vibe-select` (photoPath true); "Explore
  Without Scanning" → `vibe-select` (photoPath false); "Sign In" → `home` (mock).
→ **Data displayed:** static copy (wordmark, headline "Your best style, discovered
  by AI.", value line, CTAs, privacy note).
→ **Data source:** none (static copy).
→ **Required future backend data:** account/session check to make "Sign In" real
  (currently a mock `goNamed(home)`).
→ **Related domain entities:** (future) `User` / auth session.

## 1.3 VibeSelectScreen

- **File path:** `lib/features/onboarding/presentation/screens/vibe_select_screen.dart`
- **Route:** `RouteNames.vibeSelect` → `/onboarding/vibe`
- **Entry point:** pushed by Entry with extra `{'photoPath': bool}` (read in
  `didChangeDependencies`, defaults true). No constructor params.
- **Main purpose:** pick 1 of 6 style vibes to seed personalization.
- **Main widgets/components:** `VibeCard` (feature widget), `GridView.count`,
  `FansiButton.primary/tertiary`; staggered card animations.
- **Data displayed:** question + 6 `StyleVibe` cards (Minimalist, Bold, Classic,
  Trendy, Natural, Edgy) with `vibeGradientColors` gradients.
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `camera-permission` (extra `{'vibe': String?}`),
  `home` (extra `{'vibe': String?}`).
- **Widget tests:** none.
- **Dependencies:** `features/onboarding/data/onboarding_data.dart` +
  `vibe_card.dart`; shared.

### VibeSelectScreen
→ **User action:** tap a vibe (select/deselect), "Continue" (enabled when
  selected) → camera permission (photo path) or home (explore path); "skip for
  now" → same two destinations with `vibe: null`.
→ **Data displayed:** 6 vibe cards with gradient + label; selected-state styling.
→ **Data source:** mock const (`StyleVibe` enum, `vibeGradientColors` map).
→ **Required future backend data:** a server-side style/preference list or
  reference to the catalog's style-type vocabulary (currently hardcoded enum);
  persist chosen vibe on the user profile.
→ **Related domain entities:** `UserModel` (future `styleType`), `StyleVibe`.

## 1.4 CameraPermissionScreen

- **File path:** `lib/features/onboarding/presentation/screens/camera_permission_screen.dart`
- **Route:** `RouteNames.cameraPermission` → `/onboarding/camera-permission`
- **Entry point:** pushed by VibeSelect (extra `{'vibe': ...}` — received but not
  consumed). Also reachable from `FirstTimeLightPathHomeScreen` "Analyze My Style".
- **Main purpose:** trust-building explanation before camera/gallery access.
- **Main widgets/components:** `_AnimatedSection`, `_TrustItem`,
  `FansiButton.primary/secondary/tertiary`.
- **Data displayed:** static copy ("One Photo Is All It Takes", 3 privacy trust
  rows, camera/gallery/skip CTAs).
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `photo-capture` (extra `{'source': 'camera'|'gallery'}`),
  `home` (extra `{'vibe': null}`).
- **Widget tests:** indirect — `first_time_light_path_home_screen_test.dart`
  asserts its headline after navigation.
- **Dependencies:** shared only.

### CameraPermissionScreen
→ **User action:** "Allow Camera" → photo capture (source camera); "Choose from
  Gallery" → photo capture (source gallery); "Skip for now" → home.
→ **Data displayed:** static trust copy + illustration.
→ **Data source:** none (static copy).
→ **Required future backend data:** real camera permission state + (future)
  media-picker source; no server data.
→ **Related domain entities:** none.

## 1.5 PhotoCaptureScreen

- **File path:** `lib/features/onboarding/presentation/screens/photo_capture_screen.dart`
- **Route:** `RouteNames.photoCapture` → `/onboarding/photo-capture`
- **Entry point:** pushed by CameraPermission (extra `{'source': ...}` →
  constructor `source`, currently unused). Retake fallback from YourAnalysis.
- **Main purpose:** simulated camera viewfinder with silhouette guide; capture →
  timed auto-transition to AI analysis.
- **Main widgets/components:** `_SilhouettePainter` (CustomPainter), `_CaptureButton`,
  guide-frame `Container`, captured preview (`AnimatedBuilder` + 2s `Timer`).
- **Data displayed:** static silhouette guide, "Looks great!", "Retake", "Skip".
  No real image data.
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `ai-analysis` (extra `{'photoPath': 'captured'}`),
  `home` (extra `{'vibe': null}`).
- **Widget tests:** none.
- **Dependencies:** shared theme only.

### PhotoCaptureScreen
→ **User action:** capture → 2s preview → auto-push `ai-analysis`; "Retake" resets;
  "Skip" → home.
→ **Data displayed:** simulated viewfinder (no real camera/image bytes yet).
→ **Data source:** ephemeral widget state.
→ **Required future backend data:** real captured image upload for face/outfit
  analysis (image bytes, upload endpoint), plus camera wiring.
→ **Related domain entities:** (future) `FaceAnalysis`/`OutfitAnalysis` from an
  image; `UserModel` face profile.

## 1.6 AiAnalysisScreen

- **File path:** `lib/features/onboarding/presentation/screens/ai_analysis_screen.dart`
- **Route:** `RouteNames.aiAnalysis` → `/onboarding/analysis`
- **Entry point:** pushed by PhotoCapture (extra `{'photoPath': 'captured'}`,
  not consumed). No constructor params.
- **Main purpose:** atmospheric "analyzing" screen; auto-navigates to results.
- **Main widgets/components:** `_ParticlePainter`, `_ArcPainter`, `_FloatingTerms`,
  2.5s arc controller + 0.5s timer.
- **Data displayed:** "Analyzing your style…", floating terms SILHOUETTE/HARMONY/
  PROPORTION/PALETTE.
- **Loading / Empty / Error states:** loading = the whole screen (simulated 3s).
- **Navigation destinations:** `your-analysis` (`replaceNamed`).
- **Widget tests:** none.
- **Dependencies:** shared only.

### AiAnalysisScreen
→ **User action:** none (auto-advance after ~3s → `your-analysis`).
→ **Data displayed:** processing animation + floating terms.
→ **Data source:** none (pure animation).
→ **Required future backend data:** real face-analysis request/result; progress
  could be driven by server processing status.
→ **Related domain entities:** (future) analysis job/result.

## 1.7 YourAnalysisScreen

- **File path:** `lib/features/onboarding/presentation/screens/your_analysis_screen.dart`
- **Route:** `RouteNames.yourAnalysis` → `/onboarding/result`
- **Entry point:** `replaceNamed` from AiAnalysis (no extra). No constructor params.
- **Main purpose:** shows mock analysis results: score, palette, insights, AI
  capability progress; Save/Retake actions.
- **Main widgets/components:** `AnimatedScoreCounter`, `ColorPaletteDisplay`,
  `AnalysisInsightCard`, `AiCapabilityIcon`, `FansiButton.primary/tertiary`.
- **Data displayed:** mock score 82 + "Style Score"; 5 `PaletteSwatch` (Charcoal,
  Taupe, Gold, Cream, Sage); 3 AI insight cards; 7 `allCapabilities` (2 active:
  Face Analysis, Color Analysis; 5 locked with unlock hints).
- **Loading / Empty / Error states:** none (score counts up on entrance).
- **Navigation destinations:** `account-creation`, `photo-capture` (retake fallback).
- **Widget tests:** none.
- **Dependencies:** `onboarding_data.dart` + onboarding widgets; shared.

### YourAnalysisScreen
→ **User action:** "Save My Progress" → `account-creation`; "Retake Photo" → pop
  or `photo-capture`; tap locked capability → SnackBar unlock hint.
→ **Data displayed:** score, colour palette swatches, 3 insights, capability grid.
→ **Data source:** mock const inline (`_mockScore`, `_mockPalette`) + const
  `allCapabilities`.
→ **Required future backend data:** real analysis result from the face-analysis
  service (score, palette, insights, capability unlocks) persisted to the user
  profile; capability list/status from backend.
→ **Related domain entities:** (future) `AnalysisResult`, `UserModel` face/style
  data; `AiCapability`.

## 1.8 AccountCreationScreen

- **File path:** `lib/features/onboarding/presentation/screens/account_creation_screen.dart`
- **Route:** `RouteNames.accountCreation` → `/onboarding/account`
- **Entry point:** pushed by YourAnalysis (no extra). No constructor params.
- **Main purpose:** mock account form (email/password/name + Google/Apple +
  save-locally); all paths land on Home with onboarding-complete extras.
- **Main widgets/components:** `FansiButton.primary/tertiary`, 3 `TextField`s,
  2 `FilledButton.icon`; SweepGradient avatar from hardcoded palette.
- **Data displayed:** static form labels + palette avatar.
- **Loading / Empty / Error states:** none (no validation messages; button
  disabled until email passes a local `@`/`.` check).
- **Navigation destinations:** `home` with extras (`onboarding_complete: true` +
  `display_name` / `provider` / `saved_locally`).
- **Widget tests:** none.
- **Dependencies:** shared only.

### AccountCreationScreen
→ **User action:** enter email/password/name → "Create Account" (enabled when
  email valid) → home; "Google"/"Apple" → home; "Maybe Later — Save Locally" → home.
→ **Data displayed:** form fields + static copy (no real account state).
→ **Data source:** ephemeral local form state.
→ **Required future backend data:** real auth endpoints (register/social),
  account identity + persisted profile (name, email, auth provider).
→ **Related domain entities:** `User` (future), `UserModel`.

---

# 2. Feature: Home

## 2.1 HomeScreen

- **File path:** `lib/features/home/presentation/home_screen.dart`
- **Route:** `RouteNames.home` → `/home` (first shell branch)
- **Entry point:** shell tab; receives `state.extra` as `Map<String, dynamic>?`
  (constructor `onboardingData`). Dispatcher: first-visit → `FirstTimeHomeScreen` /
  `FirstTimeLightPathHomeScreen`; otherwise the returning-user dashboard.
- **Main purpose:** personalized home dashboard + first-visit branch routing.
- **Main widgets/components:** `GreetingHeader`, `TodaysLookCard`, `StyleScoreCard`,
  `QuickActionCard`, `StyleStreakCard`, `AIInsightCard` (all in
  `home/presentation/widgets/home_widgets.dart`, built on FansiHeroCard /
  FansiInsightCard / FansiMiniCard / FansiBadge / FansiImageWell).
- **Data displayed:** greeting (Welcome/Good morning + name `Alex` default + live
  date), `TodaysLookData.mock` (Modern Minimalist, occasion, weather, score 87),
  `StyleScoreData.mock` (84, weekly trend, breakdown), `QuickActionData.mockActions`,
  `StyleStreakData.mock` (12/28/156), `AIWardrobeInsightData.mock` (Wardrobe Gap).
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `daily-outfit`, `build-outfit`, `scan-outfit`;
  some actions show SnackBars.
- **Widget tests:** `home_screen_test.dart`, `widget_test.dart` (navigation).
- **Dependencies:** home data/widgets; `shared/utils/user_session.dart`
  (`UserSession.hasSavedWardrobeItem` gates light-path first visit); first-time
  screens (same feature). No learning signals.

### HomeScreen
→ **User action:** "Try This Look" → daily-outfit; "Change Style"/quick actions →
  build-outfit/scan-outfit; "View Recommendations" → SnackBar.
→ **Data displayed:** greeting, Today's Look card, Style Score breakdown, quick
  actions, streak timeline, wardrobe-gap insight.
→ **Data source:** mock consts (`home_mock_data.dart`) + runtime date + incoming
  onboarding `extra`; `UserSession` flag.
→ **Required future backend data:** daily outfit (server-driven "today's look"),
  computed style score + trend, streak persistence, AI wardrobe insight from real
  user data.
→ **Related domain entities:** `UserModel`, `DailyOutfit`/`Look`, `StyleScore`,
  `WardrobeInsight`; `savedLooks` when saving.

## 2.2 DailyOutfitScreen

- **File path:** `lib/features/home/presentation/daily_outfit_screen.dart`
- **Route:** `RouteNames.dailyOutfit` → `/home/daily-outfit`
- **Entry point:** pushed by Home / FirstTime screens ("Try This Look"). No extra.
- **Main purpose:** editorial "Today's Look" — hero, ensemble, AI insights,
  alternatives, quick actions.
- **Main widgets/components:** shared `FansiButton`, `FansiHeroCard`;
  private `_glassPill`, `_garmentTag`, `_componentCard`, `_insightCard`,
  `_alternativeCard`, `_goldGradientCta`; 7-section staggered entrance animation.
- **Data displayed:** `DailyOutfitData.mock` (match 91%, "TODAY'S LOOK", Casual
  Friday, 68°F, title Modern Minimalist, AI note, 5-component "The Ensemble",
  4 "Why It Works" insights, 3 alternatives, daily style tip). Fields
  `reasons`/`styleDna`/`wardrobeContext` exist in the model but are **not
  rendered**.
- **Loading / Empty / Error states:** empty — daily style tip section hides when
  `dailyStyleTip` is null; sections skip when their lists are empty. No error state.
- **Navigation destinations:** none (all actions are SnackBars; back = pop).
- **Widget tests:** `daily_outfit_screen_test.dart` (23 tests).
- **Dependencies:** `features/learning` (`LearningService.addSavedLook` on "Save
  Look", signal `look_saved`); home mock data; shared.

### DailyOutfitScreen
→ **User action:** "Wear This Look" → SnackBar; "Generate Another Look" →
  SnackBar; "Save Look" → `LearningService.addSavedLook` + SnackBar; "Share" →
  SnackBar; "See Details" per alternative → SnackBar.
→ **Data displayed:** hero match-score, occasion/weather tags, AI note, 5-piece
  ensemble, 4 insights, 3 alternative looks, daily style tip.
→ **Data source:** mock const `DailyOutfitData.mock`; save writes a local learning
  signal.
→ **Required future backend data:** personalized daily outfit recommendation
  (title, components, alternatives, scores), saved-look persistence, sharing
  (real share sheet), "generate another look" regeneration.
→ **Related domain entities:** `Look`/`DailyOutfit`, `OutfitComponent`,
  `savedLooks` (`UserModel`), `LearningSignal`.

## 2.3 FirstTimeHomeScreen

- **File path:** `lib/features/home/presentation/first_time_home_screen.dart`
- **Route:** none — rendered inline by `HomeScreen` (photo-path first visit with
  analysis, no saved wardrobe item).
- **Entry point:** `HomeScreen` when `_isFirstVisit && _hasAnalysis &&
  !UserSession.hasSavedWardrobeItem`. Constructor param `displayName` (from
  onboarding extra `display_name`).
- **Main purpose:** first-visit "analysis complete" celebration: score/DNA hero,
  first recommendation, capability grid, tools, AI quote.
- **Main widgets/components:** `FansiButton.primary/secondary`; private
  `_buildScoreGlobe`, `_buildPaletteBar`, `_buildLookEditorial`,
  `_buildCapabilityGrid`, `_glassTool`, `_buildAiQuote`; 2000ms staggered reveal.
- **Data displayed:** welcome + name; mock score 82, DNA "Refined Minimalist",
  palette (Charcoal/Taupe/Gold/Cream/Sage); "FIRST RECOMMENDATION" Modern
  Minimalist (score 87, 4 tags); all 7 `allCapabilities`; 5 tools; AI quote.
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `daily-outfit`, `scan-outfit`, `wardrobe` (go),
  `hairstyle`, `discover` (go), `events` (go).
- **Widget tests:** none dedicated (`first_time_home_screen_test.dart` does not
  exist).
- **Dependencies:** `features/onboarding/data/onboarding_data.dart`
  (`allCapabilities`, `PaletteSwatch`); shared. No learning signals.

### FirstTimeHomeScreen
→ **User action:** "Try This Look" → daily-outfit; glass tools → scan-outfit /
  wardrobe / hairstyle / discover / events; "Explore Hairstyles" → hairstyle;
  locked capability tap → SnackBar.
→ **Data displayed:** style score, DNA, palette, first recommendation, capability
  grid, tools, AI quote.
→ **Data source:** hardcoded consts in-file + `allCapabilities`.
→ **Required future backend data:** real analysis results persisted from
  onboarding; capability unlock status; first recommendation from recommendation
  service.
→ **Related domain entities:** (future) `AnalysisResult`/`UserModel` style data,
  `AiCapability`.

## 2.4 FirstTimeLightPathHomeScreen

- **File path:** `lib/features/home/presentation/first_time_light_path_home_screen.dart`
- **Route:** none — rendered inline by `HomeScreen` for light-path first visits
  (with or without a saved wardrobe item). Constructor param `vibeName` (from
  onboarding extra `vibe`).
- **Entry point:** `HomeScreen` when first visit on the explore path. `vibeName`
  resolved via `_vibeFromName` → `StyleVibe?`.
- **Main purpose:** first-visit home for "Explore Without Scanning": acknowledge
  chosen vibe, single analyze CTA, preview look, tools, AI quote.
- **Main widgets/components:** `FansiButton.primary/tertiary`; private `_craftedCard`,
  `_medallion`, `_buildVibeCard`, `_buildAnalysisCard`, `_buildPreviewLook`,
  `_glassTool`, `_buildAiQuote`; `_vibeIcons`/`_vibeFromName` const maps.
- **Data displayed:** vibe card (`_vibe?.label` or "Open to Everything" +
  description + gradient accent); "YOUR ANALYSIS IS WAITING"; "A PREVIEW OF
  WHAT'S WAITING" (Modern Minimalist, score 87, 4 tags); 5 tools; "AI IS READY
  WHEN YOU ARE".
- **Loading / Empty / Error states:** none (unknown vibe falls back to "Open to
  Everything").
- **Navigation destinations:** `camera-permission`, `discover` (go),
  `daily-outfit`, `scan-outfit`, `wardrobe` (go), `hairstyle`, `events` (go).
- **Widget tests:** `first_time_light_path_home_screen_test.dart` (4 tests).
- **Dependencies:** `features/onboarding/data/onboarding_data.dart` (`StyleVibe`,
  `vibeGradientColors`); shared. No learning signals.

### FirstTimeLightPathHomeScreen
→ **User action:** "Analyze My Style" → camera-permission; "Explore looks while
  you wait" → discover; "Try This Look" → daily-outfit; glass tools →
  scan-outfit/wardrobe/hairstyle/discover/events.
→ **Data displayed:** chosen vibe direction, analysis-pending CTA, preview look,
  tools, AI quote.
→ **Data source:** passed-in `vibeName` → `StyleVibe`/`vibeGradientColors`; inline
  consts.
→ **Required future backend data:** persist the chosen vibe as a preference;
  personalize recommendations from it; capability unlock gating.
→ **Related domain entities:** `UserModel` (future `styleType`), `StyleVibe`.

---

# 3. Feature: Discover

## 3.1 DiscoverScreen

- **File path:** `lib/features/discover/presentation/discover_screen.dart`
- **Route:** `RouteNames.discover` → `/discover` (second shell branch)
- **Entry point:** shell tab; also reached via `goNamed(discover)` from first-time
  home screens. No extra.
- **Main purpose:** personalized/trending looks with search, filters, tabs, grid.
- **Main widgets/components:** `DiscoverTabButton`, `LookCard` (feature widgets),
  `FansiButton`, `FansiChip`, `_FilterSheet` (modal bottom sheet).
- **Data displayed:** search field; "For You"/"Trending" tabs; results count;
  grid from `DiscoverLookData.forYouMock` / `trendingMock` (6 each) with title,
  occasion, match score badge, tags, "Trending" badge; filters
  (`OccasionFilters`, `StyleFilters`, `FitFilters` options).
- **Loading / Empty / Error states:** empty — "No looks found" + reset button.
  No loading/error.
- **Navigation destinations:** `look-details` (extra `DiscoverLookData`).
- **Widget tests:** `discover_screen_test.dart`, `discover_widgets_test.dart`.
- **Dependencies:** discover data/widgets; shared. No learning signals.

### DiscoverScreen
→ **User action:** switch tabs, type search / clear, open filter sheet and select
  occasion/style/fit chips, "Clear all"/"Show results", tap a look card → details.
→ **Data displayed:** searchable/filterable grid of looks with scores, occasions,
  tags, match badges.
→ **Data source:** mock const lists (`DiscoverLookData.forYouMock`/`trendingMock`,
  filter option consts).
→ **Required future backend data:** looks catalog (title, images, tags, occasions,
  scores, match-reason data) served from the backend; per-user personalization
  (For You) and trending feed; search/filter server-side or hydrated catalog.
→ **Related domain entities:** `Look`/`DiscoverLookData`, `MatchScoreDetails`,
  `RecommendationReason`, `EnsembleComponent`, `WardrobeAlternative`.

## 3.2 LookDetailsScreen

- **File path:** `lib/features/discover/presentation/look_details_screen.dart`
- **Route:** `RouteNames.lookDetails` → `/discover/look-details`
- **Entry point:** pushed by Discover with `extra: DiscoverLookData`; router
  renders `_missingDataScreen()` if null. Constructor requires `look`.
- **Main purpose:** single-look detail: match-score breakdown, reasons, tags,
  ensemble, wardrobe alternatives, save/share.
- **Main widgets/components:** `LookDetailCard`, `ScoreCategoryRow`, `ReasonRow`,
  `LookTag`, `ComponentRow`, `AlternativeSection` (feature widgets), `FansiBadge`,
  `FansiButton.primary/secondary`.
- **Data displayed:** `look` fields: match score + Fit/Color/Occasion/Creativity
  breakdown, recommendation reasons, style/fit tags + occasion, ensemble
  components (with Owned badge), wardrobe alternatives (replace suggestions with
  item match %).
- **Loading / Empty / Error states:** sections omitted when their lists are null;
  router-level error → `FansiErrorView` fallback. No in-screen loading.
- **Navigation destinations:** none (pop + SnackBars).
- **Widget tests:** `look_details_screen_test.dart`.
- **Dependencies:** `features/learning` (`addSavedLook` on "Save Look"); discover
  data/widgets; shared.

### LookDetailsScreen
→ **User action:** "Save Look"/favorite → `LearningService.addSavedLook` +
  SnackBar; "Share" → SnackBar; back → pop.
→ **Data displayed:** match-score breakdown, personalized reasons, tags, ensemble,
  wardrobe-alternative swaps.
→ **Data source:** passed-in `DiscoverLookData` (from Discover mocks); save writes
  a learning signal.
→ **Required future backend data:** look detail payload from catalog/recommender
  (scores, reasons, ensemble, alternatives grounded in the user's actual wardrobe
  from `UserModel.wardrobe`), saved-look persistence, real sharing.
→ **Related domain entities:** `Look`, `MatchScoreDetails`, `EnsembleComponent`,
  `WardrobeAlternative`, `savedLooks`.

---

# 4. Feature: Wardrobe

## 4.1 WardrobeScreen

- **File path:** `lib/features/wardrobe/presentation/wardrobe_screen.dart`
- **Route:** `RouteNames.wardrobe` → `/wardrobe` (fourth shell branch)
- **Entry point:** shell tab; reads `LearningService.instance.wardrobe` in
  `initState`, subscribes via listener. No extra.
- **Main purpose:** digital wardrobe dashboard — insight card, category chips,
  item grid, sticky "Add Item" bar.
- **Main widgets/components:** `WardrobeDashboardHeader`, `WardrobeInsightCard`
  (→ `FansiInsightCard`), `CategoryTile`, `ClothingItemCard` (→ `FansiMiniCard` +
  `FansiImageWell` + `_FavoriteHeart`), `FansiButton.primary` in a
  `bottomNavigationBar` bar.
- **Data displayed:** "My Wardrobe" header, style type ("Modern Minimalist"),
  favorites count, category chips (All/Tops/Bottoms/Outerwear/Footwear/Accessories)
  with live counts, item grid (`WardrobeItemData` name/category/color/material/
  isFavorite), `WardrobeInsightData.mock` ("Wardrobe Health"), empty state.
- **Loading / Empty / Error states:** empty — "No items in this category yet". No
  loading/error UI.
- **Navigation destinations:** `wardrobe-add-category` (awaits `WardrobeItemData`
  result), `wardrobe-item-details` (extra `WardrobeItemData`).
- **Widget tests:** `wardrobe_screen_test.dart`.
- **Dependencies:** `features/learning` (source of truth + `addItem` signal
  `item_added`), `shared/utils/user_session.dart` (sets `hasSavedWardrobeItem`),
  wardrobe data/widgets; shared.

### WardrobeScreen
→ **User action:** select category chip (filters grid); "View Analysis" →
  SnackBar; tap item → item details; "Add Item to Wardrobe" → add-category flow,
  then `LearningService.addItem` on returned item + SnackBar.
→ **Data displayed:** persisted item list with categories/favorites, category
  counts, AI wardrobe insight.
→ **Data source:** **Local** — `LearningService.instance.wardrobe` (seeded from
  `defaultWardrobe`, persisted via SharedPreferences); mock consts for
  categories/insight.
→ **Required future backend data:** wardrobe CRUD (server-persisted items, image
  uploads, categories as configuration), wardrobe analytics (health insight),
  sync across devices.
→ **Related domain entities:** `WardrobeEntry` (`UserModel.wardrobe`),
  `WardrobeItemData`, `WardrobeCategory`, `LearningSignal` (`item_added`).

## 4.2 AddWardrobeCategoryScreen

- **File path:** `lib/features/wardrobe/presentation/add_wardrobe_category_screen.dart`
- **Route:** `RouteNames.wardrobeAddCategory` → `/wardrobe/add-category`
- **Entry point:** pushed by WardrobeScreen; no extra; pops back a
  `WardrobeItemData`.
- **Main purpose:** category picker for the add-item flow.
- **Main widgets/components:** `_CategoryCard`, `GridView.builder`, `AppBar`.
- **Data displayed:** `AddItemConfig.categories` (Tops 12 types, Bottoms 9,
  Shoes 10, Layers 9 — each with icon + type count).
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `wardrobe-add-item` (extra `AddItemCategoryConfig`).
- **Widget tests:** `add_wardrobe_category_screen_test.dart`.
- **Dependencies:** wardrobe data; shared theme; `route_names`.

### AddWardrobeCategoryScreen
→ **User action:** tap a category → push add-item; forwards the returned item
  back to the wardrobe screen; back → pop.
→ **Data displayed:** 4 category cards with type counts.
→ **Data source:** mock const `AddItemConfig`.
→ **Required future backend data:** categories/types as backend configuration
  (config-driven, not hardcoded).
→ **Related domain entities:** `WardrobeCategory`.

## 4.3 AddWardrobeItemScreen

- **File path:** `lib/features/wardrobe/presentation/add_wardrobe_item_screen.dart`
- **Route:** `RouteNames.wardrobeAddItem` → `/wardrobe/add-item`
- **Entry point:** pushed by AddWardrobeCategory with `extra: AddItemCategoryConfig`
  (router shows `_missingDataScreen()` if null). Constructor requires `category`.
- **Main purpose:** form to create a wardrobe item (type, color, optional texture);
  pops a `WardrobeItemData`.
- **Main widgets/components:** `_SectionLabel`, `_buildCategoryIndicator`,
  `_buildChipRow`, `_buildColorChipRow`, error banner, `FilledButton.icon`.
- **Data displayed:** `category.types` (per category, e.g. Tops: T-Shirt,
  Button-Down…), `AddItemConfig.colors` (18 `ColorOption`s), `AddItemConfig.textures`
  (16 `TextureOption`s).
- **Loading / Empty / Error states:** error — validation banner "Please select a
  type and color." when Save tapped with incomplete selection.
- **Navigation destinations:** none (pops with result).
- **Widget tests:** `add_wardrobe_item_screen_test.dart`.
- **Dependencies:** wardrobe data; shared theme.

### AddWardrobeItemScreen
→ **User action:** select type + color (+ optional texture), "Save Item" →
  validates and pops a `WardrobeItemData` (id from `DateTime.now()`).
→ **Data displayed:** type/color/texture option chips per selected category.
→ **Data source:** mock const `AddItemConfig`; produced item passed via pop.
→ **Required future backend data:** item creation endpoint (name, category,
  color, material, image), category/option vocabulary from config.
→ **Related domain entities:** `WardrobeEntry` (created upstream in WardrobeScreen).

## 4.4 WardrobeItemDetailsScreen

- **File path:** `lib/features/wardrobe/presentation/wardrobe_item_details_screen.dart`
- **Route:** `RouteNames.wardrobeItemDetails` → `/wardrobe/item-details`
- **Entry point:** pushed by WardrobeScreen with `extra: WardrobeItemData` (router
  `_missingDataScreen()` if null). Constructor requires `item`.
- **Main purpose:** detail view of one wardrobe item; Edit/Add to Outfit/Delete
  actions (currently SnackBars only).
- **Main widgets/components:** `_buildVisualSection`, `_buildInfoCard`,
  `_buildMetadataCard` (+ `_metadataRow`), `_buildActionsSection`
  (`FilledButton.icon` / `OutlinedButton.icon`).
- **Data displayed:** `item` name, category (resolved via
  `WardrobeMockData.categories`), color swatch, material, favorite status.
- **Loading / Empty / Error states:** none (category resolution falls back to raw
  id).
- **Navigation destinations:** none (SnackBars only).
- **Widget tests:** `wardrobe_item_details_screen_test.dart`.
- **Dependencies:** wardrobe data; shared theme.

### WardrobeItemDetailsScreen
→ **User action:** "Edit Item" → SnackBar; "Add to Outfit" → SnackBar; "Delete" →
  SnackBar (no persistence change).
→ **Data displayed:** item visual placeholder, category, color/material, status.
→ **Data source:** passed-in `WardrobeItemData`.
→ **Required future backend data:** item edit/delete endpoints (real mutations of
  `UserModel.wardrobe`), add-to-outfit wiring into outfit builder, item images.
→ **Related domain entities:** `WardrobeItemData`/`WardrobeEntry`.

---

# 5. Feature: Stylist

## 5.1 StylistScreen

- **File path:** `lib/features/stylist/presentation/stylist_screen.dart`
- **Route:** `RouteNames.stylist` → `/stylist` (third shell branch)
- **Entry point:** shell tab. No extra.
- **Main purpose:** launcher hub — "Ask the Assistant" hero + 2×2 action grid.
- **Main widgets/components:** `FansivibeCard`; `_buildAssistantHero`
  (gradient InkWell), `_buildActionGrid` (`_buildGridTile`, `_buildHeroTile`).
- **Data displayed:** `StylistActionData.mockActions` (5 actions, defined inline in
  this file): scan_outfit "Scan My Outfit", build_outfit "Build Outfit", hairstyle
  "Hairstyle", grooming "Beard / Glasses", event "Event Planning" — each with
  title/subtitle/icon/accent color.
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `assistant`, `scan-outfit`, `build-outfit`,
  `hairstyle`, `grooming`, `events`.
- **Widget tests:** no dedicated file; `/stylist` used as initial location in
  `outfit_builder_screens_test.dart` and navigation covered by `widget_test.dart`.
- **Dependencies:** `route_names`, shared card. No learning.

### StylistScreen
→ **User action:** tap assistant hero → `/assistant`; tap an action tile →
  scan-outfit / build-outfit / hairstyle / grooming / events.
→ **Data displayed:** static stylist action grid.
→ **Data source:** mock const actions defined in-file.
→ **Required future backend data:** action/feature list as configuration
  (feature flags), personalized/active capability surfacing.
→ **Related domain entities:** none (launcher hub).

---

# 6. Feature: Outfit Scan

## 6.1 OutfitScanScreen

- **File path:** `lib/features/outfit_scan/presentation/outfit_scan_screen.dart`
- **Route:** `RouteNames.scanOutfit` → `/stylist/scan-outfit`
- **Entry point:** pushed by Stylist/Home screens. No extra. Implements
  `WidgetsBindingObserver`; camera init deferred post-frame and skipped in test
  binding.
- **Main purpose:** live camera outfit capture with readiness checks + capture →
  processing.
- **Main widgets/components:** real `CameraPreview` (package:camera) or
  `CameraPreviewPlaceholder` (feature widget), `CheckIndicator` rows,
  `_buildCameraErrorCard`, `_buildCaptureButton` ("View Analysis"),
  `_buildSecondaryActions` (Share/Rescan), "AI Analysis Active" badge.
- **Data displayed:** check indicators (Lighting pass, Framing pass, Posture fail
  + tip), camera state enum (`initial/loading/ready/permissionDenied/unavailable/
  error`), error messages.
- **Loading / Empty / Error states:** loading — placeholder + spinner badge;
  empty — "Camera unavailable" card; error — "Camera permission denied" / "Camera
  error" cards with "Scan Outfit" retry.
- **Navigation destinations:** `scan-processing` (extra `String?` image path).
- **Widget tests:** `outfit_scan_screen_test.dart`.
- **Dependencies:** `package:camera` (only feature using it); outfit_scan
  data/widgets; shared. No learning.

### OutfitScanScreen
→ **User action:** "View Analysis" → takes picture (or mock path in tests) →
  push scan-processing; "Rescan" → switch camera; "Share" → SnackBar; retry
  re-initializes camera.
→ **Data displayed:** camera preview, lighting/framing/posture checks, capture UI.
→ **Data source:** camera package (real) / placeholder (test); no app data.
→ **Required future backend data:** outfit image upload + server-side clothing
  detection/analysis; posture/lighting check results from processing.
→ **Related domain entities:** (future) `OutfitAnalysis` from image;
  `DetectedClothingItem`; `UserModel.wardrobe` matching.

## 6.2 OutfitProcessingScreen

- **File path:** `lib/features/outfit_scan/presentation/outfit_processing_screen.dart`
- **Route:** `RouteNames.scanProcessing` → `/stylist/scan-outfit/processing`
- **Entry point:** pushed by OutfitScan with `extra: String?` (constructor
  `capturedImagePath`).
- **Main purpose:** simulated stage-by-stage processing; auto-navigates to analysis.
- **Main widgets/components:** `ProcessingStageIndicator` (feature widget),
  circular progress/success indicator, `FansiButton.primary` "View Results".
- **Data displayed:** `ProcessingStage.mockStages` (5: detecting clothing items,
  analyzing proportions, analyzing colors, applying Style DNA, generating
  recommendations — each with ms duration).
- **Loading / Empty / Error states:** loading = the whole screen (timer-driven).
- **Navigation destinations:** `scan-analysis` (`replaceNamed`, extra
  `capturedImagePath`).
- **Widget tests:** `outfit_processing_screen_test.dart`.
- **Dependencies:** outfit_scan data/widgets; shared. No learning.

### OutfitProcessingScreen
→ **User action:** none (auto-advance); "View Results" when complete →
  scan-analysis.
→ **Data displayed:** 5-stage processing list with per-stage status.
→ **Data source:** mock const `ProcessingStage.mockStages`; timers.
→ **Required future backend data:** real processing job status/progress from the
  analysis service.
→ **Related domain entities:** `ProcessingStage` (future job), `OutfitAnalysis`.

## 6.3 OutfitAnalysisScreen

- **File path:** `lib/features/outfit_scan/presentation/outfit_analysis_screen.dart`
- **Route:** `RouteNames.scanAnalysis` → `/stylist/scan-outfit/processing/analysis`
- **Entry point:** `replaceNamed` from processing (extra `String?` image path).
- **Main purpose:** show structured analysis: sections with scores, detected
  items, save/generate actions.
- **Main widgets/components:** `AnalysisSectionCard`, `DetectedItemChip` (feature
  widgets), `FansiButton.primary/secondary`, share AppBar action.
- **Data displayed:** `OutfitAnalysisData.mock` (title "Modern Minimalist Look";
  6 `AnalysisSection`s: silhouette 0.88, balance 0.85, fit 0.92, volume 0.82,
  color_harmony 0.86, structure 0.84; 5 `DetectedClothingItem`s: blazer, crewneck,
  trousers, boots, belt).
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** none (pops); "Generate Look" → `LearningService.
  addSavedLook` (signal `look_saved`) + SnackBar.
- **Widget tests:** `outfit_analysis_screen_test.dart`.
- **Dependencies:** `features/learning` (`addSavedLook`); outfit_scan data/widgets;
  shared.

### OutfitAnalysisScreen
→ **User action:** "Save" → pop; "Generate Look" → `addSavedLook` + SnackBar;
  share → SnackBar.
→ **Data displayed:** analysis sections with scores + descriptions, detected
  items list, captured-path label.
→ **Data source:** mock const `OutfitAnalysisData.mock` + passed `capturedImagePath`.
→ **Required future backend data:** server-side outfit analysis result (sections,
  scores, detected items), save-to-wardrobe/looks persistence.
→ **Related domain entities:** `OutfitAnalysis`, `AnalysisSection`,
  `DetectedClothingItem`, `savedLooks`.

---

# 7. Feature: Outfit Builder

## 7.1 BuildOutfitScreen

- **File path:** `lib/features/outfit_builder/presentation/build_outfit_screen.dart`
- **Route:** `RouteNames.buildOutfit` → `/stylist/build-outfit`
- **Entry point:** pushed by Stylist/Home/EventDetails. No extra.
- **Main purpose:** preference collection (occasion, mood, fit, color palette).
- **Main widgets/components:** `OptionSection` / `OptionChip` (feature widgets),
  `FansiButton.primary` "Build Outfit" (disabled until all four selected).
- **Data displayed:** `BuilderOption.occasionOptions` (5), `moodOptions` (4),
  `fitOptions` (3), `colorPaletteOptions` (3), each with icon + description.
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `outfit-generation` (extra `Map<String,String>`:
  occasion/mood/fit/colorPalette).
- **Widget tests:** `outfit_builder_screens_test.dart`.
- **Dependencies:** outfit_builder data/widgets; shared. No learning.

### BuildOutfitScreen
→ **User action:** select one chip per section; "Build Outfit" (when all selected)
  → outfit-generation with preferences as route extra.
→ **Data displayed:** 4 preference sections of option chips.
→ **Data source:** mock const `BuilderOption` lists; selections passed via extra.
→ **Required future backend data:** preference vocabulary as configuration;
  persist preferences; feed to outfit generation.
→ **Related domain entities:** (future) `OutfitPreferences`/`UserModel` style
  preferences.

## 7.2 OutfitGenerationScreen

- **File path:** `lib/features/outfit_builder/presentation/outfit_generation_screen.dart`
- **Route:** `RouteNames.outfitGeneration` → `/stylist/build-outfit/generation`
- **Entry point:** pushed by BuildOutfit with `extra: Map<String,String>`
  (router `_missingDataScreenWithText("Missing outfit preferences.")` if null).
  Constructor takes occasion/mood/fit/colorPalette.
- **Main purpose:** simulated generation sequence + preference summary.
- **Main widgets/components:** `_buildSelectionSummary` ("Your Preferences" + 4
  `_buildPreferenceChip`), `_buildStageIndicator` rows, circular progress/success,
  `FansiButton.primary` "View Generation".
- **Data displayed:** `GenerationStage.mockStages` (5: analyzing wardrobe items,
  matching occasion preferences, applying Style DNA, selecting complementary
  pieces, generating recommendations); preference labels resolved via `_labelForId`.
- **Loading / Empty / Error states:** loading = whole screen (timer-driven).
- **Navigation destinations:** `outfit-recommendation` (`replaceNamed`).
- **Widget tests:** `outfit_builder_screens_test.dart`.
- **Dependencies:** outfit_builder data; shared. No learning.

### OutfitGenerationScreen
→ **User action:** none (auto-advance); "View Generation" when complete →
  outfit-recommendation.
→ **Data displayed:** preference summary + 5-stage progress.
→ **Data source:** mock const `GenerationStage.mockStages` + passed preference
  strings.
→ **Required future backend data:** real outfit-generation job/progress; generation
  grounded in the user's wardrobe (`UserModel.wardrobe`).
→ **Related domain entities:** `GenerationStage` (future job), `OutfitPreferences`,
  `WardrobeEntry`.

## 7.3 OutfitRecommendationScreen

- **File path:** `lib/features/outfit_builder/presentation/outfit_recommendation_screen.dart`
- **Route:** `RouteNames.outfitRecommendation` → `/stylist/build-outfit/generation/recommendation`
- **Entry point:** `replaceNamed` from generation. No extra.
- **Main purpose:** show generated outfit: hero, match score, components, reasons,
  metrics, impact/improvement, save/regenerate.
- **Main widgets/components:** `FansiHeroCard` + `FansiImageWell`, `ScoreCircle`,
  `OutfitComponentCard`, `MetricCard` (→ `FansiInsightCard`), `FansiInsightCard`
  (impact/improvement), `FansiButton.primary/secondary`.
- **Data displayed:** `OutfitRecommendation.mock` ("Refined Office Ensemble",
  match 91%, Office/Classic/Warm; 5 components with color/material/reason; 4
  reasons; colorHarmony/bodyFit/occasionMatch; styleScoreImpact "+3 Style Score";
  improvementSuggestion).
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** none (SnackBars only).
- **Widget tests:** `outfit_builder_screens_test.dart`.
- **Dependencies:** outfit_builder data/widgets; shared cards. No learning signals
  (despite SnackBar copy saying "Look saved to wardrobe").

### OutfitRecommendationScreen
→ **User action:** per-component "Replace" → SnackBar; "Save Outfit" → SnackBar;
  "Regenerate" → SnackBar.
→ **Data displayed:** recommendation hero, score, 5 components, reasons, metrics,
  impact/improvement cards.
→ **Data source:** mock const `OutfitRecommendation.mock`.
→ **Required future backend data:** real generation result (components from the
  user's wardrobe, scores, reasons); persist saved outfit / regenerate calls;
  connect "Save Outfit" to `savedLooks`.
→ **Related domain entities:** `OutfitRecommendation`, `OutfitComponent`,
  `savedLooks` (future write), `WardrobeEntry`.

---

# 8. Feature: Hairstyle

## 8.1 FaceScanScreen

- **File path:** `lib/features/hairstyle/presentation/face_scan_screen.dart`
- **Route:** `RouteNames.hairstyle` → `/stylist/hairstyle`
- **Entry point:** pushed by Stylist / first-time home screens / assistant.
  No extra.
- **Main purpose:** pre-scan camera preview with face-detection checks + "Scan
  Face" CTA.
- **Main widgets/components:** `FacePreviewPlaceholder` (oval guide, "Face
  Detection Active" spinner), `HairstyleCheckIndicator`, `FansiButton.primary`.
- **Data displayed:** `FaceScanCheck.mockChecks` (Lighting pass, Distance pass,
  Alignment fail + "Center your face in the frame").
- **Loading / Empty / Error states:** decorative spinner badge only.
- **Navigation destinations:** `hairstyle-processing`.
- **Widget tests:** `hairstyle_scan_screen_test.dart`.
- **Dependencies:** hairstyle data/widgets; shared. No learning.

### FaceScanScreen
→ **User action:** "Scan Face" → hairstyle-processing; back → pop.
→ **Data displayed:** simulated face-preview with detection checks.
→ **Data source:** mock const `FaceScanCheck.mockChecks`.
→ **Required future backend data:** real face image capture + face-shape/skin-tone
  analysis service; check results from processing.
→ **Related domain entities:** (future) `FaceProfile` (`UserModel.face`).

## 8.2 FaceProcessingScreen

- **File path:** `lib/features/hairstyle/presentation/face_processing_screen.dart`
- **Route:** `RouteNames.hairstyleProcessing` → `/stylist/hairstyle/processing`
- **Entry point:** pushed by FaceScan. No extra.
- **Main purpose:** simulated face-analysis stages; auto-navigates to results.
- **Main widgets/components:** circular progress/success, `HairstyleStageIndicator`,
  `FansiButton.primary` "View Results".
- **Data displayed:** `HairstyleProcessingStage.mockStages` (5: detecting face
  features, analyzing face shape, analyzing skin tone, applying Style DNA,
  ranking hairstyle recommendations).
- **Loading / Empty / Error states:** loading = whole screen (timer-driven).
- **Navigation destinations:** `hairstyle-result` (`replaceNamed`).
- **Widget tests:** `hairstyle_processing_screen_test.dart`.
- **Dependencies:** hairstyle data/widgets; shared. No learning.

### FaceProcessingScreen
→ **User action:** none (auto-advance); "View Results" → hairstyle-result.
→ **Data displayed:** 5-stage face-analysis progress.
→ **Data source:** mock const `HairstyleProcessingStage.mockStages`.
→ **Required future backend data:** real face-analysis job/status; write
  `FaceProfile` back to the user model.
→ **Related domain entities:** `FaceProfile`, `HairstyleProcessingStage` (future
  job).

## 8.3 HairstyleResultScreen

- **File path:** `lib/features/hairstyle/presentation/hairstyle_result_screen.dart`
- **Route:** `RouteNames.hairstyleResult` → `/stylist/hairstyle/processing/result`
- **Entry point:** `replaceNamed` from processing. No extra.
- **Main purpose:** hair analysis summary: style profile, top recommendation,
  alternatives, actions.
- **Main widgets/components:** `HairstyleCard` (→ `FansiHeroCard` + `FansiImageWell`
  + `FansiBadge`), `FansiButton.primary/secondary`.
- **Data displayed:** `HairstyleAnalysisResult.mock`: face shape Oval, skin tone
  Warm Medium, Style DNA Modern Classic•Minimalist•Structured; top rec "Textured
  Quiff" 94%; 3 alternatives (Classic Pompadour 87, Side Part 82, Brushed Up
  Undercut 78).
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `hairstyle-details` (extra `HairstyleRecommendation`),
  `hairstyle` ("Try Another", replace).
- **Widget tests:** `hairstyle_result_screen_test.dart`.
- **Dependencies:** hairstyle data; shared. "Save Style" is SnackBar-only (no
  learning write).

### HairstyleResultScreen
→ **User action:** tap top/alternative card → hairstyle-details; "Try Another" →
  hairstyle (rescan); "Save Style" → SnackBar.
→ **Data displayed:** style profile, top recommendation with match %, alternatives.
→ **Data source:** mock const `HairstyleAnalysisResult.mock`.
→ **Required future backend data:** hairstyle recommendations grounded in real
  `FaceProfile`; persist saved style to `UserModel`.
→ **Related domain entities:** `HairstyleRecommendation`, `FaceProfile`,
  (future) saved style.

## 8.4 HairstyleDetailsScreen

- **File path:** `lib/features/hairstyle/presentation/hairstyle_details_screen.dart`
- **Route:** `RouteNames.hairstyleDetails` → `/stylist/hairstyle/processing/result/details`
- **Entry point:** pushed by result screen with `extra: HairstyleRecommendation`
  (router returns `const SizedBox()` if null). Constructor requires
  `recommendation`.
- **Main purpose:** detail view of one hairstyle: score, description, reasons,
  styling tips, maintenance, best-for.
- **Main widgets/components:** `FansiButton.primary` "Try This Style"; private
  `_buildDescriptionCard`, `_buildReasonsSection`, `_buildInfoCard`.
- **Data displayed:** `recommendation` name/bestFor/matchScore/icon/description/
  reasons/stylingTips/maintenance/bestFor.
- **Loading / Empty / Error states:** router-level only (SizedBox when extra null).
- **Navigation destinations:** none (SnackBar only).
- **Widget tests:** `hairstyle_details_screen_test.dart`.
- **Dependencies:** hairstyle data; shared. No learning.

### HairstyleDetailsScreen
→ **User action:** "Try This Style" → SnackBar "saved to profile"; back → pop.
→ **Data displayed:** full recommendation details (reasons, tips, maintenance,
  best-for).
→ **Data source:** passed-in `HairstyleRecommendation`.
→ **Required future backend data:** full recommendation payload from backend;
  actually persist the "saved to profile" action.
→ **Related domain entities:** `HairstyleRecommendation`.

---

# 9. Feature: Grooming

## 9.1 GroomingInputScreen

- **File path:** `lib/features/grooming/presentation/grooming_input_screen.dart`
- **Route:** `RouteNames.grooming` → `/stylist/grooming`
- **Entry point:** pushed by Stylist / assistant. No extra.
- **Main purpose:** collect grooming profile (face shape, beard style, density,
  color) via chips.
- **Main widgets/components:** `GroomingOptionSection` / `GroomingOptionChip`
  (feature widgets), `FansiButton.primary` "Analyze Style" (disabled until all
  four selected).
- **Data displayed:** `GroomingOption.faceShapeOptions` (6), `beardStyleOptions`
  (6), `densityOptions` (3), `colorOptions` (6) — each with icon/label/description.
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `grooming-processing` (extra `Map<String,String>`:
  faceShape/beardStyle/beardDensity/beardColor).
- **Widget tests:** `grooming_input_screen_test.dart`.
- **Dependencies:** grooming data/widgets; shared. No learning.

### GroomingInputScreen
→ **User action:** select chips across 4 sections; "Analyze Style" →
  grooming-processing with selected labels as route extra.
→ **Data displayed:** 4 sections of option chips with descriptions.
→ **Data source:** mock const `GroomingOption` lists; ephemeral selection state.
→ **Required future backend data:** grooming profile persistence
  (write to `UserModel`), option vocabulary as configuration.
→ **Related domain entities:** `FaceProfile` (future grooming fields),
  (future) `GroomingPreferences`.

## 9.2 GroomingProcessingScreen

- **File path:** `lib/features/grooming/presentation/grooming_processing_screen.dart`
- **Route:** `RouteNames.groomingProcessing` → `/stylist/grooming/processing`
- **Entry point:** pushed by input with `extra: Map<String,String>` (router
  `_missingDataScreenWithText("Missing grooming data.")` if null). Constructor
  takes the four label strings.
- **Main purpose:** simulated grooming-analysis stages; forwards inputs to result.
- **Main widgets/components:** circular progress/success, `GroomingStageIndicator`,
  `FansiButton.primary` "View Results".
- **Data displayed:** `GroomingProcessingStage.mockStages` (5: analyzing face
  shape, evaluating facial features, matching beard styles, selecting eyewear
  options, ranking grooming recommendations).
- **Loading / Empty / Error states:** loading = whole screen (timer-driven).
- **Navigation destinations:** `grooming-result` (`replaceNamed`, same Map extra).
- **Widget tests:** `grooming_processing_screen_test.dart`.
- **Dependencies:** grooming data/widgets; shared. No learning.

### GroomingProcessingScreen
→ **User action:** none (auto-advance); "View Results" → grooming-result.
→ **Data displayed:** 5-stage progress (inputs not rendered, only forwarded).
→ **Data source:** mock const `GroomingProcessingStage.mockStages`.
→ **Required future backend data:** real grooming-analysis job/status.
→ **Related domain entities:** `GroomingProcessingStage` (future job),
  `GroomingPreferences`.

## 9.3 GroomingResultScreen

- **File path:** `lib/features/grooming/presentation/grooming_result_screen.dart`
- **Route:** `RouteNames.groomingResult` → `/stylist/grooming/processing/result`
- **Entry point:** `replaceNamed` from processing (Map extra; `_missingDataScreenWithText`
  if null). Constructor takes the four label strings.
- **Main purpose:** grooming analysis summary: feature profile, match score,
  beard + eyewear recommendations, why-it-works, specs, alternatives, actions.
- **Main widgets/components:** `GroomingRecommendationCard` (uses
  `scoreColorFromDouble`), `FansiButton.primary/secondary`.
- **Data displayed:** feature profile rows (from constructor strings), 92% match
  ("Structured Goatee"), primary beard rec card, eyewear suggestion (Rectangular
  Frames), 4 reasons, grooming specs (beard length, cheek line, eyewear frame),
  3 alternatives (Classic Stubble 85, Cropped Full Beard 79, Sleek Moustache 72).
- **Loading / Empty / Error states:** router-level only (missing-data fallback).
- **Navigation destinations:** `grooming-details` (extra `GroomingRecommendation`),
  `grooming` ("Try Another", replace).
- **Widget tests:** `grooming_result_screen_test.dart`.
- **Dependencies:** grooming data/widgets; `shared/utils/score_colors.dart`;
  shared. "Save Look" is SnackBar-only.

### GroomingResultScreen
→ **User action:** tap rec card → grooming-details; "Try Another" → grooming;
  "Save Look" → SnackBar.
→ **Data displayed:** feature profile, match score, beard + eyewear recs, specs,
  alternatives.
→ **Data source:** mock const `GroomingAnalysisResult.mock` + constructor strings.
→ **Required future backend data:** grooming recommendations grounded in face
  profile; persist saved result to `UserModel`.
→ **Related domain entities:** `GroomingRecommendation`, `GroomingAnalysisResult`,
  (future) saved grooming profile.

## 9.4 GroomingDetailsScreen

- **File path:** `lib/features/grooming/presentation/grooming_details_screen.dart`
- **Route:** `RouteNames.groomingDetails` → `/stylist/grooming/processing/result/details`
- **Entry point:** pushed by result screen with `extra: GroomingRecommendation`
  (router `_missingDataScreen()` if null). Constructor requires `recommendation`.
- **Main purpose:** detail view of one grooming recommendation.
- **Main widgets/components:** `FansiButton.primary` "Try This Look"; private
  `_buildDescriptionCard`, `_buildReasonsSection`, `_buildSpecCard`, `_buildInfoCard`.
- **Data displayed:** `recommendation` name/bestFor/matchScore/icon/description/
  reasons, spec cards (beard length, cheek line, eyewear frame, eyewear
  recommendation), info cards (styling tips, maintenance, best-for).
- **Loading / Empty / Error states:** router-level only (`_missingDataScreen()`).
- **Navigation destinations:** none (SnackBar only).
- **Widget tests:** `grooming_details_screen_test.dart`.
- **Dependencies:** grooming data; shared. No learning.

### GroomingDetailsScreen
→ **User action:** "Try This Look" → SnackBar "saved to profile"; back → pop.
→ **Data displayed:** full grooming recommendation details.
→ **Data source:** passed-in `GroomingRecommendation`.
→ **Required future backend data:** full recommendation payload; persist "saved to
  profile".
→ **Related domain entities:** `GroomingRecommendation`.

---

# 10. Feature: Events

## 10.1 EventListScreen

- **File path:** `lib/features/events/presentation/event_list_screen.dart`
- **Route:** `RouteNames.events` → `/stylist/events`
- **Entry point:** pushed by Stylist / first-time home screens. No extra.
- **Main purpose:** list upcoming events with outfit-readiness status.
- **Main widgets/components:** `EventCard` (feature widget), `FansiButton.primary`
  "Add event", AppBar add action, `_buildEmptyState`.
- **Data displayed:** `_events` (in-memory `List<UserEvent>` seeded from
  `UserEvent.mockEvents`: Company Gala/Formal/Ready, Weekend Brunch/Casual/Pending,
  Client Presentation/Business/Pending, Anniversary Dinner/Date Night/Ready) —
  name, `date • time`, eventType name, Ready/Pending badge.
- **Loading / Empty / Error states:** empty — "No events yet / Tap + to add your
  first event".
- **Navigation destinations:** `event-add` (awaits `UserEvent` result),
  `event-details` (extra `UserEvent`).
- **Widget tests:** `event_screens_test.dart`.
- **Dependencies:** events data/widgets; shared. **Events are ephemeral — never
  persisted.**

### EventListScreen
→ **User action:** "+"/"Add event" → event-add, then append returned event to the
  in-memory list; tap card → event-details.
→ **Data displayed:** event list with type + Ready/Pending outfit status.
→ **Data source:** mock const seed copied into widget state; new events ephemeral.
→ **Required future backend data:** event CRUD persistence, event outfit-recommendation
  status from backend.
→ **Related domain entities:** `UserEvent`, (future) event calendar; occasion
  signal (`addPreferredOccasion` via AddEvent).

## 10.2 AddEventScreen

- **File path:** `lib/features/events/presentation/add_event_screen.dart`
- **Route:** `RouteNames.eventAdd` → `/stylist/events/add`
- **Entry point:** pushed by EventList; pops back a `UserEvent`. No extra.
- **Main purpose:** create-event form (name, date, time, type); records occasion
  learning signal.
- **Main widgets/components:** `TextField`, `_buildPickerTile`, `showDatePicker` /
  `showTimePicker` (dark-themed), `_buildEventTypeGrid`, `FansiButton.primary`.
- **Data displayed:** form fields; `EventType.mockTypes` (8 types: Casual, Formal,
  Business, Date Night, Party, Travel, Workout, Other).
- **Loading / Empty / Error states:** none (button disabled until valid).
- **Navigation destinations:** none (pops with `UserEvent`).
- **Widget tests:** `event_screens_test.dart`.
- **Dependencies:** `features/learning` (`LearningService.addPreferredOccasion`,
  signal `occasion_preferred`) on add; events data; shared.

### AddEventScreen
→ **User action:** type name, pick date/time, pick type, "Add Event" →
  `addPreferredOccasion` + pop `UserEvent` back to list.
→ **Data displayed:** event form + 8-type grid.
→ **Data source:** ephemeral form state + mock const `EventType.mockTypes`.
→ **Required future backend data:** event creation endpoint; date/time/type
  vocabulary as configuration; persist preferred occasions server-side.
→ **Related domain entities:** `UserEvent`, `LearningSignal` (`occasion_preferred`),
  (future) `UserModel.preferredOccasions`.

## 10.3 EventDetailsScreen

- **File path:** `lib/features/events/presentation/event_details_screen.dart`
- **Route:** `RouteNames.eventDetails` → `/stylist/events/details`
- **Entry point:** pushed by EventList with `extra: UserEvent` (router
  `_missingDataScreen()` if null). Constructor requires `event`.
- **Main purpose:** event details + outfit status; generate outfit / edit actions.
- **Main widgets/components:** `FansiButton.primary/secondary`; `_buildInfoCard`
  (+ `_infoRow`), `_buildStatusCard`.
- **Data displayed:** `event` name/date/time/type icon, Ready/Pending outfit status
  card.
- **Loading / Empty / Error states:** router-level only.
- **Navigation destinations:** `build-outfit`.
- **Widget tests:** `event_screens_test.dart`.
- **Dependencies:** events data; `route_names` → outfit_builder navigation; shared.
  No learning.

### EventDetailsScreen
→ **User action:** "Generate Outfit" → build-outfit; "Edit Event" → SnackBar.
→ **Data displayed:** event info + outfit-recommendation status.
→ **Data source:** passed-in `UserEvent`.
→ **Required future backend data:** event detail payload, real outfit-recommendation
  status + generation grounded in occasion.
→ **Related domain entities:** `UserEvent`, `OutfitPreferences` (via build-outfit).

---

# 11. Feature: Profile

## 11.1 ProfileScreen

- **File path:** `lib/features/profile/presentation/profile_screen.dart`
- **Route:** `RouteNames.profile` → `/profile` (fifth shell branch)
- **Entry point:** shell tab; also `goNamed(profile)` from assistant. No extra.
- **Main purpose:** profile dashboard — stats, achievements, style DNA, saved-look
  previews, Account menu.
- **Main widgets/components:** `ProfileHeroCard`, `AchievementBar`, `StyleDnaCard`
  (→ 4 stacked `FansiInsightCard`s), `SavedLooksRow`, `ProfileMenuCard` (feature
  widgets), `FansivibeCard`.
- **Data displayed:** `ProfileData.mock` (Alex/@alex_styles, Lvl 4 Style Seeker,
  XP 3200/5000, Style Score 84, Global Rank #128, DNA rows Skin Tone Warm Medium /
  Face Shape Oval / Body Type Athletic / Style Type Modern Minimalist, achievements
  4/6, saved-look previews 87/82/91/85, menu: Preferences/Saved Looks/Subscription/
  Support/Settings/Sign Out).
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** `profile-preferences`, `profile-saved-looks`,
  `profile-subscription`, `profile-support`, `profile-settings` (pushNamed).
- **Widget tests:** `profile_screen_test.dart`, `widget_test.dart`.
- **Dependencies:** profile data/widgets; shared. No LearningService (profile data
  is **not** backed by `UserModel`).

### ProfileScreen
→ **User action:** tap menu card → corresponding sub-screen; "View All" →
  saved-looks; "Sign Out" → SnackBar only.
→ **Data displayed:** user stats, achievements, style DNA, saved-look previews,
  account menu.
→ **Data source:** mock const `ProfileData.mock`.
→ **Required future backend data:** real profile from `UserModel`/backend (name,
  avatar, level, XP, score, rank), DNA from analysis, achievements, saved looks
  from persisted data, real sign-out.
→ **Related domain entities:** `UserModel`, `ProfileData` (future), `savedLooks`,
  `StyleDnaData`.

## 11.2 PreferencesScreen

- **File path:** `lib/features/profile/presentation/preferences_screen.dart`
- **Route:** `RouteNames.profilePreferences` → `/profile/preferences`
- **Entry point:** pushed by ProfileScreen. No extra.
- **Main purpose:** edit style preferences via option chips (ephemeral).
- **Main widgets/components:** `FansivibeCard`, `_PreferenceTile` + chip rows.
- **Data displayed:** `ProfileMockData.stylePreferences` (4 sections: Style Vibe,
  Color Palette, Fit Preference, Occasion Focus).
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** none.
- **Widget tests:** `profile_screens_test.dart`.
- **Dependencies:** profile data; shared.

### PreferencesScreen
→ **User action:** tap chip to change selection (local state); back → pop.
→ **Data displayed:** 4 preference sections with selectable options.
→ **Data source:** mock const copied to local state.
→ **Required future backend data:** persist preferences to `UserModel`/backend;
  preferences used by recommendation engines.
→ **Related domain entities:** `PreferenceOption`, (future) `UserModel` style
  preferences.

## 11.3 SavedLooksScreen

- **File path:** `lib/features/profile/presentation/saved_looks_screen.dart`
- **Route:** `RouteNames.profileSavedLooks` → `/profile/saved-looks`
- **Entry point:** pushed by ProfileScreen. No extra.
- **Main purpose:** full list of saved look cards.
- **Main widgets/components:** `_SavedLookCard` → `FansiHeroCard` + `FansiImageWell`
  + `FansiBadge`.
- **Data displayed:** `ProfileMockData.savedLooks` (6 `SavedLookDetail`: Modern
  Minimalist 87, Weekend Casual 82, Smart Business 91, Date Night 85, Summer
  Breeze, Office Ready — with dates + joined item strings).
- **Loading / Empty / Error states:** none (always 6).
- **Navigation destinations:** none.
- **Widget tests:** `profile_screens_test.dart`.
- **Dependencies:** profile data; shared cards.

### SavedLooksScreen
→ **User action:** back → pop (cards not tappable).
→ **Data displayed:** saved-look cards with score + items + date.
→ **Data source:** mock const `ProfileMockData.savedLooks` (**not**
  `UserModel.savedLooks`).
→ **Required future backend data:** saved looks from persisted `UserModel.savedLooks`
  / backend; item images; detail navigation.
→ **Related domain entities:** `SavedLookDetail`/`SavedLookPreview`, `savedLooks`
  (currently disconnected from the persisted model).

## 11.4 SubscriptionScreen

- **File path:** `lib/features/profile/presentation/subscription_screen.dart`
- **Route:** `RouteNames.profileSubscription` → `/profile/subscription`
- **Entry point:** pushed by ProfileScreen. No extra.
- **Main purpose:** show Free/Premium/Elite plans + subscribe CTA.
- **Main widgets/components:** `_PlanCard` → `FansivibeCard` (`CardVariant.high`
  for popular), `ElevatedButton`, `Popular` badge.
- **Data displayed:** `ProfileMockData.plans` (Free $0, Premium $9.99 Popular,
  Elite $19.99 — each with feature lists); footer "Cancel anytime · No hidden
  fees".
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** none.
- **Widget tests:** `profile_screens_test.dart`.
- **Dependencies:** profile data; shared.

### SubscriptionScreen
→ **User action:** "Current Plan"/"Subscribe" buttons → no-op; back → pop.
→ **Data displayed:** 3 plan cards with pricing + features.
→ **Data source:** mock const `ProfileMockData.plans`.
→ **Required future backend data:** real subscription plans/config from backend,
  entitlement gating, payment flow.
→ **Related domain entities:** `SubscriptionPlan` (future), entitlements.

## 11.5 SupportScreen

- **File path:** `lib/features/profile/presentation/support_screen.dart`
- **Route:** `RouteNames.profileSupport` → `/profile/support`
- **Entry point:** pushed by ProfileScreen. No extra.
- **Main purpose:** help-center topics + contact row.
- **Main widgets/components:** `_SupportTopicTile`, `FansivibeCard`, `ListTile`.
- **Data displayed:** `ProfileMockData.topics` (6 `SupportTopic`: Getting Started,
  Style Score, Wardrobe Management, Account & Privacy, Report a Bug, Contact Us) +
  "Send us a message" contact card.
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** none (tiles are no-ops).
- **Widget tests:** `profile_screens_test.dart`.
- **Dependencies:** profile data; shared.

### SupportScreen
→ **User action:** tap topic / contact → no-op; back → pop.
→ **Data displayed:** support topics + contact card.
→ **Data source:** mock const `ProfileMockData.topics`.
→ **Required future backend data:** help-center content (topics/FAQs) from backend;
  real contact/help-desk submission.
→ **Related domain entities:** `SupportTopic` (future content).

## 11.6 SettingsScreen

- **File path:** `lib/features/profile/presentation/settings_screen.dart`
- **Route:** `RouteNames.profileSettings` → `/profile/settings`
- **Entry point:** pushed by ProfileScreen. No extra.
- **Main purpose:** app settings toggles + display rows.
- **Main widgets/components:** `_SettingsTile` (label/description + `Switch` or
  value row), `FansivibeCard`, `Divider`.
- **Data displayed:** `ProfileMockData.settingsGroups` (6 `SettingsItem`:
  Notifications on, Sound Effects off, Haptic Feedback on, Theme Dark, Units
  Imperial, Data Saver off).
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** none.
- **Widget tests:** `profile_screens_test.dart`.
- **Dependencies:** profile data; shared.

### SettingsScreen
→ **User action:** toggle switches (local state); back → pop.
→ **Data displayed:** 6 settings rows with switch/value.
→ **Data source:** mock const copied to local state.
→ **Required future backend data:** persist settings (device preferences) and
  sync where relevant.
→ **Related domain entities:** `SettingsItem` (future persisted preferences).

---

# 12. Feature: Assistant

## 12.1 AssistantScreen

- **File path:** `lib/features/assistant/presentation/assistant_screen.dart`
- **Route:** `RouteNames.assistant` → `/assistant` (top-level GoRoute, **outside**
  the shell).
- **Entry point:** `pushNamed(assistant)` from `FloatingAssistantButton` (FAB on
  every tab). Constructor `AssistantService? service` injectable for tests; when
  null, creates `AssistantService()..attachLearning(LearningService.instance)`.
  No `state.extra`.
- **Main purpose:** AI stylist chat — rich suggestion cards, clarification chips,
  navigation buttons; backend-first with offline fallback.
- **Main widgets/components:** `MessageBubble`, `SuggestionCardView`, `_TypingDots`
  (feature widgets), `TextField` + `IconButton.filled` input bar, `_buildEmptyState`
  (5 suggestion chips), auto-scroll `ListView.builder`.
- **Data displayed:** `_service.messages` (`List<AssistantMessage>`: role, text,
  `cards`, `clarifications`, `navigation`, `pending`); empty-state "Your AI
  stylist" + suggestion chips ("What should I wear to a date?", "Best hairstyle
  for me?", "Grooming tips", "Show my wardrobe", "Open my wardrobe").
- **Loading / Empty / Error states:** loading — pending assistant message renders
  `_TypingDots`; empty — full empty-state; error — none in UI (backend failure
  silently falls back to `OfflineAssistant`).
- **Navigation destinations:** `goNamed` via `AssistantRoutes.routeFor(...)`
  mapping card actions / navigation requests → `build-outfit`, `hairstyle`,
  `grooming`, `wardrobe`, `stylist`, `daily-outfit`, `discover`, `home`, `profile`
  (default `stylist`). Uses `goNamed` to avoid shell page-key duplication.
- **Widget tests:** `assistant_screen_test.dart` (incl. FAB/navigation regression),
  `offline_assistant_test.dart` (service logic).
- **Dependencies:** `features/learning` (`LearningService.instance` via attach;
  records `assistant_message`, `suggestion_opened`, `assistant_navigation`);
  `features/assistant` data/domain (client, offline assistant, service, routes,
  widgets); `package:http` (via AssistantClient); OfflineAssistant reads
  hairstyle/grooming/wardrobe mock data for grounding.

### AssistantScreen
→ **User action:** send text (submit/send button/empty-state chips); tap a
  suggestion card "Open" → `goNamed(routeFor(card.action))` + signal; tap a
  clarification chip → resend; tap navigation button → `goNamed` + signal; back →
  `Navigator.maybePop()`.
→ **Data displayed:** chat messages with cards (kind/title/subtitle/score/items/
  action), clarification chips, navigation buttons, typing indicator, suggestions.
→ **Data source:** **Remote** — `AssistantClient.chat` → `POST
  $ASSISTANT_BASE_URL/v1/assistant/chat` (default `http://localhost:8000`,
  12s timeout; null on failure) → **Local fallback** — `OfflineAssistant.replyFor`
  grounded in `LearningRepository` context (`UserModel` snapshot: wardrobe, face,
  savedLooks, preferredOccasions).
→ **Required future backend data:** real user store (auth, `UserModel` server-side)
  so the engine can ground in persisted data; conversation persistence; server
  recommendation catalog replacing the client mock grounding.
→ **Related domain entities:** `AssistantMessage`/`AssistantReply`,
  `SuggestionCard`, `ClarificationOption`, `NavigationRequest`, `UserContext`
  (from `UserModel`), `LearningSignal` (`assistant_message`/`suggestion_opened`/
  `assistant_navigation`).

---

# 13. Cross-cutting: Router Shell

## 13.1 RouterShell (app shell)

- **File path:** `lib/app/router/router_shell.dart`
- **Route:** none of its own — the `builder` of `StatefulShellRoute.indexedStack`;
  hosts 5 branches: `/home`, `/discover`, `/stylist`, `/wardrobe`, `/profile`.
- **Entry point:** constructed by the shell route with `StatefulNavigationShell`.
- **Main purpose:** 5-tab app chrome (bottom `NavigationBar` + assistant FAB).
- **Main widgets/components:** `NavigationBar` (5 `NavigationDestination`s),
  `FloatingAssistantButton`, private `_GlowingIcon` (glow on selected icon only,
  `indicatorColor: Colors.transparent`).
- **Data displayed:** `navigationShell.currentIndex`; destinations Home/Discover/
  Stylist/Wardrobe/Profile.
- **Loading / Empty / Error states:** none.
- **Navigation destinations:** pushes `/assistant` via FAB; `goBranch` switches
  tabs (state preserved via IndexedStack).
- **Widget tests:** `widget_test.dart` (shell render, tab switching, navigation);
  most screen tests boot through the shell at `/home`.
- **Dependencies:** `shared/components/floating_assistant_button.dart` +
  `route_names`; shared theme.

### RouterShell
→ **User action:** tap tab → `goBranch`; tap FAB → push `/assistant`.
→ **Data displayed:** current tab index + 5 destinations.
→ **Data source:** none (navigation state).
→ **Required future backend data:** none (chrome only; may surface notification/
  badge state later).
→ **Related domain entities:** none.

## 13.2 Route-level missing-data fallback screens

- **File path:** `lib/app/router/app_router.dart`
- **Route:** not user-facing routes — builders return `_missingDataScreen()`
  (`FansiErrorView`, "Could not load the requested content. Please go back and try
  again.") or `_missingDataScreenWithText(label)`.
- **Used when `state.extra` is null for:** `look-details` (DiscoverLookData),
  `wardrobe-add-item` (AddItemCategoryConfig), `wardrobe-item-details`
  (WardrobeItemData), `event-details` (UserEvent), `grooming-details`
  (GroomingRecommendation); `outfit-generation` ("Missing outfit preferences."),
  `grooming-processing` / `grooming-result` ("Missing grooming data.").
  `hairstyle-details` returns `const SizedBox()` instead.
- **Data source:** none (static error view).
- **Required future backend data:** none — these protect against eager route
  evaluation; with a real store, screens could load from the backend by id instead
  of requiring a passed object.

---

# Cross-cutting observations (data inventory summary)

1. **Only persisted data source:** `UserModel` blob (SharedPreferences via
   `features/learning`). Only `WardrobeScreen` reads it directly; others write
   learning signals or nothing.
2. **Only remote screen:** `AssistantScreen` (backend `/v1/assistant/chat` with
   offline fallback). All other screens use mock consts, ephemeral state, or
   route extras.
3. **Route-extras carry "live" data:** looks, wardrobe items, events, grooming/
   outfit prefs, hairstyle/grooming recommendations, onboarding flags travel via
   `state.extra`. Several routes render a shared `FansiErrorView` when the extra
   is missing (see 13.2).
4. **Most screens have NO loading/empty/error states** — data is static mock so
   the app never waits or fails. Processing screens (`*ProcessingScreen`,
   `AiAnalysisScreen`) simulate loading via timers. Empty states exist only on
   Discover, Wardrobe grid, and EventList.
5. **Many "save" actions are SnackBar-only** (WardrobeItemDetails edit/delete,
   Hairstyle/Grooming save, OutfitRecommendation save/regenerate, Profile sign
   out) — no persistence. Real saves write learning signals only:
   `look_saved` (DailyOutfit, LookDetails, OutfitAnalysis), `item_added`
   (Wardrobe), `occasion_preferred` (AddEvent), `assistant_*` (Assistant).
6. **Profile data is disconnected** from `UserModel` (mock stats, mock saved
   looks, ephemeral preferences/settings). SavedLooksScreen shows a different
   dataset than the `savedLooks` the LearningService persists.
7. **Mock scores are disconnected** from the computed `LearningService.styleScore`
   (e.g. Home 84/87 vs computed 60-based).
8. **First-time screens are not routed** — `FirstTimeHomeScreen` and
   `FirstTimeLightPathHomeScreen` are inline branches of `HomeScreen`, selected
   by `onboardingData` extra + `UserSession` flag.
9. **`/splash` route is registered but unreachable** — nothing navigates to it;
   the app boots directly at `/entry`.
10. **Test coverage gap:** onboarding screens (Splash → AccountCreation) have no
    dedicated widget tests; `FirstTimeHomeScreen` has none; StylistScreen has no
    dedicated file. All 342 baseline tests pass.
