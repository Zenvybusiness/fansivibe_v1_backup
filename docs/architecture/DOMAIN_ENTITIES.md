# Fansivibe — Domain Entities

> **STEP 3 (continuation) — DOMAIN MODEL DESIGN.** Identifies the **actual
> domain entities** of the real Fansivibe product from the STEP 2 inventory,
> and separates them from everything that merely *looks* like a model: UI
> models, DTOs, value objects, temporary objects, API responses, derived
> values, and system knowledge lookups.
>
> Companion to `DOMAIN_MODEL_RULES.md` (the taxonomy + relationship rules).
> This document applies that taxonomy to every candidate and produces the
> authoritative entity list for the Step 4 PostgreSQL design.
>
> **Source of truth:** the real repository (`newproject/flutter_application_1` +
> `backend/`) and the 12 STEP 2 inventory documents in this directory.
>
> **Status:** documentation only. No SQL, no migrations, no tables, no
> repositories, no services, no Flutter/UI/routing changes, no dependencies, no
> code deleted.
>
> **Method:** every candidate below was collected from
> `DATA_MODEL_INVENTORY.md` (§19.3 domain-like models, §19.6 missing concepts,
> §19.2 UI-only models, §19.4 API DTOs) and verified against source. A
> candidate is a **true domain entity** only if it passes all four tests:
>
> 1. **Identity** — the product refers to it by a stable id over time.
> 2. **Lifecycle** — it is created, mutated/deprecated, and (for user data)
>    deleted.
> 3. **Durability** — it holds state the product must remember beyond the
>    current screen/request.
> 4. **Product behavior** — it is a fact the product cares about, not a shape
>    that only exists to render a screen or cross a boundary.

---

## 1. Candidate pool and verdicts

Every candidate from STEP 2, with the classification used to decide whether it
is a domain entity. **ENTITY** = true domain entity (detailed in §2).
Everything else is one of the non-entity kinds (detailed in §3).

| # | Candidate (STEP 2 ref) | Verdict | Classification |
| --- | --- | --- | --- |
| 1 | `User` (missing concept §19.6) | **ENTITY** | Domain entity — user-owned, aggregate root |
| 2 | `UserModel` aggregate (§1.1) | Not entity | Current profile state *projection* — split into entities |
| 3 | `WardrobeEntry` + `WardrobeItemData` + backend `WardrobeItem` + discover `WardrobeItem` (§1.2, §4, §15, §6) | **ENTITY** | Domain entity `WardrobeItem` (canonical of 4 shapes) |
| 4 | `FaceProfile` (§1.3) | Not entity | Value object (current profile state; AI-generated content) |
| 5 | `LearningSignal` (§1.4) | **ENTITY** | Historical record — user-owned, append-only |
| 6 | `defaultWardrobe` seed (§1.7) | Not entity | System knowledge seed (creates `WardrobeItem` entities) |
| 7 | `SuggestionCard`/`AssistantReply`/`ClarificationOption`/`NavigationRequest` (§2.1–2.4) | Not entity | DTO (AI-output content) |
| 8 | `AssistantUserContext` / backend `UserContext` (§2.6, §15) | Not entity | DTO (derived snapshot of profile state) |
| 9 | `AssistantMessage` / conversation (§2.5) | Not entity | Temporary processing state (history = undecided) |
| 10 | Offline `_LookCard` + catalog cards (§2.9, §16) | Not entity | System knowledge content (mirrors the look catalog) |
| 11 | `GreetingData`, `QuickActionData`, `StyleTrend` (§3.1) | Not entity | UI model / system chrome (cache) |
| 12 | `TodaysLookData`, `DailyOutfitData` (§3) | Not entity (conditional) | AI output / derived daily snapshot; entity only if history is kept (P1 decision) |
| 13 | Outfit-piece family: `OutfitItemData`, `DailyOutfitComponent`, `EnsembleComponent`, `OutfitComponent`, `DetectedClothingItem` (§3, §6, §7, §8) | Not entity | Value objects (one canonical outfit-piece value object) |
| 14 | `StyleScoreData`, `StyleScoreBreakdownItem` (§3.1) | Not entity | Derived value (current `StyleScore`, formula) |
| 15 | `StyleStreakData`, `StreakDayData` (§3.1) | Not entity | UI models of the historical `ActivityDay` record |
| 16 | `AIWardrobeInsightData`, `WardrobeInsightData`, `AiInsightData` (§3, §4) | Not entity | AI output (derived insight) |
| 17 | `StyleDnaContext`, `StyleDnaData` (§3, §12) | Not entity | Derived view over `StyleProfile` |
| 18 | `WardrobeContext` (§3.2) | Not entity | Derived value (aggregated wardrobe stats) |
| 19 | `WardrobeCategory`, `ColorOption`, `TextureOption`, `AddItemCategoryConfig`, `AddItemConfig` (§4) | Not entity | System knowledge vocabulary (lookup values) |
| 20 | `StylistActionData` / quick-action ids (§5) | Not entity | System knowledge (action/navigation config) |
| 21 | `DiscoverLookData` (§6) | **ENTITY** | Domain entity `Look` — system-owned knowledge content |
| 22 | `MatchScoreDetails`, `RecommendationReason` (§6) | Not entity | Value objects (AI output) |
| 23 | `WardrobeAlternative`, discover `WardrobeItem` (§6) | Not entity | Derived value objects (wardrobe × catalog) |
| 24 | `FilterOption`, `OccasionFilters`, `StyleFilters`, `FitFilters`, `DiscoverTab*` (§6) | Not entity | System knowledge vocab + temporary UI state |
| 25 | `OutfitAnalysisData`, `AnalysisSection` (§7) | Not entity | AI output snapshot (embedded in `AnalysisRun`) |
| 26 | `ProcessingStage` ×4 (§7–§10) | Not entity | Temporary processing state |
| 27 | `OutfitRecommendation`, `OutfitComponent` (§8) | Not entity | AI output (value objects) |
| 28 | `BuilderOption` (§8), `GroomingOption` (§10) | Not entity | System knowledge vocabulary |
| 29 | `FaceScanCheck` (§9) | Not entity | System knowledge config |
| 30 | `HairstyleRecommendation`/`HairstyleAnalysisResult` (§9) | Not entity (conditional) | AI output / knowledge content; gains id-reference only when Save Style lands (P1) |
| 31 | `GroomingRecommendation`/`GroomingAnalysisResult` (§10) | Not entity (conditional) | AI output / knowledge content (same as #30) |
| 32 | `EventType` (§11) | Not entity | System knowledge vocabulary |
| 33 | `UserEvent` (§11) | **ENTITY** | Domain entity — user-owned |
| 34 | `ProfileData`, `StylistLevelData`, `GlobalRankData`, `StyleProgressData` (§12) | Not entity | Derived values (UI aggregation) |
| 35 | `AchievementData` (§12) | Not entity | Derived state; definitions = system knowledge |
| 36 | `SavedLookPreview`, `SavedLookDetail` (§12) | Not entity | Derived views of the `SavedLook` entity |
| 37 | `ProfileMenuAction`, `PreferenceOption`, `SettingsItem`, `SupportTopic`, `SubscriptionPlan` (§12.2) | Not entity | System knowledge + user preference values |
| 38 | `StyleVibe`, `vibeGradientColors`, `PaletteSwatch`, `AiCapability`, `allCapabilities` (§13) | Not entity | System knowledge config |
| 39 | `AnalysisResult`, `OnboardingResult` (§13, dead code) | Not entity | Intended shape of the `AnalysisResult` AI output — never used |
| 40 | `UserSession.hasSavedWardrobeItem` (§14) | Not entity | Current profile state flag (belongs to the user model) |
| 41 | Backend catalog constants: looks/hairstyles/grooming/tips/insights (§16) | Not entity | System knowledge content (seeds the `Look` catalog) |
| 42 | Score/streak history (missing §19.6) | **ENTITY** | `StyleScoreRecord` + `ActivityDay` — historical, derived |
| 43 | Event rows (missing §19.6) | = #33 | Covered by `UserEvent` |
| 44 | Achievements / ranks / XP (missing §19.6) | Not entity | Derived aggregates; definitions = knowledge |
| 45 | Media / images (missing §19.6) | Not entity | `MediaRef` value object → external blob; media-asset entity deferred (MS10.2) |
| 46 | Recommendation history (missing §19.6) | **ENTITY** (conditional, P3) | Historical record of shown/saved recommendations |
| 47 | Subscription (missing §19.6) | **ENTITY** (P2) | Domain entity — user-owned state + external entitlement |
| 48 | Saved-look full payload (missing §19.6) | = #36/#21 | Snapshot value objects inside `SavedLook` |
| 49 | Today's-look snapshot (missing §19.6) | Not entity (conditional) | Derived daily snapshot; history only if product decides (P1) |
| 50 | Weather literal (§3.1) | Not entity | External data (cache) |

**Result: 10 true domain entities** (detailed below), of which 2 are
conditional on product decisions that STEP 2 flags as pending.

---

## 2. True domain entities

For each entity: name, purpose, owner, lifecycle, and the seven binary
determinations the task asks for, plus related features. "Owner" = the feature
that creates/manages it; the single-persistence-owner rule
(`ARCHITECTURE_GAP_REPORT.md` F1.1) means user-owned state is persisted through
`features/learning` today.

### E1. `User`

- **Purpose:** the account identity that scopes every user-owned entity; the
  root of the aggregate. Without it no relational write can be user-scoped
  (`ARCHITECTURE_GAP_REPORT.md` AU11.1, AZ12.3).
- **Owner:** `auth` feature (future; created through the onboarding
  `AccountCreationScreen` UI today — mock).
- **Lifecycle:** register (email/password/social) → authenticate → update →
  delete (cascades user-owned data per `STORAGE_INVENTORY.md` retention).
- **User-owned:** yes (it is the user).
- **System-owned:** no (the *platform* owns its auth system, not the entity).
- **AI-generated:** no.
- **Historical:** no (current identity state).
- **Own identity:** yes — stable account id (future, from `POST /auth/register`).
- **Exists independently:** yes — the aggregate root; everything else hangs off it.
- **Related features:** onboarding (create), auth (future), home (greeting name),
  profile (dashboard), all user-scoped writes.
- **Evidence:** `DATA_MODEL_INVENTORY.md` §19.6; `DATA_OWNERSHIP.md` missing
  concepts; `ACTION_API_INVENTORY.md` #1–4, #32.

### E2. `WardrobeItem`

- **Purpose:** one owned piece of clothing/accessory — the canonical resolution
  of the 4 wardrobe-item shapes (`WardrobeEntry`, `WardrobeItemData`, backend
  `WardrobeItem`, discover alternative).
- **Owner:** `wardrobe` feature (domain); persisted via `features/learning`
  (sole persistence owner today).
- **Lifecycle:** created by the Add Item flow (`wardrobe_screen.dart:301` →
  `addItem`); mutated (favorite toggle today; edit/delete are stubs —
  `UI_UX_GAP_REPORT.md` #4); deleted by the user (no UI yet).
- **User-owned:** yes.
- **System-owned:** no.
- **AI-generated:** no (future image tags could be AI content).
- **Historical:** no (mutable current state; only `item_added` signals are history).
- **Own identity:** yes — item id (already carried by `WardrobeEntry`).
- **Exists independently:** yes — stored as its own user-scoped rows.
- **Related features:** wardrobe, learning, assistant (context), home (today's
  look), discover (matching), outfit_builder, outfit_scan.
- **Evidence:** `DATA_OWNERSHIP.md` §`WardrobeEntry`; `FEATURE_DATA_MATRIX.md` §3.

### E3. `UserEvent`

- **Purpose:** a user-created, dated event that provides occasion context for
  outfit recommendations. Today it is widget state only and is lost on restart
  (`DATA_MODEL_INVENTORY.md` §11).
- **Owner:** `events` feature (domain); only the occasion reaches learning today
  (`addPreferredOccasion`).
- **Lifecycle:** created by the Add Event form; edited/deleted (stubs —
  `UI_UX_GAP_REPORT.md` #5); may trigger outfit generation per event.
- **User-owned:** yes.
- **System-owned:** no.
- **AI-generated:** no.
- **Historical:** partly — dated, but editable; primary nature is a current
  user entity with historical aspects (`DATA_OWNERSHIP.md` §`UserEvent`).
- **Own identity:** yes — event id (already carried by `UserEvent` mock).
- **Exists independently:** yes — stored as user-scoped dated rows.
- **Related features:** events, learning (occasion preference), outfit_builder
  (event-seeded generation), assistant (event context).
- **Evidence:** `DATA_OWNERSHIP.md` §`UserEvent`; `STORAGE_INVENTORY.md` Part 2
  (events); `ACTION_API_INVENTORY.md` #9–11.

### E4. `SavedLook`

- **Purpose:** the user's durable record of choosing to keep a look, with a
  snapshot of what was saved. Today only a title string persists
  (`UserModel.savedLooks: List<String>`) and the Saved Looks screen reads a mock
  instead of the persisted list (`UI_UX_GAP_REPORT.md` #7).
- **Owner:** `features/learning` (persisted truth); displayed as derived views
  by `profile` and referenced by the save paths in `home`/`discover`/
  `outfit_scan`/future `outfit_builder`/`hairstyle`/`grooming`.
- **Lifecycle:** created from any save path (Daily Outfit :1172, Look Details
  :327, Outfit Analysis :260, future Save Outfit/Save Style); removed by the
  user (no UI today).
- **User-owned:** yes.
- **System-owned:** no.
- **AI-generated:** no (user chooses; the referenced `Look` is knowledge/AI content).
- **Historical:** partly — additive with a saved-at timestamp conceptually
  (`DATA_OWNERSHIP.md` §"Saved looks").
- **Own identity:** yes — saved-look id (future, from `POST /looks/saved`).
- **Exists independently:** yes — user-scoped rows + snapshot payload.
- **Related features:** home, discover, outfit_scan, outfit_builder, hairstyle,
  grooming, profile (Saved Looks), learning, assistant (context).
- **Evidence:** `DATA_OWNERSHIP.md` §"Saved looks"; `STORAGE_INVENTORY.md` §1.7.

### E5. `Look`

- **Purpose:** one entry in the shared look catalog (the canonical "look":
  discover feed looks, today's-look content, outfit suggestions, backend catalog
  looks, offline cards). This is the knowledge the product recommends from; it is
  the only knowledge content that gains true entity semantics because `SavedLook`
  and future recommendation records reference it **by id**
  (`ACTION_API_INVENTORY.md` #14: "with the catalog look id, not just a title").
- **Owner:** backend knowledge source / content management (system). Today it is
  mirrored 4 ways (`DiscoverLookData`, `OutfitRecommendation.mock`,
  `DailyOutfitData.mock`, catalog constants) — the domain model requires one
  canonical source (`ARCHITECTURE_GAP_REPORT.md` K9.1, K9.2).
- **Lifecycle:** authored, versioned, deprecated by content management; never
  tied to a user (`STORAGE_INVENTORY.md` §1.8 retention).
- **User-owned:** no.
- **System-owned:** yes.
- **AI-generated:** the *content* is authored; the *match scoring* on top of it
  is AI output (separate value objects).
- **Historical:** no (versioned content, not append-only history).
- **Own identity:** yes — look id (already carried by `DiscoverLookData`).
- **Exists independently:** yes — system-wide shared catalog, independent of users.
- **Related features:** discover, home, assistant, outfit_builder, saved looks,
  backend knowledge.
- **Evidence:** `DATA_OWNERSHIP.md` §"DiscoverLookData and the look family";
  `DATA_MODEL_INVENTORY.md` §19.3.

### E6. `AnalysisRun`

- **Purpose:** the record of one scan/analysis execution (outfit scan,
  hairstyle, grooming, future onboarding face analysis) linking the user, the
  source media, and the result snapshot. STEP 2 requires results to be "linked
  to the source image + scan run" (`STORAGE_INVENTORY.md` §1.6).
- **Owner:** the analysis features (`outfit_scan`, `hairstyle`, `grooming`);
  result state persisted through `features/learning`; media via `MediaRef`.
- **Lifecycle:** created per analysis execution; result retained only while
  useful or if the user saves the look (`STORAGE_INVENTORY.md` §1.6 retention).
- **User-owned:** yes (the run belongs to a user).
- **System-owned:** no.
- **AI-generated:** the run *record* is not; the `AnalysisResult` snapshot it
  holds is AI output.
- **Historical:** yes — append-only linkage record.
- **Own identity:** yes — run id.
- **Exists independently:** yes — user-scoped rows referencing media + result.
- **Related features:** outfit_scan, hairstyle, grooming, saved looks (link),
  onboarding (future), learning.
- **Evidence:** `STORAGE_INVENTORY.md` §1.6, §1.2; `ACTION_API_INVENTORY.md` #16/17/21/23.

### E7. `LearningSignal`

- **Purpose:** a typed, append-only trace of user interaction that drives
  gradual learning (8 types: `item_added`, `analysis_updated`, `style_updated`,
  `look_saved`, `occasion_preferred`, `assistant_message`,
  `suggestion_opened`, `assistant_navigation`).
- **Owner:** `features/learning` (written by `LearningService` + the assistant).
- **Lifecycle:** appended on every relevant action; never edited or deleted
  (soft-delete/retention only — `DATA_OWNERSHIP.md` deletion matrix).
- **User-owned:** yes.
- **System-owned:** no.
- **AI-generated:** no.
- **Historical:** yes — the only true append-only history today.
- **Own identity:** yes — as a stored record it gets a row id (today it is
  `{type, label, timestamp}` without one).
- **Exists independently:** yes — append-only rows per user.
- **Related features:** all (each feature records signals via `LearningService`).
- **Evidence:** `DATA_OWNERSHIP.md` §`LearningSignal`; `DATA_MODEL_INVENTORY.md` §1.4.

### E8. `StyleScoreRecord`

- **Purpose:** a dated snapshot of the computed style score, enabling the Home
  score card trend and Profile history. Today the score is computed in-memory
  (`60 + wardrobe.clamp(0,20) + savedLooks*2.clamp(0,20)`) and the history is a
  mock (`StyleScoreData`) — the concept is a missing historical entity
  (`DATA_MODEL_INVENTORY.md` §19.6).
- **Owner:** `features/learning` (derived from signals/saves/wardrobe).
- **Lifecycle:** created periodically / on score change; append-only.
- **User-owned:** yes.
- **System-owned:** no.
- **AI-generated:** no (deterministic formula, not AI).
- **Historical:** yes.
- **Own identity:** yes — record id (user + timestamp).
- **Exists independently:** yes — rows derived from durable inputs.
- **Related features:** home (score card), profile (dashboard), learning.
- **Evidence:** `STORAGE_INVENTORY.md` "score history"; `MVP_SCOPE.md` P1
  (score/streak history).

### E9. `ActivityDay`

- **Purpose:** one record per styled day backing the streak timeline
  (`StyleStreakData`/`StreakDayData` are its UI mocks today).
- **Owner:** `features/learning` (derived from signals/saved looks).
- **Lifecycle:** created when a styled day is recorded; append-only.
- **User-owned:** yes.
- **System-owned:** no.
- **AI-generated:** no.
- **Historical:** yes.
- **Own identity:** yes — record id (user + day).
- **Exists independently:** yes — rows derived from activity.
- **Related features:** home (streak card), profile, learning.
- **Evidence:** `STORAGE_INVENTORY.md` "streak/activity rows"; `DATA_MODEL_INVENTORY.md` §19.6.

### E10. `Subscription` (P2)

- **Purpose:** the user's paid entitlement state (plan, active period). Today
  plans are mock (`SubscriptionPlan`) and purchase is a stub
  (`ACTION_API_INVENTORY.md` #30).
- **Owner:** `profile`/`subscription` feature; external entitlement/payment
  service (`STORAGE_INVENTORY.md` cat 5).
- **Lifecycle:** activate → renew → cancel/expire (via external service).
- **User-owned:** yes (state).
- **System-owned:** the *plan catalog* is system knowledge; the entitlement
  state is user-owned.
- **AI-generated:** no.
- **Historical:** no (current state; billing history is external).
- **Own identity:** yes — subscription id.
- **Exists independently:** yes — user-scoped state referencing a plan id.
- **Related features:** profile, subscription/upgrade screens, external purchase.
- **Evidence:** `DATA_MODEL_INVENTORY.md` §19.6; `ACTION_API_INVENTORY.md` #30;
  `MVP_SCOPE.md` P2.

### Conditional entities (defined, but existence depends on a pending product decision)

- **`Today'sLookRecord` (P1 decision)** — a per-user dated snapshot of the
  daily look. Today `DailyOutfitData`/`TodaysLookData` are regenerated mocks and
  nothing is persisted. If the product wants look history / "what I wore"
  (referenced by `STORAGE_INVENTORY.md` "daily_look row per user/day"), it
  becomes a historical entity; otherwise it stays a derived snapshot in cache.
  **User-owned / historical / own identity / independent: yes**; **AI-generated:
  content is knowledge + scoring is AI output**; **owner:** home + learning.
  Related features: home, saved looks, profile.
- **`RecommendationHistory` (P3 decision)** — the trace of recommendations
  shown/saved for personalization analytics
  (`DATA_MODEL_INVENTORY.md` §19.6; `MVP_SCOPE.md` P3). Today only the
  `look_saved` signal traces it. If built, it is a user-owned historical
  entity referencing `Look` + scores. Related features: discover, home,
  assistant, outfit_builder.

---

## 3. What is NOT a domain entity (and why)

Grouped by the classification that replaces "entity" for each candidate.

### 3.1 Value objects (no identity, embedded in an entity)

- `FaceProfile` fields (`faceShape`, `skinTone`, `bodyType`, `styleType`) —
  current profile state content inside `StyleProfile`/`User`.
- The **outfit-piece family** (`OutfitItemData`, `DailyOutfitComponent`,
  `EnsembleComponent`, `OutfitComponent`, `DetectedClothingItem`) — one
  canonical outfit-piece value object embedded in `Look`, `SavedLook`
  snapshot, or a recommendation.
- `MatchScoreDetails`, `RecommendationReason` — AI-output scoring value objects.
- `MediaRef` — reference to an object-storage blob (face/outfit/item image);
  the blob itself is external data.
- `WardrobeAlternative` — derived value object (wardrobe × catalog).

### 3.2 Current profile state (projection, not separate entities)

- `UserModel` aggregate — the device-local JSON blob; a *projection* that mixes
  entities + value objects. It is split into the entities above, not itself an
  entity (`STORAGE_INVENTORY.md` Part 4 #1).
- `StyleProfile` (face attributes + `styleType`) — part of the `User` aggregate,
  embedded.
- `Wardrobe` collection — the aggregate's collection of `WardrobeItem`s.
- `PreferredOccasions` — user preference list of vocabulary ids.
- `UserSession.hasSavedWardrobeItem` — a user-state flag (derived from a
  non-empty wardrobe) that must live in the user model, not as an entity
  (`ARCHITECTURE_GAP_REPORT.md` F1.4).
- Current `StyleScore` — computed value, cache-only.

### 3.3 DTOs (boundary shapes, never the source of truth)

- Assistant contract: `AssistantReply`, `SuggestionCard`,
  `ClarificationOption`, `NavigationRequest`, `AssistantMessage`,
  `AssistantUserContext` (+ backend `schemas.py` mirrors). Wire contract — KEEP
  mirrored (`ARCHITECTURE_GAP_REPORT.md` A3.1).
- Future API request/response shapes (auth, wardrobe, events, looks, analysis,
  sync) — defined at the contract step, carry the entities above.

### 3.4 AI outputs (regenerable; never stored as truth)

- `OutfitRecommendation` + `OutfitComponent`, `HairstyleRecommendation`/
  `HairstyleAnalysisResult`, `GroomingRecommendation`/`GroomingAnalysisResult`,
  `OutfitAnalysisData`/`AnalysisSection`, `TodaysLookData`/`DailyOutfitData`
  (the personalized view), insights (`AIWardrobeInsightData`/`WardrobeInsightData`/
  `AiInsightData`), `StyleDnaData`/`StyleDnaContext` (derived view over
  `StyleProfile`), discover match scores/reasons. Persist only as user-saved
  snapshots (`SavedLook`/`AnalysisRun`) or discard (`DATA_OWNERSHIP.md` rule 3).

### 3.5 System knowledge (reference data, not entities)

- Vocabularies: occasion, style, wardrobe category, color, material/texture,
  event type, builder/grooming options, filters. Referenced by id; content-managed.
- Catalog cards: hairstyle/grooming/tip/insight cards — content served in DTOs;
  they gain id-reference semantics only when Save Style lands (#30/#31).
- Config: `allCapabilities`/`AiCapability`, action/navigation maps,
  `FaceScanCheck`, subscription plans, support topics, achievement definitions,
  `StyleVibe` + palette swatches, `defaultWardrobe` seed.

### 3.6 Temporary processing state

- `ProcessingStage` ×4, in-flight conversation (`AssistantMessage` list), scan
  buffers / transient image paths, generation previews, route extras, active
  filters, scroll state.

### 3.7 UI models (render-only; cache)

- `GreetingData`, `QuickActionData`, `StyleTrend`, `StyleStreakData`/
  `StreakDayData` (UI render of `ActivityDay`), `StyleScoreData`/
  `StyleScoreBreakdownItem` (UI render of `StyleScoreRecord`), `ProfileData`/
  `StylistLevelData`/`GlobalRankData`/`StyleProgressData`/`AchievementData`
  (derived UI aggregation), `SavedLookPreview`/`SavedLookDetail` (derived views
  of `SavedLook`), `WardrobeCategory`/`FilterOption`/`DiscoverTab*` (UI chips),
  `PaletteSwatch`, `ProfileMenuAction`.

### 3.8 External data

- Weather (cache-only, never durable), auth-provider identity, entitlement
  result, optional LLM enrichment, media bytes (via `MediaRef`).

### 3.9 Dead / never-used models

- `AnalysisResult`, `OnboardingResult` (`onboarding_data.dart`) — the intended
  onboarding-analysis AI-output shape, never instantiated
  (`DATA_MODEL_INVENTORY.md` §13). Delete or promote to the `AnalysisResult`
  AI-output definition (an `ARCHITECTURE_GAP_REPORT.md` M2.3 decision).

---

## 4. Entity × feature matrix

| Entity | Onboarding | Home | Discover | Wardrobe | Outfit Scan | Outfit Builder | Hairstyle | Grooming | Events | Profile | Assistant | Learning | Backend |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `User` | create | read (name) | — | scope | scope | scope | scope | scope | scope | read | scope | read | identity |
| `WardrobeItem` | — | read | read | **own/write** | read | read | — | — | — | read | read | persist | context |
| `UserEvent` | — | read (context) | — | — | — | generate | — | — | **own/write** | — | read | occasion | — |
| `SavedLook` | — | write | write | — | write | write (future) | write (future) | write (future) | — | **read** | read | persist | write |
| `Look` | — | serve | **serve** | — | serve | serve | — | — | serve | — | serve | — | **author** |
| `AnalysisRun` | future | — | — | — | **create** | — | **create** | **create** | — | — | — | persist | process |
| `LearningSignal` | write | write | write | write | write | — | — | — | write | — | write | **persist** | — |
| `StyleScoreRecord` | — | read | — | — | — | — | — | — | — | read | — | **derive** | — |
| `ActivityDay` | — | read | — | — | — | — | — | — | — | read | — | **derive** | — |
| `Subscription` | — | — | — | — | — | — | — | — | — | **own/read** | — | — | purchase |

Legend: `**own/write**` = primary owner/creator; `write` = creates/records;
`read` = consumes; `serve`/`author` = system content; `persist`/`derive` =
cross-cutting learning layer.

---

## 5. Report — what was found & what must be modeled next

### What was found

- **10 true domain entities** after separating non-entities: `User`,
  `WardrobeItem`, `UserEvent`, `SavedLook`, `Look`, `AnalysisRun`,
  `LearningSignal`, `StyleScoreRecord`, `ActivityDay`, `Subscription`.
- **2 conditional entities** gated on pending product decisions: `Today'sLookRecord`
  (P1), `RecommendationHistory` (P3).
- **No Dart class was promoted to entity without passing the four tests**
  (identity + lifecycle + durability + product behavior). The look "family"
  collapsed to two entities (`Look` + `SavedLook`); the outfit-piece family to a
  value object; the 4 wardrobe shapes to one entity; analysis results to a
  snapshot inside `AnalysisRun`.
- **Deliberately excluded:** all assistant DTOs (wire contract, KEEP), UI/mock
  models, processing stages, filters, vocabularies (system knowledge), weather,
  media bytes, achievements/XP (derived), and the dead onboarding models.
- **Ownership pattern confirmed:** user-owned entities all hang off `User`;
  `Look` is the only system-owned entity; everything else is derived, knowledge,
  DTO, temporary, or external.

### What must be modeled next (dependency order, none implemented)

1. **Typed API + error contract** (A3.2/A3.3) carrying these entities, starting
   with the P0 endpoints in `MVP_SCOPE.md` Part 1 (auth, wardrobe CRUD, saved
   looks, assistant, `POST /users/me/sync`).
2. **Auth + anonymous→sync design** (AU11.1/AU11.2) — defines `User`'s fields and
   the device↔account merge for the `UserModel` projection.
3. **Per-feature repository interfaces** (R4.2) over `WardrobeItem`,
   `SavedLook`, `Look`, `AnalysisRun`, `LearningSignal`.
4. **Storage split (Step 4)** — relational rows for the 10 entities, JSONB for
   current-profile/snapshot payloads, knowledge content for `Look` and
   vocabularies, object storage for `MediaRef` blobs.
5. **Media privacy policy** (MS10.3) before any media persistence.
6. **P1/P3 decisions:** persist `Today'sLookRecord` and `RecommendationHistory`?
   Persist conversations? — each is explicitly flagged as an open product
   choice in the inventories.

---

## Constraints honored

- No SQL, no migrations, no tables, no repositories, no services.
- No Flutter/UI/routing changes, no dependencies, no code deleted.
- Every verdict traces to a STEP 2 inventory reference and to real source.
- The real Fansivibe repository is the source of truth; the separate reference
  project was not used.
