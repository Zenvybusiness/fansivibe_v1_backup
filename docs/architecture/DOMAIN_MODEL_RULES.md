# Fansivibe — Domain Model Rules

> **STEP 3 — DOMAIN MODEL DESIGN.** This document defines Fansivibe's business
> / domain entities and their relationships *before* any PostgreSQL design.
> It is the agreed "what is real product data vs. what is derived / display /
> transport" map that constrains the Step 4 database and the service layer.
>
> **Source of truth:** the REAL Fansivibe repository (Flutter app at
> `newproject/flutter_application_1`, backend at `backend/`) and the completed
> STEP 2 inventory documents in this directory. The separate reference project
> is NOT merged and is not used here.
>
> **Status:** documentation only. No SQL, no migrations, no tables, no
> repositories, no FastAPI services, no Flutter architecture changes, no UI or
> routing changes, no dependencies, no code deleted. Nothing here is
> implemented.
>
> **Scope discipline:** every entity below traces to product behavior and to a
> STEP 2 inventory reference. No entity is invented beyond what STEP 2 supports.
> Missing-concepts entities (STEP 2 `DATA_MODEL_INVENTORY.md` §19.6) are defined
> *as domain concepts* — they are the reason STEP 3 exists — but their storage
> shape is deliberately out of scope here.

---

## 1. Category system

The domain model distinguishes **ten** kinds of data. Every concept in the
product must be classified into exactly one primary category; secondary aspects
are noted per entity.

| # | Category | Definition | Decision test |
| --- | --- | --- | --- |
| 1 | **Domain entity** | Has its own identity (stable id), a lifecycle (create → mutate → delete), and is the durable subject of business rules. | "Does the product refer to this thing over time by id?" |
| 2 | **Value object** | Immutable, no identity, defined entirely by its attributes; interchangeable when attributes match; embedded inside entities. | "Can I replace it with an identical one with no effect?" |
| 3 | **DTO** | A boundary shape that crosses the app↔backend wire (request/response contract). Never persisted as the source of truth. | "Does it exist only to carry data across a boundary?" |
| 4 | **AI output** | A computed/generated result (recommendation, analysis, insight, match score). Reproducible from inputs; **never a source of truth**. | "Can this be regenerated from durable inputs?" |
| 5 | **Historical record** | Append-only evidence of what happened over time (signals, score snapshots, activity days, analysis runs). | "Is it an immutable trace of a past event?" |
| 6 | **Current profile state** | The user's durable evolving state right now (style profile, wardrobe collection, saved-look list, session flags that belong to the user). Mutable snapshot. | "Is it the user's present state that the product must remember?" |
| 7 | **User preference** | An explicit choice the user made (style vibe, builder prefs, grooming inputs, settings toggles). Durable, user-scoped. | "Did the user explicitly choose this value?" |
| 8 | **System knowledge** | Backend-owned reference content shared by all users: catalogs, vocabularies, options, plans, tips, seed data. | "Is it system-authored content that every user reads?" |
| 9 | **External data** | Originates outside the product (device media, weather provider, auth provider identity, payment/entitlement service, optional LLM). | "Does a third party or the device produce it?" |
| 10 | **Temporary processing state** | Mid-pipeline or session-only data with no durable value (processing stages, scan buffers, in-flight conversation, route extras, filters). | "Is it gone the moment the screen/request finishes?" |

### Classification decision procedure

1. Is it produced by the device or a third party? → **External data**.
2. Is it system-authored content shared by all users? → **System knowledge**.
3. Does it only carry data across the app↔backend boundary? → **DTO**.
4. Is it an append-only trace of a past event? → **Historical record**.
5. Can it be recomputed from durable inputs (score, count, match %, derived view)? → **Derived value** — render as **AI output** when an engine/AI produces it, otherwise as a derived view over durable state (never stored as truth).
6. Does it exist only mid-screen/mid-request? → **Temporary processing state**.
7. Is it an explicit user choice? → **User preference**.
8. Is it the user's present durable state? → **Current profile state**.
9. Does it have identity + lifecycle? → **Domain entity**.
10. Otherwise → **Value object**.

The single most important rule from STEP 2 (`DATA_OWNERSHIP.md` rule 3): **AI
output is never a source of truth.** Durable inputs (user data, captured media)
and durable outcomes (saved-look references, signals, snapshots the user keeps)
are what the domain model persists; ephemeral analysis is discarded or kept only
as a user-saved snapshot.

---

## 2. Canonical domain model

### 2.1 Aggregate root — `User`

- **Category:** Domain entity (aggregate root).
- **Definition:** The account identity that owns and scopes all user data. It is
  the reason every future relational write has a user scope
  (`ACTION_API_INVENTORY.md` Part 4 #1; `ARCHITECTURE_GAP_REPORT.md` AU11.1,
  AZ12.3). Account creation today is a mock (`account_creation_screen.dart:74`);
  the domain model treats it as the root regardless.
- **Identity:** stable account id issued on registration/`POST /auth/register`.
- **Attributes (facts, not columns):** authentication identity (email/password
  hash or social provider subject), display name, anonymous-vs-account state
  (for the "Maybe Later — Save Locally" → sync path, `ACTION_API_INVENTORY.md`
  #4/#32), membership/subscription state reference.
- **Lifecycle:** create (register/social), authenticate, update, delete (cascades
  user-owned data per `STORAGE_INVENTORY.md` retention principle).
- **Relationships:** 1–N to every user-owned entity below. It aggregates the
  **current profile state** (2.3) and the **user preferences** (2.4).
- **Evidence:** missing concept (`DATA_MODEL_INVENTORY.md` §19.6), ownership
  pending DB design (`DATA_OWNERSHIP.md` missing-concepts table), auth = P0
  prerequisite (`MVP_SCOPE.md` Part 1, `ARCHITECTURE_GAP_REPORT.md` AU11.1).
- **Future note:** this entity must exist before any user-scoped table; its
  exact fields belong to the auth + anonymous→sync design, which Step 2 flags as
  interdependent with `User` (`STEP_2_FINAL_REPORT.md` §14 #5).

### 2.2 User-owned domain entities

#### `WardrobeItem`

- **Category:** Domain entity.
- **Definition:** A single piece of clothing/accessory the user owns. It is the
  canonical resolution of the 4 wardrobe-item shapes
  (`WardrobeEntry`, `WardrobeItemData`, backend `WardrobeItem`, discover
  `WardrobeItem` alternative — `DATA_MODEL_INVENTORY.md` §19.1).
- **Identity:** stable item id (the `id` already carried by `WardrobeEntry`).
- **Attributes:** name; category (reference to a **wardrobe-category vocabulary**
  id, §2.7); color (reference to a **color vocabulary** id); material/texture
  (optional, vocabulary id); favorite flag; optional **media reference** to a
  user-captured image (object storage, `STORAGE_INVENTORY.md` §1.4).
- **Lifecycle:** created by the Add Item flow (`wardrobe_screen.dart:301` →
  `LearningService.addItem`), mutated (favorite toggle today; edit/delete are
  stubs — `UI_UX_GAP_REPORT.md` #4), deleted (user-owned, deletable per
  `DATA_OWNERSHIP.md` deletion matrix).
- **Relationships:** 1–N per `User`; referenced (read) by the assistant context,
  discover matching, today's look, outfit generation.
- **Evidence:** `DATA_OWNERSHIP.md` §`WardrobeEntry`; `FEATURE_DATA_MATRIX.md` §3.

#### `UserEvent`

- **Category:** Domain entity.
- **Definition:** A user-created, dated calendar event that provides occasion
  context for outfit recommendations. Today it exists only as widget state and
  is lost on restart (`DATA_MODEL_INVENTORY.md` §11); only the occasion reaches
  `preferredOccasions` via `addPreferredOccasion` (`add_event_screen.dart:116`).
- **Identity:** stable event id (the `id` carried by `UserEvent` mock).
- **Attributes:** name; date; time; **event type** (reference to the event-type
  vocabulary id, §2.7); whether an outfit recommendation has been generated
  (`hasOutfitRecommendation`); optional link to a generated recommendation.
- **Lifecycle:** create (Add Event form), edit/delete (stubs today —
  `UI_UX_GAP_REPORT.md` #5), "Generate Outfit" (navigates to the builder with no
  event data today — `event_details_screen.dart:317`; the future flow must seed
  the occasion).
- **Relationships:** 1–N per `User`; references event-type vocabulary;
  optionally links to an **outfit recommendation**.
- **Evidence:** `DATA_OWNERSHIP.md` §`UserEvent`; `STORAGE_INVENTORY.md` Part 2
  (events row); `FEATURE_DATA_MATRIX.md` §11.

#### `SavedLook`

- **Category:** Domain entity.
- **Definition:** A user's durable record of choosing to keep a look, with a
  snapshot of what was saved. Today only a title string is persisted
  (`UserModel.savedLooks: List<String>`), the detail payload exists only in
  mocks (`SavedLookPreview`/`SavedLookDetail`), and the Saved Looks screen reads
  a mock instead of the persisted list (`UI_UX_GAP_REPORT.md` #7).
- **Identity:** stable saved-look id (future; returned by the future
  `POST /looks/saved` per `ACTION_API_INVENTORY.md` #12/14/17/22/24).
- **Attributes:** reference to the source **look** (knowledge id) or to the
  analysis/outfit it came from; saved-at timestamp; **snapshot payload** (the
  ensemble components, score, and reasons at save time — `STORAGE_INVENTORY.md`
  §1.7, `DATA_MODEL_INVENTORY.md` §19.6 saved-look full payload); optional
  media reference to the source image.
- **Lifecycle:** created from any of the 4 save paths (Home `daily_outfit_screen.dart:1172`,
  Discover `look_details_screen.dart:327`, Outfit Scan `outfit_analysis_screen.dart:260`,
  and future Builder/Hairstyle/Grooming saves); removed by the user (no UI today).
- **Relationships:** 1–N per `User`; references **Look** knowledge content;
  embeds the snapshot value objects; optional **AnalysisRun** link.
- **Evidence:** `DATA_OWNERSHIP.md` §"Saved looks"; `STORAGE_INVENTORY.md` Part 2
  (saved_look + payload).

#### `AnalysisRun` (introduced from STEP 2 storage requirements)

- **Category:** Historical record (linkage) + AI output (result).
- **Definition:** The record of one scan/analysis execution (outfit scan,
  hairstyle, grooming, future onboarding face analysis) that links the user, the
  source media, and the result snapshot. Step 2 requires analysis results to be
  "linked to the source image + scan run"
  (`STORAGE_INVENTORY.md` §1.6, `AI_DATA_FLOW.md` Part C).
- **Identity:** stable run id.
- **Attributes:** user; **feature/analysis type** (vocabulary: outfit/hairstyle/
  grooming); source **media reference**; timestamp; **result snapshot** (AI
  output, §2.6); optional **SavedLook** link; optional derived `FaceProfile`
  attributes write.
- **Lifecycle:** created per analysis execution; result retained only while
  useful or if the user saves the look (`STORAGE_INVENTORY.md` §1.6 retention).
- **Relationships:** N per `User`; N per `MediaRef`; 1–N `AnalysisResult`
  snapshots; optional link to `SavedLook`.
- **Evidence:** `STORAGE_INVENTORY.md` §1.6 ("latest per source image; older
  runs retained only if the user saves the look"), §1.2; `ACTION_API_INVENTORY.md`
  #16/17/21/23.

### 2.3 Current profile state

The current `UserModel` aggregate (`lib/features/learning/data/models.dart:106`)
is the **single persisted current-state snapshot** today
(`DATA_OWNERSHIP.md` — USER_OWNED aggregate). In the domain model it splits into
distinct current-state concepts; the model *documents the split*, it does not
implement it (`STORAGE_INVENTORY.md` Part 4 #1, `ARCHITECTURE_GAP_REPORT.md` P7.1).

- **`StyleProfile`** (current profile state) — the user's durable style
  attributes: face attributes (`FaceProfile` value object: `faceShape`,
  `skinTone`, `bodyType`, `styleType`), `styleType`, and the derived **Style DNA
  view** (mocks `StyleDnaData`/`StyleDnaContext` are the derived display shape,
  `DATA_MODEL_INVENTORY.md` §19.1). Content is AI-generated (from future face
  analysis) but the state is durable and user-owned
  (`DATA_OWNERSHIP.md` §`FaceProfile`). Note: today `FaceProfile` is never
  written (`setFace` uncalled — verified), so the domain model defines the
  target, not current behavior.
- **`Wardrobe`** (current profile state) — the user's collection of
  `WardrobeItem` entities (the persisted `UserModel.wardrobe`).
- **`SavedLooks` list** (current profile state) — the user's collection of
  `SavedLook` references/entities.
- **`PreferredOccasions`** (current profile state / user preference) — the
  accumulated occasion focus recorded from events and elsewhere
  (`UserModel.preferredOccasions`).
- **`UserSession` flag** (current profile state — to become user state) —
  `hasSavedWardrobeItem` currently lives in `shared/` and is lost on restart
  (`DATA_MODEL_INVENTORY.md` §14, `ARCHITECTURE_GAP_REPORT.md` F1.4). The domain
  model classifies it as a **user profile state** flag (derived from a non-empty
  wardrobe), not a session flag.
- **`StyleScore`** (derived value, current) — computed
  `60 + wardrobe.length.clamp(0,20) + savedLooks.length*2.clamp(0,20)`
  (`learning_service.dart`, verified). Recomputed, never stored as truth
  (current value = cache; history = §2.5).

### 2.4 User preferences

Explicit user choices, durable and user-scoped. Today most are ephemeral widget
state (`FEATURE_DATA_MATRIX.md` rows marked "ephemeral" / `UI_UX_GAP_REPORT.md`
#6/#28). Domain concepts:

- **Style vibe / style type** — the 6 `StyleVibe` choices (`onboarding_data.dart`)
  and the profile style preferences; maps to `StyleProfile.styleType`.
- **Builder preferences** — occasion / mood / fit / color-palette selections
  (`BuilderOption` vocabulary, `outfit_builder_mock_data.dart`).
- **Grooming inputs** — face shape / beard style / density / color selections
  (`GroomingOption` vocabulary).
- **Profile preferences & settings toggles** — `PreferenceOption` / `SettingsItem`
  values (`profile_mocks.dart`).

Rule: a preference is a *chosen value* referencing a **vocabulary id** (system
knowledge), never a free-form duplicate of the vocabulary
(`ARCHITECTURE.md` "Expandable Data", "no hardcoded backend-controlled
categories").

### 2.5 Historical records

- **`LearningSignal`** — the only truly append-only history today (8 types:
  `item_added`, `analysis_updated`, `style_updated`, `look_saved`,
  `occasion_preferred`, `assistant_message`, `suggestion_opened`,
  `assistant_navigation`; `learning_service.dart` + assistant writes). Each
  signal carries type, label, timestamp. Per-user; append-only; soft-delete/
  retention (`DATA_OWNERSHIP.md` §`LearningSignal`, deletion matrix).
- **`StyleScoreRecord`** (missing concept — `DATA_MODEL_INVENTORY.md` §19.6;
  `STORAGE_INVENTORY.md` "score history") — dated score snapshots derived from
  signals/saves; enables the Home score card trend and Profile history.
- **`ActivityDay`** (missing concept — `STORAGE_INVENTORY.md` "streak/activity
  rows") — one record per styled day backing the streak timeline
  (`StyleStreakData`/`StreakDayData` mocks).
- **`Recommendation history`** (missing concept — `DATA_MODEL_INVENTORY.md`
  §19.6) — the trace of recommendations shown/saved, distinct from the
  `look_saved` signal; feeds personalization (P3 per `MVP_SCOPE.md`).
- **`AnalysisRun`** — see §2.2 (linkage record; historical).

### 2.6 AI outputs

Everything in this category is **reproducible from durable inputs + knowledge
and is never stored as truth** (`DATA_OWNERSHIP.md` rule 3; `STORAGE_INVENTORY.md`
Part 4 #6). Today all of these are static mocks (verified — `AI_DATA_FLOW.md`
headline).

- **`Recommendation`** — outfit / hairstyle / grooming recommendations with
  match score + reasons + alternatives (the `OutfitRecommendation`,
  `HairstyleRecommendation`, `GroomingRecommendation` families and the assistant
  suggestion cards). Content references knowledge; scoring is AI output.
- **`AnalysisResult`** — structured analysis output: outfit scan
  (`OutfitAnalysisData`: sections + detected items + scores), hairstyle/grooming
  results, future onboarding analysis (the dead `AnalysisResult`/`OnboardingResult`
  are its intended shape — `DATA_MODEL_INVENTORY.md` §13). Stored only as a
  **user-saved snapshot** linked to an `AnalysisRun`; otherwise cache-only.
- **`Today'sLook`** — the personalized daily look card
  (`DailyOutfitData`/`TodaysLookData`). A dated derived snapshot; current value
  cached, history per-user if kept (`STORAGE_INVENTORY.md` Part 2).
- **`Insight`** — wardrobe insight / AI insight cards
  (`WardrobeInsightData`/`AIWardrobeInsightData`/`AiInsightData`,
  `catalog.WARDROBE_INSIGHT`). Derived from wardrobe + knowledge; cache-only.
- **`MatchScore` / `RecommendationReason` / `EnsembleComponent` with
  `isOwned`** — discover look scoring/alternatives, derived from wardrobe +
  look catalog (`DATA_OWNERSHIP.md` §Discover; `DATA_MODEL_INVENTORY.md` §6).
- **`StyleDna` view** — the derived style-DNA display block over `StyleProfile`
  (see §2.3).
- **Assistant reply payload** — intent + text + cards + clarifications +
  navigation (see §2.9 DTOs); the *content* is AI output, the *shape* is a DTO.

### 2.7 System knowledge

Backend-owned reference content, shared, never user-tied, versioned
(`STORAGE_INVENTORY.md` Part 3 #7; `ARCHITECTURE_GAP_REPORT.md` K9.1). This is
where the **4× duplicated vocabularies and 3–4× mirrored catalogs** resolve
(`DATA_MODEL_INVENTORY.md` §19.1). The domain model requires **one canonical
vocabulary per concept**, referenced by stable id.

| Vocabulary / catalog | Step 2 duplicates being consolidated |
| --- | --- |
| **Occasion vocabulary** | `EventType` ids, builder/assistant `occasionOptions`, discover `OccasionFilters`, `backend OCCASIONS` — 4 copies |
| **Style vocabulary** | `StyleVibe`, profile style preferences, builder `moodOptions`, discover `StyleFilters` — 4 copies |
| **Wardrobe category / color / material / texture** | `AddItemCategoryConfig`, `ColorOption`, `TextureOption`, `AddItemConfig`, backend `WARDROBE` categories |
| **Event types** | `EventType.mockTypes` |
| **Look catalog** | `DiscoverLookData` mocks, `OutfitRecommendation.mock`, `DailyOutfitData.mock`, offline `_LookCard`, backend `catalog.py` looks — the "5 looks in 4 shapes" family |
| **Hairstyle / grooming catalog** | `HairstyleAnalysisResult.mock`, `GroomingAnalysisResult.mock`, backend `TEXTURED_QUIFF` / `STRUCTURED_GOATEE` etc. |
| **Builder / grooming options** | `BuilderOption`, `GroomingOption` |
| **Filters** | `OccasionFilters`, `StyleFilters`, `FitFilters` |
| **Capabilities / actions / navigation** | `allCapabilities`, `QuickActionData`, `StylistActionData`, backend `NAVIGATION_MAP` — config content |
| **Plans / support / achievements definitions** | `SubscriptionPlan`, `SupportTopic`, `AchievementData` definitions |
| **Seed wardrobe** | `defaultWardrobe` (24 items) + `WardrobeMockData.items` + backend `WARDROBE` |

Rule: knowledge is referenced by id from user data; it is never embedded per
user and never hardcoded in a feature (`ARCHITECTURE.md` Expandable Data).

### 2.8 External data

- **Weather** — external provider value, cache-only with short TTL, never a
  durable table (`STORAGE_INVENTORY.md` §1.9; today a fake literal).
- **Device media** — captured face/outfit/item images. Represented in the domain
  as **`MediaRef` value objects** (reference to object storage); the bytes are
  external blobs, never embedded in relational data (`STORAGE_INVENTORY.md`
  Part 3 #3; privacy policy MS10.3 required).
- **Auth provider identity** — Google/Apple subject id from `POST /auth/social`.
- **Entitlement / payment** — purchase service result backing subscription
  state (`STORAGE_INVENTORY.md` cat 5).
- **Optional LLM (Ollama)** — text enrichment; never routed by the LLM
  (`AI_DATA_FLOW.md` Part A; `engine.py` keeps structure).

### 2.9 DTOs (boundary contracts)

- **Assistant contract (existing, mirrored 1:1):** `AssistantReply`,
  `SuggestionCard`, `ClarificationOption`, `NavigationRequest`, `AssistantMessage`,
  `AssistantUserContext` (`features/assistant/data/models.dart` ↔
  `backend/app/models/schemas.py`) plus `ChatMessage`/`AssistantRequest`,
  backend `WardrobeItem`/`FaceData`/`UserContext`. These are **wire shapes**,
  not domain entities; the DB stores domain equivalents, not these
  (`DATA_MODEL_INVENTORY.md` §19.4). The mirrored contract is a KEEP
  (`ARCHITECTURE_GAP_REPORT.md` A3.1).
- **`AssistantUserContext`** is a **derived DTO** (a per-request snapshot of
  current profile state), not an entity (`DATA_OWNERSHIP.md` §`AssistantUserContext`).
- **Future API DTOs** — typed request/response shapes for auth, wardrobe CRUD,
  events, saved looks, analysis, generation, profile, sync
  (`ACTION_API_INVENTORY.md` Part 1). These are Step 4+ work; the domain model
  only fixes the domain concepts they carry.

### 2.10 Temporary processing state

Never durable, discarded when the screen/request ends
(`STORAGE_INVENTORY.md` cat 6; `DATA_OWNERSHIP.md` per-feature tables):

- Processing-stage choreography (`ProcessingStage`/`GenerationStage`/
  `HairstyleProcessingStage`/`GroomingProcessingStage`).
- In-flight assistant conversation (`AssistantService._messages`) and the
  request context snapshot.
- Scan buffers / transient image paths.
- Generation previews (pre-save).
- Route extras, active filters, scroll state.
- Greeting / date label / quick-action chrome (cache; `DATA_OWNERSHIP.md` §Home).

### 2.11 Explicitly NOT domain entities (presentation-only)

The STEP 2 UI-only models (`DATA_MODEL_INVENTORY.md` §19.2) stay presentation
DTOs / cache: `GreetingData`, `StyleTrend`, `StyleStreakData`, `StreakDayData`,
`QuickActionData`, `WardrobeCategory` (UI chip), `ColorOption`/`TextureOption`
(UI swatches — their *ids* come from knowledge), filter chips, `DiscoverTab*`,
`FaceScanCheck`, `AchievementData` (state render), `ProfileMenuAction`,
`PaletteSwatch`, `vibeGradientColors`, `AiCapability` (config render),
`StylistActionData`. These describe how a screen looks, not product facts; they
are intentionally excluded so the domain model represents product behavior, not
the Dart class list.

---

## 3. Relationship rules

Canonical ownership graph (owner → children; cardinality in parentheses):

```
User (aggregate root)
├── StyleProfile            (1, current profile state; embeds FaceProfile value object)
├── WardrobeItem            (0..N; domain entity)
├── UserEvent               (0..N; domain entity)
├── SavedLook               (0..N; domain entity, embeds snapshot value objects)
├── LearningSignal          (0..N; historical, append-only)
├── StyleScoreRecord        (0..N; historical, derived)
├── ActivityDay             (0..N; historical, derived)
├── AnalysisRun             (0..N; historical linkage)
├── UserPreferences         (1, user preference set, references vocabulary ids)
└── SubscriptionState       (0..1; user state + external entitlement)

System knowledge (system-scoped, shared, referenced by id):
  Look catalog · Occasion · Style · Wardrobe category · Color · Material/Texture ·
  EventType · Hairstyle/Grooming catalog · Builder/Grooming options · Filters ·
  Plans/Support/Achievement definitions · Capability/Action/Navigation config ·
  defaultWardrobe seed

Cross-entity relationships (concepts, not keys):
  SavedLook ──references──▶ Look (knowledge id)
  SavedLook ──embeds──▶ snapshot value objects (ensemble, score, reasons)
  SavedLook ──links──▶ AnalysisRun (when saved from a scan)
  UserEvent ──references──▶ EventType (vocabulary id)
  UserEvent ──links──▶ Recommendation (generated outfit; seeded with occasion)
  WardrobeItem ──references──▶ Category/Color/Material vocabulary ids
  WardrobeItem ──has──▶ MediaRef (value object → object storage)
  AnalysisRun ──links──▶ MediaRef (source image) + AnalysisResult (AI-output snapshot)
  Recommendation ──derived from──▶ StyleProfile + Wardrobe + Look knowledge
  StyleScore ──derived from──▶ Wardrobe count + SavedLook count (formula)
  StyleDna view ──derived from──▶ StyleProfile
  AssistantUserContext ──derived snapshot of──▶ StyleProfile + Wardrobe + SavedLooks + PreferredOccasions
  Today'sLook ──derived from──▶ StyleProfile + Wardrobe + UserEvents + Weather + preferences
```

Rules:

1. **User is the scope boundary.** Every user-owned concept hangs off `User`; no
   user-owned concept exists standalone.
2. **Value objects are embedded, entities are referenced.** `FaceProfile` fields,
   outfit components, media refs, scores, reasons are value objects living inside
   their owning entity.
3. **Knowledge is referenced by id, never copied per user.** A user's saved look
   points at a `Look`; it does not carry the catalog in duplicate.
4. **AI output is linked, not owned.** Recommendations/analysis/insights point at
   their inputs; they are regenerable.
5. **Historical records are append-only and never edited** (signals, score
   records, activity days, analysis runs).
6. **Derived values recompute from durable inputs** — never duplicated at rest
   (resolves the duplicate families in `DATA_MODEL_INVENTORY.md` §19.1).
7. **The current `UserModel` blob is a projection, not a source of truth.** The
   domain concepts it mixes (profile state, wardrobe, saved looks, signals,
   preferences) are the real entities; the blob's split is a migration concern
   (`STORAGE_INVENTORY.md` Part 4 #1).

---

## 4. Invariants (domain rules the model enforces)

1. **AI output is never a source of truth.** Persist inputs (user data, media)
   and outcomes (saved-look refs, signals, kept snapshots); discard or snapshot
   ephemeral analysis (`DATA_OWNERSHIP.md` rule 3).
2. **One owner per concept.** Each canonical entity has exactly one owning
   feature / domain boundary; screens talk to repositories, never storage
   (`ARCHITECTURE_GAP_REPORT.md` F1.1, R4.1).
3. **Vocabularies are backend-controlled.** No feature hardcodes a
   backend-controlled category; knowledge comes from the backend
   (`ARCHITECTURE.md` Expandable Data; `ARCHITECTURE_GAP_REPORT.md` K9.1).
4. **Appearance data is private.** Face/outfit media is user-scoped, retained
   per policy, deletable, and never logged (AGENTS safety rules; MS10.3).
5. **Historical data is append-only** with retention/soft-delete rules
   (`DATA_OWNERSHIP.md` deletion matrix).
6. **A value object is interchangeable and immutable** — mutating it replaces
   the whole object inside its owner.
7. **Identity is stable** for entities; nothing reuses another entity's id
   across concepts (the current 3× mirror of the 24-item wardrobe with the same
   ids is a knowledge seed, not three user-owned entity sets).

---

## 5. STEP 2 → domain category mapping

Primary category assigned to every important STEP 2 concept. This is the
coverage proof for §2 (nothing invented, nothing unclassified).

| STEP 2 concept (inventory ref) | Domain category |
| --- | --- |
| `UserModel` aggregate (§1.1) | Current profile state (projection to split) |
| `WardrobeEntry` / `WardrobeItemData` / backend `WardrobeItem` / discover `WardrobeItem` (§1.2, §4, §15, §6) | Domain entity `WardrobeItem` (canonical) |
| `FaceProfile` (§1.3) | Current profile state (value object content, AI-generated) |
| `LearningSignal` (§1.4) | Historical record |
| `defaultWardrobe` seed (§1.7) | System knowledge (seed) |
| `AssistantUserContext` / backend `UserContext` (§2.6, §15) | DTO (derived snapshot) |
| `AssistantMessage` / conversation (§2.5) | Temporary processing state (DTO payload; historical only if retention decided) |
| `SuggestionCard` / `AssistantReply` / `ClarificationOption` / `NavigationRequest` (§2.1–2.4, §15) | DTO (shape) + AI output (content) |
| `OfflineAssistant` / `_LookCard` (§2.8–2.9) | System knowledge (mirrored catalog) + system logic |
| `GreetingData`, `QuickActionData`, `StyleTrend` (§3.1) | Temporary / system chrome (cache) |
| `TodaysLookData`, `DailyOutfitData`, `AlternativeLookData` (§3) | System knowledge (catalog) + AI output (scoring) |
| `StyleScoreData`, `StyleScoreBreakdownItem` (§3.1) | Derived value (current `StyleScore`) |
| `StyleStreakData`, `StreakDayData` (§3.1) | Historical record (future `ActivityDay`) |
| `AIWardrobeInsightData`, `WardrobeInsightData`, `AiInsightData` (§3–4) | AI output (derived insight) |
| `StyleDnaContext`, `StyleDnaData` (§3, §12) | Derived view over `StyleProfile` |
| `WardrobeContext` (§3.2) | Derived value |
| `WardrobeCategory`, `ColorOption`, `TextureOption`, `AddItemCategoryConfig`, `AddItemConfig` (§4) | System knowledge (vocabularies) |
| `StylistActionData` (§5) | System knowledge (action config) |
| `DiscoverLookData` (§6) | System knowledge (look catalog) |
| `MatchScoreDetails`, `RecommendationReason` (§6) | AI output (value objects) |
| `EnsembleComponent`, `WardrobeAlternative` (§6) | Derived value objects (from wardrobe + catalog) |
| `FilterOption`, `OccasionFilters`, `StyleFilters`, `FitFilters`, `DiscoverTab*` (§6) | System knowledge (filter vocabularies) / temporary (UI) |
| `OutfitAnalysisData`, `AnalysisSection`, `DetectedClothingItem` (§7) | AI output (`AnalysisResult` snapshot) |
| `ProcessingStage` ×4 (§7–10) | Temporary processing state |
| `OutfitRecommendation`, `OutfitComponent` (§8) | AI output (value objects) |
| `BuilderOption` (§8), `GroomingOption` (§10) | System knowledge (option vocabularies) |
| `FaceScanCheck` (§9) | System knowledge (readiness config) |
| `HairstyleRecommendation` / `HairstyleAnalysisResult` (§9) | AI output (+ knowledge catalog content) |
| `GroomingRecommendation` / `GroomingAnalysisResult` (§10) | AI output (+ knowledge catalog content) |
| `EventType` (§11) | System knowledge (vocabulary) |
| `UserEvent` (§11) | Domain entity |
| `ProfileData`, `StylistLevelData`, `GlobalRankData`, `StyleProgressData`, `AchievementData` (§12) | Derived values (definitions = knowledge) |
| `SavedLookPreview`, `SavedLookDetail` (§12) | Derived view over `SavedLook` |
| `PreferenceOption`, `SettingsItem`, `SupportTopic`, `SubscriptionPlan` (§12.2) | System knowledge + user preference (values) |
| `StyleVibe`, `vibeGradientColors`, `PaletteSwatch`, `AiCapability`, `allCapabilities` (§13) | System knowledge (onboarding config) |
| `AnalysisResult`, `OnboardingResult` (§13, dead) | AI output (intended onboarding analysis shape) |
| `UserSession.hasSavedWardrobeItem` (§14) | Current profile state flag (belongs to user model) |
| Backend `schemas.py` DTOs (§15) | DTO (wire contract) |
| Backend `catalog.py` constants (§16) | System knowledge |
| Weather literal (§3.1) | External data (cache) |
| Missing concepts: `User`, score/streak history, event rows, achievements/XP, media, recommendation history, subscription, saved-look payload, today's-look snapshot (§19.6) | Domain entity / Historical / Derived / External per §2 |
| Camera image paths, stage timers, filters, route extras | Temporary processing state |

---

## 6. Resolution of the STEP 2 open questions (domain-model answers)

From `STEP_2_FINAL_REPORT.md` §13; these are the domain-model positions. Storage
shapes are deliberately deferred to Step 4.

1. **Where does `User` formally live?** — `User` is the aggregate root of all
   user-owned entities (§2.1). Everything else is scoped to it. Its *code*
   location is an architecture decision (auth feature), not a domain question.
2. **Assistant wardrobe-context snapshot ownership?** — `AssistantUserContext`
   is a **derived DTO** built from current profile state per request
   (`DATA_OWNERSHIP.md` §`AssistantUserContext`). It is never a domain entity
   and never stored.
3. **Knowledge source: catalog table or served config?** — Domain model: it is
   **system knowledge** referenced by id (§2.7). Whether the backend serves it
   as a config contract or a versioned catalog store is a Step 4 storage
   decision; the domain only requires a single canonical source per vocabulary.
4. **Event entity: ownable or trigger?** — `UserEvent` is an **ownable user
   entity** (§2.2) that *also* acts as an outfit-generation trigger. Both roles
   coexist: it is persisted and editable, and its `EventType`/occasion feeds
   recommendation generation and the `PreferredOccasions` preference.

---

## 7. Report — what was found & what must be modeled next

### What was found

- **The domain core already exists implicitly** in `features/learning`
  (`WardrobeEntry`, `FaceProfile`, `LearningSignal`, `UserModel`) but is merged
  into one blob and partly dead (`setFace` never called; `FaceProfile` empty;
  `savedLooks` written but never displayed).
- **Five durable domain entities are evidenced and modeled here:** `User`
  (missing, required), `WardrobeItem` (canonical of 4 shapes), `UserEvent`
  (unpersisted today), `SavedLook` (title-only today, payload missing), and
  `AnalysisRun` (linkage required by the storage inventory).
- **Everything else that looks like data is one of:** system knowledge
  (vocabularies + catalogs, currently 3–4× duplicated), AI output (all currently
  mock), derived values (recomputable), DTOs (the assistant wire contract),
  external data (weather, media, auth/entitlements), or temporary processing
  state. The STEP 2 UI-only list (§19.2) is deliberately excluded from the
  domain.
- **Three ownership ambiguities are resolved at the domain level:** saved looks
  (learning owns, profile displays derived views), the session flag (profile
  state, derived from wardrobe), and vocabularies (single backend-owned source
  per concept).
- **The AI-output-never-truth rule is the binding invariant:** durable inputs +
  user-saved snapshots are persisted; ephemeral analysis is not.

### What must be modeled next (in dependency order)

1. **Typed API + error contract** (A3.2/A3.3/E13.1) shaped by these entities —
   starting with the P0 endpoints (`MVP_SCOPE.md` Part 1): auth, wardrobe CRUD,
   saved looks, assistant, `POST /users/me/sync`.
2. **The auth + anonymous→sync design** (AU11.1/AU11.2) against `User`, since it
   defines `User`'s fields and the account↔device merge semantics.
3. **Per-feature repository interfaces** (R4.2) over the canonical entities
   (learning/wardrobe/assistant first) so the mock→backend swap has a seam.
4. **The storage split** (P7.1): which of these entities become relational rows,
   which are JSONB current-state/snapshot, which are knowledge content, and
   where `MediaRef` points (object storage). This is Step 4.
5. **Media privacy policy** (MS10.3) for face/outfit media before any media
   persistence.
6. **Sequence per `MVP_SCOPE.md`:** P0 = `User`, `WardrobeItem`, `SavedLook`
   reference, `LearningSignal`, vocabularies for P0; P1 = `UserEvent`,
   saved-look payload, score/streak records, `StyleProfile` pipeline, `ActivityDay`;
   P2/P3 = analysis runs, recommendation history, achievements/XP, subscription,
   today's-look history.

These are model/contract decisions only — none are implemented by this step.

---

## Constraints honored

- No SQL, no migrations, no database tables, no repositories, no FastAPI
  services.
- No Flutter architecture changes, no UI or routing changes, no new
  dependencies, no code deleted.
- No entity invented beyond STEP 2 evidence; each canonical entity cites its
  inventory reference.
- The REAL Fansivibe repository is the source of truth; the separate reference
  project was not merged or used.
