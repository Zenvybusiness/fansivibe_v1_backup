# Fansivibe — Domain Model v1 (Consolidated)

> **STEP 3 FINAL — DOMAIN MODEL DESIGN.** The single, consolidated domain model
> for the real Fansivibe product. It synthesizes the ten STEP 3 documents and
> cross-checks their every verdict against the real source
> (`newproject/flutter_application_1` + `backend/`) and the twelve STEP 2
> inventory documents, resolving duplicates, conflicts, and unnecessary
> entities into one authoritative model for Step 4 (PostgreSQL design).
>
> **Status:** documentation only. No SQL, no migrations, no tables, no
> repositories, no services, no Flutter/UI/routing changes, no dependencies, no
> code deleted. Nothing here is implemented.
>
> **Source of truth:** the real repository. The separate reference project is
> not merged and was not used.

---

## 1. Domain overview

Fansivibe is an **appearance-styling product**: the user curates a wardrobe,
receives personalized recommendations (today's look, discover, outfit
generation, hairstyle/grooming), and interacts with an AI assistant. The domain
model separates the small number of **true entities** (10, +2 conditional)
from everything that merely looks like data — value objects, DTOs, AI outputs,
derived values, system knowledge, external data, and temporary state.

The model is governed by one binding invariant from STEP 2
(`DATA_OWNERSHIP.md` rule 3): **AI output is never a source of truth.** Durable
inputs (user data, captured media) and durable outcomes (saved-look references,
signals, kept snapshots) are persisted; ephemeral analysis is discarded or kept
only as a user-saved snapshot.

Core shape:

```
User (aggregate root)
├── StyleProfile            (1; current profile state, embeds FaceProfile value object)
├── WardrobeItem            (0..N; domain entity)
├── UserEvent               (0..N; domain entity)
├── SavedLook               (0..N; domain entity, embeds snapshot value objects)
├── LearningSignal          (0..N; historical, append-only)
├── StyleScoreRecord        (0..N; historical, derived)
├── ActivityDay             (0..N; historical, derived)
├── AnalysisRun             (0..N; historical linkage)
├── UserPreferences         (1; preference set referencing vocabulary ids)
└── Subscription            (0..1; user state + external entitlement, P2)

System knowledge (system-scoped, shared, referenced by id):
  Look catalog · Occasion · Style · Wardrobe category · Color · Material/Texture ·
  EventType · Hairstyle/Grooming catalog · Builder/Grooming options · Filters ·
  Plans/Support/Achievement definitions · Capability/Action/Navigation config ·
  defaultWardrobe seed
```

---

## 2. Cross-check audit method

The final model was produced by re-running the entity classification and
relationship rules of the ten STEP 3 documents against three independent
references and reconciling every discrepancy:

| Cross-check reference | What it guards against |
| --- | --- |
| Real source tree (`lib/features/*`, `backend/app/*`) | invented or dead concepts; wrong cardinality |
| `FEATURE_INVENTORY.md`, `DATA_MODEL_INVENTORY.md` | entities missing from the 50-candidate pool |
| `FEATURE_DATA_MATRIX.md`, `DATA_OWNERSHIP.md` | wrong owner, duplicated shapes, wrong storage home |
| `AI_DATA_FLOW.md` | AI-output/domain-model confusion |
| `MVP_SCOPE.md` | P0/P1/P2/P3 entity scoping |

Spot-verified facts that anchor the model (re-checked against source this step):

- **Score formula** — `60 + wardrobe.length.clamp(0,20) + (savedLooks.length*2).clamp(0,20)` at `learning_service.dart:228-229`. Deterministic; derived, never a truth store.
- **Capabilities are marketing config** — `allCapabilities` (`onboarding_data.dart:79`) lists 7 items, only 2 `active: true` (`:83`, `:94`). No per-user capability state exists anywhere.
- **`FaceProfile` is never written** — `setFace` is declared (`learning_service.dart:276`, `learning_repository.dart:25`) but has zero call sites in `lib/`.
- **No feedback feature exists** — no like/dislike/why anywhere (grep-verified during STEP 3).
- **Only real API** — `POST /v1/assistant/chat`; no auth; `account_creation_screen.dart` branches all just navigate home.
- **Event context is lost** — Event Details "Generate Outfit" pushes `RouteNames.buildOutfit` with no event data (`event_details_screen.dart:316-318`).
- **Weather is a fake literal** — `'68°F • Partly Cloudy'` in `home_mock_data.dart:63` / `daily_outfit_mock_data.dart:65`.
- **Assistant DTOs mirror backend 1:1** — `features/assistant/data/models.dart` ↔ `backend/app/models/schemas.py`; KEEP (`ARCHITECTURE_GAP_REPORT.md` A3.1).

---

## 3. Category system

Every concept is classified into exactly one primary kind
(`DOMAIN_MODEL_RULES.md` §1; decision procedure there):

1. **Domain entity** — own identity + lifecycle + durable business subject.
2. **Value object** — immutable, no identity, embedded in an entity.
3. **DTO** — boundary shape across app↔backend; never a source of truth.
4. **AI output** — regenerable computed result; never stored as truth.
5. **Historical record** — append-only evidence of the past.
6. **Current profile state** — the user's durable present state.
7. **User preference** — explicit user choice referencing vocabulary ids.
8. **System knowledge** — backend-owned shared reference content.
9. **External data** — produced by a third party / the device.
10. **Temporary processing state** — gone when the screen/request ends.

Primary rule from STEP 2: **AI output is never a source of truth.**

---

## 4. Entity catalog

**10 true domain entities** (from the 50-candidate pool, each passing the four
tests: identity, lifecycle, durability, product behavior). Two conditional
entities follow.

| ID | Entity | Owner (feature) | User-owned | Historical | Persisted today |
| --- | --- | --- | --- | --- | --- |
| E1 | `User` | auth (future) | yes (is the user) | no | no (missing concept) |
| E2 | `WardrobeItem` | wardrobe (via learning) | yes | no | yes (inside `UserModel` blob) |
| E3 | `UserEvent` | events | yes | partly | no (widget state only) |
| E4 | `SavedLook` | learning (truth), profile (views) | yes | partly | title-only (`List<String>`) |
| E5 | `Look` | backend knowledge / content | no | no | no (mock catalog ×4) |
| E6 | `AnalysisRun` | outfit_scan / hairstyle / grooming | yes | yes | no (mock pipeline) |
| E7 | `LearningSignal` | learning | yes | yes | yes (append-only) |
| E8 | `StyleScoreRecord` | learning (derived) | yes | yes | no (computed + mock) |
| E9 | `ActivityDay` | learning (derived) | yes | yes | no (mock streak) |
| E10 | `Subscription` | profile / external entitlement | yes (state) | no | no (mock plans) |

**Conditional entities** (exist only if a pending product decision is yes):

- **`Today'sLookRecord`** (P1 decision) — per-user dated snapshot of the daily
  look. `DailyOutfitData`/`TodaysLookData` are regenerated mocks today. Becomes
  a historical entity only if the product wants "what I wore" history
  (`STORAGE_INVENTORY.md` "daily_look row per user/day").
- **`RecommendationHistory`** (P3 decision) — trace of recommendations
  shown/saved for personalization analytics. Today only `look_saved` signals
  trace it. If built: user-owned historical entity referencing `Look` + scores.

**Deliberately excluded** (verdicts and rationale in `DOMAIN_ENTITIES.md` §3):
all assistant DTOs (wire contract, KEEP), UI/mock models, processing stages,
filters, vocabularies, weather, media bytes, achievements/XP (derived), and the
dead onboarding models (`AnalysisResult`/`OnboardingResult`, never used).

---

## 5. Value objects

**No value object gets its own table** (`VALUE_OBJECTS.md`). All 11 candidates
passed the identity test (interchangeable when attributes match). Canonical set:

| Value object | Home / embedded in | Note |
| --- | --- | --- |
| `FaceProfile` (`faceShape`, `skinTone`, `bodyType`, `styleType`) | `StyleProfile` (→ `User`) | AI-generated content; durable state; `setFace` dead today |
| Outfit-piece object (canonical of `OutfitItemData`, `DailyOutfitComponent`, `EnsembleComponent`, `OutfitComponent`, `DetectedClothingItem`) | `Look`, `SavedLook` snapshot, recommendations | 5 shapes collapsed to one |
| `MatchScoreDetails`, `RecommendationReason` | recommendations / look details | AI-output scoring |
| `MediaRef` | `WardrobeItem`, `AnalysisRun`, `SavedLook` | points to object-storage blob |
| `WardrobeAlternative` | discover result | derived (wardrobe × catalog) |
| `AnalysisResult` snapshot (`OutfitAnalysisData`, `AnalysisSection`, etc.) | `AnalysisRun` | AI output; stored only as saved snapshot |
| Style DNA view (`StyleDnaData`/`StyleDnaContext`) | derived over `StyleProfile` | display shape, not entity |
| Insight family (`WardrobeInsightData`/`AIWardrobeInsightData`/`AiInsightData`) | cache | AI output, derived |
| Score + breakdown (`StyleScoreData`/`StyleScoreBreakdownItem`) | cache / `StyleScoreRecord` | derived |
| `AssistantUserContext` / `UserContext` | assistant request | derived DTO |
| `SavedLook` snapshot payload (ensemble, score, reasons at save time) | `SavedLook` | boundary case — snapshot of AI output |

Rules: vocabularies are **config** (system knowledge), chosen values are **id
columns** referencing the vocabulary, derived values are **immutable snapshots**
never recomputed-and-overwritten as truth. Non-value-object look-alikes
(`SavedLook`, `Look`, `SubscriptionPlan`, AI Model Version, `WardrobeItem`,
`UserEvent`) remain entities because they carry identity/state (`VALUE_OBJECTS.md` §6).

---

## 6. Relationships

The full relationship set is captured per domain in
`DOMAIN_RELATIONSHIPS.md` (R1–R51 core), `STYLE_WARDROBE_DOMAIN_MODEL.md`
(W1–W25), `APPEARANCE_DOMAIN_MODEL.md` (P1–P17), `CONTEXT_DOMAIN_MODEL.md`
(C1–C16), `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md` (G1–G11), and
`AI_DOMAIN_MODEL.md` (R-A1–R-A21). Cross-checked, they form one consistent
graph with no duplicate or conflicting edges.

**Backbone** (`DOMAIN_RELATIONSHIPS.md`):

```
User ──scopes──▶ WardrobeItem | UserEvent | SavedLook | LearningSignal |
                 StyleScoreRecord | ActivityDay | AnalysisRun | Subscription
User ──owns──▶ StyleProfile (1) ──embeds──▶ FaceProfile
User ──holds──▶ PreferredOccasions (preference list)
SavedLook ──references──▶ Look (by id, not title)
SavedLook ──embeds──▶ snapshot value objects
SavedLook ──links──▶ AnalysisRun (when saved from a scan)
UserEvent ──references──▶ EventType vocabulary
UserEvent ──links──▶ Recommendation (generated outfit, occasion-seeded; future)
WardrobeItem ──references──▶ Category/Color/Material vocabularies
WardrobeItem ──has──▶ MediaRef → object storage
AnalysisRun ──links──▶ MediaRef (source) + AnalysisResult snapshot
Recommendation ──derived from──▶ StyleProfile + Wardrobe + Look knowledge
StyleScore ──derived from──▶ wardrobe count + savedLooks count (formula)
StyleDna ──derived from──▶ StyleProfile
AssistantUserContext ──derived snapshot of──▶ StyleProfile + Wardrobe + SavedLooks + PreferredOccasions
Today'sLook ──derived from──▶ StyleProfile + Wardrobe + UserEvents + weather + preferences
```

**Cross-domain edges** (the final synthesis):

- **Wardrobe ⇄ Assistant:** assistant context reads up to 12 `WardrobeItem`s
  (`AI_DATA_FLOW.md`; `engine.py` `_context_summary`); `AssistantUserContext`
  is a derived DTO, never stored.
- **Wardrobe ⇄ Discover:** discover look scoring = `WardrobeAlternative` +
  `MatchScoreDetails` derived over wardrobe × `Look` catalog.
- **Events ⇄ Outfit Builder:** "Generate Outfit" today drops event context
  (`event_details_screen.dart:316-318`); the domain model requires `UserEvent`
  → `Recommendation` linkage so the occasion seeds generation (P1 fix).
- **Saved Look ⇄ Catalog:** every save path (Daily Outfit :1172, Look Details
  :327, Outfit Analysis :260, future Builder/Style saves) records a `SavedLook`
  referencing a `Look` **id** (`ACTION_API_INVENTORY.md` #14).
- **AI ⇄ Learning:** assistant emits 3 signal types (`assistant_message`,
  `suggestion_opened`, `assistant_navigation`); learning emits 5. All feed the
  derived score/streak records.

**Honest corrections recorded during STEP 3** (no fabrication, no over-reach):

1. There is **no standalone `Outfit` entity** — "outfit" is a value-object
   ensemble inside a `Look`, a `SavedLook` snapshot, or a recommendation.
2. **Recommendation → Feedback** relationship is **future** — no feedback
   feature exists today; the domain defines it as the intended learning loop,
   not current behavior.
3. **User → AI Capabilities** is **future/prospective** — capabilities are
   config; per-user capability state would be a new domain concept, deferred.

---

## 7. Ownership

Single-persistence-owner rule (`ARCHITECTURE_GAP_REPORT.md` F1.1) is KEEP:
`LearningService`/`LocalStore` owns all local persistence today. The domain
model assigns exactly one owning feature per canonical entity
(`DOMAIN_ENTITIES.md` §4 matrix; `DATA_OWNERSHIP.md` master classification):

| Entity | Owning feature | Other consumers |
| --- | --- | --- |
| `User` | auth (future) | every feature (scope) |
| `WardrobeItem` | wardrobe | learning, assistant, home, discover, builder, scan |
| `UserEvent` | events | learning (occasion), builder (future), assistant |
| `SavedLook` | learning (truth) | profile (views), home/discover/scan/builder/hairstyle/grooming (writers) |
| `Look` | backend knowledge (system) | discover, home, assistant, saved looks |
| `AnalysisRun` | outfit_scan / hairstyle / grooming | learning (persist), saved looks |
| `LearningSignal` | learning | all features (writers) |
| `StyleScoreRecord` | learning (derived) | home, profile |
| `ActivityDay` | learning (derived) | home, profile |
| `Subscription` | profile / external entitlement | — |

**Ownership decisions resolved at the domain level:**

- **Saved looks:** `features/learning` owns the persisted truth; `profile`
  renders derived views (`SavedLookPreview`/`SavedLookDetail`). Fix `UI_UX_GAP_REPORT.md` #7.
- **Session flag:** `hasSavedWardrobeItem` is **user profile state** (derived
  from a non-empty wardrobe), not a session flag — move to the user model
  (`ARCHITECTURE_GAP_REPORT.md` F1.4).
- **Assistant wardrobe-context snapshot:** `AssistantUserContext` is a
  **derived DTO** built per request, never an entity and never stored.
- **Vocabularies:** one backend-owned source per concept, referenced by id
  (`ARCHITECTURE_GAP_REPORT.md` K9.1) — resolves the 4× duplicated occasion/
  style vocabularies and 3–4× mirrored catalogs.
- **User identity:** `User` is the aggregate root; its *code* location (auth
  feature) is an architecture decision, not a domain question.

---

## 8. Lifecycle

Per entity (full detail in `DOMAIN_ENTITIES.md` §2 and `DOMAIN_MODEL_RULES.md`
§2.2):

- **E1 `User`** — register/social → authenticate → update → delete (cascades
  user-owned data per `STORAGE_INVENTORY.md` retention).
- **E2 `WardrobeItem`** — create (`wardrobe_screen.dart:301` → `addItem`);
  mutate (favorite today; edit/delete stubs — gap #4); delete (no UI yet).
- **E3 `UserEvent`** — create (Add Event form); edit/delete (stubs — gap #5);
  may trigger outfit generation.
- **E4 `SavedLook`** — create from any of 4 save paths; remove (no UI yet).
- **E5 `Look`** — authored/versioned/deprecated by content management; never
  user-tied.
- **E6 `AnalysisRun`** — created per analysis execution; result retained only
  while useful or if the user saves the look (`STORAGE_INVENTORY.md` §1.6).
- **E7 `LearningSignal`** — appended on every relevant action; never edited or
  deleted (soft-delete/retention only).
- **E8/E9 `StyleScoreRecord`/`ActivityDay`** — created periodically / per
  styled day; append-only.
- **E10 `Subscription`** — activate → renew → cancel/expire (external service).

**Lifecycle rule:** current-state entities are mutable (edited in place);
historical entities are **append-only and never edited** (invariant 5).

---

## 9. Current vs historical

Classification (from `DOMAIN_STATE_AND_HISTORY.md`) — the "what is now vs what
happened" split that determines storage and update rules:

| Concept | Kind | Reproducibility policy | Do-not-overwrite rule |
| --- | --- | --- | --- |
| `User` | current state | n/a | — |
| `StyleProfile` + `FaceProfile` | current state | mutable projection with `source_run_id` provenance | never clobbered by a stale run; a new run appends then projects |
| `Wardrobe` collection | current state | — | user edits in place |
| `PreferredOccasions` | current state / preference | — | additive |
| `SavedLook` list | current state | — | user-managed |
| `WardrobeItem` | current state | — | user edits in place |
| `UserEvent` | current (dated, editable) | — | user edits in place |
| `LearningSignal` | **historical** | append-only | never edited/deleted |
| `StyleScoreRecord` | **historical** | derived from durable inputs | append-only |
| `ActivityDay` | **historical** | derived from signals/looks | append-only |
| `AnalysisRun` | **historical** | linkage record | append-only; result snapshot may be re-derived but not overwritten in place |
| `Today'sLookRecord` (conditional) | **historical** (if kept) | derived daily snapshot | append-only per day |
| `RecommendationHistory` (conditional) | **historical** | shown/saved trace | append-only |
| AI outputs (scores, reasons, insights, DNA view) | derived/AI | **recompute, never overwrite stored truth** | never persisted as truth |

**Policy:** current state = mutable, owned by `User`; history = append-only,
derived from signals/durable inputs; AI outputs and derived views recompute and
are cached, never persisted as truth. The current `UserModel` blob is a
**projection** that mixes both — it splits in Step 4 (`STORAGE_INVENTORY.md`
Part 4 #1; `ARCHITECTURE_GAP_REPORT.md` P7.1).

---

## 10. AI domain

From `AI_DOMAIN_MODEL.md`. Ten AI concepts classified into the ten categories;
the result is that **AI leaves almost no durable domain state behind**:

| AI concept | Classification | Relationship to the domain |
| --- | --- | --- |
| AI model provider (Ollama) | External data / system | referenced by config; never routed by LLM (`engine.py`) |
| AI model version (`llama3.1:8b`, env `FANSIVIBE_OLLAMA_MODEL`/`HOST`, `FANSIVIBE_DISABLE_LLM=1`) | System knowledge (config) | reference, not entity |
| AI capability (`allCapabilities`/`AiCapability`) | System knowledge (config) | 7 items / 2 active = marketing copy; no per-user state |
| AI capability progress | Config only (UI copy) | no rows; per-user progress = future concept |
| Assistant chat | DTO + AI output + temporary | `POST /v1/assistant/chat`; offline mirror fallback |
| Analysis (scan/hairstyle/grooming) | AI output → `AnalysisRun` | run = historical, result = snapshot value object |
| Recommendations | AI output | content references knowledge; scoring = value objects |
| Insights / Style DNA / match scores | AI output (derived) | cache-only |
| Confidence | **Not computed anywhere** | card scores are catalog constants; no confidence field |
| Feedback | Future historical | learning loop; not in MVP P0/P1 scope today |

Pipeline chain (`R-A1`–`R-A21`): user state → context DTO → provider →
typed reply → offline mirror; each hop typed and reversible. **There is no
structured "reason" field on any AI output** (`AI_DATA_FLOW.md` Part D.4); the
domain model does not invent one.

---

## 11. Appearance domain

From `APPEARANCE_DOMAIN_MODEL.md`. Nine concepts; only four have any real
(dead/mock) shape, and two of those are planned:

| Concept | Status | Domain treatment |
| --- | --- | --- |
| `FaceProfile` | defined, **never written** (`setFace` uncalled) | value object in `StyleProfile` |
| Style Profile / Style DNA | mock derived view | current profile state + derived view |
| Appearance Analysis | dead (`AnalysisResult`/`OnboardingResult` never used) | intended `AnalysisRun` snapshot shape |
| Style Score | computed (`learning_service.dart:228`) | derived; history = `StyleScoreRecord` |
| Hair Profile | **PLANNED** (capability flag only) | no entity, no table |
| Grooming Profile | **PLANNED** | no entity, no table |
| Color Profile | **PLANNED** | no entity, no table |
| Appearance Intelligence | UI copy only (`entry_screen.dart:203`, `your_analysis_screen.dart:266`) | not a domain fact |
| AI Capability Progress | static config + "2 of 7 active" count | no per-user state |

**Decision:** the appearance domain contributes **no new entity**. It maps to
existing ones: `FaceProfile` value object, `StyleProfile` state, `AnalysisRun`
(once face analysis is real — P3), `StyleScoreRecord` (score history), and the
privacy rule that appearance data is user-scoped and never logged.

---

## 12. Wardrobe / outfit domain

From `STYLE_WARDROBE_DOMAIN_MODEL.md`. Twelve concepts collapse to **three
entities** (`WardrobeItem`, `SavedLook`, `Look`) and **no `Outfit` entity**:

- **Wardrobe item** — one entity canonicalizing 4 shapes (`WardrobeEntry`,
  `WardrobeItemData`, backend `WardrobeItem`, discover alternative).
- **Outfit** — a value-object ensemble (5 piece shapes collapsed), embedded in
  `Look`, `SavedLook` snapshot, or a recommendation.
- **Saved look** — user's durable save with snapshot payload + `Look` id.
- **Look** — the shared catalog item, the only knowledge content with entity
  semantics (referenced by id).
- **Wardrobe gap** — a typed insight value object, not an entity.
- **Outfit feedback** — one concept merged with Recommendation feedback
  (future).
- 4 occasion vocabularies → one; 3 insight shapes → one.

25 relationships (W1–W25) verified consistent with the core graph.

---

## 13. Context / events domain

From `CONTEXT_DOMAIN_MODEL.md`. Six concepts; **two entities**:

- **`UserEvent`** — ownable, dated user entity (also a generation trigger).
- **`SavedLook`** — referenced by events context.
- **Event Styling** — a capability + flow, not an entity. Today "Generate
  Outfit" navigates with **no event data** (`event_details_screen.dart:316-318`).
  Fix (P1): carry occasion into the builder.
- **Weather** — **external cache only**, never a table. The literal
  `'68°F • Partly Cloudy'` (`home_mock_data.dart:63`) is not product data.
- **Discover Content** — `Look` catalog knowledge.
- **Event Type** — vocabulary (8 types, `event_mock_data.dart:10`).

16 relationships (C1–C16) verified consistent with the core graph.

---

## 14. Account / subscription domain

From `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md`. Nine concepts; **two entities**
(`User`, `Subscription` P2):

- **Auth** — an external boundary process. `User` holds an **opaque identity
  reference**; the three account branches today just navigate home
  (`account_creation_screen.dart:74-98`). No auth model inside the domain.
- **Subscription** (P2) — user-owned entitlement state; plans are system
  knowledge; `SubscriptionPlan.price` is a display `String`
  (`profile_mocks.dart`); purchase is external.
- **Feature Entitlement** — derived, no entity.
- **Feature Usage** — maps to the existing `LearningSignal`.
- **Conversation** — transient processing state; retention **undecided**.
- **Assistant Message** — DTO, mirrored (KEEP).
- **Assistant Action** — config: 16 action ids (`assistant_routes.dart:8`).

11 relationships (G1–G11) verified consistent with the core graph.

---

## 15. Assistant domain

From `AI_DOMAIN_MODEL.md` + `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md`:

- The assistant is the **only real pipeline**: chat → `POST /v1/assistant/chat`
  → `engine.py` (system prompt + up to 12-item wardrobe context) → typed
  `ChatReply` → offline mirror fallback.
- Its contract is **DTOs**, mirrored 1:1 with the backend (`schemas.py`),
  KEEP (`ARCHITECTURE_GAP_REPORT.md` A3.1). The DB stores domain equivalents,
  not these shapes.
- The assistant **writes `LearningSignal`s** (3 types) and reads current
  profile state via a derived `AssistantUserContext` DTO.
- It has **no durable domain entity of its own**: no conversation table, no
  message table, no capability state.

---

## 16. Domain boundaries

What lives **outside** the entity model (and is explicitly not built):

- **System knowledge** — vocabularies, catalogs, options, plans, capabilities,
  config, seed wardrobe: backend-owned, versioned, referenced by id
  (`DOMAIN_MODEL_RULES.md` §2.7). One canonical source per concept.
- **DTOs** — the assistant wire contract (KEEP mirrored) and future API shapes.
- **External data** — weather (cache), device media (via `MediaRef` → object
  storage), auth-provider identity, entitlement/payment, optional LLM.
- **Temporary processing state** — processing stages ×4, in-flight
  conversations, scan buffers, generation previews, route extras, filters.
- **Derived/AI values** — scores, insights, DNA view, match details: recompute,
  cache, never truth.
- **Dead models** — `AnalysisResult`/`OnboardingResult`; cleanup is an
  `ARCHITECTURE_GAP_REPORT.md` M2.3 decision, opportunistically done with each
  migration.

**Boundary rules** (`DOMAIN_MODEL_RULES.md` §3): value objects embedded,
entities referenced; knowledge referenced by id never copied per user; AI
output linked not owned; history append-only; derived values recomputed.

---

## 17. P0 / P1 / P2 / P3 entity mapping

Grounded in `MVP_SCOPE.md`. **Nothing is built by this step; this scopes Step 4
table design.**

| Priority | Entities to model | Scope notes |
| --- | --- | --- |
| **P0** | `User`, `WardrobeItem`, `SavedLook` (reference + title), `LearningSignal`, `Look` (P0 vocab only) | The vertical slice "sign in → my wardrobe → my assistant". Requires `User` for user_id FK (AU11.1, AZ12.3). `UserModel` blob split (`POST /users/me/sync`). |
| **P1** | `UserEvent`, `SavedLook` (full snapshot payload), `StyleScoreRecord`, `ActivityDay`, `StyleProfile` pipeline, `Today'sLookRecord` (decision), feedback signal | Completes the primary journey; event context carried into generation; score/streak derived rows; `setFace` written from real scans. |
| **P2** | `AnalysisRun`, `Subscription` | Analysis contract + processing; monetization. |
| **P3** | `RecommendationHistory`, real AI analysis runs, per-user capability state, achievements/XP (if ever) | Require capability that does not exist today. |

**MUST NOT be built yet:** real AI models, media/object storage, weather
integration, multi-device, contract versioning, XP/achievements, recommendation
analytics, onboarding face AI (`MVP_SCOPE.md` Part 5).

---

## 18. Open questions carried into Step 4

Resolved at the domain level, storage shape pending Step 4:

1. **`User` fields** — defined by the auth + anonymous→sync design
   (AU11.1/AU11.2), interdependent with `User` (`STEP_2_FINAL_REPORT.md` §14 #5).
2. **`Today'sLookRecord`** — persist per-user daily look history (P1) or keep a
   derived cache?
3. **`RecommendationHistory`** — build the shown/saved trace (P3)?
4. **Conversation retention** — persist assistant conversations or treat as
   transient? Currently undecided; domain default = transient.
5. **Knowledge source shape** — config contract vs versioned catalog store for
   P0 vocab (backend decision, K9.1).
6. **Media privacy policy (MS10.3)** — must be decided before any media
   persistence (before Step 4 media tables).
7. **Feedback design** — the future Recommendation→Feedback loop needs a shape
   decision before Step 4 adds tables.

## Step 4 recommendation (closing)

Proceed to **Step 4 — PostgreSQL schema design** using this document as the
canonical contract, in this order:

1. **Relational rows** for the P0 entities first (`users`, `wardrobe_items`,
   `saved_looks` + snapshot JSONB, `learning_signals`, `looks` catalog), each
   scoped by `user_id` (AZ12.3).
2. **JSONB** for remaining `UserModel` current-state/snapshot payloads
   (style profile, preferences, session-derived flag) — the P7.1 blob split.
3. **Knowledge content** for `Look` + vocabularies (K9.1).
4. **Object storage** behind `MediaRef` (MS10.3 privacy policy first).
5. P1+ entities (`user_events`, `style_score_records`, `activity_days`,
   `analysis_runs`) once their product decisions land.
6. Typed API + error contract (A3.2/A3.3/E13.1) and per-feature repository
   interfaces (R4.2) are designed **against** this model, not before it.

---

## Constraints honored

- No SQL, no migrations, no database tables, no repositories, no FastAPI
  services, no Flutter/UI/routing changes, no dependencies, no code deleted.
- No entity invented beyond STEP 2 evidence; every canonical entity and
  relationship traces to an inventory reference and to real source.
- The real Fansivibe repository is the source of truth; the separate reference
  project was not merged or used.
- Honest AI status maintained: no capability claimed that does not exist
  (confidence, feedback, capability state, face analysis are all explicitly
  future).
