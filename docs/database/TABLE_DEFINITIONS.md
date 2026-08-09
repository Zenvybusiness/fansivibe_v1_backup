# Fansivibe — Logical Table Definitions

> **STEP 4 (continuation) — DATABASE DESIGN.** Defines the **logical schema** for
> every proposed PostgreSQL table from `DOMAIN_TABLE_MAPPING.md`: table name,
> purpose, primary key, columns with PostgreSQL data types, nullability,
> defaults, unique/foreign-key/check constraints, generated fields, and
> timestamps. **No SQL is written here** — this document is the contract the
> schema/migration step implements verbatim.
>
> **Status: documentation only. No PostgreSQL database is created, no
> migrations are written, no SQL is run, no Flutter/backend/routing code
> changes, no repositories or endpoints, no dependencies, nothing deleted.**
>
> **Source of truth:** the finalized domain model (STEP 3), the
> `DOMAIN_TABLE_MAPPING.md` verdicts, and `DATABASE_DESIGN_RULES.md`
> (PR-1…PR-12, key policy §5, JSONB policy §8, media policy §9, table catalog
> §6, open decisions §16). Only tables **supported by the finalized domain
> model** are defined here; concepts the mapping resolved as non-tables are
> listed in §8 with their home instead.

---

## 1. Purpose and method

For each proposed table this document specifies what the task requires:

| # | Element | Meaning |
| --- | --- | --- |
| 1 | Table name | Exact `snake_case` plural name, finalized in the mapping. |
| 2 | Purpose | Why the table exists and what a row models. |
| 3 | Primary key | `uuid` (user-owned) or stable `text` code (knowledge). |
| 4 | Columns | Logical column, PostgreSQL type, nullability, default, constraints, description. |
| 5 | Unique / FK / CHECK | Constraints in rule-doc terms (names pending the migration step). |
| 6 | Generated / derived fields | Stored generated columns; derived-but-never-stored facts are called out. |
| 7 | `created_at` / `updated_at` | Timestamp policy per table (PR-11). |

Only the **23 finalized tables** (14 entity/state + 9 reference/config) are
defined. Concepts the task prompt lists that the finalized model resolved as
**non-tables** (`face_profiles`, `outfits`, `media_assets`, `assistant`, …) are
mapped to their actual home in §6 — they are deliberately **not** defined as
tables.

---

## 2. Conventions (from `DATABASE_DESIGN_RULES.md`)

- **Key policy (§5, PR-3):** user-owned entity rows use `id uuid` generated
  server-side (`gen_random_uuid()`), never supplied by a client; knowledge
  reference tables use a stable `text` `code` as primary key.
- **Foreign keys (§4, PR-4):** `user_id` composition → `ON DELETE CASCADE`;
  knowledge references → `ON DELETE RESTRICT` (required) or `SET NULL`
  (deprecated/droppable); cross-links (`SavedLook.source_run_id`,
  `SavedLook.look_id`) → `ON DELETE SET NULL`.
- **JSONB (§8, PR-9):** only where justified — current-state unit payloads
  (`user_state`), immutable AI/derived snapshots (`saved_looks.snapshot`,
  `analysis_runs.result`, `style_score_records.breakdown`), and `MediaRef`
  references (`image_ref`, `input_media`). Never a query axis.
- **Media (PR-8):** PostgreSQL stores only `MediaRef` values (object key / URL +
  media type + optional display metadata); bytes live in object storage.
- **Append-only history (§10):** `learning_signals`, `style_score_records`,
  `activity_days`, `analysis_runs` (and future `today_look_records`,
  `recommendation_history`, `feedback_events`) get `INSERT`/`SELECT` only at the
  API-role grant level; `UPDATE`/`DELETE` are not granted.
- **Timestamps (PR-11):** every table has `created_at`; current-state tables also
  have `updated_at`; dated history tables use `occurred_at` / `day` /
  `recorded_at` instead of creation timestamps.
- **Types used:** `uuid`, `text`, `date`, `timestamptz`, `jsonb`, `smallint`,
  `int`, `bool`.

---

## 3. P0 tables (first vertical slice)

### TABLE: `users`

**Purpose:** the account identity (E1 `User`, aggregate root) that scopes every
user-owned row; holds the opaque external-boundary auth reference (provider +
subject) and the display name. The row exists even before auth is designed so
every other table has a `user_id` FK (`AZ12.3`).

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | Server-generated user id; never client-supplied (PR-3). |
| `auth_provider` | `text` | NOT NULL | – | | Opaque auth-provider identifier (external boundary; exact set pending auth design, §16 of the rules doc). |
| `auth_subject` | `text` | NOT NULL | – | | Provider-side subject identifier; uniqueness is the provider+subject pair. |
| `display_name` | `text` | NOT NULL | – | | User-chosen display name (registration today navigates home; no auth yet). |
| `created_at` | `timestamptz` | NOT NULL | `now()` | | Account creation time. |
| `updated_at` | `timestamptz` | NOT NULL | `now()` | | Last profile-row update; maintained by the API on write. |

**Unique constraints:** `UNIQUE (auth_provider, auth_subject)`.

**Foreign keys:** none — root of the aggregate.

**Check constraints:** `CHECK (char_length(display_name) BETWEEN 1 AND 100)`.

**Generated / derived fields:** none. Derived identity state (e.g. "is signed
in") belongs to the auth boundary, never this row.

**Timestamps:** `created_at`, `updated_at` (current state).

### TABLE: `user_state`

**Purpose:** 1:1 current-state projection of the user's profile world — the
`UserModel` blob split (P7.1). One row per `users` row, holding `style_profile`
(the Style Profile + `FaceProfile` value object + `style_type` +
`source_run_id` provenance), `preferences` (vocabulary-id lists such as
`preferred_occasions`), and `flags` (e.g. `has_saved_wardrobe_item`, F1.4).
Read/written as a unit; JSONB justified per PR-9 / rules §8.

**Primary key:** `user_id uuid` (1:1 with `users`; no separate id).

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `user_id` | `uuid` | NOT NULL | – | PK, FK → `users.id` | Owner; one state row per user. |
| `style_profile` | `jsonb` | NOT NULL | `'{}'` | | Current profile state: `face_shape`, `skin_tone`, `body_type`, `style_type` (id into `styles`), and `source_run_id` provenance (id into `analysis_runs`, P2). Shape evolves with the AI pipeline. |
| `preferences` | `jsonb` | NOT NULL | `'{}'` | | Sparse vocabulary-id lists, e.g. `preferred_occasions: ["formal", ...]`. References are ids, never copied values (K9.1). |
| `flags` | `jsonb` | NOT NULL | `'{}'` | | Sparse user/derived flags, e.g. `has_saved_wardrobe_item`. |
| `version` | `int` | NOT NULL | `0` | `CHECK (version >= 0)` | Optimistic-concurrency / migration counter for the projection. |
| `updated_at` | `timestamptz` | NOT NULL | `now()` | | Last mutation of the projection. |

**Unique constraints:** none beyond the PK (1:1 is guaranteed by PK).

**Foreign keys:** `user_id → users(id) ON DELETE CASCADE`.

**Check constraints:** `CHECK (version >= 0)`.

**Generated / derived fields:** none stored. `style_profile.source_run_id` is a
provenance link (SET NULL semantics via the parent rules; enforced at the
application layer because it lives in JSONB).

**Timestamps:** `updated_at` only — `created_at` is inherited from
`users.created_at` (row is born with the user).

### TABLE: `wardrobe_items`

**Purpose:** E2 `WardrobeItem` — one owned clothing/accessory per user (the
canonical of the 4 mirrored shapes). Queried, counted, and fed to assistant/look
scoring, so it is a normalized row, not a blob (PR-1).

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | Item id; DB owns identity (the Dart `WardrobeEntry.id` string is never reused as a key, PR-3). |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id` | Owner. |
| `name` | `text` | NOT NULL | – | `CHECK (char_length(name) BETWEEN 1 AND 100)` | Item display name. |
| `category_id` | `text` | NOT NULL | – | FK → `wardrobe_categories.code` | Mandatory category (R18). |
| `color_id` | `text` | NOT NULL | – | FK → `colors.code` | Mandatory color (R18). |
| `material_id` | `text` | NULL | – | FK → `materials.code` | Optional material/texture. |
| `is_favorite` | `bool` | NOT NULL | `false` | | Favorite flag (toggled today). |
| `image_ref` | `jsonb` | NULL | – | | `MediaRef` reference (object key/URL + media type); never the bytes (PR-8). |
| `created_at` | `timestamptz` | NOT NULL | `now()` | | |
| `updated_at` | `timestamptz` | NOT NULL | `now()` | | Maintained by the API on edit. |

**Unique constraints:** none beyond the PK.

**Foreign keys:** `user_id → users CASCADE`; `category_id → wardrobe_categories
RESTRICT`; `color_id → colors RESTRICT`; `material_id → materials RESTRICT`.

**Check constraints:** `CHECK (char_length(name) BETWEEN 1 AND 100)`.

**Generated / derived fields:** none. "Wardrobe count", "owns an item of category
X" etc. are derived queries, never stored.

**Timestamps:** `created_at`, `updated_at` (current state).

### TABLE: `saved_looks`

**Purpose:** E4 `SavedLook` — the user's durable record of keeping a look. The
*list* is current state; each *save* is a dated event with an immutable
snapshot — the only durable trace of AI output the user kept
(`AI-output-never-truth` boundary case, R31).

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | Saved-look id. |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id` | Owner. |
| `look_id` | `text` | NULL | – | FK → `looks.code` | Optional catalog reference (P0 stores reference + title); survives catalog edits (R30). |
| `title` | `text` | NOT NULL | – | `CHECK (char_length(title) BETWEEN 1 AND 200)` | Saved-look title (today only titles persist in the blob). |
| `snapshot` | `jsonb` | NOT NULL | – | | Immutable payload frozen at save time — ensemble, score, reasons (R31). Never updated once written. |
| `source_run_id` | `uuid` | NULL | – | FK → `analysis_runs.id` | Optional provenance when saved from a scan (P2; SET NULL until runs exist). |
| `created_at` | `timestamptz` | NOT NULL | `now()` | | Save time. |

**Unique constraints:** none beyond the PK.

**Foreign keys:** `user_id → users CASCADE`; `look_id → looks SET NULL`;
`source_run_id → analysis_runs SET NULL`.

**Check constraints:** `CHECK (char_length(title) BETWEEN 1 AND 200)`.

**Generated / derived fields:** none. The current "score/ensemble/reasons" of the
look live in the immutable `snapshot`; the live recommendation is never stored.

**Timestamps:** `created_at` only — the row is immutable once written (R31;
snapshot, look, title are never updated by the API).

### TABLE: `learning_signals`

**Purpose:** E7 `LearningSignal` — append-only, typed interaction history
(8 signal types: `item_added`, `analysis_updated`, `style_updated`,
`look_saved`, `occasion_preferred` + `assistant_message`,
`suggestion_opened`, `assistant_navigation`) that drives learning and feeds
the derived score/streak records. Written by `LearningService`, all features,
and the assistant.

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | Signal id. |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id` | Owner; index-leading column of all history reads. |
| `signal_type` | `text` | NOT NULL | – | FK → `signal_types.code` | One of the 8 seeded types; never a free string. |
| `label` | `text` | NOT NULL | – | `CHECK (char_length(label) BETWEEN 1 AND 200)` | Human-readable event label. |
| `context` | `jsonb` | NULL | – | | Small optional payload preserving the event's context for future read models; never a filter axis. |
| `occurred_at` | `timestamptz` | NOT NULL | – | | When the signal happened (event timestamp, not row-creation). |

**Unique constraints:** none beyond the PK.

**Foreign keys:** `user_id → users CASCADE`; `signal_type → signal_types
RESTRICT`. **Intentionally no FK to the triggering entity**
(`wardrobe_items`, `saved_looks`) — deleting current state never deletes
history (§10 rule 3).

**Check constraints:** `CHECK (char_length(label) BETWEEN 1 AND 200)`.

**Generated / derived fields:** none. Aggregated preferences are derived
queries over these rows, never stored.

**Timestamps:** `occurred_at` (append-only history; `created_at`/`updated_at`
are not used — the event time is the only timestamp). API role gets
`INSERT`/`SELECT` only (PR-5).

### TABLE: `looks`

**Purpose:** E5 `Look` — the only system-owned knowledge entity: the canonical
look catalog (title, ensemble payload, image ref, content version, deprecation)
that recommendations, discover, and `saved_looks` reference **by stable id**.
One canonical source resolves the 4 mirrored catalog shapes (K9.1).

**Primary key:** `code text` (stable natural key, backend-authored).

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `code` | `text` | NOT NULL | – | PK | Stable look id (e.g. `leather-jacket-formal`); survives re-seeds (PR-3). |
| `title` | `text` | NOT NULL | – | `CHECK (char_length(title) BETWEEN 1 AND 200)` | Catalog title. |
| `image_ref` | `jsonb` | NULL | – | | Catalog asset `MediaRef`; never the bytes (PR-8). |
| `content_version` | `text` | NOT NULL | – | | Content version for auditability/reproducibility of references. |
| `published_at` | `timestamptz` | NULL | – | | When the look went live. |
| `deprecated_at` | `timestamptz` | NULL | – | | Soft-deprecation; deprecated looks are never deleted while referenced (R30). |
| `payload` | `jsonb` | NOT NULL | `'{}'` | | The ensemble value object + occasion/style tags; rich content shape follows the K9.1 decision (§16). |
| `created_at` | `timestamptz` | NOT NULL | `now()` | | |
| `updated_at` | `timestamptz` | NOT NULL | `now()` | | Content edits by the backend. |

**Unique constraints:** none beyond the PK.

**Foreign keys:** none — system-owned knowledge; referenced **by** other tables.

**Check constraints:** `CHECK (char_length(title) BETWEEN 1 AND 200)`.

**Generated / derived fields:** none. Recommendation "match score" against this
look is computed at read time, never stored.

**Timestamps:** `created_at`, `updated_at` (backend-managed content).

## 4. P1 tables (next core features)

### TABLE: `user_events`

**Purpose:** E3 `UserEvent` — a user-created, dated event providing occasion
context (today it is widget state lost on restart). Dated and individually
editable, so rows. Also FEEDS `preferred_occasions` (R36) and seeds outfit
generation (R35).

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | Event id. |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id` | Owner. |
| `title` | `text` | NOT NULL | – | `CHECK (char_length(title) BETWEEN 1 AND 200)` | Event name. |
| `event_type_id` | `text` | NOT NULL | – | FK → `event_types.code` | Mandatory event type (R34). |
| `event_date` | `date` | NOT NULL | – | | When the event happens (date value object; not a timestamp). |
| `location` | `text` | NULL | – | | Optional free-text location. |
| `notes` | `text` | NULL | – | | Optional free-text notes. |
| `created_at` | `timestamptz` | NOT NULL | `now()` | | |
| `updated_at` | `timestamptz` | NOT NULL | `now()` | | Maintained by the API on edit. |

**Unique constraints:** none beyond the PK.

**Foreign keys:** `user_id → users CASCADE`; `event_type_id → event_types
RESTRICT`.

**Check constraints:** `CHECK (char_length(title) BETWEEN 1 AND 200)`.

**Generated / derived fields:** none. The "upcoming events" aggregation is a
query, never stored.

**Timestamps:** `created_at`, `updated_at` (current state).

### TABLE: `style_score_records`

**Purpose:** E8 `StyleScoreRecord` — dated, append-only snapshots of the
computed style score (formula 60–100; range `0–100`). The **current** score is a
derived cache; this table is its **history**, so the Home trend and Profile
history survive input changes.

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id` | Owner. |
| `score` | `smallint` | NOT NULL | – | `CHECK (score BETWEEN 0 AND 100)` | Immutable score snapshot (formula-derived, PR-5). |
| `breakdown` | `jsonb` | NULL | – | | Immutable `StyleScoreBreakdownItem` snapshot (what contributed). |
| `recorded_at` | `date` | NOT NULL | – | | The calendar day the score was recorded (trend/query axis). |
| `occurred_at` | `timestamptz` | NOT NULL | – | | Exact event time. |

**Unique constraints:** none beyond the PK (multiple records per day are
allowed; uniqueness is per-row identity).

**Foreign keys:** `user_id → users CASCADE`.

**Check constraints:** `CHECK (score BETWEEN 0 AND 100)`.

**Generated / derived fields:** none stored — `score` is written from the
formula, never recomputed in place. Append-only: API role gets
`INSERT`/`SELECT` only (PR-5).

**Timestamps:** `recorded_at`, `occurred_at` (append-only history).

### TABLE: `activity_days`

**Purpose:** E9 `ActivityDay` — one record per styled day backing the streak
timeline. The current streak is derived; this table is its immutable per-day
history.

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id` | Owner. |
| `day` | `date` | NOT NULL | – | `UNIQUE (user_id, day)` | The styled calendar day. |
| `styled` | `bool` | NOT NULL | `false` | | Whether the day counts as "styled". |
| `summary` | `jsonb` | NULL | – | | Nullable derived aggregate for the day (small). |
| `occurred_at` | `timestamptz` | NOT NULL | – | | When the day was recorded. |

**Unique constraints:** `UNIQUE (user_id, day)` — one activity row per user per
day (PR-5, §11).

**Foreign keys:** `user_id → users CASCADE`.

**Check constraints:** none beyond `UNIQUE`.

**Generated / derived fields:** none — the current streak is recomputed from
these rows (PR-2). Append-only (`INSERT`/`SELECT` only).

**Timestamps:** `occurred_at` (append-only history).

### TABLE: `today_look_records` — P1, gated by product decision

**Purpose:** conditional `Today'sLookRecord` — per-user per-day immutable
snapshot of the daily look ("what I wore" history). **Created only if** the
product decision lands; otherwise the daily look stays a derived cache and
this table is not created (PR-12, `DOMAIN_TABLE_MAPPING.md` §4.10).

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id` | Owner. |
| `day` | `date` | NOT NULL | – | `UNIQUE (user_id, day)` | The look's calendar day. |
| `snapshot` | `jsonb` | NOT NULL | – | | The daily look, frozen (ensemble + scores + reasons). |
| `occurred_at` | `timestamptz` | NOT NULL | – | | When recorded. |

**Unique constraints:** `UNIQUE (user_id, day)`.

**Foreign keys:** `user_id → users CASCADE`.

**Check constraints:** none.

**Generated / derived fields:** none — the *current* today's look is a cache;
only history is persisted here. Append-only (`INSERT`/`SELECT` only).

**Timestamps:** `occurred_at` (append-only history).

### TABLE: `feedback_events` — P1, created only when the feature lands

**Purpose:** Recommendation / Outfit Feedback — append-only user reaction
(rating / like / dislike / why) to a recommendation or saved look, closing the
learning loop (R-A13→R-A16). One concept shared by the wardrobe and general
recommendation clusters. **No table until the rating UI exists** (feature
missing — `UI_UX_GAP_REPORT.md` #17).

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id` | Owner (the event). |
| `target_look_id` | `text` | NULL | – | FK → `looks.code` | Optional target look. |
| `target_saved_look_id` | `uuid` | NULL | – | FK → `saved_looks.id` | Optional target saved look. |
| `rating` | `text` | NOT NULL | – | | Rating tag; exact vocabulary pending the feedback design (§16 of the rules doc). |
| `reason` | `text` | NULL | – | | Optional free-text "why". |
| `occurred_at` | `timestamptz` | NOT NULL | – | | When rated. |

**Unique constraints:** none beyond the PK.

**Foreign keys:** `user_id → users CASCADE`; `target_look_id → looks SET NULL`;
`target_saved_look_id → saved_looks SET NULL`.

**Check constraints:** none beyond what the feedback design defines.

**Generated / derived fields:** none. FEEDS the derived-preference loop via
aggregation, never stored as state.

**Timestamps:** `occurred_at` (append-only history; `INSERT`/`SELECT` only).

## 5. P2 and P3 tables (supporting + future)

### TABLE: `analysis_runs`

**Purpose:** E6 `AnalysisRun` — per-execution record of a scan/analysis (outfit,
face, hairstyle, grooming): durable inputs (`input_media` `MediaRef`),
immutable `result` snapshot, and `engine_version` for reproducibility (PR-6).
"AI event = reproducible history."

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id` | Owner. |
| `run_type` | `text` | NOT NULL | – | FK → `run_types.code` | outfit / face / hairstyle / grooming. |
| `status` | `text` | NOT NULL | – | `CHECK (status IN ('pending','completed','failed'))` | Lifecycle state of the run. |
| `engine_version` | `text` | NOT NULL | – | | Engine/model version so past results can be re-derived or audited (PR-6). |
| `input_media` | `jsonb` | NULL | – | | `MediaRef` to the source scan image (durable input); never the bytes (PR-8). |
| `result` | `jsonb` | NULL | – | | Immutable `AnalysisResult` snapshot; NULL until completed; never overwritten in place (PR-6). |
| `created_at` | `timestamptz` | NOT NULL | `now()` | | Run start. |
| `completed_at` | `timestamptz` | NULL | – | | Run end; NULL while pending/failed. |

**Unique constraints:** none beyond the PK.

**Foreign keys:** `user_id → users CASCADE`; `run_type → run_types RESTRICT`.

**Check constraints:** `CHECK (status IN ('pending','completed','failed'))`.

**Generated / derived fields:** none stored — the analysis result is a frozen
snapshot, re-derivable from inputs + engine version. Append-only
(`INSERT`/`SELECT` only; PR-5).

**Timestamps:** `created_at`, `completed_at` (append-only history).

### TABLE: `subscriptions`

**Purpose:** E10 `Subscription` — the user's paid entitlement state (plan,
status, period, external ref), 0..1 per user. Entitlement is **derived** from
config × this row (R45), never stored; billing is driven by an external payment
service (R51).

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id`, `UNIQUE` | At most one subscription per user (0..1, R10). |
| `plan_code` | `text` | NOT NULL | – | FK → `subscription_plans.code` | The plan; plans are knowledge content (RESTRICT). |
| `status` | `text` | NOT NULL | – | | Subscription lifecycle status; exact vocabulary set with the billing integration (open decision §16). |
| `started_at` | `timestamptz` | NOT NULL | – | | Activation time. |
| `renews_at` | `timestamptz` | NULL | – | | Next renewal; NULL for non-recurring. |
| `external_ref` | `text` | NULL | – | | Reference to the external payment/entitlement service (R51). |
| `created_at` | `timestamptz` | NOT NULL | `now()` | | |
| `updated_at` | `timestamptz` | NOT NULL | `now()` | | Maintained by the API on status/period changes. |

**Unique constraints:** `UNIQUE (user_id)` — 0..1 per user.

**Foreign keys:** `user_id → users CASCADE`; `plan_code → subscription_plans
RESTRICT`.

**Check constraints:** none beyond what the billing design defines (status
vocabulary pending).

**Generated / derived fields:** none — "is the feature available?" is derived at
read time from config × this row (PR-2, R45).

**Timestamps:** `created_at`, `updated_at` (current state).

### TABLE: `recommendation_history` — P3, gated by product decision

**Purpose:** conditional `RecommendationHistory` — immutable trace of
shown/saved recommendations (look ref + score/reasons snapshot + shown-at) for
personalization analytics. **Created only if** the P3 analytics/recall feature
is built; today only `look_saved` signals trace it (PR-12,
`DOMAIN_TABLE_MAPPING.md` §4.14).

**Primary key:** `id uuid`

**Columns:**

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `id` | `uuid` | NOT NULL | `gen_random_uuid()` | PK | |
| `user_id` | `uuid` | NOT NULL | – | FK → `users.id` | Owner. |
| `look_id` | `text` | NULL | – | FK → `looks.code` | Optional target look. |
| `snapshot` | `jsonb` | NOT NULL | – | | Score + reasons at show time (frozen). |
| `saved` | `bool` | NOT NULL | `false` | | Whether the user saved the recommendation. |
| `shown_at` | `timestamptz` | NOT NULL | – | | When shown/saved. |

**Unique constraints:** none beyond the PK.

**Foreign keys:** `user_id → users CASCADE`; `look_id → looks SET NULL`.

**Check constraints:** none.

**Generated / derived fields:** none. Append-only (`INSERT`/`SELECT` only).

**Timestamps:** `shown_at` (append-only history).

---

## 6. Reference / config tables (system knowledge, K9.1)

Backend-authored, versioned content. Either DB rows **or** versioned backend
config (the K9.1 decision); either way entities reference them **by stable
id, never by embedded value** (PR-2). Default shape for the vocabulary tables:

| Column | PostgreSQL Type | Null | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `code` | `text` | NOT NULL | – | PK | Stable, immutable natural key (e.g. `'formal'`, `'look_saved'`); survives re-seeding (PR-3). |
| `label` | `text` | NOT NULL | – | `CHECK (char_length(label) BETWEEN 1 AND 100)` | Human-readable label. |
| `sort_order` | `int` | NOT NULL | `0` | `CHECK (sort_order >= 0)` | Presentation order. |
| `active` | `bool` | NOT NULL | `true` | | Soft deactivation without deleting referenced rows. |
| `created_at` | `timestamptz` | NOT NULL | `now()` | | |
| `updated_at` | `timestamptz` | NOT NULL | `now()` | | Backend content edits. |

| Table | Purpose | Referenced by | FK rule |
| --- | --- | --- | --- |
| `wardrobe_categories` | Canonical item categories (P0) | `wardrobe_items.category_id` | RESTRICT, NOT NULL |
| `colors` | Canonical colors (P0) | `wardrobe_items.color_id` | RESTRICT, NOT NULL |
| `materials` | Canonical materials/textures (P0) | `wardrobe_items.material_id` | RESTRICT, nullable |
| `occasions` | Shared occasion list — canonical of 4 copies (P0) | `user_state.preferences` ids, `looks.payload` (JSONB) | application-level (JSONB refs, no hard FK) |
| `event_types` | Event occasion types (P0) | `user_events.event_type_id` | RESTRICT, NOT NULL |
| `styles` | Style Vibe, 6 values (P0) | `user_state.style_profile.style_type` (JSONB) | application-level (JSONB ref) |
| `signal_types` | 8 learning-signal types (P0) | `learning_signals.signal_type` | RESTRICT, NOT NULL |
| `subscription_plans` | Plan catalog (P2) | `subscriptions.plan_code` | RESTRICT, NOT NULL |
| `run_types` | Analysis run types (P2) | `analysis_runs.run_type` | RESTRICT, NOT NULL |

`subscription_plans` additionally carries the price as a **display string**
(`price_display text`, no money math) and an optional
`features jsonb` for config-driven capability names (PR-12; entitlement stays
derived, R45).

## 7. Relationships

All `user_id` FKs → `users(id)` `ON DELETE CASCADE` (user composition, PR-4).
Knowledge references are never `CASCADE`. Cross-links are `SET NULL`.

### 7.1 Composition from `users` (CASCADE)

| Parent | Child table | FK column | Notes |
| --- | --- | --- | --- |
| `users` | `user_state` | `user_id` (PK/FK) | 1:1; created/deleted with the user. |
| `users` | `wardrobe_items` | `user_id` | 1:N. |
| `users` | `saved_looks` | `user_id` | 1:N. |
| `users` | `learning_signals` | `user_id` | 1:N, append-only. |
| `users` | `user_events` | `user_id` | 1:N (P1). |
| `users` | `style_score_records` | `user_id` | 1:N, append-only (P1). |
| `users` | `activity_days` | `user_id` | 1:N, append-only, `UNIQUE(user_id,day)` (P1). |
| `users` | `today_look_records` | `user_id` | 1:N, append-only, `UNIQUE(user_id,day)` (P1, conditional). |
| `users` | `feedback_events` | `user_id` | 1:N, append-only (P1, feature-gated). |
| `users` | `analysis_runs` | `user_id` | 1:N, append-only (P2). |
| `users` | `subscriptions` | `user_id` | 1:0..1, `UNIQUE(user_id)` (P2). |
| `users` | `recommendation_history` | `user_id` | 1:N, append-only (P3, conditional). |

### 7.2 Knowledge references (RESTRICT / SET NULL)

| Child | Column | → Table | Rule |
| --- | --- | --- | --- |
| `wardrobe_items` | `category_id` | `wardrobe_categories(code)` | RESTRICT, NOT NULL (R18) |
| `wardrobe_items` | `color_id` | `colors(code)` | RESTRICT, NOT NULL (R18) |
| `wardrobe_items` | `material_id` | `materials(code)` | RESTRICT, nullable |
| `user_events` | `event_type_id` | `event_types(code)` | RESTRICT, NOT NULL (R34) |
| `learning_signals` | `signal_type` | `signal_types(code)` | RESTRICT, NOT NULL |
| `subscriptions` | `plan_code` | `subscription_plans(code)` | RESTRICT, NOT NULL |
| `analysis_runs` | `run_type` | `run_types(code)` | RESTRICT, NOT NULL |
| `saved_looks` | `look_id` | `looks(code)` | SET NULL (deprecation-safe, R30) |
| `feedback_events` | `target_look_id` | `looks(code)` | SET NULL |
| `recommendation_history` | `look_id` | `looks(code)` | SET NULL (P3) |

`occasions` and `styles` are referenced **inside JSONB** (`user_state.preferences`,
`user_state.style_profile`, `looks.payload`), so no hard FK exists — the
application layer enforces stable ids (K9.1; JSONB is never a query axis).

### 7.3 Cross-links between user entities (SET NULL)

| Child | Column | → Table | Rule | Notes |
| --- | --- | --- | --- | --- |
| `saved_looks` | `source_run_id` | `analysis_runs(id)` | SET NULL | provenance; deleting current state never deletes history (P2). |
| `feedback_events` | `target_saved_look_id` | `saved_looks(id)` | SET NULL | target may be removed (P1, feature-gated). |
| `user_state` | `style_profile.source_run_id` (JSONB) | `analysis_runs(id)` | application-level | provenance inside JSONB (P2). |

### 7.4 Explicitly absent

- **No FK from `learning_signals` to any current-state entity** — history
  survives item/event/saved-look deletion (§10 rule 3).
- **No media table and no FK to object storage** — only `MediaRef` JSONB
  reference columns (PR-8).
- **No FK into `occasions`/`styles` from JSONB columns** — enforced in code.

---

## 8. Requested concepts → actual homes (finalized domain model)

The task's suggested list is honored as follows. Every concept that the
finalized model resolved as a **non-table** is mapped to where it actually
lives; **none** is added as a speculative table (PR-12).

| Requested concept | Finalized table? | Actual home |
| --- | --- | --- |
| `users` | yes | **`users`** (P0) |
| `user_profiles` | no | `user_state` (P0) — 1:1 projection |
| `user_preferences` | no | `user_state.preferences` JSONB |
| `style_profiles` | no | `user_state.style_profile` JSONB |
| `face_profiles` | no | value object inside `user_state.style_profile` (P7.1; `setFace` uncalled today) |
| `hair_profiles` | no | PLANNED — no table until a hair pipeline lands (P1) |
| `grooming_profiles` | no | PLANNED — no table until a grooming pipeline lands (P1) |
| `appearance capabilities` | no | system config; availability derived (never rows) |
| `media_assets` | no | object storage behind `MediaRef` columns (`image_ref`, `input_media`); bytes never in PostgreSQL (PR-8) |
| `scans` | no (renamed) | **`analysis_runs`** (P2) is the scan/analysis run |
| `scan results` | no | `analysis_runs.result` JSONB (immutable snapshot) |
| `wardrobe` | no (renamed) | **`wardrobe_items`** (P0); the collection is derived |
| `outfits` | no | value object embedded in `looks.payload` / `saved_looks.snapshot` |
| `recommendations` | no | AI output — regenerable, never truth; occurrence = `recommendation_history` (P3, conditional) |
| `recommendation reasons` | no | value objects snapshotted in `saved_looks.snapshot` |
| `feedback` | no (renamed + gated) | **`feedback_events`** (P1, only when the rating UI lands) |
| `saved looks` | yes | **`saved_looks`** (P0) |
| `events` | no (renamed) | **`user_events`** (P1) |
| `daily outfits` | no | derived cache; history = `today_look_records` (P1, conditional) |
| `assistant` | no | conversations transient; DTOs are wire contract; actions are config; assistant activity traced via `learning_signals` |
| `subscriptions` | yes | **`subscriptions`** (P2) |

---

## 9. Report — summary

- **23 logical tables defined** (no SQL): 14 entity/state tables (P0 `users`,
  `user_state`, `wardrobe_items`, `saved_looks`, `learning_signals`, `looks`;
  P1 `user_events`, `style_score_records`, `activity_days` + conditional
  `today_look_records`, `feedback_events`; P2 `analysis_runs`, `subscriptions`;
  P3 conditional `recommendation_history`) + 9 reference/config tables.
- **Every definition** carries purpose, primary key, typed columns with
  null/default/constraints, unique/FK/CHECK constraints, generated/derived
  fields, and the timestamp policy — in the exact format the task requested.
- **Constraints encoded:** `UNIQUE (auth_provider, auth_subject)`,
  `UNIQUE (user_id)` on `subscriptions`, `UNIQUE (user_id, day)` on
  `activity_days`/`today_look_records`, `CHECK (score BETWEEN 0 AND 100)`,
  `CHECK (status IN (...))` where the vocabulary is stable, `ON DELETE
  CASCADE` for user composition, `RESTRICT`/`SET NULL` for knowledge and
  cross-links.
- **Append-only enforced** at the grant level for all history tables
  (`INSERT`/`SELECT` only); current-state tables keep `updated_at`.
- **Derived facts are never stored:** current score/streak/today's look, style
  DNA, insights, match scores, entitlements — all recomputed; only their
  immutable snapshots persist.
- **Consistent with `DOMAIN_TABLE_MAPPING.md` and `DATABASE_DESIGN_RULES.md`:**
  identical table names, phasing, JSONB columns, lifecycle rules, and key
  policy. Nothing invented beyond the finalized domain model.

---

## Constraints honored

- No SQL written, no PostgreSQL database created, no migrations, no
  repositories, no endpoints.
- No Flutter, routing, UI, or backend code changes; no dependencies; nothing
  deleted.
- Only tables **supported by the finalized domain model** are defined; every
  requested concept is mapped to its home, and non-table concepts are
  documented, not silently dropped.
- The real Fansivibe repository is the source of truth; the separate reference
  project was not merged.





