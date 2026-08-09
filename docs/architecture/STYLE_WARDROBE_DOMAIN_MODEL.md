# Fansivibe — Style & Wardrobe Domain Model

> **STEP 3 (continuation) — DOMAIN MODEL DESIGN.** Defines the domain model for
> Fansivibe's wardrobe and outfit system: what a wardrobe item is, what an
> outfit is (and is not), how looks get saved, recommended, scored, and
> explained, and how feedback flows back into learning — without inventing an
> entity for every shape that appears in the code.
>
> **Source of truth:** the real repository
> (`newproject/flutter_application_1` + `backend/`), the 12 STEP 2 inventory
> documents, and the STEP 3 companions (`DOMAIN_ENTITIES.md`, `DOMAIN_MODEL_RULES.md`,
> `DOMAIN_RELATIONSHIPS.md`, `DOMAIN_STATE_AND_HISTORY.md`, `AI_DOMAIN_MODEL.md`).
>
> **Status:** documentation only. **No SQL, no tables, no repositories, no
> services, no Flutter changes.** This is the conceptual model for the Step 4
> schema and the wardrobe/outfit API contract.

---

## 1. Design principles for this cluster

1. **Not every concept is an entity.** Identity, lifecycle, and durability are
   required; an "outfit" that is regenerated on demand and never stored is a
   **value object**, not an entity (`DOMAIN_ENTITIES.md` four tests).
2. **Avoid duplication.** Fansivibe currently has 4 wardrobe-item shapes, 5
   outfit-piece shapes, 3 insight shapes, 4 occasion vocabularies, and 3 look
   shapes (`DATA_MODEL_INVENTORY.md` §19.1). This model collapses each family to
   **one canonical concept**; duplicates become derived views or knowledge
   references.
3. **Knowledge is referenced, never copied per user.** Clothing categories,
   attributes, and occasions are backend-owned vocabularies; a user item stores
   their **ids**, not duplicated strings (`ARCHITECTURE.md` "Expandable Data").
4. **AI output is never a source of truth.** Recommendations, insights, gaps,
   scores, and match reasons are regenerable; only *user-saved* outcomes
   (`SavedLook` snapshots) and *events* (signals, feedback, runs) are durable
   (`DOMAIN_MODEL_RULES.md` invariant 1).
5. **Current state and history are separate.** The wardrobe is mutable current
   state; its usage is append-only history. Deleting an item never deletes its
   signals (`DOMAIN_STATE_AND_HISTORY.md` §8).

---

## 2. The twelve concepts — verdict

| # | Concept | Verdict | Category (DOMAIN_MODEL_RULES) |
| --- | --- | --- | --- |
| 1 | **Wardrobe** | Not an entity | Current profile state (aggregate *collection* of `WardrobeItem`) |
| 2 | **Wardrobe Item** | **ENTITY** (`WardrobeItem`, E2) | Domain entity (canonical of 4 shapes) |
| 3 | **Clothing Category** | Not an entity | System knowledge (vocabulary) |
| 4 | **Clothing Attribute** | Not an entity | System knowledge (vocabulary) + value references on the item |
| 5 | **Outfit** | Not an entity | Value object (an ordered list of outfit pieces) |
| 6 | **Outfit Item** | Not an entity | Value object (canonical outfit-piece; 5 shapes → 1) |
| 7 | **Saved Look** | **ENTITY** (`SavedLook`, E4) | Domain entity (user-owned; snapshot payload) |
| 8 | **Outfit Recommendation** | Not an entity | AI output (value object) |
| 9 | **Outfit Feedback** | Future historical record | Historical record (mirrors `Recommendation Feedback`, `AI_DOMAIN_MODEL.md` §4.5) |
| 10 | **Wardrobe Insight** | Not an entity | AI output (value object) |
| 11 | **Wardrobe Gap** | Not an entity | Derived data (a *typed* Wardrobe Insight — no separate concept) |
| 12 | **Outfit Occasion** | Not an entity | System knowledge (vocabulary) |

**Only three true entities in this cluster: `WardrobeItem`, `SavedLook`, and the
knowledge entity `Look`.** Everything else is a value object, a vocabulary, a
derived view, or a historical record.

---

## 3. The concepts in detail

### 3.1 Wardrobe

- **Verdict:** not an entity — the aggregate **collection** of `WardrobeItem`
  entities, owned 1:1 by `User` (composition, `DOMAIN_RELATIONSHIPS.md` R16/R17).
- **Ownership:** user-owned; the container exists with the user and may be empty
  (seeded with `defaultWardrobe` on first run — `STORAGE_INVENTORY.md` §1.7).
- **Lifecycle:** created-with/deleted-with `User`.
- **Current vs historical:** current state. The *usage* of the wardrobe over
  time is historical — `LearningSignal` (`item_added`, `style_updated`) and
  `AnalysisRun`/`StyleScoreRecord`/`ActivityDay` derivations
  (`DOMAIN_STATE_AND_HISTORY.md` §5.9).
- **Avoid duplication:** `WardrobeContext` (aggregated stats) is a **derived
  view** over the collection (`matchingItems`, `totalItems`), not a separate
  concept (`DATA_OWNERSHIP.md` §Home).

### 3.2 Wardrobe Item

- **Verdict:** **ENTITY** (E2) — the canonical resolution of the 4 shapes:
  `WardrobeEntry` (`learning/data/models.dart:4`), `WardrobeItemData`
  (`wardrobe_mock_data.dart:17`), backend `WardrobeItem` (assistant DTO), and the
  discover substitute `WardrobeItem` (`discover_mock_data.dart:987`).
- **Ownership:** user-owned; created by the Add Item flow
  (`wardrobe_screen.dart:301` → `LearningService.addItem`).
- **Fields:** stable `id`; `name`; `category` → **Clothing Category** id;
  `color`/`material` → **Clothing Attribute** ids; `isFavorite`; optional
  `MediaRef` to a user-captured photo (object storage — `STORAGE_INVENTORY.md`
  §1.4). No image bytes in the row.
- **Lifecycle:** create → mutate (favorite toggle today; edit/delete are stubs —
  `UI_UX_GAP_REPORT.md` #4) → delete by user (cascades its media).
- **Current vs historical:** current state (mutable). Each change emits
  append-only signals (`item_added`), which are history.
- **AI-generated vs user-created:** **user-created.** Future image tags could be
  AI content, but the item itself is the user's input.
- **AI-generated?** no.

### 3.3 Clothing Category

- **Verdict:** system knowledge **vocabulary**, not an entity. `WardrobeCategory`
  (`wardrobe_mock_data.dart:2`, a UI chip with `itemCount`), `AddItemCategoryConfig`
  (add-item form), and backend `WARDROBE` categories are **three views of one
  canonical category list** (`DATA_MODEL_INVENTORY.md` §19.1).
- **Ownership:** system-owned, content-managed, shared by all users.
- **Relationships:** referenced by id from `WardrobeItem.category` (R18) and from
  outfit-piece `category`; read by filters. Knowledge never references users.
- **Avoid duplication:** one canonical list; `itemCount` on the UI chip is a
  **derived** count, not a stored field.

### 3.4 Clothing Attribute

- **Verdict:** system knowledge **vocabularies** (color, material/texture, fit)
  + **value references** on the item. `ColorOption`/`TextureOption`
  (`wardrobe_mock_data.dart:327/335`), `AddItemConfig`, and the discover/builder
  fit lists are views over the same attribute vocabularies.
- **Ownership:** system-owned vocabularies; the *chosen values* live on the user
  item as ids (`WardrobeItem.color`, `.material`, piece `.fit`).
- **Relationships:** N:1 from `WardrobeItem` and outfit pieces to each attribute
  vocabulary (R18).
- **Avoid duplication:** attributes are **not** per-item free text; they are ids
  into vocabularies. `colorHex` on an outfit piece is a presentation value, not
  domain data.

### 3.5 Outfit

- **Verdict:** **value object** — an ordered ensemble of outfit pieces
  (`OutfitItem`/pieces), never an entity. It exists only inside three containers:
  - `Look` catalog content (system-authored ensemble, R23),
  - `OutfitRecommendation` (AI-generated ensemble, R22),
  - `SavedLook` snapshot (user-saved ensemble, R31).
- **Ownership:** context-dependent — system knowledge content (in `Look`),
  AI output (in a recommendation), user-owned snapshot (in `SavedLook`). No
  standalone owner, no rows.
- **Lifecycle:** created/regenerated with its container; never independently
  stored, edited, or deleted.
- **Current vs historical:** neither — it is recomputed. A *saved* outfit
  becomes historical via the `SavedLook` snapshot; a *recommended* one via
  `RecommendationHistory` (P3).
- **Why not an entity:** it fails the durability and lifecycle tests — the
  product never refers to "outfit id 5" as a durable fact
  (`DOMAIN_ENTITIES.md` §3.1).

### 3.6 Outfit Item (piece)

- **Verdict:** **value object** — the canonical outfit-piece collapsing the 5
  duplicate shapes: `OutfitItemData` (`home_mock_data.dart:103`),
  `DailyOutfitComponent` (`daily_outfit_mock_data.dart:195`), `EnsembleComponent`
  (`discover_mock_data.dart:955`), `OutfitComponent`
  (`outfit_builder_mock_data.dart:158`), `DetectedClothingItem`
  (`outfit_scan_mock_data.dart:2`).
- **Fields (canonical):** category id; name; color id; material id; optional fit;
  optional image ref; `isOwned` (**derived** — from the user's wardrobe, used on
  discover ensembles).
- **Ownership:** embedded; the owning container determines provenance.
- **Lifecycle:** regenerated with the outfit; immutable as a value.
- **Avoid duplication:** the piece carries *references* to knowledge (category/
  color/material ids), never duplicated vocabulary strings.

### 3.7 Saved Look

- **Verdict:** **ENTITY** (E4). The user's durable record of choosing to keep a
  look/outfit, with a snapshot of what was saved.
- **Ownership:** user-owned; persisted truth in `features/learning` (today only
  a title in `UserModel.savedLooks: List<String>`; the Saved Looks screen reads
  a mock instead — `UI_UX_GAP_REPORT.md` #7).
- **Fields:** stable id; optional reference to `Look` (catalog) and/or
  `AnalysisRun` (when saved from a scan); saved-at timestamp; **snapshot
  payload** (pieces + score + reasons at save time — R31).
- **Lifecycle:** created from the 4 save paths (Daily Outfit
  `daily_outfit_screen.dart:1172`, Look Details `look_details_screen.dart:327`,
  Outfit Analysis `outfit_analysis_screen.dart:260`, future Builder/Hairstyle/
  Grooming saves); removed by the user (no UI today); snapshot immutable once
  written.
- **Current vs historical:** both — the *list* is current state (mutable); each
  *save* is a dated event with an immutable snapshot, and a `look_saved` signal
  traces it (`DOMAIN_STATE_AND_HISTORY.md` §5.10, R33).
- **AI-generated vs user-created:** **user-created** (the user chooses to save);
  the referenced content (ensemble, score, reasons) is knowledge/AI and is
  *copied into the snapshot* so later catalog/wardrobe edits can't rewrite what
  was saved (R31).
- **Relationship to Outfit:** the saved outfit is the snapshot payload; the
  `SavedLook` entity is the durable anchor. Do not add a separate "saved outfit"
  concept.

### 3.8 Outfit Recommendation

- **Verdict:** **AI output** value object. `OutfitRecommendation`
  (`outfit_builder_mock_data.dart:179`): `title`, `matchScore` (static constant),
  `components[]`, `reasons[]`, metrics (`colorHarmony`, `bodyFit`,
  `occasionMatch`, `styleScoreImpact`, `improvementSuggestion`), and the selected
  occasion/mood/color palette.
- **Ownership:** AI-output (or the future rules/generation engine); never
  user-authored. Regenerable from decision context (wardrobe + profile +
  preferences) + knowledge (`Look`, occasion) — R21/R24.
- **Lifecycle:** produced on demand; persists only when the user saves it
  (`SavedLook` snapshot) or when history records it (`RecommendationHistory`,
  P3 — `STORAGE_INVENTORY.md` §1.7).
- **Current vs historical:** neither by itself. **AI-generated:** yes — the
  whole payload (title, score, components, reasons, metrics) is generated.
- **Avoid duplication:** the recommendation *reuses* the `Look`/outfit-piece
  value objects and the occasion vocabulary; it does not carry duplicate
  catalogs.
- **Feedback link:** see 3.9.

### 3.9 Outfit Feedback

- **Verdict:** **future historical record.** A user's reaction to an outfit /
  recommendation (rating, like/dislike, useful) — the wardrobe flavor of the
  general **Recommendation Feedback** concept (`AI_DOMAIN_MODEL.md` §4.5,
  R-A13/R-A14). **One concept, modeled once** — no separate "outfit feedback"
  entity beyond the general one.
- **Ownership:** user-owned (the event); append-only, immutable.
- **Status:** **feature does not exist today** — no rating/feedback UI anywhere
  (verified; `UI_UX_GAP_REPORT.md` #17). "Save Outfit" is a SnackBar stub
  (`AI_DATA_FLOW.md` B2).
- **Lifecycle (future):** created per user rating, linked to the recommendation
  (or its `SavedLook`/`AnalysisRun`); never edited; feeds `LearningSignal` and
  the derived preference state.
- **AI-generated vs user-created:** **user-created** (feedback is the user's
  explicit reaction — the *only* user-authored item in the recommendation
  cluster).

### 3.10 Wardrobe Insight

- **Verdict:** **AI output** value object. `WardrobeInsightData`
  (`wardrobe_mock_data.dart:36`), `AIWardrobeInsightData`, `AiInsightData`, and
  the backend `WARDROBE_INSIGHT` catalog are **three shapes of one concept**
  (`AI_DATA_FLOW.md` B6/B7).
- **Ownership:** AI-generated (derived from wardrobe + knowledge); cache only —
  never stored as truth (`DATA_OWNERSHIP.md` §Home/§Wardrobe).
- **Lifecycle:** regenerated when the wardrobe or knowledge changes; a static
  card today (`WardrobeInsightData.mock`).
- **AI-generated vs user-created:** **AI-generated.** When model-produced, the
  insight references its model version for reproducibility
  (`AI_DOMAIN_MODEL.md` R-A18).
- **Avoid duplication:** one insight concept; the three Dart shapes are display
  variants, not three domain concepts.

### 3.11 Wardrobe Gap

- **Verdict:** **derived data** — a **typed Wardrobe Insight**, not a separate
  entity. A gap is a *finding* of the form "you're missing a [category] for
  [occasion/season]; adding it unlocks [N] combinations". Example: the mock
  "consider adding a lightweight jacket to expand spring outfit options by 8+
  combinations" (`wardrobe_mock_data.dart:51`); the assistant's
  `wardrobe_summary` tool expresses the same rule ("consider a lightweight
  jacket").
- **Classification rationale:** a gap has no identity or independent lifecycle —
  it is an insight carrying a *missing-piece reference* + *action label* +
  *impact estimate*. Model it as an insight subtype (an **insight with an action
  target**), not as an entity or its own table.
- **Derived from:** a coverage analysis of the wardrobe (categories/occasions
  present) against a target coverage model (knowledge).
- **AI-generated vs user-created:** **AI-generated/derived**; regenerable.
- **Avoid duplication:** `WardrobeGap` as a standalone concept would duplicate
  `WardrobeInsight`; keep one insight concept with an optional gap payload.

### 3.12 Outfit Occasion

- **Verdict:** system knowledge **vocabulary**, not an entity. The **4
  overlapping occasion vocabularies** (`DATA_MODEL_INVENTORY.md` §19.1) —
  `EventType` ids (`events`), builder/assistant `occasionOptions`, discover
  `OccasionFilters`, backend `OCCASIONS` — resolve to **one canonical
  vocabulary** referenced by id.
- **Ownership:** system-owned, backend-controlled
  (`ARCHITECTURE_GAP_REPORT.md` K9.1).
- **Referenced from:** `UserEvent` (type), `Look` (occasion tags, R28), outfit
  recommendations (`selectedOccasion`), discover filters, assistant replies.
- **Lifecycle:** content-managed/versioned; never user-tied.
- **Avoid duplication:** this one vocabulary replaces the 4 copies; per-user
  occasion *preferences* (`preferredOccasions`) reference its ids and are a
  separate derived preference state.

---

## 4. Relationships

Legend (from `DOMAIN_RELATIONSHIPS.md`): **COMPOSITION / REFERENCE /
DERIVED_FROM / GENERATED_FROM / FEEDS / GATES** × 1:1 / 1:N / N:M.
`(future)`/`(P3)` = prospective. Cross-references to the master tables.

| # | Concept A | Relationship | Concept B | Cardinality | Note |
| --- | --- | --- | --- | --- | --- |
| W1 | `User` | COMPOSITION | Wardrobe (collection) | 1:1 | container; may be empty; = R16 |
| W2 | Wardrobe | COMPOSITION | `WardrobeItem` | 1:N (0..N) | = R17 |
| W3 | `WardrobeItem` | REFERENCE | Clothing Category (vocab) | N:1 | = R18; category id required |
| W4 | `WardrobeItem` | REFERENCE | Clothing Attribute vocabs (color/material/fit) | N:1 each | = R18; color required, material optional |
| W5 | `WardrobeItem` | REFERENCE | `MediaRef` (photo) | 0..1:1 | object storage; = R19 |
| W6 | `WardrobeItem` | FEEDS | `LearningSignal` (`item_added`, …) | 1:N | append-only history |
| W7 | `WardrobeItem` | FEEDS | AI Decision Context / `AssistantUserContext` | N:1 | snapshot per request; = R20 |
| W8 | `WardrobeItem` + knowledge | DERIVED_FROM | `WardrobeContext` (stats) | N:1 | derived view, never stored |
| W9 | `Look` (catalog) | COMPOSITION | Outfit (value) / Outfit Item | 1:1..N | = R23; system content |
| W10 | `UserEvent` | REFERENCE | Outfit Occasion vocab | N:1 | = R34; `EventType` id |
| W11 | `UserEvent` | GENERATED_FROM | OutfitRecommendation | 1:N | event seeds the occasion; = R35 |
| W12 | OutfitRecommendation | DERIVED_FROM | AI Decision Context + `Look` + wardrobe + Outfit Occasion | 1:1 | regenerable; = R24 |
| W13 | OutfitRecommendation | COMPOSITION | Outfit Item + reasons + score (values) | 1:1..N | = R22, R26 |
| W14 | OutfitRecommendation | recorded → (P3) | `RecommendationHistory` | 1:0..1 | shown occurrence; `STORAGE_INVENTORY.md` §1.7 |
| W15 | OutfitRecommendation / `SavedLook` | COMPOSITION (future) | Outfit Feedback | 1:0..N | = Recommendation Feedback; R-A13 |
| W16 | Outfit Feedback (future) | FEEDS | `LearningSignal` + derived preference state | 1:N | the learning loop; R-A14/R-A15 |
| W17 | `SavedLook` | REFERENCE | `Look` | 0..1:1 | catalog ref; = R30 |
| W18 | `SavedLook` | REFERENCE | `AnalysisRun` | 0..1:1 | when saved from a scan; = R32 |
| W19 | `SavedLook` | COMPOSITION | snapshot value objects (pieces/score/reasons) | 0..N:1 | immutable at save time; = R31 |
| W20 | `SavedLook` | FEEDS → DERIVED_FROM | `StyleScoreRecord` + `ActivityDay` | N:1 | via `look_saved` + formula; = R33 |
| W21 | `Look` | REFERENCE | Outfit Occasion vocab | N:M | occasion tags; = R28 |
| W22 | Wardrobe + knowledge | DERIVED_FROM | Wardrobe Insight | N:1 | regenerable; cache only |
| W23 | Wardrobe Insight | DERIVED_FROM | Wardrobe Gap (typed finding) | 1:0..1 | gap = insight + missing-piece payload |
| W24 | Wardrobe Insight | REFERENCE | AI Model Version | 0..1:1 | when model-produced |
| W25 | Outfit Recommendation | REFERENCE | AI Model Version | 0..1:1 | reproducibility trace |

### Relationship rules (cluster-specific)

1. **One entity per durable truth:** the only durable objects are `User` +
   `WardrobeItem` + `SavedLook` (+ knowledge `Look`). Recommendations, outfits,
   pieces, insights, gaps, and contexts are values attached to those anchors.
2. **Values travel with their container:** the same outfit-piece value object
   appears in `Look`, in a recommendation, and in a saved snapshot — never in a
   standalone "outfit" table.
3. **Knowledge is id-referenced:** items and pieces store category/attribute/
   occasion ids, never duplicated strings (W3/W4/W10/W21).
4. **AI outputs are linked to inputs, not owned:** recommendations and insights
   point at the decision context + knowledge that produced them; they are
   regenerable (W12/W22).
5. **The feedback loop is a feed, not a state:** feedback and signals are
   append-only and aggregate into a derived preference state that seeds the next
   recommendation (W15/W16/W7).

---

## 5. Current vs historical state

| Concept | Current state? | Historical? | Notes |
| --- | --- | --- | --- |
| Wardrobe (collection) | **Yes** (mutable) | No | only its *usage* is history |
| `WardrobeItem` | **Yes** (mutable) | No | `item_added` signals are the history |
| Clothing Category / Attribute / Occasion | No | No | system content, versioned |
| Outfit / Outfit Item (values) | No | No | recomputed with container |
| `SavedLook` | **Yes** (list, mutable) | **Yes** (save event + immutable snapshot) | dual nature (§3.7) |
| OutfitRecommendation | No | Only via `RecommendationHistory` (P3) | regenerable |
| Outfit Feedback | No | **Yes** (future, append-only) | feature missing |
| Wardrobe Insight / Gap | No | No | regenerable; cache |
| `LearningSignal` (`item_added`, `look_saved`, …) | No | **Yes** (append-only) | the usage history |
| `AnalysisRun` / `StyleScoreRecord` / `ActivityDay` | No | **Yes** | derived-from / produced history |

**Do-not-overwrite rules carried into this cluster** (`DOMAIN_STATE_AND_HISTORY.md`
§8): deleting a wardrobe item or saved look never deletes its signals; a saved
look snapshot never changes when the catalog or wardrobe changes (W19); a new
recommendation never rewrites a previous one (W14).

---

## 6. AI-generated vs user-created

| Concept | User-created | AI-generated / derived | System-authored (knowledge) |
| --- | --- | --- | --- |
| `WardrobeItem` | **Yes** (Add Item) | future image tags | seed `defaultWardrobe` |
| `SavedLook` | **Yes** (save action) | — | — |
| Outfit / Outfit Item | — | match/isOwned scoring | ensemble *content* in `Look` |
| OutfitRecommendation | — | **whole payload** (title/score/pieces/reasons/metrics) | catalog content it references |
| Outfit Feedback | **Yes** (future rating) | — | — |
| Wardrobe Insight / Gap | — | **finding + impact estimate** | target coverage model |
| Clothing Category / Attribute / Occasion | — | — | **whole vocabularies** |
| `LearningSignal` | **Yes** (actions emit) | — | — |

Only two truly user-authored *entities* (`WardrobeItem`, `SavedLook`) plus the
future feedback *events*. Everything else in this cluster is generated output or
system knowledge — which is exactly why the storage split must never persist AI
outputs as truth (`DOMAIN_MODEL_RULES.md` invariant 1).

---

## 7. The wardrobe → outfit → save → feedback → learning flow

```
  USER creates
    ├─ WardrobeItem (Add Item) ───────────────► LearningSignal('item_added')
    └─ UserEvent (Add Event) ──────────────────► LearningSignal('occasion_preferred')

  AI / engine, given AI Decision Context (wardrobe + profile + events)
    │  + Knowledge (Look catalog, occasion vocab, attribute vocabs)
    ▼
  OutfitRecommendation (VALUE)          Wardrobe Insight / Gap (VALUE)
    ├─ pieces (Outfit Item values)          ├─ finding + missing-piece payload
    ├─ reasons (explanation)                └─ actionLabel → route
    └─ score (not confidence today)
    │
    ├─ user saves ──► SavedLook (ENTITY) ──► snapshot (immutable) + 'look_saved'
    │                     └─ refs Look / AnalysisRun
    └─ user reacts (future) ──► Outfit Feedback (HISTORICAL)
                                      │
                                      ▼
                  LearningSignal → derived preference state → next decision context
```

This satisfies the STEP 2 requirement that recommendations and saved looks be
"linked to the catalog look id, not just a title"
(`ACTION_API_INVENTORY.md` #14) and that the learning loop remain traceable.

---

## 8. What was collapsed (duplication removed)

| Duplicate family today | Canonical concept |
| --- | --- |
| `WardrobeEntry` / `WardrobeItemData` / backend `WardrobeItem` / discover `WardrobeItem` (4) | **`WardrobeItem`** (entity) |
| `OutfitItemData` / `DailyOutfitComponent` / `EnsembleComponent` / `OutfitComponent` / `DetectedClothingItem` (5) | **Outfit Item** (value object) |
| `OutfitRecommendation.mock` / `DailyOutfitData.mock` / `DiscoverLookData` / offline `_LookCard` / backend catalog (3–4) | **`Look`** (knowledge content) + **OutfitRecommendation** (AI output) |
| `WardrobeInsightData` / `AIWardrobeInsightData` / `AiInsightData` / backend `WARDROBE_INSIGHT` (3–4) | **Wardrobe Insight** (value object) + optional **Gap** payload |
| `EventType` ids / builder+assistant `occasionOptions` / discover `OccasionFilters` / backend `OCCASIONS` (4) | **Outfit Occasion** (one vocabulary) |
| `WardrobeContext` (derived stats) | **Derived view** over the collection |
| "Saved Outfit" (builder stub) vs `SavedLook` | **`SavedLook`** (snapshot payload) |

---

## 9. Report — what was found & what must be modeled next

### What was found

- **This cluster has exactly three true entities** — `WardrobeItem`,
  `SavedLook`, and the knowledge `Look`. "Outfit", "outfit item", "clothing
  category/attribute", "occasion", "recommendation", "insight", and "gap" are
  all **value objects or vocabularies**; treating each as an entity would
  duplicate storage and contradict the four-test entity definition.
- **Two concepts are explicitly NOT separate things:** **Wardrobe Gap** is a
  typed Wardrobe Insight (derived finding), and **Outfit Feedback** is the
  wardrobe flavor of the general Recommendation Feedback (one future historical
  record, one concept).
- **Ownership is clean:** user-owned = `WardrobeItem` + `SavedLook` + future
  feedback events; AI-generated = recommendations, insights, gaps, scores;
  system-authored = categories, attributes, occasions, `Look` catalog.
- **AI output never becomes truth:** recommendations/insights/gaps are
  regenerable values; only user saves (`SavedLook` snapshot) and events
  (signals, future feedback) are durable — matching the binding invariant and
  the `look_saved`-only trace observed today.

### What must be modeled next (dependency order, none implemented)

1. **Step 4 storage:** rows for `WardrobeItem` + `SavedLook` (+ future feedback/
   history); JSONB for snapshot/insight/recommendation payloads; content stores
   for the category/attribute/occasion vocabularies and `Look` catalog; object
   storage for `MediaRef` photos.
2. **Wardrobe CRUD + saved-look API contract (A3.2/A3.3, P0):** the P0
   endpoints in `MVP_SCOPE.md` Part 1 (wardrobe CRUD, `POST /looks/saved`)
   carrying these entities; saved looks reference catalog ids.
3. **Edit/delete wiring (P1):** the stub edit/delete paths
   (`UI_UX_GAP_REPORT.md` #4/#5) and "Save Outfit" (`#2`) become real repository
   operations over `WardrobeItem`/`SavedLook`.
4. **Feedback feature (P1)** and **`RecommendationHistory` (P3)** design — each
   is the durable record that turns this cluster's feed loop into trainable
   history.
5. **Knowledge rollout (P0–P1):** single backend-owned sources for the
   category/attribute/occasion vocabularies and `Look` catalog
   (`ARCHITECTURE_GAP_REPORT.md` K9.1) before screens stop hardcoding them.

---

## Constraints honored

- **No SQL, no tables, no repositories, no services, no Flutter changes.**
- No new dependencies, no code deleted, nothing invented beyond STEP 2 evidence.
- Every verdict and relationship traces to a STEP 2 inventory reference and the
  STEP 3 companions; verified source shapes cited (learning models,
  wardrobe_mock_data, outfit_builder_mock_data, discover_mock_data,
  daily_outfit_mock_data, outfit_scan_mock_data).
- The real Fansivibe repository is the source of truth; the separate reference
  project was not used.
