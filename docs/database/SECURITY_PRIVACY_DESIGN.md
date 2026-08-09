# Fansivibe — Database Security & Privacy Design

> **STEP 4 (continuation) — DATABASE DESIGN.** Defines the **security and privacy
> model** for the PostgreSQL schema designed in `TABLE_DEFINITIONS.md`: per
> sensitive-data-category sensitivity/ownership/access/deletion/retention/
> encryption/logging, the **user ownership boundary** (no cross-user access),
> and **account-deletion behavior**.
>
> This is the **privacy layer** over the logical schema. It does not implement
> authentication or authorization — auth is out of scope (see §7). It states
> *what* the database layer and the backend role must guarantee, and which
> controls are deferred to the auth/API design.
>
> **Documentation only — no code, no SQL, no migrations, no backend/Flutter
> changes, no dependencies, no media storage configured.** Claims verified
> against `DATA_OWNERSHIP.md`, `STORAGE_INVENTORY.md`,
> `DOMAIN_RELATIONSHIPS.md`, `DATABASE_DESIGN_RULES.md` (PR-10), and the
> STEP 4 database deliverables. The reference project was not merged.

---

## 1. Purpose and method

The task: define, for every sensitive data category, its **sensitivity**,
**owner**, **who may access**, **deletion requirements**, **retention
considerations**, **whether it is encrypted at rest**, and **whether access is
logged** — then define the **user ownership boundary** and the **account
deletion behavior**.

Method:

1. Reuse the ownership classification from `DATA_OWNERSHIP.md`
   (USER_OWNED / SYSTEM_OWNED / AI_GENERATED / KNOWLEDGE / EXTERNAL /
   DERIVED / HISTORICAL) as the **owner** axis.
2. Map every sensitive concept to its **actual schema home** in
   `TABLE_DEFINITIONS.md` (§8 concept→table map) and its **storage category**
   from `STORAGE_INVENTORY.md` (1 relational / 2 JSONB / 3 object storage /
   4 cache / 5 external / 6 temporary / 7 knowledge).
3. Derive access, deletion, and retention from the **relationship lifecycle**
   (`RELATIONSHIP_CONSTRAINTS.md`: composition = deleted-with-user; history =
   append-only) and the retention rules in `STORAGE_INVENTORY.md`.
4. The **user ownership boundary** (§2) is a construction rule (PR-10) applied
   to the whole schema: every user-owned row is scoped by `user_id`, and the
   backend enforces that identity. No row in the design can be read or written
   without its owning `user_id`.
5. **Encryption at rest** and **access logging** are stated as policies with an
   explicit default per category, because the database layer itself cannot
   enforce them — see §6.
6. **Account deletion** (§5) is defined as a database behavior (full CASCADE)
   plus the coordinated object-storage cleanup and external-service
   notifications that the schema requires to make erasure complete.

### 1.1 Scope boundaries

- **In scope:** sensitive data categories in PostgreSQL + their object-storage
  and external counterparts, ownership boundary, per-category access/deletion/
  retention/encryption/logging policy, account deletion.
- **Explicitly out of scope (do not implement here):** authentication,
  authorization, session handling, OAuth flows, API endpoint security, TLS,
  key management infrastructure. The DB design **assumes** an authenticated
  `user_id` from session context and that the backend never trusts a
  client-supplied `user_id` (`DATABASE_DESIGN_RULES.md` PR-10; `AZ12.3`).
- **Gates carried forward (from `DATABASE_DESIGN_RULES.md` §16):** media
  privacy policy **MS10.3** (decided before any media persistence — §4.3),
  conversation retention decision (§4.7), and auth design (§7).

### 1.2 The privacy invariant

> **Fansivibe processes appearance and image data. Treat it as
> privacy-sensitive.** The schema is built so that a user can never observe,
> query, or write another user's records, and account deletion is a complete
> right to erasure — no PII-holding snapshot survives unanchored.

---

## 2. User ownership boundary

### 2.1 The rule (PR-10, made concrete)

Every user-owned row in the schema carries a mandatory `user_id` FK →
`users(id)` and is scoped by it:

- `user_state` (1:1), `wardrobe_items`, `saved_looks`, `learning_signals`,
  `user_events`, `style_score_records`, `activity_days`, `analysis_runs`,
  `subscriptions` — and the conditional `today_look_records`,
  `recommendation_history`, `feedback_events`.
- The **user's id is never trusted from the client.** Identity comes from
  authenticated session context; the backend derives `user_id` from the session
  and injects it into every query. A client cannot select another user's rows
  by passing a foreign `user_id` (PR-10, `AZ12.3`).
- **Knowledge/reference tables** (`looks`, `wardrobe_categories`, `colors`,
  `materials`, `occasions`, `event_types`, `styles`, `signal_types`,
  `subscription_plans`, `run_types`) have **no `user_id`** — they are
  system-owned shared content read by all authenticated users. A user reads
  them but cannot modify them (content management only, K9.1).

### 2.2 Enforcement layers

| Layer | Mechanism | Who |
| --- | --- | --- |
| Schema | mandatory `NOT NULL` `user_id` FK on every user-owned table (PR-10, §4) | migration/DB |
| Query path | every read/write filtered by session-derived `user_id`; never client-supplied | backend/API role |
| FK lifecycle | `ON DELETE CASCADE` from `users` on all 12 composition FKs → deleting the account removes every child | database |
| Append-only history | `INSERT`/`SELECT` only grants on `learning_signals`, `style_score_records`, `activity_days`, `analysis_runs` (+ conditional history) → a user cannot alter past records (`DATABASE_DESIGN_RULES.md` §10 rule 1) | DB role grants |
| Blob storage | object keys namespaced `users/{user_id}/...` → cleanup/access can never cross users (`MEDIA_STORAGE_DESIGN.md` §7) | object storage |

### 2.3 What a user may and may not access

**May access:** their own user-owned rows; the system-owned knowledge tables
(read-only); nothing else.

**May never access:** any other user's user-owned rows; another user's blobs;
internal system state; logging output (§6.2).

### 2.4 Why the boundary holds even for history

History tables are children of `users` by composition (R7, R9; see
`RELATIONSHIP_CONSTRAINTS.md` §5.1) and are user-scoped by `user_id`. They have
**no FK to current-state entities** (e.g. `learning_signals` has no
item/look FK), so there is no join path through which a user could reach
another user's history either. Knowledge rows are shared but immutable to
users. The FK graph is acyclic (§6 of `RELATIONSHIP_CONSTRAINTS.md`), so the
boundary has no indirect escape.

### 2.5 What this document does not decide

Auth, sessions, and multi-device authorization are out of scope (§1.1, §7).
The boundary is designed to hold once identity exists; the exact provider and
merge semantics are open (`DATABASE_DESIGN_RULES.md` §16.1).

---

## 3. Sensitive data categories — master matrix

Every sensitive category, its schema/storage home, and the seven required
attributes. Sensitivity scale: **CRITICAL** (appearance/biometric/image data
with erasure obligations), **HIGH** (identity/account/entitlement data),
**MEDIUM** (user-authored personal data), **LOW** (non-personal system/
knowledge content). Retention column summarizes `STORAGE_INVENTORY.md` and the
STEP 4 retention rules; encryption/logging policies are defined in §6.

### 3.1 Identity and account

| Category | Schema / storage home | Sensitivity | Owner | Who may access | Deletion requirements | Retention | Encrypted at rest | Access logged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Account identity (`users`: auth pair, name, timestamps) | `users` (1 relational) | HIGH | USER_OWNED | the user; backend session; (no other user) | deleted on account deletion (CASCADE root) | life of account | **yes** (§6.1) | no (metadata only) |
| Auth reference (`auth_provider`, `auth_subject`) | `users` (1) | HIGH | USER_OWNED (external boundary) | auth service + backend only | removed at erasure; external provider state handled by auth design (out of scope) | life of account | **yes** | no (tokens never logged) |
| Current profile projection (face attributes, style, prefs, flags) | `user_state.style_profile` / `.preferences` / `.flags` (2 JSONB) | CRITICAL | USER_OWNED (content partly AI_GENERATED) | the user; assistant context builder; AI pipeline | deleted at account erasure; re-writable as unit while account lives (projection, PR-7) | life of account (projection); `source_run_id` provenance links history | **yes** (§6.1) | **yes** (appearance attributes, §6.2) |

### 3.2 Appearance and AI analysis

| Category | Schema / storage home | Sensitivity | Owner | Who may access | Deletion requirements | Retention | Encrypted at rest | Access logged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Face scan image | object storage via `analysis_runs.input_media` (3) | CRITICAL | USER_OWNED blob | the user; AI pipeline (transient); never another user | raw scan auto-expires unless saved; removed with run/account | `STORAGE_INVENTORY.md` §1.2 — latest per source kept; older pruned unless saved | **yes** (object storage, §6.1) | **yes** (§6.2) |
| Face analysis result (attributes) | `user_state.style_profile` (projection) + `analysis_runs.result` snapshot (2) | CRITICAL | USER_OWNED (content AI_GENERATED) | the user; AI pipeline | projection deleted at erasure; snapshots CASCADE at erasure; append-only while account lives | life of account / run retention per §1.6 | **yes** | **yes** |
| Outfit scan image | object storage via `analysis_runs.input_media` (3) | CRITICAL | USER_OWNED blob | the user; AI pipeline; never another user | auto-expire unsaved (30 days); with run/account | `STORAGE_INVENTORY.md` §1.3 | **yes** | **yes** |
| Outfit analysis result | `analysis_runs.result` (2 JSONB, immutable) | CRITICAL | USER_OWNED (content AI_GENERATED) | the user; AI pipeline | append-only; removed at erasure / retention prune (§1.6) | keep latest per source image; older only if saved | **yes** | **yes** |
| Hairstyle / grooming analysis result | `analysis_runs.result` (2 JSONB) | CRITICAL | USER_OWNED (content AI_GENERATED) | the user; AI pipeline | same as outfit result | latest per scan; catalog content versioned | **yes** | **yes** |
| Engine/run metadata (`engine_version`, status, timestamps) | `analysis_runs` columns (1) | MEDIUM | SYSTEM_OWNED (wraps user run) | the user; backend ops | removed at erasure | run retention | **yes** (at-rest policy) | no (non-PII metadata) |
| Generated images | object storage, referenced by run/saved-look (3) | CRITICAL | USER_OWNED / AI_GENERATED | the user | follow referencing run/saved look; orphan-swept; at erasure removed | while referenced; else pruned (§1.5) | **yes** | **yes** |

### 3.3 Personal content (user-authored)

| Category | Schema / storage home | Sensitivity | Owner | Who may access | Deletion requirements | Retention | Encrypted at rest | Access logged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Wardrobe items | `wardrobe_items` (1) | MEDIUM (image: CRITICAL) | USER_OWNED | the user; assistant context builder | deleted by user (edit/delete wiring P1) or at account erasure | until user deletes / erasure (R3) | **yes** | item rows: no; item images: **yes** |
| Wardrobe item image | object storage via `wardrobe_items.image_ref` (3) | CRITICAL | USER_OWNED blob | the user; never another user | with the item (CASCADE) + blob cleanup (§7 of `MEDIA_STORAGE_DESIGN.md`) | item/user lifecycle (§1.4) | **yes** | **yes** |
| Grooming information (profile-level attributes) | `user_state.style_profile` (projection, 2) | CRITICAL | USER_OWNED (content AI_GENERATED) | the user; AI pipeline | projection erasure; snapshots append-only | life of account (projection) | **yes** | **yes** |
| Saved looks | `saved_looks` (1) + `snapshot` JSONB (2, immutable) | MEDIUM | USER_OWNED (payload partly AI_GENERATED) | the user; profile screen | removed by user or at erasure | until user removes / erasure (R5) | **yes** | no (user's own list) |
| User events (calendar) | `user_events` (1) | MEDIUM | USER_OWNED | the user | edited/deleted by user (P1); removed at erasure | until user deletes; completed events archived (R4) | **yes** | no |
| Learning signals (append-only trace) | `learning_signals` (1) | MEDIUM | HISTORICAL | the user (read); analytics | never deleted while account lives (append-only, §3.3 of `RELATIONSHIP_CONSTRAINTS.md`); removed at erasure | long-lived; retention rules; **removed at erasure** | **yes** | no (anonymized aggregates only) |
| Activity days / style-score records | `activity_days`, `style_score_records` (1) | LOW–MEDIUM | HISTORICAL | the user (read); aggregation | append-only; removed at erasure | long-lived | **yes** | no |

### 3.4 Assistant conversations

| Category | Schema / storage home | Sensitivity | Owner | Who may access | Deletion requirements | Retention | Encrypted at rest | Access logged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Conversation messages | **transient today** (`STORAGE_INVENTORY.md` §1.10, cat. 6) — no table | CRITICAL | USER_OWNED (session) | the user; assistant pipeline | cleared with session; never stored unless retention decided | short window (30–90 days) **if** retention accepted; else session-only | n/a while transient; **yes** if ever persisted | **yes** (if persisted) |
| Assistant context snapshot (`AssistantUserContext`) | temporary processing (cat. 6), **never stored** (R47) | CRITICAL | DERIVED | per-request pipeline only | discarded | none | n/a | no (never logged) |
| Assistant action payloads | `learning_signals.context` (optional JSONB, not in P0) | MEDIUM | USER_OWNED | the user; analytics | append-only; at erasure | long-lived if built | **yes** | no |

### 3.5 Subscription and external

| Category | Schema / storage home | Sensitivity | Owner | Who may access | Deletion requirements | Retention | Encrypted at rest | Access logged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Subscription entitlement state | `subscriptions` (1) | HIGH | USER_OWNED (+ EXTERNAL entitlement, R10/R51) | the user; entitlement check | removed at erasure (CASCADE); external payment state cancelled via external service (R51) — §5 | life of account | **yes** | **yes** (entitlement changes, §6.2) |
| Plan catalog | `subscription_plans` (7 knowledge) | LOW | KNOWLEDGE | all authenticated users (read-only) | content management only; never user-deleted | versioned | n/a (non-PII) | no |
| Weather / other external cache | external service + cache (5/4), **not in DB** | LOW | EXTERNAL | all users (derived view) | cache-only, evicted | short TTL, no history (§1.9) | n/a | no |

### 3.6 Knowledge / system (non-sensitive)

| Category | Schema / storage home | Sensitivity | Owner | Who may access | Deletion requirements | Retention | Encrypted at rest | Access logged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Look catalog + vocabularies (categories, colors, occasions, styles, event types, signal types, run types) | `looks` + reference tables (7 / 1 knowledge) | LOW | KNOWLEDGE | all authenticated users (read-only) | deprecate, never delete while referenced (R30); content management | versioned, never tied to a user | n/a | no |
| Capability/plan config, processing config | knowledge/config (7) | LOW | SYSTEM_OWNED / KNOWLEDGE | all users (derived views) | config migration | versioned | n/a | no |

---

## 4. Special-attention deep dives

The nine categories the task flags, each with the full policy for its storage
home(s).

### 4.1 Face analysis

- **Home:** raw scan → object storage (`analysis_runs.input_media`); attributes
  → `user_state.style_profile` projection + `analysis_runs.result` snapshot.
- **Sensitivity:** CRITICAL — biometric-adjacent appearance attributes and a
  raw image of the face.
- **Access:** the owning user, the AI pipeline, and (in the future) the
  assistant context builder. Never another user; never logs.
- **Deletion:** raw scan auto-expires after analysis **unless saved**
  (`STORAGE_INVENTORY.md` §1.2); snapshots are append-only while the account
  lives; all of it CASCADEs at account erasure.
- **Retention:** attributes live for the account's life (they are the durable
  profile); scans keep the latest per source image, older pruned unless saved.
- **Encryption at rest:** yes (§6.1). **Access logged:** yes (§6.2).

### 4.2 Appearance analysis (outfit / hairstyle / grooming)

- **Home:** `analysis_runs.result` (immutable JSONB) + `input_media` (source
  image); projection attributes in `user_state.style_profile`.
- **Sensitivity:** CRITICAL — appearance data, explicitly privacy-sensitive
  (AGENTS safety; `DOMAIN_MODEL_RULES.md` §12).
- **Access:** owning user + AI pipeline only.
- **Deletion:** results are append-only (no `UPDATE`/`DELETE` grants) while the
  account lives; removed at erasure. Source images auto-expire unless saved.
- **Retention:** keep the latest per source image; older runs retained only if
  the user saved the look (`STORAGE_INVENTORY.md` §1.6).
- **Encryption at rest:** yes. **Access logged:** yes.

### 4.3 Photos (scans, item images, generated images, profile image)

- **Home:** all object storage behind `MediaRef` columns; never in PostgreSQL
  (PR-8). Profile image has **no column today** (future `users`/`user_state`
  `avatar_ref`).
- **Sensitivity:** CRITICAL (all user blobs). **Access:** owner only; blob keys
  namespaced `users/{user_id}/...` so no cross-user touch is possible
  (`MEDIA_STORAGE_DESIGN.md` §7).
- **Deletion:** blob lifecycle follows the referencing row; async cleanup job
  deletes orphaned blobs; account erasure removes all `users/{user_id}/...`
  blobs (complete erasure).
- **Retention:** per media type (§8 of `MEDIA_STORAGE_DESIGN.md`): scans
  auto-expire unless saved; item images follow the item; generated images while
  referenced; catalog images deprecate-not-delete.
- **Encryption at rest:** yes (object storage). **Access logged:** yes.
- **Gate:** **MS10.3** (media privacy policy) must be decided before any media
  persistence/bucket configuration; the `MediaRef` reference columns ship
  regardless (§6 of `MEDIA_STORAGE_DESIGN.md`).

### 4.4 Wardrobe

- **Home:** `wardrobe_items` relational rows + `image_ref` MediaRef.
- **Sensitivity:** MEDIUM (item metadata) / CRITICAL (item images).
- **Access:** owner + assistant context builder; never another user.
- **Deletion:** user-deleted (P1 wiring) with image cascade; removed at
  erasure (CASCADE R3).
- **Retention:** until user deletes or account erasure. Item deletion never
  deletes its signals (`STYLE_WARDROBE_DOMAIN_MODEL.md` §8; history survives).
- **Encryption at rest:** yes. **Access logged:** item rows no; item images yes.

### 4.5 Grooming information

- **Home:** profile-level attributes in `user_state.style_profile` (projection)
  and `analysis_runs.result` snapshots; catalog content (`looks`/grooming
  options) is knowledge.
- **Sensitivity:** CRITICAL (appearance attributes) — the domain treats grooming
  like face/appearance data.
- **Access:** owner + AI pipeline. **Deletion:** projection erasure + snapshot
  CASCADE at erasure; append-only while account lives.
- **Retention:** attributes life-of-account; run snapshots per §1.6.
- **Encryption at rest:** yes. **Access logged:** yes.

### 4.6 Personal profile (name, preferences, flags, style profile)

- **Home:** `users` (name/identity) + `user_state` (projection).
- **Sensitivity:** HIGH–CRITICAL (appearance attributes inside the profile).
- **Access:** owner only; assistant context derived per request (R47 — never
  stored).
- **Deletion:** at account erasure; the projection is re-writable as a unit
  while the account lives.
- **Retention:** life of account; `deleted_at` soft-delete is **not** introduced
  (PR-11 — only where a feature needs it; erasure is the removal path).
- **Encryption at rest:** yes. **Access logged:** appearance attributes yes;
  name/preferences no.

### 4.7 Assistant conversations

- **Home:** **transient today** — no table. If retention is later accepted,
  JSONB history with a short window (30–90 days) per `STORAGE_INVENTORY.md`
  §1.10.
- **Sensitivity:** CRITICAL — the conversation can restate appearance data and
  personal context.
- **Access:** the user only (and the assistant pipeline while processing).
- **Deletion:** session-clear today; a short-window retention job if persisted;
  always removed at erasure.
- **Retention:** default = transient. Retention is an **open product decision**
  (`DATABASE_DESIGN_RULES.md` §16.4); the minimal durable trace (learning
  signals) stays relational.
- **Encryption at rest:** yes if ever persisted. **Access logged:** yes if
  persisted; the context snapshot is never logged (R47).

### 4.8 Events

- **Home:** `user_events` (relational, P1) + `event_types` (knowledge).
- **Sensitivity:** MEDIUM — user-authored calendar/occasion data, can carry
  personal context.
- **Access:** owner only. **Deletion:** user edit/delete (P1 wiring); removed
  at erasure (CASCADE R4).
- **Retention:** until user deletes; completed events archived.
- **Encryption at rest:** yes. **Access logged:** no.

### 4.9 Subscription information

- **Home:** `subscriptions` (relational) + `subscription_plans` (knowledge) +
  external entitlement/payment service (R51).
- **Sensitivity:** HIGH — entitlement/paid state; payment data itself lives in
  the external service, **never in Fansivibe**.
- **Access:** the user; entitlement checks. **Deletion:** row CASCADEs at
  account erasure; the **external subscription must be cancelled/notified via
  the payment service** — Fansivibe does not hold payment instrument data.
- **Retention:** life of account; plan catalog versioned.
- **Encryption at rest:** yes. **Access logged:** yes (entitlement changes).

---

## 5. Account deletion behavior

### 5.1 Database behavior — full CASCADE

Deleting the `users` row removes **all 12 user-owned children** in one cascade,
including the historical/AI records (`learning_signals`, `style_score_records`,
`activity_days`, `analysis_runs`, and the conditional `today_look_records`,
`recommendation_history`, `feedback_events`). Full rationale and rejected
alternatives are in `RELATIONSHIP_CONSTRAINTS.md` §3.1–3.2. The cascade is a
**complete right to erasure**: no PII-holding snapshot survives unanchored.

### 5.2 Coordinated non-database steps

Erasure is complete only when all four layers act together:

| Layer | Action |
| --- | --- |
| PostgreSQL | delete `users` row → CASCADE all user-owned rows (including JSONB snapshots with embedded appearance data) |
| Object storage | async cleanup job deletes every `users/{user_id}/...` blob (scans, item images, generated images, future avatar) — §7 of `MEDIA_STORAGE_DESIGN.md` |
| External services | cancel/notify the subscription payment service (R51) and any future third parties; auth-provider state is handled by the auth design (out of scope) |
| Caches / transient | derived caches and per-request data are recomputable and evicted; nothing durable remains |

### 5.3 What is never left behind

- No orphaned `analysis_runs.result` snapshots, saved-look payloads, or signal
  rows (CASCADE, §3.1 of `RELATIONSHIP_CONSTRAINTS.md`).
- No user blobs (cleanup job, §7 of `MEDIA_STORAGE_DESIGN.md`).
- No anonymized "kept" signals — the `user_id SET NULL` alternative is rejected
  (§3.2).
- No `deleted_at` soft-delete resurrection path — PR-11 does not introduce it
  speculatively (§3.2).
- Knowledge tables (`looks`, vocabularies) are **not** deleted — they are
  system-owned and shared.

### 5.4 While the account lives

Account deletion is the **only** cascade path. While the account lives, history
is append-only (INSERT/SELECT grants) and current state is mutable by the user;
retention/soft-delete processes are the only history-removal path and are a
separate, future concern (§3.3 of `RELATIONSHIP_CONSTRAINTS.md`).

---

## 6. Encryption at rest and access logging

The database layer cannot fully enforce these; they are **platform/ops
policies** that the schema and operations must honor. Defaults per category are
in §3.

### 6.1 Encryption at rest

- **Default: all user data encrypted at rest.** Applies to PostgreSQL tables
  containing user-owned rows (identity, profile, wardrobe, events, signals,
  scores, analyses, subscriptions) and to **object storage** for all user blobs.
  Implementation (disk/volume encryption, key management) is an ops concern
  outside this document; the policy is that **no category in §3 is marked
  "no"** for user-owned data.
- **Knowledge/system data** (catalogs, vocabularies, config) may ride on the
  same at-rest encryption without a per-row requirement — no exception needed.
- **Derived caches and temporary processing data** (assistant context, current
  score, weather) hold no durable PII by construction (R47; §1.9) and are not
  separately encrypted.

### 6.2 Access logging

- **Never logged:** authentication tokens, assistant context snapshots,
  raw appearance/scan images in logs, full conversation text, and any
  user-owned payload echoed into log lines (AGENTS safety; PR-10).
- **Logged (access events only, no payload):** reads/writes of CRITICAL
  appearance data (face/outfit/grooming analysis results and images) and
  entitlement changes — an **audit trail of who accessed what category**, keyed
  by `user_id` + operation + timestamp, with **no content**.
- **Not logged:** ordinary reads of user-authored MEDIUM data (wardrobe rows,
  events, saved looks, signals) beyond standard request logging; these carry no
  content in logs.
- **Deletion proof:** access-log entries never expose the data they refer to;
  they are operational metadata only.

### 6.3 What the schema enforces vs. what ops must

| Requirement | Enforced by |
| --- | --- |
| `user_id` scoping on every user-owned row | schema (PR-10) |
| no client-trusted identity | backend/API (PR-10; out of scope here) |
| append-only history grants | DB role grants (§10 rule 1) |
| CASCADE erasure | schema (PR-4) |
| encryption at rest | platform/ops policy (§6.1) |
| access-log discipline (no PII in logs) | backend + ops policy (§6.2) |

---

## 7. Report

### Design principles

1. **Privacy by construction (PR-10):** mandatory `user_id` scoping on every
   user-owned row; the ownership boundary holds across current state, history,
   and blobs.
2. **Erasure is complete:** account deletion = full CASCADE + blob cleanup +
   external cancellation; no orphaned PII snapshots (§3.1–3.2 of
   `RELATIONSHIP_CONSTRAINTS.md`; §7 of `MEDIA_STORAGE_DESIGN.md`).
3. **History is append-only, never mutated** — a user cannot edit their past
   records; retention is the only removal path and erasure overrides it.
4. **AI output is never truth, and appearance data is never in logs.**
5. **Encryption at rest for all user data; access logging is metadata-only.**
6. **No speculative machinery:** no audit framework, no multi-tenant layer, no
   `deleted_at` columns, no media storage — per PR-12 and the gates in §1.1.

### Assumptions

1. Authentication exists and yields a trusted `user_id`; the backend never
   trusts a client-supplied one (`AZ12.3`).
2. Media privacy policy (MS10.3) is decided before any media persistence; the
   `MediaRef` reference columns ship regardless.
3. Conversation retention is an open product decision; the default is
   transient (§4.7).
4. Payment data lives in the external service; Fansivibe stores only an
   entitlement reference (R51).
5. The design is valid under either resolution of the open decisions in
   `DATABASE_DESIGN_RULES.md` §16.

### Open decisions carried forward

- **Auth design** (AU11.1/AU11.2) — pins identity, sessions, and anonymous→sync
  merge semantics; the boundary is designed for regardless.
- **Media privacy policy (MS10.3)** — decided before media persistence.
- **Conversation retention** — persist vs. transient (default transient).
- **Feedback design** — `feedback_events` shape created only when the feature
  lands (P1).

### Where this leaves the schema step

The security & privacy model is the final STEP 4 layer. The full database
design is now: rules → mapping → table definitions → relationships →
history/versioning → JSONB → media storage → indexes → **security & privacy**.
The next step after this series is the **schema/migration step** (actual
PostgreSQL DDL), which will encode the erasure semantics (§5), append-only
grants, and the ownership boundary (§2) into migrations.

---

## Constraints honored

- No PostgreSQL database created, no migrations written, no SQL run.
- No Flutter, routing, UI, or backend code changes; no repositories, no API
  endpoints, no dependencies added, no existing code deleted.
- No authentication/authorization implemented or designed at the code level;
  auth is explicitly scoped out and referenced as a prerequisite.
- Every claim traces to `DATA_OWNERSHIP.md`, `STORAGE_INVENTORY.md`,
  `DOMAIN_RELATIONSHIPS.md`, `DATABASE_DESIGN_RULES.md` (PR-4/PR-10/PR-12),
  and the STEP 4 database deliverables; nothing is invented beyond the domain
  model.
- The real Fansivibe repository is the source of truth; the separate reference
  project was **not** merged into this design.

