# Fansivibe — Index Strategy

> **STEP 4 (continuation) — DATABASE DESIGN.** Defines the PostgreSQL **indexing
> strategy** grounded in the **actual access patterns** discovered in
> `FEATURE_DATA_MATRIX.md`, `ACTION_API_INVENTORY.md`, and
> `DOMAIN_RELATIONSHIPS.md`. Each index specifies table, columns, index type,
> the query it accelerates, reason, expected selectivity, and uniqueness.
>
> **Status: documentation only. No indexes are created, no SQL, no PostgreSQL
> database, no migrations, no repositories, no endpoints, no application code
> changes, nothing deleted.**
>
> **Sources:** `FEATURE_DATA_MATRIX.md` (what each feature reads/displays per
> user), `ACTION_API_INVENTORY.md` (the future backend operations and their
> lookups), `DOMAIN_RELATIONSHIPS.md` (R1–R51 cardinalities and scoping),
> plus the prior STEP 4 docs (`TABLE_DEFINITIONS.md`, `RELATIONSHIP_CONSTRAINTS.md`,
> `HISTORY_AND_VERSIONING.md`, `JSONB_STRATEGY.md`, `DATABASE_DESIGN_RULES.md`
> §12 baseline indexing).

---

## 1. Purpose and method

Every user-owned access in this product is **scoped by `user_id`** (PR-10); every
list access is **ordered by a date** (`created_at`, `occurred_at`, `day`,
`event_date`, `shown_at`); every detail access is **by id + user_id**. The
strategy is therefore: **composite btree indexes whose leading column is
`user_id`** on each user-owned table, matching the observed query shapes.

For each proposed index, the eight attributes the task requires:

| # | Attribute | Meaning |
| --- | --- | --- |
| 1 | Table | The table the index is on. |
| 2 | Columns | Column(s) and order. |
| 3 | Index type | PostgreSQL index type (all btree here). |
| 4 | Query it accelerates | The concrete future operation/access it serves (with source). |
| 5 | Reason | Why the column shape is the right one (from the access pattern). |
| 6 | Expected selectivity | Rough rows matched per query (high = few rows). |
| 7 | Unique? | Whether the index enforces a uniqueness constraint. |

**Principle (PR-12):** start minimal, add with measured queries. Every index
below maps to an **observed or derived access pattern**; candidates that do not
are listed in §6 as deliberately **not** created.

---

## 2. The discovered access patterns

Real queries extracted from the three sources — each proposed index exists to
serve at least one of these.

| # | Access pattern | Source | Served by |
| --- | --- | --- | --- |
| A1 | Auth lookup: register/login by provider+subject | `ACTION_API_INVENTORY.md` #1–3 | `users (auth_provider, auth_subject)` UNIQUE |
| A2 | "My wardrobe" list + insight aggregation | `FEATURE_DATA_MATRIX.md` §3; #5, #8 | `wardrobe_items (user_id)` |
| A3 | Wardrobe grid **by category** | `FEATURE_DATA_MATRIX.md` §3 "item grid by category" | `wardrobe_items (user_id, category_id)` |
| A4 | Item detail / favorite / edit/delete by id | `ACTION_API_INVENTORY.md` #6–7 | PK `id` (+ user_id in the WHERE) |
| A5 | Saved-looks list (ordered newest-first) | Profile; #12/14/17 → `POST /looks/saved` | `saved_looks (user_id, created_at)` |
| A6 | Learning feed / signal aggregation | `FEATURE_DATA_MATRIX.md` §13; `DOMAIN_RELATIONSHIPS.md` R41–R42 | `learning_signals (user_id, occurred_at)` |
| A7 | Score trend on Home/Profile | `FEATURE_DATA_MATRIX.md` §2 "style-score history"; R43 | `style_score_records (user_id, recorded_at)` |
| A8 | Streak computation (per-day) | `FEATURE_DATA_MATRIX.md` §2 "streak"; R9 | `activity_days (user_id, day)` UNIQUE |
| A9 | Event list (upcoming, by date) | `FEATURE_DATA_MATRIX.md` §11; #9–11 | `user_events (user_id, event_date)` |
| A10 | Scans by user/date; latest analysis of a type | #16/21/23; R15 latest-wins provenance | `analysis_runs (user_id, created_at)` + `(user_id, run_type, created_at)` |
| A11 | Subscription status by user (0..1) | #30; R10 | `subscriptions (user_id)` UNIQUE |
| A12 | Feedback by user (feature-gated) | #31; R27 | `feedback_events (user_id, occurred_at)` |
| A13 | Recommendation trace by user/date (P3) | §6 Discover; R-A16 | `recommendation_history (user_id, shown_at)` |
| A14 | Today's-look history by user/day (P1) | `HISTORY_AND_VERSIONING.md` §5.11 | `today_look_records (user_id, day)` UNIQUE |
| A15 | Latest profile state (point read) | `FEATURE_DATA_MATRIX.md` §12; R1 | `user_state` PK `user_id` (no extra index) |

Explicitly **not** a table/query today: **assistant conversations** (transient,
retention undecided — no table, hence no index, §6).

---

## 3. Proposed index catalog

All indexes are **btree** (PostgreSQL default; covers equality + range + order
by). Existing PK/UNIQUE constraints already provide their own indexes and are
listed for completeness (marked "implicit").

| Table | Columns | Type | Accelerates | Unique |
| --- | --- | --- | --- | --- |
| `users` | `(auth_provider, auth_subject)` | btree | A1 auth lookup | **Yes** (UNIQUE constraint) |
| `wardrobe_items` | `(user_id)` | btree | A2 my-wardrobe list + insight | No |
| `wardrobe_items` | `(user_id, category_id)` | btree | A3 wardrobe grid by category | No |
| `saved_looks` | `(user_id, created_at)` | btree | A5 saved-looks list, newest first | No |
| `learning_signals` | `(user_id, occurred_at)` | btree | A6 learning feed + aggregation | No |
| `style_score_records` | `(user_id, recorded_at)` | btree | A7 score trend | No |
| `activity_days` | `(user_id, day)` | btree | A8 streak + per-day uniqueness | **Yes** (UNIQUE constraint) |
| `user_events` | `(user_id, event_date)` | btree | A9 event list by date | No |
| `analysis_runs` | `(user_id, created_at)` | btree | A10 scans by user/date | No |
| `analysis_runs` | `(user_id, run_type, created_at)` | btree | A10 latest analysis of a type (provenance) | No |
| `subscriptions` | `(user_id)` | btree | A11 subscription status | **Yes** (UNIQUE constraint) |
| `feedback_events` | `(user_id, occurred_at)` | btree | A12 feedback (feature-gated) | No |
| `recommendation_history` | `(user_id, shown_at)` | btree | A13 trace (P3, conditional) | No |
| `today_look_records` | `(user_id, day)` | btree | A14 per-day history (P1, conditional) | **Yes** (UNIQUE constraint) |

Implicit indexes (PKs — no extra index created): `users.id`,
`user_state.user_id`, `wardrobe_items.id`, `saved_looks.id`,
`learning_signals.id`, `user_events.id`, `style_score_records.id`,
`activity_days.id`, `analysis_runs.id`, `subscriptions.id`, and the `code` PKs
of `looks` + all 9 reference tables (vocabulary lookups, A4/A-vocab).

---

## 4. Per-index detail

### 4.1 `users (auth_provider, auth_subject)` — UNIQUE btree

- **Columns:** `auth_provider`, `auth_subject` (composite).
- **Index type:** btree (backing the `UNIQUE` constraint).
- **Query it accelerates:** auth register/login — find-or-create by the opaque
  provider identity (A1; `ACTION_API_INVENTORY.md` #1–3).
- **Reason:** identity is a fact (R1); the pair is the external-boundary key and
  must be unique (PR-5).
- **Expected selectivity:** very high — matches at most **1 row**.
- **Unique:** **yes** (enforces uniqueness; also the login lookup).

### 4.2 `wardrobe_items (user_id)` — btree

- **Columns:** `user_id` only.
- **Index type:** btree.
- **Query it accelerates:** "my wardrobe" list and the wardrobe-insight
  aggregation over a user's items (A2; `FEATURE_DATA_MATRIX.md` §3, #5/#8).
- **Reason:** every wardrobe access is user-scoped; `user_id` is the leading
  column of all wardrobe reads (PR-10, R3).
- **Expected selectivity:** moderate — a small slice of the global table per
  user (typically dozens of rows).
- **Unique:** no.

### 4.3 `wardrobe_items (user_id, category_id)` — btree

- **Columns:** `user_id`, `category_id`.
- **Index type:** btree.
- **Query it accelerates:** the wardrobe grid filtered **by category** (A3;
  `FEATURE_DATA_MATRIX.md` §3 "item grid by category"); also category counts.
- **Reason:** the grid groups items by category; the composite matches the
  `WHERE user_id = ? AND category_id = ?` shape exactly (R18).
- **Expected selectivity:** high — a small subset of one user's items.
- **Unique:** no.

### 4.4 `saved_looks (user_id, created_at)` — btree

- **Columns:** `user_id`, `created_at`.
- **Index type:** btree (serves a `DESC` scan for newest-first).
- **Query it accelerates:** the saved-looks list, ordered newest-first (A5;
  Profile saved-looks section; `POST /looks/saved` in #12/14/17).
- **Reason:** the list is the primary saved-look access and is always user-
  scoped + date-ordered; the composite gives both without a sort.
- **Expected selectivity:** moderate — one user's saves (small list).
- **Unique:** no.

### 4.5 `learning_signals (user_id, occurred_at)` — btree

- **Columns:** `user_id`, `occurred_at`.
- **Index type:** btree (DESC-capable).
- **Query it accelerates:** the learning feed and the aggregation that feeds
  scores/streak/preferences (A6; `FEATURE_DATA_MATRIX.md` §13, R41–R42).
- **Reason:** signals are the append-only history of a user's activity; all
  aggregation reads them per user over time (PR-5 append-only, §10).
- **Expected selectivity:** moderate-low — a time-bounded slice of a per-user
  event stream.
- **Unique:** no.

### 4.6 `style_score_records (user_id, recorded_at)` — btree

- **Columns:** `user_id`, `recorded_at`.
- **Index type:** btree.
- **Query it accelerates:** the style-score trend on Home/Profile (A7;
  `FEATURE_DATA_MATRIX.md` §2; R43).
- **Reason:** the trend reads dated snapshots per user in order; the composite
  covers the full history scan and the `UNIQUE (user_id, day)`-style range.
- **Expected selectivity:** moderate — dated per-user snapshots.
- **Unique:** no (multiple records per day allowed).

### 4.7 `activity_days (user_id, day)` — UNIQUE btree

- **Columns:** `user_id`, `day`.
- **Index type:** btree (backing the `UNIQUE` constraint).
- **Query it accelerates:** streak computation and the per-day styled check (A8;
  `FEATURE_DATA_MATRIX.md` §2, R9).
- **Reason:** one activity row per user per day is a business invariant
  (PR-5, §11); the unique index both enforces it and serves the streak scan.
- **Expected selectivity:** very high — at most **1 row** per `(user_id, day)`.
- **Unique:** **yes.**

### 4.8 `user_events (user_id, event_date)` — btree

- **Columns:** `user_id`, `event_date`.
- **Index type:** btree.
- **Query it accelerates:** the event list, sorted by date, and "upcoming
  events" (A9; `FEATURE_DATA_MATRIX.md` §11; #9–11).
- **Reason:** events are dated, user-scoped rows; the composite serves the list
  in date order and the upcoming-event range (R4, R34).
- **Expected selectivity:** moderate — few events per user.
- **Unique:** no.

### 4.9 `analysis_runs (user_id, created_at)` — btree

- **Columns:** `user_id`, `created_at`.
- **Index type:** btree (DESC-capable).
- **Query it accelerates:** scans by user/date — the scan/analysis history
  (A10; #16/21/23; R6).
- **Reason:** every analysis read is user-scoped and date-ordered; the composite
  is the scan-history access (append-only, PR-6).
- **Expected selectivity:** moderate-low — a user's run history over time.
- **Unique:** no.

### 4.10 `analysis_runs (user_id, run_type, created_at)` — btree

- **Columns:** `user_id`, `run_type`, `created_at`.
- **Index type:** btree.
- **Query it accelerates:** "latest completed analysis of a type" — the
  **latest-wins** projection that sets `user_state.style_profile.source_run_id`
  (A10; R15; `HISTORY_AND_VERSIONING.md` §5).
- **Reason:** the provenance path needs the newest run per `run_type` for a
  user; the composite makes that a bounded lookup instead of a full history
  scan.
- **Expected selectivity:** high — the newest run of one type for one user.
- **Unique:** no (many runs per user/type; the index is non-unique).

### 4.11 `subscriptions (user_id)` — UNIQUE btree

- **Columns:** `user_id`.
- **Index type:** btree (backing the `UNIQUE` constraint).
- **Query it accelerates:** subscription status / entitlement check (A11; #30;
  R10).
- **Reason:** 0..1 subscription per user is a business invariant (PR-5, §11);
  the unique index enforces it and gives an O(1) status lookup.
- **Expected selectivity:** very high — at most **1 row**.
- **Unique:** **yes.**

### 4.12 `feedback_events (user_id, occurred_at)` — btree (feature-gated)

- **Columns:** `user_id`, `occurred_at`.
- **Index type:** btree.
- **Query it accelerates:** a user's feedback history and its aggregation into
  derived preference state (A12; #31 — the missing feature; R27).
- **Reason:** feedback is append-only, user-owned event history; aggregation is
  per user over time (PR-7, §10).
- **Expected selectivity:** moderate-low — per-user event stream.
- **Unique:** no. **Created only when the `feedback_events` table is created**
  (feature lands; PR-12).

### 4.13 `recommendation_history (user_id, shown_at)` — btree (P3, conditional)

- **Columns:** `user_id`, `shown_at`.
- **Index type:** btree (DESC-capable).
- **Query it accelerates:** the shown/saved recommendation trace by user/date
  (A13; `FEATURE_DATA_MATRIX.md` §6; R-A16).
- **Reason:** the trace is append-only, user-scoped, date-ordered — the exact
  analytics shape (PR-6, §10).
- **Expected selectivity:** moderate-low.
- **Unique:** no. **Created only if the P3 `recommendation_history` decision
  lands** (PR-12).

### 4.14 `today_look_records (user_id, day)` — UNIQUE btree (P1, conditional)

- **Columns:** `user_id`, `day`.
- **Index type:** btree (backing the `UNIQUE` constraint).
- **Query it accelerates:** the per-user/per-day daily-look history (A14;
  `HISTORY_AND_VERSIONING.md` §5.11).
- **Reason:** one "what I wore" row per user per day is the invariant; the
  unique index enforces it and serves the daily history scan.
- **Expected selectivity:** very high — at most **1 row** per `(user_id, day)`.
- **Unique:** **yes.** **Created only when the P1 table is created.**

### 4.15 Latest profile data (`user_state`) — no extra index

- `user_state` is keyed by `user_id` (PK/FK, 1:1). Reading the **latest profile
  state** is a single-row point read on the PK (A15; R1); no additional index.
- The **current score / streak / today's look** are derived **caches**, not
  tables — they have no index (and no row) to index (`HISTORY_AND_VERSIONING.md`
  §4).

---

## 5. Unique indexes also enforce constraints

Three of the four unique indexes are **business invariants** from
`DATABASE_DESIGN_RULES.md` §11, not just access aids:

- `users (auth_provider, auth_subject)` — auth identity is unique.
- `activity_days (user_id, day)` — one activity row per user per day.
- `today_look_records (user_id, day)` — one daily-look row per user per day
  (conditional).
- `subscriptions (user_id)` — at most one subscription per user (0..1, R10).

The uniqueness is therefore created **with the constraint** (in the migration),
and the same btree serves the reads.

---

## 6. Deliberately NOT indexed (avoid speculative indexes, PR-12)

| Candidate | Why rejected |
| --- | --- |
| GIN on any JSONB (`snapshot`, `result`, `payload`, `style_profile`, …) | every approved JSONB column is explicitly a **non-query axis** (`JSONB_STRATEGY.md` §6); a GIN would invite JSONB-as-query abuse |
| `wardrobe_items (user_id, is_favorite)` | no dedicated favorites-filter screen or endpoint exists today (#6 is a point update by id); add only when a favorites view appears |
| `user_events.event_type_id` / `learning_signals.signal_type` / `analysis_runs.run_type` / `run_type`-alone indexes | small vocabularies (≤8 values) with **low selectivity**; covered by the composite indexes |
| `analysis_runs.status` alone | small enum (`pending/completed/failed`); low selectivity; no status-only query |
| `looks` occasion/style tags via GIN on `payload` | catalog is small and backend-filtered; if it grows, **promote tags to relational columns** (additive migration) instead of indexing JSONB (`JSONB_STRATEGY.md` §6) |
| **Assistant conversations** | conversations are **transient** — no table exists, so no index. If conversation retention is ever decided (open question), a `(user_id, created_at)` index would be added **with that table** — never before |
| `feedback_events (user_id, target_look_id)` | feature-gated; the per-user history index (§4.12) covers the aggregation; target-side grouping is added only if a measured need appears |
| Indexes on conditional tables (`recommendation_history`, `today_look_records`, `feedback_events`) | created **only with their tables** (P1/P3/feature decisions; PR-12) — no schema objects before the decision |

**Rule:** no index exists without a query that exercises it today or is
deterministically required by a decided feature. Indexes are added by **additive
migration** (PR-11) when a measured query needs them.

---

## 7. Indexing vs JSONB — the boundary

All query axes are **relational columns**, never JSONB fields:

- List/history queries filter and order on `user_id`, `created_at`,
  `occurred_at`, `recorded_at`, `event_date`, `day`, `shown_at`, `run_type`,
  `category_id` — all typed columns with btree indexes.
- JSONB payloads (`result`, `snapshot`, `style_profile`, …) are read whole with
  their row; **no GIN, no JSON-path filter** is ever the primary access
  (`JSONB_STRATEGY.md` §2.2, §6).
- If a future feature needs to filter inside a payload, the fix is to
  **promote the field to a column** (additive migration), never to index the
  JSONB.

---

## 8. Report — summary

- **14 indexes defined** (10 user-scoped btree, 4 unique) plus the implicit
  PK/`code` indexes — each traced to an actual access pattern from
  `FEATURE_DATA_MATRIX.md`, `ACTION_API_INVENTORY.md`, or
  `DOMAIN_RELATIONSHIPS.md` (§2 A1–A15).
- **The shape is uniform:** composite btree with `user_id` leading, ordered by
  the date/taxonomy column of the read — matching "user-owned records" and the
  date-ordered lists that dominate the product.
- **Task considerations resolved:** user-owned records (every composite),
  latest profile data (`user_state` PK point-read; `analysis_runs
  (user_id, run_type, created_at)` latest-wins), scans by user/date
  (`analysis_runs (user_id, created_at)`), recommendations by user/date
  (`recommendation_history (user_id, shown_at)`), saved looks
  (`saved_looks (user_id, created_at)`), wardrobe filtering
  (`wardrobe_items (user_id, category_id)`), event lookup
  (`user_events (user_id, event_date)`), feedback (`feedback_events
  (user_id, occurred_at)`), subscription status (`subscriptions (user_id)`
  UNIQUE), and assistant conversations (**not indexed — no table**, transient).
- **No speculative indexes:** GIN/JSONB, low-selectivity single columns,
  favorites, conditional-table indexes, and conversation tables are all
  explicitly deferred (§6).
- **Consistent with the whole STEP 4 set:** same tables/columns as
  `TABLE_DEFINITIONS.md`, same scoping as `RELATIONSHIP_CONSTRAINTS.md`, same
  snapshot/retention semantics as `HISTORY_AND_VERSIONING.md`, same JSONB
  boundary as `JSONB_STRATEGY.md`, and extends `DATABASE_DESIGN_RULES.md` §12.

---

## Constraints honored

- No SQL, no indexes created, no PostgreSQL database, no migrations, no
  repositories, no endpoints, no application code changes, no dependencies,
  nothing deleted.
- Every index maps to an access pattern found in the three named sources; no
  speculative index is proposed (PR-12).
- The real Fansivibe repository is the source of truth; the separate reference
  project was not merged.


