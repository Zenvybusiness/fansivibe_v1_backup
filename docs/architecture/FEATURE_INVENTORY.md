# Fansivibe Feature Inventory

> Inventory of features that **actually exist** in the real repository
> (Flutter app at `newproject/flutter_application_1`, backend at `backend/`).
>
> No future/planned features are listed here. Status reflects verified code
> only, not documentation intent. Last verified: 2026-08-09.

## Priority Legend

| Priority | Meaning |
|----------|---------|
| **P0** | Essential foundation / core product |
| **P1** | Important core expansion |
| **P2** | Supporting feature |
| **P3** | Future / optional (code present but empty or placeholder) |

## Data Usage Legend

| Value | Meaning |
|-------|---------|
| Mock | Hardcoded `static const` data compiled into the app |
| Local | Persisted on-device (SharedPreferences via `features/learning`) |
| Remote | Fetched from the backend via HTTP |
| Ephemeral | Held in widget state only, lost on restart |

---

## Feature Summary Table

| Feature | Screens | Current Data | Backend | Tests | Status | Priority |
|---|---|---|---|---|---|---|
| Onboarding | 9 screens | Mock + static | None | via `widget_test`, home/first-time tests | Implemented, 2 dead models | **P0** |
| Home | 4 screens | Mock + Local (saved looks) | None | 3 files | Implemented | **P0** |
| Discover | 2 screens | Mock + Local (saved look signal) | None | 3 files | Implemented | **P0** |
| Wardrobe | 4 screens | Mock + **Local** (`UserModel.wardrobe`) | None (mirrored in catalog) | 4 files | Implemented, 2 data sources | **P0** |
| Stylist | 1 screen | Mock actions | None | covered by `widget_test` | Implemented (launcher hub) | **P1** |
| Outfit Scan | 3 screens | Mock + Local (saved look signal) | None | 3 files | Implemented, simulated camera | **P1** |
| Outfit Builder | 3 screens | Mock | None | 1 file | Implemented | **P1** |
| Hairstyle | 4 screens | Mock + Local (face profile) | None | 4 files | Implemented, simulated scan | **P1** |
| Grooming | 4 screens | Mock | None | 4 files | Implemented | **P1** |
| Events | 3 screens | Mock + Ephemeral + Local (occasion signal) | None | 1 file | Implemented, not persisted | **P2** |
| Profile | 6 screens | Mock + Ephemeral | None | 2 files | Implemented, not backed by UserModel | **P1** |
| Assistant | 1 screen | Remote → Local fallback | FastAPI `/v1/assistant/chat` | 2 files | Implemented | **P1** |
| Learning | — (service only) | **Local** (`UserModel` blob) | None (sent to assistant) | 1 file | Implemented | **P1** |
| Backend AI | — (service only) | Static catalog (server-side) | FastAPI + rules engine + Ollama | 2 pytest files | Implemented | **P1** |
| Scan Center | — | — | — | — | **Empty scaffolding** | **P3** |

---

## Feature Detail

### 1. Onboarding (`lib/features/onboarding/`)

- **Purpose:** First-launch journey: splash → entry → vibe select → camera
  permission → photo capture → AI analysis → result → account creation. Two
  paths (photo / light), leading into a personalized Home.
- **Status:** Implemented. Routed (routes `splash`…`accountCreation`).
- **Screens:** `splash_screen.dart`, `entry_screen.dart`, `vibe_select_screen.dart`,
  `camera_permission_screen.dart`, `photo_capture_screen.dart`, `ai_analysis_screen.dart`,
  `your_analysis_screen.dart`, `account_creation_screen.dart`.
- **Widgets/components:** `glass_container.dart`, `vibe_card.dart`,
  `color_palette_display.dart`, `ai_capability_icon.dart`, `analysis_insight_card.dart`,
  `animated_score_counter.dart`.
- **Models:** `StyleVibe` (enum, live), `vibeGradientColors` (live),
  `PaletteSwatch`, `AiCapability` + `allCapabilities` (live),
  `AnalysisResult`, `OnboardingResult` (**dead — never instantiated**; screens
  pass raw `Map<String, dynamic>` through route `extra`).
- **Services / Repositories:** none.
- **API/Backend:** none.
- **Tests:** no dedicated file; covered indirectly by `widget_test.dart`,
  `home_screen_test.dart`, `first_time_light_path_home_screen_test.dart`.
- **Data usage:** Mock / static only; onboarding outcome not persisted into
  `UserModel` (no `setFace`/`setStyleType` wiring).
- **Limitations:** analysis results are simulated; score/palette mocked inline;
  account creation does not create a real account or persist identity.
- **Dependencies:** none (Home depends on it via `onboardingData` extra).

### 2. Home (`lib/features/home/`)

- **Purpose:** Daily personalized style dashboard — Today's Look, Style Score,
  streak, AI insight, quick actions, and first-visit experiences.
- **Status:** Implemented.
- **Screens:** `home_screen.dart`, `daily_outfit_screen.dart`,
  `first_time_home_screen.dart`, `first_time_light_path_home_screen.dart`.
- **Widgets/components:** `widgets/home_widgets.dart` (TodaysLookCard, streak,
  quick action, insight cards).
- **Models:** `home_mock_data.dart` (`GreetingData`, `TodaysLookData`,
  `OutfitItemData`, `StyleScoreData`, `StyleTrend`, `StyleStreakData`,
  `StreakDayData`, `AIWardrobeInsightData`, `QuickActionData`);
  `daily_outfit_mock_data.dart` (`DailyOutfitData`, `AiInsightData`,
  `AlternativeLookData`, `DailyOutfitComponent`, `StyleDnaContext`,
  `WardrobeContext`; `DailyOutfitComponentCategory` is **dead**).
- **Services:** `LearningService.instance` (records `look_saved` from
  `daily_outfit_screen.dart`). `UserSession` flag gates light-path first visit.
- **Repositories:** none directly (uses `LearningService.instance`).
- **API/Backend:** none.
- **Tests:** `home_screen_test.dart`, `daily_outfit_screen_test.dart`,
  `first_time_light_path_home_screen_test.dart`.
- **Data usage:** Mock (mostly) + Local (saved-look signals).
- **Limitations:** scores (84/87) are disconnected from computed
  `LearningService.styleScore` (base 60); `GreetingData.mock` unused;
  duplicate "Today's Look" models (`TodaysLookData` vs `DailyOutfitData`).
- **Dependencies:** routes to discover, hairstyle, wardrobe, scan; reads
  onboarding `extra`; writes to Learning.

### 3. Discover (`lib/features/discover/`)

- **Purpose:** Personalized + trending looks with search, filters, match
  score, look details, wardrobe alternatives.
- **Status:** Implemented.
- **Screens:** `discover_screen.dart`, `look_details_screen.dart`.
- **Widgets/components:** `widgets/discover_widgets.dart`,
  `widgets/look_details_widgets.dart`.
- **Models:** `discover_mock_data.dart` (`DiscoverLookData`, `FilterOption`,
  `OccasionFilters`, `StyleFilters`, `FitFilters`, `DiscoverTab`,
  `DiscoverTabData`, `MatchScoreDetails`, `RecommendationReason`,
  `EnsembleComponent`, `WardrobeAlternative`, `WardrobeItem`).
- **Services:** none; `look_details_screen.dart` records `addSavedLook` signal.
- **Repositories:** none.
- **API/Backend:** none (looks are static; not served by backend).
- **Tests:** `discover_screen_test.dart`, `discover_widgets_test.dart`,
  `look_details_screen_test.dart`.
- **Data usage:** Mock + Local (saved-look signal).
- **Limitations:** `WardrobeItem` here is a third wardrobe-item model unrelated
  to `WardrobeItemData`/`WardrobeEntry`; `imageUrl` fields point nowhere
  (no asset/images bundled).
- **Dependencies:** Learning (signal on save).

### 4. Wardrobe (`lib/features/wardrobe/`)

- **Purpose:** Digital wardrobe — browse, filter, add, categorize items,
  item details, insights.
- **Status:** Implemented. Reads/writes the persisted `UserModel.wardrobe`.
- **Screens:** `wardrobe_screen.dart`, `add_wardrobe_category_screen.dart`,
  `add_wardrobe_item_screen.dart`, `wardrobe_item_details_screen.dart`.
- **Widgets/components:** `widgets/wardrobe_widgets.dart`.
- **Models:** `wardrobe_mock_data.dart` (`WardrobeCategory`, `WardrobeItemData`,
  `WardrobeInsightData`, `WardrobeMockData`, `AddItemCategoryConfig`,
  `ColorOption`, `TextureOption`, `AddItemConfig`).
- **Services:** `LearningService.instance` — wardrobe list is the source of
  truth; add-item persists a new `WardrobeEntry`.
- **Repositories:** `LearningRepository` (via `LearningService.instance`).
- **API/Backend:** none; `WardrobeMockData.items` mirrored server-side in
  `backend/app/data/catalog.py:18`.
- **Tests:** `wardrobe_screen_test.dart`, `add_wardrobe_category_screen_test.dart`,
  `add_wardrobe_item_screen_test.dart`, `wardrobe_item_details_screen_test.dart`.
- **Data usage:** Mock seed + **Local** persistence (item adds survive restart).
- **Limitations:** two overlapping sources — `WardrobeMockData.items` and
  `LearningService.defaultWardrobe` are byte-identical duplicates; item
  favorites edit `WardrobeItemData` copies but persistence flows only through
  Learning; `WardrobeInsightData` duplicates home `AIWardrobeInsightData`.
- **Dependencies:** Learning (persisted), consumed by OfflineAssistant.

### 5. Stylist (`lib/features/stylist/`)

- **Purpose:** Launcher hub for specialized AI workflows + assistant entry.
- **Status:** Implemented (thin navigation surface).
- **Screens:** `stylist_screen.dart`.
- **Widgets/components:** none (uses `FansivibeCard`).
- **Models:** `StylistActionData` (defined inside `stylist_screen.dart`,
  `mockActions`, 5 actions).
- **Services / Repositories / API:** none.
- **Tests:** covered by `widget_test.dart`/`home_screen_test.dart` navigation
  checks; no dedicated file.
- **Data usage:** Mock actions only.
- **Limitations:** actions are hardcoded (not configuration-driven from
  backend/feature flags).
- **Dependencies:** routes to scan/build/hairstyle/grooming/events/assistant.

### 6. Outfit Scan (`lib/features/outfit_scan/`)

- **Purpose:** Capture outfit → process → analyze (silhouette, fit, color
  harmony) → result with detected items and sections.
- **Status:** Implemented; camera capture is simulated (mock stage timing).
- **Screens:** `outfit_scan_screen.dart`, `outfit_processing_screen.dart`,
  `outfit_analysis_screen.dart`.
- **Widgets/components:** `widgets/outfit_scan_widgets.dart`.
- **Models:** `outfit_scan_mock_data.dart` (`DetectedClothingItem`,
  `AnalysisSection`, `ProcessingStage`, `OutfitAnalysisData`).
- **Services:** `LearningService.instance` (`addSavedLook` on "Generate Look").
- **Repositories:** none.
- **API/Backend:** none (analysis is mocked).
- **Tests:** `outfit_scan_screen_test.dart`, `outfit_processing_screen_test.dart`,
  `outfit_analysis_screen_test.dart`.
- **Data usage:** Mock + Local (saved-look signal). **Only feature importing
  `package:camera`** (though capture is simulated).
- **Limitations:** no real image upload/analysis; `ProcessingStage` duplicated
  in outfit_builder/hairstyle/grooming.
- **Dependencies:** Learning (signal); route chain from Stylist.

### 7. Outfit Builder (`lib/features/outfit_builder/`)

- **Purpose:** Build outfit from occasion/mood/fit/color palette →
  generation → recommendation with components, reasons, alternatives.
- **Status:** Implemented.
- **Screens:** `build_outfit_screen.dart`, `outfit_generation_screen.dart`,
  `outfit_recommendation_screen.dart`.
- **Widgets/components:** `widgets/outfit_builder_widgets.dart`.
- **Models:** `outfit_builder_mock_data.dart` (`BuilderOption`, `GenerationStage`,
  `OutfitComponent`, `OutfitRecommendation`).
- **Services / Repositories / API:** none.
- **Tests:** `outfit_builder_screens_test.dart`.
- **Data usage:** Mock only.
- **Limitations:** result does not write to Learning/UserModel; preference
  inputs not persisted; component slots hardcoded.
- **Dependencies:** routed from Stylist/Home.

### 8. Hairstyle (`lib/features/hairstyle/`)

- **Purpose:** Face scan → process → hairstyle recommendations + details,
  grounded in face shape/skin tone/Style DNA.
- **Status:** Implemented; scan is simulated (mock checks/stages).
- **Screens:** `face_scan_screen.dart`, `face_processing_screen.dart`,
  `hairstyle_result_screen.dart`, `hairstyle_details_screen.dart`.
- **Widgets/components:** `widgets/hairstyle_widgets.dart`.
- **Models:** `hairstyle_mock_data.dart` (`FaceScanCheck`,
  `HairstyleProcessingStage`, `HairstyleRecommendation`, `HairstyleAnalysisResult`).
- **Services:** none (consumed read-only by `offline_assistant.dart`).
- **Repositories:** none.
- **API/Backend:** recommendation data mirrored in `catalog.py`.
- **Tests:** `hairstyle_scan_screen_test.dart`, `hairstyle_processing_screen_test.dart`,
  `hairstyle_result_screen_test.dart`, `hairstyle_details_screen_test.dart`.
- **Data usage:** Mock only; `HairstyleAnalysisResult.mock` reused offline.
- **Limitations:** does not write face shape into `UserModel.face`; scan is a
  simulation; `HairstyleProcessingStage` duplicates other stage models.
- **Dependencies:** routed from Stylist; consumed by Assistant.

### 9. Grooming (`lib/features/grooming/`)

- **Purpose:** Beard/eyewear suggestions from face shape, beard style,
  density, color → results + details.
- **Status:** Implemented.
- **Screens:** `grooming_input_screen.dart`, `grooming_processing_screen.dart`,
  `grooming_result_screen.dart`, `grooming_details_screen.dart`.
- **Widgets/components:** `widgets/grooming_widgets.dart`.
- **Models:** `grooming_mock_data.dart` (`GroomingOption`,
  `GroomingProcessingStage`, `GroomingRecommendation`, `GroomingAnalysisResult`).
- **Services / Repositories / API:** none (offline assistant reads the mock).
- **Tests:** `grooming_input_screen_test.dart`, `grooming_processing_screen_test.dart`,
  `grooming_result_screen_test.dart`, `grooming_details_screen_test.dart`.
- **Data usage:** Mock only.
- **Limitations:** does not write to `UserModel`; recommendation static.
- **Dependencies:** routed from Stylist; consumed by Assistant.

### 10. Events (`lib/features/events/`)

- **Purpose:** Event list → add event → details; events give outfit
  recommendation context.
- **Status:** Implemented but **ephemeral** — events are created in widget
  state and lost on restart.
- **Screens:** `event_list_screen.dart`, `add_event_screen.dart`,
  `event_details_screen.dart`.
- **Widgets/components:** `widgets/events_widgets.dart`.
- **Models:** `event_mock_data.dart` (`EventType`, `UserEvent`).
- **Services:** `LearningService.instance` (`addPreferredOccasion` on add).
- **Repositories:** none.
- **API/Backend:** none.
- **Tests:** `event_screens_test.dart`.
- **Data usage:** Mock + Ephemeral + Local (occasion signal).
- **Limitations:** no persistence of events; `EventType.typeById` dead code;
  no date picker storage beyond strings.
- **Dependencies:** Learning (occasion signal).

### 11. Profile (`lib/features/profile/`)

- **Purpose:** Style identity — style score, DNA, progress, achievements,
  saved looks, preferences, subscription, support, settings.
- **Status:** Implemented; profile data is static mock, preferences/settings
  are ephemeral.
- **Screens:** `profile_screen.dart`, `preferences_screen.dart`,
  `saved_looks_screen.dart`, `subscription_screen.dart`, `support_screen.dart`,
  `settings_screen.dart`.
- **Widgets/components:** `widgets/profile_widgets.dart`.
- **Models:** `profile_mock_data.dart` (`ProfileData`, `StylistLevelData`,
  `GlobalRankData`, `StyleProgressData`, `StyleDnaData`, `AchievementData`,
  `SavedLookPreview`, `ProfileMenuAction`);
  `profile_mocks.dart` (`PreferenceOption`, `SavedLookDetail`,
  `SubscriptionPlan`, `SupportTopic`, `SettingsItem`, `ProfileMockData`).
- **Services:** none (SavedLooks screen reads mock, not `UserModel.savedLooks`).
- **Repositories:** none.
- **API/Backend:** none.
- **Tests:** `profile_screen_test.dart`, `profile_screens_test.dart`.
- **Data usage:** Mock + Ephemeral.
- **Limitations:** `ProfileData.mock` not backed by `UserModel`; saved looks,
  preferences, settings not persisted; `StyleDnaData` duplicates home
  `StyleDnaContext` and learning `FaceProfile`; duplicate saved-look models.
- **Dependencies:** routed from shell; conceptually depends on Learning
  (unused so far).

### 12. Assistant (`lib/features/assistant/`)

- **Purpose:** Chat with the AI stylist — suggests, clarifies, navigates;
  grounded in the on-device user model; offline-capable.
- **Status:** Implemented. Backend-first with deterministic offline fallback.
- **Screens:** `assistant_screen.dart`.
- **Widgets/components:** `widgets/assistant_widgets.dart` (bubbles, cards,
  chips, nav button, typing dots); `assistant_routes.dart` maps actions→routes.
- **Models:** `data/models.dart` (DTOs mirroring backend schemas:
  `SuggestionCard`, `ClarificationOption`, `NavigationRequest`, `AssistantReply`,
  `AssistantMessage`, `AssistantUserContext`).
- **Services:** `domain/assistant_service.dart` (`ChangeNotifier`, injectable;
  attaches `LearningRepository`, records signals, offline fallback).
- **Repositories:** `LearningRepository` (consumed).
- **API/Backend:** `data/assistant_client.dart` — POST
  `$ASSISTANT_BASE_URL/v1/assistant/chat` (default `http://localhost:8000`,
  overridable via `--dart-define`), 12s timeout, returns null on failure.
  `data/offline_assistant.dart` mirrors `engine.py` rules on-device.
- **Tests:** `assistant_screen_test.dart`, `offline_assistant_test.dart`.
- **Data usage:** Remote (backend) → Local fallback (offline rules + mock
  catalog data). Uses `UserModel` snapshot as `AssistantUserContext`.
- **Limitations:** no auth; conversation not persisted; offline look cards are
  a second copy of `catalog.py` data.
- **Dependencies:** Learning (context + signals), Hairstyle/Grooming/Wardrobe
  mocks (offline grounding), Backend AI service, Router (navigation).

### 13. Learning (`lib/features/learning/`)

- **Purpose:** On-device evolving user model (wardrobe, face profile, saved
  looks, occasions, signals) + progressive style score. The personalization
  backbone consumed by every other feature.
- **Status:** Implemented. The only persisted data in the app.
- **Screens:** none (no UI).
- **Models:** `data/models.dart` (`WardrobeEntry`, `FaceProfile`,
  `LearningSignal`, `UserModel` — all with `toJson`/`fromJson`).
- **Services:** `domain/learning_service.dart` — `LearningService.instance`
  singleton (`ChangeNotifier`), seeds `defaultWardrobe` (24 items), persists
  via `LocalStore`, computes `styleScore = 60 + min(wardrobe,20) + min(savedLooks*2,20)`,
  records signals on every mutation; `@visibleForTesting resetForTest()`.
- **Repositories:** `learning_repository.dart` — the public contract other
  features must import (no internals).
- **API/Backend:** none (snapshot sent to backend inside assistant requests).
- **Persistence:** `data/local_store.dart` — SharedPreferences key
  `fansivibe.user_model.v1`, single JSON blob, graceful in-memory fallback.
- **Tests:** `learning_service_test.dart`.
- **Data usage:** **Local** (persisted). Seed duplicated from
  `WardrobeMockData.items`.
- **Limitations:** no migrations/versioning beyond the key suffix; face/style
  data never actually written by onboarding/hairstyle/grooming; signals
  accumulate unbounded.
- **Dependencies:** consumed by Wardrobe, Home, Discover, Events, Outfit Scan,
  Assistant.

### 14. Backend AI (`backend/`)

- **Purpose:** Fansivibe's own server-side AI assistant — deterministic rules
  engine, typed structured replies, optional Ollama enrichment. Flutter never
  talks to an AI provider directly.
- **Status:** Implemented. 19 pytest tests passing.
- **Screens:** none.
- **API:** FastAPI — `GET /health`, `POST /v1/assistant/chat`
  (`backend/app/main.py`).
- **Engine:** `app/ai/engine.py` (orchestration + dialogue policy),
  `app/ai/intent.py` (rules classifier), `app/ai/tools.py` (recommendation
  tools grounded in `UserContext`), `app/ai/llm_backend.py` (optional Ollama
  enrichment; degrades to rules when unavailable).
- **Models:** `app/models/schemas.py` (`WardrobeItem`, `FaceData`,
  `UserContext`, `ChatMessage`, `AssistantRequest`, `SuggestionCard`,
  `ClarificationOption`, `NavigationRequest`, `AssistantReply`) — mirrored by
  Flutter DTOs in `features/assistant/data/models.dart`.
- **Data:** `app/data/catalog.py` — static recommendation catalog mirroring
  Flutter mocks (24-item wardrobe, occasion looks, hairstyle/grooming cards,
  navigation map).
- **Tests:** `tests/test_engine.py`, `tests/test_intent.py`.
- **Data usage:** Static catalog (server-side constants), stateless per
  request. **No database, no auth, no user store, no persistence.**
- **Limitations:** no users/accounts, no real LLM backend, catalog is a static
  mirror, no CORS config beyond defaults, no API versioning beyond `/v1`.
- **Dependencies:** consumed by Assistant feature; Docker Compose for Ollama.

### 15. Scan Center (`lib/features/scan_center/`)

- **Purpose:** (intended) central scan/processing hub.
- **Status:** **Empty scaffolding** — only empty `data/` and
  `presentation/widgets/` directories. Zero files. Not imported anywhere, not
  routed.
- **Tests:** none.
- **Dependencies:** none.

---

## Cross-Cutting Layers (not features)

| Layer | Location | Notes |
|-------|----------|-------|
| Router/shell | `lib/app/` | go_router 17.2.3, `StatefulShellRoute.indexedStack`, 5 tabs, `RouteNames` |
| Theme/design tokens | `lib/shared/theme/` | colors, typography, spacing, radius, shadows, theme |
| Shared components | `lib/shared/components/` | FansiButton, FansiBadge, FansiChip, FansiHeroCard, FansiMiniCard, FansiInsightCard, FansiImageWell, FansiLoadingView, FansiErrorView, FansivibeCard, SectionTitle, FloatingAssistantButton |
| Shared utils | `lib/shared/utils/` | `score_colors.dart`, `icon_utils.dart`, `user_session.dart` |

---

## Classification by Existence

### Features that definitely exist (fully implemented)
Onboarding, Home, Discover, Wardrobe, Stylist, Outfit Scan, Outfit Builder,
Hairstyle, Grooming, Events, Profile, Assistant, Learning, Backend AI.

### Features partially implemented
- **Wardrobe** — two overlapping data sources (mock vs `UserModel`), favorites
  edits not reliably persisted to the model.
- **Profile** — UI complete but mock/ephemeral data; not backed by
  `UserModel`; saved looks/preferences/settings not persisted.
- **Events** — fully functional UI but events are ephemeral (never persisted).
- **Onboarding** — flow complete but results never persist into `UserModel`
  (dead `AnalysisResult`/`OnboardingResult` models), account creation is a
  mock.
- **Assistant / Backend** — working end-to-end but grounded in a static catalog
  mirror, no auth, no user store.

### Features that are UI-only (no backend, mostly mock/local data)
Onboarding, Home, Discover, Stylist, Outfit Scan, Outfit Builder, Hairstyle,
Grooming, Events, Profile. (Assistant and Learning additionally use local
persistence/remote calls.)

### Features that are backend-only
Backend AI service (`backend/`) — no UI. The only client consumer is the
Assistant feature.

### Features referenced in documentation but not implemented (verified absent)
- **`core/` infrastructure layer** (`docs/ARCHITECTURE.md`) — no `lib/core/`.
- **`auth/` and `style_profile/` features** (`docs/ARCHITECTURE.md`) — not present.
- **PostgreSQL database** (`DECISIONS.md` DEC-004, `PROJECT_CONTEXT.md`) —
  accepted *direction* only; no DB code anywhere.
- **Feature flags** (`docs/ARCHITECTURE.md`) — no infrastructure.
- **Skincare / Accessories / Hair Care / Fragrance / Packing / Virtual Try-On**
  (`docs/PRODUCT_BLUEPRINT.md`) — future expansion list, no code.
- **`main_shell.dart` legacy shell** (`CURRENT_STATE.md`) — no longer present
  (router is the only shell).
- **Scan Center** — dirs exist but empty; effectively a placeholder.

---

## Data Architecture Notes (input for DB design)

1. **Only persisted entity today:** `UserModel` blob (SharedPreferences).
2. **Wardrobe item modeled 3 ways:** `WardrobeItemData` (wardrobe),
   `WardrobeEntry` (learning/persisted), `WardrobeItem` (discover) + server
   `WardrobeItem` (catalog).
3. **Style DNA modeled 3 ways:** `StyleDnaContext` (home), `StyleDnaData`
   (profile), `FaceProfile` (learning).
4. **Event persistence gap:** events are created and shown but never stored.
5. **Score disconnect:** mock scores (84/87) vs computed `LearningService.styleScore`.
6. **Occasion vocabulary repeated** in 4+ places as loose strings.
