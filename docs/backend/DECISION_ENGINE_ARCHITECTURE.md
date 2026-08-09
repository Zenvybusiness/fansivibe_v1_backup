# Fansivibe — Decision Engine Architecture

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Defines the architecture of the
> Fansivibe **Decision Engine** (module M6 `ai_engine`): the domain-layer
> component that sits **between application services and AI/knowledge
> capabilities**, producing every recommendation, analysis, and assistant
> reply in the system.
>
> The engine is designed as a **pipeline of small, single-responsibility
> stages** — **not a giant class**:
>
> ```
> INPUT
>   ↓
> Context Builder
>   ↓
> Candidate Generation
>   ↓
> Filtering
>   ↓
> Scoring
>   ↓
> Ranking
>   ↓
> Explanation
>   ↓
> Recommendation
>   ↓
> Feedback  ─────────────┐
>       ↑                │
>       └────────────────┘  (feedback flows back into context)
> ```
>
> **Status: architecture design only. The engine is NOT implemented.** No
> code, files, or directories are created; the existing live assistant
> contract (`POST /v1/assistant/chat`) is unchanged.
>
> **Source of truth:** the real Fansivibe repository — the working rules
> engine today (`backend/app/ai/engine.py`, `intent.py`, `tools.py`,
> `llm_backend.py`, `data/catalog.py`) is the seed this architecture
> generalizes, and the accepted STEP 5 docs (`BACKEND_ARCHITECTURE_RULES.md`
> BA-3/BA-6/BA-8, `BACKEND_FOLDER_STRUCTURE.md` §6.6, `BACKEND_MODULE_MAP.md`
> M6, `DEPENDENCY_RULES.md` DR-5/F-7, `APPLICATION_USE_CASES.md`) constrain
> the design.

---

## 1. Purpose and scope

This document defines:

1. **Where the Decision Engine sits** — between application services (callers)
   and AI/knowledge capabilities (sources), never in between or beyond them.
2. **The pipeline** — the canonical stage sequence every decision flows
   through (input → context → candidates → filter → score → rank → explain →
   recommend → feedback).
3. **What each stage does** — responsibility, input, output, and what it is
   forbidden from doing.
4. **The role catalogue** — how each input type (user profile, preferences,
   appearance profile, wardrobe, occasion, weather, knowledge, AI model
   output, business rules, user feedback) enters the pipeline and what it is
   allowed to influence.
5. **The decomposition** — how the engine is split into small modules/classes
   so it never becomes a monolith class.

It does **not** define code, function signatures, or the exact DTO shapes
(those are `api/schemas`, and the assistant DTOs are the frozen A3.1 mirror).

**Grounding facts (BAR-0):** the engine produces **AI/derived output that is
never a source of truth** — recommendations, analyses, and today's look are
regenerable; only user saves and history rows persist (TRX-2/TRX-4). The
engine is **pure domain** (BA-3): no I/O, no FastAPI, no SQLAlchemy, no
provider SDKs; it depends on ports (`ports/external.py`) that the
application/infrastructure layers inject.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `backend/app/ai/engine.py`, `intent.py`, `tools.py` | The working rules engine — today's flow is `classify → tools → dialogue → optional LLM text enrichment`. This architecture generalizes it into stages. |
| `backend/app/ai/llm_backend.py`, `data/catalog.py` | The `AIProvider` (optional, degrades) and `KnowledgeSource` (K9.1) seeds. |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | Entities/value objects (StyleProfile, FaceProfile, WardrobeItem, UserEvent, Look, Today'sLook, AssistantUserContext) the engine consumes. |
| `BACKEND_ARCHITECTURE_RULES.md` | BA-3 (pure domain), BA-6 (external via ports), BA-8 (AI only via engine). |
| `BACKEND_MODULE_MAP.md` | M6 `ai_engine` — domain-only module, no API/router/repo; owns intent/tools/dialogue + generation + analysis rules + `AIProvider`/`KnowledgeSource` ports. |
| `BACKEND_FOLDER_STRUCTURE.md` | `domain/services/` files (engine, intent, tools, recommendations, analysis_rules) + `domain/ports/external.py`. |
| `DEPENDENCY_RULES.md` | DR-5 (AI adapters → AI interfaces), F-7 (provider-specific code never leaks), F-3 (domain has no HTTP). |
| `APPLICATION_USE_CASES.md` | The callers: UC-22 assistant, UC-16 daily outfit, UC-21/28/29 outfit generation, UC-24…27 analysis, UC-31 discover ordering. |
| `TRANSACTION_BOUNDARIES.md` | Engine output is computation (§5): never inside a transaction; only a persisted snapshot (save/show) is a write. |

---

## 3. Position of the engine

The Decision Engine is a **domain service** invoked by **application
services**; it reaches **AI and knowledge** only through **ports**. It does
not talk to the API layer, Flutter, or PostgreSQL directly.

```
┌──────────────┐   POST /v1/assistant/chat, /outfits/generate, /analysis/*, …
│  app/api     │  routers (validate, auth dep → user_id)
└──────┬───────┘
       │ calls exactly one use case (DR-1)
┌──────▼───────┐
│  application │  UC-22/16/21/24…/31  (loads state via ports, TRX boundary)
└──────┬───────┘
       │ injects ports (repositories, providers)
┌──────▼──────────────────────────────────────────────┐
│                DECISION ENGINE (M6)                 │
│   domain/services: pipeline of stages               │
│   INPUT ─ ContextBuilder ─ CandidateGen ─ Filter ─  │
│   Score ─ Rank ─ Explain ─ Recommend ─ Feedback     │
└──────┬─────────────────────────────┬────────────────┘
       │ depends on ports only       │ depends on ports only
┌──────▼─────────┐           ┌───────▼──────────────────┐
│ KnowledgeSource│           │ AIProvider (+ Weather,   │
│ (K9.1 catalog) │           │  storage via M16)        │
└────────────────┘           └──────────────────────────┘
   (infrastructure/external/knowledge.py)   (infrastructure/external/ai.py)
```

**Rules that pin the position:**

- **Callers are application services, never routers** (DR-1): a router calls
  `application/assistant.py`, which runs the engine; it never imports
  `domain/services/engine.py`.
- **The engine reaches AI only through `AIProvider`** (BA-8): the concrete
  adapter (`infrastructure/external/ai.py`) is injected; the engine sees only
  the interface. Swapping/disabling the LLM is a one-file change and the
  rules-only path always works (today's graceful degradation is preserved).
- **The engine reads knowledge only through `KnowledgeSource`** (K9.1, BA-11):
  no hardcoded vocabulary anywhere else.
- **The engine never persists** (TRX-4/TRX-7): output is regenerable; saving
  is the application layer's job (UC-15/UC-30).

---

## 4. The pipeline

Every decision (assistant reply, outfit, today's look, hairstyle/grooming/
outfit analysis, discover ordering) flows through the same stage sequence.
Stages are **pluggable and per-task**: a task may use only the stages it
needs (e.g. discover ordering uses filter→score→rank, no generation; analysis
uses generate→score→explain, no dialogue). The pipeline is a **composition
of small stages**, not a giant method.

```
 INPUT ──► ContextBuilder ──► CandidateGeneration ──► Filtering
            │                       │                     │
            │  (enriched context)    ▼                     ▼
            │                   Scoring ◄────── business rules
            │                       │
            │                       ▼
            │                   Ranking
            │                       │
            │                       ▼
            │                   Explanation
            │                       │
            │                       ▼
            └────────────────► Recommendation ──► OUTPUT
                                   │
                                   ▼
                              Feedback ─────────────► (into ContextBuilder)
```

| Stage | Question it answers | Typical task mapping |
| --- | --- | --- |
| 1. Context Builder | "What does the engine know?" | assistant, today's look, outfit, analysis, discover |
| 2. Candidate Generation | "What are the options?" | all except pure discover ordering |
| 3. Filtering | "What must be excluded?" | all |
| 4. Scoring | "How well does each fit?" | all |
| 5. Ranking | "What order?" | all |
| 6. Explanation | "Why this one?" | all |
| 7. Recommendation | "What is the deliverable?" | all |
| 8. Feedback | "Did it help?" | assistant, save, discover |

---

## 5. Stage definitions

For each stage: **responsibility**, **input**, **output**, **forbidden from**.

### 5.1 Stage 1 — Context Builder

- **Responsibility:** assemble the **typed decision context** from the input
  (the task's request + `user_id`) by reading domain state through ports. It
  decides *what is relevant* to this task and *what is stale/excluded*.
- **Input:** raw task input (message text, preferences, event id, image ref)
  + `user_id`.
- **Output:** an immutable **`DecisionContext`** value object — the single
  object all later stages read. It bundles: `user_profile` (identity/name),
  `preferences`, `appearance_profile` (StyleProfile/FaceProfile), `wardrobe`
  (owned items), `occasion`, `weather_hint`, `knowledge_snapshot` (relevant
  catalog subset), `history` (recent signals/looks).
- **Forbidden from:** decision logic, calling the AI provider, persisting,
  returning more than the task needs. It is the *only* stage that touches
  repositories (via ports).

**Mapping to today:** `_context_summary()` (`engine.py`) and the client-sent
`UserContext` are the seed; tomorrow the context is loaded from repositories
(UC-22 note: "today client-sent, unchanged; future repository-loaded").

### 5.2 Stage 2 — Candidate Generation

- **Responsibility:** produce the **candidate set** — the possible options for
  this decision (looks, outfits, hairstyles, grooming styles, analysis
  attributes). Uses knowledge (catalog) and, where appropriate, AI model
  output; always validated against the controlled vocabulary.
- **Input:** `DecisionContext`.
- **Output:** `List[Candidate]` — unranked options with their base
  attributes. A candidate for a look is grounded in `Look` catalog rows; for
  an outfit, a combination of owned items; for analysis, detected attributes.
- **Forbidden from:** filtering, scoring, ranking, dialogue policy. It must
  never narrow the set itself (filtering is its own stage).

**Mapping to today:** `tools.recommend_outfit/hairstyle/grooming` are the
seed — but today they *both generate and select*. This architecture splits
selection into the ranking stages.

### 5.3 Stage 3 — Filtering

- **Responsibility:** remove candidates that **must not** be shown: violates a
  business rule (e.g. item not owned for an outfit builder, occasion mismatch,
  season/weather conflict, size/color mismatch, deprecated content, privacy
  exclusion).
- **Input:** `List[Candidate]` + `DecisionContext`.
- **Output:** a reduced `List[Candidate]` (possibly empty).
- **Forbidden from:** assigning scores or reordering; it is binary
  (keep/drop) and deterministic (BA-3).

### 5.4 Stage 4 — Scoring

- **Responsibility:** assign a **match score** to each surviving candidate —
  how well it fits the user's profile, preferences, wardrobe, and occasion.
  Scoring is a **composition of weighted signals**; weights come from business
  rules (config-driven), never hardcoded per-feature.
- **Input:** filtered candidates + context + scoring weights.
- **Output:** candidates each with a numeric `score` (and per-signal
  breakdown for explanation).
- **Forbidden from:** deciding the final order (ranking does), generating
  candidates, calling the AI provider per-candidate (score computation is
  deterministic; AI enrichment is a separate, text-only stage).

**Mapping to today:** `recommend_outfit`'s "prefer the look with the most
owned items" and `recommend_hairstyle`'s face-shape switch are the first
scoring signals.

### 5.5 Stage 5 — Ranking

- **Responsibility:** order scored candidates into the **final list**
  (top pick first). May apply task-specific policies (variety/seed for
  regeneration, "don't repeat the last pick", personalization from learning
  signals).
- **Input:** scored candidates + context + ranking policy.
- **Output:** ordered `List[ScoredCandidate]`; the first is the primary
  recommendation.
- **Forbidden from:** re-scoring, changing scores, or filtering. It only
  orders.

### 5.6 Stage 6 — Explanation

- **Responsibility:** produce the **human reasons** for the top picks —
  "why this suits you", the `aiSelectionReason`/`matchScore` text the UI
  renders. Always grounded in the score signals (or a chosen reason from a
  validated reason catalog), so explanations are truthful and never invented.
- **Input:** ranked candidates + their score breakdown + context.
- **Output:** per-candidate `Explanation` (title + reasons + CTA text).
- **Forbidden from:** generating new candidates or claiming knowledge it
  doesn't have. If the LLM enriches wording, it enriches **only text**, never
  structure or scores (BA-8, today's `llm_backend.enrich_reply`).

### 5.7 Stage 7 — Recommendation

- **Responsibility:** assemble the **typed deliverable** — the DTO-shaped
  result the caller maps to the API response: `AssistantReply` (cards,
  clarifications, navigation), `OutfitRecommendation`, `TodayLook`,
  `AnalysisResult`, or ordered look feed. It maps domain candidates → the
  task's output contract. For the assistant this is the **frozen A3.1 shape**.
- **Input:** ranked + explained candidates + task output spec.
- **Output:** the typed recommendation/result value object.
- **Forbidden from:** re-running the pipeline, persisting, or constructing
  HTTP/flutter-specific content beyond the DTO contract.

### 5.8 Stage 8 — Feedback

- **Responsibility:** accept **user feedback** on a delivered recommendation —
  save, open, rate, dismiss — and feed it back into the engine's context so
  future decisions adapt (feedback is an input to Context Builder, closing
  the loop). It translates feedback into typed **learning signals** (via the
  application layer; the engine defines the signal shape, never writes rows).
- **Input:** feedback event (card interaction, save, rating, dismiss).
- **Output:** a validated `FeedbackEvent`/signal descriptor for the
  application layer to persist (UC-23, UC-32).
- **Forbidden from:** writing history itself (TRX-3 persists it in the
  application layer), over-correcting (single feedback never flips a hard
  rule), or storing raw user comments inside the engine.

---

## 6. Role catalogue — what each input may influence

| Input | Stage it enters | Role / influence | Never allowed to |
| --- | --- | --- | --- |
| **User profile** (E1 identity, name, style DNA) | Context Builder → used in Scoring/Explanation | Seed identity for personalization and display; style DNA informs base scores. | Override explicit user choices; be exposed raw in API output beyond DTO. |
| **Preferences** (E1.1 `UserPreferences` JSONB) | Context Builder → Filtering + Scoring | Hard constraints (Filtering) and soft weights (Scoring) — e.g. color palette preference filters or boosts candidates. | Be ignored once stated; be overridden by AI model output. |
| **Appearance profile** (`StyleProfile`/`FaceProfile`) | Context Builder → Scoring | Face shape/skin tone/body type drive hairstyle/grooming scores (today's face-shape switch); style type steers look choice. | Be fabricated by the engine if absent — absence means "neutral/default", never a guess. |
| **Wardrobe** (E2 owned items) | Context Builder → Filtering + Scoring | Outfit builder filters to owned items; match scores reward "uses items you own" (today's `_owned` signal). | Be treated as exhaustive knowledge; empty wardrobe → candidates from knowledge, not nothing. |
| **Occasion** (from message / event type / preference) | Context Builder → Filtering + Scoring | Hard constraint on look/outfit (event type, detected occasion) and a scoring signal (occasion-to-look map, today's `OCCASION_TO_LOOK`). | Be fabricated — if absent the engine asks (clarification policy), it does not guess. |
| **Weather** (external `WeatherProvider` hint) | Context Builder → Filtering (optional) | Advisory filter (e.g. "rain → recommend a jacket); **never authoritative** — a hint inside rules only. | Block a recommendation outright on its own; fail the pipeline if unavailable (degrades to no-hint). |
| **Knowledge** (E5 `Look` + vocabularies, K9.1) | Context Builder → Candidate Generation | The source of all candidates and controlled vocabulary; categories/colors/occasions are always validated against it. | Be bypassed by hardcoded per-feature lists (BA-11); be mutated by engine output. |
| **AI model output** (`AIProvider`) | Candidate Generation (optional) + Explanation (text only) | May enrich generation (new candidates from model, still validated against vocabulary) and **rewrite explanation wording** only. Structure, scores, and typed output are always the engine's (BA-8). | Decide final rank, set scores, change DTO shape, block the rules-only path when unavailable, leak provider names (F-7). |
| **Business rules** (config-driven weights, limits, policies) | Filtering + Scoring + Ranking | Enforce invariants (item-ownership, season, occasion match), supply scoring weights, apply ranking policy (variety/seed). Config-driven, not hardcoded in features. | Be overridden by AI output; be scattered across features (single rules source). |
| **User feedback** (signals: saved, opened, rated) | Feedback → Context Builder (next run) | Personalization: repeated "saved/dismissed" patterns adjust scores and ranking (via learning signals). | Flip a hard business rule instantly; be persisted by the engine itself. |

**Principle (DE-0):** *deterministic rules decide; AI enriches text and may
suggest candidates; user feedback tunes; business rules bound.* Each input
has an explicit, bounded influence (the table above) and none can hijack the
pipeline.

---

## 7. Decomposition — never a giant class

The engine is **one thin orchestrator + many small, stateless stages**. The
orchestrator (`Pipeline`) knows *the order* but implements *no* logic; every
stage is a small class/function with a single responsibility. This mirrors
and extends the accepted `domain/services/` layout:

```
app/domain/services/                     # M6 ai_engine (module map §5)
├── engine.py            # thin orchestrator: composes stages per task (moved from app/ai)
├── pipeline.py          # DECISION-ENGINE pipeline definition + stage registry
├── intent.py            # intent classification (moved from app/ai) — stage 0 filter
├── context.py           # ContextBuilder → DecisionContext          (stage 1)
├── tools.py             # candidate generation tools (moved from app/ai) (stage 2)
├── filters.py           # Filtering: hard rules (ownership, occasion, season) (stage 3)
├── scoring.py           # Scoring: weighted signal composition         (stage 4)
├── ranking.py           # Ranking: order + variety/seed policy         (stage 5)
├── explanation.py       # Explanation: truthful reasons from scores    (stage 6)
├── recommendations.py   # Recommendation: typed deliverable assembly   (stage 7, M6/M13)
├── feedback.py          # Feedback: feedback → typed signal shape      (stage 8)
├── analysis_rules.py    # outfit/hairstyle/grooming run rules (M12) — reuses stages
├── business_rules.py    # config-driven weights/limits/policies (single source)
└── ports/external.py    # AIProvider, KnowledgeSource, WeatherProvider (BA-6)
```

**Why this is not a giant class:**

- **The orchestrator has no logic.** `Pipeline.run(task, context)` only
  calls stages in order; adding a stage (e.g. a new filter) is adding a small
  file, not editing a god method.
- **Stages are pure and stateless.** Each takes typed input → typed output,
  no hidden state, no I/O → trivially unit-testable (like today's
  `test_engine.py`/`test_intent.py`, which keep passing because behavior
  doesn't change).
- **Per-task composition.** Assistant (UC-22), outfit (UC-28/29), today's look
  (UC-16), analysis (UC-24…27), and discover (UC-31) each define *which*
  stages they use, reusing the same small stages instead of each having its
  own code path.
- **Config-driven business rules** (`business_rules.py`) keep weights and
  limits out of both stages and features (single source, no hardcoding).

**Stage ↔ today's code mapping (M1 seed):** `engine.py` (dialogue policy →
stage 0 + orchestration), `intent.py` (→ intent stage), `tools.py`
(recommend_* → candidate generation + first scoring signals), `llm_backend.py`
(→ `AIProvider` port, text-only enrichment), `catalog.py` (→
`KnowledgeSource` port). No behavior changes in M1 — the pipeline is
introduced **after** the folder skeleton (M2+), stage by stage, keeping
`POST /v1/assistant/chat` and the 19 tests green.

---

## 8. Two operating modes (preserved from today)

The engine always runs **rules-first**; AI is additive:

| Mode | When | What AI contributes | Guarantee |
| --- | --- | --- | --- |
| **Rules-only** (default, deterministic) | Always works; no provider configured | Nothing — full pipeline in `domain/services` | Typed output, reproducible, offline-testable (BA-3). Today's behavior. |
| **LLM-enriched** | Provider available (`FANSIVIBE_OLLAMA_HOST` set) | New candidate *suggestions* (validated against vocabulary) + explanation **wording** only | Structure, scores, ranks, DTO shape never change (BA-8, F-13). Degrades to rules-only on failure. |

This preserves the current `llm_backend.is_available()` / `enrich_reply`
behavior and the offline fallback (ACTION_API #25).

---

## 9. Cross-cutting constraints

- **Pure domain (BA-3, F-1…F-4):** no FastAPI, SQLAlchemy, HTTP, env reads,
  or config imports in the engine. Settings/weights are injected via the
  `DecisionContext` or business rules.
- **Output is never truth (BAR-0):** nothing the engine computes is
  persisted as authoritative; the application layer persists only user saves
  and snapshots (TRX-2/TRX-4).
- **AI confined (BA-8, F-7):** the engine holds the *interface* to
  `AIProvider`; only `infrastructure/external/ai.py` knows a provider exists.
- **Validated structured output:** every stage's output is typed and
  validated against the controlled vocabulary before it reaches the next
  stage (A3.3 — invalid candidates are filtered, never surfaced).
- **No engine I/O:** all reads go through ports injected by the application
  layer; the engine never opens a session or calls out (F-3).

---

## 10. Report, assumptions, constraints

**What changed (this step):** added `DECISION_ENGINE_ARCHITECTURE.md` — the
pipeline-based architecture of the Decision Engine (M6). No implementation.

**Skills used:** repository analysis (current `app/ai/engine.py`, `intent.py`,
`tools.py`, `llm_backend.py`, `catalog.py`; domain model; STEP 5 module map,
folder structure, dependency rules, use cases) — architecture documentation
only.

**Files changed:** `docs/backend/DECISION_ENGINE_ARCHITECTURE.md` (new).

**Validation run:**
- Mapped every pipeline stage to today's working code (`engine.py`,
  `intent.py`, `tools.py`, `llm_backend.py`) and to the accepted
  `domain/services/` file list — no conflicts, M1-safe (no behavior change).
- Verified every role in §6 maps to a domain-model concept (E1/E1.1/E2/E3/E5)
  or an accepted port (AIProvider/KnowledgeSource/WeatherProvider).
- Verified the position diagram against BA-6/BA-8 and DR-1 (routers never
  call the engine directly).
- `git status --short`: only this new doc + `CURRENT_STATE.md` update; no
  code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- Next implementation steps per `BACKEND_ARCHITECTURE_RULES.md` §9: M1 folder
  skeleton (engine/intent/tools/catalog/schemas move intact), M2 typed
  errors, then introduce the pipeline **stage by stage** (context first, then
  split filtering/scoring/ranking/explanation out of today's `tools.py`),
  always keeping `POST /v1/assistant/chat` and the 19 tests green.
- The `DecisionContext` and `business_rules` config shapes are design
  targets; exact fields/weights are decided at implementation, not now.
- No `DECISIONS.md` entry needed: no accepted architectural decision made
  (documentation only); open items remain in §8 of `BACKEND_ARCHITECTURE_RULES.md`.

**Assumptions recorded:**
- "Decision Engine" = module M6 `ai_engine` (`domain/services`), consistent
  with the module map and folder structure.
- The pipeline is a design generalization of the *working* rules engine — it
  does not invent new product behavior; it organizes existing behavior into
  stages.
- Stages are per-task composable; not every task uses all eight stages.
- Weather is always a non-authoritative hint (matches `WeatherProvider` port
  design); absence degrades gracefully.

**Constraints honored:** BAR-0 (AI output never truth; assistant DTOs frozen
A3.1), BA-3 (pure domain), BA-6/BA-8 (external via ports; AI only via the
engine), BA-11 (single knowledge source), DR-1/DR-5/F-7 (callers and AI
confinement), the UI Change Safety Rule (no UI touched), and the Scope rule
(this document only).
