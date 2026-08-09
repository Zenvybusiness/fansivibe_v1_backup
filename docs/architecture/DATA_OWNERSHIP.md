# Fansivibe — Data Ownership Analysis

> Companion to `FEATURE_INVENTORY.md`, `SCREEN_DATA_INVENTORY.md`,
> `DATA_MODEL_INVENTORY.md`, and `FEATURE_DATA_MATRIX.md`.
>
> For every important data concept this document determines who owns/creates/
> modifies/reads it, whether it is user-specific or system-wide, AI-generated,
> knowledge, external, historical, whether it can be deleted, and what references
> it — then classifies each entity into exactly one of:
>
> **USER_OWNED** — belongs to a single user; created/modified by user actions;
> per-user durable state.
>
> **SYSTEM_OWNED** — owned by the platform/app; configuration, feature flags,
> navigation, session flags, infrastructure.
>
> **AI_GENERATED** — produced by AI analysis/generation (or today's mock stand-in
> that will be AI-produced).
>
> **KNOWLEDGE** — curated static catalog content (looks, options, tips,
> vocabularies) that is system-authored reference data.
>
> **EXTERNAL** — data obtained from an external service/system (device media,
> future image-analysis, purchase service).
>
> **DERIVED** — computed on the fly from other data (scores, counts, ranks,
> aggregation).
>
> **HISTORICAL** — append-only history/audit data (signals, past results).
>
> Entities are classified by their **primary** nature; secondary aspects are noted
> in each block. This is documentation only — no code, no SQL, no UI changes.
> Claims verified against source; inventory refs point at `DATA_MODEL_INVENTORY.md`.

---

## Master classification

| Entity | Classification | Notes |
| --- | --- | --- |
| `UserModel` (aggregate) | USER_OWNED | The whole per-user model blob |
| `WardrobeEntry` | USER_OWNED | User-added item |
| `FaceProfile` | USER_OWNED | (AI-derived attributes, but user-owned entity; **never written today**) |
| `LearningSignal` | HISTORICAL | Append-only interaction log |
| `defaultWardrobe` (seed) | KNOWLEDGE | System-authored starter catalog |
| `AssistantUserContext` | DERIVED | Snapshot derived from UserModel for the request |
| `AssistantMessage` | USER_OWNED | User-authored text + assistant replies (ephemeral) |
| `SuggestionCard` / `AssistantReply` / `ClarificationOption` / `NavigationRequest` | AI_GENERATED | Backend/offline engine output (DTO shape) |
| `_LookCard` (offline) | KNOWLEDGE | Hardcoded look mirror |
| `GreetingData`, `QuickActionData`, `StyleTrend` | SYSTEM_OWNED | Static dashboard chrome |
| `TodaysLookData`, `DailyOutfitData`, `AlternativeLookData` | KNOWLEDGE | Catalog look (mock stand-in; will be AI/catalog) |
| `StyleScoreData`, `StyleScoreBreakdownItem` | DERIVED | Computed score + breakdown |
| `StyleStreakData`, `StreakDayData` | HISTORICAL | Per-user streak history (mock today) |
| `AIWardrobeInsightData`, `WardrobeInsightData`, `AiInsightData` | AI_GENERATED | Insight content (mock today) |
| `StyleDnaContext`, `StyleDnaData` | DERIVED | Style DNA derived from FaceProfile (mock today) |
| `WardrobeContext` | DERIVED | Wardrobe stats derived from items |
| `WardrobeItemData`, `WardrobeMockData` | USER_OWNED | UI copy of user wardrobe (mock seed today) |
| `WardrobeCategory`, `ColorOption`, `TextureOption`, `AddItemCategoryConfig`, `AddItemConfig` | KNOWLEDGE | Add-item vocabularies/config |
| `StylistActionData` | SYSTEM_OWNED | Launcher config |
| `DiscoverLookData` | KNOWLEDGE | Looks catalog (mock today) |
| `MatchScoreDetails`, `RecommendationReason` | AI_GENERATED | Match scoring output |
| `EnsembleComponent`, `WardrobeAlternative`, `WardrobeItem`(discover) | DERIVED | Look detail derived from catalog + wardrobe |
| `FilterOption`, `OccasionFilters`, `StyleFilters`, `FitFilters`, `DiscoverTab`, `DiscoverTabData` | KNOWLEDGE | Filter vocabularies/config |
| `OutfitAnalysisData`, `AnalysisSection`, `DetectedClothingItem` | AI_GENERATED | Scan analysis output (mock today) |
| `ProcessingStage`, `GenerationStage`, `HairstyleProcessingStage`, `GroomingProcessingStage` | SYSTEM_OWNED | Processing UI choreography |
| `OutfitRecommendation`, `OutfitComponent` | AI_GENERATED | Generated outfit (mock today) |
| `BuilderOption` | KNOWLEDGE | Builder option vocabulary |
| `FaceScanCheck` | SYSTEM_OWNED | Readiness-check config |
| `HairstyleRecommendation`, `HairstyleAnalysisResult` | AI_GENERATED | Hairstyle analysis output (mock today) |
| `GroomingRecommendation`, `GroomingAnalysisResult` | AI_GENERATED | Grooming analysis output (mock today) |
| `GroomingOption` | KNOWLEDGE | Grooming option vocabulary |
| `EventType` | KNOWLEDGE | Event-type vocabulary |
| `UserEvent` | USER_OWNED | User-created event (**unpersisted today**) |
| `ProfileData`, `StylistLevelData`, `GlobalRankData`, `StyleProgressData`, `AchievementData` | DERIVED | Profile stats derived from user activity (mock today) |
| `SavedLookPreview`, `SavedLookDetail` | DERIVED | Saved-look summaries (mock today; source = UserModel.savedLooks) |
| `ProfileMenuAction`, `SettingsItem`, `SupportTopic`, `SubscriptionPlan`, `PreferenceOption` | KNOWLEDGE | Profile/config content |
| `StyleVibe`, `vibeGradientColors`, `PaletteSwatch`, `AiCapability`, `allCapabilities` | KNOWLEDGE | Onboarding config/capabilities |
| `AnalysisResult`, `OnboardingResult` | AI_GENERATED | Dead-code onboarding result (never used) |
| `UserSession.hasSavedWardrobeItem` | SYSTEM_OWNED | Session flag (ephemeral) |
| Backend `schemas.py` DTOs | SYSTEM_OWNED | Wire contract (request/response shape) |
| Backend `catalog.py` constants | KNOWLEDGE | Static catalog content |
| Backend AI engine (intent/tools/engine/llm_backend) | SYSTEM_OWNED | System logic (produces AI_GENERATED output) |

**Gaps for the future design** (see §Missing concepts): no `User`/auth entity,
no persisted event rows, no score/streak history, no achievement/rank model, no
image/media entity, no recommendation history, no subscription state — every one
of these will be USER_OWNED or HISTORICAL when added.

---

## Domain entities (full 12-question detail)

### `UserModel` (aggregate)

- **Who owns it?** `features/learning` (sole persistence owner).
- **Who creates it?** `LocalStore`/`LearningService.load()` — seeded with
  `defaultWardrobe` on first run.
- **Who can modify it?** `LearningService` only, via public methods
  (`addItem`, `setFace`, `setStyleType`, `addSavedLook`, `addPreferredOccasion`,
  `recordSignal`). No other feature touches it directly.
- **Who can read it?** `features/learning` (repository contract); Assistant
  reads it to build context; Wardrobe/Home/Discover/Events/OutfitScan write
  through it.
- **User-specific?** Yes — one model per device/user.
- **System-wide?** No.
- **AI-generated?** Partly — `face`/`styleType` are AI-analysis outputs when
  written; the rest is user data.
- **Knowledge data?** No (its seed wardrobe is knowledge, the aggregate is not).
- **External?** No.
- **Historical?** No (current-state snapshot, not append-only).
- **Can it be deleted?** Yes — the whole blob is replaceable (nothing today
  exposes delete; reinstall/reset drops it).
- **References it?** `AssistantUserContext` (mirror), `WardrobeScreen` reads
  `.wardrobe`, Home reads name via onboarding extras (not the model), all
  `LearningService` consumers.
- **Primary classification:** USER_OWNED.

### `WardrobeEntry`

- **Owner:** `features/learning`. **Creates:** user via Wardrobe Add Item →
  `LearningService.addItem` (also seed `defaultWardrobe`). **Modifies:**
  `LearningService` (`copyWith(isFavorite)`); edit/delete UI is snackbar-only.
  **Reads:** wardrobe screen, assistant context, (future) discover matching.
- **User-specific?** Yes. **System-wide?** No. **AI-generated?** No (future
  image tags may be). **Knowledge?** No. **External?** No. **Historical?** No
  (mutated current state; only `item_added` signals are historical).
- **Deleted?** Yes (user-owned; delete flow is a stub today).
- **Referenced by:** `UserModel.wardrobe`, `AssistantUserContext.wardrobe`,
  `WardrobeItemData` (UI dup), backend `WardrobeItem` (DTO dup).
- **Primary classification:** USER_OWNED.

### `FaceProfile`

- **Owner:** `features/learning`. **Creates:** intended = onboarding/scan
  analysis via `setFace` — **no screen calls it today**, so it stays null.
  **Modifies:** `setFace`. **Reads:** assistant context, (would-be) hairstyle/
  grooming/profile style-DNA.
- **User-specific?** Yes. **System-wide?** No. **AI-generated?** Yes — its
  fields (`faceShape`, `skinTone`, `bodyType`, `styleType`) are analysis
  outputs. **Knowledge?** No. **External?** No (values derived from device
  images). **Historical?** No (current snapshot).
- **Deleted?** Yes (user-owned; no UI path today).
- **Referenced by:** `UserModel.face`, `AssistantUserContext.face`, backend
  `FaceData` (DTO dup), `StyleDnaData`/`StyleDnaContext` (derived dups).
- **Primary classification:** USER_OWNED (entity) / AI_GENERATED (content).

### `LearningSignal`

- **Owner:** `features/learning`. **Creates:** `LearningService` + features via
  `recordSignal` (8 types). **Modifies:** none — append-only. **Reads:**
  `features/learning` (aggregate consumers). 
- **User-specific?** Yes (per-user). **System-wide?** No. **AI-generated?** No.
  **Knowledge?** No. **External?** No. **Historical?** Yes — the only
  append-only history in the system.
- **Deleted?** Ideally no (audit); nothing deletes today. **Referenced by:**
  `UserModel.signals`; future analytics.
- **Primary classification:** HISTORICAL.

### `UserEvent`

- **Owner:** ambiguous — created in `features/events` (`EventListScreen`
  state); persisted only as `EventType.name` via `addPreferredOccasion`.
  **Creates:** user (Add Event form). **Modifies:** none. **Reads:** events
  screens only (widget state).
- **User-specific?** Yes. **System-wide?** No. **AI-generated?** No.
  **Knowledge?** No. **External?** No. **Historical?** Arguably — events are
  dated, but they are **not persisted** (lost on restart).
- **Deleted?** Should be (user-owned); nothing deletes today.
- **Referenced by:** nothing durable (only `preferredOccasions` signal + the
  event-type vocabulary).
- **Primary classification:** USER_OWNED (entity), with HISTORICAL aspects.

### `DiscoverLookData` and the "look" family

(`DiscoverLookData`, `TodaysLookData`, `DailyOutfitData`,
`OutfitRecommendation`, backend catalog looks, offline `_LookCard`)

- **Owner:** `features/discover`/`home`/`outfit_builder` for the Flutter shapes;
  **backend `catalog.py`** for the canonical content. **Creates:** system
  (catalog authoring) today — all static. **Modifies:** none. **Reads:**
  discover/home/builder screens, assistant offline replies.
- **User-specific?** No — the *catalog* is system-wide content; per-user
  aspects (`wardrobeMatchCount`, `isOwned`) are derived. **System-wide?** Yes
  (shared feed). **AI-generated?** The match scoring is; the look content is
  authored. **Knowledge?** Yes — curated catalog. **External?** No (future:
  look images in object storage). **Historical?** Today's-look is regenerated
  per day (a dated snapshot); feed items are static.
- **Deleted?** Catalog rows yes (system admin); no user-facing delete.
- **Referenced by:** `EnsembleComponent`, `WardrobeAlternative`,
  `MatchScoreDetails`, `RecommendationReason`, `DailyOutfitComponent`,
  `OutfitComponent`; saved-look titles reference look ids.
- **Primary classification:** KNOWLEDGE (content) with AI_GENERATED (scoring).

### Saved looks (persisted + UI shapes)

(`UserModel.savedLooks` List<String>, `SavedLookPreview`, `SavedLookDetail`)

- **Owner:** persisted truth = `features/learning`; displayed shapes owned by
  `profile`. **Creates:** user via Discover/OutfitScan/Home `addSavedLook`.
  **Modifies:** none (additive). **Reads:** profile Saved Looks screen — but it
  reads **mock** `ProfileMockData.savedLooks`, not the persisted list.
- **User-specific?** Yes. **System-wide?** No. **AI-generated?** No (user
  chooses; the referenced look is AI/catalog content). **Knowledge?** No.
  **External?** No. **Historical?** Partly — save actions have timestamps
  conceptually; today only titles.
- **Deleted?** Should be (user-owned); no UI path today.
- **Referenced by:** `UserModel.savedLooks`; `AssistantUserContext.savedLooks`.
- **Primary classification:** USER_OWNED.

### `AssistantUserContext`

- **Owner:** `features/assistant` (built in `AssistantService._buildContext`).
  **Creates:** `AssistantService` from the learning repository per request.
  **Modifies:** none (fresh snapshot each request). **Reads:** backend
  (`UserContext` schema) / `OfflineAssistant`.
- **User-specific?** Yes (copy of user data). **System-wide?** No.
  **AI-generated?** No. **Knowledge?** No. **External?** No (sent *to* an
  external service, not sourced from one). **Historical?** No.
- **Deleted?** Ephemeral per request — nothing retained.
- **Referenced by:** `AssistantRequest.user`; backend `UserContext`.
- **Primary classification:** DERIVED.

### `AssistantMessage` / conversation

- **Owner:** `features/assistant` (`AssistantService` holds the list).
  **Creates:** user messages + engine replies. **Modifies:** none (append;
  pending flag toggles). **Reads:** assistant screen.
- **User-specific?** Yes (per-user conversation). **System-wide?** No.
  **AI-generated?** Assistant turns yes; user turns no. **Knowledge?** No.
  **External?** Engine replies come from the backend (external) or offline
  engine. **Historical?** Session history only — **not persisted**.
- **Deleted?** Cleared with the session; no explicit delete.
- **Referenced by:** request payload `messages`; `LearningSignal`
  (`assistant_message`) traces.
- **Primary classification:** USER_OWNED (session) — candidates for HISTORICAL
  if conversations are retained.

### Backend DTOs (`schemas.py`)

- **Owner:** backend (FastAPI contract). **Creates:** serializers/validation.
  **Modifies:** none (immutable wire shape). **Reads:** app client + backend
  engine.
- **User-specific?** Partly (`UserContext` carries user data; `AssistantReply`
  is generic). **System-wide?** The contract is. **AI-generated?** The reply
  payload is; the DTO shape is not. **Knowledge?** No. **External?** They are
  the *boundary* of the external service. **Historical?** No.
- **Deleted?** N/A (schema).
- **Referenced by:** Flutter `assistant/data/models.dart` mirror (1:1).
- **Primary classification:** SYSTEM_OWNED (contract).

### Backend catalog (`catalog.py`)

- **Owner:** backend (system content). **Creates:** system authoring.
  **Modifies:** system admin. **Reads:** backend tools/engine → replies.
- **User-specific?** No. **System-wide?** Yes. **AI-generated?** No (authored;
  structured as if AI). **Knowledge?** Yes — canonical catalog. **External?**
  No. **Historical?** No.
- **Deleted?** Yes (content management), no UI path.
- **Referenced by:** `tools.py`, `engine.py`, offline `_LookCard`,
  Flutter mocks (mirrors).
- **Primary classification:** KNOWLEDGE.

---

## Per-feature ownership (UI-only / mock / config models)

These are compact: ownership is uniform within each row's feature; the 12
questions reduce to the few dimensions that vary. Inventory refs in parens.

### Learning (infrastructure)

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `LocalStore` (1.5) | SYSTEM_OWNED | Persistence adapter, no domain data; read/write by `LearningService` only |
| `LearningRepository`/`LearningService` (1.6) | SYSTEM_OWNED | The contract + singleton; sole writer of UserModel; read by all features |
| `defaultWardrobe` seed (1.7) | KNOWLEDGE | System-authored 24-item starter; consumed by wardrobe screen + assistant fallback; mirrors §4/§16 |

### Assistant

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `SuggestionCard`/`AssistantReply`/`ClarificationOption`/`NavigationRequest` (2.1–2.4) | AI_GENERATED | Created by backend engine or `OfflineAssistant`; read by assistant screen; user-specific only in content, not shape; not persisted |
| `AssistantClient` (2.7) | SYSTEM_OWNED | HTTP transport; no data |
| `OfflineAssistant` (2.8) | SYSTEM_OWNED | Rules engine (logic dup of backend); reads mocks + learning context; outputs AI_GENERATED-shaped replies |
| `_LookCard` (2.9) | KNOWLEDGE | Private hardcoded 5-look mirror of backend catalog |

### Home

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `GreetingData`, `QuickActionData`, `StyleTrend` (3.1) | SYSTEM_OWNED | Static chrome/config; read-only; not persisted |
| `TodaysLookData`, `DailyOutfitData`, `AlternativeLookData` (3.1/3.2) | KNOWLEDGE | Catalog look content; AI scoring aspects; regenerated mock daily; user can save it (→ `addSavedLook`) |
| `OutfitItemData`, `DailyOutfitComponent` (3.1/3.2) | KNOWLEDGE | Look pieces (component of look content) |
| `StyleScoreData`, `StyleScoreBreakdownItem` (3.1) | DERIVED | Derived from UserModel + activity; mock today; not persisted |
| `StyleStreakData`, `StreakDayData` (3.1) | HISTORICAL | Per-user streak history; mock today; future per-user rows |
| `AIWardrobeInsightData`, `AiInsightData` (3.1/3.2) | AI_GENERATED | Insight copy; mock today; future AI |
| `StyleDnaContext` (3.2) | DERIVED | From FaceProfile; mock today |
| `WardrobeContext` (3.2) | DERIVED | Aggregated wardrobe stats (matchingItems, totalItems) |

### Wardrobe

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `WardrobeItemData`, `WardrobeMockData` (4) | USER_OWNED | UI shape of the user's wardrobe; today seeded from a 24-item mirror; the *persisted* twin is `WardrobeEntry` |
| `WardrobeInsightData` (4) | AI_GENERATED | Insight card (dup of `AIWardrobeInsightData`) |
| `WardrobeCategory` (4) | KNOWLEDGE | Category vocabulary |
| `ColorOption`, `TextureOption`, `AddItemCategoryConfig`, `AddItemConfig` (4) | KNOWLEDGE | Add-item form vocabularies/config; user picks from them |

### Stylist

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `StylistActionData` (5) | SYSTEM_OWNED | Launcher config; static; dups `QuickActionData`; ids match assistant `action` values + backend `NAVIGATION_MAP` |

### Discover

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `MatchScoreDetails`, `RecommendationReason` (6) | AI_GENERATED | Scoring output per look; mock today |
| `EnsembleComponent` (6) | DERIVED | Look piece with `isOwned` derived from wardrobe |
| `WardrobeAlternative`, `WardrobeItem`(discover) (6) | DERIVED | Substitutes matched from wardrobe/catalog |
| `FilterOption`, `OccasionFilters`, `StyleFilters`, `FitFilters`, `DiscoverTab`, `DiscoverTabData` (6) | KNOWLEDGE | Filter vocabularies/config |

### Outfit Scan / Builder / Hairstyle / Grooming

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `OutfitAnalysisData`, `AnalysisSection`, `DetectedClothingItem` (7) | AI_GENERATED | Scan analysis output; mock today; can be saved → `addSavedLook` |
| `OutfitRecommendation`, `OutfitComponent` (8) | AI_GENERATED | Generated outfit + pieces; mock today; save is snackbar-only |
| `HairstyleRecommendation`, `HairstyleAnalysisResult` (9) | AI_GENERATED | Analysis output; mock today; mirrors backend catalog scores |
| `GroomingRecommendation`, `GroomingAnalysisResult` (10) | AI_GENERATED | Analysis output; mock today |
| `BuilderOption` (8), `GroomingOption` (10) | KNOWLEDGE | Option vocabularies user picks from |
| `FaceScanCheck` (9) | SYSTEM_OWNED | Readiness-check config |
| `ProcessingStage`, `GenerationStage`, `HairstyleProcessingStage`, `GroomingProcessingStage` (7–10) | SYSTEM_OWNED | Processing UI choreography (4 identical shapes) |

### Events

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `EventType` (11) | KNOWLEDGE | Type vocabulary; user picks from it; name persisted via `addPreferredOccasion` |
| `UserEvent` (11) | USER_OWNED | User-created; widget-state only today (see full block) |

### Profile

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `ProfileData`, `StylistLevelData`, `GlobalRankData`, `StyleProgressData`, `AchievementData` (12.1) | DERIVED | Aggregated stats/ranks/achievements; mock today; future derived from user activity |
| `StyleDnaData` (12.1) | DERIVED | Style DNA (mock; source should be FaceProfile) |
| `SavedLookPreview`, `SavedLookDetail` (12.1/12.2) | DERIVED | Saved-look summaries (mock; source should be `UserModel.savedLooks`) |
| `ProfileMenuAction`, `SettingsItem`, `SupportTopic`, `SubscriptionPlan`, `PreferenceOption` (12.2) | KNOWLEDGE | Profile/config content; user picks settings (ephemeral) |

### Onboarding

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `StyleVibe`, `vibeGradientColors`, `PaletteSwatch`, `AiCapability`, `allCapabilities` (13) | KNOWLEDGE | Onboarding vocab/config; user picks vibe |
| `AnalysisResult`, `OnboardingResult` (13) | AI_GENERATED | Dead code — never used (see §Ambiguous) |

### Shared

| Entity | Class | Ownership facts |
| --- | --- | --- |
| `UserSession.hasSavedWardrobeItem` (14) | SYSTEM_OWNED | Session-scoped flag (ephemeral, not persisted); written by Wardrobe, read by Home first-visit gate; a user-flag that lives outside `features/learning` |

---

## Cross-cutting ownership rules (the real design constraints)

1. **Single persistence owner:** `features/learning` owns every durable byte
   today (the `UserModel` blob). All other features are either mock-readers or
   `LearningService` writers. Any future DB must preserve this boundary —
   features talk to the repository, never to storage.
2. **User data vs system content:** USER_OWNED entities (`UserModel`,
   `WardrobeEntry`, `FaceProfile`, saved looks, `UserEvent`) are per-user and
   deletable. KNOWLEDGE entities (catalogs, vocabularies, options, plans,
   tips) are system-wide, shared, and deleted only by content management —
   this split is the foundation for "no hardcoded backend-controlled
   categories": knowledge must come from the backend, not from feature-local
   consts.
3. **AI output is never a source of truth:** every AI_GENERATED entity
   (`AnalysisResult`, recommendations, insights, match scores) is derived from
   user + knowledge data and is reproducible/regenerable. Persist the *inputs*
   (user data, captured images) and the *outcome* (saved look references,
   signals) — the ephemeral intermediate analysis is cache-only.
4. **History vs snapshot:** only `LearningSignal` is truly HISTORICAL. Streaks,
   scores, achievements, and events each *should* be historical per-user rows
   but are currently mocks or lost state.
5. **Derived data is recomputable:** `styleScore`, `StyleDnaData`,
   `WardrobeContext`, `GlobalRankData`, match scores, and saved-look previews are
   DERIVED — they must not be duplicated in the DB; they are computed from
   durable inputs (this resolves several duplicate-family problems in
   `DATA_MODEL_INVENTORY.md` §19.1).
6. **Deletion matrix:** USER_OWNED → deletable (user-driven, no UI today).
   HISTORICAL → append-only, soft-delete/retention. KNOWLEDGE → content
   management. SYSTEM_OWNED → config migration. DERIVED/AI_GENERATED → never
   persisted, so nothing to delete.

---

## Missing concepts (ownership pending the DB design)

Each is implied by the UI/UX but unmodeled; when added, ownership/classification
resolves as noted (`DATA_MODEL_INVENTORY.md` §19.6):

| Missing concept | Classification (when added) | Notes |
| --- | --- | --- |
| `User`/account/auth | USER_OWNED | `AccountCreationScreen` collects email/password/name; "sign in" is mock |
| Style-score & streak history | HISTORICAL | per-user score/streak rows (today in-memory/mock) |
| Event persistence | USER_OWNED | events are widget state (lost) |
| Achievements / ranks / XP | DERIVED (+ catalog KNOWLEDGE for definitions) | mock only |
| Wardrobe item images / media | USER_OWNED (object storage) | `imageUrl` strings only; no media entity |
| Recommendation history | HISTORICAL | only `look_saved` signals trace it today |
| Subscription / plans | USER_OWNED (state) + KNOWLEDGE (plan catalog) | mock only |
| Saved-look full payload | USER_OWNED | persisted only as titles today |
| Current/last "today's look" | USER_OWNED/DERIVED | not persisted; regenerated from mock |

---

## Ambiguous ownership (decisions the next phase must make)

From `DATA_MODEL_INVENTORY.md` §19.7 — each is today's gap, not a resolution:

- **`UserSession.hasSavedWardrobeItem`** — a user flag living in `shared`
  instead of the user model; SYSTEM_OWNED now, should become USER_OWNED when
  persistence exists.
- **`UserEvent`** — no single owner: created in `events`, only the occasion
  vocabulary reaches learning. Decide whether `features/events` owns persisted
  event rows.
- **Saved looks** — 3 shapes across `profile`/`home`/`learning`; the persisted
  truth is `learning`, screens read mocks. Owner = `features/learning`; display
  shapes are DERIVED.
- **Style/occasion vocabularies** — 4 independent vocabularies (events, builder,
  assistant, discover, profile). All KNOWLEDGE; need one backend-owned source.
- **Offline rules engine** (`OfflineAssistant`) vs backend engine — SYSTEM_OWNED
  logic duplicated in two codebases; needs a shared contract or generated source.
- **`AssistantUserContext`** — DERIVED domain data re-shaped as a DTO inside the
  assistant feature; should be built from the learning contract.
- **`AnalysisResult`/`OnboardingResult`** — dead AI_GENERATED models; decide
  remove vs promote to the real analysis entity.
