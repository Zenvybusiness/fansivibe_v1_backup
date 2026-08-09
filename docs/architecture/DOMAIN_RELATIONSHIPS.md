# Fansivibe — Domain Relationships

> **STEP 3 (continuation) — DOMAIN MODEL DESIGN.** Defines the relationships
> between the Fansivibe domain entities identified in `DOMAIN_ENTITIES.md`,
> grounded in the STEP 2 inventory and the real repository
> (`newproject/flutter_application_1` + `backend/`).
>
> For every relationship this document specifies: **Entity A**, **Relationship**
> (type + cardinality), **Entity B**, **Ownership**, **Lifecycle dependency**,
> and **mandatory vs optional**.
>
> **Status:** documentation only. No SQL, no tables, no repositories, no
> services, no Flutter/UI/routing changes, no dependencies, no code deleted.
> This is the relationship *model*, not a schema.
>
> **Entity key** (from `DOMAIN_ENTITIES.md`): **E1** `User` · **E2**
> `WardrobeItem` · **E3** `UserEvent` · **E4** `SavedLook` · **E5** `Look` ·
> **E6** `AnalysisRun` · **E7** `LearningSignal` · **E8** `StyleScoreRecord` ·
> **E9** `ActivityDay` · **E10** `Subscription`. Non-entity concepts that appear
> in relationships are marked **(value)** = value object, **(derived)** =
> derived view, **(collection)** = aggregate collection, **(config)** = system
> knowledge, **(external)** = external data, **(DTO)** = wire shape.

---

## 1. Relationship-type legend

A relationship is described by a **nature** plus a **cardinality**. Nature:

| Type | Meaning |
| --- | --- |
| **ONE_TO_ONE / ONE_TO_MANY / MANY_TO_MANY** | Cardinality qualifier applied with a nature below (composition/reference/derived/generated/feeds). |
| **COMPOSITION** | Whole–part: the child belongs to and cannot exist without the parent; parent lifecycle governs the child (cascade delete). |
| **REFERENCE** | Loose link by stable id; both sides can exist independently; no lifecycle coupling (knowledge refs, cross-cluster links). |
| **DERIVED_FROM** | The target is computed from the source(s); not independently created; recomputable. |
| **GENERATED_FROM** | The target is produced by a generation/analysis/AI step from the inputs; exists as an output, not as user-authored data. |
| **FEEDS** | The source contributes state/data to the target over time (signals → score, saves → streak, events → preferences). |
| **PRODUCES** | A process/entity produces another (scan → analysis, analysis → profile attributes). |

Values used with natures: **1:1**, **1:N**, **N:M**. A relationship may combine
(e.g. "1:N, COMPOSITION", "1:1, DERIVED_FROM").

### Attribute conventions

- **Ownership** — who owns the relationship side: `User-owned` / `System-owned`
  / `Derived` / `External` / `AI-output`. Mirrors `DATA_OWNERSHIP.md`.
- **Lifecycle dependency** — how the target's lifecycle depends on the source:
  *created-with / deleted-with* (composition), *independent* (reference),
  *recomputed* (derived), *appended* (history), *produced-on-demand*
  (generated), *accumulates* (feeds).
- **Mandatory / optional** — mandatory = always present for a valid domain
  state; optional = may be absent. Empty content (e.g. a profile with no face
  attributes) is still a valid mandatory container relationship.

---

## 2. Conceptual graph

```
                        ┌────────────────────────── SYSTEM ──────────────────────────┐
                        │  (config) EventType   (config) Category/Color   (config)    │
                        │  occasion/style vocab · plans · capabilities · options      │
                        └──────────▲─────────────────────────▲───────────────────────┘
                                   │ REFERENCE              │ REFERENCE
   ┌───────────────────────────────┼─────────────────────────┼────────────────────────────┐
   │  USER-OWNED AGGREGATE (root = E1 User)                    │                            │
   │                                                           │                            │
   │  E1 User ──1:1 COMPOSITION──► StyleProfile ──1:1 COMP──► FaceProfile (value)          │
   │     │        (current profile state)       ◄──PRODUCES── E6 AnalysisRun (face scan)  │
   │     │─1:1 COMPOSITION──► UserPreferences (choices)                                     │
   │     │─1:N COMPOSITION──► E2 WardrobeItem ──REF──► category/color vocab                 │
   │     │      ◄─1:1 REF──► MediaRef (value) ──► (external) object storage                 │
   │     │─1:N COMPOSITION──► E3 UserEvent ──REF──► EventType (config)                     │
   │     │─1:N COMPOSITION──► E4 SavedLook ──REF──► E5 Look (catalog) ──COMP──► OutfitItem │
   │     │      │                └──1:N COMP──► snapshot (value: items, score, reasons)     │
   │     │      │                └──REF──► E6 AnalysisRun (when saved from a scan)          │
   │     │─1:N COMPOSITION──► E6 AnalysisRun ──1:1 COMP──► AnalysisResult (value, AI)       │
   │     │      └──1:1 REF──► MediaRef (source image)                                       │
   │     │─1:N COMPOSITION──► E7 LearningSignal (append-only)                               │
   │     │─1:N DERIVED──► E8 StyleScoreRecord   ◄──FEEDS── E7/E2/E4                          │
   │     │─1:N DERIVED──► E9 ActivityDay        ◄──FEEDS── E7/E4                            │
   │     │─0..1 REF──► E10 Subscription ──REF──► plan (config) ──► (external) entitlement   │
   │     │─1:N GENERATED──► OutfitRecommendation (AI) ──1:N COMP──► OutfitItem/Reason (val) │
   │     │                      ◄─GENERATED_FROM── UserPreferences + Wardrobe + Look        │
   │     │─DERIVED──► CapabilityAvailability (from config + E10)                            │
   └─────┴──────────────────────────────────────────────────────────────────────────────┘
                                 ▲ DERIVED (DTO snapshot)
                    AssistantUserContext (DTO) ──► assistant ──► AssistantReply (AI, FEEDS E7)
                    Today'sLook (derived) ◄──DERIVED_FROM── StyleProfile+Wardrobe+UserEvent+Weather
```

---

## 3. Master relationship table

| # | Entity A | Relationship | Entity B | Cardinality | Ownership | Lifecycle dependency | Mandatory / Optional |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **User root** |
| R1 | `User` | ONE_TO_ONE, COMPOSITION | StyleProfile (current profile state) | 1:1 | User-owned | created-with; deleted-with | Mandatory (container; contents optional) |
| R2 | `User` | ONE_TO_ONE, COMPOSITION | UserPreferences (preference set) | 1:1 | User-owned | created-with; deleted-with | Mandatory (container; contents optional) |
| R3 | `User` | ONE_TO_MANY, COMPOSITION | `WardrobeItem` | 1:N (0..N) | User-owned | created-by-user; deleted-with-user (cascade) | Optional |
| R4 | `User` | ONE_TO_MANY, COMPOSITION | `UserEvent` | 1:N (0..N) | User-owned | created-by-user; deleted-with-user | Optional |
| R5 | `User` | ONE_TO_MANY, COMPOSITION | `SavedLook` | 1:N (0..N) | User-owned | created-by-user; deleted-with-user | Optional |
| R6 | `User` | ONE_TO_MANY, COMPOSITION | `AnalysisRun` | 1:N (0..N) | User-owned | created-by-user; deleted-with-user | Optional |
| R7 | `User` | ONE_TO_MANY, COMPOSITION (append-only) | `LearningSignal` | 1:N (0..N) | User-owned / historical | appended; never deleted (retention rules) | Optional but grows |
| R8 | `User` | ONE_TO_MANY, DERIVED_FROM | `StyleScoreRecord` | 1:N (0..N) | Derived | recomputed/appended over time | Optional |
| R9 | `User` | ONE_TO_MANY, DERIVED_FROM | `ActivityDay` | 1:N (0..N) | Derived | recomputed/appended per styled day | Optional |
| R10 | `User` | ONE_TO_ONE, REFERENCE | `Subscription` | 0..1:1 | User-owned (+ external) | independent; entitlement from external service | Optional |
| R11 | `User` | MANY_TO_MANY, REFERENCE | `Look` | N:M | User-owned side / System-owned side | independent (via `SavedLook`) | Optional |
| R12 | `User` | ONE_TO_MANY, DERIVED_FROM | CapabilityAvailability (derived) | 1:N | Derived (+ config + E10) | recomputed; prospective | Optional (prospective) |
| **Profile cluster** |
| R13 | StyleProfile | ONE_TO_ONE, COMPOSITION | FaceProfile (value) | 1:1 | User-owned; content AI-generated | created-with; replaced whole | Mandatory container; face content optional (never written today) |
| R14 | StyleProfile | ONE_TO_ONE, DERIVED_FROM | StyleDnaView (derived) | 1:1 | Derived | recomputed on demand | Derived (always recomputable) |
| R15 | `AnalysisRun` (face scan) | ONE_TO_ONE, PRODUCES → DERIVED_FROM | StyleProfile.FaceProfile | 1:1 (latest wins) | AI-generated → user-owned | produced per face analysis; latest analysis updates profile | Optional (no face analysis today) |
| **Wardrobe cluster** |
| R16 | `User` | ONE_TO_ONE, COMPOSITION | Wardrobe (collection) | 1:1 | User-owned | created-with; deleted-with | Mandatory (may be empty) |
| R17 | Wardrobe (collection) | ONE_TO_MANY, COMPOSITION | `WardrobeItem` | 1:N (0..N) | User-owned | items owned by collection/user | Optional |
| R18 | `WardrobeItem` | ONE_TO_MANY, REFERENCE | category/color/material vocab (config) | N:1 | System-owned (knowledge) | independent; values reference vocab ids | Mandatory (category, color required) |
| R19 | `WardrobeItem` | ONE_TO_ONE, REFERENCE | MediaRef (value → object storage) | 0..1:1 | User-owned blob (external) | independent blob; deleted with item | Optional (no images today) |
| R20 | `WardrobeItem` | FEEDS | AssistantUserContext (DTO) | N:1 | Derived (DTO) | snapshot per request | Derived |
| **Look / Outfit / Recommendation cluster** |
| R21 | `User` | ONE_TO_MANY, GENERATED_FROM | OutfitRecommendation (AI output) | 1:N (per generate action) | AI-output | produced on demand; not user-authored | Optional |
| R22 | OutfitRecommendation (AI) | ONE_TO_MANY, COMPOSITION | OutfitItem (value) | 1:N (1..N) | AI-output | embedded; regenerated | Mandatory (an outfit has pieces) |
| R23 | `Look` (catalog) | ONE_TO_MANY, COMPOSITION | OutfitItem (value) | 1:N (1..N) | System-owned | embedded content | Mandatory |
| R24 | OutfitRecommendation (AI) | DERIVED_FROM / GENERATED_FROM | UserPreferences + Wardrobe + `Look` | N:1 | AI-output | recomputed from inputs | Generated |
| R25 | `Look` | ONE_TO_ONE, DERIVED_FROM | MatchScore value (personalized) | 1:1 | Derived (AI) | recomputed from wardrobe × catalog | Optional (mock today) |
| R26 | Recommendation (AI) | ONE_TO_MANY, COMPOSITION | Reason (value) | 1:N (1..N) | AI-output | embedded; regenerated | Mandatory |
| R27 | Recommendation (AI) | ONE_TO_MANY, REFERENCE | Feedback (future) | 1:N (0..N) | User-owned | independent; created by user | Optional (feature missing) |
| R28 | `Look` | ONE_TO_MANY, REFERENCE | occasion/style vocab (config) | N:M | System-owned | independent; values reference vocab ids | Mandatory (occasion/tags present) |
| R29 | `Look` | ONE_TO_MANY, REFERENCE | MediaRef (image) | 0..N:1 | System-owned content | independent blobs (catalog assets) | Optional |
| **Saved-look cluster** |
| R30 | `SavedLook` | ONE_TO_ONE, REFERENCE | `Look` | 0..1:1 | User-owned → System-owned | independent; catalog may be deprecated without deleting saves | Optional (catalog ref may be absent) |
| R31 | `SavedLook` | ONE_TO_MANY, COMPOSITION | snapshot value objects (items/score/reasons) | 0..N:1 | User-owned | captured at save time; immutable | Optional (full payload missing today) |
| R32 | `SavedLook` | ONE_TO_ONE, REFERENCE | `AnalysisRun` | 0..1:1 | User-owned | independent; links when saved from a scan | Optional |
| R33 | `SavedLook` | FEEDS → DERIVED_FROM | `StyleScoreRecord` + `ActivityDay` | N:1 | Derived | accumulates over time | Implied (via formula + `look_saved`) |
| **Event cluster** |
| R34 | `UserEvent` | ONE_TO_MANY, REFERENCE | EventType vocab (config) | N:1 | System-owned | independent; values reference vocab ids | Mandatory (type required) |
| R35 | `UserEvent` | ONE_TO_MANY, GENERATED_FROM | OutfitRecommendation (AI) | 1:N | AI-output | produced on demand (event seeds occasion) | Optional (Generate Outfit) |
| R36 | `UserEvent` | FEEDS | PreferredOccasions (preference) | N:1 | User-owned | accumulates on add | Implied (`addPreferredOccasion`) |
| **Scan / analysis cluster** |
| R37 | `AnalysisRun` | ONE_TO_ONE, REFERENCE | MediaRef (source image) | 0..1:1 | User-owned blob (external) | independent blob; retained per policy | Optional (no media today) |
| R38 | `AnalysisRun` | ONE_TO_ONE, COMPOSITION | AnalysisResult (value, AI) | 0..1:1 | AI-output | embedded on completion | Optional (pending/failed run has none) |
| R39 | `AnalysisRun` | ONE_TO_ONE, REFERENCE | `SavedLook` | 0..1:1 | User-owned | independent; links when the look is saved | Optional |
| R40 | `AnalysisRun` | FEEDS | `LearningSignal` | 1:N | Historical | appended (`analysis_updated`) | Implied |
| **History cluster** |
| R41 | `LearningSignal` | FEEDS → DERIVED_FROM | `StyleScoreRecord` | N:1 | Derived | accumulates; records derived | Implied |
| R42 | `LearningSignal` | FEEDS → DERIVED_FROM | `ActivityDay` | N:1 | Derived | accumulates; records derived | Implied |
| R43 | `WardrobeItem` + `SavedLook` | FEEDS → DERIVED_FROM | current `StyleScore` (derived) | N:1 | Derived | recomputed (formula) | Implied |
| **Subscription / capability cluster** |
| R44 | `Subscription` | ONE_TO_ONE, REFERENCE | SubscriptionPlan (config) | 0..1:1 | System-owned | independent (plan catalog) | Mandatory when a subscription exists |
| R45 | `Subscription` | FEEDS → DERIVED_FROM | CapabilityAvailability (derived) | 1:1 | Derived | recomputed on entitlement change | Implied (prospective) |
| R46 | `User` | DERIVED_FROM | Capability config (`allCapabilities`) | N:M | System-owned | static config today | Prospective (no per-user state today) |
| **Assistant / external cluster** |
| R47 | AssistantUserContext (DTO) | DERIVED_FROM | StyleProfile + Wardrobe + SavedLooks + PreferredOccasions | 1:1 | Derived (DTO) | snapshot per request; never stored | Derived |
| R48 | AssistantReply (AI) | GENERATED_FROM | message + context + `Look` knowledge | 1:1 | AI-output | produced per request | Generated |
| R49 | Today'sLook (derived) | DERIVED_FROM | StyleProfile + Wardrobe + `UserEvent` + Weather + `Look` | 1:1 | Derived (AI) | recomputed daily | Derived (mock today) |
| R50 | Weather (external) | DERIVED_FROM (feed) | Today'sLook (derived) | 1:1 | External | cached, short TTL | Optional (fake literal today) |
| R51 | `Subscription` | REFERENCE | external entitlement/payment service | 1:1 | External | independent service call | Mandatory when subscribing |

---

## 4. Detail — the relationships STEP 2 called out specifically

### 4.1 `User` → Profile

- **Type:** ONE_TO_ONE, COMPOSITION · **Cardinality:** 1:1.
- **Ownership:** User-owned. **Lifecycle:** created-with/deleted-with the user.
- **Mandatory?** The profile container is mandatory; its contents (name,
  `StyleProfile`, derived stats) may be empty or mock-backed today
  (`ProfileData.mock` disconnected from `UserModel` — `UI_UX_GAP_REPORT.md` #6).
- **Note:** "Profile" is the user-facing view of the current profile state
  (identity + `StyleProfile` + preferences + derived aggregates), not a separate
  entity.

### 4.2 `User` → Preferences

- **Type:** ONE_TO_ONE, COMPOSITION · **Cardinality:** 1:1.
- **Ownership:** User-owned. **Lifecycle:** created-with/deleted-with.
- **Mandatory?** Container mandatory; each preference (vibe, builder prefs,
  grooming inputs, settings) optional. Today all are ephemeral widget state
  (`FEATURE_DATA_MATRIX.md` §12; `UI_UX_GAP_REPORT.md` #28).
- **Note:** preferences reference **vocabulary ids** (config), never duplicate
  the vocabulary (`ARCHITECTURE.md` Expandable Data).

### 4.3 `User` → Style Profile

- **Type:** ONE_TO_ONE, COMPOSITION · **Cardinality:** 1:1.
- **Ownership:** User-owned; the face content is AI-generated.
- **Lifecycle:** created-with; `FaceProfile` value replaced whole on analysis.
- **Mandatory?** Container mandatory; `FaceProfile` content optional — and in
  practice **never written today** (`setFace` uncalled — verified in
  `learning_service.dart`).
- **Chain:** `User` → `StyleProfile` → `FaceProfile` (value) ◄— PRODUCES —
  `AnalysisRun` (4.16).

### 4.4 `User` → Scans

- **Type:** ONE_TO_MANY, COMPOSITION · **Cardinality:** 1:N (0..N).
- **Ownership:** User-owned. **Lifecycle:** each scan creates an `AnalysisRun`;
  deleted with the user.
- **Mandatory?** Optional — a user may have no scans.
- **Note:** scans = `AnalysisRun` records (outfit scan, hairstyle face scan,
  grooming). Source media is a `MediaRef` (R37).

### 4.5 Scan → Analysis

- **Type:** ONE_TO_ONE, COMPOSITION · **Cardinality:** 0..1:1.
- **Ownership:** AI-output (result snapshot embedded in the run).
- **Lifecycle:** embedded on completion; absent while pending/failed
  (`STATE_EDGE_CASE_INVENTORY.md` — today processing is a fixed timer over
  mocks).
- **Mandatory?** Optional — a run may have no completed result.
- **Note:** the scan is the *input evidence*, the analysis the *output
  snapshot*; STEP 2 requires the link ("result linked to source image + scan
  run" — `STORAGE_INVENTORY.md` §1.6).

### 4.6 Analysis → Profile

- **Type:** PRODUCES → DERIVED_FROM · **Cardinality:** 1:1 (latest wins).
- **Ownership:** AI-generated content → user-owned profile state.
- **Lifecycle:** a successful face analysis produces `FaceProfile` attributes
  that update `StyleProfile`; the analysis may also record `analysis_updated`
  and feed a saved look (R39).
- **Mandatory?** Optional — the pipeline is dead today (no `setFace` caller,
  `AI_DATA_FLOW.md` Part D.6).

### 4.7 `User` → Wardrobe

- **Type:** ONE_TO_ONE, COMPOSITION · **Cardinality:** 1:1.
- **Ownership:** User-owned. **Lifecycle:** created-with/deleted-with.
- **Mandatory?** Mandatory container (may be empty; seeded with
  `defaultWardrobe` on first run).
- **Note:** the Wardrobe is the aggregate *collection* of `WardrobeItem`
  entities — the grouping is derived, not a separate entity.

### 4.8 Wardrobe → Wardrobe Item

- **Type:** ONE_TO_MANY, COMPOSITION · **Cardinality:** 1:N (0..N).
- **Ownership:** User-owned. **Lifecycle:** items created by the Add Item flow,
  deleted with the wardrobe/user (cascade images per `STORAGE_INVENTORY.md`
  §1.4).
- **Mandatory?** Optional (0..N items).

### 4.9 `User` → Outfits

- **Type:** no standalone `Outfit` entity — resolved into three relationships:
  - `User` → `SavedLook` (saved outfits): ONE_TO_MANY, COMPOSITION, optional.
  - `User` → OutfitRecommendation (generated): ONE_TO_MANY, GENERATED_FROM,
    optional, AI-output (`MVP_SCOPE.md` P2 — builder generation is rules-based
    future work).
  - `User` ↔ `Look` (catalog): MANY_TO_MANY, REFERENCE via `SavedLook`, optional.
- **Ownership:** mixed (user-owned saves; AI-output generations; system-owned
  catalog). **Lifecycle:** none durable today — "Save Outfit" is a SnackBar
  stub (`UI_UX_GAP_REPORT.md` #2) and builder results are mock.
- **Note:** the outfit itself is a **value object** (a list of `OutfitItem`),
  not an entity (`DOMAIN_ENTITIES.md` §3.1).

### 4.10 Outfit → Outfit Items

- **Type:** ONE_TO_MANY, COMPOSITION · **Cardinality:** 1:N (1..N).
- **Ownership:** System-owned (for `Look` content, R23) / AI-output (for
  recommendations, R22).
- **Lifecycle:** embedded; regenerated with the outfit.
- **Mandatory?** Mandatory — an outfit without pieces is not an outfit.
- **Note:** this is the canonical outfit-piece relationship resolving the 5
  duplicate piece shapes (`DATA_MODEL_INVENTORY.md` §19.1).

### 4.11 Recommendation → Reasons

- **Type:** ONE_TO_MANY, COMPOSITION · **Cardinality:** 1:N (1..N).
- **Ownership:** AI-output (value objects). **Lifecycle:** embedded; regenerated.
- **Mandatory?** Mandatory — recommendations are explained by reasons
  (PRODUCT_BLUEPRINT: "explainable"; assistant reply text already explains).
- **Note:** `RecommendationReason`/`reasons[]` are the only structure today;
  a dedicated explanation field is a FUTURE contract change (`AI_DATA_FLOW.md`
  Part D.4).

### 4.12 Recommendation → Feedback

- **Type:** ONE_TO_MANY, REFERENCE · **Cardinality:** 1:N (0..N).
- **Ownership:** User-owned (feedback submitted by the user).
- **Lifecycle:** independent; created per user rating.
- **Mandatory?** Optional — **the feature does not exist today** (verified: no
  rating/feedback UI anywhere; `UI_UX_GAP_REPORT.md` #17; `ACTION_API_INVENTORY.md`
  #31). The relationship is a future requirement, not observed behavior.
- **Note:** feedback would link a recommendation (or its source `Look`/
  `AnalysisRun`) back into learning — the missing explicit learning signal.

### 4.13 `User` → Saved Looks

- **Type:** ONE_TO_MANY, COMPOSITION · **Cardinality:** 1:N (0..N).
- **Ownership:** User-owned (persisted truth in `features/learning`).
- **Lifecycle:** created from 4 save paths (Daily Outfit :1172, Look Details
  :327, Outfit Analysis :260, future Builder/Hairstyle/Grooming); deleted by the
  user (no UI today).
- **Mandatory?** Optional.
- **Note:** `SavedLook` is the aggregate; its display shapes
  (`SavedLookPreview`/`SavedLookDetail`) are derived views (`DOMAIN_ENTITIES.md`
  §3.7).

### 4.14 `User` → Events

- **Type:** ONE_TO_MANY, COMPOSITION · **Cardinality:** 1:N (0..N).
- **Ownership:** User-owned. **Lifecycle:** created by the Add Event form;
  edit/delete are stubs today; deleted with the user.
- **Mandatory?** Optional.
- **Note:** events also FEED `PreferredOccasions` (R36) and seed outfit
  generation (R35) — the entity-and-trigger duality resolved in
  `DOMAIN_MODEL_RULES.md` §6.4.

### 4.15 `User` → AI Capabilities

- **Type:** DERIVED_FROM (availability view), conceptual MANY_TO_MANY through
  the capability config · **Cardinality:** 1:N.
- **Ownership:** System-owned config (`allCapabilities`) + derived per-user
  availability.
- **Lifecycle:** recomputed; today static config.
- **Mandatory?** Prospective — **no per-user capability state exists today**
  (`allCapabilities` lists Face/Color Analysis as `active` marketing copy with
  no computation; `AI_DATA_FLOW.md` Part D.1). The user's *effective*
  capabilities derive from config × subscription (R45) once entitlement exists.
- **Note:** `AiCapability`/`allCapabilities` are system knowledge
  (`DOMAIN_ENTITIES.md` #38); do not model per-user capability rows unless a
  real capability system lands (`MVP_SCOPE.md` P3).

### 4.16 AI Analysis → Current Profile

- **Type:** PRODUCES → DERIVED_FROM · **Cardinality:** 1:1 (latest wins).
- **Ownership:** AI-generated content → user-owned current profile state.
- **Lifecycle:** face analysis produces `FaceProfile` attributes updating
  `StyleProfile` (R15); outfit/other analyses feed `AnalysisResult` snapshots,
  saved looks, and `analysis_updated` signals — never the source of truth
  (`DATA_OWNERSHIP.md` rule 3).
- **Mandatory?** Optional; the pipeline is dead in practice today
  (`FaceProfile` never written).

---

## 5. Lifecycle-dependency rules

1. **Composition cascades from `User`:** every user-owned child
   (`StyleProfile`, `UserPreferences`, `WardrobeItem`, `UserEvent`,
   `SavedLook`, `AnalysisRun`, `LearningSignal`, `StyleScoreRecord`,
   `ActivityDay`) is created with and deleted with the user
   (`STORAGE_INVENTORY.md` retention principle — user blobs follow user
   lifecycle).
2. **References never couple lifecycles:** knowledge refs (`Look`, vocab,
   `SubscriptionPlan`) and cross-links (`SavedLook`→`Look`,
   `SavedLook`→`AnalysisRun`) remain valid when the referenced side changes or
   is deprecated; a saved look survives catalog edits.
3. **Derived is recomputed, never stored as truth:** `StyleScore`,
   `StyleScoreRecord`, `ActivityDay`, style-DNA view, match scores,
   `Today'sLook`, capability availability — all regenerate from durable inputs
   (`DATA_OWNERSHIP.md` rules 3 and 5).
4. **Generated is produced on demand:** recommendations and analysis results
   exist only as outputs; they persist only when the user saves them
   (`SavedLook` snapshot / `AnalysisRun` retention).
5. **Historical is append-only:** `LearningSignal`, `StyleScoreRecord`,
   `ActivityDay`, `AnalysisRun` never mutate after creation; retention/soft-
   delete rules apply (`DATA_OWNERSHIP.md` deletion matrix).
6. **Media is referenced, not embedded:** `MediaRef` value objects point at
   object storage; blob lifecycle follows the referencing entity (deleted with
   item/saved-look, or auto-expired per policy — `STORAGE_INVENTORY.md` §1.2/1.3).
7. **Vocabularies are one-way referenced:** entities point at knowledge ids;
   knowledge never references user entities (system content is user-agnostic).

---

## 6. Report — what was found & what must be modeled next

### What was found

- **~50 relationships** across the domain, dominated by **composition from the
  `User` root** (10 user-owned children), **references to knowledge**
  (vocabularies, `Look`, plans), **derived/generated AI relationships**, and
  **feeds** into the historical/score cluster.
- **The 16 specifically-called-out pairs all resolve cleanly** against the real
  product — with three honest corrections:
  - **User → Outfits** has no `Outfit` entity; it decomposes into `SavedLook`
    (saves), OutfitRecommendation (generated, AI-output), and `Look` (catalog).
  - **Recommendation → Feedback** is a *future* relationship (feature missing).
  - **User → AI Capabilities** is prospective — no per-user capability state
    exists today; availability is a derived view over config × subscription.
- **Cardinality summary:** all user-owned children are 1:N or 1:1 composition;
  the only true N:M is `User`↔`Look` (via `SavedLook`). Mandatory relationships
  are the container/composition and the vocab-ref/outfit-pieces cases;
  everything content-level is optional because today it is mock or unwritten.

### What must be modeled next (dependency order, none implemented)

1. **Storage split (Step 4):** map the composition relationships to rows/FKs,
   the references to id columns, the derived views to queries/JSONB, and
   `MediaRef` to object-storage URLs — per `STORAGE_INVENTORY.md` Part 2.
2. **Typed API + error contract (A3.2/A3.3):** each relationship that crosses a
   boundary (wardrobe, events, saved looks, analysis, generation, assistant
   context) becomes request/response shapes; the P0 endpoints in
   `MVP_SCOPE.md` Part 1 come first.
3. **Auth + anonymous→sync (AU11.1/AU11.2):** the `User` root and its
   composition cascade define the account ↔ device merge semantics for
   `POST /users/me/sync`.
4. **Feedback (#27) and capability availability (#45/#46)** are design-input
   only — build them when the product decides the features exist (P1/P3).
5. **Per-feature repository interfaces (R4.2)** over the composition roots
   (`WardrobeItem`, `SavedLook`, `AnalysisRun`, `LearningSignal`).

---

## Constraints honored

- No SQL, no tables, no repositories, no services.
- No Flutter/UI/routing changes, no dependencies, no code deleted.
- Every relationship traces to `DOMAIN_ENTITIES.md` entities and a STEP 2
  inventory reference; no relationship invents a capability the inventory does
  not support.
- The real Fansivibe repository is the source of truth; the separate reference
  project was not used.
