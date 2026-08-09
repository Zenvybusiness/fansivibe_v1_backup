# Fansivibe — Business Constraints Catalog

> **STEP 4 (continuation) — DATABASE DESIGN.** Identifies the **database-level
> business constraints** required by Fansivibe: the invariants that PostgreSQL
> must enforce so that no row in the schema can violate them even under
> concurrent access, buggy code, or a misbehaving client. For every constraint:
> **table**, **rule**, **PostgreSQL mechanism** (`UNIQUE`, `CHECK`,
> `FOREIGN KEY`, `NOT NULL`), and **reason**.
>
> This document is the **constraint contract** for the schema/migration step. It
> extends `DATABASE_DESIGN_RULES.md` §11 (the short list) into a full catalog,
> and it draws the **boundary**: what belongs in the database vs. what belongs
> in the domain/service layer.
>
> **Status: documentation only. No SQL, no database, no migrations, no
> repositories, no endpoints, no application code changes, nothing deleted.**
>
> **Sources:** `TABLE_DEFINITIONS.md` (the 23 logical tables and their
> constraints), `RELATIONSHIP_CONSTRAINTS.md` (FK lifecycle semantics),
> `DATABASE_DESIGN_RULES.md` (PR-1…PR-12, §11 business constraints, §10
> current-vs-history enforcement), `DOMAIN_RELATIONSHIPS.md` (R1–R51),
> `STORAGE_INVENTORY.md` (retention), and `SECURITY_PRIVACY_DESIGN.md`
> (ownership boundary).

---

## 1. Purpose and method

The task asks for the **database-level business constraints** Fansivibe
requires, with the examples listed in the prompt, and for each: table, rule,
PostgreSQL mechanism, reason. It also warns: **do not put business logic into
database constraints if it belongs in the domain/service layer.**

Method:

1. **Enumerate the invariants** the domain model states as unconditional rules
   (a wardrobe item always has a category and color; an event always has a
   type; a signal always has a type; at most one subscription per user; one
   activity row per user per day; one today's-look per user per date; scores in
   range; auth identity unique).
2. **Classify each into a mechanism** (`UNIQUE` / `CHECK` / `FOREIGN KEY` /
   `NOT NULL`) and give the exact table + column from `TABLE_DEFINITIONS.md`.
3. **Apply the DB-vs-domain boundary (§2):** a rule becomes a *database*
   constraint only when PostgreSQL can enforce it cheaply, unconditionally, and
   without recomputation; everything computed, workflow-dependent, or living
   inside an evolving JSONB payload stays in the domain/service layer.
4. **Cover every task example** in the prompt explicitly (§4), including the
   ones that correctly resolve to *domain-layer* rules.

### 1.1 Scope

- **In scope:** constraints on the **23 logical tables** from
  `TABLE_DEFINITIONS.md` (P0–P3, including the conditional tables
  `today_look_records`, `feedback_events`, `recommendation_history`).
- **Out of scope:** the auth/authorization layer, API security, retention jobs,
  and the media-privacy policy (MS10.3) — none is a schema constraint.
- **Open decisions (§16 of the rules doc) still gate specific vocabulary**
  (subscription status, feedback rating, exact `users` auth columns); the
  catalog notes each and remains valid under either resolution.

---

## 2. What belongs in the database vs. the domain/service layer

### 2.1 Rule for putting a constraint in the database

A business rule becomes a PostgreSQL constraint only if **all** hold:

| Condition | Meaning | Example that satisfies it |
| --- | --- | --- |
| **Unconditional** | The rule holds for every row, forever, with no exceptions by context. | A score is always 0–100. |
| **Local** | The rule depends only on the row (or a small, stable reference set), never on cross-row computation or other users' data. | `user_events.event_type_id` must exist in `event_types`. |
| **Mechanically cheap** | `UNIQUE`/`CHECK`/`FK`/`NOT NULL` can express it exactly — no triggers, functions, or procedural logic. | A subscription is 0..1 per user (`UNIQUE (user_id)`). |
| **Not recomputed** | The value is stored, not derived at read time. | `style_score_records.score` is stored; "is this feature available?" is derived. |
| **Stable vocabulary** | The allowed set is fixed and seeded. | `analysis_runs.status IN ('pending','completed','failed')`. |

### 2.2 What stays in the domain/service layer

| Situation | Why not a DB constraint | Example |
| --- | --- | --- |
| The value lives inside **evolving JSONB** (AI output, snapshots) | JSONB is explicitly not a query axis and its shape evolves (`PR-9`); validating it needs functions/triggers. | `analysis_runs.result` structure, `saved_looks.snapshot`, `looks.payload`. |
| The rule requires **computation or workflow** | Cross-entity, multi-step, or derived logic belongs in the service. | Recommendation "matches" the user's profile; capability availability (config × subscription, R45). |
| The vocabulary is **pending a product/billing decision** | A `CHECK` on an unsettled set is speculative (PR-12). | `subscriptions.status`, `feedback_events.rating`. |
| The rule is **temporal/retention policy** | Deletion-after-retention is a job, not a constraint. | "Latest analysis per source image" pruning (§1.6). |

### 2.3 Resulting policy

**Enforce in PostgreSQL:** uniqueness invariants, existence/ownership
references (FK + NOT NULL), scalar range/format checks, and stable
enumerations. **Enforce in the domain/service layer:** AI payload validation,
entitlement/capability logic, recommendation correctness, retention, and
anything pending an open decision.

---

## 3. Master constraint catalog

Constraints are grouped by mechanism. Each row gives **table · rule ·
mechanism · reason**. Rule IDs are stable for the migration step
(`BC-1` … `BC-n`).

### 3.1 `UNIQUE` — identity and cardinality invariants

| # | Table | Rule | Mechanism | Reason |
| --- | --- | --- | --- | --- |
| BC-1 | `users` | One account per external auth identity. | `UNIQUE (auth_provider, auth_subject)` | The provider+subject pair is the opaque external-boundary identity (PR-3). Prevents duplicate accounts for the same provider sign-in; the pair, not a raw subject, is unique because different providers can issue the same subject string. |
| BC-2 | `user_state` | Exactly **one current profile projection per user**. | PK on `user_id` (implies `UNIQUE (user_id)` + `NOT NULL`) | 1:1 composition R1/R2 — the `UserModel` projection is born with and deleted with the account. The user has one profile world, not many. |
| BC-3 | `subscriptions` | At most **one subscription per user** (0..1). | `UNIQUE (user_id)` | R10. Entitlement is derived from config × this single row (R45); a second row would make "which plan am I on?" ambiguous. |
| BC-4 | `activity_days` | One activity/streak record per user per date. | `UNIQUE (user_id, day)` | Per-user-per-day identity IS the row (composite PK semantics, PR-5 §11). Two rows for one styled day would double-count the streak. |
| BC-5 | `today_look_records` (P1, conditional) | One **primary daily outfit snapshot per user per date**. | `UNIQUE (user_id, day)` | The task's "one primary daily outfit per user per date". The daily look is a dated snapshot; at most one per user per day is the durable history rule. |
| BC-6 | `saved_looks` | **Deliberately no** `UNIQUE (user_id, look_id)`. | (none) | A user may legitimately save the same catalog look on different days (different saved-look rows with distinct `created_at` and snapshots). Uniqueness would break that legitimate behavior. |

### 3.2 `CHECK` — scalar range and format invariants

| # | Table | Rule | Mechanism | Reason |
| --- | --- | --- | --- | --- |
| BC-7 | `style_score_records` | Score is a **valid score range**. | `CHECK (score BETWEEN 0 AND 100)` | The stored snapshot must be a valid score. The live formula emits 60–100 but the persisted range is 0–100 (PR-5 §11); the check bounds the column regardless of formula drift. |
| BC-8 | `analysis_runs` | Run status is one of the **three valid states**. | `CHECK (status IN ('pending','completed','failed'))` | The run lifecycle is a fixed, seeded enumeration (PR-5); a free-string status would corrupt reproducibility guarantees (PR-6). |
| BC-9 | `users` | Display name is a **non-empty, bounded** string. | `CHECK (char_length(display_name) BETWEEN 1 AND 100)` | Input bound from the UI; prevents empty/blank identity and unbounded text. |
| BC-10 | `wardrobe_items` | Item name is non-empty and bounded. | `CHECK (char_length(name) BETWEEN 1 AND 100)` | Same input-bound rationale for a user-authored row. |
| BC-11 | `saved_looks` | Title is non-empty and bounded. | `CHECK (char_length(title) BETWEEN 1 AND 200)` | Saved-look titles persist from the look/UI; bounded to keep list rendering predictable. |
| BC-12 | `learning_signals` | Signal label is non-empty and bounded. | `CHECK (char_length(label) BETWEEN 1 AND 200)` | Append-only history labels stay readable and bounded. |
| BC-13 | `user_events` | Event title is non-empty and bounded. | `CHECK (char_length(title) BETWEEN 1 AND 200)` | Calendar titles bounded for rendering. |
| BC-14 | `looks` | Catalog title is non-empty and bounded. | `CHECK (char_length(title) BETWEEN 1 AND 200)` | System-authored content stays bounded. |
| BC-15 | `user_state` | Projection version counter is **non-negative**. | `CHECK (version >= 0)` | Optimistic-concurrency / migration counter can never go negative (PR-11). |
| BC-16 | Reference tables (all 9) | Label non-empty and bounded; `sort_order` **non-negative**. | `CHECK (char_length(label) BETWEEN 1 AND 100)`, `CHECK (sort_order >= 0)` | Vocabulary labels render in UI; ordering is 0-based presentation order, never negative. |

### 3.3 `FOREIGN KEY` — ownership and referential validity

#### 3.3.1 User ownership (composition, CASCADE) — the ownership boundary

| # | Table | Rule | Mechanism | Reason |
| --- | --- | --- | --- | --- |
| BC-17 | `user_state` | **Valid profile ownership** — the projection belongs to a user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | R1/R2 composition; born/deleted with the account (PR-4, PR-10). |
| BC-18 | `wardrobe_items` | **Valid wardrobe ownership** — every item belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | R3 composition; an item cannot exist without its owner; erasure cascades (PR-10). |
| BC-19 | `saved_looks` | **Valid ownership** — every saved look belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | R5 composition; save list is per-user (PR-10). |
| BC-20 | `learning_signals` | **Valid ownership** — every signal belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | R7 composition; append-only history scoped per user (PR-10, §3 of `RELATIONSHIP_CONSTRAINTS.md`). |
| BC-21 | `user_events` | **Valid ownership** — every event belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | R4 composition; calendar is per-user (PR-10). |
| BC-22 | `style_score_records` | **Valid ownership** — every score record belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | Composition (PR-4); score history is per-user. |
| BC-23 | `activity_days` | **Valid ownership** — every activity day belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | Composition; streak timeline is per-user. |
| BC-24 | `today_look_records` (P1, conditional) | **Valid ownership** — every daily-look record belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | Composition; daily history is per-user. |
| BC-25 | `feedback_events` (P1, feature-gated) | **Valid feedback ownership** — every feedback event belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | The reaction is user-authored and user-scoped (PR-10). |
| BC-26 | `analysis_runs` | **Valid ownership** — every analysis run belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | R6 composition; AI history scoped and erased with the account (PR-10). |
| BC-27 | `subscriptions` | **Valid ownership** — a subscription belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | R10; entitlement state erased with the account. |
| BC-28 | `recommendation_history` (P3, conditional) | **Valid recommendation ownership** — every shown/saved recommendation belongs to one user. | `user_id uuid NOT NULL FK → users(id) ON DELETE CASCADE` | R7-adjacent composition; recall analytics are per-user (PR-10). |

#### 3.3.2 Knowledge references (RESTRICT) — vocabulary validity

| # | Table | Rule | Mechanism | Reason |
| --- | --- | --- | --- | --- |
| BC-29 | `wardrobe_items` | Item always has a **valid category**. | `category_id text NOT NULL FK → wardrobe_categories(code) ON DELETE RESTRICT` | R18 — a wardrobe item is always categorized; the vocabulary is backend-controlled (K9.1), and a referenced category must not vanish under live items (PR-4). |
| BC-30 | `wardrobe_items` | Item always has a **valid color**. | `color_id text NOT NULL FK → colors(code) ON DELETE RESTRICT` | R18; same rationale as category. |
| BC-31 | `wardrobe_items` | Optional material is **valid when present**. | `material_id text NULL FK → materials(code) ON DELETE RESTRICT` | Optional texture; when supplied it must be from the vocabulary. |
| BC-32 | `user_events` | Event always has a **valid type**. | `event_type_id text NOT NULL FK → event_types(code) ON DELETE RESTRICT` | R34 — an event is always typed; the vocabulary is stable. |
| BC-33 | `learning_signals` | Signal always has a **valid type** (never a free string). | `signal_type text NOT NULL FK → signal_types(code) ON DELETE RESTRICT` | One of the 8 seeded types (PR-5); free strings would corrupt the learning feed. |
| BC-34 | `analysis_runs` | Run always has a **valid run type**. | `run_type text NOT NULL FK → run_types(code) ON DELETE RESTRICT` | outfit/face/hairstyle/grooming vocabulary; reproducibility needs a typed run. |
| BC-35 | `subscriptions` | Subscription always references a **valid plan**. | `plan_code text NOT NULL FK → subscription_plans(code) ON DELETE RESTRICT` | R44; entitlement is derived from config × plan, so the plan must exist. |

#### 3.3.3 Cross-links (SET NULL) — references that must not block the target's removal

| # | Table | Rule | Mechanism | Reason |
| --- | --- | --- | --- | --- |
| BC-36 | `saved_looks` | Catalog link is informational — **saved look survives look deprecation**. | `look_id text NULL FK → looks(code) ON DELETE SET NULL` | R30; the immutable `snapshot` keeps the ensemble when the catalog look is deprecated (K9.1). |
| BC-37 | `saved_looks` | Provenance link survives **run retention**. | `source_run_id uuid NULL FK → analysis_runs(id) ON DELETE SET NULL` | R32; a saved look stays intact when old runs are pruned under retention (§1.6). |
| BC-38 | `feedback_events` (P1) | Feedback target look is **optional and droppable**. | `target_look_id text NULL FK → looks(code) ON DELETE SET NULL` | The reaction survives catalog deprecation. |
| BC-39 | `feedback_events` (P1) | Feedback target saved look is **optional and droppable**. | `target_saved_look_id uuid NULL FK → saved_looks(id) ON DELETE SET NULL` | The reaction survives the user removing the saved look. |
| BC-40 | `recommendation_history` (P3) | Recommendation target look is **optional and droppable**. | `look_id text NULL FK → looks(code) ON DELETE SET NULL` | Recall trace survives look deprecation (P3). |

#### 3.3.4 Deliberately absent FKs

| # | Table | Rule | Mechanism | Reason |
| --- | --- | --- | --- | --- |
| BC-41 | `learning_signals` | **No FK** to any current-state entity (item/look/saved look). | (none) | History survives item/event/saved-look deletion (§10 rule 3). A signal outlives the entity that triggered it by design. |
| BC-42 | `saved_looks` / `feedback_events` / `recommendation_history` | **No FK** into `occasions`/`styles`/JSONB vocabularies. | (none) | References live inside JSONB (`user_state`, `looks.payload`); JSONB is not a query axis and cannot carry a hard FK (PR-9, K9.1). |

### 3.4 `NOT NULL` — mandatory presence

`NOT NULL` appears in three roles (each already listed above but stated as its
own mechanism per the task):

| # | Table(s) | Rule | Mechanism | Reason |
| --- | --- | --- | --- | --- |
| BC-43 | `users` | Identity columns always present. | `id`, `auth_provider`, `auth_subject`, `display_name` NOT NULL | The account root must always have an identity + name (PR-3). |
| BC-44 | all 12 user-owned tables | `user_id` always present. | `user_id NOT NULL` on every user-owned row | Ownership boundary (PR-10): no row exists without an owner; a NULL owner would defeat scoping. |
| BC-45 | `wardrobe_items` | Category and color always present. | `category_id NOT NULL`, `color_id NOT NULL` | R18 (enforced jointly with BC-29/BC-30). |
| BC-46 | `user_events` | Type always present. | `event_type_id NOT NULL` | R34 (with BC-32). |
| BC-47 | `learning_signals` | Type and label always present. | `signal_type NOT NULL`, `label NOT NULL`, `occurred_at NOT NULL` | Append-only trace must always be typed, labeled, and timestamped. |
| BC-48 | `saved_looks` | Snapshot always present (the durable record). | `snapshot jsonb NOT NULL`, `title NOT NULL`, `created_at NOT NULL` | A saved look without a frozen payload is meaningless (R31). |
| BC-49 | `analysis_runs` | Run metadata always present; `result` absent until completed. | `run_type NOT NULL`, `status NOT NULL`, `engine_version NOT NULL`, `created_at NOT NULL`; `result` NULL until `completed` | Reproducibility requires engine + type always; the result is written once at completion (PR-6). |
| BC-50 | `subscriptions` | Entitlement row always identifies plan + start. | `plan_code NOT NULL`, `status NOT NULL`, `started_at NOT NULL` | A subscription without a plan/status/start is invalid state. |
| BC-51 | `looks` + reference tables | Content identity always present. | `code NOT NULL`, `label/title NOT NULL`, `content_version NOT NULL` (looks) | Knowledge rows need stable identity + content version (PR-3, K9.1). |

---

## 4. Task examples — resolved

Every example from the prompt, mapped to its mechanism (and boundary):

| Task example | Resolution | Table · mechanism |
| --- | --- | --- |
| one primary profile per user | DB constraint | `user_state` PK on `user_id` (BC-2) |
| unique ownership relationships | DB constraints | `UNIQUE (auth_provider, auth_subject)` (BC-1); `UNIQUE (user_id)` on `subscriptions` (BC-3) |
| one primary daily outfit per user per date | DB constraint | `today_look_records UNIQUE (user_id, day)` (BC-5) |
| valid recommendation ownership | DB constraint | `recommendation_history.user_id FK NOT NULL` (BC-28); `look_id SET NULL` (BC-40) |
| valid outfit-item relationships | **domain/service layer** | Outfits are value objects in `looks.payload` / `saved_looks.snapshot` JSONB — no outfit table, no FK (PR-9, K9.1). Membership integrity is validated by the domain, not a constraint. |
| valid wardrobe ownership | DB constraint | `wardrobe_items.user_id FK NOT NULL CASCADE` (BC-18); category/color validity (BC-29/BC-30) |
| valid feedback ownership | DB constraint | `feedback_events.user_id FK NOT NULL` (BC-25); targets `SET NULL` (BC-38/BC-39) |
| valid subscription states | partially DB, partially domain | Ownership/0..1/plan = DB (BC-3, BC-27, BC-35); the **status vocabulary** stays in the domain layer until the billing decision fixes it (BC-53) |
| valid capability states | **domain/service layer** | Capability availability is *derived* from config × subscription at read time (R45); no capability rows, so no constraint (BC-54). |
| valid date ranges | partially DB, partially domain | Event dates are `date` (not timestamp) by design; the **business** validity of "event is in the past/future" is a workflow rule (domain). DB enforces only type + presence. |
| valid score ranges | DB constraint | `style_score_records CHECK (score BETWEEN 0 AND 100)` (BC-7) |
| valid confidence ranges | **domain/service layer** | Confidence lives inside `analysis_runs.result` JSONB (AI output, evolving shape). Validated by the AI result contract, not a DB `CHECK` (BC-52) |

---

## 5. Constraints deliberately kept OUT of the database

These are the prompt-adjacent rules that **must not** become DB constraints
because they belong in the domain/service layer (per §2):

| # | Rule | Why it is not a database constraint |
| --- | --- | --- |
| BC-52 | Analysis **confidence/result validity** (ranges, required fields, consistency of detected items) | Lives in `analysis_runs.result` JSONB — evolving AI output, not a query axis (PR-9). Validation belongs to the AI result contract/service. |
| BC-53 | **Subscription status transitions** (active→canceled→expired → …) and status vocabulary | Pending the billing integration (§16); a `CHECK IN (...)` on an unsettled set is speculative (PR-12). Ownership/plan/0..1 are already DB-enforced (BC-3/BC-35). |
| BC-54 | **Capability availability** ("does this user have feature X?") | Derived from config × subscription at read time (R45, PR-2). Storing or constraining it would duplicate derived state. |
| BC-55 | **Recommendation correctness** ("does this recommendation match this user's profile/wardrobe?") | A computation over user_state + wardrobe + catalog at generation time. The DB enforces only structural ownership (BC-28). |
| BC-56 | **Outfit-item membership** (an outfit references items the user owns) | Outfits are JSONB value objects; membership is validated by the domain when composing `looks.payload`/`saved_looks.snapshot`. |
| BC-57 | **Event date business validity** (not in the past, or required future date) | A workflow rule; the DB enforces only `date` type + `NOT NULL` (BC-50-area). |
| BC-58 | **Retention / auto-expiry** (latest analysis per source image, scan auto-expire, conversation window) | Temporal policy executed by jobs (`STORAGE_INVENTORY.md` §§1.2/1.3/1.6), never by row constraints. |
| BC-59 | **`saved_looks.snapshot` structural validity** (ensemble must reference owned items) | Immutable JSONB payload validated at save time by the service (R31). |
| BC-60 | **Daily-look product rule** (a daily look must exist for "styled" days) | Cross-row workflow between `activity_days` and `today_look_records`; enforcing it in DB would need triggers — domain/service concern. |

---

## 6. Constraint mechanics summary

The complete mechanism inventory the migration step will implement:

| Mechanism | Count | Examples |
| --- | --- | --- |
| `UNIQUE` | 5 + PKs | BC-1…BC-5 (plus PK uniqueness on `users`, `user_state`, entity ids) |
| `CHECK` | 12 | BC-7…BC-16 (score range, status enum, text bounds, version, sort order) |
| `FOREIGN KEY` (CASCADE) | 12 | BC-17…BC-28 (user composition) |
| `FOREIGN KEY` (RESTRICT) | 7 | BC-29…BC-35 (knowledge vocabularies) |
| `FOREIGN KEY` (SET NULL) | 5 | BC-36…BC-40 (cross-links) |
| `NOT NULL` | 9 groups | BC-43…BC-51 (identity, ownership, mandatory presence) |
| deliberately absent | 2 | BC-41…BC-42 (history independence, JSONB refs) |

**Total database-enforced rules: 51** (`BC-1`–`BC-51`); **domain/service-layer
rules documented for boundary clarity: 9** (`BC-52`–`BC-60`).

---

## 7. Report

### Design principles

1. **The database enforces only what it can enforce unconditionally** — every
   `BC-*` constraint is local, cheap, and vocabulary-stable (§2.1). Anything
   computed, workflow-dependent, or inside evolving JSONB is explicitly
   delegated to the domain/service layer (§2.2, §5).
2. **Ownership is the strongest invariant** — 12 CASCADE `user_id` FKs make the
   ownership boundary and account erasure structurally enforced (PR-4, PR-10;
   `SECURITY_PRIVACY_DESIGN.md` §2/§5).
3. **Uniqueness encodes real cardinality** — 1:1 profile, 0..1 subscription,
   one activity day per user per date, one daily look per user per date; no
   speculative uniqueness (e.g. `saved_looks` deliberately allows repeat saves,
   BC-6).
4. **Vocabulary references are never free strings** — every typed column is a
   RESTRICT FK to a seeded knowledge table (BC-29…BC-35), and JSONB id
   references are enforced in code (K9.1, BC-42).
5. **Cross-links never block removal** — SET NULL everywhere a child must
   survive its target's deprecation/retention (BC-36…BC-40).
6. **No triggers, no functions, no procedural checks** — the catalog uses only
   `UNIQUE`, `CHECK`, `FOREIGN KEY`, `NOT NULL`, per the task. Everything else
   is a documented domain-layer rule.

### Relationship to earlier STEP 4 deliverables

- **`TABLE_DEFINITIONS.md`** — this catalog restates its per-table constraints
  with rule IDs and reasons; no new columns are invented.
- **`DATABASE_DESIGN_RULES.md` §11** — the short list is expanded here from 9
  rows to the full `BC-*` catalog; §10 rule 1 (append-only grants) remains the
  mechanism that *blocks* `UPDATE`/`DELETE` on history, complementary to `CHECK`.
- **`RELATIONSHIP_CONSTRAINTS.md`** — the FK actions here match §5 of that
  document exactly (12 CASCADE / 7 RESTRICT / 5 SET NULL).
- **`SECURITY_PRIVACY_DESIGN.md`** — the ownership boundary (its §2) is the
  purpose of BC-17…BC-28 and BC-44.

### Open decisions carried forward

- **Subscription status vocabulary** (BC-53) — `CHECK` added when the billing
  integration fixes the set.
- **Feedback rating vocabulary** (BC-38/BC-39 area) — `feedback_events` created
  only when the feature lands; `rating` CHECK follows the feedback design.
- **`users` auth columns** — `UNIQUE (auth_provider, auth_subject)` is designed
  for regardless; exact column set waits on auth (AU11.1/AU11.2).
- **`today_look_records` / `recommendation_history`** — conditional tables
  created only when their product decisions land (PR-12).

---

## Constraints honored

- No SQL written, no PostgreSQL database created, no migrations, no triggers,
  no functions, no repositories, no endpoints.
- No Flutter, routing, UI, or backend code changes; no dependencies added;
  nothing deleted.
- Every constraint traces to `TABLE_DEFINITIONS.md`, `DATABASE_DESIGN_RULES.md`
  (§11), `RELATIONSHIP_CONSTRAINTS.md`, `DOMAIN_RELATIONSHIPS.md`, and the
  finalized domain model; nothing is invented beyond it.
- The boundary rule (§2) is applied honestly: rules that belong in the
  domain/service layer are documented as such (BC-52…BC-60), not forced into
  database constraints.
- The real Fansivibe repository is the source of truth; the separate reference
  project was not merged.
