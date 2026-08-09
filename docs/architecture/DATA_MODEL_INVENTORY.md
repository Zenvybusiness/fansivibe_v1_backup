# Fansivibe Data Model Inventory

> Complete inventory of every **data / model representation** that actually
> exists in the repo: Dart model classes, DTOs, request/response models, local
> data objects, mock data objects, repositories, services, backend Pydantic
> schemas, and catalog JSON structures. Companion to
> `docs/architecture/FEATURE_INVENTORY.md` and
> `docs/architecture/SCREEN_DATA_INVENTORY.md`.
>
> This documents **what exists** — it proposes nothing. No model merging, no
> SQL, no implementation changes. It is the input for the next phase: designing
> the production database / service layer.
>
> Last verified: 2026-08-09. Every entry verified against source code.

## Legend

| Flag | Meaning |
|------|---------|
| **UI-only** | Presentation helper / card DTO; no domain value, exists only to render a screen |
| **Domain** | A real concept the product cares about (user, wardrobe item, look, event…) |
| **API** | DTO that crosses the app↔backend boundary (`AssistantClient` ↔ FastAPI) |
| **Persisted** | Written to SharedPreferences as part of the `UserModel` blob |
| **AI-generated** | Represents an AI/analysis result (score, reasons, recommendation) |
| **Historical** | Currently hardcoded mock; would need to be captured/history-tracked in a DB |
| **Ephemeral** | Held in widget/service state only, lost on restart |
| **Seed** | Default data used to initialize the user model on first launch |

## Cross-cutting facts

- **Only persistence:** `UserModel` JSON blob under key `fansivibe.user_model.v1`
  in SharedPreferences, written by `LocalStore` (`features/learning`). Everything
  else is `static const` mock, ephemeral widget state, or route extras.
- **Only remote API:** the Assistant (`POST $ASSISTANT_BASE_URL/v1/assistant/chat`,
  default `http://localhost:8000`). Contract = `assistant/data/models.dart`
  mirrored 1:1 by `backend/app/models/schemas.py`.
- **Only repository abstraction:** `LearningRepository` (abstract) implemented by
  `LearningService.instance` (singleton `ChangeNotifier`). All other features
  read mocks directly or accept route-extras.
- **Seed data:** `defaultWardrobe` (`learning_service.dart`) mirrors
  `WardrobeMockData.items` and `backend/app/data/catalog.py::WARDROBE` (24 items,
  same ids/names/categories/favorites).
- **Catalog mirrors:** backend `catalog.py` looks mirror Flutter mocks
  (`Refined Office` ↔ `OutfitRecommendation.mock`; `Textured Quiff` ↔
  `HairstyleAnalysisResult.mock.topRecommendation`; `Structured Goatee` ↔
  `GroomingAnalysisResult.mock.topRecommendation`). The offline assistant
  (`offline_assistant.dart::_LookCard`) is a third mirror of the same looks.
- **Dead code (defined, never referenced):** `AnalysisResult`,
  `OnboardingResult` in `onboarding_data.dart` (see §13).

---

# 1. Feature: Learning (`lib/features/learning/`)

The only feature with a domain/persistence/repository layer. Owns the single
on-device user model and the cross-feature contract.

## 1.1 `UserModel`

- **Path:** `lib/features/learning/data/models.dart:106`
- **Purpose:** The evolving on-device user model — the source of truth for
  personalization; serialized to a JSON blob for persistence and sent (as a
  snapshot) to the AI backend.
- **Fields:**
  | Field | Type | Required |
  |-------|------|----------|
  | `wardrobe` | `List<WardrobeEntry>` | required |
  | `face` | `FaceProfile?` | optional |
  | `styleType` | `String?` | optional |
  | `savedLooks` | `List<String>` | default `[]` |
  | `preferredOccasions` | `List<String>` | default `[]` |
  | `signals` | `List<LearningSignal>` | default `[]` |
- **Serialization:** `toJson()` / `fromJson()` / `encode()` (JSON string) / `decode()`.
- **Owner:** `features/learning`
- **Source:** persisted (LocalStore), seeded with `defaultWardrobe`
- **Flags:** Domain, Persisted
- **Related features:** all (assistant reads it via context; wardrobe/home write it)
- **Duplicates:** none (the aggregate root; see `AssistantUserContext` DTO mirror in §2)

## 1.2 `WardrobeEntry`

- **Path:** `lib/features/learning/data/models.dart:4`
- **Purpose:** A wardrobe item in the user's evolving model.
- **Fields:** `id` String (req), `name` String (req), `category` String (req),
  `color` String (req), `material` String? (opt), `isFavorite` bool (default false).
- **Serialization:** `toJson` / `fromJson` / `copyWith({isFavorite})`.
- **Owner:** `features/learning`
- **Source:** persisted via `UserModel`
- **Flags:** Domain, Persisted
- **Related features:** wardrobe, home, discover, outfit_builder, outfit_scan, assistant
- **Duplicates:** ⚠ `WardrobeItemData` (wardrobe UI mock, §4), `WardrobeItem`
  (backend Pydantic, §15), `WardrobeItem` (discover alternative model, §6).

## 1.3 `FaceProfile`

- **Path:** `lib/features/learning/data/models.dart:50`
- **Purpose:** Face/analysis attributes learned from onboarding and scans.
- **Fields:** `faceShape` String? (opt), `skinTone` String? (opt), `bodyType`
  String? (opt), `styleType` String? (opt).
- **Serialization:** `toJson` / `fromJson`.
- **Owner:** `features/learning`
- **Source:** persisted via `UserModel` (`UserModel.face`)
- **Flags:** Domain, Persisted, AI-generated (intended result of face analysis)
- **Related features:** hairstyle, grooming, assistant, profile, home
- **Duplicates:** ⚠ `FaceData` (backend Pydantic, §15), `StyleDnaData`
  (profile mock, §12), `StyleDnaContext` (home mock, §3).

## 1.4 `LearningSignal`

- **Path:** `lib/features/learning/data/models.dart:80`
- **Purpose:** A typed interaction signal. Accumulates over time and drives
  gradual learning; every add/save/scan/feedback is recorded.
- **Fields:** `type` String (req), `label` String (req), `timestamp` int? (opt,
  defaults to now on write).
- **Serialization:** `toJson` / `fromJson`.
- **Owner:** `features/learning`
- **Source:** persisted via `UserModel.signals`; written by `LearningService`
  mutations and `recordSignal`.
- **Flags:** Domain, Persisted, Historical
- **Known signal types written today:** `item_added`, `analysis_updated`,
  `style_updated`, `look_saved`, `occasion_preferred`, `assistant_message`,
  `suggestion_opened`, `assistant_navigation`.
- **Related features:** all (each feature records signals via `LearningService`)
- **Duplicates:** none.

## 1.5 `LocalStore`

- **Path:** `lib/features/learning/data/local_store.dart:11`
- **Purpose:** Persists the on-device user model as a single JSON blob via
  SharedPreferences (key `fansivibe.user_model.v1`); degrades to in-memory
  when storage is unavailable (headless tests).
- **Members:** `readRaw()`, `writeRaw(encoded)`, `load() → UserModel?`, `save(UserModel)`.
- **Owner:** `features/learning`
- **Source:** persistence adapter (no model data itself)
- **Flags:** — (infrastructure)
- **Duplicates:** none (only persistence layer in the app).

## 1.6 `LearningRepository` + `LearningService`

- **Path:** `lib/features/learning/learning_repository.dart:5` (abstract),
  `lib/features/learning/domain/learning_service.dart:194` (concrete singleton).
- **Purpose:** Public contract other features use to read/update the user model;
  `LearningService` is the `ChangeNotifier` singleton implementation.
- **Contract:** `wardrobe`, `face`, `styleType`, `savedLooks`, `preferredOccasions`,
  `signals`, `styleScore` (computed: 60 + wardrobe up to +20 + savedLooks ×2 up
  to +20), `load()`, `addItem`, `setFace`, `setStyleType`, `addSavedLook`,
  `addPreferredOccasion`, `recordSignal`.
- **Owner:** `features/learning`
- **Source:** in-memory + persisted via `LocalStore`
- **Flags:** Domain (service), Persisted (behind)
- **Related features:** all (wardrobe, home, discover, events, outfit_scan,
  assistant use `LearningService.instance`)
- **Duplicates:** none (only repository/service abstraction in the app).

## 1.7 `defaultWardrobe` (seed)

- **Path:** `lib/features/learning/domain/learning_service.dart:9`
- **Purpose:** Default starter wardrobe (24 items) mirroring `WardrobeMockData.items`.
- **Fields:** 24 × `WardrobeEntry`.
- **Owner:** `features/learning`
- **Source:** seed data
- **Flags:** Domain, Seed
- **Related features:** wardrobe (initial state), assistant (fallback wardrobe)
- **Duplicates:** ⚠ same 24 items duplicated 3×: here, in
  `WardrobeMockData.items` (§4), and in backend `catalog.py::WARDROBE` (§16).

---

# 2. Feature: Assistant (`lib/features/assistant/`)

The only remote-data feature. DTOs mirror `backend/app/models/schemas.py` 1:1.

## 2.1 `SuggestionCard`

- **Path:** `lib/features/assistant/data/models.dart:7`
- **Purpose:** Typed suggestion/result card in assistant replies (mirrors
  backend `SuggestionCard`).
- **Fields:** `kind` String (req), `title` String (req), `subtitle` String (req),
  `score` int? (opt), `items` `List<String>` (default []), `action` String? (opt).
- **Serialization:** `fromJson` / `toJson`.
- **Owner:** `features/assistant`
- **Source:** API response (backend) or built by `OfflineAssistant`
- **Flags:** API, AI-generated
- **Related features:** assistant, discover (action links), build-outfit/hairstyle/grooming (action targets)
- **Duplicates:** none (client/backend pair; backend `catalog.py` constants are instances).

## 2.2 `ClarificationOption`

- **Path:** `lib/features/assistant/data/models.dart:45`
- **Purpose:** A tappable clarification chip (e.g. occasion choices).
- **Fields:** `label` String (req), `value` String (req).
- **Serialization:** `fromJson` / `toJson`.
- **Owner:** `features/assistant`
- **Source:** API / offline engine
- **Flags:** API
- **Duplicates:** none (mirrors backend `ClarificationOption`).

## 2.3 `NavigationRequest`

- **Path:** `lib/features/assistant/data/models.dart:60`
- **Purpose:** Assistant-directed navigation (route + label).
- **Fields:** `route` String (req), `label` String (req).
- **Serialization:** `fromJson` / `toJson`.
- **Owner:** `features/assistant`
- **Source:** API / offline engine
- **Flags:** API
- **Duplicates:** none (mirrors backend `NavigationRequest`).

## 2.4 `AssistantReply`

- **Path:** `lib/features/assistant/data/models.dart:75`
- **Purpose:** Structured reply: intent + text + cards + clarifications + navigation.
- **Fields:** `intent` String (req), `text` String (req), `cards`
  `List<SuggestionCard>` (default []), `clarifications` `List<ClarificationOption>`
  (default []), `navigation` `NavigationRequest?` (opt).
- **Serialization:** `fromJson`.
- **Owner:** `features/assistant`
- **Source:** API response or `OfflineAssistant.replyFor`
- **Flags:** API, AI-generated
- **Duplicates:** none (mirrors backend `AssistantReply`).

## 2.5 `AssistantMessage`

- **Path:** `lib/features/assistant/data/models.dart:108`
- **Purpose:** One message in the chat conversation (user or assistant).
- **Fields:** `role` String (req), `text` String (req), `cards` (default []),
  `clarifications` (default []), `navigation` NavigationRequest? (opt),
  `pending` bool (default false, typing indicator).
- **Serialization:** none on client — history serialized as `{role, content}` in
  the request payload (see 2.7). Mirrors backend `ChatMessage` (role/content only).
- **Owner:** `features/assistant` (`AssistantService` holds the list)
- **Source:** ephemeral conversation state
- **Flags:** Ephemeral, API (partial: request payload)
- **Duplicates:** none client-side; backend `ChatMessage` is the API shape.

## 2.6 `AssistantUserContext`

- **Path:** `lib/features/assistant/data/models.dart:140`
- **Purpose:** Snapshot of the user model sent with every assistant request
  (grounding context).
- **Fields:** `wardrobe` `List<WardrobeEntry>` (default []), `face` `FaceProfile?`
  (opt), `savedLooks` `List<String>` (default []), `preferredOccasions`
  `List<String>` (default []).
- **Serialization:** `toJson` (reuses `WardrobeEntry`/`FaceProfile` serializers).
- **Owner:** `features/assistant`
- **Source:** built from `LearningRepository` in `AssistantService._buildContext`
- **Flags:** API (request), Domain-derived
- **Related features:** learning (source), backend (receives)
- **Duplicates:** ⚠ mirrors backend `UserContext` (§15) and duplicates the shape
  of `UserModel` minus `styleType`/`signals`.

## 2.7 `AssistantClient`

- **Path:** `lib/features/assistant/data/assistant_client.dart:14`
- **Purpose:** HTTP client for the AI backend. Returns `AssistantReply?` (null on
  failure so callers fall back to offline).
- **Members:** `baseUrl` (dart-define `ASSISTANT_BASE_URL`, default
  `http://localhost:8000`), `_timeout` 12s, `chat({history, context})`, `dispose()`.
- **Request payload:** `{messages: [{role, content}], user: context.toJson()}`.
- **Owner:** `features/assistant`
- **Flags:** API (transport)
- **Duplicates:** none.

## 2.8 `OfflineAssistant`

- **Path:** `lib/features/assistant/data/offline_assistant.dart:26`
- **Purpose:** Deterministic offline rules engine mirroring `backend/app/ai/engine.py`;
  answers from app data when the backend is unreachable.
- **Members:** `_occasions` const list; `replyFor(text, context)`;
  private `_outfit`, `_hairstyle`, `_grooming`, `_wardrobe`, `_help`,
  `_navigateFor`, `_occasionFor`, `_hasAny`.
- **Owner:** `features/assistant`
- **Source:** consumes `WardrobeMockData`, `HairstyleAnalysisResult.mock`,
  `GroomingAnalysisResult.mock`, learning `WardrobeEntry`
- **Flags:** API (response-shape), AI-generated
- **Duplicates:** logic duplicates backend `engine.py` + `tools.py` + `intent.py`.

## 2.9 `_LookCard` (private)

- **Path:** `lib/features/assistant/data/offline_assistant.dart:8`
- **Purpose:** Single outfit suggestion mirroring `backend/app/data/catalog.py`
  looks (office/date/party/travel/casual).
- **Fields:** `title` String (req), `items` `List<String>` (req), `score` int (req).
- **Owner:** `features/assistant`
- **Source:** hardcoded const per occasion
- **Flags:** UI-only, AI-generated
- **Duplicates:** ⚠ the same 5 looks exist as backend `catalog.py::OCCASION_TO_LOOK`
  and conceptually as `OutfitRecommendation.mock` / `DailyOutfitData` (§3/§8).

---

# 3. Feature: Home (`lib/features/home/data/`)

All mock — pure screen data. Two files: `home_mock_data.dart` (dashboard) and
`daily_outfit_mock_data.dart` (Today's Look).

## 3.1 `home_mock_data.dart`

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `GreetingData` | 4 | Personalized greeting header | `greeting` String, `name` String, `dateLabel` String (all req) + `mock` | UI-only |
| `TodaysLookData` | 30 | Home "Today's Look" card | `title`/`occasion`/`weather`/`description` String (req), `items` `List<OutfitItemData>` (req), `styleScore` int (req) + `mock` | UI-only, AI-generated, Historical |
| `OutfitItemData` | 103 | One outfit piece in the card | `id`/`name`/`category`/`color` String (req) | UI-only, Historical |
| `StyleScoreData` | 126 | Style score card | `currentScore` int, `weeklyChange` int, `weeklyTrend` `StyleTrend`, `breakdown` `List<StyleScoreBreakdownItem>` (all req) + `mock` | UI-only, AI-generated, Historical |
| `StyleScoreBreakdownItem` | 178 | One score category | `category`/`label` String, `score` int (all req) | UI-only |
| `StyleTrend` | 197 | Enum | `up`, `down`, `stable` | UI-only (enum) |
| `StyleStreakData` | 209 | Streak card | `currentStreak`/`longestStreak`/`totalDaysStyled`/`thisWeekCount`/`weeklyGoal` int, `recentActivity` `List<StreakDayData>` (all req) + `mock` | UI-only, Historical |
| `StreakDayData` | 258 | One day in streak timeline | `day` String (req), `styled` bool (req), `score` int? (opt) | UI-only |
| `AIWardrobeInsightData` | 273 | "Wardrobe Gap Detected" insight | `title`/`insight`/`iconName`/`actionLabel`/`actionRoute` String, `accentColor` int (all req) + `mock` | UI-only, AI-generated, Historical |
| `QuickActionData` | 315 | Home quick action tiles | `id`/`title`/`subtitle`/`iconName`/`route` String (req), `accentColor` int (default) + `mockActions` (3) | UI-only |

**Duplicates:**
- ⚠ `OutfitItemData` duplicates `DailyOutfitComponent` (§3.2) and `OutfitComponent`
  (§8) — 3+ outfit-piece shapes.
- ⚠ `AIWardrobeInsightData` duplicates `WardrobeInsightData` (§4) and backend
  `WARDROBE_INSIGHT` (§16) — 3 wardrobe-insight shapes.
- ⚠ `QuickActionData` duplicates `StylistActionData` (stylist inline, §5) — 2
  quick-action shapes.
- ⚠ `TodaysLookData` duplicates `DailyOutfitData` (same look, 2 shapes).

## 3.2 `daily_outfit_mock_data.dart`

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `AiInsightData` | 1 | AI insight card (color harmony, proportions…) | `title`/`description`/`iconName` String (req) | UI-only, AI-generated |
| `AlternativeLookData` | 13 | Alternative look row | `id`/`name`/`styleName` String, `matchScore` int (all req) | UI-only, Historical |
| `DailyOutfitData` | 27 | Today's Look full model | `title`/`occasion`/`weather`/`description` String, `matchScore`/`styleScore` int, `components` `List<DailyOutfitComponent>`, `reasons` `List<String>`, `styleDna` `StyleDnaContext`, `wardrobeContext` `WardrobeContext` (all req); `aiSelectionReason`/`confidenceBoost`/`dailyStyleTip` String?; `aiInsights` (default []), `alternatives` (default []) + `mock` | UI-only, AI-generated, Historical |
| `DailyOutfitComponent` | 195 | Ensemble piece | `id`/`name`/`category`/`color` String (req), `material`/`colorHex` String? (opt) | UI-only, Historical |
| `StyleDnaContext` | 213 | Style DNA block | `styleType`/`bodyType`/`skinTone`/`faceShape` String (all req) | UI-only |
| `WardrobeContext` | 227 | Wardrobe stats block | `totalItems` int, `matchingItems` int, `insight` String (all req) | UI-only |
| `DailyOutfitComponentCategory` | 239 | String constants | `outerwear`/`tops`/`bottoms`/`footwear`/`accessories` (const String) | UI-only |

**Duplicates:**
- ⚠ `DailyOutfitData` is the "today's look" concept (2nd shape after
  `TodaysLookData`).
- ⚠ `DailyOutfitComponent` duplicates `OutfitItemData`, `OutfitComponent` (§8),
  `EnsembleComponent` (§6), `DetectedClothingItem` (§7).
- ⚠ `StyleDnaContext` duplicates `FaceProfile` (§1), `StyleDnaData` (§12),
  backend `FaceData` (§15).
- ⚠ `WardrobeContext` ("you own 6 of these") duplicates `WardrobeAlternative` /
  `wardrobeMatchCount` concepts in discover (§6).

---

# 4. Feature: Wardrobe (`lib/features/wardrobe/data/wardrobe_mock_data.dart`)

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `WardrobeCategory` | 2 | Category filter chip | `id`/`name`/`iconName` String (req), `itemCount` int (default 0) | UI-only |
| `WardrobeItemData` | 17 | Wardrobe screen item | `id`/`name`/`category`/`color` String (req), `material` String? (opt), `isFavorite` bool (default false) | UI-only, Historical |
| `WardrobeInsightData` | 36 | AI wardrobe insight card | `title`/`insight`/`iconName`/`actionLabel` String, `accentColor` int (all req) + `mock` | UI-only, AI-generated |
| `WardrobeMockData` | 62 | Static holder | `styleType` ('Modern Minimalist'), `categories` (6), `items` (24), `itemsForCategory()`, `countForCategory()` | UI-only, Seed (mirrors defaultWardrobe) |
| `AddItemCategoryConfig` | 296 | Add-item category | `id`/`name`/`iconName` String, `types` `List<String>` (all req); `wardrobeCategoryId` getter (shoes→footwear, layers→outerwear) | UI-only |
| `ColorOption` | 327 | Add-item color swatch | `name` String, `colorValue` int (both req) | UI-only |
| `TextureOption` | 335 | Add-item texture chip | `name` String (req) | UI-only |
| `AddItemConfig` | 342 | Static config holder | `categories` (4), `colors` (18), `textures` (16) | UI-only |

**Duplicates:**
- ⚠ `WardrobeItemData` duplicates `WardrobeEntry` (§1) field-for-field (except
  no `copyWith`/JSON). The wardrobe screen + add flow use `WardrobeItemData`;
  persistence stores `WardrobeEntry`.
- ⚠ `WardrobeInsightData` duplicates `AIWardrobeInsightData` (§3) + backend
  `WARDROBE_INSIGHT` (§16).

---

# 5. Feature: Stylist (`lib/features/stylist/`)

## 5.1 `StylistActionData` (inline)

- **Path:** `lib/features/stylist/presentation/stylist_screen.dart:8`
- **Purpose:** Launcher hub action tile (defined inline in the screen file, not
  in a `data/` dir).
- **Fields:** `id`/`title`/`subtitle` String (req), `icon` IconData (req),
  `accentColor` Color (default gold) + `mockActions` (5: scan_outfit,
  build_outfit, hairstyle, grooming, event).
- **Owner:** `features/stylist`
- **Source:** const in-file
- **Flags:** UI-only
- **Duplicates:** ⚠ duplicates `QuickActionData` (§3) — same id/icon/color/title
  pattern; the 5 action ids also match assistant `action` values and backend
  `NAVIGATION_MAP` keys.

---

# 6. Feature: Discover (`lib/features/discover/data/discover_mock_data.dart`)

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `DiscoverLookData` | 4 | A look card (For You / Trending) | `id`/`imageUrl`/`title`/`description`/`occasion` String, `styleTags`/`fitTags` `List<String>`, `matchScore` int (req); `isTrending` bool (default false), `wardrobeMatchCount` int (default 0), `matchScoreDetails` `MatchScoreDetails?`, `recommendationReasons` `List<RecommendationReason>?`, `ensembleComponents` `List<EnsembleComponent>?`, `wardrobeAlternatives` `List<WardrobeAlternative>?` + `forYouMock` (6) + `trendingMock` (6) | UI-only, AI-generated, Historical |
| `FilterOption` | 745 | Filter chip | `id`/`label` String, `icon` IconData (req); `isSelected` bool (default false) + `copyWith` | UI-only |
| `OccasionFilters` | 783 | Static options | `options` (7: all/work/casual/evening/weekend/event/travel) | UI-only |
| `StyleFilters` | 813 | Static options | `options` (9) | UI-only |
| `FitFilters` | 845 | Static options | `options` (7) | UI-only |
| `DiscoverTab` | 883 | Enum | `forYou`, `trending` | UI-only (enum) |
| `DiscoverTabData` | 892 | Tab meta | `tab` enum, `label` String, `icon` IconData | UI-only |
| `MatchScoreDetails` | 925 | Score breakdown | `overall`/`fit`/`colorHarmony`/`occasion`/`creativity` int (all req) | UI-only, AI-generated |
| `RecommendationReason` | 942 | Reason card | `title`/`description` String, `icon` IconData (all req) | UI-only, AI-generated |
| `EnsembleComponent` | 955 | Ensemble piece | `category`/`name`/`color`/`material`/`fit`/`imageUrl` String, `isOwned` bool (all req) | UI-only, Historical |
| `WardrobeAlternative` | 976 | Alternatives for a component category | `componentCategory` String, `alternatives` `List<WardrobeItem>` (all req) | UI-only, Historical |
| `WardrobeItem` | 987 | Substitutable wardrobe item | `id`/`name`/`color`/`imageUrl` String, `isOwned` bool, `matchScore` int (all req) | UI-only, Historical |

**Duplicates:**
- ⚠ `WardrobeItem` (discover) — a class named `WardrobeItem` that is **not** the
  user's own persisted item; it is a substitute suggestion (id/name/color/imageUrl/
  isOwned/matchScore). Distinct from `WardrobeEntry` (§1) and backend `WardrobeItem` (§15).
- ⚠ `EnsembleComponent` duplicates `DailyOutfitComponent`, `OutfitComponent`,
  `OutfitItemData`, `DetectedClothingItem`.
- ⚠ `MatchScoreDetails`/`RecommendationReason` duplicate the "match score +
  reasons" concept in `OutfitRecommendation`, `GroomingRecommendation`,
  `HairstyleRecommendation`, `StyleScoreBreakdownItem`.

---

# 7. Feature: Outfit Scan (`lib/features/outfit_scan/data/outfit_scan_mock_data.dart`)

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `DetectedClothingItem` | 2 | Item detected from photo | `name`/`category`/`color` String (req), `material` String? (opt) | UI-only, AI-generated, Historical |
| `AnalysisSection` | 17 | One analysis section | `id`/`label`/`description` String (req), `score` double? (opt), `detail` String? (opt) | UI-only, AI-generated |
| `ProcessingStage` | 34 | One scan processing stage | `id`/`label` String (req), `duration` Duration (default 800ms) + `mockStages` (5) | UI-only |
| `OutfitAnalysisData` | 71 | Structured analysis result | `title` String, `sections` `List<AnalysisSection>`, `detectedItems` `List<DetectedClothingItem>` (all req) + `mock` | UI-only, AI-generated, Historical |

**Duplicates:**
- ⚠ `ProcessingStage` — 1 of 4 processing-stage models (also `GenerationStage`
  §8, `HairstyleProcessingStage` §9, `GroomingProcessingStage` §10); identical
  `id`/`label`/`duration` shape.
- ⚠ `DetectedClothingItem` duplicates the outfit-piece shape family.
- ⚠ `AnalysisSection` (score double) vs `StyleScoreBreakdownItem` (int) — similar
  score+label+description pattern.

---

# 8. Feature: Outfit Builder (`lib/features/outfit_builder/data/outfit_builder_mock_data.dart`)

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `BuilderOption` | 4 | Selectable preference chip | `id`/`label` String, `icon` IconData, `description` String (all req) + `occasionOptions` (5: casual/office/date/party/travel), `moodOptions` (4), `fitOptions` (3), `colorPaletteOptions` (3) | UI-only |
| `GenerationStage` | 121 | One generation processing stage | `id`/`label` String (req), `duration` Duration (default 800ms) + `mockStages` (5) | UI-only |
| `OutfitComponent` | 158 | Recommended outfit piece | `id`/`name`/`category`/`color`/`colorHex` String, `reason` String (req), `material` String? (opt) | UI-only, AI-generated, Historical |
| `OutfitRecommendation` | 179 | Full generated outfit | `title` String, `matchScore` double, `components` `List<OutfitComponent>`, `reasons` `List<String>`, `colorHarmony`/`bodyFit`/`occasionMatch`/`styleScoreImpact`/`improvementSuggestion`/`selectedOccasion`/`selectedMood`/`selectedColorPalette` String (all req) + `mock` | UI-only, AI-generated, Historical |

**Duplicates:**
- ⚠ `GenerationStage` — 2 of 4 processing-stage models.
- ⚠ `OutfitComponent` duplicates the outfit-piece family (`DailyOutfitComponent`,
  `EnsembleComponent`, `OutfitItemData`, `DetectedClothingItem`).
- ⚠ `OutfitRecommendation` is the "recommended look" concept — mirrored by
  backend `catalog.py::REFINED_OFFICE`, offline `_LookCard` (office), and
  conceptually `DailyOutfitData`. Also duplicates "score + reasons + metrics"
  patterns elsewhere.

---

# 9. Feature: Hairstyle (`lib/features/hairstyle/data/hairstyle_mock_data.dart`)

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `FaceScanCheck` | 3 | Pre-scan readiness check | `id`/`label` String (req), `isPassing` bool (req), `message` String? (opt) + `mockChecks` (3) | UI-only |
| `HairstyleProcessingStage` | 28 | One face-analysis stage | `id`/`label` String (req), `duration` Duration (default 800ms) + `mockStages` (5) | UI-only |
| `HairstyleRecommendation` | 64 | A hairstyle recommendation | `id`/`name`/`description` String, `matchScore` double, `reasons` `List<String>`, `stylingTips`/`maintenance`/`bestFor` String, `icon` IconData (all req; icon default) | UI-only, AI-generated, Historical |
| `HairstyleAnalysisResult` | 88 | Full hair analysis result | `faceShape`/`skinTone`/`styleDna` String, `topRecommendation` `HairstyleRecommendation`, `alternatives` `List<HairstyleRecommendation>` (all req) + `mock` | UI-only, AI-generated, Historical |

**Duplicates:**
- ⚠ `HairstyleProcessingStage` — 3 of 4 processing-stage models.
- ⚠ `HairstyleRecommendation` mirrors backend `catalog.py::TEXTURED_QUIFF` /
  `CLASSIC_POMPADOUR` (same 94/87 scores) and the offline assistant's cards.
- ⚠ `HairstyleAnalysisResult` duplicates the "analysis result with top rec +
  alternatives" shape of `GroomingAnalysisResult` and `OutfitAnalysisData`.

---

# 10. Feature: Grooming (`lib/features/grooming/data/grooming_mock_data.dart`)

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `GroomingOption` | 3 | Selectable input option | `id`/`label` String, `icon` IconData, `description` String (all req) + `faceShapeOptions` (6), `beardStyleOptions` (6), `densityOptions` (3), `colorOptions` (6) | UI-only |
| `GroomingProcessingStage` | 155 | One grooming-analysis stage | `id`/`label` String (req), `duration` Duration (default 800ms) + `mockStages` (5) | UI-only |
| `GroomingRecommendation` | 191 | A grooming recommendation | `id`/`name`/`description` String, `matchScore` double, `reasons` `List<String>`, `beardLength`/`cheekLine`/`eyewearFrame`/`eyewearRecommendation`/`stylingTips`/`maintenance`/`bestFor` String, `icon` IconData (all req; icon default) | UI-only, AI-generated, Historical |
| `GroomingAnalysisResult` | 223 | Full grooming analysis result | `faceShape`/`beardStyle`/`beardDensity`/`beardColor` String, `topRecommendation` `GroomingRecommendation`, `alternatives` `List<GroomingRecommendation>` (all req) + `mock` | UI-only, AI-generated, Historical |

**Duplicates:**
- ⚠ `GroomingProcessingStage` — 4 of 4 processing-stage models (same shape as
  `ProcessingStage`, `GenerationStage`, `HairstyleProcessingStage`).
- ⚠ `GroomingRecommendation` mirrors backend `catalog.py::STRUCTURED_GOATEE` /
  `CLASSIC_STUBBLE` (92/85) and the offline assistant's grooming card.
- ⚠ `GroomingAnalysisResult` duplicates the "top rec + alternatives" result shape.

---

# 11. Feature: Events (`lib/features/events/data/event_mock_data.dart`)

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `EventType` | 3 | Event type vocabulary | `id`/`name` String, `icon` IconData (all req) + `mockTypes` (8: casual/formal/business/date/party/travel/workout/other) | UI-only |
| `UserEvent` | 34 | A user's event | `id`/`name`/`date`/`time` String, `eventType` `EventType`, `hasOutfitRecommendation` bool (default false) + `mockEvents` (4) + `typeById(id)` | UI-only, Historical |

**Duplicates:**
- ⚠ `UserEvent` is **not persisted** — events are held in `EventListScreen`
  state only and never written to `UserModel`. `EventType.name` is recorded as a
  `LearningSignal` via `addPreferredOccasion`, but the event itself is lost on restart.
- ⚠ Occasion vocabulary mismatch: `EventType` ids (formal/business/date/party/
  travel/workout) differ from builder/assistant occasions (casual/office/date/
  party/travel) and discover `OccasionFilters` (work/evening/weekend/event) — 4
  overlapping vocabularies (see §19).

---

# 12. Feature: Profile (`lib/features/profile/data/`)

Two files: `profile_mock_data.dart` (dashboard) and `profile_mocks.dart`
(preferences / saved looks / subscription / support / settings).

## 12.1 `profile_mock_data.dart`

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `ProfileData` | 1 | Full profile dashboard model | `name`/`username`/`avatarInitials`/`joinDate` String, `stylistLevel` `StylistLevelData`, `styleScore` int, `globalRank` `GlobalRankData`, `styleProgress` `StyleProgressData`, `styleDna` `StyleDnaData`, `achievements` `List<AchievementData>`, `savedLooks` `List<SavedLookPreview>`, `menuActions` `List<ProfileMenuAction>` (all req) + `mock` | UI-only, Historical |
| `StylistLevelData` | 114 | Level label/progress | `label` String, `level`/`maxLevel` int (all req) | UI-only |
| `GlobalRankData` | 126 | Global rank | `position`/`total` int (all req) | UI-only, Historical |
| `StyleProgressData` | 133 | XP progress | `current`/`next` int, `label` String (all req) | UI-only, Historical |
| `StyleDnaData` | 145 | Style DNA block | `skinTone`/`faceShape`/`bodyType`/`styleType` String (all req) | UI-only, AI-generated |
| `AchievementData` | 159 | Achievement badge | `iconName`/`label` String (req), `unlocked` bool (req) | UI-only, Historical |
| `SavedLookPreview` | 171 | Saved-look summary | `id`/`title` String, `score` int (all req) | UI-only, Historical |
| `ProfileMenuAction` | 183 | Profile menu item | `id`/`label`/`iconName` String (all req) | UI-only |

## 12.2 `profile_mocks.dart`

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `PreferenceOption` | 1 | Preference row | `label`/`value` String, `options` `List<String>`, `selectedIndex` int (default 0) | UI-only |
| `SavedLookDetail` | 15 | Saved look detail | `id`/`title`/`date` String, `score` int, `items` `List<String>` (all req) | UI-only, Historical |
| `SubscriptionPlan` | 31 | Plan card | `name`/`price`/`period` String, `features` `List<String>`, `isPopular` bool (all req) | UI-only |
| `SupportTopic` | 47 | Support tile | `title`/`description`/`iconName` String (all req) | UI-only |
| `SettingsItem` | 59 | Settings row | `label`/`description` String (req), `value` String? (opt), `isSwitch`/`switchValue` bool (default false) | UI-only |
| `ProfileMockData` | 75 | Static holder | `stylePreferences` (4), `savedLooks` (6), `plans` (3), `topics` (6), `settingsGroups` (6) | UI-only |

**Duplicates:**
- ⚠ `ProfileData` / `SavedLookPreview` / `SavedLookDetail` vs persisted
  `UserModel.savedLooks` (List<String>) — 3 saved-look shapes, none reading the
  persisted list (SavedLooksScreen shows `ProfileMockData.savedLooks`).
- ⚠ `StyleDnaData` duplicates `FaceProfile` (§1), `StyleDnaContext` (§3),
  backend `FaceData` (§15) — the style-DNA concept, 3 Flutter shapes + 1 backend.
- ⚠ `StyleScoreData` (home) vs `ProfileData.styleScore`/`StyleProgressData` —
  two "style score" representations.

---

# 13. Feature: Onboarding (`lib/features/onboarding/data/onboarding_data.dart`)

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `StyleVibe` (enum) | 3 | 6 style vibes | `label`/`description` String per value (minimalist/bold/classic/trendy/natural/edgy) | UI-only, Seed (feeds home light-path) |
| `vibeGradientColors` | 24 | Per-vibe gradient pair | `Map<StyleVibe, List<Color>>` | UI-only |
| `AnalysisResult` | 33 | Mock analysis result | `score` int, `silhouetteLabel` String, `observations` `List<String>`, `palette` `List<PaletteSwatch>`, `formalityLabel` String | UI-only, **Dead code** |
| `PaletteSwatch` | 49 | Palette swatch | `color` int, `label` String (both req) | UI-only |
| `AiCapability` | 55 | Capability status | `name`/`description` String, `active` bool, `unlockHint` String? (opt) | UI-only |
| `OnboardingResult` | 69 | Onboarding outcome | `vibe` `StyleVibe?`, `analysis` `AnalysisResult?`, `displayName` String? | UI-only, **Dead code** |
| `allCapabilities` | 79 | 7 AI capabilities | `List<AiCapability>` (Face Analysis + Color Analysis active; 5 locked) | UI-only |

**Notes:**
- **Dead code:** `AnalysisResult` and `OnboardingResult` are defined but never
  referenced anywhere in `lib/` or `test/` (verified by search). `YourAnalysisScreen`
  and `FirstTimeHomeScreen` build their own inline palettes from `PaletteSwatch`
  and use `allCapabilities` directly.
- ⚠ `StyleVibe` (6 values) vs profile `PreferenceOption.stylePreferences` style
  options (5: Modern Minimalist/Classic Elegance/Street Style/Bohemian/Athleisure)
  vs builder `moodOptions` vs discover `StyleFilters` — 4 overlapping style
  vocabularies (see §19).

---

# 14. Feature: Shared (`lib/shared/`)

## 14.1 `UserSession`

- **Path:** `lib/shared/utils/user_session.dart:5`
- **Purpose:** Session-scoped flags (no persistence). Only member:
  `static bool hasSavedWardrobeItem = false` — gates the light-path first-visit
  Home branch after the user adds their first wardrobe item.
- **Owner:** shared
- **Source:** ephemeral in-memory
- **Flags:** Ephemeral
- **Duplicates:** none (but it is user-flag data living outside `features/learning`).

## 14.2 Theme/component classes (not data models)

`FansivibeColors`, `FansivibeTypography`, `FansivibeSpacing`, `FansivibeRadius`,
`FansivibeShadows`, `FansivibeTheme`, plus widget-only enums (`BadgeSize`,
`FansiButtonVariant`, `CardVariant`) — presentation tokens, excluded from this
inventory.

---

# 15. Backend: models (`backend/app/models/schemas.py`)

Pydantic DTOs. The docstring states they are the typed request/response
contract shared with the app; the Flutter client mirrors them exactly. **No DB,
no ORM, no persistence in the backend.**

| Model | Line | Purpose | Fields | Flags |
|-------|------|---------|--------|-------|
| `WardrobeItem` | 16 | Wardrobe item in context | `id`/`name`/`category`/`color` str, `material` Optional[str], `isFavorite` bool (default False) | API (request part) |
| `FaceData` | 25 | Face attributes in context | `faceShape`/`skinTone`/`bodyType`/`styleType` Optional[str] | API (request part) |
| `UserContext` | 32 | Snapshot of the on-device user model | `wardrobe` `List[WardrobeItem]`, `face` `Optional[FaceData]`, `savedLooks` `List[str]`, `preferredOccasions` `List[str]` | API (request part) |
| `ChatMessage` | 41 | One message | `role` str, `content` str | API |
| `AssistantRequest` | 46 | Chat request | `messages` `List[ChatMessage]`, `user` `Optional[UserContext]` | API (request) |
| `SuggestionCard` | 51 | Typed result card | `kind`/`title`/`subtitle` str, `score` Optional[int], `items` `List[str]`, `action` Optional[str] | API (response part) |
| `ClarificationOption` | 60 | Clarification chip | `label` str, `value` str | API |
| `NavigationRequest` | 65 | Navigation | `route` str, `label` str | API |
| `AssistantReply` | 70 | Structured reply | `intent` str, `text` str, `cards` `List[SuggestionCard]`, `clarifications` `List[ClarificationOption]`, `navigation` Optional[NavigationRequest] | API (response) |

**Duplicates:**
- Mirrors the Flutter `assistant/data/models.dart` DTOs 1:1 (by design — the
  sync contract).
- ⚠ `WardrobeItem`/`FaceData`/`UserContext` re-express the persisted
  `WardrobeEntry`/`FaceProfile`/`UserModel` (§1) minus `styleType`/`signals`.

---

# 16. Backend: catalog (`backend/app/data/catalog.py`)

Static recommendation data (a mirror of the Flutter mocks). No DB.

| Constant | Purpose | Flags |
|----------|---------|-------|
| `WARDROBE` (`List[WardrobeItem]`, 24) | Static wardrobe mirroring `WardrobeMockData.items` / `defaultWardrobe` | API, Seed |
| `REFINED_OFFICE` / `CASUAL_LOOK` (`SuggestionCard`) | Office/casual outfit looks | API, AI-generated |
| `TEXTURED_QUIFF` / `CLASSIC_POMPADOUR` | Hairstyle looks | API, AI-generated |
| `STRUCTURED_GOATEE` / `CLASSIC_STUBBLE` | Grooming looks | API, AI-generated |
| `STYLE_TIP` / `WARDROBE_INSIGHT` | Tip / wardrobe insight cards | API, AI-generated |
| `OCCASIONS` (`List[str]`) | casual/office/date/party/travel | — (vocabulary) |
| `OCCASION_TO_LOOK` (`Dict[str, SuggestionCard]`) | Per-occasion looks (also date/party/travel) | API, AI-generated |
| `NAVIGATION_MAP` (`Dict[str, tuple]`) | assistant `action` → (route, label) | — (routing config) |

**Duplicates:**
- ⚠ The same 5 looks are mirrored in Flutter as `OutfitRecommendation.mock`,
  `DailyOutfitData.mock`, and `OfflineAssistant._LookCard` — the same content in
  4 shapes across 3 codebases (Flutter UI, Flutter offline, backend).
- ⚠ `WARDROBE` re-encodes the 24-item wardrobe a 3rd time (see §1.7, §4).

---

# 17. Backend: AI engine (`backend/app/ai/`)

Deterministic logic — the structured "own AI" layer. Constants/maps, not models,
but included for the data-flow picture.

| File | Purpose | Notes |
|------|---------|-------|
| `intent.py` | Rules-based intent classifier + occasion detector | `INTENT_*` string constants (outfit/hairstyle/grooming/wardrobe/navigate/tip/greeting/thanks/clarify/unknown); `_NAVIGATE_TARGETS` map |
| `tools.py` | Recommendation tools grounded in user context | Returns `SuggestionCard`s from `catalog` |
| `engine.py` | Orchestration: intent → tools → dialogue policy | `_OUTFIT_CLARIFICATION` (5 occasion chips), `_context_summary` string building |
| `llm_backend.py` | Optional Ollama enrichment | Only rewrites reply **text**; never touches structure |

**Duplicates:**
- ⚠ `intent.py` keyword lists + `engine.py` dialogue policy are duplicated on the
  client in `OfflineAssistant` (`offline_assistant.dart`) — two copies of the
  rules engine (online backend vs offline fallback).
- ⚠ `_NAVIGATE_TARGETS` (intent.py) vs `NAVIGATION_MAP` (catalog.py) vs offline
  `_navigateFor` targets — three navigation maps.

---

# 18. Repositories / services / API summary

| Artifact | Path | Kind | Backed by |
|----------|------|------|-----------|
| `LearningRepository` | `lib/features/learning/learning_repository.dart` | abstract contract | — |
| `LearningService` | `lib/features/learning/domain/learning_service.dart` | singleton `ChangeNotifier` | `LocalStore` + in-memory `UserModel` |
| `LocalStore` | `lib/features/learning/data/local_store.dart` | persistence adapter | SharedPreferences key `fansivibe.user_model.v1` |
| `AssistantService` | `lib/features/assistant/domain/assistant_service.dart` | `ChangeNotifier` conversation orchestration | `AssistantClient` → backend, else `OfflineAssistant`; records signals via `LearningRepository` |
| `AssistantClient` | `lib/features/assistant/data/assistant_client.dart` | HTTP client | `POST {base}/v1/assistant/chat` (12s timeout, null on failure) |
| `OfflineAssistant` | `lib/features/assistant/data/offline_assistant.dart` | offline rules engine | Flutter mock data + learning context |
| FastAPI app | `backend/app/main.py` | `/health`, `/v1/assistant/chat` | `engine.handle()` (no DB) |

**Service→model ownership (who writes what):**
- `LearningService`: persists `UserModel`; writes `item_added`, `look_saved`,
  `occasion_preferred`, `analysis_updated`, `style_updated` signals.
- `AssistantService`: records `assistant_message`, `suggestion_opened`,
  `assistant_navigation` signals; builds `AssistantUserContext` snapshot.
- All other features only **read** mocks or write via `LearningService.instance`.

---

# 19. Final analysis (input for the DB/service-layer design)

> These are observations, not approved changes. Each category below points at
> the concrete models from the inventory so the next phase can design around them.

## 19.1 Duplicated concepts (models that represent the same real-world thing)

| Concept | Distinct shapes | Where (inventory refs) |
|---------|-----------------|------------------------|
| Wardrobe item | 3–4 | `WardrobeEntry` (§1), `WardrobeItemData` (§4), backend `WardrobeItem` (§15), plus the discover `WardrobeItem` **alternative** (§6) — 4 shapes, 3 identical fields |
| Style DNA / face profile | 4 | `FaceProfile` (§1), `StyleDnaContext` (§3), `StyleDnaData` (§12), backend `FaceData` (§15) |
| Processing / generation stage | 4 | `ProcessingStage` (§7), `GenerationStage` (§8), `HairstyleProcessingStage` (§9), `GroomingProcessingStage` (§10) — identical id/label/duration shape |
| Saved look | 3 | persisted `UserModel.savedLooks` (List\<String\>, §1), `SavedLookPreview` (§12.1), `SavedLookDetail` (§12.2) — none reads the persisted list |
| Today's look / recommended look | 3–4 | `TodaysLookData` (§3.1), `DailyOutfitData` (§3.2), `OutfitRecommendation` (§8), backend `catalog` looks (§16), offline `_LookCard` (§2.9) |
| Wardrobe insight | 3 | `WardrobeInsightData` (§4), `AIWardrobeInsightData` (§3.1), backend `WARDROBE_INSIGHT` (§16) |
| Outfit piece | 5 | `OutfitItemData` (§3.1), `DailyOutfitComponent` (§3.2), `EnsembleComponent` (§6), `OutfitComponent` (§8), `DetectedClothingItem` (§7) |
| Quick action / stylist action | 2 | `QuickActionData` (§3.1), `StylistActionData` (§5) |
| Match score + reasons | 5+ | `MatchScoreDetails`/`RecommendationReason` (§6), `OutfitRecommendation` reasons/metrics (§8), `HairstyleRecommendation` (§9), `GroomingRecommendation` (§10), `StyleScoreBreakdownItem` (§3.1), `AnalysisSection` (§7) |
| Occasion vocabulary | 4 | `EventType` ids (§11), builder/assistant `occasionOptions` (§8, §2.8, backend `OCCASIONS` §16), discover `OccasionFilters` (§6), profile `PreferenceOption` occasion focus (§12.2) |
| Style vocabulary | 4 | `StyleVibe` (§13), profile style preferences (§12.2), builder `moodOptions` (§8), discover `StyleFilters` (§6) |

## 19.2 UI-only models (no domain meaning; candidate to stay as view DTOs)

These describe how a screen looks, not product facts — keep them UI-local or
collapse them into one shared view-DTO:
- `GreetingData`, `StyleTrend`, `StyleStreakData`, `StreakDayData`, `QuickActionData` (§3.1)
- `WardrobeCategory`, `ColorOption`, `TextureOption`, `AddItemCategoryConfig`, `AddItemConfig` (§4)
- `FilterOption`, `OccasionFilters`, `StyleFilters`, `FitFilters`, `DiscoverTab`, `DiscoverTabData` (§6)
- `BuilderOption`, `GenerationStage`, `ProcessingStage`, `HairstyleProcessingStage`, `GroomingProcessingStage` (§7–§10)
- `FaceScanCheck` (§9), `GroomingOption` (§10), `EventType` (§11)
- `ProfileMenuAction`, `AchievementData`, `SubscriptionPlan`, `SupportTopic`, `SettingsItem`, `PreferenceOption`, `AiCapability`, `PaletteSwatch`, `vibeGradientColors`, `allCapabilities` (§12–§13)
- `StylistActionData` (§5), `UserSession` flag (§14)

## 19.3 Domain-like models (real product concepts — the candidates for DB tables)

These are the facts the app actually cares about; everything else derives from
them:
- `UserModel` aggregate + `WardrobeEntry` + `FaceProfile` + `LearningSignal` (§1) — already the persisted core
- `UserEvent` (§11) — real entity today, **unpersisted**
- `DiscoverLookData` (looks catalog) (§6) — real catalog content
- `DailyOutfitData` / `OutfitRecommendation` / saved looks (§3.2, §8) — the "look" entity family
- `StyleDnaData`/`StyleDnaContext`/`FaceProfile` — the style-profile entity
- `StyleScoreData` + `styleScore` (§3.1, §1.6) — computed/derived value
- `HairstyleRecommendation`/`GroomingRecommendation` + results (§9–§10) — recommendation entities
- `AiCapability` (§13) — capability/feature-flag entity

## 19.4 API DTOs (boundary contracts — keep mirrored, don't persist)

- Flutter `assistant/data/models.dart` (§2.1–2.6) ↔ backend `schemas.py` (§15).
  These are wire contracts; a DB should store the *domain* equivalents, not these.
- Backend `catalog.py` constants (§16) are **static content**, not DB yet — they
  are the seed of a looks/wardrobe catalog.

## 19.5 Mock-only models (hardcoded today; where the real data will come from)

Every model flagged **Historical** is a `static const` stand-in for future
backend/DB data:
- wardrobe seed + catalog (§1.7, §4, §16)
- looks/discover feeds (§6), today's-look (§3.2), outfit builder results (§8)
- analysis results: hairstyle (§9), grooming (§10), outfit scan (§7), profile (§12)
- streak / score / rank / achievements (§3.1, §12) — would need per-user state
- events (§11) — currently lost on restart

## 19.6 Missing data concepts (referenced by UI/UX but not modeled at all)

Concepts the product implies but no model represents today:
- **User / account / auth** — `AccountCreationScreen` collects email/password/name
  and "sign in" is a mock; no `User` entity exists.
- **Style score & streak persistence** — computed in-memory (`LearningService.styleScore`)
  or hardcoded mocks; no history table (only `LearningSignal` history exists).
- **Event persistence** — events are widget state; not in `UserModel`.
- **Achievements / ranks / XP** — mock only, no model.
- **Wardrobe item images / media** — `imageUrl` strings in discover; no asset/image entity.
- **Recommendation history** — cards/scores are mock or ephemeral; only `look_saved`
  signals capture a trace.
- **Subscription / plans** — mock only.
- **Saved-look full payload** — persisted only as `List<String>` titles; details
  (components, date, items) exist only in mocks.
- **Current/last "today's look"** — not persisted; regenerated from mock.

## 19.7 Ambiguous ownership

Models whose owning feature is unclear or whose data lives in the wrong layer:
- **`UserSession.hasSavedWardrobeItem`** (§14) — a user flag outside `features/learning`;
  should be part of the user model when persistence exists.
- **`UserEvent`** (§11) — event data owned by `events`, written to learning only
  as `addPreferredOccasion`; no single owner for the entity itself.
- **Saved looks** — three shapes owned by `profile`, `home`, `learning` (§1, §3.2,
  §12); the persisted source of truth is `learning`, but screens read mocks.
- **Style/occasion vocabularies** — 4 independent vocabularies across features
  (§11, §6, §8, §12); no shared configuration source (violates the "no hardcoded
  backend-controlled categories" rule).
- **Offline rules engine** (`OfflineAssistant`, §2.8) vs backend engine (§17) —
  the same business logic duplicated across two codebases with no shared contract
  or generated source.
- **`AssistantUserContext`** (§2.6) — domain data (wardrobe/face) re-shaped as a
  DTO in the assistant feature rather than consumed directly from the contract.
- **`AnalysisResult`/`OnboardingResult`** (§13) — dead models whose intent
  (onboarding analysis result) is re-implemented inline elsewhere; decide whether
  to remove or promote to the real analysis entity.
