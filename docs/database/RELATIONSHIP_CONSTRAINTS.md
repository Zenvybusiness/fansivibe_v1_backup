# Fansivibe — Relational Integrity Model

> **STEP 4 (continuation) — DATABASE DESIGN.** Defines the **relational
> integrity model** for every foreign key in `TABLE_DEFINITIONS.md`, grounded in
> the lifecycle semantics of `DOMAIN_RELATIONSHIPS.md` (R1–R51). For each FK:
> source table + column, target table + column, cardinality, `ON DELETE`,
> `ON UPDATE`, nullability, and **why the relationship exists**.
>
> **Status: documentation only. No SQL, no database, no migrations, no
> repositories, no endpoints, no application code changes, nothing deleted.**
>
> **Sources:** `TABLE_DEFINITIONS.md` (the 23 logical tables and their FKs),
> `DOMAIN_RELATIONSHIPS.md` (relationship natures, cardinalities, lifecycle
> dependencies R1–R51), `DATABASE_DESIGN_RULES.md` (PR-4 FK lifecycle
> semantics, PR-6 historical-AI preservation, §10 current-vs-history
> enforcement, §11 business constraints).

---

## 1. Purpose and method

This document answers one question per FK: **what happens to this reference when
either side is created, changed, or deleted — and why that behavior is the
correct one for the domain.** It is the contract the schema/migration step uses
for every `REFERENCES` clause; no SQL is written here.

Each FK is specified with the eight attributes the task requires:

| # | Attribute | Where defined |
| --- | --- | --- |
| 1 | Source table / column | The child column holding the reference. |
| 2 | Target table / column | The referenced parent (usually its primary key). |
| 3 | Cardinality | How many child rows may reference one parent row (and vice versa). |
| 4 | `ON DELETE` | Action when the parent row is deleted. |
| 5 | `ON UPDATE` | Action when the parent key value changes. |
| 6 | Nullable? | Whether the child column may be NULL. |
| 7 | Why it exists | The domain relationship (R#) and lifecycle dependency it enforces. |

**Scope:** §4–§5 cover every **hard FK column**. References that live inside
JSONB (`user_state`, `looks.payload`) cannot be database foreign keys — they are
listed in §5.4 and enforced at the application layer, exactly as
`DATABASE_DESIGN_RULES.md` §8 and `DOMAIN_RELATIONSHIPS.md` §5 rule 7 require.

---

## 2. The referential-action decision framework

Four `ON DELETE` actions were evaluated. The decision rule: **the action must
mirror the relationship's lifecycle dependency** (`DOMAIN_RELATIONSHIPS.md`
§5), never a blanket default.

| Action | Meaning | Where it is used | Why |
| --- | --- | --- | --- |
| **CASCADE** | Deleting the parent deletes the child. | **Only** the `user_id` composition from `users` (12 FKs). | Every user-owned child is **deleted-with** the account (`R3–R9`, lifecycle rule 1). Account erasure is a privacy requirement — see §3. |
| **RESTRICT** | Deleting the parent fails while any child references it. | **Only** knowledge references to vocabularies/plans (`category_id`, `color_id`, `material_id`, `event_type_id`, `signal_type`, `plan_code`, `run_type`). | Knowledge is system-owned content; a referenced row is **in use** and must not vanish under a live entity (PR-4). Removal is done by soft-deactivate (`active=false`) + deprecate, never by force. |
| **SET NULL** | Deleting the parent nulls the child's reference; the child survives. | **Only** optional cross-references (`saved_looks.look_id`, `source_run_id`, feedback targets, `recommendation_history.look_id`). | The child is user-owned and must **survive** the target's removal (catalog deprecation, history retention). The reference is informational, not existential (R30, R32). |
| **SET DEFAULT** | Deleting the parent sets the child to a fixed default. | **Never.** | Requires a sentinel row per FK (e.g. an "uncategorized" category). The domain model defines **no such sentinel**; inventing one would falsify data (a deleted category's items would silently become "uncategorized") and add speculative content (PR-12). Rejected for every FK. |

**`ON UPDATE` is `NO ACTION` everywhere.** Both key kinds are **immutable by
design**:

- `uuid` primary keys (`users.id`, entity `id`s, `analysis_runs.id`) are
  server-generated and never reassigned (PR-3). `NO ACTION` and `CASCADE` are
  functionally identical here; `NO ACTION` states the intent that key rotation
  does not happen.
- `text` codes (`wardrobe_categories.code`, `looks.code`, …) are **stable and
  immutable** (PR-3): a code never changes, so renames are performed as
  add-new + deprecate-old. `NO ACTION` deliberately *blocks* a hard-FK rename —
  which is correct, because JSONB-referenced codes (`occasions`, `styles`) can
  never be cascaded and must stay immutable too. A rename is a data migration,
  never an `ON UPDATE CASCADE` event.

---

## 3. Special attention: user deletion and historical AI records

This is the decision the task flags, so it is stated first and explicitly.

### 3.1 Account deletion → full `CASCADE` (including AI history)

Deleting a `users` row cascades to **all 12 user-owned children**, including the
historical/AI records (`learning_signals`, `style_score_records`,
`activity_days`, `analysis_runs`, and the conditional `today_look_records`,
`recommendation_history`, `feedback_events`).

**Why this is the correct behavior:**

1. **The domain says so.** Every one of these is `COMPOSITION` from `User`
   (`DOMAIN_RELATIONSHIPS.md` R3–R9): lifecycle = *created-with; deleted-with*
   (lifecycle-dependency rule 1). Composition cascades from the root.
2. **Privacy by construction (PR-10).** Fansivibe stores appearance and image
   data. Account deletion must be a **complete right to erasure** — no orphaned
   `analysis_runs.result` snapshots, saved-look payloads, or signal rows may
   survive with PII unanchored. `STORAGE_INVENTORY.md` retention principle:
   *user blobs follow user lifecycle*.
3. **Cascade is safe here despite cross-links.** `saved_looks.source_run_id →
   analysis_runs.id` (SET NULL) and `analysis_runs` are both children of
   `users`. On account deletion PostgreSQL removes both; the `SET NULL`
   update on a `saved_looks` row that is itself being deleted is a no-op.
   There is **no cycle** in the FK graph (§6), so the cascade terminates.

### 3.2 Rejected alternatives for account deletion

| Alternative | Why rejected |
| --- | --- |
| `user_id SET NULL` on history rows ("keep anonymized signals") | Orphaned user-less AI records; requires an anonymization pipeline the domain model does not define; contradicts *composition* (the rows cannot exist without the user) and the deletion matrix. |
| Soft-delete the account, keep rows (`deleted_at`) | PR-11 adds `deleted_at` **only where a feature needs it**; no product requirement to resurrect accounts; the erasure/retention matrix is the removal path. Not introduced speculatively. |
| Delete current state but retain history | A two-tier lifecycle the domain does not define and that would leak PII inside retained AI snapshots. |

### 3.3 Historical AI records within a user's lifetime

Cascade governs **account deletion only**. While the account lives, history is
**append-only** (PR-6, rules-doc §10 rule 1): the API role gets `INSERT`/`SELECT`
only on `learning_signals`, `style_score_records`, `activity_days`,
`analysis_runs` (+ conditional history tables), so no integrity path can
`UPDATE`/`DELETE` a snapshot. Retention/soft-delete is the only removal path,
and it is a **separate, future process** — not a referential-action decision.

Two integrity consequences follow:

1. **`saved_looks.look_id` is `SET NULL`, never `RESTRICT`.** The catalog
   (`looks`) is system-owned knowledge that can be **deprecated** (R30). A saved
   look must survive deprecation; its `snapshot` JSONB already carries the frozen
   ensemble, so nulling the link loses nothing (K9.1 id-ref rule).
2. **`saved_looks.source_run_id` is `SET NULL`, never `CASCADE`.** If history
   retention ever removes old `analysis_runs`, the saved look (which may be
   referenced again in the future) stays intact; the provenance link is
   informational (R32).

### 3.4 The no-FK-to-trigger rule

`learning_signals` deliberately has **no FK to the entity that triggered the
signal** (`wardrobe_items`, `saved_looks`, `user_events`). Deleting a wardrobe
item, a saved look, or an event must **never touch the signal history** — history
survives current-state deletion (rules-doc §10 rule 3). The triggering event's
identity is preserved as a denormalized snapshot in `context` JSONB instead of a
hard reference. See §6.

---

## 4. Master FK catalog

24 hard foreign keys. `NO ACTION` = `ON UPDATE NO ACTION` throughout
(immutable keys, §2). **Null** = whether the child column may be NULL.

| # | Source table | Source column | Target table | Target column | Cardinality | ON DELETE | ON UPDATE | Null | Why the relationship exists |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **Composition from `users` (CASCADE)** |
| 1 | `user_state` | `user_id` | `users` | `id` | 1:1 | CASCADE | NO ACTION | NOT NULL | 1:1 current-profile projection, born and deleted with the account (R1/R2). |
| 2 | `wardrobe_items` | `user_id` | `users` | `id` | 1:N | CASCADE | NO ACTION | NOT NULL | user-owned items scoped to the account (R3). |
| 3 | `saved_looks` | `user_id` | `users` | `id` | 1:N | CASCADE | NO ACTION | NOT NULL | user-owned saves scoped to the account (R5). |
| 4 | `learning_signals` | `user_id` | `users` | `id` | 1:N | CASCADE | NO ACTION | NOT NULL | append-only history scoped; removed at account erasure (R7). |
| 5 | `user_events` | `user_id` | `users` | `id` | 1:N | CASCADE | NO ACTION | NOT NULL | user-owned, dated, editable events (R4, P1). |
| 6 | `style_score_records` | `user_id` | `users` | `id` | 1:N | CASCADE | NO ACTION | NOT NULL | derived score history scoped (R8, P1). |
| 7 | `activity_days` | `user_id` | `users` | `id` | 1:N | CASCADE | NO ACTION | NOT NULL | streak day history scoped (R9, P1). |
| 8 | `today_look_records` | `user_id` | `users` | `id` | 1:N | CASCADE | NO ACTION | NOT NULL | daily-look history scoped (P1, conditional). |
| 9 | `feedback_events` | `user_id` | `users` | `id` | 1:N | CASCADE | NO ACTION | NOT NULL | feedback history scoped (P1, feature-gated). |
| 10 | `analysis_runs` | `user_id` | `users` | `id` | 1:N | CASCADE | NO ACTION | NOT NULL | reproducible AI-event history scoped (R6, P2). |
| 11 | `subscriptions` | `user_id` | `users` | `id` | 1:0..1 | CASCADE | NO ACTION | NOT NULL (UNIQUE) | 0..1 paid state per account (R10, P2). |
| 12 | `recommendation_history` | `user_id` | `users` | `id` | 1:N | CASCADE | NO ACTION | NOT NULL | shown/saved trace scoped (P3, conditional). |
| **Knowledge references (RESTRICT)** |
| 13 | `wardrobe_items` | `category_id` | `wardrobe_categories` | `code` | N:1 | RESTRICT | NO ACTION | NOT NULL | mandatory category vocab ref (R18). |
| 14 | `wardrobe_items` | `color_id` | `colors` | `code` | N:1 | RESTRICT | NO ACTION | NOT NULL | mandatory color vocab ref (R18). |
| 15 | `wardrobe_items` | `material_id` | `materials` | `code` | N:1 (0..1) | RESTRICT | NO ACTION | NULL | optional material/texture ref. |
| 16 | `user_events` | `event_type_id` | `event_types` | `code` | N:1 | RESTRICT | NO ACTION | NOT NULL | mandatory event type (R34, P1). |
| 17 | `learning_signals` | `signal_type` | `signal_types` | `code` | N:1 | RESTRICT | NO ACTION | NOT NULL | typed signal vocabulary (8 types). |
| 18 | `subscriptions` | `plan_code` | `subscription_plans` | `code` | N:1 | RESTRICT | NO ACTION | NOT NULL | plan catalog ref (R44, P2). |
| 19 | `analysis_runs` | `run_type` | `run_types` | `code` | N:1 | RESTRICT | NO ACTION | NOT NULL | run-type vocabulary (P2). |
| **Cross-links / optional references (SET NULL)** |
| 20 | `saved_looks` | `look_id` | `looks` | `code` | 0..1:1 | SET NULL | NO ACTION | NULL | catalog ref that must survive deprecation (R30). |
| 21 | `saved_looks` | `source_run_id` | `analysis_runs` | `id` | 0..1:1 | SET NULL | NO ACTION | NULL | provenance link when saved from a scan (R32). |
| 22 | `feedback_events` | `target_look_id` | `looks` | `code` | 0..1:1 | SET NULL | NO ACTION | NULL | feedback target; informational (P1, feature-gated). |
| 23 | `feedback_events` | `target_saved_look_id` | `saved_looks` | `id` | 0..1:1 | SET NULL | NO ACTION | NULL | feedback target; must survive save removal (P1). |
| 24 | `recommendation_history` | `look_id` | `looks` | `code` | 0..1:1 | SET NULL | NO ACTION | NULL | trace target; informational (P3, conditional). |

---

## 5. Per-relationship detail

### 5.1 Composition from `users` — FKs #1–#12 (CASCADE)

All twelve are **whole–part composition** (R1–R10): the child cannot exist
without the user, and account deletion cascades. Identical policy, three
variations in cardinality:

- **1:1 (`user_state`, #1):** `user_id` is both primary key and foreign key —
  the projection is born and erased with the account. CASCADE is the only
  sane action; there is no "orphan state".
- **1:0..1 (`subscriptions`, #11):** `UNIQUE (user_id)` enforces at-most-one
  plan; CASCADE removes entitlement state at account erasure (the external
  payment service is separately notified — R51, out of DB scope).
- **1:N (all others):** many children per user; CASCADE applies the erasure
  policy uniformly.

**On `ON UPDATE`:** `users.id` is an immutable, server-generated `uuid`; it is
never reassigned, merged by id change, or recycled. `NO ACTION` therefore
never fires. (Anonymous→registered **merge** is a row-rewrite on the device
sync path — `AU11.2` — not a PK update.)

### 5.2 Knowledge references — FKs #13–#19 (RESTRICT)

Entities point **by stable id** at system-owned knowledge; knowledge never
references user data (`DOMAIN_RELATIONSHIPS.md` §5 rule 7). `RESTRICT` means a
referenced row cannot be deleted while in use:

- **Required refs (#13, #14, #16, #17, #18, #19):** the child column is
  `NOT NULL`, so a referenced vocabulary row is permanently coupled while any
  child exists. Vocabularies are never force-deleted; they are soft-deactivated
  (`active = false`) and replaced by new codes (add-new + deprecate-old).
- **Optional ref (`material_id`, #15):** nullable, still `RESTRICT` — if a
  material id is present it must resolve to a live row; absence (NULL) is the
  only "no material" representation. This keeps the data honest: a broken
  reference is impossible, and there is no silent re-pointing to a default
  (no `SET DEFAULT`, §2).

**Why not `SET NULL` here?** These references are *mandatory content* of the
entity (a wardrobe item always has a category and color — R18). Nulling them
would silently invalidate the entity, which `NOT NULL` + `RESTRICT` forbids.

### 5.3 Cross-links / optional references — FKs #20–#24 (SET NULL)

These link user data to knowledge (`look_id`) or to other user history
(`source_run_id`, `target_saved_look_id`) for **informational** purposes. The
child is the durable side and must survive the target's removal:

- **#20 `saved_looks.look_id → looks.code`:** catalog rows are deprecated, never
  deleted-with-saves (R30). Nulling loses nothing: the immutable `snapshot`
  JSONB already contains the frozen ensemble/score/reasons. The FK is for
  linking/attribution only.
- **#21 `saved_looks.source_run_id → analysis_runs.id`:** if history retention
  removes an old run, the saved look persists with `NULL` provenance (R32).
- **#22/#23 `feedback_events` targets:** feedback history survives the removal
  of its target (a deprecated look or a deleted saved look). The rating/why
  row is the durable learning input; the target is context.
- **#24 `recommendation_history.look_id`:** same informational pattern (P3).

`SET NULL` is chosen over `CASCADE` here because the child **is not** part of
the target — deleting a catalog look or an old run must not delete user saves
or feedback (rules-doc §10 rule 3).

### 5.4 Application-level references inside JSONB — no hard FK

These reference stable ids but live inside JSONB documents, so no database
constraint can exist; the backend enforces id validity on write (K9.1).

| Reference (in JSONB) | Points at | Domain relationship |
| --- | --- | --- |
| `user_state.preferences.preferred_occasions[]` | `occasions.code` | preferences reference vocab ids (R2/R36). |
| `user_state.style_profile.style_type` | `styles.code` | current style vibe id (R1/R13). |
| `user_state.style_profile.source_run_id` | `analysis_runs.id` | provenance of the current profile projection (R15; P2). |
| `looks.payload` occasion/style tags | `occasions.code`, `styles.code` | catalog tagging (R28). |

Deletion semantics at the application layer: `occasions`/`styles` codes are
immutable and soft-deprecated (never removed while any JSONB ref may hold
them); a `source_run_id` dangling after retention is treated as `NULL`
provenance. **The absence of a hard FK here is deliberate** — JSONB is not a
query/join axis (rules-doc §8), and the refs are enforcement-agnostic by design.

---

## 6. Intentional absences — FKs deliberately not created

| Case | Why there is no FK |
| --- | --- |
| `learning_signals` → triggering entity (`wardrobe_items`, `saved_looks`, `user_events`) | **No-FK-to-trigger rule (§3.4):** deleting current state never deletes history (rules-doc §10 rule 3). A hard FK would either `CASCADE` (destroy history) or `RESTRICT` (block deleting an item that had ever produced a signal) — both wrong. |
| `saved_looks.snapshot` / `analysis_runs.result` "breakdown → wardrobes/looks" | Snapshots are **immutable value-object copies**, not references (R31, R38); integrity is immutability + grants, not FK links. |
| Media / object storage (`MediaRef`, `image_ref`, `input_media`) | Media bytes live outside PostgreSQL (PR-8); `MediaRef` is a URL/object-key value, not a row in this database. |
| `user_state`, `looks.payload` → `occasions`/`styles` | JSONB refs, app-enforced (§5.4). |
| `users` → auth provider | Auth is an external boundary process; only the opaque `(auth_provider, auth_subject)` pair is stored, never an FK into provider systems (PR-10). |
| `subscriptions` → external payment service | External service call (R51), not a DB relationship; `external_ref` is an opaque string. |

**No circular references:** the FK graph is acyclic (composition tree from
`users` + leaf references to `looks`/vocab), so no deferred constraints are
needed.

---

## 7. Report — summary

- **24 hard foreign keys**, exactly one integrity policy per relationship
  class: `CASCADE` for user composition (12), `RESTRICT` for knowledge
  references (7), `SET NULL` for optional cross-links (5); `ON UPDATE NO ACTION`
  everywhere because all keys are immutable by design.
- **`SET DEFAULT` rejected** everywhere: it would require sentinel rows the
  domain model does not define and would silently falsify data.
- **User deletion = full cascade**, explicitly including all historical AI
  records (`learning_signals`, `style_score_records`, `activity_days`,
  `analysis_runs` + conditional history) — a complete right to erasure
  consistent with composition, PR-10 privacy, and the retention matrix.
- **Historical AI integrity:** append-only grants protect snapshots from
  mutation; `look_id` and `source_run_id` are `SET NULL` so catalog deprecation
  and history retention never delete user saves; `learning_signals` carries no
  FK to its triggers.
- **JSONB-referenced ids** (`occasions`, `styles`, `source_run_id` provenance)
  are app-enforced, documented, and deliberately FK-free.

---

## 8. Constraints honored

- No SQL written, no database created, no migrations, no repositories, no
  endpoints.
- No Flutter, routing, UI, or backend code changes; no dependencies; nothing
  deleted.
- Every action traces to a lifecycle rule in `DOMAIN_RELATIONSHIPS.md`
  (R1–R51, §5) and a principle in `DATABASE_DESIGN_RULES.md` (PR-4, PR-6,
  PR-10, §10); nothing is invented beyond the domain model.
- The real Fansivibe repository is the source of truth; the separate reference
  project was not merged.


