# Fansivibe — PostgreSQL Database Design Rules

> **STEP 4 — DATABASE DESIGN.** Translates the finalized Fansivibe domain model
> (`FANSIVIBE_DOMAIN_MODEL_V1.md`, STEP 3 FINAL) into the rules and target shape
> for a production-ready PostgreSQL database. Every rule and table below traces
> to that model and to the STEP 2 inventory (`STORAGE_INVENTORY.md`,
> `DATA_OWNERSHIP.md`, `MVP_SCOPE.md`).
>
> **Status: design only. No PostgreSQL database is created, no migrations are
> written, no SQL is run, no Flutter/backend/routing code changes, no
> repositories or endpoints are created, no dependencies are added, nothing is
> deleted.** This document is the contract the schema-migration step will be
> built against.
>
> **Source of truth:** the real Fansivibe repository
> (`newproject/flutter_application_1` + `backend/`). The separate reference
> project is reference material only and was **not** merged into this design.

---

## 1. Purpose and scope

This step produces the **rules and target schema shape** for the Fansivibe
PostgreSQL database. It answers three questions:

1. **What is stored relationally, and in which table?** — the entity catalog
   (E1–E10 + conditional entities) mapped to tables.
2. **What rules govern every table?** — keys, foreign keys, constraints,
   JSONB policy, media policy, history-vs-state enforcement.
3. **What is deliberately kept out of PostgreSQL?** — external data, cache,
   temporary processing state, media bytes, and derived values.

It does **not** answer how to run the database, which migration tool to use, or
the exact SQL text — those belong to the next step (schema/migrations), which
must implement these rules verbatim.

**Design derivation rule (DBR-0):** the database represents the **domain model,
not the Flutter UI**. A table may only exist if it corresponds to a domain
entity, value-object snapshot, or knowledge reference in
`FANSIVIBE_DOMAIN_MODEL_V1.md`. UI models, DTOs, mock shapes, and widget state
are never table shapes (`DATA_MODEL_INVENTORY.md` §19.2; the assistant DTOs are
KEEP as wire contract, never stored as their own tables).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | The canonical contract — entities, value objects, relationships, ownership, lifecycle. |
| `DOMAIN_STATE_AND_HISTORY.md` §8 | The six rules the schema must enforce (history vs state). |
| `DOMAIN_RELATIONSHIPS.md` | R1–R51 cardinalities and lifecycle semantics for foreign keys. |
| `STORAGE_INVENTORY.md` | Storage category assignments (1–7) and retention per object. |
| `DATA_OWNERSHIP.md` | Owner, deletion matrix, AI-output-never-truth. |
| `MVP_SCOPE.md` | P0/P1/P2/P3 phasing of what to create first. |
| `DECISIONS.md` DEC-004 | PostgreSQL is the intended primary relational database. |

Spot facts re-verified from source this step (they anchor the design):

- **Score formula** — `60 + wardrobe.length.clamp(0,20) + (savedLooks.length*2).clamp(0,20)`
  (`learning_service.dart:228-229`) → derived, range 60–100, never stored as truth.
- **8 signal types** — 5 learning (`item_added`, `analysis_updated`,
  `style_updated`, `look_saved`, `occasion_preferred`) + 3 assistant
  (`assistant_message`, `suggestion_opened`, `assistant_navigation`).
- **Current persistence** — single `UserModel` JSON blob, SharedPreferences key
  `fansivibe.user_model.v1`, via `LocalStore`; the blob holds `wardrobe[]`,
  `face{}`, `styleType`, `savedLooks[]` (titles only), `preferredOccasions[]`,
  `signals[]` (`models.dart:106-171`).
- **No auth** — all account-creation branches just navigate home; `user_id`
  scoping is designed for, not implemented.
- **`setFace` never called** — `FaceProfile` is defined but never written.
- **Weather** is a fake literal (`'68°F • Partly Cloudy'`) — never a table.
- **No images persist** — `FansiImageWell` is a gradient placeholder; no media
  tables exist and none are added now.

---

## 3. Design principles (the binding rules)

Every table and column in this design must satisfy these principles. They are
numbered (PR-1…PR-12) so later steps can reference them.

### PR-1 — Relational-first, normalized schema

Normalize by default. Each durable fact lives in exactly one place, modeled as
rows and foreign keys, not as nested blobs. A fact is promoted to a row when it
needs to be **queried, joined, counted, or individually owned**
(`wardrobe_items`, `learning_signals`, `saved_looks`, `user_events`,
`analysis_runs`, `style_score_records`, `activity_days`).

### PR-2 — No unnecessary duplication

Every fact has exactly **one owner and one home**. This is the direct fix for
the three known duplicate families:

- **The `UserModel` blob split** — one row per user-owned entity plus one
  current-state JSONB document; the blob is a projection, not a table
  (`STORAGE_INVENTORY.md` Part 4 #1; §7 below).
- **The mirrored catalogs** — the 3–4× duplicated vocabularies collapse to one
  backend-owned reference source per concept, referenced by id (K9.1).
- **Derived values** — score, streak, style DNA, match scores, today's look are
  **recomputed**, never written twice; only their **immutable snapshots**
  (`StyleScoreRecord`, `ActivityDay`, `SavedLook` payload) persist.

Duplication is only acceptable for **immutable snapshots captured at a point in
time** (see PR-6), never for live state.

### PR-3 — UUID primary keys where appropriate

- **All user-owned entity tables use `uuid` primary keys** (`gen_random_uuid()`).
  UUIDs are generated by the server/backend, never accepted from clients, and
  make multi-device sync, anonymous→registered account merge, and backup/restore
  safe without centralized id assignment (required by `AU11.1/AU11.2`).
- **System-knowledge reference tables prefer stable, immutable text codes** as
  natural keys (e.g. `occasion_code = 'formal'`, `signal_type = 'look_saved'`).
  Knowledge rows are backend-controlled, versioned content; a stable code
  survives re-seeding and is human-auditable. If a UUID is used anyway, a
  stable `code` column must still exist and be the referenced value.
- **Never reuse a client-generated string as a primary key** (the current
  `WardrobeEntry.id` is a Dart-side string; the DB owns identity).

### PR-4 — Foreign keys with explicit lifecycle semantics

Every relationship in `DOMAIN_RELATIONSHIPS.md` maps to a foreign key whose
`ON DELETE` matches the relationship's lifecycle rule
(`DOMAIN_RELATIONSHIPS.md` §5):

- **Composition from `User`** (R3–R9: wardrobe items, events, saved looks,
  analysis runs, signals, score records, activity days) → `user_id NOT NULL`
  FK with `ON DELETE CASCADE`. The user owns the data; deleting the account
  deletes its data (per `STORAGE_INVENTORY.md` retention principle).
- **Reference to knowledge** (`SavedLook.look_id`, item category/color/occasion,
  event type) → FK is **never `ON DELETE CASCADE`**. Use `ON DELETE RESTRICT`
  (a live catalog row may not vanish while referenced) or `ON DELETE SET NULL`
  where the reference may legitimately be dropped (deprecated `Look`,
  `SavedLook.look_id`). A saved look survives catalog edits
  (`DOMAIN_RELATIONSHIPS.md` R30).
- **Cross-links between user entities** (`SavedLook.source_run_id` →
  `analysis_runs`) → `ON DELETE SET NULL`; the link is informational, and
  deleting current state never deletes history (rule §10).

### PR-5 — Enforce important business constraints

Constraints are enforced in the database, not only in application code:

- `NOT NULL` on every mandatory relationship (e.g. `wardrobe_items.category_id`,
  `user_events.event_type_id`, every `user_id`).
- `CHECK` on numeric ranges (e.g. `style_score_records.score BETWEEN 0 AND 100`).
- `UNIQUE` on per-user-per-period rows (`activity_days (user_id, day)`,
  `today_look_records (user_id, day)`), on identity (`users.auth_subject`), and
  on the 0..1 `subscriptions.user_id`.
- `CHECK` on enum-like `status`/`type` columns where the vocabulary is stable
  and small; otherwise FK to the reference table (PR-4).
- All history tables get **no `UPDATE`/`DELETE` grants** for the API role —
  append-only is enforced at the permission layer, not just by convention
  (§10, rule 1).

### PR-6 — Preserve historical AI results

The binding domain invariant is **"AI output is never a source of truth, but an
AI *event* is a historical fact that must remain reproducible."** The schema
preserves reproducibility by keeping, per historical row, the three elements of
`DOMAIN_STATE_AND_HISTORY.md` §6:

1. **durable inputs** — user data (referenced by `user_id`) + `MediaRef` to the
   source media;
2. **an immutable result snapshot** — JSONB payload frozen at completion
   (`analysis_runs.result`, `saved_looks.snapshot`);
3. **engine/config version** — `analysis_runs.engine_version` so a past result
   can be re-derived or audited.

Append-only historical tables: `learning_signals`, `style_score_records`,
`activity_days`, `analysis_runs`, and (when built) `today_look_records`,
`recommendation_history`, `feedback_events`.

### PR-7 — Separate current profile state from historical analyses

The core Step 4 split (`DOMAIN_STATE_AND_HISTORY.md` §8 rule 2; the
`UserModel` blob conflation):

- **Current state** — the user's present, mutable world: `users`,
  `user_state` (style/face profile, preferences, flags), `wardrobe_items`,
  `user_events`, `saved_looks` (list), `subscriptions`. These tables support
  `UPDATE` and are edited in place.
- **Historical** — the immutable, append-only trace: `learning_signals`,
  `style_score_records`, `activity_days`, `analysis_runs` + snapshots.
- **Provenance:** current profile projections name their source
  (`user_state.style_profile.source_run_id → analysis_runs.id`); they never
  contain history and never rewrite it.

A history table and a current-state table are **never** the same table. A new
analysis creates a new `analysis_runs` row and projects attributes forward into
`user_state`; it never rewrites an old run.

### PR-8 — Media binaries live outside PostgreSQL

PostgreSQL stores **references, never bytes**:

- User photos, face scans, outfit photos, wardrobe images, and generated images
  go to **object storage**; the DB row carries a `MediaRef` — the object key /
  URL plus a small amount of metadata (media type, dimensions) needed for
  display.
- No `BYTEA` columns for product images. No media table is created now
  (nothing persists media today); when the media pipeline lands it is object
  storage + reference columns, gated by the media-privacy policy (MS10.3) (§9).

### PR-9 — JSONB only where schema flexibility is genuinely useful

JSONB is a deliberate exception, used **only** for payloads that are (a) large,
structured, evolving, and written/read as a unit, or (b) immutable snapshots of
AI/derived output whose shape is not a query axis. Every JSONB column must have
a written justification (§8). **JSONB is never used as an excuse to avoid
relational modeling** — anything that is queried, joined, counted, or owned
individually must be a row.

### PR-10 — Design for user ownership and privacy

- Every user-owned table has a mandatory `user_id` FK and is scoped by it.
- The API never trusts a client-supplied `user_id`; identity comes from
  authenticated session context.
- Privacy-sensitive data (appearance attributes, images, raw scans) is scoped,
  never logged, and follows the retention rules in `STORAGE_INVENTORY.md`
  (raw scans auto-expire unless saved; blobs follow the user lifecycle).
- Conversations stay transient by default; retention is a pending privacy
  decision (§16), never assumed.

### PR-11 — Design for future migrations

- All schema changes ship as versioned, forward-only migrations; every table
  is created through migrations, never ad hoc.
- Additive-first: add nullable columns / new tables; backfill; then drop —
  never destructive `ALTER`s in one step.
- The blob→rows split (`POST /users/me/sync`) is a **data migration with a
  defined backfill path** (idempotent, resumable), not a hand-edited blob.
- Reserved-for-evolution: every table carries `created_at timestamptz NOT NULL
  DEFAULT now()`; current-state tables also carry `updated_at`; soft-delete
  `deleted_at` is added only where a feature actually needs it (avoid premature
  columns).

### PR-12 — Avoid premature complexity

Only the entities and snapshots the product actually needs are modeled. P3-only
concepts (`RecommendationHistory`, per-user capability state, XP/achievements,
real analysis runs) get **no table until their product decision lands**
(`MVP_SCOPE.md` Part 5; `DOMAIN_STATE_AND_HISTORY.md` §8 rule 6). No speculative
tables, no audit framework, no multi-tenant machinery.

---

## 4. Naming conventions and schema layout

- **Tables:** plural `snake_case` named after the domain entity —
  `users`, `wardrobe_items`, `saved_looks`, `learning_signals`, `looks`,
  `user_events`, `style_score_records`, `activity_days`, `analysis_runs`,
  `subscriptions`, `user_state`.
- **Columns:** `snake_case`. Every table uses `id` as the primary key name
  (except knowledge reference tables, which use their `code` as PK).
- **Foreign keys:** `<singular_entity>_id` for single refs
  (`user_id`, `look_id`, `event_type_id`, `source_run_id`).
- **Timestamps:** `created_at`, `updated_at` (current state only), `occurred_at`
  (historical events), `day`/`recorded_at` (dated history).
- **JSONB columns:** named for their sub-document — `snapshot`, `result`,
  `payload`, `style_profile`, `preferences`, `flags`, `context`.
- **Schema layout:** default `public` schema in P0/P1 (single service, single
  tenant), namespaced by table name. A dedicated API/backend role owns all
  tables; the backend enforces `user_id` scoping at the application layer.
  No schema-per-feature in P0 — it would duplicate the entity catalog without
  benefit (PR-12).

---

## 5. Key policy

| Table group | Primary key | Why |
| --- | --- | --- |
| User-owned entity tables | `id uuid` (server-generated) | multi-device sync + anonymous→registered merge safety (PR-3) |
| Knowledge/vocabulary reference tables | `code text` (stable) | backend-owned versioned content; stable identity across re-seeds (PR-3) |
| Join/history rows | `id uuid` or composite `(user_id, period)` | composite when a per-user-per-period uniqueness IS the identity (`activity_days`) |

`users` identity: the account's **opaque auth reference** is an external-boundary
concern (auth provider, provider subject) — the DB holds it as a unique,
non-nullable pair (`auth_provider`, `auth_subject`, `UNIQUE`) without importing
provider flows into the domain (`ACCOUNT_ASSISTANT_DOMAIN_MODEL.md`). Exact
columns wait on the auth design (open question §16).

---

## 6. Target table catalog

The shape below is the **target relational shape** per entity. Column lists are
the required core; they are the contract migrations implement, in the priority
order of §14. **No SQL is written here.**

### 6.1 P0 tables (first vertical slice)

**`users`** — E1 `User`, current state, aggregate root.
`id uuid PK` · `auth_provider text` · `auth_subject text` ·
`display_name text` · `created_at` · `updated_at`.
`UNIQUE (auth_provider, auth_subject)`.
Auth-design details pending (§16); the row exists so every other table has a
`user_id` FK (P0 prerequisite, `AZ12.3`).

**`user_state`** — current-state projection, 1:1 with `users`.
`user_id uuid PK/FK → users ON DELETE CASCADE` · `style_profile jsonb`
(current profile state: the `FaceProfile` value object — `face_shape`,
`skin_tone`, `body_type`, `style_type` — plus `style_type` and `source_run_id`
provenance) · `preferences jsonb` (reference-list ids, e.g.
`preferred_occasions: [occasion ids]`) · `flags jsonb`
(`has_saved_wardrobe_item` — the F1.4 session flag moved into the user model) ·
`version int` · `updated_at`.
Justified JSONB: current-state payloads are read/written as a unit, their shape
evolves, and they carry cross-feature state (PR-9; §7).

**`wardrobe_items`** — E2 `WardrobeItem`, current state, user-owned.
`id uuid PK` · `user_id uuid FK → users CASCADE NOT NULL` · `name text NOT NULL` ·
`category_id text FK → wardrobe_categories RESTRICT NOT NULL` ·
`color_id text FK → colors RESTRICT NOT NULL` · `material_id text FK → materials`
(nullable) · `is_favorite bool DEFAULT false` · `image_ref jsonb` (MediaRef:
object key/URL + media type; nullable) · `created_at` · `updated_at`.
Mandatory category + color (`DOMAIN_RELATIONSHIPS.md` R18). `image_ref` is the
only JSONB on a current-state row and is a *reference*, never a blob (PR-8).

**`saved_looks`** — E4 `SavedLook`, current state (the list), user-owned.
`id uuid PK` · `user_id uuid FK → users CASCADE NOT NULL` ·
`look_id text FK → looks SET NULL` (nullable; P0 stores reference + title) ·
`title text NOT NULL` · `snapshot jsonb` (immutable payload captured at save
time — ensemble, score, reasons; R31) · `source_run_id uuid FK → analysis_runs
SET NULL` (nullable, P2; links when saved from a scan) · `created_at`.
The `snapshot` JSONB is the **boundary case**: an AI/derived output that becomes
history only because the user saved it (R31; `VALUE_OBJECTS.md` boundary cases).

**`learning_signals`** — E7 `LearningSignal`, **append-only history**.
`id uuid PK` · `user_id uuid FK → users CASCADE NOT NULL` ·
`signal_type text FK → signal_types RESTRICT NOT NULL` (8 types, §2) ·
`label text NOT NULL` · `context jsonb` (nullable, small optional payload) ·
`occurred_at timestamptz NOT NULL`.
No `UPDATE`/`DELETE` for the API role (PR-5). **No FK to the triggering entity**
(`wardrobe_items`, `saved_looks`) — deleting current state never deletes history
(§10 rule 3). `context` preserves event payloads when a read model later needs
them; it is optional and must stay small.

**`looks`** — E5 `Look`, system-owned knowledge catalog (P0: reference set).
`code text PK` (stable) · `title text NOT NULL` · `image_ref jsonb` (catalog
asset reference) · `content_version text` · `published_at` · `deprecated_at`
(nullable) · `payload jsonb` (ensemble value object; rich content shape follows
the K9.1 decision, §16).
Never user-tied; referenced by `saved_looks.look_id`; deprecation never deletes
referenced rows (R30).

**P0 knowledge/vocabulary reference tables** — single backend-owned source per
concept (K9.1): `wardrobe_categories`, `colors`, `materials`, `occasions`,
`styles`, `event_types`, `signal_types`. Minimal shape:
`code text PK` · `label text NOT NULL` · `sort_order int` · `active bool`.
Storage-home note: these may ship as **versioned config** served by the backend
instead of DB rows (K9.1 open question, §16). Either way the DB contract holds:
entities reference knowledge by **stable id, never embed the value**
(`DOMAIN_RELATIONSHIPS.md` §5 rule 7).

### 6.2 P1 tables (next core features)

**`user_events`** — E3 `UserEvent`, current state (dated, editable), user-owned.
`id uuid PK` · `user_id uuid FK → users CASCADE NOT NULL` · `title text NOT NULL` ·
`event_type_id text FK → event_types RESTRICT NOT NULL` (R34) ·
`event_date date NOT NULL` · `location text` · `notes text` ·
`created_at` · `updated_at`.
Also FEEDS `preferred_occasions` (R36) and seeds outfit generation (R35, P1 fix
that carries the occasion into the builder).

**`style_score_records`** — E8 `StyleScoreRecord`, **append-only history**.
`id uuid PK` · `user_id uuid FK → users CASCADE NOT NULL` ·
`score smallint NOT NULL CHECK (score BETWEEN 0 AND 100)` ·
`breakdown jsonb` (immutable `StyleScoreBreakdownItem` snapshot) ·
`recorded_at date NOT NULL` · `occurred_at timestamptz NOT NULL`.
Derived from the score formula (§2); the **current** score is a cache, this
table is its history (PR-2, PR-7). Append-only grants (PR-5).

**`activity_days`** — E9 `ActivityDay`, **append-only history** (streak source).
`id uuid PK` · `user_id uuid FK → users CASCADE NOT NULL` · `day date NOT NULL` ·
`styled bool NOT NULL DEFAULT false` · `summary jsonb` (nullable derived
aggregate for the day) · `occurred_at timestamptz NOT NULL`.
`UNIQUE (user_id, day)`. Feeds the current streak (derived cache).

**`today_look_records`** — conditional entity, **P1 decision**. If "what I wore"
history is wanted: `id uuid PK` · `user_id FK CASCADE` · `day date` · `snapshot
jsonb` (the daily look, frozen) · `UNIQUE (user_id, day)` · append-only.
If the product decides a derived cache is enough, **this table is not created**
(`FANSIVIBE_DOMAIN_MODEL_V1.md` §4 conditional; `MVP_SCOPE.md` P1).

**`feedback_events`** — future feedback feature (P1). Design-input only: created
only when the like/dislike/why UI exists. `id uuid PK` · `user_id FK CASCADE` ·
`target_look_id text FK → looks SET NULL` · `target_saved_look_id uuid FK → saved_looks
SET NULL` · `rating text` · `reason text` · `occurred_at`. Append-only history
that FEEDS the derived-preference loop (`AI_DOMAIN_MODEL.md` R-A13→R-A16).

### 6.3 P2 tables (supporting features)

**`analysis_runs`** — E6 `AnalysisRun`, **append-only history**, user-owned.
`id uuid PK` · `user_id uuid FK → users CASCADE NOT NULL` ·
`run_type text FK → run_types RESTRICT NOT NULL` (outfit/face/hairstyle/grooming) ·
`status text NOT NULL` (pending/completed/failed) ·
`engine_version text` (reproducibility, PR-6) ·
`input_media jsonb` (MediaRef to the source scan image; nullable) ·
`result jsonb` (immutable `AnalysisResult` snapshot; nullable until complete) ·
`created_at` · `completed_at` (nullable).
Append-only; a result snapshot may be re-derived from inputs but never
overwritten in place (PR-6, §10).

**`subscriptions`** — E10 `Subscription`, current state, user-owned (P2).
`id uuid PK` · `user_id uuid FK → users CASCADE NOT NULL UNIQUE` (0..1) ·
`plan_code text FK → subscription_plans RESTRICT NOT NULL` (plans are knowledge
content; `SubscriptionPlan.price` is a display string) · `status text NOT NULL` ·
`started_at` · `renews_at` (nullable) · `external_ref text` (external
entitlement/payment service, R51) · `created_at` · `updated_at`.
Entitlement is derived from config × this row (R45), not stored.

### 6.4 P3 (future — no table until the decision lands)

- **`recommendation_history`** — conditional entity (P3): shown/saved
  recommendation trace; `user_id` · `look_id` · `snapshot` (score + reasons at
  show time) · `shown_at` · `saved bool`. Only with `RecommendationHistory`
  decision (`MVP_SCOPE.md` P3).
- Per-user capability state, XP/achievements, real face-analysis pipelines —
  explicitly **not modeled** (PR-12; `DOMAIN_STATE_AND_HISTORY.md` §8 rule 6).

---

## 7. The `UserModel` blob split (P7.1)

The current blob (`models.dart:106-171`) is a projection mixing current state
and history. Its six fields land in exactly one place each:

| Blob field | Land | Reason |
| --- | --- | --- |
| `wardrobe[]` | `wardrobe_items` rows (P0) | queried/counted/owned individually (PR-1) |
| `signals[]` | `learning_signals` rows (P0) | append-only history (PR-7) |
| `savedLooks[]` (titles) | `saved_looks` rows (P0) | user-managed list (PR-1) |
| `face{}` + `styleType` | `user_state.style_profile` JSONB (P0) | current profile projection, read/written as a unit (PR-7) |
| `preferredOccasions[]` | `user_state.preferences` JSONB (P0) | reference ids, additive (PR-7) |
| `hasSavedWardrobeItem` (session flag, F1.4) | `user_state.flags` JSONB (P0) | user model state, not session (F1.4) |

`POST /users/me/sync` migrates the blob into these rows **idempotently and
resumably** (PR-11). The old blob is not a table; it is the pre-migration
transport and the offline snapshot.

---

## 8. JSONB usage rules

**Allowed (each with its justification):**

| Column | Why JSONB (justification) |
| --- | --- |
| `user_state.style_profile` | current profile state; read/written as a unit; shape evolves with the AI pipeline; carries `source_run_id` provenance (PR-7) |
| `user_state.preferences` | sparse set of vocabulary ids; additive; no per-preference query |
| `user_state.flags` | sparse derived/user flags; no join axis |
| `saved_looks.snapshot` | immutable AI/derived payload frozen at save time; not a query axis (PR-6, R31) |
| `learning_signals.context` | small optional event payload; never a filter axis |
| `analysis_runs.result` | immutable structured AI output; evolving shape (PR-6; `STORAGE_INVENTORY.md` §1.6) |
| `looks.payload` | ensemble value object; content shape governed by K9.1 |
| `image_ref` (any) | MediaRef reference metadata; never the bytes (PR-8) |

**Forbidden:**

- No JSONB for `wardrobe_items`, `user_events`, `learning_signals` rows
  themselves, `saved_looks` list, `style_score_records`, `activity_days` — all
  are query/join/count axes (PR-1).
- No JSONB that **replaces a vocabulary reference**: an entity's category/color/
  occasion/type is always an FK to the reference table (PR-2, K9.1).
- No JSONB that **mirrors a Flutter model** wholesale (DBR-0).
- No JSONB storing AI output as the *current* truth — AI output is never a
  source of truth; JSONB snapshots are history only (PR-6).

---

## 9. Media and object storage policy

- **PostgreSQL never stores media bytes.** Product images, scans, and generated
  images live in object storage; the DB row carries a `MediaRef`
  (`image_ref`/`input_media`/`looks.image_ref`).
- **`MediaRef` shape (value object):** object key (user-scoped, e.g.
  `users/{user_id}/{entity}/{entity_id}.{ext}`) or signed URL + media type +
  optional display metadata (width/height). No blob column.
- **Lifecycle follows the referencing row** (`STORAGE_INVENTORY.md` Part 4 #7):
  item image deleted with the item; saved-look images follow the saved look;
  raw scans auto-expire unless the user saves them.
- **Precondition:** no media *storage* is implemented until the **media-privacy
  policy (MS10.3)** is decided — it gates object-storage configuration, not the
  `MediaRef` reference columns, which are already in the target schema (PR-8).

---

## 10. Current-state vs history — schema enforcement

The six rules of `DOMAIN_STATE_AND_HISTORY.md` §8, made enforceable:

1. **Append-only history.** `learning_signals`, `style_score_records`,
   `activity_days`, `analysis_runs` (and future `today_look_records`,
   `recommendation_history`, `feedback_events`) are created once and never
   updated or deleted by the application: the API role gets `INSERT`/`SELECT`
   only on these tables (PR-5). Edits and deletes apply to current state only.
2. **Current state is a projection with provenance.** `user_state.style_profile`
   names its `source_run_id`; it never contains history.
3. **Deleting current state never deletes history.** No history table has a FK
   to a current-state entity (`learning_signals` has no item/look FK); the
   history survives item/event/saved-look deletion. Soft-delete/retention is the
   only history-removal path (`DATA_OWNERSHIP.md` deletion matrix).
4. **Derived values recompute; snapshots persist.** Current score, style DNA,
   match scores, and today's look are never written as truth; only the
   immutable snapshot tables (`style_score_records`, `activity_days`,
   `saved_looks.snapshot`) persist them.
5. **AI events stay reproducible.** `analysis_runs` keeps durable inputs
   (`input_media`), the immutable `result` snapshot, and `engine_version` (§6.3).
6. **No speculative history tables.** Feedback, capability progress, and
   recommendation history are modeled only when their features land (PR-12).

---

## 11. Business constraints the schema must enforce

| Constraint | Mechanism |
| --- | --- |
| A wardrobe item always has a category and color | `NOT NULL` + FK RESTRICT on `wardrobe_items.category_id`, `color_id` (R18) |
| An event always has a type | `NOT NULL` + FK RESTRICT on `user_events.event_type_id` (R34) |
| A signal always has a type | `NOT NULL` + FK on `learning_signals.signal_type` |
| Scores stay in the valid range (formula 60–100) | `CHECK (score BETWEEN 0 AND 100)` on `style_score_records` |
| One activity row per user per day | `UNIQUE (user_id, day)` on `activity_days` |
| One today's-look record per user per day | `UNIQUE (user_id, day)` on `today_look_records` (if built) |
| At most one subscription per user | `UNIQUE (user_id)` on `subscriptions` (0..1, R10) |
| Auth identity is unique | `UNIQUE (auth_provider, auth_subject)` on `users` |
| History cannot be mutated | permission layer (§10 rule 1) |

---

## 12. Indexing strategy

Start minimal; add with measured queries (PR-12). Baseline indexes:

- Every user-owned table: index on `user_id` (leading column of all access
  paths; PR-10).
- History feeds: `(user_id, occurred_at)` on `learning_signals`;
  `(user_id, day)`/`(user_id, recorded_at)` on dated tables
  (`style_score_records`, `activity_days`) — covers streak/score aggregation
  and the existing `UNIQUE` constraints where applicable.
- Reference lookups: `saved_looks (user_id, created_at)` (the saved-looks list),
  `wardrobe_items (user_id, category_id)` (wardrobe filtering).
- **No speculative indexes** on JSONB (no JSON query axes today; the JSONB
  columns are explicitly non-query axes, §8).

---

## 13. Migration and versioning rules

1. **Versioned, forward-only migrations.** One file per change; sequential
   ordering; never edited after application.
2. **Additive-first.** Add nullable column → backfill → enforce `NOT NULL` →
   drop old — never a destructive one-step `ALTER` (PR-11).
3. **The blob split is a data migration.** `POST /users/me/sync` runs an
   idempotent, resumable backfill from the device blob into `users` +
   `user_state` + `wardrobe_items` + `saved_looks` + `learning_signals`
   (PR-11, §7).
4. **Knowledge tables are seeded by migration/config** (K9.1): the reference
   rows (categories, colors, occasions, event types, signal types) ship with a
   deterministic seed; entity rows never duplicate them (PR-2).
5. **Contract versioning** is out of scope until endpoints stabilize
   (`MVP_SCOPE.md` P3); schema changes are still versioned from day one.

---

## 14. Phased build order

From `FANSIVIBE_DOMAIN_MODEL_V1.md` §17 and `MVP_SCOPE.md`:

| Phase | Tables | Gates |
| --- | --- | --- |
| **P0** | `users`, `user_state`, `wardrobe_items`, `saved_looks`, `learning_signals`, `looks` (+ P0 vocab refs: `wardrobe_categories`, `colors`, `materials`, `occasions`, `signal_types`) | auth design, canonical models, `POST /users/me/sync`, API contract |
| **P1** | `user_events`, `style_score_records`, `activity_days`, `today_look_records` (if decided), `feedback_events` (if built), full vocab refs | event persistence, score/streak pipeline, feedback feature, today's-look decision |
| **P2** | `analysis_runs`, `subscriptions`, `run_types` | analysis contract, subscription/entitlement |
| **P3** | `recommendation_history`, capability/achievement state (if ever) | real AI/analytics capability |

**Must NOT be built yet:** real AI models, media/object storage, weather
integration, multi-device authorization, contract versioning, XP/achievements,
recommendation analytics, onboarding face AI (`MVP_SCOPE.md` Part 5).

---

## 15. What is deliberately kept OUT of PostgreSQL

| Item | Home | Reason |
| --- | --- | --- |
| Media bytes (photos, scans, images) | object storage (PR-8) | blobs, referenced by `MediaRef` |
| Weather | external service + cache | third-party data, never owned (`STORAGE_INVENTORY.md` §1.9) |
| Current style score / streak / today's look | derived cache | recomputable; history lives in snapshot tables (PR-2) |
| Style DNA view, match scores, insights | derived cache | recomputed, never truth (PR-2) |
| Assistant conversations | transient; retention undecided (§16) | privacy/product decision pending |
| Assistant context snapshot | temporary processing | per-request DTO, never stored (R47) |
| Assistant DTOs, UI/mock models | code (wire contract) | DBR-0; KEEP as contract (A3.1) |
| Processing stages, scan buffers, filters | temporary processing | no durable value |
| Knowledge config (if config-hosted per K9.1) | versioned backend config | reference tables are the DB shape only if DB-hosted (§6.1) |

---

## 16. Open decisions carried into implementation

These were open at the end of STEP 3 and remain open here; **none blocks the
rules in this document**, each only delays a specific table:

1. **`User` fields / auth design** (AU11.1/AU11.2) — pins the exact `users`
   columns and the anonymous→sync merge semantics (PR-3). `user_id` scoping is
   designed for regardless.
2. **`Today'sLookRecord`** — create the per-user daily snapshot (P1) or keep a
   derived cache? (§6.2)
3. **`RecommendationHistory`** — build the shown/saved trace (P3)? (§6.4)
4. **Conversation retention** — persist conversations (JSONB history with a
   short window) or keep transient? Domain default = transient (§15).
5. **Knowledge source shape (K9.1)** — versioned DB tables vs versioned config
   for vocabularies/catalogs; the DB shape is defined either way (§6.1).
6. **Media privacy policy (MS10.3)** — must be decided before any media
   persistence; gates object storage, not the `MediaRef` reference columns (§9).
7. **Feedback design** — `feedback_events` shape is created only when the
   feature lands (P1; §6.2).

---

## 17. Report — database design principles and assumptions

### Design principles

1. **Relational-first, normalized** — rows + FKs by default; JSONB is the
   documented exception, never a normalization dodge (PR-1, PR-9).
2. **One owner and one home per fact** — fixes the `UserModel` blob mix and the
   duplicated catalogs; duplication only as immutable snapshots (PR-2, PR-6).
3. **UUID keys for user-owned data; stable text codes for knowledge** — sync- and
   merge-safe identity vs. auditable backend-controlled reference (PR-3).
4. **Foreign keys mirror relationship lifecycle** — `CASCADE` only for user
   composition; `RESTRICT`/`SET NULL` for knowledge and cross-links (PR-4).
5. **Constraints live in the database** — `NOT NULL`, `CHECK`, `UNIQUE`, and
   append-only permission grants (PR-5).
6. **AI output is never truth, but AI events stay reproducible** — inputs +
   immutable snapshot + engine version (PR-6).
7. **Current state and history are never the same table** — mutable projections
   vs. append-only traces, with `source_run_id` provenance (PR-7).
8. **Media stays out of PostgreSQL** — `MediaRef` reference columns only (PR-8).
9. **User ownership and privacy by construction** — mandatory `user_id` scoping,
   no client-trusted identity, sensitive-data retention (PR-10).
10. **Migratable and phased** — versioned additive migrations, idempotent blob
    split, P0→P3 table order, no speculative tables (PR-11, PR-12).

### Assumptions

1. **PostgreSQL is the primary relational database** (DEC-004), used for
   current state + append-only history; JSONB stays in Postgres; media moves to
   object storage; cache/external/temporary state stay out of the DB.
2. **The domain model V1 is the contract** — tables map 1:1 to E1–E10 and the
   conditional entities; nothing is invented beyond it (DBR-0).
3. **Identity and scoping precede data** — `users` exists even before auth is
   designed, so every row has a `user_id` FK (`AZ12.3`).
4. **The `UserModel` blob is legacy transport, not a schema** — it is split
   into rows + `user_state` JSONB via an idempotent migration (§7).
5. **P0/P1/P2/P3 sequencing holds** — P3 tables (`recommendation_history`,
   capability/achievement state) are deliberately absent until their product
   decisions land (PR-12).
6. **Open questions do not block the rules** — they gate only specific tables
   (§16); the design remains valid under either resolution.
7. **Privacy-sensitive appearance and image data** is never logged, is
   user-scoped, and follows the retention policy of `STORAGE_INVENTORY.md`.

---

## Constraints honored

- No PostgreSQL database created, no migrations written, no SQL run.
- No Flutter, routing, UI, or backend code changes; no repositories, no API
  endpoints, no dependencies added, no existing code deleted.
- Every table and constraint traces to `FANSIVIBE_DOMAIN_MODEL_V1.md`, the
  STEP 2 inventory, and real source; no entity is invented beyond the domain
  model.
- The real Fansivibe repository is the source of truth; the separate reference
  project was **not** merged into this design.


