# Fansivibe — History and Versioning Strategy

> **STEP 4 (continuation) — DATABASE DESIGN.** Defines how the database
> separates **CURRENT STATE** from **HISTORICAL DATA** for every table in
> `TABLE_DEFINITIONS.md`, classifies each concept into the six storage
> categories the task requires, and pins the policy that keeps **historical AI
> results reproducible** and **never silently destroyed by a newer analysis**.
>
> **Status: documentation only. No SQL, no database, no migrations, no
> repositories, no endpoints, no application code changes, nothing deleted.**
>
> **Sources:** `DOMAIN_STATE_AND_HISTORY.md` (the classification this document
> operationalizes — the core principle "never overwrite history", the
> decision procedure §2, the master classification §3, the special-attention
> deep dives §5, the reproducibility policy §6, the enforceable rules §8),
> `DOMAIN_RELATIONSHIPS.md` (R15/R39/R40 latest-wins semantics),
> `TABLE_DEFINITIONS.md` (the 23 tables), `RELATIONSHIP_CONSTRAINTS.md` (the 24
> FKs), and `DATABASE_DESIGN_RULES.md` (PR-6 preserve-historical-AI, PR-7
> current-vs-history split, §10 schema enforcement).

---

## 1. Purpose and method

The database must never conflate the two piles the domain keeps apart
(`DOMAIN_STATE_AND_HISTORY.md` §1): an **immutable, append-only trace of what
happened** and the **user's present, mutable world**. Every concept is assigned
to exactly one storage category, and every stored concept that is a *value of
the moment* gets a defined **history form** if the product needs to recall the
past.

For every table and every special-attention concept this document specifies:

| # | Element | Meaning |
| --- | --- | --- |
| 1 | Classification | One of the six storage categories (§2). |
| 2 | Mutable? | Whether rows may be `UPDATE`d/`DELETE`d by the API. |
| 3 | Write policy | Current state = mutable; history = `INSERT`/`SELECT` only (grant-level). |
| 4 | Snapshot / immutable part | The JSONB or field that is frozen once written. |
| 5 | Provenance | How the value names its source history. |
| 6 | Reproducibility | Whether a past result is exactly reproducible, and how (§5). |

---

## 2. The six storage categories

| Category | Definition | Stored? | Mutable? | Writes |
| --- | --- | --- | --- | --- |
| **CURRENT_STATE** | The user's present, editable world, scoped to `User`. | Yes (rows) | Yes | `INSERT`/`UPDATE`/`DELETE` |
| **HISTORICAL_RECORD** | An immutable snapshot of a point in time; the trace. | Yes (rows) | No | `INSERT`/`SELECT` only; retention is the only removal |
| **EVENT** | A historical record whose essence is *"something happened at T"*. | Yes (rows) | No | `INSERT`/`SELECT` only |
| **DERIVED_STATE** | Computed from durable inputs; never the source of truth; may be persisted **only as immutable snapshots**. | Snapshot only | No | snapshot `INSERT`/`SELECT` only |
| **CACHE** | The live, regenerable *current* value of a derived fact; discardable. | Optional, always regenerable | Yes (rewritten) | rewritten freely, never truth |
| **TEMPORARY_PROCESSING** | Per-request / in-flight state with no durable value. | Not in PostgreSQL | – | ephemeral |

Two clarifications that keep the six categories honest:

1. **EVENT ⊂ HISTORICAL_RECORD.** An event is a historical record with an
   `occurred_at` identity (`learning_signals`, `feedback_events`,
   `analysis_runs`). It is listed separately because its reproducibility
   contract is the strictest (raw occurrence, never recomputed).
2. **DERIVED_STATE vs CACHE are one concept in two storage forms.** A derived
   value (score, streak, today's look) is *computed* (DERIVED_STATE); its live
   value is kept as a **CACHE** (regenerable, never truth); its past is kept as
   immutable **HISTORICAL_RECORD** snapshots. The current cache may be dropped
   at any time and recomputed; the snapshot rows are permanent until retention.

A seventh bucket exists but is not one of the six: **SYSTEM KNOWLEDGE**
(`looks`, the 9 reference/config tables). It is versioned backend content —
neither user current state nor user history (`DOMAIN_STATE_AND_HISTORY.md`
§2 step 5). It is classified here for completeness and otherwise excluded from
the state/history machinery.

---

## 3. Master classification — every table

| Table | Category | Mutable? | Writes | Immutable / snapshot part | Provenance |
| --- | --- | --- | --- | --- | --- |
| `users` | CURRENT_STATE | Y | CRUD | – | identity is a fact, never recomputed |
| `user_state` | CURRENT_STATE (projection) | Y | UPDATE | – | `style_profile.source_run_id` → `analysis_runs` |
| `wardrobe_items` | CURRENT_STATE | Y | CRUD | – | user-authored; signals trace it |
| `saved_looks` | CURRENT_STATE (list) + immutable snapshot per row | Y (list) / N (snapshot) | add/remove only | `snapshot` JSONB | `source_run_id` when saved from a scan |
| `learning_signals` | EVENT (historical) | N | INSERT only | whole row | raw event, never recomputed |
| `user_events` | CURRENT_STATE (dated, editable) | Y | CRUD | – | not audit history |
| `style_score_records` | DERIVED_STATE → HISTORICAL_RECORD | N | INSERT only | `score` + `breakdown` | derived from formula inputs at the time |
| `activity_days` | DERIVED_STATE → HISTORICAL_RECORD | N | INSERT only | whole row | derived from activity/signals |
| `today_look_records` | DERIVED_STATE → HISTORICAL_RECORD (P1, conditional) | N | INSERT only | `snapshot` | regenerated daily; kept for history |
| `feedback_events` | EVENT (historical, P1, feature-gated) | N | INSERT only | whole row | raw user event |
| `analysis_runs` | EVENT (historical) | N | INSERT only | `result` JSONB, `input_media`, `engine_version` | the run IS the history |
| `subscriptions` | CURRENT_STATE | Y | UPDATE | – | billing history is external (R51) |
| `recommendation_history` | DERIVED_STATE → HISTORICAL_RECORD (P3, conditional) | N | INSERT only | `snapshot` | shown/saved trace |
| `looks` | SYSTEM KNOWLEDGE | Y (content mgmt) | backend | `payload`, `content_version` | versioned content, never user data |
| 9 reference tables | SYSTEM KNOWLEDGE | Y (content mgmt) | backend | stable codes | versioned content (K9.1) |

**Key design rule (from the table):** a single table may be **CURRENT_STATE for
its list and HISTORICAL_RECORD for its payload** (`saved_looks`), and a
**DERIVED_STATE value always stores only its snapshot form in a
HISTORICAL_RECORD table** (`style_score_records`, `activity_days`,
`today_look_records`, `recommendation_history`). No table is both a mutable
current value **and** its own history — that is the `UserModel` blob conflation
the split fixes (`DOMAIN_STATE_AND_HISTORY.md` §4).

---

## 4. The derived / cache cluster — where each current value lives

| Current value (CACHE, regenerable) | Never truth | History table (HISTORICAL_RECORD) |
| --- | --- | --- |
| Style Score (current) | recomputed by formula `60 + wardrobe.clamp(0,20) + savedLooks*2.clamp(0,20)` | `style_score_records` |
| Streak (current) | recomputed from `activity_days` | `activity_days` |
| Today's Look (current) | regenerated from StyleProfile + Wardrobe + events + weather | `today_look_records` (P1 decision) |
| Style DNA view | recomputed from `FaceProfile` | none — re-derivable while producing run kept |
| Recommendation (current) | regenerated from inputs; never stored | `recommendation_history` (P3 decision) + `look_saved` signal |
| Weather | external feed, short TTL | none |

The current values above are **CACHE**: they may be dropped and recomputed
without loss. Their **history**, where the product needs recall, lives only in
the immutable snapshot tables. Nothing in the cache column is ever written as
truth (`DOMAIN_STATE_AND_HISTORY.md` §8 rule 4).

---

## 5. Special-attention deep dives

Each of the thirteen flagged concepts, resolved to category + reproducibility
contract. The unifying rule is stated first, then applied case by case:

> **A newer AI analysis never destroys an older analysis.** A new analysis
> **INSERTs a new `analysis_runs` row** (append-only, immutable) and, if its
> attributes are accepted, **UPDATEs the current projection**
> (`user_state.style_profile`, replaced whole with a new `source_run_id`). The
> old run, its snapshot, and its media ref are **untouched**. "Latest wins"
> applies to the *projection* (R15), never to the *history*.

### 5.1 Face analyses

- **Category:** current state = `user_state.style_profile` (mutable projection);
  history = `analysis_runs` (EVENT/HISTORICAL_RECORD) with immutable `result`.
- **Today:** nothing is written — `setFace` has no caller; the schema is the
  target, not current behavior.
- **Newer analysis:** INSERT new face run → on accept, UPDATE
  `style_profile` whole with the new attributes + `source_run_id`. The old run
  remains reproducible.
- **Reproducibility:** exact — `input_media` (MediaRef to the scan) + `result`
  snapshot + `engine_version`. Retention may prune old runs per policy
  (`STORAGE_INVENTORY.md` §1.6) — deletion under a rule, never in-place mutation.

### 5.2 Hair analyses

- **Category:** no persisted state today (mock result). When the hair pipeline +
  "Save Style" land (**P1**): each execution is an `analysis_runs` row
  (EVENT/HISTORICAL_RECORD) with an immutable snapshot; accepted attributes
  project into the profile JSONB.
- **No overwrite:** a new hair analysis **adds a run** — it never rewrites a
  "current hair profile" that erases the old one (there is no such row).
- **Reproducibility:** same contract as §5.1 (inputs + snapshot + engine version).

### 5.3 Grooming analyses

- Identical structure to §5.2: future `analysis_runs` (grooming) with immutable
  snapshots; beard/glasses recommendations are AI output regenerable from inputs
  + catalog.
- **No table until the pipeline lands** (P1); nothing overwrites anything today.

### 5.4 Style analyses (style/outfit scan + `style_type`)

- **Category:** the scan is an `analysis_runs` (EVENT/HISTORICAL_RECORD); its
  accepted `style_type` projects into `user_state.style_profile.style_type`
  (CURRENT_STATE) and is traced by the `style_updated` signal.
- **No overwrite:** re-scanning creates a new run and updates the projection's
  `style_type`; the prior run and its result remain intact.
- **Reproducibility:** exact via the run (inputs + snapshot + engine version);
  the projection value itself names its `source_run_id`.

### 5.5 Style DNA

- **Category:** **DERIVED_STATE** — a view over `FaceProfile`; never stored,
  never its own history (`DOMAIN_STATE_AND_HISTORY.md` §5.4).
- **Reproducibility:** *re-derivable* from `FaceProfile`, so a past DNA remains
  reconstructable **as long as the producing `AnalysisRun` is retained** (§5.1).
  It is never saved as its own history; no `style_dna` table exists.

### 5.6 Style Score

- **Category:** current = **CACHE** (formula, recomputable); history =
  `style_score_records` (DERIVED_STATE → HISTORICAL_RECORD, immutable).
- **No overwrite:** deleting a wardrobe item lowers *today's* score but must
  **not** edit past `style_score_records` rows — the history records the score
  as it was when recorded.
- **Reproducibility:** exact — each record snapshots `score` + `breakdown` at
  `recorded_at`; it is also recomputable from durable inputs-at-T.

### 5.7 Scans

- **Category:** `analysis_runs` = **EVENT/HISTORICAL_RECORD** (append-only
  linkage: user, feature type, source `MediaRef`, timestamps, result snapshot).
- **No overwrite:** re-running a scan **creates a new run**; the old run, its
  snapshot, and its linkage to the source image are untouched. Retention prunes
  only under rules.
- **Reproducibility:** exact from `input_media` + `result` + `engine_version`;
  the run itself is never regenerated or edited.

### 5.8 Recommendations

- **Category:** **AI output** — regenerable from inputs, never stored as truth.
  Its durable trace today is the `look_saved` signal; a full shown/saved trace
  is `recommendation_history` (**P3**, conditional, immutable snapshots).
- **No overwrite:** showing a new recommendation must not erase the record of a
  previous one, and later wardrobe edits must not rewrite the score/reasons shown
  at the time of a save (hence `SavedLook.snapshot`).
- **Reproducibility:** *regenerable* from current inputs always; the **exact
  previously shown result** only with a persisted snapshot
  (`recommendation_history`). If the product never needs "what did we recommend
  last month", recompute only.

### 5.9 Recommendation feedback

- **Category:** **EVENT/HISTORICAL_RECORD** (`feedback_events`, P1,
  feature-gated) — a raw user event, append-only, immutable, never derived.
- **No overwrite:** feedback aggregates into derived preference state over time
  without ever rewriting it; deleting a target (look/saved look) nulls the link
  (SET NULL) but keeps the feedback row.
- **Reproducibility:** exact (a recorded occurrence); no recomputation.

### 5.10 Wardrobe usage

- **Category:** current = `wardrobe_items` (CURRENT_STATE, mutable); history =
  `learning_signals` (`item_added`, `analysis_updated`, `style_updated`,
  `look_saved`, `occasion_preferred`, assistant signals) + derived
  `activity_days`/`style_score_records`.
- **No overwrite:** editing or deleting a wardrobe item **never** edits the
  signals about it — `item_added` stays a fact after the item is gone
  (no-FK-to-trigger rule; `RELATIONSHIP_CONSTRAINTS.md` §3.4).
- **Reproducibility:** the signals are exact raw events; usage aggregates
  (`activity_days`, scores) are snapshots.

### 5.11 Daily outfits

- **Category:** current = **CACHE** (today's derived look card, regenerated
  from StyleProfile + Wardrobe + events + weather); history =
  `today_look_records` (**P1**, conditional) — per-user/per-day immutable
  snapshots ("what I wore today").
- **No overwrite:** each day's record (if kept) is immutable; a new day never
  edits the previous day's entry.
- **Reproducibility:** the current look is regenerable; a past day is exact only
  with a `today_look_records` snapshot.

### 5.12 AI capability progress

- **Category:** **not state and not history.** `allCapabilities` is static
  system config (7 capabilities, 2 marked active — marketing copy with no
  computation); availability is a **derived view** over config × subscription.
- **Do not model** per-user capability rows or a progress log until a real
  capability/unlock system lands (**P3**). If it does: unlocks = CURRENT_STATE
  (mutable), unlock/usage events = EVENT history (immutable).
- **Reproducibility:** n/a (config, no per-user data).

### 5.13 AI model versions

- **Category:** system config, recorded per history row for reproducibility.
  `analysis_runs.engine_version` (text) identifies the engine/model used so a
  past result can be re-derived or audited (PR-6). Catalog content carries
  `looks.content_version`; reference tables are versioned content (K9.1).
- **No overwrite:** upgrading the engine does **not** rewrite old rows — old runs
  keep their `engine_version`; new runs record the new version.
- **Reproducibility:** the combination `input_media` + `result` +
  `engine_version` is the reproducibility contract for every analysis run
  (rules-doc PR-6, §10 rule 5).

---

## 6. Reproducibility policy — the contract per previous result

| Previous result | Exactly reproducible? | Mechanism | Where enforced |
| --- | --- | --- | --- |
| `AnalysisRun` result (face/hair/grooming/outfit) | **Yes** | `input_media` (MediaRef) + immutable `result` snapshot + `engine_version`; retention prunes only | `analysis_runs` (append-only grants) |
| Recommendation shown | Only with `RecommendationHistory` (P3) | `snapshot` (look ref + score + reasons) at show time | `recommendation_history` (conditional) |
| Saved look's score/reasons | **Yes** | `SavedLook.snapshot` frozen at save time (R31) | `saved_looks` (snapshot never updated) |
| Style DNA view | Re-derivable | from `FaceProfile`, while producing `AnalysisRun` is retained | no table (derived view) |
| Style score at date T | **Yes** | `StyleScoreRecord.score` + `breakdown` snapshot; also recomputable from inputs-at-T | `style_score_records` (append-only) |
| Today's look at date D | Only with `Today'sLookRecord` (P1) | per-day immutable `snapshot` | `today_look_records` (conditional) |
| Insight cards / match scores | No (recomputable) | never stored | none |

The binding rule (from `DOMAIN_STATE_AND_HISTORY.md` §6 and rules-doc PR-6):
**AI output is never a source of truth — but an AI *event* (a run, a shown
recommendation, a save) is a historical fact that must remain reproducible.**
Persist inputs + the user outcome + an immutable snapshot when the product must
answer "what did the product tell me back then".

---

## 7. The "never silently destroy an older analysis" invariant

The write path is designed so a newer analysis can **never** destroy an older
one. The invariant is: **INSERT a run, UPDATE a projection — never UPDATE a
history row.**

```
New face/hair/grooming/style analysis
        │
        ▼
INSERT analysis_runs  (new row; run_type, input_media, engine_version, status)
        │ completes
        ▼
  result JSONB written once (immutable snapshot)   ◄── never overwritten
        │ attributes accepted ("latest wins" on the PROJECTION only, R15)
        ▼
UPDATE user_state.style_profile  (replaced whole; new source_run_id → the run)
        │ (optionally) FEEDS
        ▼
  learning_signals (analysis_updated)  +  saved_looks.source_run_id (SET NULL link)
```

What can and cannot happen to an old run:

| Operation | Allowed? | Mechanism |
| --- | --- | --- |
| Re-run / new scan | Yes | always a **new** `analysis_runs` row |
| Overwrite old run's `result` | **No** | append-only grants (`INSERT`/`SELECT` only, PR-5) |
| Edit old run's `engine_version` | **No** | immutable column |
| Delete old run | Only under retention | a future, rule-based process; never in-place |
| Change the current projection | Yes | `user_state.style_profile` is mutable and names its `source_run_id` |
| Old projection value disappears | Not silently | the old run still holds the old result; the projection simply moves on |

**Why this is safe structurally:** the FK graph is acyclic
(`RELATIONSHIP_CONSTRAINTS.md` §6); `saved_looks.source_run_id → analysis_runs`
is `SET NULL`, so pruning an old run never cascades into saved looks; and no
history table has a FK to a current-state trigger, so deleting current state
never touches history.

---

## 8. Versioning strategy

Versioning has four distinct layers; each has its own rule.

### 8.1 Engine / model version — reproducibility of AI results

- `analysis_runs.engine_version` (text, NOT NULL) records the engine/model that
  produced a result. A version upgrade **never** rewrites existing rows — new
  runs simply record the new version. This is the reproducibility anchor
  (PR-6, §10 rule 5).

### 8.2 Content version — system knowledge

- `looks.content_version` tracks catalog revisions; a look is versioned and
  deprecated (`deprecated_at`), never deleted while referenced
  (`saved_looks.look_id SET NULL`).
- Reference tables are **versioned content** (K9.1): codes are stable and
  immutable; content changes ship as add-new + deprecate-old, never as renames
  (`RELATIONSHIP_CONSTRAINTS.md` §2 — `ON UPDATE NO ACTION`).

### 8.3 Data-model / schema version — migrations

- All schema changes ship as **versioned, forward-only migrations**
  (PR-11): additive-first (add nullable column → backfill → enforce → drop old),
  never a destructive one-step `ALTER`.
- The `UserModel` blob → rows split is a **data migration**
  (`POST /users/me/sync`, idempotent and resumable), not a hand-edited blob
  (rules-doc §7, §13).
- `user_state.version` (int) gives optimistic concurrency for the mutable
  projection and supports migration-friendly re-projections.

### 8.4 Contract version — API (out of scope here)

- API/contract versioning is deferred until endpoints stabilize
  (`MVP_SCOPE.md` P3); schema versioning still applies from day one
  (rules-doc §13 rule 5). The assistant DTOs are KEEP wire contracts, never
  stored (DBR-0).

---

## 9. Enforcement — where the strategy becomes mechanical

| Rule | Mechanism (already defined in the prior Step 4 docs) |
| --- | --- |
| History is append-only | Grant-level `INSERT`/`SELECT` only on `learning_signals`, `style_score_records`, `activity_days`, `analysis_runs`, + conditional history (PR-5; §10 rule 1) |
| Current state is a projection with provenance | `user_state.style_profile.source_run_id` → `analysis_runs` (R15; provenance enforced at the app layer in JSONB) |
| Deleting current state never deletes history | no FK from `learning_signals` to any trigger; history survives (no-FK-to-trigger rule) |
| Derived values recompute; snapshots persist | current score/streak/today's look/DNA are caches; only snapshot tables persist (PR-2, PR-7) |
| AI events stay reproducible | `analysis_runs`: durable inputs + immutable `result` + `engine_version` (PR-6) |
| Retention is the only history removal | soft-delete/retention matrix (`DATA_OWNERSHIP.md`); never in-place mutation (§10 rule 3) |
| No speculative history | feedback, capability progress, recommendation history modeled only when features land (PR-12) |

---

## 10. Report — summary

- **Every table and flagged concept is classified** into the six storage
  categories (plus SYSTEM KNOWLEDGE, called out separately); no concept is left
  ambiguous. `saved_looks` and the derived-score cluster are explicitly
  dual-form (mutable list / immutable snapshot; live cache / historical record).
- **The special-attention items resolve cleanly:** face/hair/grooming/style
  analyses are `analysis_runs` EVENT history + mutable profile projection;
  Style DNA is a derived view (never stored); Style Score is a cache + snapshot
  history; scans are immutable EVENT records; recommendations and feedback are
  AI-output/event history (conditional/feature-gated); wardrobe usage history
  lives in signals; daily outfits are a cache + conditional per-day history; AI
  capability progress is config only (not modeled); AI model versions are the
  `engine_version` reproducibility anchor.
- **Reproducibility is category-dependent and explicit** (§6): runs and saved
  looks are exactly reproducible; DNA and current values re-derive; shown
  recommendations and past daily looks are exact only if their conditional
  snapshot tables exist.
- **A newer AI analysis can never silently destroy an older one** (§7): INSERT a
  run + UPDATE a projection, never UPDATE a history row — enforced by append-only
  grants, immutable columns, the acyclic FK graph, and SET NULL cross-links.
- **Consistent with the whole STEP 4 set:** same table names, same lifecycle
  rules, same grants as `TABLE_DEFINITIONS.md`, `RELATIONSHIP_CONSTRAINTS.md`,
  and `DATABASE_DESIGN_RULES.md`. Nothing invented beyond the finalized domain
  model.

---

## Constraints honored

- No SQL, no database, no migrations, no repositories, no endpoints, no
  application code changes, no dependencies, nothing deleted.
- Every classification and reproducibility contract traces to
  `DOMAIN_STATE_AND_HISTORY.md` (§1–§8), `DOMAIN_RELATIONSHIPS.md`, and the
  prior STEP 4 documents; no behavior is invented.
- The real Fansivibe repository is the source of truth; the separate reference
  project was not merged.


