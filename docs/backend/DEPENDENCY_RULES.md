# Fansivibe — Backend Dependency Rules

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Defines the **explicit dependency
> rules** for the real Fansivibe production FastAPI backend. These are the
> binding import/architecture contracts that hold the modular monolith
> together, stated independently so they can be **enforced by tooling**
> (import-linter, CI, code review) and checked before any module is
> implemented.
>
> Derived from the already-accepted STEP 5 deliverables:
> `BACKEND_ARCHITECTURE_RULES.md` (BA-1…BA-15, §5 dependency direction) and
> `BACKEND_FOLDER_STRUCTURE.md` (§5 import matrix). This document extracts the
> dependency direction into **standalone, machine-checkable rules** and adds
> the **forbidden-dependency catalogue**.
>
> **Status: design only. No code, directories, files, or dependencies are
> created or changed.**

---

## 1. Purpose and scope

This document is the **dependency contract** for the Fansivibe backend. It
answers two questions for every file that will be written:

1. **What may this file import?** (allowed dependencies)
2. **What must this file never import?** (forbidden dependencies)

It covers exactly the requested edges:

- API → Application
- Application → Domain
- Infrastructure → Application/Domain interfaces
- Repositories → Database
- AI adapters → AI interfaces
- Knowledge adapters → Knowledge interfaces

…plus the forbidden set (Domain↛FastAPI/SQLAlchemy/HTTP, UI concepts, database
models as API contracts, AI provider leakage, etc.).

It does **not** define endpoints, classes, or code. It is the rulebook the
implementation steps (M1–M6) and CI must obey.

**Grounding fact (BAR-0):** rules exist to keep the backend a faithful,
testable representation of the **domain model**, not a mirror of the Flutter
UI, and to keep the one **live contract** (`POST /v1/assistant/chat`, A3.1)
unbroken while the architecture evolves.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `BACKEND_ARCHITECTURE_RULES.md` | BA-2 (layers), BA-3 (pure domain), BA-5 (no cycles), BA-6 (external via ports), BA-8 (AI only via engine), BA-10 (repositories only data path), BA-14 (minimal transactions); §5 dependency-direction rules 1–6. |
| `BACKEND_FOLDER_STRUCTURE.md` | §5 import matrix (from → may import → must never import) per folder; §6.6 domain purity; §6.8.3 AI/knowledge adapters. |
| `BACKEND_MODULE_MAP.md` | M1–M16 module boundaries — which module owns which domain concept and which API/application/repository file. |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | Entities E1–E10 — what "domain" is; UI concepts are not among them. |
| `ACTION_API_INVENTORY.md` | The 32 user actions — the application use cases; API is a thin projection of them. |
| `TRANSACTION_BOUNDARIES.md` | TRX-1…TRX-8 — where transactions live (application layer), reinforcing "repositories never own business flow". |
| Current `backend/app` | The seeds to be migrated (engine/intent/tools → domain, llm_backend → AI adapter, catalog → knowledge adapter, schemas → DTO split). |

---

## 3. The dependency graph (canonical)

```
                       ┌──────────────────────────────────────────────┐
                       │  app.main (composition root / DI wiring)      │
                       └───────────────────────┬──────────────────────┘
                                               │ imports & wires everything
        ┌──────────────────────┐               │
        │       API            │               │
        │  routers, DTOs,      │──────────────►│
        │  auth dep, errors    │  depends on   │
        └──────────┬───────────┘               │
                   │  depends on               │
        ┌──────────▼───────────┐               │
        │   Application        │               │
        │  use cases, TRX      │──────────────►│
        └──────────┬───────────┘               │
                   │  depends on               │
        ┌──────────▼───────────┐   ┌───────────▼───────────┐
        │       Domain         │◄──│    Infrastructure     │
        │  models, services,   │   │  db, repositories,    │
        │  ports, events       │   │  external adapters    │
        └──────────────────────┘   │  implements Domain    │
                                   │  ports                │
                                   └───────────────────────┘
                                     │
                                     ▼
                              PostgreSQL / providers
                              (reached only through
                               infrastructure)
```

**The one rule that everything else derives from (DR-0):**

> **Dependencies point inward.** `API → Application → Domain`; `Infrastructure`
> points *up at Domain's interfaces* and *down at concrete externals*. Nothing
> ever points back up. Violating DR-0 is the only dependency error that
> requires an architecture decision to fix, not just a refactor.

---

## 4. Allowed dependency rules

### 4.1 API → Application  (DR-1)

**Statement:** API code may depend on Application use cases, on its own DTOs
(`api/schemas/`), on `domain` only for error codes / event types used in
response mapping, and on `config`.

**What it means in code:**

- `app/api/v1/*.py` imports `app/application/*` (the use case it serves) and
  `app/api/schemas/*` (the request/response DTOs it validates/serializes).
- A router **calls exactly one application use case**, then maps the result to
  an HTTP response. It never reimplements logic.
- The auth dependency (`deps.py`) resolves session → `user_id` and passes it
  to the use case; the use case is what enforces scoping (BA-8), not the
  router.

**Examples:**

```python
# app/api/v1/assistant.py
from app.application.assistant import chat_with_user   # application use case
from app.api.schemas.assistant import AssistantRequest, AssistantReply
```

**Forbidden (see §5):** importing `app/infrastructure`, SQLAlchemy, provider
SDKs, or business logic from a router.

### 4.2 Application → Domain  (DR-2)

**Statement:** Application depends on Domain **only** — its models (to read
state), its services (the decision engine), and its **ports** (interfaces to
persistence and externals). It depends on `config` for feature gates. It never
depends on Infrastructure by import.

**What it means in code:**

- `app/application/*.py` imports `app/domain/models`, `app/domain/services`,
  `app/domain/ports`, `app/domain/events`, `app/config`.
- A use case receives repository/port **instances** (constructor injection,
  wired by the composition root), never imports the concrete SQLAlchemy
  repository.
- Transactions open/close here (TRX-1…TRX-8, BA-14), not in repositories or
  routers.

**Examples:**

```python
# app/application/wardrobe.py
from app.domain.ports.repositories import WardrobeItemRepository  # interface
from app.domain.models.wardrobe_item import WardrobeItem
```

**Forbidden (see §5):** importing `app/infrastructure` or FastAPI/SQLAlchemy;
constructing repositories; HTTP calls to providers.

### 4.3 Infrastructure → Application/Domain interfaces  (DR-3)

**Statement:** Infrastructure **implements** the interfaces that Domain and
Application depend on. It imports Domain (ports + models) and `config`. It
never imports API or Application.

**What it means in code:**

- `app/infrastructure/repositories/*` implement `domain/ports/repositories.py`
  — each is a `class XRepository` subclass/implementer of the port interface,
  and maps rows ↔ domain models.
- `app/infrastructure/external/*` implement `domain/ports/external.py`
  (`AIProvider`, `ObjectStorage`, `WeatherProvider`, `KnowledgeSource`).
- `app/infrastructure/db/*`, `app/infrastructure/events.py`,
  `app/infrastructure/jobs.py` also sit below Domain.
- Wiring of Infrastructure into Application happens **only in `main.py`**
  (composition root / DI), never via imports in use-case code (BA-5 rule 4).

**Examples:**

```python
# app/infrastructure/repositories/wardrobe_items.py
from app.domain.ports.repositories import WardrobeItemRepository  # implements
from app.domain.models.wardrobe_item import WardrobeItem
```

**Forbidden (see §5):** importing `app/api` or `app/application` from
infrastructure; embedding business/decision rules in a repository.

### 4.4 Repositories → Database  (DR-4)

**Statement:** Repository implementations are the **only** code that talks to
PostgreSQL. They depend on the DB engine/session (`infrastructure/db`) and on
the domain models they map.

**What it means in code:**

- `app/infrastructure/repositories/*` imports `app/infrastructure/db` (session
  factory) + `app/domain/models` + `app/domain/ports` (the interface it
  implements).
- Every repository query is scoped by `user_id` (BA-8), honors append-only
  grants (BA-9), and uses only the tables from `TABLE_DEFINITIONS.md`.
- No router or use case imports SQLAlchemy directly; the session is used only
  inside repository methods and the TRX boundary helper
  (`application/transactions.py`).

**Examples:**

```python
# app/infrastructure/repositories/learning_signals.py
from app.infrastructure.db import get_session
from app.domain.models.learning_signal import LearningSignal
```

**Forbidden (see §5):** SQLAlchemy/PG imports outside `infrastructure/db` +
`infrastructure/repositories` + `application/transactions.py`; repositories
containing decision rules or returning raw ORM rows as API responses.

### 4.5 AI adapters → AI interfaces  (DR-5)

**Statement:** AI-provider code is confined to **one adapter**,
`infrastructure/external/ai.py`, which implements the Domain `AIProvider`
port. Nothing else in the codebase knows an AI provider exists.

**What it means in code:**

- `app/infrastructure/external/ai.py` imports `domain/ports/external.py`
  (`AIProvider`) and `config` (host/model) and the HTTP client SDK (httpx).
- The **only** caller of `AIProvider` is the Domain decision engine
  (`domain/services/engine.py`) — which depends on the *interface*, never on
  the adapter. This is BA-8: AI is reached only through the engine.
- Swapping Ollama → a hosted provider, or disabling the LLM, touches only this
  file (today's `llm_backend.py` degrades gracefully; that contract is kept).

**Examples:**

```python
# app/infrastructure/external/ai.py
from app.domain.ports.external import AIProvider

class OllamaAIProvider(AIProvider):   # the only AI-specific code
    ...
```

**Forbidden (see §5):** importing `ai.py` (or an SDK) from `api/`,
`application/`, or any `domain/` file; hardcoding provider names elsewhere.

### 4.6 Knowledge adapters → Knowledge interfaces  (DR-6)

**Statement:** Knowledge content is reached only through the Domain
`KnowledgeSource` port. The curated catalog (today's `catalog.py`, K9.1) lives
behind one adapter, `infrastructure/external/knowledge.py`. Consumers
(assistant engine, discover, generation) depend on the port, never on the
concrete catalog.

**What it means in code:**

- `app/infrastructure/external/knowledge.py` implements
  `domain/ports/external.py: KnowledgeSource`.
- The `looks`/categories/colors/occasions/items vocabulary is **domain-owned
  data** (M5); the API exposes it through `api/v1/knowledge.py` →
  `application/knowledge.py` → the port.
- No feature hardcodes its own category list (BA-11 single knowledge source).

**Examples:**

```python
# app/infrastructure/external/knowledge.py
from app.domain.ports.external import KnowledgeSource

class CatalogKnowledgeSource(KnowledgeSource):   # migrated catalog.py
    ...
```

**Forbidden (see §5):** importing `catalog.py`/`knowledge.py` from features;
hardcoded vocabularies in feature code; knowledge content leaking into AI
adapter code (knowledge is data, AI is inference).

---

## 5. Forbidden dependencies (catalogue)

These are explicit "never do this" rules. Each is stated as an invariant with
its rationale. A violation of **any** of these is a merge-blocking defect.

### F-1 — Domain must not import FastAPI. 

Domain is pure Python (BA-3). `app/domain/*` may import only the stdlib
(`dataclasses`, `enum`, `abc`, `typing`, `dataclasses.field`, …). No
`fastapi.*`, no Pydantic `BaseModel` for domain entities, no
`Depends`/`APIRouter`, no HTTP decorators. Rationale: the domain (engine,
recommendation rules, entities) must be testable without a server, and must
survive a framework change.

### F-2 — Domain must not import SQLAlchemy (or any ORM / driver).

No `sqlalchemy.*`, no `psycopg`, no column/declarative imports in `domain/`.
Domain models are plain classes/`dataclasses`; mapping to tables belongs to
`infrastructure/repositories` + `infrastructure/db`. Rationale: entities are
not rows; DB concerns change independently of business rules.

### F-3 — Domain must not depend on HTTP.

No `httpx`, `requests`, `aiohttp`, no URLs, no client code, no `HTTPException`
in `domain/`. If the domain needs an external result (weather, AI, a webhook
callback), it declares a **port** (`ports/external.py`) and the caller injects
the result; the domain never fetches it. Rationale: the decision engine must
stay synchronous, deterministic, and offline-testable.

### F-4 — Domain must not import config / read environment.

No `app.config`, no `os.environ` reads, no global `Settings` in `domain/`.
Settings that shape rules are **passed in** as parameters by the application
layer. Rationale: keeps domain free of ambient state (BA-3).

### F-5 — UI concepts must not enter the backend domain.

The domain contains only `FANSIVIBE_DOMAIN_MODEL_V1.md` concepts (E1–E10 +
value objects). Forbidden in `domain/`: Flutter widget names, route names,
screen names, `lib/features/*` concepts, client DTO shapes (BAR-0), and
UI-only concerns (splash, theming, navigation). Rationale: the backend
represents the domain model, not the app UI; UI shapes are boundary projections
(`api/schemas/`) that may change without touching domain code.

### F-6 — Database models must not become API contracts automatically.

ORM/table classes (`infrastructure/db`) and domain models are **not** the HTTP
contract. Every response passes through an explicit DTO in `api/schemas/`; a
table column must never serialize to JSON because the ORM row was returned.
Rationale: API stability and privacy — the wire shape is owned by the API
layer (A3.1 assistant DTOs are the KEEP mirror), so schema changes never
silently break clients or leak fields.

### F-7 — AI provider-specific code must not leak throughout the application.

`Ollama`, `llama3.1`, `11434`, provider SDKs, prompt-format details — all live
in exactly one file: `infrastructure/external/ai.py`. Nothing in `api/`,
`application/`, or `domain/` may mention a provider or import its SDK.
Rationale (BA-8): the app depends on the `AIProvider` interface; a provider
swap is a one-file change, and provider-specific failure modes never surface
in use cases.

### F-8 — No repository or external-adapter imports from API or Application.

`infrastructure/*` never does `from app.api…` or `from app.application…`.
Rationale (DR-3/BA-5): direction is upward only; Infrastructure implements
ports, it does not reach into upper layers.

### F-9 — No use case imports a concrete repository.

`application/*` may import `domain/ports/repositories.py` (the interface) but
never `infrastructure/repositories/*`. Repositories reach the use case via
**constructor/DI injection** wired in `main.py`. Rationale (BA-5 rule 4):
keeps application code free of concrete persistence and trivially testable
with fakes.

### F-10 — No cross-feature internal access.

One module's use case must not reach into another module's internal
data/presentation (feature isolation, `docs/ARCHITECTURE.md`, BA-5 rule 6).
Cross-feature needs go through the shared **Domain model + ports** (e.g.
`outfits` reads wardrobe items via the `WardrobeItemRepository` port, not by
importing wardrobe internals). Rationale: modules stay independently
testable and migratable (BA-11, PR-11).

### F-11 — No domain event/decision logic in routers or repositories.

Routers parse and respond; repositories read/write rows. Neither performs
decision-engine or recommendation logic. Rationale (BA-3/BA-14): decisions
belong to `domain/services`; transactions belong to `application`.

### F-12 — No live external calls inside a transaction.

An AI/weather/billing call never happens between `BEGIN` and `COMMIT` of a
PostgreSQL transaction (TRX-1…TRX-8). External effects happen **after commit**
via `infrastructure/jobs.py` or the events dispatcher. Rationale: DB
transactions stay short and replayable.

### F-13 — Assistant DTOs must never change shape.

`api/schemas/assistant.py` (the A3.1 KEEP mirror of `models.dart`) is frozen:
no field is renamed/removed/retyped while clients run. Other DTOs may evolve;
the assistant contract may not. Rationale: it is the one live wire contract
(`POST /v1/assistant/chat`).

---

## 6. Boundary cases and clarifications

These edges are common sources of confusion; the rule is stated to remove
ambiguity.

| Edge | Allowed? | Resolution |
| --- | --- | --- |
| `api/schemas` importing `domain/models` | ✅ | DTOs project **from** canonical models (read-only); they never mutate domain state. |
| `domain/services` importing `domain/models` | ✅ | Same layer, inward. |
| `domain/services` calling `AIProvider` port | ✅ | Via the **interface** from `ports/external.py`; the concrete adapter is injected. |
| `application` reading env for a feature gate | ✅ | Via `config` (allowed), not via `os.environ` inline; domain never does. |
| `infrastructure/repositories` returning ORM rows to the API | ❌ | Must return **domain models**; API maps domain → DTO (F-6). |
| `infrastructure/external/knowledge.py` imported by assistant feature directly | ❌ | Only through `domain/ports` (DR-6/F-10). |
| `api/v1/assistant.py` importing `domain/services/engine.py` directly | ❌ | Routers call the **application** use case (`application/assistant.py`), which runs the engine (DR-1). |
| Domain throwing an HTTP error | ❌ | Domain raises **domain exceptions**; `api/errors.py` maps them to HTTP (F-3, A3.3/E13.1). |

---

## 7. Enforcement (how the rules are checked)

Design-only now; these are the mechanisms that will apply from M1 onward:

1. **Import-linter / layer enforcement** — a CI check (e.g. `import-linter`)
   asserting the layer contracts:
   - `api` may import `application`, `api`, `domain` (allowed subset), `config`.
   - `application` may import `domain`, `config`.
   - `domain` may import nothing outside `domain` (stdlib-only).
   - `infrastructure` may import `domain`, `config`.
   - Contract violations = CI failure (F-1…F-13 are expressible as layer +
     forbidden-import rules).
2. **Code review checklist** — the F-1…F-13 catalogue is the review checklist;
   a PR touching `domain/` with a framework import is auto-rejected.
3. **Composition root rule** — `main.py` is the only file that may reference
   both `application` and `infrastructure` (DI wiring). No other file may.
4. **Frozen-contract guard** — a unit test asserting the serialized shape of
   `AssistantReply` stays stable (F-13).

---

## 8. Open decisions (unchanged, carried forward)

None of the decisions below changes the dependency rules; they only change
which file implements a port:

1. **Auth provider** — affects `api/deps.py` + M1; not the API→Application edge.
2. **AI provider** — affects `infrastructure/external/ai.py` only (DR-5 holds).
3. **`user_state` shape** — affects M2 repository only.
4. **Knowledge seeding source** — affects `infrastructure/external/knowledge.py`
   only (DR-6 holds).
5. **Media gate MS10.3** — gates `external/object_storage.py`; DR-3 applies when
   it lifts.
6. **Billing provider** — affects the M15 webhook adapter only.
7. **Migration tooling** — Alembic vs plain SQL for `db/migrations/`; DR-4
   holds either way.

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `DEPENDENCY_RULES.md` — the explicit,
enforceable dependency contract (DR-0…DR-6 allowed edges; F-1…F-13 forbidden
set; boundary clarifications; enforcement mechanisms). No implementation.

**Skills used:** repository analysis (architecture rules, folder structure,
module map, domain model) — architecture documentation only.

**Files changed:** `docs/backend/DEPENDENCY_RULES.md` (new).

**Validation run:**
- Cross-checked DR-0…DR-6 against `BACKEND_ARCHITECTURE_RULES.md` §5 rules 1–6
  and `BACKEND_FOLDER_STRUCTURE.md` §5 import matrix; confirmed no conflict.
- Confirmed each forbidden rule (F-1…F-13) maps to an accepted rule
  (BA-2/3/5/6/8/10/14, TRX-1…TRX-8, BAR-0) or a live-contract constraint (A3.1).
- `git status --short`: no code, directories, or files created/changed beyond
  this document (see below).
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- Next implementation step (per `BACKEND_ARCHITECTURE_RULES.md` §9 M1): create
  the folder skeleton + move engine/intent/tools/catalog/schemas into target
  folders **without behavior change**, keeping `POST /v1/assistant/chat` and
  the 19 existing tests green — the first place these rules are enforced.
- Introduce import-linter config in CI at M1/M2 (this document is the spec for
  that config).
- No `DECISIONS.md` entry needed: no accepted architectural decision was made
  in this step (documentation only); open items remain in §8.

**Assumptions recorded:**
- "Domain" = `app/domain/` in `BACKEND_FOLDER_STRUCTURE.md`; rules reference
  that layout, which is already accepted.
- Forbidden rules are stated as **merge-blocking invariants**; enforcement is
  expected to be automated at M1+, not manual.
- The rules intentionally add no new concept not already present in the
  accepted architecture docs — this document is a consolidation + the missing
  forbidden-catalogue, not a new design.

**Constraints honored:** BAR-0 (domain-model-driven; UI never enters domain;
assistant DTOs frozen), BA-2/3/5/6/8/10/14 (layers, purity, no cycles, ports,
AI confinement, repository-only data path, minimal transactions), the UI
Change Safety Rule (no UI touched), and the Scope rule (this document only).
