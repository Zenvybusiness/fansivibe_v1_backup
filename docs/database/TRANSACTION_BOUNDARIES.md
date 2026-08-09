# Fansivibe — Transaction Boundaries

> **STEP 4 (continuation) — DATABASE DESIGN.** Identifies the **operations that
> require PostgreSQL transactions**: the units of work that must be atomic so
> that Fansivibe state never becomes partially written. For every transaction:
> **operation**, **tables involved**, **required atomicity**, **failure
> behavior**, and **consistency requirement**.
>
> **Status: documentation only. No transactions are implemented, no SQL is
> written, no PostgreSQL database is created, no migrations, no repositories, no
> endpoints, no application code changes, nothing deleted.**
>
> **Sources:** `TABLE_DEFINITIONS.md` (the 23 logical tables), `BUSINESS_
> CONSTRAINTS.md` (BC-1…BC-51), `RELATIONSHIP_CONSTRAINTS.md` (FK lifecycle
> semantics), `HISTORY_AND_VERSIONING.md` (the "never destroy an analysis"
> invariant), `MEDIA_STORAGE_DESIGN.md` (blob lifecycle), `JSONB_STRATEGY.md`
> (snapshot payloads), `DATABASE_DESIGN_RULES.md` (PR-4/PR-5/PR-6/PR-10), and
> `SECURITY_PRIVACY_DESIGN.md` (erasure).

---

## 1. Purpose and method

The task asks for the operations that need a **transaction** — a unit of work
that either fully commits or fully rolls back — and, for each, its operation,
tables, atomicity requirement, failure behavior, and consistency requirement.

Method:

1. **Start from the single-write primitive.** PostgreSQL gives atomicity for a
   **single statement on a single row** for free (row-level MVCC). A
   *transaction* is required only when a logical operation must write **more
   than one row**, or **more than one table**, and all-or-nothing is required.
   This catalog therefore distinguishes *trivially atomic* writes (single-row)
   from *true transactions* (multi-row/multi-table).
2. **Map each logical operation** to the tables it touches in
   `TABLE_DEFINITIONS.md`, using the relationship lifecycle
   (`RELATIONSHIP_CONSTRAINTS.md`), the history rules (`HISTORY_AND_
   VERSIONING.md` §7), and the media lifecycle (`MEDIA_STORAGE_DESIGN.md` §7).
3. **Name the atomicity boundary precisely** — which statements must be in one
   transaction, and what is deliberately left out (object storage, external
   services, derived caches).
4. **State failure behavior** (what a rollback leaves behind and how the app
   recovers) and **consistency requirement** (the invariant the transaction
   guarantees, cross-referenced to `BUSINESS_CONSTRAINTS.md` and the
   append-only rules).

### 1.1 Scope

- **In scope:** every operation that writes durable user state in the schema
  (P0–P3, including the conditional tables). Both the prompt's eight examples
  and the canonical writes they imply.
- **Out of scope:** implementation (no `BEGIN`/`COMMIT` anywhere yet),
  isolation-level tuning, and anything non-durable (caches, derived views,
  in-flight processing state).
- **Boundary rule (§2):** object-storage blobs and external-service calls
  (payment, weather, auth) can **never** join a PostgreSQL transaction. The DB
  transaction covers only relational rows; everything else is coordinated
  around it at the application layer.

---

## 2. The atomicity model

### 2.1 What a Fansivibe transaction can contain

| Yes — inside a DB transaction | No — must stay outside |
| --- | --- |
| `INSERT`/`UPDATE`/`DELETE` of user-owned and knowledge rows | Object-storage blob upload/delete (async cleanup job; `MEDIA_STORAGE_DESIGN.md` §7) |
| Multi-row writes needed for one logical unit (e.g. run + signal) | External service calls (payment/entitlement R51, weather, auth) |
| The `DELETE users` cascade (erasure) | Derived caches (current score, today's look, entitlements — recomputable) |

**Why media is outside:** the DB stores only `MediaRef` references (PR-8); the
bytes live in object storage. A transaction cannot span two systems. The blob
is uploaded *before* the row insert (so the reference never dangles), and
deleted *after* the row delete by an async cleanup job. Ordering is an
application concern, not a transaction one.

### 2.2 Two tiers of atomicity

1. **Trivially atomic (no explicit transaction needed):** a single-row write.
   PostgreSQL already guarantees the row is never partially visible. Examples:
   recording one `learning_signals` row, updating one `user_state` projection.
2. **True transaction (multi-row or multi-table):** a logical operation that
   must write several rows in one all-or-nothing unit. These are the catalog's
   main entries. A single `UPDATE` on a JSONB column still counts as tier 1 —
   the whole JSONB document is one value.

### 2.3 The append-only rule shapes transactions

History tables (`learning_signals`, `style_score_records`, `activity_days`,
`analysis_runs`, + conditional history) are `INSERT`/`SELECT` only
(`TABLE_DEFINITIONS.md` §2; rules-doc §10 rule 1). Consequences:

- A transaction **never** `UPDATE`s or `DELETE`s a history row — the only
  mutations allowed are `INSERT`s (and, for `analysis_runs`, the single
  guarded completion write described in TRX-5).
- "Deleting current state never deletes history" (BC-41): deleting a wardrobe
  item or saved look must **not** be in a transaction that touches history
  beyond adding a signal.
- Where a current-state write and a history trace belong together (e.g. "save
  a look" + its `look_saved` signal), they go in **one** transaction so the
  trace can never be missing from a successful save.

### 2.4 Cross-references used below

- BC-* = `BUSINESS_CONSTRAINTS.md` rule ids.
- R# = `DOMAIN_RELATIONSHIPS.md` relationship.
- §7 = `HISTORY_AND_VERSIONING.md` "never destroy an analysis" invariant.

---

## 3. Master transaction catalog

### TRX-1 — Creating a wardrobe item and its media reference

| Attribute | Detail |
| --- | --- |
| **Operation** | User adds an item to the wardrobe, optionally with a photo. |
| **Tables involved** | `wardrobe_items` (one row; `image_ref` JSONB is part of the same row). Blob upload to object storage is **outside** the transaction. |
| **Required atomicity** | The single `INSERT` is atomic by itself (tier 1). No multi-table unit exists: the item row carries its whole `MediaRef`. The blob must be uploaded **before** the `INSERT` (so the reference never dangles); if the `INSERT` then fails, the uploaded blob is orphaned and swept by the cleanup job. |
| **Failure behavior** | `INSERT` fails (e.g. invalid `category_id`/`color_id` FK, BC-29/BC-30, or duplicate) → no row, nothing to clean in the DB; an already-uploaded blob is removed by the async sweep. App returns a typed error; user retries. |
| **Consistency requirement** | The row references existing vocabulary codes (BC-29/BC-30/BC-31); `image_ref` points at an object the user owns (PR-10, `users/{user_id}/wardrobe/{item_id}`); exactly one owner (BC-18). |

### TRX-2 — Creating an outfit and outfit items

| Attribute | Detail |
| --- | --- |
| **Operation** | Composing an outfit (ensemble + items) for a look. |
| **Tables involved** | **None as separate rows** — the domain resolved outfits and outfit-items to **value objects** inside `looks.payload` (catalog) or `saved_looks.snapshot` (user save), not tables (`TABLE_DEFINITIONS.md` §8: `outfits` → value object; BC-56). |
| **Required atomicity** | The outfit + its items are **one JSONB document**, written atomically with the single row that owns it (tier 1). No outfit/outfit_items tables exist, so no multi-table transaction is possible or needed (PR-12). |
| **Failure behavior** | The single row insert/update fails or commits as a unit; the JSONB payload can never be half-written. Membership validation (items belong to the wardrobe) is domain-layer (BC-56). |
| **Consistency requirement** | An outfit never exists without its items and vice versa — guaranteed by construction because they are one value. |

### TRX-3 — Saving a recommendation (saved look)

| Attribute | Detail |
| --- | --- |
| **Operation** | User saves a recommendation/look → durable `saved_looks` row + its `look_saved` trace signal. |
| **Tables involved** | `saved_looks` (row: `look_id`, `title`, immutable `snapshot`, `source_run_id`); `learning_signals` (`look_saved` signal); optionally `recommendation_history` (P3: set `saved=true`). |
| **Required atomicity** | **True transaction.** The `INSERT saved_looks` and the `INSERT learning_signals(look_saved)` must commit together: a saved look without its trace is a silent learning gap; a `look_saved` signal without a saved look is noise. When `recommendation_history` exists (P3), flipping its `saved` flag goes in the same unit. |
| **Failure behavior** | Any statement fails (e.g. FK on `look_id` → `SET NULL`, BC-36; snapshot too large) → full rollback: no saved look, no signal. App returns a typed error; user retries. |
| **Consistency requirement** | A save always leaves exactly one `saved_looks` row (repeat saves allowed, BC-6) + exactly one matching `look_saved` signal; `snapshot` is immutable once written (R31); `source_run_id` is a `SET NULL` provenance link (BC-37). |

### TRX-4 — Creating a recommendation and its reasons

| Attribute | Detail |
| --- | --- |
| **Operation** | Producing a recommendation with its scoring/reasons. |
| **Tables involved** | **No recommendation table exists** — recommendations are regenerable AI output, never truth (`TABLE_DEFINITIONS.md` §8; `recommendation_history.snapshot` is the only persisted trace, P3). Reasons are value objects inside the snapshot. |
| **Required atomicity** | The recommendation + reasons are one JSONB snapshot (`saved_looks.snapshot` at save time, or `recommendation_history.snapshot` at show time) — a single value in a single row (tier 1). The *generation* itself is computation, not a write. |
| **Failure behavior** | The single snapshot write commits or rolls back as a unit. A failed generation writes nothing and the user sees the error — no partial recommendation state. |
| **Consistency requirement** | A persisted snapshot always contains its reasons; score/reasons are frozen at the moment of save/show (R31; `recommendation_history` P3, `JSONB_STRATEGY.md` §4.2). |

### TRX-5 — Completing an analysis (run completion)

| Attribute | Detail |
| --- | --- |
| **Operation** | An AI analysis (outfit/face/hairstyle/grooming) finishes: the run records its result. |
| **Tables involved** | `analysis_runs` (one row: `status`, `result`, `completed_at`). The scan blob already exists in object storage (outside the transaction). |
| **Required atomicity** | The completion write must be **atomic and write-once**. The run row is created (tier 1), then completed by a **single guarded statement** that sets `status='completed'`, `completed_at`, and the immutable `result` together. This is the **only** permitted mutation of a run row — append-only grants (PR-6) forbid any other `UPDATE`. The guard (`WHERE id=$1 AND status='pending'`) prevents a double-complete racing. |
| **Failure behavior** | The guarded completion fails or rolls back as a unit → the run stays `pending` (or the whole insert fails → run absent). No run can ever appear `completed` without a result, and no result can be written to a `completed` run (write-once, PR-6). Retry is safe because of the status guard. |
| **Consistency requirement** | `CHECK (status IN ('pending','completed','failed'))` (BC-8); `result` is NULL until `completed` (BC-49); `engine_version` recorded for reproducibility (PR-6); the run is scoped to its user (BC-26) and never mutated afterward (`HISTORY_AND_VERSIONING.md` §7). |

### TRX-6 — Updating current profile from an analysis

| Attribute | Detail |
| --- | --- |
| **Operation** | A completed analysis is accepted → the current projection is replaced and the acceptance traced. |
| **Tables involved** | `user_state` (one row: `style_profile` replaced whole, `version` incremented, new `source_run_id`); `learning_signals` (`analysis_updated`/`style_updated` signal); optionally a `saved_looks.source_run_id` link. |
| **Required atomicity** | **True transaction** when the trace signal is included: the `UPDATE user_state` (optimistic concurrency via `version`, BC-15) and the `INSERT learning_signals` commit together, so an accepted analysis is never applied without its trace. The `user_state` update alone is tier 1. |
| **Failure behavior** | Version mismatch (concurrent edit) → the guarded `UPDATE` affects 0 rows → **rollback**, app refreshes and user re-applies; trace insert failure → rollback (projection not updated). The old analysis run is never touched (BC-41, §7). |
| **Consistency requirement** | `style_profile.source_run_id` names an existing completed run (provenance, §7); the projection is current state, the run is history — never the same row (PR-7); "latest wins" applies to the projection only, never the history (§7). |

### TRX-7 — Creating an event recommendation (event-driven look)

| Attribute | Detail |
| --- | --- |
| **Operation** | A user event is created and occasions an outfit/look recommendation. |
| **Tables involved** | `user_events` (one row: type, date, title, optional location/notes). The event-driven recommendation is **AI/derived output** — regenerable, not stored (unless later saved via TRX-3). |
| **Required atomicity** | The `INSERT user_events` is a single-row write (tier 1). No multi-table unit: the recommendation is computed from the event + wardrobe at read time and is not a row (`TABLE_DEFINITIONS.md` §8: `daily outfits` → derived; `recommendations` → regenerable). |
| **Failure behavior** | Event insert fails (e.g. invalid `event_type_id`, BC-32; duplicate nothing — no unique constraint beyond PK) → rollback, no event, no recommendation; app returns a typed error. |
| **Consistency requirement** | An event always has a valid type (BC-32) and a date; it is owned by one user (BC-21); it feeds `preferred_occasions` and outfit generation (R35/R36) via derived computation, never by storing a generated outfit (BC-56). |

### TRX-8 — Account deletion (complete erasure)

| Attribute | Detail |
| --- | --- |
| **Operation** | User deletes the account → complete right to erasure. |
| **Tables involved** | `users` (one row) plus **all 12 user-owned children** by CASCADE (BC-17…BC-28): `user_state`, `wardrobe_items`, `saved_looks`, `learning_signals`, `user_events`, `style_score_records`, `activity_days`, `today_look_records`*, `feedback_events`*, `analysis_runs`, `subscriptions`, `recommendation_history`* (* conditional tables). |
| **Required atomicity** | **True transaction, single statement.** One `DELETE FROM users WHERE id=$1` is atomic across the entire cascade — the FK graph is acyclic, so the cascade terminates (`RELATIONSHIP_CONSTRAINTS.md` §3.1, §6). `SET NULL` updates on rows being deleted are no-ops. |
| **Failure behavior** | The `DELETE` commits or rolls back as a whole — no partial erasure is possible. Object-storage blob deletion (async cleanup job) and external subscription cancellation (R51) run **after** commit, as compensating steps outside the DB (`SECURITY_PRIVACY_DESIGN.md` §5.2); they are idempotent/retryable. If the DB `DELETE` fails, nothing is erased and the job is not triggered. |
| **Consistency requirement** | No orphaned PII snapshots, signals, or saved-look payloads survive (complete erasure, `RELATIONSHIP_CONSTRAINTS.md` §3; `SECURITY_PRIVACY_DESIGN.md` §5); knowledge tables (`looks`, vocabularies) are **never** deleted; no anonymized "kept" signals (SET NULL alternative rejected, §3.2). |

---

## 4. Canonical single-row writes (trivially atomic — no transaction required)

Not every operation needs a transaction. These are single-row writes whose
atomicity PostgreSQL guarantees without an explicit `BEGIN`/`COMMIT`:

| Operation | Table | Key constraint honored |
| --- | --- | --- |
| Record a learning signal | `learning_signals` (INSERT) | typed (BC-33), labeled (BC-12), append-only |
| Record a style score snapshot | `style_score_records` (INSERT) | score range (BC-7), append-only |
| Record an activity day | `activity_days` (INSERT) | `UNIQUE (user_id, day)` (BC-4) |
| Record a today's-look snapshot (P1) | `today_look_records` (INSERT) | `UNIQUE (user_id, day)` (BC-5), append-only |
| Record a feedback event (P1) | `feedback_events` (INSERT) | ownership (BC-25), targets `SET NULL` (BC-38/39) |
| Log a recommendation shown/saved (P3) | `recommendation_history` (INSERT) | ownership (BC-28), `saved` flag, snapshot |
| Edit a wardrobe item (favorite/fields) | `wardrobe_items` (UPDATE) | category/color presence (BC-45) |
| Edit or delete a user event | `user_events` (UPDATE/DELETE) | ownership (BC-21) |
| Change subscription state (P2) | `subscriptions` (UPDATE) | 0..1 (BC-3), plan (BC-35); external payment call is **outside** |
| Update catalog content | `looks` / reference tables (INSERT/UPDATE) | stable codes (PR-3), deprecate-not-delete |

**Why these are not transactions:** each writes exactly one row; the row-level
MVCC guarantee already provides the required atomicity. Grouping them into
explicit transactions would add locking overhead without changing the
guarantee (PR-12).

---

## 5. Deliberately non-transactional operations

These must **not** be wrapped in a Fansivibe PostgreSQL transaction:

| Operation | Why it stays outside |
| --- | --- |
| Blob upload/delete (object storage) | The DB holds only `MediaRef` references (PR-8); a transaction cannot span object storage. Upload *before* the row write; delete *after* by the async cleanup job (`MEDIA_STORAGE_DESIGN.md` §7). |
| External payment/entitlement calls (R51) | Cross-system side effects; the DB only stores the entitlement row. The payment call runs after commit and is idempotent/retryable. |
| AI/derived computation (recommendation generation, scoring, style DNA, current today's-look) | Computation is not a write; results are either regenerable or frozen into a single snapshot row (TRX-2/TRX-4). |
| Cache population/eviction (current score, feed, weather) | Recomputed, evictable, no durability requirement (`STORAGE_INVENTORY.md` category 4). |
| Assistant conversation handling | Transient by default; retention undecided; no table → no transaction (PR-12). |
| Retention/pruning jobs (auto-expire scans, prune old runs) | Rule-based, async, run in their own transactions per job; never in a user-facing operation (`STORAGE_INVENTORY.md` §§1.2/1.3/1.6). |

---

## 6. Transaction vs. constraint interaction

Transactions and constraints (BC-1…BC-51) are complementary:

| Guarantee | Provided by |
| --- | --- |
| A row can never violate an invariant | constraints (`UNIQUE`, `CHECK`, `FK`, `NOT NULL`) — enforced per statement |
| A *group* of rows reaches a valid state together | transactions — enforce atomicity across statements |
| History can never be mutated | append-only grants (INSERT/SELECT only) — enforced at the role level, complementary to both |
| Erasure is complete | the `DELETE users` transaction (TRX-8) + post-commit compensating jobs |

**Ordering rule for the migration step:** constraints are created with the
tables; transactions are then designed so that *no logical operation can
submit a state that satisfies every per-row constraint but violates a
multi-row invariant* — that is the exact boundary this catalog draws (e.g.
TRX-3 couples the save to its signal precisely because neither table alone
enforces the coupling).

---

## 7. Report

### Design principles

1. **Single-row writes are not transactions.** PostgreSQL row-level atomicity
   already covers them; explicit transactions are reserved for multi-row/multi-
   table all-or-nothing units (§4).
2. **The database can only be atomic about rows.** Blobs and external services
   live outside transactions; ordering (upload-before-insert,
   delete-after-commit) is an application concern (`MEDIA_STORAGE_DESIGN.md`
   §7).
3. **History is written, never touched again.** Transactions only `INSERT`
   history rows (plus the single guarded `analysis_runs` completion write);
   "deleting current state never deletes history" holds by construction
   (BC-41, §2.3).
4. **Current state and history are never the same row** (PR-7): the analysis
   run (TRX-5) and the projection update (TRX-6) are separate transactions —
   the run commits first, then the projection update references it. A newer
   analysis can never destroy an older one (§7).
5. **Erasure is one atomic statement.** Account deletion is a single `DELETE
   users` cascade (TRX-8); everything after it (blob cleanup, payment
   cancellation) is compensating and idempotent.
6. **Non-tables need no transactions.** Outfits, recommendations, and reasons
   are value objects / regenerable output, not rows (TRX-2, TRX-4) — no
   transaction where there is no multi-row write (PR-12).

### Relationship to earlier STEP 4 deliverables

- **`TABLE_DEFINITIONS.md`** — every operation here names the exact tables and
  columns from that schema; no new tables or columns are invented.
- **`BUSINESS_CONSTRAINTS.md`** — each transaction's consistency requirement
  cites BC-* rules; transactions exist precisely where constraints alone
  cannot guarantee a multi-row invariant.
- **`HISTORY_AND_VERSIONING.md`** — TRX-5/TRX-6 encode its §7 invariant
  ("INSERT a run, UPDATE a projection — never UPDATE a history row") as
  transaction boundaries.
- **`RELATIONSHIP_CONSTRAINTS.md`** — TRX-8 relies on its acyclic FK graph and
  CASCADE semantics; TRX-3/TRX-6 use its `SET NULL` cross-links.
- **`MEDIA_STORAGE_DESIGN.md`** — §2.1/§5 encode its blob-lifecycle rule into
  transaction boundaries.
- **`SECURITY_PRIVACY_DESIGN.md`** — TRX-8 is the implementation boundary of
  its §5 account-deletion behavior.

### Open decisions carried forward

- **`analysis_runs` completion shape** — the single guarded completion write
  (TRX-5) assumes a `status='pending'` guard exists; the exact guard column and
  role permissions are confirmed in the migration step (append-only grants
  allow exactly this one write).
- **`recommendation_history` (P3)** — TRX-3 includes its `saved` flip only when
  the table exists (PR-12).
- **Conditional tables** (`today_look_records`, `feedback_events`,
  `recommendation_history`) — their TRX entries apply only when the features
  land.

### Where this leaves the schema step

Transaction boundaries are the final coordination layer of the STEP 4
documentation series. The full database design is now: rules → mapping → table
definitions → relationships → history/versioning → JSONB → media storage →
indexes → security & privacy → business constraints → **transaction
boundaries**. The next step after this series is the **schema/migration step**
(actual PostgreSQL DDL), which will implement the tables, constraints, and the
transaction boundaries catalogued here.

---

## Constraints honored

- No transactions implemented, no SQL written, no PostgreSQL database created,
  no migrations, no triggers, no repositories, no endpoints.
- No Flutter, routing, UI, or backend code changes; no dependencies added;
  nothing deleted.
- Every transaction traces to `TABLE_DEFINITIONS.md`, `BUSINESS_CONSTRAINTS.md`,
  `RELATIONSHIP_CONSTRAINTS.md`, `HISTORY_AND_VERSIONING.md`,
  `MEDIA_STORAGE_DESIGN.md`, and the finalized domain model; nothing is
  invented beyond it.
- Operations the domain resolved as non-tables (outfits, recommendations,
  reasons) are documented as single-snapshot writes rather than invented
  multi-table transactions (PR-12).
- The real Fansivibe repository is the source of truth; the separate reference
  project was not merged.
