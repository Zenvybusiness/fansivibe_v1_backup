# Fansivibe — AI Integration Architecture

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Defines **how AI models integrate
> with Fansivibe** — the interfaces, boundaries, and runtime contracts between
> the application, the decision engine, and AI vendors.
>
> It **separates** the concerns that are too often conflated:
>
> | Concern | Lives where |
> | --- | --- |
> | **AI provider** | the vendor/service behind models (Ollama, hosted, …) — a seam, not code |
> | **AI model** | a named, versioned model spec (e.g. `llama3.1:8b`) |
> | **AI adapter** | `infrastructure/external/ai.py` — implements the provider port |
> | **analysis** | capability providers producing structured analysis attributes |
> | **recommendation** | capability providers producing candidates |
> | **decision engine** | M6 `domain/services` pipeline that calls capabilities via ports |
> | **persistence** | what is stored vs. what is regenerable output |
>
> **The application never depends on a specific AI vendor.** It depends on
> typed capability interfaces (`domain/ports/external.py`); vendors are chosen
> by config at the composition root.
>
> **Status: architecture design only. No AI providers are implemented.** No
> code, files, or directories are created; the live assistant contract
> (`POST /v1/assistant/chat`) is unchanged.
>
> **Honesty rule (AI-0):** capabilities that do **not** exist yet are marked
> **FUTURE** in this document — never presented as implemented. Today the only
> real AI integration is **optional text enrichment** (`llm_backend.py`); all
> analysis capabilities are FUTURE.

---

## 1. Purpose and scope

This document answers:

1. **The separation of concerns** — provider / model / adapter / analysis /
   recommendation / decision engine / persistence, and who may depend on whom.
2. **The capability interfaces** — `FaceAnalysisProvider`,
   `HairAnalysisProvider`, `OutfitAnalysisProvider`, `RecommendationProvider`,
   `ImageAnalysisProvider`, plus the shared text-enrichment and
   model-backend seams — each with input, output, confidence, model version,
   timeout, failure behavior, retry behavior, and logging requirements.
3. **Which capabilities are real today vs. FUTURE** (AI-0).
4. **Vendor-agnostic wiring** — how a vendor is chosen without leaking into
   the application (DR-5, F-7).

It does **not** implement providers, define prompt text, or pick vendors.

**Grounding facts (BAR-0):**
- Today's only AI touchpoint is `llm_backend.py`: optional Ollama text
  enrichment of the assistant's reply — **structure, scores, and DTO shape are
  always the engine's**; the LLM only rewrites wording, degrading to the
  rules text on any failure. This architecture generalizes that single seam
  into typed capability interfaces without changing behavior.
- The assistant DTOs (`schemas.py`, A3.1) are frozen — AI output is mapped
  into them by the engine, never by a provider.
- **AI output is never a source of truth** (BAR-0): analysis results and
  recommendations are regenerable; persistence is limited to snapshots/saves
  (TRX-2/TRX-4/TRX-5).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `backend/app/ai/llm_backend.py` | The real, working AI seam (Ollama, degrade-on-failure, text-only) this design extends. |
| `backend/app/ai/engine.py`, `tools.py` | Today's decision logic — deterministic, no provider calls except text enrichment. |
| `backend/app/models/schemas.py` | The frozen A3.1 DTO shapes providers never produce directly. |
| `BACKEND_ARCHITECTURE_RULES.md` | BA-6 (external via ports), BA-8 (AI only via engine), BA-3 (pure domain). |
| `BACKEND_MODULE_MAP.md` | M6 `ai_engine` owns `AIProvider`/`KnowledgeSource` ports. |
| `BACKEND_FOLDER_STRUCTURE.md` | `domain/ports/external.py`, `infrastructure/external/ai.py` (the only file touching a provider), M16 media. |
| `DEPENDENCY_RULES.md` | DR-5 (AI adapters → AI interfaces), F-7 (provider-specific code never leaks), F-3 (domain has no HTTP). |
| `DECISION_ENGINE_ARCHITECTURE.md` | The pipeline that calls these capabilities (stages 2/4/6) and the `AIProvider`/`WeatherProvider` ports. |
| `APPLICATION_USE_CASES.md` | UC-22 assistant, UC-24…27 analysis, UC-28/29 outfit, UC-16 today's look. |
| `TRANSACTION_BOUNDARIES.md` | TRX-5 run completion write-once; analysis runs persist result + engine_version; AI calls are never inside a transaction (§5). |

---

## 3. The separation model

### 3.1 The layers

```
        application (UC-22/24/26/28…)            ── never imports a vendor
              │  calls capability interfaces
              ▼
      DECISION ENGINE (M6 pipeline)              ── pure domain, owns the rules
              │  depends on ports only
              ▼
  ┌───────────────────────────┐
  │  Capability interfaces    │  domain/ports/external.py
  │  (Face/Hair/Outfit/Image/ │  typed: input, output, confidence,
  │   Recommendation/Text)    │  model version, timeout
  └───────────────────────────┘
              ▲  implemented by
              │
  ┌───────────────────────────┐
  │  AI adapter(s)            │  infrastructure/external/ai.py (the ONLY
  │  (Ollama, hosted, …)      │  file that knows a vendor exists — F-7)
  └───────────────────────────┘
              │  speaks a protocol to
              ▼
        AI provider (vendor)                 ── external service (Ollama/API)
              │
              ▼
        AI model (e.g. llama3.1:8b)          ── named, versioned artifact
```

### 3.2 Concern definitions

| Concern | Definition | In this design |
| --- | --- | --- |
| **AI provider** | A vendor/service that serves models (Ollama, OpenAI-compatible endpoint, self-hosted). It is an *external system*, never imported into app code. | Reached only by the adapter through HTTP (F-3 keeps it out of domain). |
| **AI model** | A named, versioned artifact the provider serves, with declared capabilities (text-only / vision). | A `ModelSpec` value object (name, version, capabilities, context size). No logic. |
| **AI adapter** | The concrete class implementing the model-backend seam for one vendor. | `infrastructure/external/ai.py` — one adapter per vendor; chosen by config. |
| **Analysis** | A capability that turns input (image/profile/options) into **structured attributes** (face shape, hair attributes, outfit items, scores). | `FaceAnalysisProvider`, `HairAnalysisProvider`, `OutfitAnalysisProvider`, `ImageAnalysisProvider` — all **FUTURE**. |
| **Recommendation** | A capability that produces **candidates** (looks, outfits, styles) for the engine to score/rank. | `RecommendationProvider` — rules-based today (engine tools), **AI-driven FUTURE**. |
| **Decision engine** | The pipeline (M6) that calls capabilities via ports, scores/ranks/explains, and maps to typed output. | Existing `engine.py`/`tools.py` + the future stage decomposition. |
| **Persistence** | What is stored vs. regenerable. | Analysis runs persist `result` + `engine_version` (TRX-5); recommendations are regenerable until saved (TRX-2/4). |

### 3.3 Who may depend on what

| Component | May depend on | Must never depend on |
| --- | --- | --- |
| application | domain (ports, services) | a vendor, adapter, SDK, provider-specific types |
| decision engine | capability **interfaces**, `KnowledgeSource` | concrete adapters, HTTP, vendor SDKs (F-3) |
| adapter (`ai.py`) | the interface it implements, config, its HTTP client | domain decision logic, application, API |
| capability interface | stdlib `abc`, domain models (return types) | anything concrete |

**AI-1 (vendor-agnostic):** at runtime the composition root (`main.py`)
selects an adapter from config (`FANSIVIBE_AI_PROVIDER=ollama|hosted|off`).
The application and engine hold only the interfaces — changing vendors is a
config change + one new adapter file.

---

## 4. The shared seams (exist today)

### 4.1 Model-backend seam — `AIProvider`

The lowest port: a model backend that can chat/enrich. This is today's
`llm_backend.py` behind an interface (DR-5). One adapter per vendor.

| Attribute | Spec |
| --- | --- |
| Input | `messages: List[ChatMessage]`, `model: ModelSpec`, `max_tokens`, `timeout_s` |
| Output | `ModelTextReply` (text, optional `finish_reason`) |
| Confidence | **N/A** (transport seam; no confidence on text) |
| Model version | `ModelSpec` passed in (config default `llama3.1:8b`) |
| Timeout | connect 1.5s, read 8s (today's values; configurable) |
| Failure behavior | **degrade, never error the caller** — return the base text / `None` so the engine falls back to rules text (today's behavior) |
| Retry behavior | none today (single attempt); retries live one level up (capability providers), not here |
| Logging | log provider name + model + duration + success/failure at DEBUG; **never log message content** (privacy) |

### 4.2 Text-enrichment capability — `TextEnrichmentProvider`

A **real** capability today (the only real AI integration). It rewrites the
engine's wording without touching structure/scores (BA-8).

| Attribute | Spec |
| --- | --- |
| Input | `intent`, `base_text`, `context_summary` (the `_context_summary` seed) |
| Output | enriched `text` (structure unchanged — F-13) |
| Confidence | N/A (not scored) |
| Model version | config (`llama3.1:8b`) |
| Timeout | 8s (inherits `AIProvider`) |
| Failure behavior | return the **base text unchanged** — the app never shows an error for enrichment failure |
| Retry behavior | none (degrade is the strategy) |
| Logging | DEBUG: provider+model+duration+ok/fail; INFO if degraded to base text; **no message content, no user context content** |

**Status: NOW** (wired, optional, degrades). This is the seam the new
capability interfaces are modeled on.

---

## 5. Capability interfaces

All analysis/recommendation capabilities share a **common result envelope**
(`CapabilityResult`) so the engine handles them uniformly:

```
CapabilityResult
├── status: success | no_result | error | degraded
├── output: typed structure (per capability)
├── confidence: 0.0..1.0        (or None if N/A / unavailable)
├── model_version: str | None   (provenance — always recorded, TRX-5)
├── warnings: List[str]         (e.g. "low light", "face partially obscured")
└── raw_provider: str | None    (internal only — never surfaced to clients)
```

### 5.1 `FaceAnalysisProvider` — **FUTURE**

Analyzes a face image into appearance attributes (feeds `FaceProfile`,
UC-25, R15).

| Attribute | Spec |
| --- | --- |
| Input | `image: MediaRef`, `image_binary` (via M16), optional hints |
| Output | `FaceAttributes` (face_shape, skin_tone, body_type, style_type + per-attribute confidence) |
| Confidence | per-attribute `0..1`; overall = min of attributes |
| Model version | recorded per run (provenance → `style_profile.source_run_id`, TRX-6) |
| Timeout | 30s (vision models are slower) |
| Failure behavior | run stays `pending`/`failed`; typed `ExternalServiceError` → 503; never a guessed profile (AI-0) |
| Retry behavior | 1 retry on timeout/5xx; no retry on `face not detected` (422 — don't reprocess a bad image) |
| Logging | DEBUG: run_id, model_version, confidence, duration, ok/fail; **image bytes never logged** (privacy, SAFETY); failures INFO with run_id |

### 5.2 `HairAnalysisProvider` — **FUTURE**

Produces hairstyle recommendations from a face image/profile (UC-26).

| Attribute | Spec |
| --- | --- |
| Input | `FaceAttributes` (or face image), `preferences` |
| Output | `HairRecommendationSet` (top + alternatives, each with attributes + score seed) |
| Confidence | per-candidate `0..1` |
| Model version | recorded per run |
| Timeout | 30s |
| Failure behavior | `ExternalServiceError` → 503; empty output → `no_result` (not a guess) |
| Retry behavior | 1 retry on timeout/5xx; none on invalid inputs |
| Logging | DEBUG: run_id, model_version, candidate count, ok/fail; no image content |

### 5.3 `OutfitAnalysisProvider` — **FUTURE**

Analyzes a photographed outfit into detected items + sections + scores
(UC-24).

| Attribute | Spec |
| --- | --- |
| Input | `image: MediaRef` + binary |
| Output | `OutfitAnalysisResult` (sections, detected items, scores, confidence) |
| Confidence | overall `0..1` |
| Model version | recorded per run (TRX-5 `engine_version`) |
| Timeout | 30s |
| Failure behavior | image invalid (413/422 `MediaValidationError`), no clothing detected (422 `InvalidInputError`), model failure (503) |
| Retry behavior | 1 retry on timeout/5xx; none on `no clothing detected` |
| Logging | DEBUG: run_id, model_version, confidence, detected-item count; no image bytes |

### 5.4 `ImageAnalysisProvider` — **FUTURE**

Generic image analysis utility (color palette extraction, quality checks,
duplicate/matching) shared by outfit/face/wardrobe image flows (M16-adjacent).
Exists because outfit/face/hair analysis all need common image pre-processing
without each owning it.

| Attribute | Spec |
| --- | --- |
| Input | `image: MediaRef` + binary, requested tasks |
| Output | `ImageAnalysisResult` (e.g. palette, quality, orientation) |
| Confidence | `0..1` per task |
| Model version | recorded |
| Timeout | 20s |
| Failure behavior | invalid image (413/422); failure → 503 |
| Retry behavior | 1 retry on timeout/5xx |
| Logging | DEBUG: ref, tasks, ok/fail; no image bytes |

### 5.5 `RecommendationProvider` — **rules NOW, AI-driven FUTURE**

Produces **candidates** for the engine to score/rank. **Today this is the
deterministic engine tools** (`recommend_outfit`, `recommend_hairstyle`,
`recommend_grooming`) — rules-based, no AI. The interface exists so an
AI-driven candidate source can be added later without changing the engine.

| Attribute | Spec |
| --- | --- |
| Input | `DecisionContext` (profile, preferences, appearance, wardrobe, occasion, weather hint, knowledge subset) |
| Output | `List[Candidate]` (looks/outfits/styles with base attributes + optional score seed) |
| Confidence | per-candidate `0..1` (rules today; AI later) |
| Model version | rules path: `engine_version` (rules code version); AI path: model version |
| Timeout | rules: immediate; AI-driven: 30s |
| Failure behavior | rules path never fails (deterministic); AI path: degrade to rules (never empty where rules have a result) |
| Retry behavior | AI path: 1 retry on timeout/5xx; rules path: N/A |
| Logging | DEBUG: source (rules|ai), candidate count, duration; AI fallback to rules at INFO |

### 5.6 Capability status summary (AI-0)

| Capability | Status | Serves |
| --- | --- | --- |
| `AIProvider` (model backend) | **NOW** (Ollama, optional) | all text/capability flows |
| `TextEnrichmentProvider` | **NOW** (only real AI today) | UC-22 assistant wording |
| `RecommendationProvider` | **NOW (rules) / FUTURE (AI)** | UC-16/21/28/29, discover ordering |
| `FaceAnalysisProvider` | **FUTURE** | UC-25 |
| `HairAnalysisProvider` | **FUTURE** | UC-26 |
| `OutfitAnalysisProvider` | **FUTURE** | UC-24 |
| `ImageAnalysisProvider` | **FUTURE** | outfit/face/wardrobe image pre-processing |

---

## 6. Vendor-agnostic wiring and configuration

**AI-2 (config-driven selection).** Config keys (from `app/config/settings.py`,
extending today's env vars in `llm_backend.py`):

| Key | Default | Meaning |
| --- | --- | --- |
| `FANSIVIBE_AI_PROVIDER` | `ollama` | `ollama` \| `hosted` \| `off` — which adapter the composition root injects |
| `FANSIVIBE_OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint (today) |
| `FANSIVIBE_OLLAMA_MODEL` | `llama3.1:8b` | default `ModelSpec` |
| `FANSIVIBE_DISABLE_LLM` | unset | `1` disables the provider entirely (today) |
| `FANSIVIBE_AI_TIMEOUT_S` | `8` | default capability timeout |
| `FANSIVIBE_AI_RETRIES` | `1` | default retry count for retryable capabilities |
| `FANSIVIBE_AI_*_MODEL` | per capability | optional per-capability `ModelSpec` overrides |

**AI-3 (composition root wiring).** `main.py` reads the provider key and
constructs the adapter(s); every use case and the engine receive **interfaces**
only. An adapter registry maps capability → adapter so one vendor can serve
several capabilities and capabilities can be replaced independently.

**AI-4 (capability isolation).** Each capability interface is independent:
implementing `FaceAnalysisProvider` does not require `HairAnalysisProvider`,
and a missing/FUTURE capability simply yields `no_result` — the engine handles
absence uniformly (no capability pretends to exist, AI-0).

---

## 7. Persistence boundary

| Data | Persisted? | Where / rule |
| --- | --- | --- |
| Analysis run result + `engine_version` + confidence | ✅ **yes** | `analysis_runs.result` (TRX-5 write-once completion; append-only grants PR-6) |
| Source image ref (scan/face) | ✅ ref only | `analysis_runs` source `MediaRef` (M16/MS10.3-gated); **bytes never in PG** (PR-8) |
| Accepted appearance profile | ✅ projection | `user_state.style_profile` + `source_run_id` provenance (TRX-6) |
| Recommendation / today's look | ❌ **regenerable** | not stored unless saved (TRX-2/TRX-4/TRX-7) |
| Saved look/outfit snapshot | ✅ on save | `saved_looks.snapshot` (TRX-3) |
| AI raw provider payload | ❌ never | only the typed `CapabilityResult` travels upward |
| Conversation text | ❌ transient | retention undecided (BA rules §8/§10) |

**AI-5 (AI never inside a DB transaction):** provider calls happen before or
after the transaction boundary (§5 `TRANSACTION_BOUNDARIES.md`), never between
`BEGIN` and `COMMIT` — a slow or failing model must not hold a DB transaction.

**AI-6 (provenance):** every persisted analysis carries `model_version` /
`engine_version` so results are reproducible and auditable (PR-6).

---

## 8. Cross-cutting requirements

- **Privacy (SAFETY):** image bytes, message content, and user context are
  **never logged**; only run_id/model_version/duration/confidence/status. All
  providers treat appearance data as privacy-sensitive.
- **Typed structured output only (BA-8):** providers return typed domain
  structures (`CapabilityResult` subtypes), never free-form JSON that flows
  through; the engine validates against the controlled vocabulary before
  anything reaches a DTO (A3.3).
- **Graceful degradation everywhere:** the rules path is always available;
  AI is additive. Disabling the provider (`FANSIVIBE_DISABLE_LLM=1`) must
  never change API behavior, only wording.
- **Timeouts are mandatory:** every capability declares a timeout; a hang in a
  vendor never hangs a request (bounded by the API timeout).
- **No vendor SDK in domain/application:** DR-5/F-7 — the adapter is the only
  file that knows an SDK/endpoint exists.
- **Confidence is advisory:** scores drive ranking hints, never hard
  decisions; low confidence → `warnings` + degraded explanation, never a
  fabricated result (AI-0).

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `AI_INTEGRATION_ARCHITECTURE.md` — the
AI-model integration design (separation model, capability interfaces,
vendor-agnostic wiring, persistence boundary). No implementation.

**Skills used:** repository analysis (current `llm_backend.py`,
`engine.py`, `tools.py`, `schemas.py`; STEP 5 architecture/module map/folder
structure/dependency rules/decision engine/use cases) — architecture
documentation only.

**Files changed:** `docs/backend/AI_INTEGRATION_ARCHITECTURE.md` (new).

**Validation run:**
- Every capability interface traced to a real or FUTURE need in the domain
  model and use cases (UC-24/25/26, R15, TRX-5/6); the shared seams map
  1:1 to today's working `llm_backend.py` (degrade, timeout, env vars).
- Verified against DR-5/F-7 (adapter confinement), F-3 (no HTTP in domain),
  BA-8 (AI only via engine), TRX-5 (run completion), MS10.3 (media gate).
- Honesty check (AI-0): only `TextEnrichmentProvider` + `AIProvider` marked
  NOW; all analysis providers marked FUTURE; `RecommendationProvider` marked
  rules-NOW/AI-FUTURE.
- `git status --short`: only this new doc + `CURRENT_STATE.md` update; no
  code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- Capability interfaces are design targets; the exact method signatures and
  `CapabilityResult` fields are decided at implementation (M2+), not now.
- FUTURE capabilities are **not** on any roadmap order here; they gate on
  their feature modules (M12 analysis, M16 media/MS10.3) and are built only
  when the product requires them.
- No `DECISIONS.md` entry needed: no accepted architectural decision made
  (documentation only); open items remain in `BACKEND_ARCHITECTURE_RULES.md`
  §8/§10 (provider choice, retention).

**Assumptions recorded:**
- "AI provider" = external vendor/service; "AI model" = named versioned
  artifact; "AI adapter" = `infrastructure/external/ai.py`; these match the
  module map M6 and folder structure terms exactly.
- The only AI integration that exists today is optional text enrichment; this
  document does not claim otherwise (AI-0).
- Capability interfaces live in `domain/ports/external.py` (already the
  accepted location for `AIProvider`/`KnowledgeSource`/`WeatherProvider`).

**Constraints honored:** BAR-0 (AI output never truth; assistant DTOs frozen
A3.1), BA-3/BA-6/BA-8 (pure domain, external via ports, AI only via engine),
DR-5/F-7/F-13 (adapter confinement, no leakage, frozen contract), TRX-5/6
(persist result + provenance; never inside a transaction), the UI Change
Safety Rule (no UI touched), and the Scope rule (this document only).

