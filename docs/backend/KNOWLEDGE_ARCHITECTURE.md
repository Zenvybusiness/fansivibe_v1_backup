# Fansivibe — Knowledge Architecture

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Defines the **Knowledge system**
> of Fansivibe — how curated knowledge (style/color/hair/grooming/clothing/
> outfit principles) is stored, validated, versioned, and served to the
> Decision Engine and features, **kept strictly separate from user-generated
> data.**
>
> ```
>            ┌───────────────────────────────┐
>            │  Decision Engine (M6)         │   calls KnowledgeSource port
>            └──────────────┬────────────────┘
>                           │  port (DR-6 / BA-11)
>            ┌──────────────▼────────────────┐
>            │  Knowledge Service (M5)       │  validate → lookup → retrieve
>            └──────────────┬────────────────┘
>                           │
>      ┌────────────────────┼─────────────────────┐
>      │                    │                     │
>   static files        DB tables            cache
>   (rules, vocab)    (looks, catalog)     (hot reads)
> ```
>
> **Status: architecture design only. Nothing is implemented.** No code,
> files, or directories are created; the live assistant contract
> (`POST /v1/assistant/chat`) and the current `catalog.py` are unchanged.
>
> **Source of truth:** the real Fansivibe repository. The separate reference
> project's knowledge implementation is **not** used (BMM-0, no blind
> copying).
>
> **Grounding facts (BAR-0):**
> - Today all knowledge is **one static Python file** (`backend/app/data/
>   catalog.py`): a wardrobe mirror, 2+ looks, 2 hairstyles, 2 grooming
>   styles, a tip, an insight, `OCCASIONS`, `OCCASION_TO_LOOK`, and
>   `NAVIGATION_MAP`. The assistant reads it directly (K9.1 today is satisfied
>   by this single file).
> - The knowledge module (M5) owns E5 `Look` + the vocabulary tables
>   (`categories`, `colors`, `occasions`, `size_categories`, `items`) in the
>   STEP 4 schema; it is **system-owned** data, never user-owned, and is
>   **never deleted** by erasure (TRX-8 keeps knowledge tables).
> - **Knowledge is separate from user data by construction:** different
>   tables, different owners, different lifecycle — no user write ever lands
>   in a knowledge table, and no knowledge write is ever user-scoped.

---

## 1. Purpose and scope

This document defines:

1. **The concepts** — knowledge source, repository, validation, version,
   lookup, retrieval, and the relationship with the Decision Engine.
2. **The knowledge types** — style rules, color rules, face-shape guidance,
   hairstyle knowledge, grooming knowledge, clothing knowledge, outfit
   principles.
3. **The storage decision for each type** — static / versioned /
   database-backed / file-backed / cached.
4. **The separation guarantees** — how knowledge never mixes with
   user-generated data.

It does **not** implement the knowledge service, define SQL, or write content.

**Grounding rules from accepted docs:**
- **K9.1 / BA-11 (single knowledge source):** one canonical knowledge
  service; no feature hardcodes its own category/occasion lists; the
  assistant, discover, and generation all read knowledge through the port.
- **DR-6 (knowledge adapters → knowledge interfaces):** consumers depend on
  `KnowledgeSource`; the concrete catalog lives behind the adapter
  (`infrastructure/external/knowledge.py`), seeded from today's `catalog.py`.
- **BA-3:** the knowledge *port* lives in domain; adapters in infrastructure.
- **TRX-8:** knowledge tables are never deleted (erasure excludes them).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `backend/app/data/catalog.py` | The real, current knowledge content (static, single-file) — the seed. |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | E5 `Look` + vocabulary value objects; ownership (§7): knowledge is system-owned. |
| `TABLE_DEFINITIONS.md` | The knowledge tables (`looks`, `categories`, `colors`, `occasions`, `size_categories`, `items`). |
| `DATABASE_DESIGN_RULES.md` | PR-3 stable codes / deprecate-not-delete; PR-7 current-state-vs-history; phased build order. |
| `SECURITY_PRIVACY_DESIGN.md` | Knowledge is public/system data, not user PII; erasure excludes it (TRX-8). |
| `BACKEND_MODULE_MAP.md` | M5 `knowledge`: responsibility, repositories, routers, P0→P2. |
| `BACKEND_FOLDER_STRUCTURE.md` | `domain/ports/external.py` (`KnowledgeSource`), `infrastructure/external/knowledge.py`, `application/knowledge.py`, `api/v1/knowledge.py`. |
| `DEPENDENCY_RULES.md` | DR-6 (knowledge adapters → knowledge interfaces), F-10 (no cross-feature internal access). |
| `DECISION_ENGINE_ARCHITECTURE.md` | Candidate Generation consumes knowledge (stage 2); knowledge is the source of all candidates + vocabulary. |
| `AI_INTEGRATION_ARCHITECTURE.md` | Knowledge is data; AI is inference — never merged (DR-6 note in the AI doc). |
| `TRANSACTION_BOUNDARIES.md` | TRX-8 (knowledge never deleted); catalog content updates are single-row writes (§4). |

---

## 3. Knowledge concepts

### 3.1 Knowledge source

- **Definition:** the canonical, single place Fansivibe knowledge comes from
  (K9.1). Exposed as the `KnowledgeSource` **port** in
  `domain/ports/external.py`; implemented by the knowledge adapter
  (`infrastructure/external/knowledge.py`), which serves **both** static
  rules and DB-backed content.
- **Who consumes it:** the Decision Engine (candidate generation, scoring
  vocabulary validation), `discover` (feed), `knowledge` API
  (`GET /knowledge/*`), and `wardrobe` (item reference validation).
- **What it guarantees:** a single vocabulary across features — no feature
  list, no per-feature constants (BA-11).

### 3.2 Knowledge repository

- **Definition:** the persistence layer for **database-backed** knowledge —
  the `looks` + vocabulary tables. Implements the domain repository ports
  (`LookRepository`, `CategoryRepository`, `ColorRepository`,
  `OccasionRepository`, `ItemRepository`).
- **Storage separation (KN-0):** knowledge tables are **system-owned rows**,
  never user-scoped. There is no `user_id` on any knowledge table; user data
  (wardrobe, saved looks, signals) lives in separate tables. This is the
  hard separation — enforced by schema (PR-5) and by the append-only/
  read grants on knowledge tables.

### 3.3 Knowledge validation

- **Definition:** every knowledge write is validated before acceptance: type
  correctness, code stability (PR-3: codes are stable, content changes
  versioned, never destructive), references exist (FK to vocabularies),
  enum membership (occasion/category/color within controlled vocab), and
  content policy (no subjective judgment / no appearance shaming — SAFETY).
- **Where it runs:** in the knowledge application/domain service on seed and
  admin updates (P2); every read is validated too (a retrieved look whose
  category was deprecated is filtered, not served).

### 3.4 Knowledge version

- **Definition:** knowledge has a **content version** (`knowledge_version`)
  distinct from schema version and engine version:
  - **Schema version** — which DB migration (M3).
  - **Content version** — the curated content revision (bumped on any seed /
    admin update; recorded per look row and served in API headers /
    metadata).
  - **Engine version** — rules code version (used for provenance alongside
    `model_version` in analysis, TRX-5).
- **Why:** recommendations and analyses that cite knowledge must be
  reproducible (a saved look snapshot is frozen at save time; later content
  edits never rewrite history).

### 3.5 Knowledge lookup

- **Definition:** the direct, keyed access path — "give me the look with this
  id", "give me the category codes", "what occasion is this". Exact-match,
  index-friendly, used for reference and validation (e.g. wardrobe validates
  category/color against lookup results).

### 3.6 Knowledge retrieval

- **Definition:** the **filtered/derived** access path — "give me looks for
  occasion X with colors in Y, ordered by…". Used by the Decision Engine's
  Candidate Generation and by Discover. Retrieval may apply scoring seeds but
  never user-specific scores (personalization is the engine's job, applied
  after retrieval).

### 3.7 Relationship with the Decision Engine

- The Decision Engine **never owns knowledge**; it receives it via the
  `KnowledgeSource` port.
- Pipeline mapping: **Candidate Generation** (stage 2) calls `retrieve()` for
  candidates; **Filtering** (stage 3) uses vocabulary for hard constraints;
  **Scoring/Explanation** (stages 4/6) read style/color/outfit rules for
  weights and reasons.
- **Direction (DR-6):** engine → port → adapter; knowledge never reaches the
  engine's outputs as a side channel, and the engine never writes knowledge.

---

## 4. Knowledge types and their storage decision

For each knowledge type: what it is, current state, and the storage
decision (static / versioned / DB-backed / file-backed / cached). The
decision follows one rule:

**KN-1 (storage by lifecycle):** knowledge that **changes rarely and is
tied to product semantics** (codes, rules, guidance) is **static/file-backed
+ cached**; knowledge that is **curated content with many rows** (looks,
items) is **DB-backed + versioned**; everything is **served through one
versioned interface** so the choice is swappable.

| Knowledge type | What it is (from catalog.py) | Storage decision | Notes |
| --- | --- | --- | --- |
| **Style rules** | outfit principles, "refined office", "effortless casual", tips | **static, versioned** (file-backed content + content version) | Rules are few and curated; versioned so explanations cite the rule revision. |
| **Color rules** | color vocab, palette guidance, color-combination hints | **static, versioned** (file-backed + validated against `colors` table) | Codes are stable (PR-3); guidance text versioned. |
| **Face-shape guidance** | "suits oval faces", per-face-shape cues | **static, versioned** (file-backed) | Guidance text; referenced by hair/grooming scoring. |
| **Hairstyle knowledge** | TEXTURED_QUIFF, CLASSIC_POMPADOUR (attributes, upkeep, scores) | **DB-backed + versioned** (rows in `looks` with hair type) | Curated content with many rows; each row carries content_version. |
| **Grooming knowledge** | STRUCTURED_GOATEE, CLASSIC_STUBBLE (attributes, upkeep) | **DB-backed + versioned** (rows in `looks` with grooming type) | Same as hairstyle. |
| **Clothing knowledge** | WARDROBE mirror (items), categories, textures, materials | **DB-backed + versioned** (`items`, `categories`, `colors`) | Item catalog serves wardrobe reference + validation. |
| **Outfit principles** | OCCASION_TO_LOOK mapping, occasion→look rules | **static, versioned** (file-backed rule table) | The occasion→look map is a rule set, not content rows. |
| **Navigation map** | NAVIGATION_MAP (assistant actions → routes) | **static** (not versioned) | UI contract constant, not knowledge the engine scores on. |

### 4.1 The five storage modes (KN-1 detail)

| Mode | Used for | Example | Why |
| --- | --- | --- | --- |
| **Static** | rules, vocab codes, nav map | `OCCASIONS`, `NAVIGATION_MAP`, style rules | Semantic constants; change only with product decisions, deployed with code. |
| **Versioned** | everything served that is cited by saved output | style rules, looks, items | Saved snapshots stay reproducible (frozen at save time, TRX-3/TRX-4). |
| **Database-backed** | curated content with many rows | `looks`, `items`, `categories`, `colors`, `occasions`, `size_categories` | STEP 4 schema already defines them; queryable, FK-validated, system-owned. |
| **File-backed** | static + versioned rules/guidance (seed source) | style/color/face-shape guidance; seed data for DB | Content authored by the team, versioned in the repo; seeded into DB where rows are needed. |
| **Cached** | hot read paths, stable content | `retrieve()` results, vocab lookups | Content changes rarely; cache invalidates on content_version bump. |

### 4.2 What is DB-backed today vs. later

| Table (STEP 4) | Status |
| --- | --- |
| `categories`, `colors`, `occasions`, `size_categories`, `items` | P0 subset of knowledge (M5 P0: vocabulary for wardrobe + assistant validation). |
| `looks` (catalog) | P0 seed (the current 2+ looks) → P2 full curation/feed. |

**Migration note (M1-safe):** today `catalog.py` is the single source
(K9.1 holds). It becomes the **seed file** for the knowledge adapter — the
file-backed content is preserved and served through the `KnowledgeSource`
port; DB tables are populated by the M3 migration for the P0 vocabulary
subset. No content is lost or rewritten.

---

## 5. Versioning and persistence rules

### 5.1 Version model

| Version | What it versions | Bumped when | Used for |
| --- | --- | --- | --- |
| `schema_version` | DB migrations (M3) | migration added | schema changes |
| `knowledge_version` | curated content | any seed/admin content update | cache invalidation, API header, provenance of cited knowledge |
| `engine_version` | rules code | rules code changes | provenance alongside `model_version` in analysis (TRX-5) |

### 5.2 Persistence rules

- **KN-2 (system-owned):** knowledge rows are owned by the system, not a
  user. There is **no `user_id`** on any knowledge table; user data is
  always in separate tables. This is the definitive separation.
- **KN-3 (stable codes, deprecate-not-delete, PR-3):** codes (category,
  color, occasion) never change meaning and are never deleted; deprecated
  entries are marked and filtered from retrieval, never removed — so old
  saved looks and analyses that reference them remain valid.
- **KN-4 (immutable-to-history):** once a look/snapshot is saved or an
  analysis cites knowledge, the cited content version is frozen; later
  knowledge edits never mutate that history (TRX-3/TRX-4, consistent with
  history rules).
- **KN-5 (read-grants):** knowledge tables are **read-mostly**: the API can
  only read them; writes happen via the knowledge application service
  (seed/admin, P2) under the DB role grants (append-only policy per
  `DATABASE_DESIGN_RULES.md`).
- **KN-6 (no user writes):** no user use case ever writes to a knowledge
  table (wardrobe writes `wardrobe_items`, not `items`; saved looks write
  `saved_looks`, not `looks`). Enforced by schema grants and by the
  repository layering (DR-4/DR-6).

### 5.3 Caching rules

- **KN-7 (cache on content version):** retrieval/lookup results are cached
  keyed by `knowledge_version`; a content bump invalidates the cache. No
  cache ever holds user data (cache is knowledge-only).
- **KN-8 (cache is optional):** caching is an optimization; the system
  behaves identically with cache disabled (cold reads are correct, just
  slower). No stale-write path — caches are read-through, never written back.

---

## 6. Separation from user-generated data (the hard guarantee)

| Aspect | Knowledge | User-generated data |
| --- | --- | --- |
| Tables | `looks`, `categories`, `colors`, `occasions`, `size_categories`, `items` | `users`, `user_state`, `wardrobe_items`, `saved_looks`, `learning_signals`, `user_events`, `analysis_runs`, `subscriptions`, `style_score_records`, `activity_days` |
| Owner | system | user (user_id-scoped) |
| Lifecycle | seeded, versioned, deprecate-not-delete | created/updated/deleted per user action |
| Erasure (TRX-8) | **never deleted** | cascaded delete with the user |
| Writes via | knowledge service (seed/admin, P2) | user use cases (UC-*) |
| Read grants | read-only to API, write via service role | scoped by user_id (BA-8) |
| Cache | knowledge-only (KN-7) | none (user data never cached) |
| Privacy class | public/system data | PII-sensitive (appearance, images, signals) |

**KN-9 (boundary rule):** no knowledge operation reads user data, and no user
operation writes knowledge. Cross-*references* (e.g. a saved look's `look_id`
→ knowledge `looks`, SET NULL on delete, BC-36/37) are provenance links, not
ownership — knowledge is never user-owned and user rows are never
knowledge-owned.

---

## 7. Knowledge flow (end to end)

```
assistant / discover / wardrobe / analysis
        │  call KnowledgeSource port (DR-6)
        ▼
KnowledgeService (application/knowledge.py)
        │  validate request + version
        ├─────────────► lookup()       ── exact keyed reads (validation, refs)
        ├─────────────► retrieve()     ── filtered/derived reads (engine candidates)
        │
        ▼
knowledge adapter (infrastructure/external/knowledge.py)
   ┌────┴────────────┬──────────────────┐
 static rules      DB repositories    cache
 (file-backed,      (looks, items,     (keyed by
  versioned)         vocabularies)      knowledge_version)
   └────────────┬──────────────────────┘
                ▼
      Decision Engine (stages 2/3/4/6)  — consumes via port only
```

- **lookup vs retrieve (KN-10):** `lookup()` is exact and cheap (used for
  validation and reference); `retrieve()` is filtered/derived (used for
  generation/feeds). The Decision Engine uses `retrieve()` for candidates and
  `lookup()` for vocabulary validation; neither path is user-scoped.

---

## 8. Report, assumptions, constraints

**What changed (this step):** added `KNOWLEDGE_ARCHITECTURE.md` — the
Knowledge system design (concepts, storage decisions, versioning,
separation guarantees, flows). No implementation.

**Skills used:** repository analysis (current `catalog.py`; domain model E5 +
vocabularies; STEP 4 schema; STEP 5 module map M5, folder structure,
dependency rules, decision engine, AI integration) — architecture
documentation only.

**Files changed:** `docs/backend/KNOWLEDGE_ARCHITECTURE.md` (new).

**Validation run:**
- Every concept (source/repository/validation/version/lookup/retrieval/
  decision-engine relationship) maps to accepted docs: K9.1/BA-11 (single
  source), DR-6 (port), M5 (module), STEP 4 tables, TRX-8 (never deleted).
- Every knowledge type in the task maps to real content in `catalog.py`
  (style rules, color vocab, face-shape guidance, hairstyle/grooming/clothing
  knowledge, outfit principles, occasion→look map) and got an explicit
  storage decision (§4).
- The knowledge↔user-data separation (§6) is grounded in schema ownership
  (PR-5), erasure (TRX-8), and read-grants — not asserted.
- `git status --short`: only this new doc + `CURRENT_STATE.md` update; no
  code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- The seed file shape (what becomes file-backed vs. seeded to DB) is a
  content decision for the M3 migration, not this design.
- Caching strategy details (TTL, invalidation mechanism) are implementation
  concerns for M4/P2, guided by KN-7/KN-8.
- No `DECISIONS.md` entry needed: no accepted architectural decision made
  (documentation only); open items remain in `BACKEND_ARCHITECTURE_RULES.md`
  §8/§10 (K9.1 knowledge shape, seeding source).

**Assumptions recorded:**
- "Knowledge" = system-owned curated content (E5 + vocabularies), per the
  domain model; the assistant's `catalog.py` is its current single-file seed.
- Storage choice is by lifecycle (KN-1): static/versioned for rules,
  DB-backed/versioned for content rows, cached for hot reads.
- The reference project's knowledge implementation was intentionally **not**
  consulted for content or structure (BMM-0); the design is derived only
  from Fansivibe's real data and schema.

**Constraints honored:** BAR-0 (knowledge is the domain model's system-owned
data; assistant DTOs frozen), BA-3/BA-11/DR-6 (pure domain port, single
source, adapters behind interfaces), PR-3/PR-5/PR-7 (stable codes, ownership,
current-vs-history), TRX-8 (knowledge never deleted), KN-9 (no cross-boundary
writes), the UI Change Safety Rule (no UI touched), and the Scope rule (this
document only).
