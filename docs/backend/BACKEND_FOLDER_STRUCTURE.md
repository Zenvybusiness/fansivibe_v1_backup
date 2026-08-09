# Fansivibe — Backend Folder Structure

> **STEP 5 (final part) — BACKEND ARCHITECTURE.** Defines the **production
> FastAPI folder structure** for the REAL Fansivibe backend — a modular
> monolith with a strict dependency direction:
>
> ```
> API  →  Application  →  Domain
>                            ↑
>                  Infrastructure (implements Domain ports)
> ```
>
> The structure is **derived from Fansivibe's actual domain model** (STEP 3
> `FANSIVIBE_DOMAIN_MODEL_V1.md` E1–E10) and the accepted module map (STEP 5
> `BACKEND_MODULE_MAP.md` M1–M16). It does **not** copy any architecture from
> the separate reference project — it is designed only against the real
> repository (`backend/app` + `docs/` + Flutter `lib/features/`).
>
> **Status: design only. No directories, files, or code are created.** Every
> tree in this document is a *target shape* for later implementation (per
> `BACKEND_ARCHITECTURE_RULES.md` §9 M1–M6).
>
> **Source of truth:** the real Fansivibe repository. The separate reference
> project is reference material only and is **not** merged into this design.

---

## 1. Purpose and scope

This document answers: **what folders does the production backend have, what
is each folder for, what may it import, what may it never import, and what
files live there?**

It turns the module map (which modules exist and own what) into a physical
layout (where each module's api/application/domain/infrastructure code goes)
and makes the **dependency direction explicit per folder** so the modular
monolith cannot rot into a "everything imports everything" flat package.

It covers exactly the concerns requested:

- **API** — FastAPI routers, DTOs, auth dependency, error mapping.
- **Application / use cases** — one module per user action cluster.
- **Domain** — entities, value objects, decision engine, ports.
- **Infrastructure** — repositories, external adapters, DB session.
- **Database** — engine, migrations, transaction/append-only policy.
- **AI** — the decision engine (domain) + the AI provider adapter
  (infrastructure) — **not** a separate top-level layer.
- **Knowledge** — the curated knowledge base (domain-owned data + a
  `KnowledgeSource` port), exposed by the knowledge API.
- **Shared configuration** — settings, env vars, app wiring.

It does **not** define endpoint signatures, repository methods, or SQL — later
steps implement against this map.

**Grounding fact (BAR-0):** the folder structure represents the **domain
model**, not the Flutter UI. `lib/features/*` are consumers; the backend layout
is driven by the 10 entities + 16 modules, not by the 14 feature folders.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `BACKEND_ARCHITECTURE_RULES.md` | BA-1…BA-15: four layers (§3), module boundaries + target shapes (§4), dependency direction (§5), external ports (§7), migration M1–M6 (§9). |
| `BACKEND_MODULE_MAP.md` | Module set M1–M16 + owned domain concepts + tables per module (§4–§7). |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | Entities E1–E10 + value objects + ownership (§7) — names the domain model files. |
| `ACTION_API_INVENTORY.md` | The 32 user actions → endpoint clusters — names the API router files. |
| `TABLE_DEFINITIONS.md` / `DATABASE_DESIGN_RULES.md` | The 23 tables + append-only/JSONB policy — shapes the database folders. |
| `TRANSACTION_BOUNDARIES.md` | TRX-1…TRX-8 — where transactions open/close in the application layer. |
| `SECURITY_PRIVACY_DESIGN.md` | user_id scoping, MS10.3 gate (media), erasure events. |
| Current `backend/app` | `main.py`, `ai/{engine,intent,tools,llm_backend}.py`, `data/catalog.py`, `models/schemas.py` — the seeds this structure migrates (M1). |

Re-verified facts about the real backend that anchor the design:

- **One live API** (`POST /v1/assistant/chat`) + `GET /health`, no auth, no DB,
  no typed errors (L1–L12 in `BACKEND_ARCHITECTURE_RULES.md` §8).
- The assistant engine (`app/ai/engine.py`) is the seed of the **Domain
  decision engine**; `llm_backend.py` is the seed of the **AI provider
  adapter**; `catalog.py` is the seed of the **knowledge source**; `schemas.py`
  splits into **API DTOs** + **domain models** (M1, §4.3 of the rules doc).
- **AI is not a layer.** It is an external dependency reached through a
  Domain-defined port (`AIProvider`, BA-6/BA-8) and a domain service (the
  rules engine). Giving AI its own peer folder would violate dependency
  direction (see §5.1).

---

## 3. Design principles (short form)

The folder structure is governed by `BACKEND_ARCHITECTURE_RULES.md`; the
rules that directly shape folders:

| Rule | What it means for folders |
| --- | --- |
| BA-2 four layers | Top-level `api / application / domain / infrastructure`; no other top-level peers. |
| BA-3 pure domain | `app/domain/` imports nothing but stdlib; no FastAPI/SQLAlchemy/httpx. |
| BA-6 external via ports | AI/object-storage/weather/knowledge adapters live in `infrastructure/external/`. |
| BA-8 AI only via engine | `infrastructure/external/ai.py` is the only file that touches an AI provider; called only through the port from `domain/services`. |
| BA-10 repositories only data path | `infrastructure/repositories/` are the only implementers of `domain/ports/repositories.py`. |
| BA-14 minimal transactions | transaction opening/closing happens in the application layer, not in routers or repositories. |
| BA-1 modular monolith | one deployable package, folders keep feature isolation via import rules (§4/§6). |

---

## 4. Top-level layout (target shape)

```
backend/
├── README.md
├── requirements.txt          # pinned runtime deps (FastAPI, pydantic-settings, SQLAlchemy, httpx, psycopg…)
├── docker-compose.yml        # local Ollama + (later) local PostgreSQL
├── pyproject.toml            # (optional) tooling/lint config — not required
├── app/
│   ├── __init__.py
│   ├── main.py               # composition root: create_app(), mounts /health + /v1
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py       # pydantic-settings Settings (env-driven)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── deps.py           # auth dependency → current user_id
│   │   ├── errors.py         # typed error → HTTP response mapping (A3.3/E13.1)
│   │   ├── schemas/          # request/response DTOs (boundary projections)
│   │   │   ├── __init__.py
│   │   │   ├── assistant.py  # the A3.1 KEEP mirror (moved from models/schemas.py)
│   │   │   ├── users.py
│   │   │   └── ...
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py     # mounts all v1 routers
│   │       ├── auth.py
│   │       ├── users.py
│   │       ├── wardrobe.py
│   │       ├── assistant.py
│   │       ├── knowledge.py
│   │       ├── saved_looks.py
│   │       ├── events.py
│   │       ├── daily_outfit.py
│   │       ├── feedback.py   # feature-gated (M11)
│   │       ├── analysis.py
│   │       ├── outfits.py
│   │       ├── discover.py
│   │       ├── subscriptions.py
│   │       ├── media.py      # sealed until MS10.3 (M16)
│   │       └── sync.py       # POST /users/me/sync (P7.1)
│   ├── application/
│   │   ├── __init__.py
│   │   ├── auth.py           # register/login/logout use cases
│   │   ├── users.py          # profile/preferences/settings + sync
│   │   ├── wardrobe.py
│   │   ├── assistant.py      # orchestration around the decision engine
│   │   ├── knowledge.py
│   │   ├── saved_looks.py
│   │   ├── events.py
│   │   ├── daily_outfit.py
│   │   ├── feedback.py
│   │   ├── analysis.py
│   │   ├── outfits.py
│   │   ├── discover.py
│   │   ├── subscriptions.py
│   │   ├── media.py
│   │   └── transactions.py   # TRX boundaries / unit-of-work (BA-14)
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models/           # canonical entities + value objects (BAR-0)
│   │   │   ├── __init__.py
│   │   │   ├── user.py           # E1
│   │   │   ├── wardrobe_item.py  # E2
│   │   │   ├── user_event.py     # E3
│   │   │   ├── saved_look.py     # E4
│   │   │   ├── look.py           # E5
│   │   │   ├── analysis_run.py   # E6
│   │   │   ├── learning_signal.py# E7
│   │   │   ├── style_score_record.py # E8
│   │   │   ├── activity_day.py   # E9
│   │   │   ├── subscription.py   # E10
│   │   │   └── value_objects.py  # outfit, style_profile, preferences, settings
│   │   ├── services/         # decision engine + generation/analysis rules (M6)
│   │   │   ├── __init__.py
│   │   │   ├── engine.py     # assistant engine (moved from app/ai/engine.py)
│   │   │   ├── intent.py
│   │   │   ├── tools.py
│   │   │   ├── recommendations.py # recommendation/outfit/today generation rules
│   │   │   └── analysis_rules.py  # outfit/hairstyle/grooming run rules (M12)
│   │   ├── ports/
│   │   │   ├── __init__.py
│   │   │   ├── repositories.py    # repository interfaces (BA-10)
│   │   │   └── external.py        # AIProvider, ObjectStorage, WeatherProvider, KnowledgeSource (BA-6)
│   │   └── events.py         # domain events (UserDeleted, ItemAdded, …)
│   └── infrastructure/
│       ├── __init__.py
│       ├── db/
│       │   ├── __init__.py
│       │   ├── engine.py     # SQLAlchemy engine/session factory
│       │   ├── base.py       # DeclarativeBase + shared types
│       │   └── migrations/   # versioned, forward-only SQL migrations (M3)
│       │       ├── versions/
│       │       └── ...
│       ├── repositories/     # implementations of domain ports (BA-10)
│       │   ├── __init__.py
│       │   ├── users.py
│       │   ├── wardrobe_items.py
│       │   ├── user_events.py
│       │   ├── saved_looks.py
│       │   ├── looks.py
│       │   ├── analysis_runs.py
│       │   ├── learning_signals.py
│       │   ├── subscriptions.py
│       │   └── ...
│       ├── external/         # adapters implementing domain/external.py ports
│       │   ├── __init__.py
│       │   ├── ai.py         # AIProvider adapter (moved from app/ai/llm_backend.py; Ollama)
│       │   ├── knowledge.py  # KnowledgeSource adapter (moved from app/data/catalog.py; K9.1)
│       │   ├── object_storage.py  # MS10.3-gated — not built yet (M16)
│       │   └── weather.py         # not built yet (M9)
│       ├── events.py         # in-process domain-event dispatcher (port in domain/events.py)
│       └── jobs.py           # deferred background jobs (blob cleanup, webhook sync)
└── tests/
    ├── __init__.py
    ├── conftest.py           # fixtures: app, db session, repositories
    ├── test_health.py
    ├── unit/                 # mirrors domain/services + application
    │   ├── test_engine.py    # existing (kept)
    │   ├── test_intent.py    # existing (kept)
    │   └── ...
    ├── api/                  # router/endpoint tests per v1 router
    │   ├── test_assistant.py
    │   └── ...
    └── integration/          # repository tests against PostgreSQL (local-only)
```

> **Folders that do NOT exist** (deliberately): `app/ai/` (folded into
> `domain/services/` + `infrastructure/external/ai.py`), `app/data/` (folded
> into `infrastructure/external/knowledge.py`), `app/models/` (split into
> `api/schemas/` + `domain/models/`). See §5.1 and §8.

---

## 5. Dependency direction (the rule that holds the tree together)

```
            ┌──────────────┐
            │   app.main   │   composition root — imports everything, decides wiring
            └──────┬───────┘
                   │
        ┌──────────▼──────────┐        ┌──────────────────┐
        │     app/api         │ ─────► │  app/application │
        │  routers + DTOs     │        │  use cases       │
        └─────────────────────┘        └────────┬─────────┘
                                                 │
                                    ┌────────────▼────────────┐
                                    │       app/domain         │  pure Python
                                    │  models / services /    │  (no imports out)
                                    │  ports / events          │
                                    └────────────┬────────────┘
                                                 ▲
                                    ┌────────────┴────────────┐
                                    │   app/infrastructure     │  implements
                                    │  db / repositories /     │  domain ports
                                    │  external / events / jobs│
                                    └─────────────────────────┘
```

| From | May import | Must never import |
| --- | --- | --- |
| `app/main.py` | everything (it wires the app) | business logic |
| `app/api/` | `application`, `domain` (DTOs/errors only via `api/schemas`, `domain/events` for error codes), `config` | `infrastructure`, repositories, SQLAlchemy, provider SDKs, business logic |
| `app/application/` | `domain` (models, services, ports), `config` | `api`, FastAPI, SQLAlchemy, `infrastructure`, repositories, HTTP, provider SDKs |
| `app/domain/` | stdlib only | everything (`api`, `application`, `infrastructure`, FastAPI, SQLAlchemy, httpx, config) |
| `app/infrastructure/` | `domain` (ports to implement), `config` | `api`, `application`, business/decision logic |
| `app/config/` | stdlib + `pydantic_settings` only | `app.*` (it is the leaf) |

Two cross-cutting rules:

- **No cycles (BA-5):** nothing below `api` may import `api`; nothing below
  `domain` may import `application`; `infrastructure` never imports
  `application` (repositories implement domain ports only).
- **Composition root only (`main.py`):** dependency injection is assembled
  only here. `api` never instantiates repositories; it receives application
  use cases as constructor/`Depends` objects, which are wired in `main.py`.

### 5.1 Why AI, knowledge, database, and config are NOT top-level layers

The task lists API / application / domain / infrastructure / database / AI /
knowledge / shared configuration as concerns. All eight are supported, but
only four are **layers**. The other four are concerns that live *inside* a
layer — making them peers would break the dependency direction:

| Concern | Where it lives | Why it is not a layer |
| --- | --- | --- |
| **Database** | `infrastructure/db/` + `infrastructure/repositories/` | Persistence is an implementation of domain repository ports (BA-10); a `db` peer folder would be importable from application, which is forbidden. |
| **AI** | `domain/services/` (engine + rules) + `infrastructure/external/ai.py` (provider adapter) | The *rules* are domain logic (BA-8); the *provider* is an external dependency behind `AIProvider` (BA-6). AI must never be reached from API/application directly. |
| **Knowledge** | `domain/models/{look,categories,…}` + `domain/ports` (`KnowledgeSource`) + `infrastructure/external/knowledge.py` + `api/v1/knowledge.py` | Knowledge is *domain-owned data* (K9.1) served through a port; a peer folder would let features import knowledge without the port. |
| **Shared configuration** | `config/settings.py` (imported by `main`, `api` deps, `infrastructure`) | It is a leaf utility, not a layer; it must not import `app.*` and must not be imported by domain. |

---

## 6. Per-folder definition

For every folder: **purpose**, **allowed dependencies**, **forbidden
dependencies**, **examples of files**.

### 6.1 `app/` (package root) + `app/main.py`

- **Purpose:** the deployable FastAPI package. `main.py` is the
  **composition root**: builds the app via `create_app()`, loads `config`,
  wires repositories → use cases → routers, mounts `/health` and `/v1`.
  It is the *only* place dependencies are assembled (DI), and the *only*
  place the migration M1 target surfaces: today it just mounts the assistant
  router; later it mounts all v1 routers.
- **Allowed dependencies:** everything in `app/` (that is its job).
- **Forbidden dependencies:** none from *inside* `app/`; it must not contain
  business logic — it only wires and starts.
- **Examples:** `__init__.py`, `main.py` (`create_app()`).

### 6.2 `app/config/`

- **Purpose:** shared configuration — environment-driven settings for the
  whole service (database URL, JWT/OAuth2 secrets, Ollama host/model,
  feature gates like `MS10.3_ENABLED`, log level). Loaded once by `main.py`
  and injected where needed.
- **Allowed dependencies:** stdlib, `pydantic_settings` (env parsing). It is
  a **leaf** — nothing in `app/` may be imported by config.
- **Forbidden dependencies:** any `app.*` module, any third-party SDKs, any
  I/O beyond reading env.
- **Examples:** `settings.py` (`Settings(BaseSettings)`), `__init__.py`.

### 6.3 `app/api/`

- **Purpose:** the HTTP boundary. FastAPI routers, request/response DTOs
  (boundary projections — never the source of truth, BAR-0), the auth
  dependency (`deps.py`: resolves session → `user_id`), and typed error →
  HTTP status mapping (`errors.py`, A3.3/E13.1). One router file per module
  (M1–M16), mounted under `/v1` by `router.py`.
- **Allowed dependencies:** `application` (use cases), `api/schemas`
  (DTOs), `domain` (only error codes / event types for mapping), `config`.
- **Forbidden dependencies:** `infrastructure` (repositories, db, external),
  SQLAlchemy, provider SDKs, any business/decision logic. A router parses
  input, calls exactly one application use case, maps result → HTTP response.
- **Examples:**
  - `v1/assistant.py` — `POST /v1/assistant/chat`, `POST /assistant/feedback`
  - `v1/users.py`, `v1/sync.py`, `v1/wardrobe.py`, `v1/auth.py`
  - `v1/knowledge.py`, `v1/events.py`, `v1/saved_looks.py`,
    `v1/daily_outfit.py`, `v1/analysis.py`, `v1/outfits.py`,
    `v1/discover.py`, `v1/subscriptions.py`
  - `v1/feedback.py` (feature-gated), `v1/media.py` (sealed until MS10.3)
  - `deps.py` (auth dependency), `errors.py`, `schemas/assistant.py`

### 6.4 `app/api/schemas/`

- **Purpose:** typed request/response DTOs. **`schemas/assistant.py` is the
  A3.1 KEEP mirror** — the DTO shape the Flutter `models.dart` mirrors is
  moved here *unchanged* (BAR-0, migration M1 preserves the wire contract).
  All other DTOs are projections of domain models.
- **Allowed dependencies:** `domain` (to project *from* canonical models),
  stdlib/pydantic.
- **Forbidden dependencies:** `application`, `infrastructure`, persistence;
  DTOs hold no logic and never mutate domain state.
- **Examples:** `assistant.py` (`AssistantRequest`, `AssistantReply`,
  `SuggestionCard` — moved verbatim), `users.py`, `wardrobe.py`,
  `knowledge.py`, `analysis.py`.

### 6.5 `app/application/`

- **Purpose:** use cases / application services — one file per module. Each
  use case orchestrates exactly one user action (from
  `ACTION_API_INVENTORY.md`): load domain state via repository **ports**,
  run the domain decision engine, apply the TRX boundary
  (`transactions.py`), persist via ports, return a typed result. Owns the
  `user_id` scoping for every call (BA-8) and erasure (R50/R51).
- **Allowed dependencies:** `domain` (models, services, ports), `config`
  (feature gates), `application/transactions.py`.
- **Forbidden dependencies:** `api` (FastAPI, DTOs), `infrastructure`
  (concrete repositories, SQLAlchemy), HTTP, provider SDKs. Application
  depends on **interfaces** defined in `domain/ports`, never on
  implementations.
- **Examples:**
  - `assistant.py` — `chat()` orchestrates `domain.services.engine`
  - `users.py` — `sync()` (P7.1), `update_profile()`, `update_preferences()`
  - `wardrobe.py` — `add_item()`, `list_items()`
  - `outfits.py`, `daily_outfit.py`, `analysis.py`, `discover.py`
  - `transactions.py` — unit-of-work / TRX-1…TRX-8 helpers

### 6.6 `app/domain/` (pure Python — the heart)

- **Purpose:** the Fansivibe domain as pure Python. **Models** are the 10
  entities + value objects from the domain model (the canonical shapes;
  DTOs are projections). **Services** are the decision engine and the
  recommendation/analysis rules. **Ports** are the interfaces Infrastructure
  implements. **Events** are domain events for cross-module effects.
- **Allowed dependencies:** stdlib only. (Type-only stdlib `dataclasses`,
  `enum`, `abc`, `typing`.) `models` and `services` and `ports` and
  `events` may import each other.
- **Forbidden dependencies:** `api`, `application`, `infrastructure`,
  `config`, FastAPI, SQLAlchemy, httpx, provider SDKs, any I/O. This is the
  non-negotiable (BA-3) — it is what makes the engine testable and portable.
- **Examples:**
  - `models/user.py` (E1), `models/wardrobe_item.py` (E2),
    `models/user_event.py` (E3), `models/saved_look.py` (E4),
    `models/look.py` (E5), `models/analysis_run.py` (E6),
    `models/learning_signal.py` (E7), `models/style_score_record.py` (E8),
    `models/activity_day.py` (E9), `models/subscription.py` (E10),
    `models/value_objects.py` (outfit, style_profile, preferences)
  - `services/engine.py`, `services/intent.py`, `services/tools.py`
    (moved from `app/ai/`, kept byte-compatible with today's behavior)
  - `services/recommendations.py` (M6/M13 generation rules),
    `services/analysis_rules.py` (M12)
  - `ports/repositories.py` (BA-10), `ports/external.py` (BA-6:
    `AIProvider`, `ObjectStorage`, `WeatherProvider`, `KnowledgeSource`)
  - `events.py` (`UserDeleted`, `ItemAdded`, `TodayActive`)

### 6.7 `app/domain/ports/`

- **Purpose:** the seams where the domain meets the world. `repositories.py`
  declares repository interfaces the domain/application depend on (BA-10);
  `external.py` declares the external-system interfaces (BA-6). Domain code
  depends on these abstractions and never on their implementations.
- **Allowed dependencies:** `domain/models`, `domain/events`, stdlib `abc`.
- **Forbidden dependencies:** anything concrete (SQLAlchemy, httpx, SDKs).
- **Examples:** `repositories.py` (`WardrobeItemRepository`,
  `UserRepository`, `SavedLookRepository`, `LearningSignalRepository`),
  `external.py` (`AIProvider`, `ObjectStorage`, `WeatherProvider`,
  `KnowledgeSource`).

### 6.8 `app/infrastructure/`

- **Purpose:** the concrete outside world — everything that makes the domain
  run: DB engine/session, repository implementations, external adapters,
  domain-event dispatcher, background jobs. It is the *bottom* layer: it may
  only implement what `domain/ports` declares.
- **Allowed dependencies:** `domain` (ports to implement, models), `config`.
- **Forbidden dependencies:** `api`, `application`, and any business/decision
  logic. No use case lives here; repositories are thin mappers between
  domain models and rows (respecting `TABLE_DEFINITIONS.md`, append-only
  grants BA-9, user scoping BA-8, TRX boundaries BA-14).
- **Examples:** see §6.8.1–6.8.4.

### 6.8.1 `app/infrastructure/db/`

- **Purpose:** the **database** concern — PostgreSQL connection/session
  management (`engine.py`), shared ORM base/types (`base.py`), and versioned
  **forward-only migrations** (`migrations/`) that encode the STEP 4
  23-table schema (M3). Local-only until auth decisions land (§9 M3).
- **Allowed dependencies:** `config`, `domain/models` (to map rows to
  entities), SQLAlchemy, psycopg.
- **Forbidden dependencies:** `application`, `api`, `infrastructure/repositories`
  (engine is a sibling, not a parent), business logic.
- **Examples:** `db/engine.py`, `db/base.py`,
  `db/migrations/versions/0001_init.py`, `db/migrations/versions/0002_*.py`.

### 6.8.2 `app/infrastructure/repositories/`

- **Purpose:** implementations of the `domain/ports/repositories.py`
  interfaces against PostgreSQL. One file per module's primary tables.
  Enforce user scoping (every query filters by `user_id`, BA-8), append-only
  grants (BA-9), and TRX boundaries (BA-14).
- **Allowed dependencies:** `domain` (ports, models), `config`,
  `infrastructure/db` (session).
- **Forbidden dependencies:** `api`, `application`, use-case logic.
- **Examples:** `users.py`, `wardrobe_items.py`, `user_events.py`,
  `saved_looks.py`, `looks.py`, `analysis_runs.py`, `learning_signals.py`,
  `subscriptions.py`, `style_score_records.py`, `activity_days.py`.

### 6.8.3 `app/infrastructure/external/`

- **Purpose:** the **AI / knowledge / media / weather** adapters. Each file
  implements a `domain/ports/external.py` interface. `ai.py` is the **only**
  file in the whole codebase allowed to touch an AI provider (BA-8).
  `knowledge.py` is the **KnowledgeSource** adapter (K9.1, seeded from the
  current `catalog.py`). `object_storage.py` and `weather.py` are stubs,
  gated (MS10.3 / weather feature) and not built.
- **Allowed dependencies:** `domain` (ports, models), `config` (hosts/model
  names), the relevant client SDK (httpx for Ollama, s3 client for storage).
- **Forbidden dependencies:** `api`, `application`, decision logic.
- **Examples:** `ai.py` (Ollama `AIProvider` adapter — migrated from
  `app/ai/llm_backend.py`, kept optional/degradable),
  `knowledge.py` (migrated from `app/data/catalog.py`),
  `object_storage.py` (placeholder, sealed),
  `weather.py` (placeholder).

### 6.8.4 `app/infrastructure/events.py` and `jobs.py`

- **Purpose:** the **event/background-job** machinery. `events.py` is an
  in-process domain-event dispatcher implementing the port in
  `domain/events.py` (used for `UserDeleted` erasure cascade, `ItemAdded` →
  learning signal, webhook handling). `jobs.py` holds deferred work (M16
  orphan-blob cleanup, M15 entitlement webhook sync, M9 streak derivation).
- **Allowed dependencies:** `domain` (events), `config`,
  `infrastructure/repositories`/`external`.
- **Forbidden dependencies:** `api`, `application`, business rules.
- **Examples:** `events.py`, `jobs.py`.

### 6.9 `tests/`

- **Purpose:** automated tests mirroring the layer layout. `unit/` tests
  domain + application (pure, no DB — the engine tests move here unchanged);
  `api/` tests routers via `TestClient` with injected fakes; `integration/`
  tests repositories against local-only PostgreSQL. `conftest.py` provides
  the app, a session, and fake repository fixtures.
- **Allowed dependencies:** test framework, `app` (via DI in `conftest`),
  fakes implementing `domain/ports`.
- **Forbidden dependencies:** nothing imports `tests`; tests may import any
  `app` layer (that is their job).
- **Examples:** `unit/test_engine.py`, `unit/test_intent.py` (existing tests,
  kept), `unit/test_recommendations.py`, `api/test_assistant.py`,
  `integration/test_wardrobe_repo.py`.

---

## 7. Module ↔ folder mapping (M1–M16)

Each module contributes one file per layer (and its domain model files).
`M1–M6` are P0; `M7–M11` P1; `M12–M16` P2 (per `BACKEND_MODULE_MAP.md`).

| Module | API router | Application | Domain models | Repositories |
| --- | --- | --- | --- | --- |
| M1 auth | `v1/auth.py` | `auth.py` | *(session; no entity)* | `users.py` (create only) |
| M2 users | `v1/users.py`, `v1/sync.py` | `users.py` | `models/user.py`, `value_objects.py` | `users.py`, `user_state.py` |
| M3 wardrobe | `v1/wardrobe.py` | `wardrobe.py` | `models/wardrobe_item.py` | `wardrobe_items.py` |
| M4 assistant | `v1/assistant.py` | `assistant.py` | `services/engine.py`+`intent.py`+`tools.py` | `assistant_messages.py` |
| M5 knowledge | `v1/knowledge.py` | `knowledge.py` | `models/look.py` | `looks.py`, vocab repos |
| M6 ai_engine | *(domain only)* | *(used via M4/M12/M13)* | `services/recommendations.py`, `services/analysis_rules.py`, `ports/external.py` | — |
| M7 saved_looks | `v1/saved_looks.py` | `saved_looks.py` | `models/saved_look.py` | `saved_looks.py` |
| M8 events | `v1/events.py` | `events.py` | `models/user_event.py` | `user_events.py` |
| M9 daily_outfit | `v1/daily_outfit.py` | `daily_outfit.py` | `models/activity_day.py` | `activity_days.py`, `today_look_records.py` |
| M10 learning | *(internal seam)* | `learning.py` | `models/learning_signal.py`, `style_score_record.py`, `activity_day.py` | `learning_signals.py`, `style_score_records.py` |
| M11 feedback | `v1/feedback.py` *(gated)* | `feedback.py` | `models/feedback_event.py` | `feedback_events.py` |
| M12 analysis | `v1/analysis.py` | `analysis.py` | `models/analysis_run.py` | `analysis_runs.py` |
| M13 outfits | `v1/outfits.py` | `outfits.py` | `models/value_objects.py` (outfit) | *(writes)* `analysis_runs.py`, `saved_looks.py` |
| M14 discover | `v1/discover.py` | `discover.py` | — | *(reads)* `looks.py`, `categories.py` |
| M15 subscriptions | `v1/subscriptions.py` | `subscriptions.py` | `models/subscription.py` | `subscriptions.py` |
| M16 media | `v1/media.py` *(sealed)* | `media.py` | `models/value_objects.py` (MediaRef) | media columns (owning tables) |

---

## 8. Current → target file mapping (migration M1 seed)

The real backend today has 7 Python files. This is exactly how they migrate
into the target tree without breaking the live contract (M1, `§9` of the
rules doc):

| Today (`backend/app/`) | Target | Why |
| --- | --- | --- |
| `main.py` | `main.py` (composition root) | gains `create_app()` + router mounting; `/health` and `POST /v1/assistant/chat` unchanged |
| `ai/engine.py` | `domain/services/engine.py` | decision engine is pure domain (BA-3) |
| `ai/intent.py` | `domain/services/intent.py` | same |
| `ai/tools.py` | `domain/services/tools.py` | same |
| `ai/llm_backend.py` | `infrastructure/external/ai.py` | provider adapter behind `AIProvider` port (BA-8) |
| `data/catalog.py` | `infrastructure/external/knowledge.py` | knowledge source behind `KnowledgeSource` port (K9.1) |
| `models/schemas.py` | `api/schemas/assistant.py` (DTOs, **kept verbatim** A3.1) | DTOs are boundary projections; domain models derived from STEP 3 |

No file is deleted and no behavior changes in M1 — files move, imports
rewire through `main.py`'s DI, tests keep passing (19 existing pytest cases
move to `tests/unit/` unchanged).

---

## 9. Open decisions (unchanged, carried forward)

1. **Auth provider** (OAuth2 vs email/password) — affects `api/deps.py` and
   M1. Until decided, `deps.py` is a stub that resolves a placeholder
   `user_id`.
2. **AI provider** (Ollama vs hosted) — affects `infrastructure/external/ai.py`
   only; the port and folder are provider-agnostic.
3. **`user_state` shape** (single JSONB vs columns) — affects M2 repository.
4. **Knowledge seeding source** — affects `infrastructure/external/knowledge.py`.
5. **Media gate MS10.3** — gates `infrastructure/external/object_storage.py`
   and `api/v1/media.py`.
6. **Billing provider** — affects `infrastructure/external` webhook adapter.
7. **Migration tooling** — Alembic vs plain SQL for
   `infrastructure/db/migrations/` (M3). Determined at M3, not now.

None block the P0 slice (M1–M6) folder layout.

---

## 10. Report, assumptions, constraints

**What changed (this step):** added `BACKEND_FOLDER_STRUCTURE.md` — the target
FastAPI folder layout for the real Fansivibe backend, with per-folder
purpose / allowed & forbidden dependencies / file examples and an explicit
dependency-direction rule. No directories or files created.

**Skills used:** repository analysis (actual `backend/app` structure, domain
model, module map, architecture rules) — architecture documentation only.

**Files changed:** `docs/backend/BACKEND_FOLDER_STRUCTURE.md` (new).

**Validation run:**
- Cross-checked against the real `backend/app` tree (`main.py`, `ai/*`,
  `data/catalog.py`, `models/schemas.py`) and verified each file maps to a
  target folder (§8).
- Verified folder names against `BACKEND_MODULE_MAP.md` M1–M16 and
  `FANSIVIBE_DOMAIN_MODEL_V1.md` E1–E10 (§7).
- Verified the dependency-direction table against BA-2/BA-3/BA-5/BA-6/BA-8/
  BA-10/BA-14.
- `git status --short` confirms no code/dirs created (see below).
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- Next implementation step (per rules doc §9 M1): create the folder skeleton
  **without behavior change** — move engine/intent/tools/catalog/schemas into
  the target folders behind a composition root, keeping `POST /v1/assistant/chat`
  and the 19 tests green.
- After M1: M2 typed errors, M3 SQL migrations, M4 P0 slice (auth, sync,
  wardrobe, authenticated assistant, knowledge) once auth/contract decisions
  land.
- No `DECISIONS.md` entry needed: no accepted architectural decision was made
  in this step (documentation only); open items remain in §9.

**Assumptions recorded:**
- "Folder structure" is a **target shape**; nothing is physically created
  until the M1 implementation step.
- The four-layer top level (`api/application/domain/infrastructure`) is kept
  per the already-accepted `BACKEND_ARCHITECTURE_RULES.md` BA-2; database, AI,
  knowledge, and config are intentionally *inside* those layers (§5.1), not
  peer folders, to preserve dependency direction.
- Module files are layer-first (one file per module per layer), consistent
  with §4 of the architecture rules, rather than folder-per-module, because
  the rules doc defined this shape and the module map already names modules.
- No new third-party dependencies are proposed here beyond what the layers
  require (SQLAlchemy/psycopg for the DB, pydantic-settings for config,
  httpx for the AI adapter) — each is introduced only in its implementing
  step (M3, M4) when a real need exists (BA-10/no-premature-complexity).

**Constraints honored:** BAR-0 (domain-model-driven, not UI-driven; assistant
DTOs are the KEEP mirror), BA-2 four layers, BA-3 pure domain, BA-5 no
cycles, BA-6 external via ports, BA-8 AI only in the engine/adapter,
BA-10 repositories only data path, the UI Change Safety Rule (no UI touched),
and the Scope rule (task only: this document).
