# Fansivibe — Backend Architecture Rules

> **STEP 5 — BACKEND ARCHITECTURE.** Defines the **production FastAPI
> architecture** that will expose the Fansivibe domain from STEP 3
> (`FANSIVIBE_DOMAIN_MODEL_V1.md`) over the STEP 4 PostgreSQL schema
> (`DATABASE_DESIGN_RULES.md`, `TABLE_DEFINITIONS.md`).
>
> **Status: architecture design only. Nothing is implemented.** The current
> backend prototype is not rewritten, no endpoints are deleted, the assistant
> API is not broken, no Flutter/routing/UI is modified, no database migrations
> are created, no production PostgreSQL is connected, no dependencies are added,
> no services are implemented, no microservices are introduced, nothing is
> over-engineered.
>
> **Source of truth:** the real Fansivibe repository
> (`newproject/flutter_application_1` + `backend/`). The separate reference
> project is reference material only and is **not** merged into this design.

---

## 1. Purpose and scope

This step produces the **rules** for the production backend: the architectural
principles, the module boundaries (API / Application / Domain /
Infrastructure), the dependency direction, the target conceptual request flow,
the explicit external-system interfaces, the current backend's limitations, and
the migration strategy from the current prototype to the production
architecture.

It answers:

1. **How is the backend structured?** — a **modular monolith** with four clear
   layers and a single dependency direction.
2. **How does a request flow?** — HTTP Request → Router → Application Service /
   Use Case → Domain Logic / Decision Engine → Repository → PostgreSQL, with all
   external systems reached through explicit interfaces.
3. **How do we get there from today?** — an incremental, non-breaking migration
   from the current single-purpose assistant prototype.

It does **not** answer how to write the endpoints, repositories, or SQL — those
belong to later steps, which must implement these rules.

**Binding derivation rule (BAR-0):** the backend represents the **domain model,
not the Flutter UI** (`DATABASE_DESIGN_RULES.md` DBR-0). API shapes are derived
from `FANSIVIBE_DOMAIN_MODEL_V1.md` and the STEP 4 schema — never by mirroring
a widget tree or a Dart model wholesale. The one deliberate exception is the
**assistant DTO contract**, which is KEEP as the mirrored wire contract
(`ARCHITECTURE_GAP_REPORT.md` A3.1; `schemas.py` ↔
`features/assistant/data/models.dart`).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | The canonical contract — entities (E1–E10 + conditionals), value objects, relationships, ownership, lifecycle. |
| `DATABASE_DESIGN_RULES.md` | PR-1…PR-12 the schema was built against; table catalog, JSONB/media policy, history-vs-state enforcement. |
| `TABLE_DEFINITIONS.md` | The 23 logical tables the repositories will read/write. |
| `TRANSACTION_BOUNDARIES.md` | TRX-1…TRX-8 — which operations are true DB transactions, which are single-row writes. |
| `SECURITY_PRIVACY_DESIGN.md` | The user ownership boundary (PR-10): user_id from session, never client-trusted. |
| `ACTION_API_INVENTORY.md` | The 32 future user actions → endpoint requirements (Part 1 master matrix). |
| `MVP_SCOPE.md` | P0/P1/P2/P3 phasing of the vertical slice and supporting features. |
| `ARCHITECTURE_GAP_REPORT.md` | REQUIRED_BEFORE_BACKEND findings (A3.2/A3.3, R4.2, K9.1, AU11.x, AZ12.3, E13.x). |
| `DECISIONS.md` | DEC-003 FastAPI direction; DEC-004 PostgreSQL direction. |
| Current `backend/` source | `main.py`, `app/ai/{engine,intent,tools,llm_backend}.py`, `app/data/catalog.py`, `app/models/schemas.py`, `tests/`, `requirements.txt` — the prototype being migrated. |

Spot facts re-verified from source this step (they anchor the design):

- **Current backend = assistant prototype only.** `app/main.py` exposes exactly
  `GET /health` and `POST /v1/assistant/chat`. No DB, no auth, no user store,
  no repository layer, no service boundaries (`ARCHITECTURE_GAP_REPORT.md` B5.1,
  B5.2).
- **The rules engine is real and works.** `engine.py` orchestrates
  `intent.py` (deterministic classifier, 10 intents) → `tools.py` (typed
  suggestion cards grounded in user context) → dialogue policy → optional
  Ollama text enrichment (`llm_backend.py`). 19 passing pytest cases.
- **Knowledge today is static code.** `catalog.py` hardcodes the wardrobe,
  occasion→look map (5 occasions), and navigation map — a static mirror of the
  Flutter mocks (K9.1/K9.2 duplication).
- **AI provider boundary already exists in spirit** (`llm_backend.py`) but is
  inline and optional; the structured contract never changes when the LLM is
  down.
- **No typed error contract** — the client treats any failure as "unreachable →
  offline" (`ARCHITECTURE_GAP_REPORT.md` A3.3/E13.1).
- **PostgreSQL is the intended database (DEC-004); no database exists yet.**

---

## 3. Architectural principles

Every backend module and change must satisfy these rules. They are numbered
(BA-1…BA-15) so later steps can reference them.

### BA-1 — Modular monolith

The backend is a **single deployable FastAPI application** containing clearly
separated internal modules. No microservices, no separate services, no
message broker, no per-feature deployments. Service **boundaries are
code/module boundaries**, not network boundaries. This matches the single
`backend/app` today and defers any split until it is proven necessary
(PR-12; `MVP_SCOPE.md` P3).

### BA-2 — Four layers, one dependency direction

The backend has exactly four layers, in strict order:

```
API  →  Application  →  Domain
                             ↑
                      Infrastructure
```

- **API** (routers, request/response models, HTTP concerns)
- **Application** (use cases / application services, orchestration)
- **Domain** (domain logic / decision engine / domain models)
- **Infrastructure** (repositories, external adapters, DB access, config)

Dependencies point **inward**: API may depend on Application and Domain;
Application may depend on Domain; Domain depends on nothing; Infrastructure
implements Domain-defined ports. No layer may reach around another.

### BA-3 — Domain is the center and knows nothing about the outside

Domain code is pure Python: domain models, invariants, the decision engine
(assistant intent/rules/tools), and the interfaces (ports) it needs. It does
**not** import FastAPI, SQLAlchemy, httpx, or any provider SDK, and it never
does I/O. This is what keeps business logic testable without a server or
database — as `test_engine.py`/`test_intent.py` already prove.

### BA-4 — Screens are not business logic; UI never talks to a provider

Mirror of `docs/ARCHITECTURE.md` AI rule on the backend: Flutter → FastAPI →
orchestrator → provider. The backend owns all provider access. Domain logic
and decision rules live in the **Domain** layer, never in a router.

### BA-5 — Every boundary crosses with typed structured data

All inter-layer communication uses typed Pydantic models / dataclasses. The
wire contract is typed (as today), application-layer commands/queries are
typed, repository I/O uses typed rows/aggregates, and AI responses are typed
structured schemas — never free-form text as a data source (A3.2; AI must not
control structure).

### BA-6 — External systems are reached only through explicit interfaces

AI models, object storage, weather, and knowledge are **external systems**
reached through interfaces defined in the Domain (or Application) layer and
implemented in Infrastructure. Domain code depends on the interface, not on
the concrete provider. Nothing else may call them (see §7).

### BA-7 — AI output is never a source of truth

The STEP 3 binding invariant. The backend may compute/generate AI output
(recommendations, insights, analysis), but it persists only durable inputs +
user-saved snapshots + reproducible run history (`DATABASE_DESIGN_RULES.md`
PR-6). Derived values recompute; only their immutable snapshots persist
(PR-2, PR-7).

### BA-8 — User ownership and privacy by construction

Every user-owned write is scoped by a `user_id` that comes from the
**authenticated session**, never from the client body/query
(`SECURITY_PRIVACY_DESIGN.md` §2; PR-10; AZ12.3). Appearance/image data is
never logged and follows the retention policy.

### BA-9 — History is append-only; current state is mutable

Repositories and application services honor the never-overwrite invariant
(`HISTORY_AND_VERSIONING.md`; `TRANSACTION_BOUNDARIES.md`). Append-only
history tables (`learning_signals`, `style_score_records`, `activity_days`,
`analysis_runs`, …) are only ever INSERTed; the API role has no UPDATE/DELETE
grant (`DATABASE_DESIGN_RULES.md` §10). Application services must not attempt
to mutate them.
### BA-10 — Repositories are the only data access path

No router or application service touches PostgreSQL directly. All persistence
goes through repository interfaces (ports) implemented in Infrastructure.
This preserves the KEEP'ed repository pattern from the Flutter side
(`ARCHITECTURE_GAP_REPORT.md` R4.1/R4.2) and gives tests a seam.

### BA-11 — Backend is the single knowledge source

Vocabularies and catalogs (categories, colors, occasions, event types, looks,
styles, signal types, run types, plans) have **one canonical source served by
the backend** (K9.1). Whether they are versioned DB tables or versioned config
is the K9.1 open decision (§10); either way the backend owns them and the app
fetches/caches. No hardcoded backend-controlled categories inside application
code (BA-4).

### BA-12 — No premature complexity

Same discipline as PR-12. Only what the product needs is built: no speculative
endpoints, no service-bus, no async workers, no caching framework, no RLS
machinery until a real need lands. A new pattern must earn its place.

### BA-13 — Incremental, non-breaking migration

The current backend is a working prototype with a **live contract**
(`POST /v1/assistant/chat`). Migration is additive and layered; the assistant
API keeps working at every step (see §9). No rewrite, no big-bang.

### BA-14 — Transactions are explicit and minimal

Only the TRX-1…TRX-8 operations are true DB transactions
(`TRANSACTION_BOUNDARIES.md`). Single-row writes are plain inserts/updates
(MVCC-atomic). Blobs and external calls never join a transaction
(upload-before-insert, cleanup-after-commit). Application services own
transaction boundaries; repositories do not open transactions across uses.

### BA-15 — Media stays out of PostgreSQL

Binaries live in object storage behind a `MediaRef` (PR-8). The backend's
Infrastructure layer owns any object-storage adapter; no BYTEA/base64 in the
API. Media persistence remains gated on MS10.3 (media privacy policy).

---

## 4. Module boundaries

### 4.1 API layer

**Responsible for:** HTTP entry points. FastAPI routers grouped by
resource/feature (mirroring `ACTION_API_INVENTORY.md` Part 1 clusters): auth,
users, wardrobe, events, looks, analysis, generation, assistant,
subscriptions, sync. Request validation (typed Pydantic request models), the
auth dependency (resolves session → user_id), response serialization (typed
response models), and HTTP status/error mapping.

**Forbidden from:** business logic, decision rules, persistence, provider
calls. A router only parses input, calls exactly one application use case, and
maps the result to an HTTP response.

**Target shape (design only, not created):**

```
app/api/
├── deps.py            # auth dependency → current user_id
├── errors.py          # typed error → HTTP response mapping (A3.3/E13.1)
└── v1/
    ├── router.py      # mounts the v1 routers
    ├── auth.py
    ├── users.py
    ├── wardrobe.py
    ├── events.py
    ├── looks.py
    ├── analysis.py
    ├── generation.py
    ├── assistant.py
    ├── subscriptions.py
    └── sync.py
```

### 4.2 Application layer

**Responsible for:** use cases / application services. Each use case
orchestrates one user action from `ACTION_API_INVENTORY.md`: validate against
domain rules, load domain state via repository ports, run the decision engine,
apply the transaction boundary (BA-14), persist through repositories, and
return a typed result. Owns the `user_id` scoping for every call (BA-8).

**Forbidden from:** HTTP concerns, raw provider SDK calls, and
SQL/persistence. Application code depends on Domain (models + ports) and on
nothing else concrete.

**Target shape (design only, not created):**

```
app/application/
├── auth.py
├── users.py           # profile/preferences + P7.1 sync use case
├── wardrobe.py
├── events.py
├── looks.py           # saved looks, today's look
├── analysis.py
├── generation.py      # outfit builder, event-seeded generation
├── assistant.py       # orchestration around the decision engine
├── subscriptions.py
└── feedback.py        # feature-gated (P1)
```

### 4.3 Domain layer

**Responsible for:** the Fansivibe domain, expressed as pure Python.

- **Domain models** — the entities/value objects of
  `FANSIVIBE_DOMAIN_MODEL_V1.md` (User, WardrobeItem, SavedLook, Look,
  LearningSignal, AnalysisRun, UserEvent, StyleScoreRecord, ActivityDay,
  Subscription + value objects). These are the canonical shapes; DTOs are
  boundary projections, never the source of truth (BAR-0).
- **Decision engine** — the assistant's rules (today's `engine.py`,
  `intent.py`, `tools.py`): intent classification, occasion detection, tool
  invocation, dialogue policy, and the deterministic recommendation rules.
  The engine is a Domain service: it receives typed input and returns typed
  output with **no I/O** (BA-3).
- **Ports (interfaces)** — repository interfaces (per BA-10) and external
  system interfaces (per BA-6). Domain defines them; Infrastructure implements
  them.

**Forbidden from:** FastAPI, SQLAlchemy, httpx, provider SDKs, file/network
I/O, and any import of API/Infrastructure code.

**Target shape (design only, not created):**

```
app/domain/
├── models.py          # canonical domain entities + value objects (BAR-0)
├── engine.py          # decision engine: intent, tools, dialogue (moved from app/ai)
├── intent.py
├── tools.py
└── ports/
    ├── repositories.py    # repository interfaces (BA-10)
    └── external.py        # AI / object-storage / weather / knowledge interfaces (BA-6)
```

The existing `app/ai/*` and `app/models/schemas.py` are the **seeds** of this
layer: `engine/intent/tools` become the Domain decision engine; `schemas.py`
splits into API DTOs (kept) + Domain models (derived from the STEP 3 model).
The existing `catalog.py` knowledge moves behind a knowledge port (BA-11).

### 4.4 Infrastructure layer

**Responsible for:** the concrete outside world.

- **Repositories** — implementations of the Domain repository ports against
  PostgreSQL (respecting TABLE_DEFINITIONS.md, append-only grants BA-9,
  transaction boundaries BA-14, and user scoping BA-8).
- **External adapters** — AI provider(s), object storage, weather, and
  knowledge/config source, each implementing a Domain/Application interface
  (BA-6).
- **DB session/config** — connection/session management, settings loading,
  migration tooling.

**Forbidden from:** business/decision logic, and from being imported by any
upper layer.

**Target shape (design only, not created):**

```
app/infrastructure/
├── config.py
├── db.py              # session/engine management
├── repositories/      # implementations of domain ports
│   ├── users.py
│   ├── wardrobe.py
│   ├── saved_looks.py
│   ├── learning_signals.py
│   └── ...
└── external/
    ├── ai.py          # LLM/AI provider adapter (llm_backend today)
    ├── object_storage.py   # MS10.3-gated, not built yet
    ├── weather.py          # not built yet
    └── knowledge.py        # catalog/vocabulary source (K9.1)
```

---

## 5. Dependency direction (binding)

```
          ┌──────────────┐
          │     API      │  routers, DTOs, HTTP, auth dep
          └──────┬───────┘
                 │ depends on
          ┌──────▼───────┐
          │ Application  │  use cases, orchestration, transaction boundaries
          └──────┬───────┘
                 │ depends on
          ┌──────▼───────┐       ┌──────────────────┐
          │    Domain    │◄──────┤ Infrastructure   │ implements ports
          │ models+engine│       │ repositories,    │
          │ +ports       │       │ adapters, DB, cfg │
          └──────────────┘       └──────────────────┘
```

Rules:

1. **API → Application → Domain.** Upper layers import lower layers only.
2. **Domain imports nothing** from API/Application/Infrastructure and no
   framework/provider. (BA-3)
3. **Infrastructure imports Domain** to implement its ports; it never imports
   API or Application.
4. **Application imports Domain** (models, ports) and Infrastructure **only**
   through composition at the composition root (e.g. FastAPI dependency
   injection in `app/main.py` or a DI container) — not via imports deep in
   use-case code.
5. **No cycles.** Any module that breaks these arrows is a design violation.
6. **Feature isolation** (`docs/ARCHITECTURE.md`): one feature's use case must
   not reach into another feature's internal data. Cross-feature needs go
   through the shared Domain model and its ports.

---

## 6. Preferred conceptual flow

The canonical request path, for every endpoint, is:

```
HTTP Request
  → Router                (API: validate, auth dep → user_id, typed request)
  → Application Service   (Application: one use case, transaction boundary)
  → Domain Logic /        (Domain: decision engine, invariants, rules)
    Decision Engine
  → Repository            (Infrastructure: port implementation → SQL)
  → PostgreSQL
```

Variants:

- **Read flows** stop after the repository read; the use case shapes a typed
  response (the decision engine may still run for derived values such as score
  or today's look).
- **Write flows** follow the flow fully and honor `TRANSACTION_BOUNDARIES.md`
  (BA-14): repository writes inside the use case, external effects
  after-commit.
- **External systems** (AI, object storage, weather, knowledge) are reached
  from the **Domain/Application via their interfaces**; the concrete adapter
  in Infrastructure is what actually touches the outside world. Example for
  the assistant today:

```
POST /v1/assistant/chat
  → assistant router (typed request, auth dep)
  → assistant use case (loads user context via repository ports)
  → decision engine (intent → tools → dialogue policy)   [Domain]
  → optional LLM enrichment via AI provider interface    [Domain→port→Infra]
  → typed AssistantReply DTO                              [API response]
```

### 6.1 The assistant stays a live contract throughout

`POST /v1/assistant/chat` and its mirrored DTOs (`schemas.py` ↔
`features/assistant/data/models.dart`) are the **one live wire contract**
(A3.1). Migration must keep this endpoint, its request/response shape, and its
rules behavior intact at every step (BA-13). The engine that produces it is
moved *intact* into the Domain decision engine; only its inputs change (from
the client-sent `UserContext` snapshot today to repository-loaded domain state
once auth/DB land), and the wire DTOs are preserved.

### 6.2 The user-model sync path (P0, P7.1)

`POST /users/me/sync` (ACTION_API #32) is the blob→rows migration transport:
an application use case that validates the client blob, splits it into
relational rows + `user_state` JSONB per `DATABASE_DESIGN_RULES.md` §7, and is
idempotent/resumable (PR-11). It exercises the full flow (repository writes +
transaction boundary) and is the P0 proof that the layering works end to end.

---

## 7. External systems through explicit interfaces

All external systems are reached **only** through interfaces (BA-6). They are
defined here so later steps implement them against the real adapters.

| External system | Interface (port) | What it must provide | Adapter (Infrastructure) | Status today |
| --- | --- | --- | --- | --- |
| **AI models** (LLM/Ollama today; analysis/generation later) | `TextEnrichmentProvider` (enrich text, keep structure); future `AnalysisProvider`, `GenerationProvider` | typed enrichment/analysis/generation output; graceful degradation when unavailable | `llm_backend.py` becomes the adapter; provider details (env, host, model) live here | exists as inline `llm_backend.py`; move behind port |
| **Object storage** (media bytes) | `ObjectStorage` (put/get/delete keyed by user-scoped `MediaRef`) | user-scoped keys, async cleanup, no bytes in PostgreSQL | `object_storage.py` | **not built** — gated on MS10.3 |
| **Weather** | `WeatherProvider` (fetch → typed snapshot, cache) | external data never owned by us | `weather.py` | **not built** — literal `'68°F • Partly Cloudy'` today |
| **Knowledge** (vocabularies/catalogs) | `KnowledgeSource` (list/get vocabulary + look catalog) | single canonical source (K9.1), stable `code` ids, versioned | `knowledge.py` reading DB tables or versioned config | today = static `catalog.py`; move behind port |

Rules:

1. Domain code depends on the **interface**, never the adapter or provider
   SDK (BA-3, BA-6).
2. Each external failure degrades gracefully and is **typed** — a
   provider-down must never corrupt a structured reply or a DB row.
3. External calls never join a DB transaction (BA-14): media
   upload-before-insert, cleanup-after-commit; AI enrichment after the rules
   result is structured (as today).
4. Privacy: never send appearance/image payloads to an external system without
   the media-privacy policy (MS10.3) decision; conversation context stays
   transient by default (retention undecided).

---

## 8. Current backend limitations

Verified against the real `backend/` source this step:

| # | Limitation | Evidence | What the production architecture fixes |
| --- | --- | --- | --- |
| L1 | **Assistant prototype only** — exactly two endpoints (`GET /health`, `POST /v1/assistant/chat`); no wardrobe/events/looks/analysis/sync endpoints | `app/main.py` | API layer + use cases per `ACTION_API_INVENTORY.md` |
| L2 | **No database** — no persistence, no repositories; the service is stateless and knowledge is hardcoded | `requirements.txt` (no DB driver); `catalog.py` | PostgreSQL repositories (BA-10), DEC-004 |
| L3 | **No auth / no user store** — user context is client-sent; no `user_id` scoping | `schemas.py` `UserContext`; no auth anywhere (AU11.1) | auth dependency → session `user_id` (BA-8, AZ12.3) |
| L4 | **Layering absent** — `app/ai` mixes engine+intent+tools+llm; `schemas.py` mixes wire DTOs; `catalog.py` is a static knowledge mirror | `app/ai/*`, `app/models/schemas.py`, `app/data/catalog.py` | four layers (BA-2), Domain decision engine (BA-3) |
| L5 | **No typed error contract** — the client treats every failure as "unreachable → offline", hiding real errors | `ARCHITECTURE_GAP_REPORT.md` A3.3/E13.1 | `api/errors.py` typed error model (A3.3) |
| L6 | **Knowledge duplication** — `catalog.py` mirrors Flutter mocks (wardrobe ×3, looks ×4, occasions ×4); violates "no hardcoded backend-controlled categories" | K9.1/K9.2; `catalog.py` vs Flutter mock data | backend = single knowledge source behind a port (BA-11) |
| L7 | **AI provider inline & implicit** — Ollama via `llm_backend.py` with env reads; works, but not behind a contract | `llm_backend.py` | `AIProvider` port + adapter (BA-6) |
| L8 | **No history/state discipline** — nothing persists, so append-only vs mutable is moot; must be enforced once DB lands | `TRANSACTION_BOUNDARIES.md`; `DATABASE_DESIGN_RULES.md` §10 | repositories enforce BA-9 |
| L9 | **No config management** — env vars read inline in `llm_backend.py`; no settings object | `llm_backend.py:19-20` | `infrastructure/config.py` |
| L10 | **No media, weather, or external integrations** | `STORAGE_INVENTORY.md` | ports exist (BA-6); adapters built only when their gates land (MS10.3, weather feature) |
| L11 | **Engine duplicated on-device** — `OfflineAssistant` mirrors `engine.py`; must not fork further | B5.3 | keep one canonical engine spec; the Domain engine is the backend reference |
| L12 | **Tests cover only the engine** — `tests/test_engine.py`, `test_intent.py`; no API/contract/DB tests | `backend/tests/` | add contract and repository tests with each layer |

---

## 9. Migration strategy: from prototype to production architecture

Guiding principle (BA-13): **additive, layered, non-breaking.** The assistant
endpoint and its behavior never regress. PostgreSQL, auth, and the four layers
are introduced incrementally so the backend remains runnable and green after
every step.

### Step M1 — Establish the layers without changing behavior (structure-first)

Reorganize `app/` into `api/`, `application/`, `domain/`, `infrastructure/`
and move existing code into place **without changing any wire contract or
behavior**:

- `app/ai/{engine,intent,tools}.py` → `app/domain/` as the decision engine
  (pure; delete nothing, keep the logic).
- `app/ai/llm_backend.py` → `app/infrastructure/external/ai.py` behind an
  `AIProvider` port.
- `app/data/catalog.py` → knowledge source behind a `KnowledgeSource` port.
- `app/models/schemas.py` → API DTOs (kept as the assistant wire contract).
- `app/main.py` → mounts the assistant router, keeps `/health` + the exact
  `/v1/assistant/chat` contract.
- **Validation:** the existing 19 pytest cases must still pass unchanged.

### Step M2 — Add the typed error contract (non-breaking)

Define the shared error model (A3.3/E13.1): status + stable machine-readable
code + optional detail, mapped to the error conditions in
`ACTION_API_INVENTORY.md` Part 3 (401/404/409/413/422/429/503…). Apply it to
the assistant endpoint first; every new endpoint uses it from birth. The
Flutter client can then stop collapsing everything into "offline".

### Step M3 — Introduce PostgreSQL infrastructure (no production connection)

Add the DB driver/session layer and repository ports; write the STEP 4 schema
as versioned, forward-only migrations (PR-11) in the SQL step. Repositories are
created per P0 entity. **Do not connect production PostgreSQL in this step** —
local/test-only connection so the 19 tests plus new repository tests pass.

### Step M4 — P0 vertical slice (`MVP_SCOPE.md` Part 1)

Build the authenticated P0 slice in this order:

1. **Auth** (`AU11.1/AU11.2`) — register/login/social + session token; the
   auth dependency resolves `user_id`; `users` + `user_state` rows (AZ12.3).
2. **User-model sync** — `POST /users/me/sync` (P7.1) splitting the blob into
   rows + JSONB, idempotent/resumable.
3. **Wardrobe CRUD** — `POST/PATCH/PUT/DELETE /wardrobe/items` (+
   `GET /wardrobe`), repository-backed, `user_id`-scoped.
4. **Authenticated assistant** — `POST /v1/assistant/chat` gains auth + typed
   errors; the decision engine now reads repository-loaded domain state
   instead of the client snapshot (wire DTOs unchanged).
5. **Backend knowledge source (K9.1 subset)** — categories/colors/occasions
   served by the backend; the app fetches/caches.

### Step M5 — P1 and P2 features (per `MVP_SCOPE.md` Part 2/3)

Add use cases + routers + repositories per priority: saved looks end-to-end,
events (persist + CRUD + event-seeded generation), profile/today's look,
score/streak history, full knowledge rollout, feedback actions (P1); then
analysis contract, builder generation, insights, settings, subscription (P2).
Each feature lands inside the existing layering — no new architecture.

### Step M6 — P3 / future (only when their gates land)

Recommendation history, real AI analysis, media pipeline (object storage,
MS10.3-first), weather, multi-device, contract versioning (A3.4) — built
against the ports defined in §7, never before their product decisions.

### Non-negotiables

- **Never break `/v1/assistant/chat`** — contract, mirrored DTOs, and rules
  behavior stay (A3.1).
- **No big-bang rewrite** — each step is a green, runnable backend.
- **No new dependency without a real need** — the DB driver/ORM is added in
  M3 only; nothing speculative (BA-12).
- **Privacy & ownership from the first relational write** (BA-8).
- **Migrations are versioned, forward-only, additive-first** (PR-11); the blob
  split is a data migration with a defined backfill path.

---

## 10. Open decisions carried into implementation

These are open at the end of STEP 4 and remain open here. **None blocks these
architecture rules**; each only decides a specific endpoint/table shape:

1. **`User` fields / auth design (AU11.1/AU11.2)** — pins the exact `users`
   columns and the anonymous→sync merge semantics; the architecture already
   derives `user_id` from session (BA-8).
2. **`Today'sLookRecord`** — create the per-user daily snapshot (P1) or keep a
   derived cache? (`TABLE_DEFINITIONS.md` §4)
3. **`RecommendationHistory`** — build the shown/saved trace (P3)?
4. **Conversation retention** — persist conversations (JSONB history, short
   window) or keep transient? Domain default = transient (§7).
5. **Knowledge source shape (K9.1)** — versioned DB tables vs versioned config
   for vocabularies/catalogs; the `KnowledgeSource` port works either way
   (BA-11).
6. **Media privacy policy (MS10.3)** — must be decided before any media
   persistence; gates the object-storage adapter, not the `MediaRef` columns
   or the port (BA-15).
7. **Feedback design** — `feedback_events` and its endpoint are created only
   when the feature lands (P1).

---

## 11. Report — backend architecture principles and assumptions

### Design principles

1. **Modular monolith** — one deployable FastAPI service, code-level
   boundaries, no microservices (BA-1).
2. **Four layers, one dependency direction** — API → Application → Domain,
   Infrastructure implements Domain ports; no cycles (BA-2, §5).
3. **Domain center** — pure Python domain models + decision engine + ports,
   no frameworks/I/O (BA-3).
4. **Typed everything** — typed DTOs, commands, repository I/O, and AI output
   (BA-5).
5. **External systems behind explicit interfaces** — AI, object storage,
   weather, knowledge (§7).
6. **AI output never truth; history append-only** (BA-7, BA-9).
7. **User ownership & privacy by construction** — session-derived `user_id`,
   never client-trusted (BA-8).
8. **Repositories as the only data access path** (BA-10).
9. **Backend = single knowledge source** (BA-11).
10. **Incremental, non-breaking migration** — the assistant contract never
    regresses (BA-13, §9).

### Assumptions

1. **PostgreSQL is the primary relational database (DEC-004)** — the backend
   reads/writes the STEP 4 schema; media moves to object storage; cache and
   external/temporary state stay out of the DB.
2. **The STEP 3 domain model is the contract** — backend shapes derive from it
   (BAR-0); the assistant DTOs are the one deliberate mirror (A3.1).
3. **Identity precedes data** — `users` exists and auth lands before any
   relational write; every user-owned query is scoped (AZ12.3).
4. **The current backend is a prototype to migrate, not replace** — its engine
   and contract are preserved (B5.1 KEEP, BA-13).
5. **P0/P1/P2/P3 sequencing holds** — features land per `MVP_SCOPE.md`; no
   speculative endpoints (BA-12).
6. **Open questions gate only specific endpoints** (§10); the architecture is
   valid under either resolution.
7. **Privacy-sensitive appearance/image data** is never logged, is
   user-scoped, and follows the retention policy of `STORAGE_INVENTORY.md`.

---

## Constraints honored

- No backend rewritten, no endpoints deleted, no Flutter/routing/UI modified,
  no database migrations created, no production PostgreSQL connected, no
  dependencies added, no services implemented, no microservices introduced.
- Every rule and module shape traces to the STEP 3 domain model, STEP 4
  database design, STEP 2 inventories, and the real source; nothing is
  invented beyond them.
- The real Fansivibe repository is the source of truth; the separate reference
  project was **not** merged into this design.





