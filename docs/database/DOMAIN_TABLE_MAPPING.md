# Fansivibe — Domain → Database Table Mapping

> **STEP 4 (continuation) — DATABASE DESIGN.** Maps **every domain concept** from
> the finalized Fansivibe domain model to its storage representation in
> PostgreSQL: a table, a value object embedded in a row, a JSONB payload, a
> derived value that is never persisted, or external storage.
>
> This is the concept-level companion to `DATABASE_DESIGN_RULES.md`. The rules
> document states **how** tables are designed (PR-1…PR-12, keys, constraints,
> JSONB policy, media policy); this document states **what** each concept maps
> to, table by table, and **what must never become a table**.
>
> **Sources:** the ten STEP 3 domain documents — `FANSIVIBE_DOMAIN_MODEL_V1.md`
> (canonical), `DOMAIN_ENTITIES.md`, `DOMAIN_RELATIONSHIPS.md`,
> `DOMAIN_STATE_AND_HISTORY.md`, `AI_DOMAIN_MODEL.md`,
> `STYLE_WARDROBE_DOMAIN_MODEL.md`, `APPEARANCE_DOMAIN_MODEL.md`,
> `CONTEXT_DOMAIN_MODEL.md`, `ACCOUNT_ASSISTANT_DOMAIN_MODEL.md`,
> `VALUE_OBJECTS.md` — cross-checked against the real repository
> (`newproject/flutter_application_1` + `backend/`).
>
> **Status: documentation only. No SQL, no migrations, no database, no
> application code changes, no repositories, no endpoints, nothing deleted.**

---

## 1. Purpose and method

For every domain concept this document answers the six determinations the
task requires:

| # | Determination | Meaning | Decision test |
| --- | --- | --- | --- |
| 1 | **Become a table?** | A durable, relational row with identity. | Passes the four entity tests — identity, lifecycle, durability, product behavior (`DOMAIN_ENTITIES.md` §intro) — **and** the fact is queried/joined/counted (`DATABASE_DESIGN_RULES.md` PR-1). |
| 2 | **Become a value object?** | An immutable, no-identity value that travels with an owner. | Fails identity/lifecycle; fully defined by attributes (`VALUE_OBJECTS.md` §1). |
| 3 | **Be embedded?** | The value lives *inside* its owner's row/column, not as its own row. | Value object + the product never refers to it by id. |
| 4 | **Be JSONB?** | Stored as a JSONB document rather than typed columns. | Large/evolving payload read and written as a unit, or an immutable snapshot that is not a query axis (PR-9). |
| 5 | **Be derived, not persisted?** | Recomputed from durable inputs; stored truth would be duplication. | Recomputable from inputs; history need is met by an immutable snapshot (PR-2, PR-7). |
| 6 | **Be stored externally?** | Lives outside PostgreSQL (object storage, external service). | Binary media, third-party-owned data, or boundary processes (PR-8, PR-10). |

**Order of resolution:** a concept is resolved by the first determination that
fits, using the binding domain rules:

1. **AI output is never a source of truth** — recommendations, reasons,
   scores, insights are values; they persist only as snapshots (`SavedLook`
   payload, `AnalysisRun.result`) or not at all.
2. **Current state ≠ history** — mutable projections vs. append-only traces
   are never the same table (`DOMAIN_STATE_AND_HISTORY.md` §8).
3. **Knowledge is referenced, never copied per user** — vocabularies are
   backend-owned reference tables/config; entities hold their **ids**.
4. **Media is referenced, never stored** — `MediaRef` values point at object
   storage.
5. **No speculative tables** — P3-only concepts (capability state,
   recommendation history, achievements) and planned profiles get no table
   until their product decision lands (PR-12).

---

## 2. The decision legend

Used in the master matrix (§3):

| Mark | Meaning |
| --- | --- |
| **TBL** | Becomes a relational table (see §4 for the table). |
| **TBL* (P1/P2/P3)** | Becomes a table at that phase, gated by a product decision or feature existence. |
| **VO** | Value object — embedded in its owner, never its own table. |
| **EMB** | Embedded in the owning row/column. |
| **J** | JSONB column on the owning row (justified in §4 / the rules doc §8). |
| **DER** | Derived — recomputed, cached, never persisted as truth. |
| **EXT** | Stored outside PostgreSQL (object storage / external service). |
| **–** | Not applicable / not a data concept. |

---

## 3. Master mapping matrix

For every domain concept: the six determinations and the resolved storage home.
Rows are grouped by the STEP 3 domain document they come from.

### 3.1 Core entities (`DOMAIN_ENTITIES.md` E1–E10, conditional entities)

| Concept | Table | Value object | Embedded | JSONB | Derived | External | Resolution / home |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `User` (E1) | **TBL** | – | – | – | – | auth identity (provider) | `users` (P0) |
| `UserModel` blob (projection) | – | – | – | J (split) | – | – | split into rows + `user_state` JSONB (PR-2, §7 rules doc) |
| `WardrobeItem` (E2) | **TBL** | – | – | J (image_ref) | – | media | `wardrobe_items` (P0) |
| `UserEvent` (E3) | **TBL** | – | – | – | – | – | `user_events` (P1) |
| `SavedLook` (E4) | **TBL** | – | snapshot payload | J (snapshot) | – | media | `saved_looks` (P0) |
| `Look` (E5) | **TBL** | – | ensemble content | J (payload, image_ref) | – | catalog assets | `looks` (P0) |
| `AnalysisRun` (E6) | **TBL** | – | result snapshot | J (result, input_media) | – | source media | `analysis_runs` (P2) |
| `LearningSignal` (E7) | **TBL** | – | – | J (context, optional) | – | – | `learning_signals` (P0, append-only) |
| `StyleScoreRecord` (E8) | **TBL** | – | breakdown | J (breakdown) | current score = DER | – | `style_score_records` (P1, append-only) |
| `ActivityDay` (E9) | **TBL** | – | – | J (summary, optional) | current streak = DER | – | `activity_days` (P1, append-only) |
| `Subscription` (E10) | **TBL* (P2)** | – | – | – | entitlement = DER | payment | `subscriptions` (P2) |
| `Today'sLookRecord` (conditional) | **TBL* (P1 decision)** | – | – | J (snapshot) | today's look current = DER | – | `today_look_records` only if "what I wore" history is wanted |
| `RecommendationHistory` (conditional) | **TBL* (P3 decision)** | – | – | J (snapshot) | recommendation current = DER | – | `recommendation_history` only if the trace is built |

### 3.2 Appearance cluster (`APPEARANCE_DOMAIN_MODEL.md`)

| Concept | Table | Value object | Embedded | JSONB | Derived | External | Resolution / home |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Style Profile (current profile state) | – | – | EMB | **J** | – | – | `user_state.style_profile` (P0) |
| `FaceProfile` (value) | – | **VO** | EMB | J | – | – | inside `user_state.style_profile`; `setFace` uncalled today |
| Hair Profile (planned) | – | **VO** (planned) | EMB | J (planned) | – | – | **no table** until a hair pipeline + Save Style land (P1) |
| Grooming Profile (planned) | – | **VO** (planned) | EMB | J (planned) | – | – | **no table** until a grooming pipeline lands (P1) |
| Color Profile (planned) | – | **VO** (planned) | EMB | J (planned) | – | – | **no table** until color analysis exists (P1) |
| Style DNA view | – | VO | EMB | – | **DER** | – | recomputed from `FaceProfile`; never stored |
| Appearance Intelligence | – | – | – | – | **DER** (narrative) | – | UI copy only — not a data concept |
| AI Capability Progress | – | – | – | – | **DER** (count) | – | static config; no per-user rows until a P3 capability system |
| Appearance Analysis = `AnalysisRun` | **TBL** | result = VO | result EMB | J (result) | – | source media | `analysis_runs` (P2) |
| Style Score (current) | – | VO | – | – | **DER** | – | computed by formula; cache; history = `style_score_records` |
| Grooming input options | – | VO | EMB (id refs) | – | – | – | `user_state.preferences` id refs → grooming vocab config |

### 3.3 Style / wardrobe cluster (`STYLE_WARDROBE_DOMAIN_MODEL.md`)

| Concept | Table | Value object | Embedded | JSONB | Derived | External | Resolution / home |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Wardrobe (collection) | – | – | – | – | **DER** (grouping) | – | the 1:1 collection of `wardrobe_items`; not a table |
| Clothing Category | – | VO (vocab) | EMB (id) | – | – | – | `wardrobe_categories` reference table/config |
| Clothing Attribute (color/material/fit) | – | VO (vocab) | EMB (ids) | – | – | – | `colors`/`materials` reference tables + id columns on `wardrobe_items` |
| Outfit (ensemble) | – | **VO** | EMB | J | – | – | never a table; lives in `Look` payload, `SavedLook.snapshot`, or a recommendation |
| Outfit Item (piece) | – | **VO** | EMB | J | isOwned = DER | – | inside the outfit value object |
| `SavedLook` (E4) | **TBL** | – | snapshot | J (snapshot) | – | media | `saved_looks` |
| `OutfitRecommendation` | – | **VO** (AI output) | – | – | **DER** (regenerable) | – | never stored as truth; persist only via save/history snapshot |
| Outfit Feedback | **TBL* (P1 feature)** | – | – | – | – | – | `feedback_events` — one concept with Recommendation Feedback |
| Wardrobe Insight | – | **VO** (AI output) | – | – | **DER** | – | cache; regenerated from wardrobe × knowledge |
| Wardrobe Gap | – | **VO** (typed insight) | – | – | **DER** | – | a typed Wardrobe Insight; not a separate concept |
| Outfit Occasion | – | VO (vocab) | EMB (id) | – | – | – | `occasions` reference table/config |
| `WardrobeContext` (stats) | – | VO | – | – | **DER** | – | derived view over `wardrobe_items`; never stored |

### 3.4 Context cluster (`CONTEXT_DOMAIN_MODEL.md`)

| Concept | Table | Value object | Embedded | JSONB | Derived | External | Resolution / home |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `UserEvent` (E3) | **TBL** | – | – | – | – | – | `user_events` (P1) |
| Event Styling | – | – | – | – | **DER** (flow) | – | capability + process, not data |
| Event Type | – | VO (vocab) | EMB (id) | – | – | – | `event_types` reference table/config |
| Daily Outfit / Today's Look | – | VO | EMB | J (snapshot) | **DER** | weather feed | current = cache; history = `today_look_records` (P1 decision) |
| Weather | – | VO | EMB (cache) | – | – | **EXT** (provider + cache) | never a table |
| Discover Content = `Look` (E5) | **TBL** | – | ensemble | J (payload) | – | – | `looks` |
| Saved Discover Content = `SavedLook` (E4) | **TBL** | – | snapshot | J (snapshot) | – | – | `saved_looks` |

### 3.5 AI cluster (`AI_DOMAIN_MODEL.md`)

| Concept | Table | Value object | Embedded | JSONB | Derived | External | Resolution / home |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AI Analysis run = `AnalysisRun` | **TBL** | – | result EMB | J (result) | – | source media | `analysis_runs` |
| AI Analysis result | – | **VO** | EMB | J | – | – | immutable snapshot on `analysis_runs.result` |
| AI Recommendation | – | **VO** | EMB | – | **DER** | – | never a table; occurrence = `recommendation_history` (P3) |
| Recommendation Reason | – | **VO** | EMB | J (snapshot) | – | – | snapshotted into `SavedLook.snapshot`; no structured field today |
| Recommendation Confidence | – | **VO** | EMB | J (snapshot) | **DER** | – | not computed today; snapshot only if history kept |
| Recommendation Feedback | **TBL* (P1 feature)** | – | – | – | – | – | `feedback_events` — append-only user event |
| `RecommendationHistory` | **TBL* (P3 decision)** | – | – | J (snapshot) | – | – | only if the shown/saved trace is built |
| AI Decision Context | – | VO (serialized) | EMB (optional) | – | **DER** (per request) | – | never stored; frozen copy optional in history for reproducibility |
| AI-generated Insight | – | **VO** | – | – | **DER** | – | cache; never truth |
| AI Capability | – | – | – | – | availability = DER | – | system config; no table, no per-user rows |
| AI Model Version | – | – | – | – | – | – | system config; recorded as `engine_version` on `analysis_runs` |
| User Preference Signal = `LearningSignal` | **TBL** | – | – | J (context) | aggregate prefs = DER | – | `learning_signals` |

### 3.6 Value objects & misc (`VALUE_OBJECTS.md`, `DOMAIN_ENTITIES.md` §3)

| Concept | Table | Value object | Embedded | JSONB | Derived | External | Resolution / home |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Color | – | **VO** (vocab ref) | EMB (id) | – | – | – | `colors` reference + `color_id` column |
| Score | – | **VO** | EMB | J (breakdown) | current = DER | – | snapshots as `style_score_records` |
| Confidence | – | **VO** | EMB | J (snapshot) | **DER** | – | not computed today; no column |
| Location | – | **VO** (candidate) | EMB (if used) | – | – | – | **not used today**; no table |
| Money | – | **VO** | EMB | – | – | – | display string in plan config; no money math |
| Date Range | – | **VO** | EMB (columns) | – | – | – | columns on the owning row (event date, subscription period) |
| Style Vibe | – | VO (vocab) | EMB (id) | – | – | – | `styles` reference + `style_type` in profile JSONB |
| Occasion | – | VO (vocab) | EMB (id) | – | – | – | `occasions` reference + id columns |
| Weather Snapshot | – | **VO** | EMB (cache) | – | – | **EXT** | external cache, short TTL |
| AI Reason | – | **VO** | EMB | J (snapshot) | – | – | snapshotted into `SavedLook.snapshot` |
| `MediaRef` | – | **VO** | EMB (columns/JSONB) | J (image_ref) | – | **EXT** (blob) | object storage behind the reference; bytes never in PostgreSQL |
| Assistant DTOs (`AssistantReply`, `AssistantMessage`, `AssistantUserContext`, …) | – | VO / DTO | – | – | context = DER | – | **no tables** — wire contract, KEEP mirrored |
| AI Assistant Conversation | – | – | – | J (only if retained) | – | – | **no table today**; conditional history if retention is decided |
| Assistant Action | – | – | – | – | – | – | system config (16 action ids) + route map; no table |
| Authentication | – | – | – | – | – | **EXT** (provider) | external process; opaque identity ref on `users` |
| Feature Entitlement | – | – | – | – | **DER** | – | config × subscription; no rows until a P3 capability system |
| Subscription Plan | – | VO (config) | – | – | – | – | `subscription_plans` config/reference table |
| `defaultWardrobe` seed | – | VO (config) | – | – | – | – | knowledge seed → `wardrobe_items` rows on first save |
| Achievements / ranks / XP | – | – | – | – | **DER** | – | no table (definitions = config; aggregates derived) |

---

## 4. Proposed tables

Each proposed table with the six required attributes. Phasing (P0/P1/P2/P3)
follows `DATABASE_DESIGN_RULES.md` §14. **No SQL is written here.**

### 4.1 `users` — P0

- **Domain entity:** `User` (E1) — the aggregate root.
- **Purpose:** the account identity that scopes every user-owned row; holds the
  opaque auth reference (provider + subject) and the display name.
- **Ownership:** user (the account itself); created by the future auth/account
  feature (`AU11.1`).
- **Lifecycle:** register → authenticate → update → delete (cascades all
  user-owned children per retention).
- **Persistence reason:** every user-owned entity needs a `user_id` FK; without
  the row no relational write is user-scoped (`AZ12.3`). `users` exists even
  before auth is designed.

### 4.2 `user_state` — P0

- **Domain entity:** current profile state (Style Profile + FaceProfile +
  preferences + flags) — the `UserModel` projection split (P7.1).
- **Purpose:** 1:1 current-state JSONB home for `style_profile` (face
  attributes, `style_type`, `source_run_id` provenance), `preferences`
  (vocabulary-id lists such as `preferred_occasions`), and `flags`
  (`has_saved_wardrobe_item`, F1.4).
- **Ownership:** user; created-with/deleted-with `users`.
- **Lifecycle:** mutated in place as the profile/preferences change; a new
  analysis projects forward, never rewrites history.
- **Persistence reason:** current profile state is read/written as a unit,
  its shape evolves with the AI pipeline, and it must survive restarts and
  sync (JSONB justified per PR-9; it is never a substitute for rows).

### 4.3 `wardrobe_items` — P0

- **Domain entity:** `WardrobeItem` (E2) — canonical of 4 shapes.
- **Purpose:** one owned clothing/accessory per user (name, category/color id,
  optional material id, favorite, optional `MediaRef`).
- **Ownership:** user; created by the Add Item flow
  (`wardrobe_screen.dart:301`).
- **Lifecycle:** create → mutate (favorite today; edit/delete stubs) → delete
  by user (cascades its media).
- **Persistence reason:** wardrobe is queried, counted, and fed to the
  assistant/look scoring — a normalized relational row, not a blob
  (`WARDROBE` collection is the grouping, not a table).

### 4.4 `saved_looks` — P0

- **Domain entity:** `SavedLook` (E4).
- **Purpose:** the user's durable record of keeping a look: optional `look_id`
  (catalog ref), title, immutable snapshot payload (ensemble/score/reasons),
  optional `source_run_id` (when saved from a scan).
- **Ownership:** user; persisted truth in `features/learning`.
- **Lifecycle:** created from the save paths (Daily Outfit, Look Details, Outfit
  Analysis, future Builder/Hairstyle/Grooming); removed by the user; the
  snapshot is immutable once written.
- **Persistence reason:** the *list* is current state and the *save* is a
  dated event with a frozen snapshot — the only durable trace of AI output the
  user kept (`AI-output-never-truth` boundary case).

### 4.5 `learning_signals` — P0

- **Domain entity:** `LearningSignal` (E7) — the feature-usage trace.
- **Purpose:** append-only, typed interaction history (8 signal types) that
  drives learning and feeds derived score/streak records.
- **Ownership:** user; written by `LearningService` + all features + the
  assistant.
- **Lifecycle:** appended on every relevant action; **never updated or
  deleted** (INSERT/SELECT-only grants; soft-delete/retention is the only
  removal path).
- **Persistence reason:** history is the raw evidence for learning; it must
  survive item/event/saved-look deletion, so it carries **no FK to the
  triggering entity**.

### 4.6 `looks` — P0

- **Domain entity:** `Look` (E5) — the only system-owned knowledge entity.
- **Purpose:** the canonical look catalog (title, ensemble payload, image refs,
  occasion/style tags, content version, deprecation) that recommendations,
  discover, and saved looks reference **by id**.
- **Ownership:** system / backend knowledge source (content-managed).
- **Lifecycle:** authored → versioned → deprecated; never user-tied; never
  deleted while referenced (RESTRICT / SET NULL).
- **Persistence reason:** `SavedLook` and future history records need a stable
  `look_id` reference; one canonical source resolves the 4 mirrored catalog
  shapes (K9.1).

### 4.7 `user_events` — P1

- **Domain entity:** `UserEvent` (E3).
- **Purpose:** a user-created, dated event providing occasion context; today it
  is widget state lost on restart.
- **Ownership:** user; feature owner `events`.
- **Lifecycle:** create (Add Event form) → edit/delete (stubs today) → may
  trigger occasion-seeded outfit generation (P1 fix); deleted-with-user.
- **Persistence reason:** events are user-authored, dated, and individually
  editable — rows; the occasion also FEEDS the preferred-occasions preference.

### 4.8 `style_score_records` — P1

- **Domain entity:** `StyleScoreRecord` (E8) — historical, derived.
- **Purpose:** dated, append-only snapshots of the computed style score (range
  0–100) so the Home score trend and Profile history survive input changes.
- **Ownership:** user; derived by `features/learning`.
- **Lifecycle:** created periodically / on score change; append-only.
- **Persistence reason:** the *current* score is a derived cache; the *trend*
  is history and needs immutable snapshot rows.

### 4.9 `activity_days` — P1

- **Domain entity:** `ActivityDay` (E9) — historical, derived.
- **Purpose:** one record per styled day backing the streak timeline
  (`UNIQUE (user_id, day)`).
- **Ownership:** user; derived by `features/learning`.
- **Lifecycle:** created when a styled day is recorded; append-only.
- **Persistence reason:** the current streak is derived; the per-day activity
  history must be queryable and immutable.

### 4.10 `today_look_records` — P1 (gated by product decision)

- **Domain entity:** `Today'sLookRecord` (conditional entity, P1 decision).
- **Purpose:** per-user per-day immutable snapshot of the daily look ("what I
  wore" history).
- **Ownership:** user; derived daily.
- **Lifecycle:** one row per `(user_id, day)`; append-only, never rewritten.
- **Persistence reason:** **only if** the product wants daily-look history;
  otherwise the daily look is a regenerable cache and **this table is not
  created** (PR-12).

### 4.11 `feedback_events` — P1 (created only when the feature lands)

- **Domain entity:** Recommendation / Outfit Feedback (future historical
  record; one concept shared by the wardrobe and general recommendation
  clusters).
- **Purpose:** append-only user reaction (rating/like/dislike/why) to a
  recommendation or saved look, closing the learning loop.
- **Ownership:** user (the event); target refs to `Look`/`SavedLook`.
- **Lifecycle:** created per rating; immutable; feeds `LearningSignal` and the
  derived preference state.
- **Persistence reason:** feedback is the explicit learning signal; **no table
  until the rating UI exists** (feature currently missing — `UI_UX_GAP_REPORT.md`
  #17).

### 4.12 `analysis_runs` — P2

- **Domain entity:** `AnalysisRun` (E6) — historical linkage.
- **Purpose:** per-execution record of a scan/analysis (outfit, face, hair,
  grooming): `user_id`, `run_type`, `status`, `engine_version` (reproducibility),
  source `MediaRef`, and the immutable `AnalysisResult` snapshot.
- **Ownership:** user; created by the analysis features
  (`outfit_scan`/`hairstyle`/`grooming`).
- **Lifecycle:** created per run; append-only; result retained while useful or
  while the user's saved look references it.
- **Persistence reason:** "AI event = reproducible history" — inputs +
  snapshot + engine version keep previous results answerable
  (`DOMAIN_STATE_AND_HISTORY.md` §6).

### 4.13 `subscriptions` — P2

- **Domain entity:** `Subscription` (E10).
- **Purpose:** the user's paid entitlement state (plan, status, period,
  external ref) — 0..1 per user.
- **Ownership:** user state; billing/entitlement via an external payment
  service.
- **Lifecycle:** activate → renew → cancel/expire (external service drives it).
- **Persistence reason:** user-scoped current state referencing a plan id;
  feature entitlement is **derived** from config × this row, never stored.

### 4.14 `recommendation_history` — P3 (gated by product decision)

- **Domain entity:** `RecommendationHistory` (conditional entity, P3 decision).
- **Purpose:** immutable trace of shown/saved recommendations (look ref +
  score/reasons snapshot + shown-at) for personalization analytics.
- **Ownership:** user; recorded when a recommendation is shown/saved.
- **Lifecycle:** append-only; no UPDATE/DELETE.
- **Persistence reason:** **only if** the analytics/recall feature is built
  (P3); today only `look_saved` signals trace it. No speculative table (PR-12).

### 4.15 Reference tables — P0/P1 (system knowledge, K9.1)

The vocabularies map to small reference tables (or versioned backend config —
the K9.1 decision; either way entities reference them **by stable id**):

| Table | Domain entity / concept | Purpose | Ownership | Lifecycle | Persistence reason |
| --- | --- | --- | --- | --- | --- |
| `wardrobe_categories` | Clothing Category (vocab) | canonical item categories | system | versioned content | FK target for `wardrobe_items.category_id` (required) |
| `colors` | Color (vocab) | canonical colors | system | versioned content | FK target for `wardrobe_items.color_id` (required) |
| `materials` | Material/Texture (vocab) | canonical materials | system | versioned content | FK target for `wardrobe_items.material_id` (optional) |
| `occasions` | Outfit Occasion (vocab, canonical of 4 copies) | shared occasion list | system | versioned content | id refs from events, looks, preferences |
| `event_types` | Event Type (vocab, 8 types) | event occasion types | system | versioned content | FK target for `user_events.event_type_id` (required) |
| `styles` | Style Vibe (vocab, 6 values) | style definitions | system | versioned content | id ref for profile `style_type` |
| `signal_types` | Learning-signal type (8 types) | signal vocabulary | system | versioned content | FK target for `learning_signals.signal_type` |
| `subscription_plans` | Subscription Plan (config) | plan catalog | system | versioned content | FK target for `subscriptions.plan_code` (P2) |
| `run_types` | Analysis run type (outfit/face/hair/grooming) | run-type vocabulary | system | versioned content | FK target for `analysis_runs.run_type` (P2) |

---

## 5. Concepts that MUST NOT become separate tables

Each excluded with the reason and where it lives instead. The pattern: a concept
becomes a table only when it has identity + lifecycle + durability + product
behavior (`DOMAIN_ENTITIES.md` four tests) **and** a query/join/count axis
(PR-1). Everything below fails at least one of those.

| Concept | Why it must NOT be a table | Instead |
| --- | --- | --- |
| `UserModel` blob | a mutable projection mixing current state + history; the exact conflation Step 4 splits | rows (`wardrobe_items`, `saved_looks`, `learning_signals`) + `user_state` JSONB |
| Style Profile / `FaceProfile` | current profile state with no identity of its own; read/written as a unit | JSONB in `user_state.style_profile` (with `source_run_id` provenance) |
| Hair / Grooming / Color Profile | PLANNED — only capability flags + mock outputs exist; no pipeline writes them | no table; becomes profile JSONB fields only when a real analysis lands (P1) |
| Style DNA view | derived display over `FaceProfile`; recomputable, never truth | recomputed on demand (cache) |
| Style Score (current) | derived from formula (60–100); storing it would duplicate the source | cache; history as `style_score_records` |
| Wardrobe (collection) | the 1:1 aggregate collection of items, not a separate entity | `wardrobe_items` rows; grouping is derived |
| Outfit / Outfit Item | value-object ensembles regenerated with their container; no identity, no lifecycle | embedded in `looks.payload`, `SavedLook.snapshot`, or a recommendation |
| AI Recommendation | AI output; regenerable, never a source of truth | value; occurrence → `recommendation_history` (P3) only if built |
| Recommendation Reason / Confidence | value objects; no structured field exists today (reasons live in prose) | snapshotted into `SavedLook.snapshot` |
| AI-generated Insight / Wardrobe Insight / Gap | derived AI output, cache-only | recomputed from wardrobe × knowledge |
| Wardrobe Gap | a *typed* Wardrobe Insight, not a separate concept | insight payload, never its own table |
| Weather / Weather Snapshot | third-party external data; cache with a short TTL | external service + cache; never durable |
| Assistant DTOs (`AssistantReply`, `AssistantMessage`, `AssistantUserContext`, …) | boundary wire shapes, mirrored 1:1 with the backend (KEEP A3.1) | no tables; the DB stores domain equivalents |
| AI Assistant Conversation | transient by default; retention is an undecided privacy/product choice | no table today; JSONB history only if retention is decided |
| Assistant Action | system config (16 action ids) + route mapping | config store; execution traced by signals |
| Authentication | external boundary process; provider details never enter the domain | opaque identity ref on `users`; flows in the auth service |
| Feature Entitlement | derived view (config × subscription); no per-user rows until a real capability system (P3) | derived at read time |
| AI Capability / AI Capability Progress | static config + marketing copy; no per-user state exists | config; availability derived; unlocks only with a P3 system |
| AI Model Version | system config, referenced from history for reproducibility | `engine_version` column on `analysis_runs` (+ optional config registry) |
| AI Decision Context | per-request derived snapshot, never stored | recomputed; optional frozen copy inside history JSONB |
| `defaultWardrobe` seed | knowledge seed, not user data | config → `wardrobe_items` rows on first save |
| Subscription Plan | system-authored catalog content | `subscription_plans` config/reference table |
| Achievements / ranks / XP | derived aggregates; definitions = config; no durable feature today | derived; no table |
| Media / images (blobs) | binary media must not live in PostgreSQL | object storage behind `MediaRef` reference columns |
| Location | value object, not used anywhere in the product today | no table; introduce only if a feature needs it |
| Money | display string today; no pricing math exists | field in plan config; typed amount+currency only if math lands |

---

## 6. Report — summary

- **14 proposed tables for domain entities/state** (10 true entities + the
  `user_state` projection + 2 conditional entities) + **9 reference/config
  tables** for vocabularies, phased P0→P3.
- **Every non-table concept resolves to one of:** a value object embedded in an
  owner (`FaceProfile`, outfit, scores, reasons, `MediaRef`), JSONB payload on
  an owner (`SavedLook.snapshot`, `AnalysisRun.result`, `user_state`), a
  derived cache (style DNA, insights, current score/streak/today's look), or
  external storage (media blobs, weather, auth).
- **Consistent with `DATABASE_DESIGN_RULES.md`:** same table names, same
  phasing, same JSONB columns, same lifecycle rules (CASCADE for user
  composition, RESTRICT/SET NULL for knowledge, append-only history).
- **The binding invariant holds:** AI output never becomes a table; only AI
  *events* (runs, signals, future feedback/history) get rows, and every durable
  AI row carries provenance for reproducibility.

---

## Constraints honored

- No SQL, no migrations, no database, no repositories, no endpoints.
- No Flutter, routing, UI, or backend code changes; no dependencies; nothing
  deleted.
- Every verdict traces to a STEP 3 domain document and, where it matters, to
  real source; nothing is invented beyond the domain model.
- The real Fansivibe repository is the source of truth; the separate reference
  project was not merged.




