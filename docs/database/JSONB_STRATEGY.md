# Fansivibe — JSONB Strategy

> **STEP 4 (continuation) — DATABASE DESIGN.** Determines where PostgreSQL
> **JSONB** is used and where it is **deliberately not used**, for every
> candidate JSON structure in the finalized domain model. Each candidate is
> evaluated against seven questions: why relational columns are insufficient,
> expected schema stability, query requirements, indexing requirements, whether
> it is AI-generated, whether it is historical, and whether it needs relational
> references.
>
> **Status: documentation only. No SQL, no database, no migrations, no
> repositories, no endpoints, no application code changes, nothing deleted.**
>
> **Sources:** `DATABASE_DESIGN_RULES.md` PR-9 (the JSONB guardrail) and §8
> (the allowed/forbidden matrix), `DOMAIN_TABLE_MAPPING.md` §3 (per-concept
> JSONB determinations), `TABLE_DEFINITIONS.md` (the actual JSONB columns),
> `HISTORY_AND_VERSIONING.md` (immutable-snapshot vs live-cache), and
> `DOMAIN_STATE_AND_HISTORY.md` (AI-output-never-truth).

---

## 1. Purpose and method

JSONB is a **deliberate exception**, never a normalization dodge (PR-9). This
document pins, per candidate, whether the JSONB decision holds and why. The
evaluation answers the seven questions the task requires, then a verdict:

| # | Question | What it decides |
| --- | --- | --- |
| 1 | Why are relational columns insufficient? | The structural reason (evolving shape, unit read/write, unbounded variability, immutability). |
| 2 | Expected schema stability | Stable / evolving — a *volatile or open shape* is the strongest JSONB argument. |
| 3 | Query requirements | Is the value ever filtered/joined/counted *inside* the JSON? A query axis must be a column, not JSONB. |
| 4 | Indexing requirements | Which indexes are needed (GIN on JSONB vs none vs relational btree). |
| 5 | AI-generated? | AI output may be stored only as a snapshot, never as current truth. |
| 6 | Historical? | Immutable snapshots are the sanctioned JSONB use; live current state is not. |
| 7 | Needs relational references? | If something inside must be FK'd/joined, it must be a column or an FK-able id inside the JSONB. |

**The core decision rule (PR-9):** JSONB is justified **only** when the payload
is (a) large, structured, evolving, and written/read **as a unit**, **or**
(b) an **immutable snapshot** of AI/derived output whose shape is not a query
axis. Everything else must be relational.

---

## 2. The JSONB decision test

### 2.1 Use JSONB when (any of)

| Condition | Example |
| --- | --- |
| The shape **evolves with the AI pipeline** and would churn columns every model iteration | `analysis_runs.result` |
| Written and read **as a unit**, never partially | `user_state.style_profile` |
| An **immutable snapshot** not used as a query axis | `saved_looks.snapshot`, `today_look_records.snapshot` |
| Sparse, additive, id-list state with no per-item query | `user_state.preferences`, `user_state.flags` |
| A **reference** value, not the thing itself | `image_ref` / `input_media` (MediaRef) |
| Backend-owned **content** whose rich shape is versioned externally | `looks.payload` (K9.1) |

### 2.2 Do NOT use JSONB when (any of)

| Forbidden | Why |
| --- | --- |
| The fact is **queried, joined, or counted** (PR-1) | JSONB is not a relational query axis (rules §8) |
| It would **replace a vocabulary reference** | category/color/occasion/type must be an FK id, never an embedded value (K9.1) |
| It would **mirror a Flutter/DTO model** wholesale | DBR-0; wire contracts stay code |
| It would store **AI output as current truth** | AI output is never a source of truth (PR-6) |
| It would hold **media bytes** (base64) | PR-8; PostgreSQL never stores blobs |
| It would let an **entity's core rows dodge normalization** | the `wardrobe_items`/`user_events` anti-pattern (§5) |

---

## 3. Master decision matrix

| Candidate | Verdict | Home |
| --- | --- | --- |
| AI analysis payloads | **USE** (immutable snapshot) | `analysis_runs.result` |
| AI recommendation metadata | **USE** (conditional, immutable snapshot) | `recommendation_history.snapshot` |
| Model-specific output | **USE** (nested in the run result) | inside `analysis_runs.result` |
| Flexible AI observations | **USE** (nested, never a column) | inside `analysis_runs.result` / `saved_looks.snapshot` |
| Decision context | **DO NOT STORE** (transient) | none; optional frozen copy in a history `context` |
| Assistant action payloads | **DO NOT STORE** (config) | config; execution traced by signals, payload in `learning_signals.context` |
| Current style/face profile projection | **USE** | `user_state.style_profile` |
| Preferences (vocab-id lists) | **USE** | `user_state.preferences` |
| User/derived flags | **USE** | `user_state.flags` |
| Saved-look frozen payload | **USE** | `saved_looks.snapshot` |
| Analysis input/source media ref | **USE** (reference only) | `analysis_runs.input_media`, `image_ref` columns |
| Look catalog ensemble content | **USE** (backend-governed) | `looks.payload` |
| Score breakdown snapshot | **USE** | `style_score_records.breakdown` |
| Per-day activity summary | **USE** (optional) | `activity_days.summary` |
| Daily-look snapshot (conditional) | **USE** | `today_look_records.snapshot` |
| Plan capability names (config) | **USE** | `subscription_plans.features` |
| Wardrobe items / events / signals as blobs | **REJECT** (must be rows) | `wardrobe_items`, `user_events`, `learning_signals` rows |
| Score / streak / today's-look current truth | **REJECT** (cache) | recomputed; history = snapshot rows |
| Feedback payload | **REJECT** | typed columns (`rating`, `reason`) |
| Weather data | **REJECT** | external cache, never durable |
| Assistant DTOs / replies | **REJECT** | wire contract (DBR-0) |

---

## 4. Candidate evaluations

Each candidate answered against the seven questions. Verdict: **USE** / **USE
(nested)** / **REJECT** / **DO NOT STORE**.

### 4.1 AI analysis payloads (`analysis_runs.result`)

- **Why relational columns are insufficient:** analysis output differs by run
  type (outfit vs face vs hair vs grooming) and by engine iteration; typed
  columns would need a near-empty wide table per type and a migration per model
  release. The payload is written whole on completion and read whole for display
  or replay.
- **Expected schema stability:** **low / evolving** — changes with every engine
  update; exactly why the shape must not be owned by the schema.
- **Query requirements:** none inside the JSON — the run row is the query axis
  (`user_id`, `run_type`, `status`, `created_at`); the result is never
  filtered/joined/counted by field.
- **Indexing requirements:** none (no JSON query axes; rules §12). Relational
  btree on `(user_id, created_at)` covers the run history.
- **AI-generated:** **yes** — an AI-output snapshot.
- **Historical:** **yes** — immutable once written (append-only grants, PR-6).
- **Needs relational references:** no internal FKs — the snapshot is
  self-contained; the run row carries the `user_id`/`run_type` FKs.
- **Verdict:** **USE** (`analysis_runs.result`, immutable snapshot).

### 4.2 AI recommendation metadata (`recommendation_history.snapshot`)

- **Why relational columns are insufficient:** score + reasons at show time are
  AI output whose shape may evolve with the recommendation engine; a column-per-
  reason would fight that. The `saved` bool, `shown_at`, and `look_id` are the
  actual query axes and stay relational.
- **Expected schema stability:** **low** (P3, feature not built; shape will be
  defined when the analytics feature lands).
- **Query requirements:** at most aggregate counts (`saved`, per user) — all
  on relational columns; the snapshot itself is never a filter.
- **Indexing requirements:** none on the JSONB; relational btree on
  `(user_id, shown_at)` for the trace.
- **AI-generated:** **yes**.
- **Historical:** **yes** (append-only, conditional P3).
- **Needs relational references:** `look_id` is a relational FK (SET NULL);
  the snapshot embeds the frozen score/reasons copy.
- **Verdict:** **USE** (`recommendation_history.snapshot`, only if the P3
  decision lands).

### 4.3 Model-specific output (engine fields inside a run result)

- **Why relational columns are insufficient:** a specific engine/version emits
  fields the schema cannot know in advance; promoting them to columns couples
  the DB to one model version (PR-6 reproducibility requires the opposite).
- **Expected schema stability:** **very low** — per-version by definition.
- **Query requirements:** none; model-specific fields are never queried.
- **Indexing requirements:** none.
- **AI-generated:** **yes**.
- **Historical:** **yes** — frozen inside the immutable `result`.
- **Needs relational references:** no; `engine_version` (relational column) is
  the key that maps the payload back to the model that produced it.
- **Verdict:** **USE (nested)** — always inside `analysis_runs.result`, never a
  top-level column.

### 4.4 Flexible AI observations (varied/optional detected attributes)

- **Why relational columns are insufficient:** observations vary in presence and
  shape (e.g. a detected attribute may carry a confidence, a range, or nothing);
  a fixed column set cannot express the open set without spamming nullable
  columns.
- **Expected schema stability:** **very low** (open-ended).
- **Query requirements:** none — observations are read as part of the parent
  snapshot, never filtered by field.
- **Indexing requirements:** none.
- **AI-generated:** **yes**.
- **Historical:** **yes** — carried inside an immutable snapshot
  (`analysis_runs.result`, `saved_looks.snapshot`).
- **Needs relational references:** no; observations are self-contained values.
- **Verdict:** **USE (nested)** — inside an approved snapshot; **never** a
  standalone JSONB column or table (that would be a query/analysis axis in
  disguise, PR-1).

### 4.5 Decision context (AI decision / assistant context)

- **Why relational columns are insufficient:** n/a — this is a **per-request,
  transient** serialization of derived state (AssistantUserContext), never a
  durable concept (`DOMAIN_TABLE_MAPPING.md` §3.5/§3.6).
- **Expected schema stability:** n/a (not stored).
- **Query requirements:** none — ephemeral.
- **Indexing requirements:** none.
- **AI-generated:** the context is a **serialized DTO snapshot**, not AI output
  itself.
- **Historical:** **no** by default — conversations/context stay transient
  (retention is a pending privacy decision). A **frozen copy is allowed only**
  inside a history row's `context` JSONB when reproducibility of a decision is
  actually needed.
- **Needs relational references:** no — it is a projection of other tables.
- **Verdict:** **DO NOT STORE** — no column, no table; optional frozen copy in
  `learning_signals.context` if a decision must be re-auditable.

### 4.6 Assistant action payloads

- **Why relational columns are insufficient:** n/a — assistant actions are
  **system config** (16 action ids + route map), not user data; they have no
  durable payload in the DB (`DOMAIN_TABLE_MAPPING.md` §3.6).
- **Expected schema stability:** n/a (config store).
- **Query requirements:** none — config lookup is by action id, not by payload.
- **Indexing requirements:** none.
- **AI-generated:** no — actions are config; only the *reply* is AI-generated
  (and replies are wire contract, never stored — DBR-0).
- **Historical:** no; action execution is traced as `learning_signals`
  (`assistant_message`, `suggestion_opened`, `assistant_navigation`).
- **Needs relational references:** no.
- **Verdict:** **DO NOT STORE** — actions live in config; any small execution
  payload may ride in `learning_signals.context`, never as its own JSONB column.

### 4.7 Current style/face profile projection (`user_state.style_profile`)

- **Why relational columns are insufficient:** current profile state is written
  and read **as a unit**, its shape evolves with the AI pipeline, and it carries
  cross-feature state (face attributes + `style_type` + `source_run_id`
  provenance) that no stable column set predicts.
- **Expected schema stability:** **medium/low** — evolves with AI features.
- **Query requirements:** read whole on profile load; never filtered by inner
  attribute.
- **Indexing requirements:** none.
- **AI-generated:** content is AI-produced but the **projection is current
  state**, not a snapshot — the sanctioned non-snapshot JSONB case (PR-7).
- **Historical:** no — mutable projection with provenance; history lives in
  `analysis_runs`.
- **Needs relational references:** `source_run_id` is an id into `analysis_runs`
  (app-enforced inside JSONB, per `RELATIONSHIP_CONSTRAINTS.md` §5.4);
  `style_type` is an id into `styles` (app-enforced).
- **Verdict:** **USE** (`user_state.style_profile`).

### 4.8 Preferences and flags (`user_state.preferences`, `user_state.flags`)

- **Why relational columns are insufficient:** preferences are a **sparse,
  additive set of vocabulary ids** (e.g. `preferred_occasions`) with no per-item
  query; flags are a small, sparse set with no join axis. Typed columns per
  preference/flag would be near-empty and churn on every addition.
- **Expected schema stability:** **medium** (preferences, additive); **high**
  (flags, small stable set).
- **Query requirements:** none per item — the whole set is loaded with the
  profile.
- **Indexing requirements:** none.
- **AI-generated:** no (user choices) / flags partly derived.
- **Historical:** no — current state.
- **Needs relational references:** the preference *ids* reference vocabulary
  codes (`occasions`, `styles`) — ids inside JSONB, **never embedded values**
  (K9.1; app-enforced).
- **Verdict:** **USE** (`user_state.preferences`, `user_state.flags`).

### 4.9 Saved-look frozen payload (`saved_looks.snapshot`)

- **Why relational columns are insufficient:** the ensemble/score/reasons at
  save time are AI/derived output with an evolving shape and are **never a
  query axis** — they exist only to be replayed.
- **Expected schema stability:** **high** — frozen by construction once written
  (R31); the shape only matters at write time.
- **Query requirements:** none — the list query is on `user_id`/`created_at`.
- **Indexing requirements:** none.
- **AI-generated:** yes (the saved recommendation's output).
- **Historical:** yes — immutable snapshot; the list rows themselves are current
  state (dual form, `HISTORY_AND_VERSIONING.md` §3).
- **Needs relational references:** no — self-contained; `look_id`/`source_run_id`
  are relational columns (SET NULL).
- **Verdict:** **USE** (`saved_looks.snapshot`).

### 4.10 MediaRef references (`image_ref`, `analysis_runs.input_media`)

- **Why relational columns are insufficient:** a reference (object key/URL +
  media type + optional display metadata) is a **value, not a query axis**; the
  bytes live in object storage (PR-8). Typed columns would add empty fields for
  optional metadata.
- **Expected schema stability:** **medium** (small, stable shape).
- **Query requirements:** none beyond "read the ref to load the asset".
- **Indexing requirements:** none.
- **AI-generated:** no — a durable input/reference, not AI output.
- **Historical:** no (input_media on a historical row is a durable *input*).
- **Needs relational references:** no — points **outward** to object storage,
  never into a DB table.
- **Verdict:** **USE** (`image_ref`, `input_media`) — reference metadata only,
  never bytes.

### 4.11 Look catalog ensemble content (`looks.payload`)

- **Why relational columns are insufficient:** the ensemble value object's rich
  content shape is **backend-authored and versioned** (K9.1); the schema would
  couple to a content format the backend controls.
- **Expected schema stability:** **medium/low** — governed by the K9.1 decision;
  versioned via `content_version`.
- **Query requirements:** none inside the JSON — catalog lookups are by `code`.
- **Indexing requirements:** none.
- **AI-generated:** no — system knowledge content.
- **Historical:** no — versioned content, not user history.
- **Needs relational references:** tags inside the payload reference
  `occasions`/`styles` codes (app-enforced; no hard FK into JSONB).
- **Verdict:** **USE** (`looks.payload`), pending the K9.1 shape decision.

### 4.12 Derived-history snapshots (`breakdown`, `summary`, `snapshot`)

- **Why relational columns are insufficient:** `style_score_records.breakdown`,
  `activity_days.summary`, and `today_look_records.snapshot` are immutable
  derived output written/read as a unit; their inner detail is never queried.
- **Expected schema stability:** **medium-high** — the top-level keys
  (`score`, `day`) are relational; the inner payload is free to evolve.
- **Query requirements:** none inside the JSON — trend/streak queries run on the
  relational columns (`score`, `recorded_at`, `day`).
- **Indexing requirements:** none on JSONB; btree on the dated relational
  columns.
- **AI-generated:** derived (score/activity) or AI (daily look) — either way,
  snapshots.
- **Historical:** yes — append-only.
- **Needs relational references:** no — self-contained snapshots.
- **Verdict:** **USE** for all three.

### 4.13 Plan capability names (`subscription_plans.features`)

- **Why relational columns are insufficient:** a config list of capability names
  is sparse and additive; there is no per-capability query and no relational need.
- **Expected schema stability:** **medium** (config-driven, PR-12).
- **Query requirements:** none beyond "what does this plan include" at read time.
- **Indexing requirements:** none.
- **AI-generated:** no — config content.
- **Historical:** no.
- **Needs relational references:** no — names are config strings; entitlement is
  **derived** from config × `subscriptions`, never stored (R45).
- **Verdict:** **USE** (`subscription_plans.features`).

---

## 5. Anti-patterns — JSONB must NOT simplify core relational concepts

These are the violations PR-9 and the task's warning forbid. Each is a real
temptation; each is rejected with the correct relational home.

| Anti-pattern | Why it's wrong | Correct home |
| --- | --- | --- |
| Store `wardrobe_items` as one JSONB array per user | items are **queried/counted/filtered** (PR-1) | `wardrobe_items` rows |
| Store `user_events` as JSONB | events are dated, **individually edited**, and FK'd to `event_types` | `user_events` rows |
| Store `learning_signals` as one JSONB log | signals are typed, appended, and feed aggregates | `learning_signals` rows + `context` JSONB only |
| Store the saved-looks list as JSONB | the list is the current-state query axis | `saved_looks` rows; `snapshot` JSONB per row |
| Store score/streak/today's-look as JSONB truth | derived values are caches; storing them as JSONB makes them look like truth | recomputed; history = snapshot rows |
| Store feedback as JSONB | `rating` is a typed, stable value | typed columns (`rating`, `reason`) on `feedback_events` |
| Embed vocabulary values (not ids) in JSONB | duplicates knowledge per user (K9.1) | id references into reference tables; ids inside JSONB where allowed |
| Mirror assistant DTOs / Flutter models wholesale | DBR-0; wire contract belongs in code | no table, no JSONB column |
| Base64 media inside JSONB | PR-8 — PostgreSQL never stores bytes | object storage + `MediaRef` refs |
| Use JSONB because "we'll add GIN later" | a query axis inside JSONB means the fact was relational all along | promote to a column; add btree |

---

## 6. Indexing policy for approved JSONB

- **No GIN indexes.** Every approved JSONB column is explicitly **not a query
  axis** (rules §8, §12); adding GIN would be speculative and invite
  JSONB-as-query abuse.
- The query surface of every approved payload already exists **relationally**
  on the same row: `(user_id, created_at)`, `(user_id, day)`, `score`,
  `signal_type`, `run_type`, etc. Those are the btree indexes to build.
- If a future feature genuinely needs to filter inside a payload, the fix is to
  **promote the field to a relational column** (additive migration, PR-11) — not
  to index the JSONB.

---

## 7. Report — summary

- **Every candidate is decided** with all seven required attributes: the six
  task candidates resolve to **USE** (`analysis_runs.result`,
  `recommendation_history.snapshot`), **USE (nested)** (model-specific output,
  flexible observations), and **DO NOT STORE** (decision context, assistant
  action payloads).
- **The approved JSONB set is exactly the rules-doc §8 matrix**, no more:
  current-state unit payloads (`user_state`), immutable AI/derived snapshots
  (`saved_looks.snapshot`, `analysis_runs.result`, score/day/look snapshots),
  MediaRef references, and `looks.payload` (K9.1 content).
- **The forbidden set is enforced as anti-patterns (§5):** no JSONB for
  query/join/count axes, no vocabulary-value embedding, no DTO mirrors, no media
  bytes, no JSONB-as-truth for derived values.
- **Indexing is relational-only** — no GIN anywhere; JSONB stays a
  non-query-axis by design, with promotion-to-column as the escape hatch.
- **Consistent with the whole STEP 4 set:** same columns as
  `TABLE_DEFINITIONS.md`, same justifications as `DATABASE_DESIGN_RULES.md` §8,
  same reproducibility/snapshot semantics as `HISTORY_AND_VERSIONING.md`.

---

## Constraints honored

- No SQL written, no database created, no migrations, no repositories, no
  endpoints, no application code changes, no dependencies, nothing deleted.
- Every verdict traces to PR-9 and the finalized domain model; JSONB is never
  used to simplify a core relational concept.
- The real Fansivibe repository is the source of truth; the separate reference
  project was not merged.


