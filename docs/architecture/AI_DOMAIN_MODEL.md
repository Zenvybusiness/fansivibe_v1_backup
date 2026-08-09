# Fansivibe — AI Domain Model

> **STEP 3 (continuation) — DOMAIN MODEL DESIGN.** Defines the domain model
> around Fansivibe's AI system: what an analysis is, what a recommendation is,
> what explains it, how confident it is, how the user reacts, and how all of it
> feeds future learning — **before** any real model or database exists.
>
> **Source of truth:** the real repository
> (`newproject/flutter_application_1` + `backend/`), the 12 STEP 2 inventory
> documents (especially `AI_DATA_FLOW.md`, `DATA_OWNERSHIP.md`,
> `STORAGE_INVENTORY.md`, `DATA_MODEL_INVENTORY.md`), and the STEP 3 companions
> (`DOMAIN_MODEL_RULES.md`, `DOMAIN_ENTITIES.md`, `DOMAIN_RELATIONSHIPS.md`,
> `DOMAIN_STATE_AND_HISTORY.md`).
>
> **Status:** documentation only. **No AI is implemented; no database tables are
> created.** This model classifies the concepts the future AI pipeline and the
> Step 4 schema will build on.

---

## 1. The pipeline this model must support

The task states the model must support exactly this chain:

```
User data   +   AI analysis   +   Knowledge   +   Decision
      →  Recommendation  →  Explanation  →  User feedback  →  Future learning
```

Each link maps to a concept in this document:

| Pipeline link | Concept(s) here | Notes |
| --- | --- | --- |
| User data | E1–E5 current state (`Wardrobe`, `StyleProfile`/`FaceProfile`, `SavedLook`, `UserEvent`, preferences) | Already defined in `DOMAIN_ENTITIES.md`; referenced here, not redefined |
| AI analysis | **AI Analysis** (run = historical, result = value) | `AnalysisRun` E6 + result snapshot |
| Knowledge | `Look` catalog, vocabularies | SYSTEM CONFIGURATION / system knowledge |
| Decision | **AI Decision Context** (derived snapshot + intent/policy) | `AssistantUserContext` today |
| Recommendation | **AI Recommendation** (value) | outfit / hairstyle / grooming / look |
| Explanation | **Recommendation Reason** (+ **Recommendation Confidence**) | value objects |
| User feedback | **Recommendation Feedback** (historical, future) | feeds learning |
| Future learning | **User Preference Signal** + **RecommendationHistory** | append-only training evidence |

Two system-wide concepts hold the pipeline together: **AI Capability**
(which analyses/recommendations can run) and **AI Model Version** (what produced
a result, so history stays reproducible).

**Verified headline (from `AI_DATA_FLOW.md`):** today the *only* AI-like
behavior that runs is the **Assistant** rules pipeline (backend `engine.py` +
on-device mirror + optional Ollama text enrichment). Every other AI output —
outfit scan, outfit builder, hairstyle, grooming, discover matching, today's
look, wardrobe insight, style DNA, style score — is **MOCKED** static data. This
model is the *target* the product will grow into; each concept below states its
status today.

---

## 2. Classification legend

Each concept is classified into exactly one of the five task categories, with a
secondary note when it has two aspects. These five map onto the ten-category
taxonomy of `DOMAIN_MODEL_RULES.md` §1 as follows:

| This document's category | Corresponds to (DOMAIN_MODEL_RULES) |
| --- | --- |
| **ENTITY** | Domain entity (identity + lifecycle + durability) |
| **VALUE OBJECT** | Value object / AI output (immutable, interchangeable, embedded) |
| **HISTORICAL RECORD** | Historical record (append-only, immutable trace) |
| **DERIVED DATA** | Current profile state / user preference / derived value (recomputable) |
| **SYSTEM CONFIGURATION** | System knowledge (backend-owned reference content) |

Binding rules inherited from the companions:
- **AI output is never a source of truth** (`DOMAIN_MODEL_RULES.md` invariant 1;
  `DATA_OWNERSHIP.md` rule 3) — recommendations, reasons, confidence, and
  insights are regenerable value objects.
- **An AI *event* (run, shown recommendation, feedback) IS a historical fact**
  that must remain reproducible (`DOMAIN_STATE_AND_HISTORY.md` §6).
- **History is append-only; current state is a mutable projection with
  provenance** (`DOMAIN_STATE_AND_HISTORY.md` §1, §8).

---

## 3. The ten concepts — classification

| # | Concept | Primary classification | Secondary aspect | Status today |
| --- | --- | --- | --- | --- |
| 1 | **AI Analysis** (run) | **HISTORICAL RECORD** | Realized as entity `AnalysisRun` (E6) | No runs exist (all results mock / dead code) |
| — | AI Analysis (result snapshot) | **VALUE OBJECT** | AI output, embedded in the run | Mock only |
| 2 | **AI Recommendation** | **VALUE OBJECT** | AI output; occurrence = historical only via `RecommendationHistory` (P3) | Mock / assistant cards |
| 3 | **Recommendation Reason** | **VALUE OBJECT** | AI output; the explanation | Static reason lists |
| 4 | **Recommendation Confidence** | **VALUE OBJECT** | Derived/AI; optional | **Not computed** (scores are catalog constants) |
| 5 | **Recommendation Feedback** | **HISTORICAL RECORD** | Future feature; user event | **Feature missing** |
| 6 | **AI Capability** | **SYSTEM CONFIGURATION** | Effective availability = DERIVED DATA | Static `allCapabilities` (2-of-7 active, marketing copy) |
| 7 | **AI Model Version** | **SYSTEM CONFIGURATION** | Referenced (as an id) from runs/history | Rules engine only; optional Ollama `llama3.1:8b` |
| 8 | **User Preference Signal** | **HISTORICAL RECORD** | = `LearningSignal` E7; aggregated preference state = DERIVED DATA | 8 signal types persisted in `UserModel.signals` |
| 9 | **AI Decision Context** | **DERIVED DATA** | Per-request snapshot; serialized copy embedded in history for reproducibility | `AssistantUserContext` / backend `UserContext` |
| 10 | **AI-generated Insight** | **VALUE OBJECT** | Derived from wardrobe + knowledge | Mock (3 duplicate shapes) |

Every primary classification is justified below with STEP 2 evidence and its
place in the pipeline.

---

## 4. The ten concepts — detail

### 4.1 AI Analysis

- **Classification:** **HISTORICAL RECORD** (the run) + **VALUE OBJECT** (the
  result). The run is realized by the entity `AnalysisRun` (E6) — a per-execution
  linkage record (user, feature type, source `MediaRef`, timestamp, result
  snapshot, optional `SavedLook` link) — per `STORAGE_INVENTORY.md` §1.6 and
  `DOMAIN_ENTITIES.md` E6.
- **Covers:** outfit scan, hairstyle, grooming, and future onboarding face
  analysis (`AI_DATA_FLOW.md` B1/B3/B4/B9; dead `AnalysisResult`/`OnboardingResult`).
- **Immutable / append-only:** yes — a new analysis creates a new run; nothing
  mutates an old one (`DOMAIN_STATE_AND_HISTORY.md` §5.1–5.3, §5.6).
- **Reproducible:** previous results stay reproducible by keeping inputs
  (`MediaRef`) + the immutable result snapshot + the engine/model version
  (R-A14).
- **Relationship to profile:** the *accepted* attributes update
  `StyleProfile.FaceProfile` as a mutable projection with `source_run_id`
  provenance (R-A2) — never an overwrite of the run.
- **Today:** no runs exist; every result is a static mock
  (`AI_DATA_FLOW.md` headline).

### 4.2 AI Recommendation

- **Classification:** **VALUE OBJECT** (AI output). An outfit, hairstyle,
  grooming, or discover-look recommendation is a composite value: a reference to
  `Look` knowledge (or a generated ensemble), a match score, reasons, confidence,
  and alternatives (`OutfitRecommendation`, `HairstyleRecommendation`,
  `GroomingRecommendation`, `MatchScoreDetails` families — `AI_DATA_FLOW.md`
  B2/B3/B4/B5). Never stored as truth (`DATA_OWNERSHIP.md` rule 3).
- **Occurrence as history:** the *event of recommending* is historical only if
  `RecommendationHistory` (P3, `RecommendationHistory` conditional entity) is
  built — an immutable trace referencing `Look` + snapshot + score
  (`DOMAIN_STATE_AND_HISTORY.md` §5.7).
- **Regenerable:** yes — from user data + knowledge; the exact previously-shown
  result is reproducible only with a snapshot.
- **Today:** builder/scan recommendations are mock; assistant suggestion cards
  are the one implemented (rules-based) form.

### 4.3 Recommendation Reason

- **Classification:** **VALUE OBJECT** (AI output). `RecommendationReason` /
  `reasons[]` — the *explanation* attached to a recommendation
  (`DOMAIN_RELATIONSHIPS.md` R26, 4.11; `DATA_MODEL_INVENTORY.md` §6, §8).
- **Purpose:** explainable output (PRODUCT_BLUEPRINT "explainable"); the reason
  travels *with* the recommendation and is regenerated with it.
- **Immutable:** yes, as a value; it is regenerated whole, never edited in place.
- **Today:** static reason lists / reply prose; the assistant DTO has **no
  structured reason field** (`AI_DATA_FLOW.md` Part D.4) — reasons are baked into
  reply text.

### 4.4 Recommendation Confidence

- **Classification:** **VALUE OBJECT** (derived/AI, optional). A numeric
  confidence (value + scope, e.g. fit/color/occasion) attached to a
  recommendation, plus a reference to the version that produced it so it can be
  interpreted.
- **Crucially: no confidence is computed or transmitted today.** Card scores
  (91/94/0.92…) are **catalog constants**, and mock scores are baked doubles —
  they are *not* confidence (`AI_DATA_FLOW.md` Part D.3). The assistant DTO has
  no confidence field.
- **Design position:** when real scoring lands, confidence is a derived value of
  the model run — never stored as truth, but **snapshotted into any history**
  record that must remain reproducible.
- **Optional:** a recommendation may omit confidence (the assistant does today).

### 4.5 Recommendation Feedback

- **Classification:** **HISTORICAL RECORD** (future). A user's reaction to a
  recommendation (rating/like/dislike/useful) — an **append-only, immutable
  user event** that links the recommendation (or its source `Look`/`AnalysisRun`)
  to the reaction (`DOMAIN_RELATIONSHIPS.md` R27, 4.12).
- **Status:** **the feature does not exist today** — no rating/feedback UI
  anywhere (verified; `UI_UX_GAP_REPORT.md` #17; `ACTION_API_INVENTORY.md` #31).
- **Role:** the explicit learning signal that closes the loop
  recommendation → feedback → preference (R-A10). It is the *event*; the derived
  change in user preference is separate DERIVED DATA.
- **Not mutable, not derived:** a raw user event; nothing recomputes it.

### 4.6 AI Capability

- **Classification:** **SYSTEM CONFIGURATION**. `AiCapability`/`allCapabilities`
  (`onboarding_data.dart:79`) — the static list of what the product claims it can
  do (Face Analysis, Hairstyle Profile, Color Analysis, Wardrobe Intelligence,
  Grooming Profile, Event Styling, Shopping Assistant).
- **Status:** **no per-user capability state exists.** 2 of 7 are marked `active`
  (Face Analysis, Color Analysis) — **marketing copy with no computation behind
  them** (`AI_DATA_FLOW.md` Part D.1). "2 of 7 capabilities active" is a static
  label (`your_analysis_screen.dart:289`).
- **Effective availability (DERIVED DATA):** a user's *effective* capability set
  derives from config × subscription once entitlement exists
  (`DOMAIN_RELATIONSHIPS.md` R45/R46, 4.15). Do **not** model per-user
  capability rows or "progress" until a real capability system lands
  (`MVP_SCOPE.md` P3; `DOMAIN_STATE_AND_HISTORY.md` §5.11).
- **Role:** gates which AI analyses/recommendations can run (R-A15); it is
  config the pipeline reads, never data the pipeline writes.

### 4.7 AI Model Version

- **Classification:** **SYSTEM CONFIGURATION** (a version registry), referenced
  as an id from historical records. Each entry identifies an AI capability's
  model/provider/version (e.g. optional Ollama `llama3.1:8b` for assistant text
  enrichment — `llm_backend.py`, env `FANSIVIBE_OLLAMA_MODEL`/
  `FANSIVIBE_OLLAMA_HOST`, disabled via `FANSIVIBE_DISABLE_LLM=1`;
  `AI_DATA_FLOW.md` Part A).
- **Purpose:** **reproducibility and audit.** A run or recommendation history
  record references the model version that produced it, so a previous result can
  be re-interpreted or re-run (`DOMAIN_STATE_AND_HISTORY.md` §6).
- **Today:** the rules engine has "no model" (deterministic); only the optional
  LLM names a version. The registry concept exists so future models slot in
  without schema surprises.
- **Not user data, not history:** system-owned reference content, versioned and
  content-managed (`DOMAIN_MODEL_RULES.md` §2.7).

### 4.8 User Preference Signal

- **Classification:** **HISTORICAL RECORD** — this is `LearningSignal` (E7), the
  8-type append-only interaction trace (`item_added`, `analysis_updated`,
  `style_updated`, `look_saved`, `occasion_preferred`, `assistant_message`,
  `suggestion_opened`, `assistant_navigation`; `learning_service.dart` +
  assistant writes).
- **The derived side:** signals *aggregate into* the user's preference state —
  `preferredOccasions`, `styleType`, and the implicit style vector. That
  aggregated state is **DERIVED DATA** (current profile state), recomputable from
  signals + explicit choices; the signals themselves are never edited.
- **Role in the pipeline:** feedback and ordinary actions produce signals; the
  signals are the raw training/learning evidence ("future learning" in the
  pipeline). Signals also **feed** the next `AI Decision Context` through the
  derived preference state (R-A11/R-A20).
- **Immutable:** yes — the only true append-only history today
  (`DATA_OWNERSHIP.md` §`LearningSignal`).

### 4.9 AI Decision Context

- **Classification:** **DERIVED DATA** (primary). The per-request snapshot of
  the user's current state fed into the AI at decision time:
  `AssistantUserContext`/backend `UserContext` (wardrobe, face, savedLooks,
  preferredOccasions) — built fresh each request by
  `AssistantService._buildContext` (`assistant_service.dart:41`), never stored
  (`DATA_OWNERSHIP.md` §`AssistantUserContext`; `DOMAIN_MODEL_RULES.md` §2.9).
- **Secondary aspect (value object):** to keep AI history reproducible, the
  *serialized decision context* may be embedded in the run/history record — a
  frozen copy of what the AI actually saw when it decided
  (`DOMAIN_STATE_AND_HISTORY.md` §6).
- **Derived from:** user data (wardrobe, `StyleProfile`, saved looks, occasions)
  + the decision itself (intent/policy — the assistant's `intent.classify`/
  `detect_occasion` and dialogue policy, `engine.py`).
- **Immutable as a snapshot:** yes when frozen into history; ephemeral otherwise.

### 4.10 AI-generated Insight

- **Classification:** **VALUE OBJECT** (AI output). Insights are regenerable
  statements derived from wardrobe + knowledge: `AIWardrobeInsightData`,
  `WardrobeInsightData`, `AiInsightData` (3 duplicate shapes) and the backend
  `WARDROBE_INSIGHT` catalog (`AI_DATA_FLOW.md` B6/B7; `DATA_OWNERSHIP.md` §Home/
  §Wardrobe).
- **Never stored as truth:** current insight card = cache/derived display.
- **Reproducible:** yes, from durable inputs (wardrobe + knowledge); only
  snapshotted into history if the product needs an "insight archive".
- **Today:** static mock text with no link to actual wardrobe contents
  (`AI_DATA_FLOW.md` B7) — the only real rule exists in the assistant's
  `wardrobe_summary` tool ("consider a lightweight jacket").

---

## 5. Relationships between the AI concepts

Legend from `DOMAIN_RELATIONSHIPS.md` §1: **PRODUCES / DERIVED_FROM /
GENERATED_FROM / COMPOSITION / REFERENCE / FEEDS / GATES**, with 1:1 / 1:N /
N:M. `(future)` / `(P3)` = prospective; everything else is grounded in today's
behavior or a pending decision already recorded in STEP 2.

| # | Concept A | Relationship | Concept B | Cardinality | Note |
| --- | --- | --- | --- | --- | --- |
| R-A1 | AI Analysis run | **PRODUCES** (embedded) | AI Analysis result (value) | 1:0..1 | result written on completion; absent while pending/failed |
| R-A2 | AI Analysis run | **PRODUCES** → **DERIVED_FROM** | `StyleProfile.FaceProfile` (current state) | 1:1 latest | accepted attributes update the projection; `source_run_id` provenance |
| R-A3 | AI Analysis run | **REFERENCE** | AI Model Version | 0..1:1 | which model/engine produced the result |
| R-A4 | AI Analysis run | **REFERENCE** | `MediaRef` (source media) | 0..1:1 | the input evidence (scan image) |
| R-A5 | AI Recommendation | **DERIVED_FROM** | AI Decision Context + Knowledge (`Look`/vocab) + user data | 1:1 | regenerable from inputs |
| R-A6 | AI Recommendation | **COMPOSITION** | Recommendation Reason (value) | 1:1..N | explanation travels with it |
| R-A7 | AI Recommendation | **COMPOSITION** (optional) | Recommendation Confidence (value) | 1:0..1 | absent today; snapshotted if history kept |
| R-A8 | AI Recommendation | **REFERENCE** | `Look` (knowledge) | 1:1 | the catalog/generated source it points at |
| R-A9 | AI Recommendation | **REFERENCE** | AI Model Version | 0..1:1 | reproducibility trace |
| R-A10 | AI Recommendation | **recorded →** (P3) | RecommendationHistory (historical) | 1:0..1 | shown/saved occurrence as immutable trace |
| R-A11 | RecommendationHistory | **REFERENCE** | AI Decision Context (serialized snapshot) | 1:1 | frozen inputs for re-interpretation |
| R-A12 | RecommendationHistory | **REFERENCE** | AI Model Version | 1:0..1 | version that recommended |
| R-A13 | AI Recommendation / RecommendationHistory | **COMPOSITION** | Recommendation Feedback (historical) | 1:0..N | future: user reactions |
| R-A14 | Recommendation Feedback | **FEEDS** | User Preference Signal (LearningSignal) | 1:N | each reaction becomes learning evidence |
| R-A15 | User Preference Signal | **FEEDS → DERIVED_FROM** | derived preference state (`preferredOccasions`, `styleType`, style vector) | N:1 | aggregates; never edits signals |
| R-A16 | derived preference state | **DERIVED_FROM** | AI Decision Context | 1:1 per request | the next snapshot reads it |
| R-A17 | AI-generated Insight | **DERIVED_FROM** | Wardrobe + Knowledge | N:1 | regenerable; cache only |
| R-A18 | AI-generated Insight | **REFERENCE** | AI Model Version | 0..1:1 | when model-produced |
| R-A19 | AI Capability (config) | **GATES** | AI Analysis / AI Recommendation features | N:M | which runs may exist |
| R-A20 | AI Capability (config) × `Subscription` | **DERIVED_FROM** | CapabilityAvailability (derived) | 1:1 | prospective; effective per-user availability |
| R-A21 | AI Analysis run | **REFERENCE** (optional) | `SavedLook` | 0..1:1 | when the user saves the analyzed look |

### Relationship rules

1. **Everything AI-produced is derived from a decision context + knowledge and
   is regenerable** (R-A5, R-A17) — never a source of truth.
2. **Every durable AI event references its model version** (R-A3, R-A9, R-A12,
   R-A18) so history stays reproducible.
3. **Feedback and signals are append-only; only the derived preference state is
   mutable** (R-A14, R-A15).
4. **Capability is config that gates, never state that persists** (R-A19, R-A20).

---

## 6. The full pipeline as a graph

```
                  USER DATA (current state, mutable)
  Wardrobe · StyleProfile/FaceProfile · SavedLooks · UserEvents · Preferences
        │                                                        │ accepted
        │  serialized per request                                 │ attributes
        ▼                                                         ▼
  AI DECISION CONTEXT (DERIVED, per-request)        AI ANALYSIS run (HISTORICAL, immutable)
        │                                             │  R-A1
        ▼                                             ▼
  KNOWLEDGE ─► DECISION (intent/policy)         AI AnalysisResult (VALUE, immutable)
  Look catalog · vocab · capability config            │  R-A2 (latest wins)
        │                                             ▼
        │                                   Current Profile (provenance: source_run_id)
        ▼
  AI RECOMMENDATION (VALUE, regenerable)
     ├─ R-A8  Look ref ───────────────► Knowledge
     ├─ R-A6  Recommendation Reason (VALUE — the explanation)
     └─ R-A7  Recommendation Confidence (VALUE — optional; not computed today)
        │
        ├─ R-A10 (P3) ► RecommendationHistory (HISTORICAL) ── R-A11/R-A12 ─►
        │                    (frozen decision context + model version)
        └─ R-A13 (future) ► Recommendation Feedback (HISTORICAL, immutable)
                                   │  R-A14 FEEDS
                                   ▼
                  User Preference Signal = LearningSignal (HISTORICAL, append-only)
                                   │  R-A15 aggregates
                                   ▼
                  Derived preference state (DERIVED) ── R-A16 ──► next AI Decision Context
                                   │
                                   ▼
                      Future learning / training evidence

  AI-generated Insight (VALUE) ◄── R-A17 derived ── Wardrobe + Knowledge   (cache only)

  AI Capability (SYSTEM CONFIGURATION) ── R-A19 GATES ──► which analyses/recommendations run
  AI Model Version (SYSTEM CONFIGURATION) ◄── R-A3/R-A9/R-A12/R-A18 referenced ── history
```

This satisfies the required chain end-to-end:

```
User data + AI analysis + Knowledge + Decision
   → Recommendation → Explanation (Reason ± Confidence) → User feedback
   → User Preference Signal → Future learning
```

---

## 7. Classification summary (task checklist)

| Concept | ENTITY | VALUE OBJECT | HISTORICAL RECORD | DERIVED DATA | SYSTEM CONFIGURATION |
| --- | --- | --- | --- | --- | --- |
| AI Analysis (run / result) | (run = E6) | result | **run** | — | — |
| AI Recommendation | — | **yes** | occurrence = P3 | — | — |
| Recommendation Reason | — | **yes** | — | — | — |
| Recommendation Confidence | — | **yes** | — | derived aspect | — |
| Recommendation Feedback | — | — | **yes** (future) | — | — |
| AI Capability | — | — | — | availability aspect | **yes** |
| AI Model Version | — | — | — | — | **yes** |
| User Preference Signal | — | — | **yes** | derived preference state | — |
| AI Decision Context | — | — | — | **yes** | — |
| AI-generated Insight | — | **yes** | — | derived aspect | — |

Note on "ENTITY": within this AI sub-model, the only concept that is realized as
a domain entity is `AnalysisRun` (E6) — classified **HISTORICAL RECORD** here
because that is its role in the AI pipeline (an entity can *be* a historical
record; the taxonomy is not mutually exclusive across the two documents —
`DOMAIN_ENTITIES.md` E6 itself says "Historical record (linkage) + AI output
(result)"). Recommendation Feedback and RecommendationHistory become historical
entities/records only when their features land.

---

## 8. What the model guarantees for Step 4

1. **No AI output table.** Recommendations, reasons, confidence, insights are
   value objects — they are either embedded in a run/history snapshot (JSONB) or
   recomputed. Only *events* (runs, feedback, signals, optional
   `RecommendationHistory`) get rows.
2. **Every AI row carries provenance.** A run or history record references the
   model version and, where needed, a frozen decision context — so "what did the
   product tell me and why" is answerable later
   (`DOMAIN_STATE_AND_HISTORY.md` §6, §8).
3. **Capability and model registry are config.** System-owned reference data;
   per-user availability is derived (config × subscription), never stored per
   user until a real capability system exists (P3).
4. **The learning loop has a shape.** feedback (future) and all user actions
   become append-only signals → derived preference state → next decision context
   → future training. Nothing in the loop overwrites history.

---

## 9. Report — what was found & what must be modeled next

### What was found

- **The 10 AI concepts classify into the 5 categories with no ambiguity** (§7):
  one historical-record core (`AI Analysis` run), one derived-context core
  (`AI Decision Context`), value-object outputs (recommendation, reason,
  confidence, insight, analysis result), two system-config items (capability,
  model version), and two historical event streams (feedback future, signals
  today).
- **The pipeline chain maps 1:1** to concepts and 20+ relationships (§5–6),
  including the two STEP 2–flagged gaps: **confidence** (never computed — scores
  are catalog constants) and **structured explanation** (reasons live in prose,
  not a DTO field) (`AI_DATA_FLOW.md` Part D.3/D.4).
- **Nothing here invents behavior:** every "AI" surface except the assistant is
  mock, and the model explicitly records that (capability = marketing config;
  feedback = missing; runs = nonexistent). The domain model is the agreed target,
  not a description of current computation.

### What must be modeled next (dependency order, none implemented)

1. **Step 4 storage:** rows for runs/signals/feedback/history; JSONB for
   result/reason/confidence/context snapshots; config stores for capability +
   model-version registries.
2. **Typed AI API + error contract (A3.2/A3.3):** the assistant reply DTO gains a
   structured reason/confidence shape only when the product decides to compute
   them (currently prose-only; `AI_DATA_FLOW.md` Part D.4).
3. **Feedback feature design (P1)** and **`RecommendationHistory` decision
   (P3)** — each turns a prospective relationship into concrete historical rows.
4. **Face-analysis pipeline** (`setFace` currently uncalled) before any real
   `AnalysisRun` history exists.
5. **Capability/unlock system (P3)** before per-user capability state or
   "AI Capability Progress" is modeled (`DOMAIN_STATE_AND_HISTORY.md` §5.11).

---

## Constraints honored

- **No AI implemented; no database tables created; no repositories, services,
  or dependencies.**
- No Flutter/UI/routing changes, no code deleted.
- Every classification and relationship traces to a STEP 2 inventory reference
  and the STEP 3 companions; nothing claims a behavior the repo does not have
  (`AI_DATA_FLOW.md` statuses honored).
- The real Fansivibe repository is the source of truth; the separate reference
  project was not used.
