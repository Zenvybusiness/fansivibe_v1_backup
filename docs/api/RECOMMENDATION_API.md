# Fansivibe — API Contract: Common Recommendation Contract

> **STEP 6 — API CONTRACT DESIGN.** Defines the **single shared recommendation
> API contract** for Fansivibe: the **common `Recommendation` envelope** that
> every recommendation type satisfies, the **type matrix** (which types share
> common API structures and how), the **common fields** (recommendation ID,
> type, title, description, score, confidence, reasons, warnings/trade-offs,
> created_at, expires_at), the **type-specific fields** each surface adds, and
> the **cross-cutting operations** (save, feedback, history) that treat every
> type uniformly. Its purpose is to guarantee the surface does **not** fragment
> into a separate, incompatible API format per recommendation type.
>
> It is the **umbrella companion** to `API_CONTRACT_RULES.md` (§12.6 saved
> looks, §12.10 feedback, §12.11 analysis, §12.12 outfits, §12.13 discover,
> §8.3 async run object) and `API_INVENTORY.md` (endpoints 15/23–25/30–33/35/
> 37–44), and it sits above the sibling contracts `HAIRSTYLE_RECOMMENDATION_API.md`
> (the hairstyle field-level contract), `SCAN_API.md` (the scan lifecycle),
> `APPEARANCE_API.md` (face/grooming analysis), and `PROFILE_ONBOARDING_API.md`
> (the profile inputs). The sibling docs **own** their endpoints; this doc
> defines the **shared wire vocabulary** they all use.
>
> **Status: contract design only. The common contract is NOT implemented.** No
> code, no `deps.py`, no routers, no SQL, no AI providers, no Flutter changes,
> no dependencies. The live contract (`GET /health`, `POST /v1/assistant/chat`)
> is preserved unchanged. Analysis endpoints are P2 and stay **unmounted**
> until the auth seam (D-AUTH-1), the media seal (MS10.3), and a real analysis
> pipeline land (API-12); feedback (M11) is **feature-gated** and **not
> mounted**; the P3 `recommendation_history` trace is conditional.
>
> **Source of truth:** the real Fansivibe repository and the accepted docs —
> the six real recommendation surfaces and their mock DTOs
> (`hairstyle_mock_data.dart`, `grooming_mock_data.dart`,
> `outfit_builder_mock_data.dart`, `outfit_scan_mock_data.dart`,
> `daily_outfit_mock_data.dart`, `discover_mock_data.dart`,
> `wardrobe_mock_data.dart`), STEP 3 `FANSIVIBE_DOMAIN_MODEL_V1.md`
> (E4 `SavedLook`, E5 `Look`), STEP 4 `TABLE_DEFINITIONS.md`
> (`saved_looks`, `analysis_runs`, `looks`, `recommendation_history`* P3) +
> `HISTORY_AND_VERSIONING.md` (§5.8) + `TRANSACTION_BOUNDARIES.md`
> (TRX-2/3/5/7), STEP 5 `APPLICATION_USE_CASES.md` (UC-14/15/16/21/24…32) +
> `DECISION_ENGINE_ARCHITECTURE.md` (stages 4–8) + `AI_INTEGRATION_ARCHITECTURE.md`
> (AI-0), STEP 6 `API_CONTRACT_RULES.md` (catalog §12.6/§12.10–§12.13, async
> §8.3, DTO sketches §13) + `API_INVENTORY.md` (endpoints 15/23–25/30–33/35/
> 37–44), and the sibling contracts `HAIRSTYLE_RECOMMENDATION_API.md`,
> `SCAN_API.md`, `APPEARANCE_API.md`.

---

## 1. Purpose and scope

This document answers three questions:

1. **Which recommendation types share common API structures, and what is the
   one shared structure?** (§3, §4)
2. **What are the common fields every recommendation carries, mapped honestly
   to the frozen wire?** (§4.1–§4.6)
3. **Which fields are type-specific, and where do they live?** (§4.3)

The recommendation types in scope (from the task): **hairstyle, grooming,
outfit, wardrobe, event styling, daily outfit** — plus the **discover look**
(a read-only feed sibling) and **outfit analysis** (an analysis result, not a
recommendation, included so the boundary is explicit).

**The three binding design rules of this document:**

1. **A recommendation is AI output, never truth** (BAR-0). A recommendation is
   a **value object** produced by the decision engine (stages 4–8); its durable
   forms are the immutable run `result` (TRX-5), the immutable `SavedLook`
   snapshot (TRX-3), and — only if the P3 decision lands — the
   `recommendation_history.snapshot`. There is **no `Recommendation` table and
   no "current recommendation" resource**; regenerate always produces a **new**
   value (a new run or a new generation).
2. **One envelope, frozen type shapes.** The common `Recommendation` envelope
   (§4.1) is the **semantic contract** — the canonical field vocabulary the
   whole surface shares. The existing type-specific DTOs are **not renamed,
   retired, or reshaped** (their wire shapes are frozen: hairstyle/grooming
   identical to `APPEARANCE_API.md` §5.1/§5.2, `OutfitRecommendation` identical
   to the catalog and mock). Each type's DTO **satisfies** the envelope and is
   mapped to it explicitly (§4.2). No field is renamed, removed, or retyped on
   the wire (API-2).
3. **The wire never exposes internals** (C-8/ER-0/ER-2/F-7/AI-0). No prompts,
   no provider/model names, no sampling parameters, no raw provider output —
   only the typed recommendation fields + container provenance
   (`engine_version`). §4.9.

**What it does not do:** implement anything, create a new endpoint, change the
frozen assistant DTOs, or re-own endpoints. The submission/read endpoints are
owned by the sibling docs (`POST /v1/analysis/hairstyle|grooming`,
`GET /v1/analysis/runs/{run_id}`, `POST /v1/outfits/generate`,
`POST /v1/events/{event_id}/outfit`, `GET|POST /v1/looks/today`,
`GET /v1/wardrobe/insight`, `GET /v1/looks`, `POST /v1/looks/saved`,
`POST /v1/feedback`). This doc defines the **common shape** those operations
share and keeps the shapes identical to the accepted contracts.

### 1.1 Grounding facts (re-verified)

- **Six recommendation types, four wire shapes.** The six task types + the
  discover look resolve to **four distinct wire DTOs** (§3.3), and all four
  satisfy the **one** `Recommendation` envelope (§4.1). Hairstyle and grooming
  are near-identical (grooming adds 4 fields); outfit generation and event
  styling use **literally the same** `OutfitRecommendation`; daily outfit and
  the discover look share the derived-look shape; wardrobe is a lightweight
  insight. This is the concrete answer to "avoid completely separate
  incompatible formats": the surface has **4 shapes, not 6+, and 1 envelope**.
- **No `Recommendation` entity/table exists** (`TABLE_DEFINITIONS.md` §8:
  "recommendations — no; AI output — regenerable, never truth; occurrence =
  `recommendation_history` (P3, conditional)"). The recommendation travels as a
  JSON value inside one of two containers: the async **run result** or a
  **sync value object**; its durable form is the save snapshot (§4.7, §4.8).
- **Common core is real, not aspirational.** Every recommendation DTO in the
  real mock data carries `id`-or-equivalent, a title/name, a description, a
  score, and a reasons list. `confidence` is **never computed today** (AI-0);
  `tradeOffs`/warnings are **not modeled** (additive-only); `expiresAt` is
  **not modeled** (recommendations don't expire today — only raw scan media
  does, via the retention job). These are honestly absent, never fabricated.
- **Score has two accepted scales.** The analysis family (hairstyle/grooming)
  and the ensemble family (outfit/event) use `matchScore` as a **0..1 float**
  (`hairstyle_mock_data.dart`, `grooming_mock_data.dart`,
  `outfit_builder_mock_data.dart`); the derived-look family (daily outfit,
  discover look) uses an integer **0–100** percent (`daily_outfit_mock_data.dart`,
  `discover_mock_data.dart`). The envelope documents this; normalizing the
  scale is an open decision (§8.5), never a silent wire change.
- **`type` is a derived/save-time field, not a stored per-DTO field.** No mock
  DTO stores a `type`; the type is the surface context (the endpoint /
  `run_type` / `sourceContext`). The envelope defines the **type vocabulary**
  and requires it be stamped into the snapshot at save time so history is
  uniform across types (§4.6, §4.8).
- **Save is the only durable keeper; save/feedback/history are type-agnostic.**
  `POST /v1/looks/saved` (UC-15) freezes **any** recommendation DTO verbatim as
  `snapshot` JSONB (TRX-3); `POST /v1/feedback` targets by recommendation id;
  `recommendation_history` (P3) traces shown/saved. Because the snapshot is the
  type DTO, these operations need **no per-type format**.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `hairstyle_mock_data.dart` | `HairstyleRecommendation` — `id/name/description/matchScore/reasons/stylingTips/maintenance/bestFor`; `HairstyleAnalysisResult` — `faceShape/skinTone/styleDna` + `topRecommendation` + `alternatives` (the wire maps the context block to `result.appearance`, §4.7). |
| `grooming_mock_data.dart` | `GroomingRecommendation` — the same core + `beardLength/cheekLine/eyewearFrame/eyewearRecommendation`; `GroomingAnalysisResult` — `faceShape/beardStyle/beardDensity/beardColor` + `topRecommendation` + `alternatives`. |
| `outfit_builder_mock_data.dart` | `OutfitRecommendation` — `title/matchScore/components[]/reasons[]/colorHarmony/bodyFit/occasionMatch/styleScoreImpact/improvementSuggestion/selectedOccasion/selectedMood/selectedColorPalette`. |
| `outfit_scan_mock_data.dart` | `OutfitAnalysisData` — `title/sections[]/detectedItems[]` (analysis result, NOT a `Recommendation`). |
| `daily_outfit_mock_data.dart` | `DailyOutfitData` — `title/occasion/weather/description/matchScore(0-100)/styleScore/components[]/reasons[]/styleDna/wardrobeContext/aiSelectionReason/confidenceBoost/aiInsights[]/alternatives[]/dailyStyleTip`. |
| `discover_mock_data.dart` | `DiscoverLookData` — `id/imageUrl/title/description/occasion/styleTags[]/fitTags[]/matchScore(0-100)/wardrobeMatchCount/matchScoreDetails/recommendationReasons[]/ensembleComponents[]/wardrobeAlternatives[]`. |
| `wardrobe_mock_data.dart` | `WardrobeInsightData` / home `AIWardrobeInsightData` — `title/insight/actionLabel/actionRoute` (lightweight insight; **no score today**). |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | E4 `SavedLook` (immutable snapshot), E5 `Look` (catalog, stable codes), E6 `AnalysisRun`, E7 `LearningSignal`; outfit/recommendation as value objects. |
| `TABLE_DEFINITIONS.md` | `saved_looks` (snapshot JSONB, `source_run_id`), `analysis_runs` (`result` JSONB, `run_type`), `looks` (`code` PK, `payload`), `recommendation_history` (P3, conditional). |
| `HISTORY_AND_VERSIONING.md` | §5.7/§5.8: AI output is regenerable; durable trace = save/snapshot; shown/saved trace = P3 conditional. |
| `TRANSACTION_BOUNDARIES.md` | TRX-2 (generation = computation, no write), TRX-3 (save snapshot + signal, one transaction), TRX-5 (run result write-once), TRX-7 (event outfit regenerable). |
| `APPLICATION_USE_CASES.md` | UC-14 (wardrobe insight), UC-15 (save), UC-16/17 (daily outfit), UC-21 (event outfit), UC-24…27 (analysis), UC-28/29 (generate/regenerate outfit), UC-31 (discover), UC-32 (feedback, gated). |
| `DECISION_ENGINE_ARCHITECTURE.md` | Stages 4–8: Scoring (`matchScore`), Ranking (top + alternatives / ordered feed), Explanation (grounded reasons), Recommendation (typed deliverable), Feedback (signal shape). |
| `AI_INTEGRATION_ARCHITECTURE.md` | AI-0 (no confidence today), `CapabilityResult` (raw_provider internal only), providers FUTURE. |
| `API_CONTRACT_RULES.md` | Catalog §12.6/§12.10–§12.13, async §8.3, DTO sketches §13 (incl. `WardrobeInsight` §13.3), error §9, idempotency §11, C-8/C-10/C-16. |
| `API_INVENTORY.md` | Endpoints 15 (wardrobe insight), 23–25 (saved looks), 30–33 (event outfit, today's look), 35 (feedback, gated), 37–44 (analysis runs, outfit generate/save, discover). |
| Sibling contracts | `HAIRSTYLE_RECOMMENDATION_API.md` (§4.3 the recommendation DTO), `SCAN_API.md` (§4.2/§4.3 run lifecycle + DTO), `APPEARANCE_API.md` (§5.1/§5.2 result shapes) — kept identical. |
| `PROFILE_ONBOARDING_API.md` / `AUTH_API.md` | R-1 `GET /users/me` (current profile, an engine input), auth semantics (Bearer, OW-1). |
| `ERROR_HANDLING.md` | 12-category taxonomy: VALIDATION_ERROR (422), AUTHENTICATION_ERROR (401), NOT_FOUND (404), MEDIA_FAILURE (413/422), EXTERNAL_SERVICE_FAILURE (503), PROCESSING_FAILURE (run `failed`), RATE_LIMITED (429). |

---

## 3. The recommendation type inventory (the type matrix)

### 3.1 The types in scope, mapped to their real surfaces

| Type (task) | `type` code (this contract) | Product surface | Endpoint(s) (owned by) | Sync/async | Wire DTO | Family |
| --- | --- | --- | --- | --- | --- | --- |
| **Hairstyle** | `hairstyle` | Hairstyle feature (action 21) | `POST /v1/analysis/hairstyle` + `GET /v1/analysis/runs/{run_id}` | async (run) | `HairstyleRecommendation` | Analysis |
| **Grooming** | `grooming` | Grooming feature (action 23) | `POST /v1/analysis/grooming` + run read | async (run) | `GroomingRecommendation` | Analysis |
| **Outfit** (generation) | `outfit` | Outfit Builder (actions 18/20) | `POST /v1/outfits/generate` (endpoint 41) | sync | `OutfitRecommendation` | Ensemble |
| **Event styling** | `event` | Events → outfit (action 11) | `POST /v1/events/{event_id}/outfit` (endpoint 30) | sync | `OutfitRecommendation` | Ensemble |
| **Daily outfit** | `daily` | Home → Daily Outfit (actions 12/13) | `GET|POST /v1/looks/today` (endpoints 31/32) | sync | `TodayLook` (`DailyOutfitData` shape) | Derived-look |
| **Wardrobe** | `wardrobe` | Wardrobe "View Analysis" (action 8) | `GET /v1/wardrobe/insight` (endpoint 15) | sync | `WardrobeInsight` (§13.3) | Insight |
| **Discover look** (read-only feed) | `look` | Discover (actions 14/15) | `GET /v1/looks`, `GET /v1/looks/{look_id}` (endpoints 43/44) | sync | `LookDetail` (`DiscoverLookData` shape) | Derived-look |
| **Outfit analysis** (NOT a recommendation) | `outfit_analysis` | Outfit Scan (action 16) | `POST /v1/analysis/outfit` + run read (endpoint 36/39) | async (run) | `OutfitAnalysisData` | (analysis container only) |

**Reading the matrix:** the six task types plus the discover look collapse into
**four DTO families** over **one envelope**. No type needs a private,
incompatible format.

### 3.2 What a "recommendation" is (and is not)

- **A recommendation is a typed value object** produced by the decision
  engine's Scoring → Ranking → Explanation → Recommendation stages. It is
  delivered inside one of two shared containers — the async **run result** or
  the **sync response value** (§4.7) — and it is durable only as a **snapshot**
  (`analysis_runs.result` TRX-5, `saved_looks.snapshot` TRX-3, P3
  `recommendation_history.snapshot`).
- **There is no `/v1/recommendations/*` resource.** Occurrence = a run / a
  generation / a save (`HISTORY_AND_VERSIONING.md` §5.8, BAR-0). A dedicated
  recommendation family would be an invented API (§3.3).
- **Outfit analysis is analysis output, not a recommendation.** Its result
  (`OutfitAnalysisData`: `sections[]` + `detectedItems[]`) carries per-section
  scores but no ranked recommendation list — it does **not** satisfy the
  `Recommendation` envelope. It shares only the run container with the analysis
  family. A follow-up "generate look from this outfit" is the **outfit**
  generation surface (§5, `POST /v1/outfits/generate`).
- **The assistant `SuggestionCard` is a compact card surface, not a
  recommendation DTO.** The frozen assistant contract (`SuggestionCard { kind,
  title, subtitle, score?, items[], action? }`, §13.4) is a presentation
  primitive that may *render* a recommendation; it is never the durable
  recommendation shape and is unchanged (F-13).

### 3.3 Operations explicitly NOT defined (and why)

- **A dedicated recommendation resource family** (`GET /v1/recommendations`,
  `GET /v1/recommendations/{id}`) — **NOT defined.** No `Recommendation`
  entity/table (BAR-0); details are read from the run result / look detail /
  saved snapshot by id (§5).
- **Per-type save/feedback endpoints** (`/v1/looks/saved/hairstyle`,
  `/v1/feedback/hairstyle`, …) — **NOT defined.** Save (endpoint 23), feedback
  (endpoint 35) and history (P3) are **type-agnostic**: the request carries the
  `snapshot` (the type DTO) + `sourceContext` (the type code) (§4.8). This is
  the mechanism that prevents six incompatible formats.
- **Recommendation expiry / recall** — **NOT defined.** `expiresAt` is
  additive-only (§4.6); only raw scan media expires (retention job, not an API
  concept); `recommendation_history` (P3) is conditional, not mounted.

---

## 4. The common recommendation contract

### 4.1 The `Recommendation` envelope — the common core

The shared wire vocabulary. **Semantic field → how it appears on the wire per
type** is spelled out in §4.2; here is the canonical envelope:

```
Recommendation {                        // the common contract (semantic)
  id*,            // recommendation ID — stable catalog code (PR-3) or generated UUID
                  //   (type-specific namespace, §4.2)
  type*,          // "hairstyle"|"grooming"|"outfit"|"event"|"daily"|"look"|"wardrobe"
                  //   — derived from the surface / run_type / sourceContext (§4.6)
  title*,         // display title — the human name of the recommendation
  description*,   // explanation — why this suits the user (grounded, never invented)
  score*,         // match score — 0..1 float OR 0-100 int (type-specific scale, §4.4)
  confidence?,    // FUTURE — NOT computed today (AI-0); absent from responses
  reasons*,       // string[] — grounded bullet reasons (reason catalog; never invented)
  tradeOffs?,     // warnings / trade-offs — NOT modeled today; additive-only, absent (§4.5)
  createdAt?,     // container-level today — run.created_at / SavedLook.createdAt;
                  //   per-item additive-only (§4.6)
  expiresAt?,     // NOT modeled — recommendations don't expire today;
                  //   additive-only, absent (§4.6)
}
```

Every type-specific DTO in §3.1 **satisfies** this envelope: it carries the
required core fields (id/title/description/score/reasons) and may add its
type-specific extension (§4.3). Fields marked `?` that the domain does not
compute today are **absent from responses** — never fabricated, never a guessed
value (AI-0, the honesty rule from `HAIRSTYLE_RECOMMENDATION_API.md` §4.3).

### 4.2 The task's common fields → wire mapping (the required table)

| Task requirement | Envelope field | Wire field per type | Status |
| --- | --- | --- | --- |
| recommendation ID | `id` | analysis family: `id` (stable catalog code, e.g. `textured_quiff`, `structured_goatee` — PR-3); discover look: `id` (`fy_1`, …); outfit/event: **no per-item id today** — the recommendation id = the look/catalog code or a client-generated id for the save; wardrobe: **no id** (a singleton insight) | **present** where a selectable item exists; `id` is the reference used by save (`lookId`) and feedback (`targetLookId`) |
| type | `type` | **not a stored per-DTO field** — derived from the surface (`run_type`, endpoint, `sourceContext`) | **derived** (§4.6); stamped into the save snapshot for uniform history |
| title | `title` | analysis family: `name` (e.g. "Textured Quiff"); ensemble + daily: `title` (e.g. "Refined Office Ensemble"); discover look: `title`; wardrobe: `title` | **present**, required — wire name is family-frozen (`name` vs `title`); never renamed |
| description | `description` | all families: `description` (the explanation; today's-look also exposes `aiSelectionReason`) | **present**, required (Explanation stage; grounded) |
| score | `score` | `matchScore` — analysis/ensemble: **0..1 float**; derived-look: **0–100 int**; wardrobe: **no score today** | **present** for all except wardrobe (honest gap, §8.5) |
| confidence | `confidence` | `confidence` (per-item) / run `appearance.confidence` — absent today | **NOT computed today** (AI-0); optional FUTURE field, absent |
| reasons | `reasons` | analysis/ensemble/daily: `reasons[]`; discover look: `recommendationReasons[]` (structured `{title, description}`) — same semantic, structured shape | **present**, required (grounded; never invented) |
| warnings / trade-offs | `tradeOffs` | `tradeOffs` — **not modeled in any family** | **additive-only**, absent until a grounded trade-off catalog exists (§4.5) |
| created_at | `createdAt` | analysis family: run `created_at` (container); ensemble/daily/discover: **n/a for a value object** (regenerable); saved form: `SavedLook.createdAt` | **container/snapshot-level** today; per-item additive-only (§4.6) |
| expires_at | `expiresAt` | **not modeled** — recommendations don't expire; only raw media expires via retention | **additive-only**, absent (§4.6) |

**This table is the heart of the common contract.** It proves every
recommendation type shares the same ten semantic fields and shows exactly where
each appears on the wire — without renaming any frozen field.

### 4.3 Type-specific fields (the extension table)

Beyond the common core, each family adds its own fields. These are the **only**
places the six types differ — a bounded, documented extension layer, never a
parallel format:

| Family | Type DTO | Type-specific fields (beyond the envelope) |
| --- | --- | --- |
| Analysis | `HairstyleRecommendation` | `stylingTips`, `maintenance`, `bestFor` |
| Analysis | `GroomingRecommendation` | `beardLength`, `cheekLine`, `eyewearFrame`, `eyewearRecommendation`, `stylingTips`, `maintenance`, `bestFor` |
| Ensemble | `OutfitRecommendation` | `components[]` (`OutfitComponent { id, name, category, color, colorHex, material?, reason }`), `colorHarmony`, `bodyFit`, `occasionMatch`, `styleScoreImpact`, `improvementSuggestion`, `selectedOccasion`, `selectedMood`, `selectedColorPalette` |
| Derived-look (daily) | `TodayLook` / `DailyOutfitData` | `occasion`, `weather`, `styleScore`, `components[]`, `styleDna`, `wardrobeContext`, `aiSelectionReason?`, `confidenceBoost?`, `aiInsights[]`, `alternatives[]`, `dailyStyleTip?` |
| Derived-look (discover) | `LookDetail` / `DiscoverLookData` | `imageUrl`, `occasion`, `styleTags[]`, `fitTags[]`, `wardrobeMatchCount`, `matchScoreDetails?`, `recommendationReasons[]`, `ensembleComponents[]`, `wardrobeAlternatives[]`, `isTrending` |
| Insight | `WardrobeInsight` | `insight`, `action?`, `route?` (§13.3 — no score, no reasons list today) |

**What is shared inside the families (the common API structure in practice):**

- **Analysis family:** identical container `{ context?, recommendations:
  { top, alternatives } }`; DTOs share `id/name/description/matchScore/reasons/
  stylingTips/maintenance/bestFor` — grooming only adds the 4 facial-grooming
  detail fields. One parser handles both.
- **Ensemble family:** `OutfitRecommendation` is a **single shared DTO** —
  event styling reuses it verbatim; only the seeding occasion differs.
- **Derived-look family:** both are sync derived objects with an ensemble +
  insight blocks + an alternatives list; score is the 0–100 scale; discover
  adds read-only catalog presentation (`imageUrl`, tags, `isOwned`).

### 4.4 Score and confidence

- **Score** (`matchScore`) is the deterministic Scoring-stage value over
  profile/preferences/wardrobe/occasion × knowledge
  (`DECISION_ENGINE_ARCHITECTURE.md` §5.4). It is never client-authored and
  never edited post-creation. **Two accepted scales** coexist today
  (§1.1/§4.2): `0..1` float (analysis + ensemble families) and `0–100` int
  (derived-look family). The contract documents both; unifying the scale is an
  open decision (§8.5) — never a silent wire change (API-2).
- **Confidence** is a value object (`VALUE_OBJECTS.md` §3.3) that is **not
  computed today** (`AI_DATA_FLOW.md` Part D.3, AI-0). When a real model
  computes it it appears as an optional `0..1` field inside the result — never
  an endpoint and never a substitute for `matchScore`.
- **Wardrobe insight has no score today.** `WardrobeInsight` (§13.3:
  `title/insight/action?/route?`) is derived, not scored; a score is an
  additive extension, absent today (§8.5).

### 4.5 Reasons, warnings, trade-offs

- **Reasons** (`reasons[]`) are the grounded bullets from the Explanation
  stage — always grounded in score signals or a validated reason catalog,
  never invented (`DECISION_ENGINE_ARCHITECTURE.md` §5.6). The discover family
  uses a structured form (`recommendationReasons[]: { title, description }`);
  the other families use flat strings. Same semantic, family-frozen shape.
- **Warnings / trade-offs** (`tradeOffs`) are **not modeled anywhere in the
  domain or the mock data** — additive only, absent until the domain defines a
  grounded trade-off/warning catalog (same decision as
  `HAIRSTYLE_RECOMMENDATION_API.md` §4.3/§8.4). The contract reserves the field
  in the envelope so all four families can adopt it **without a format change**
  when that catalog lands. No invented warning text.

### 4.6 `type`, `createdAt`, `expiresAt` (provenance and time semantics)

- **`type`** is not a stored per-DTO field in any family. It is **derived**:
  the surface that produced the value (`run_type` for the analysis family; the
  endpoint for the sync families; §3.1). On **save**, the type is carried
  explicitly as `SaveLookRequest.sourceContext` (the `type` code — §4.8) so the
  snapshot is tagged and history reads uniformly across types. The accepted
  `sourceContext` example is `"hairstyle"` (`HAIRSTYLE_RECOMMENDATION_API.md`
  §5.5); this contract consolidates the full vocabulary (§3.1).
- **`createdAt`** is **container-level today**: the immutable run carries
  `created_at` (analysis family); the durable save carries `SavedLook.createdAt`
  (all families). The regenerable sync value objects (outfit/event/daily) have
  **no** creation timestamp of their own — they are computation, not records
  (TRX-2/TRX-7). A per-item `createdAt` is additive-only.
- **`expiresAt`** is **not modeled**. Recommendations do not expire today; the
  only "expiry" in the system is **raw scan-media retention** (face media after
  analysis, outfit media e.g. 30 days — a storage concern, `STORAGE_INVENTORY`
  §1.2/§1.3, not an API field). A daily look is derived-per-day and replaced on
  regenerate, but no wire `expiresAt` exists. The envelope reserves the field
  for a future content-validity feature (§8.6).

### 4.7 The two shared delivery shapes (how every type reaches the client)

Every recommendation type is delivered through **one of two shared shapes** —
there is no third, per-type container:

**Shape A — the async run result (analysis family: hairstyle, grooming; plus
outfit analysis as a non-recommendation result).** The recommendation set lives
inside the immutable `AnalysisRun.result` (TRX-5), read via
`GET /v1/analysis/runs/{run_id}` (`SCAN_API.md` §4.2/§4.3):

```
AnalysisRun {
  run_id*, run_type*, status*, created_at*, completed_at?,
  engine_version?, input_media?, error?,
  result?: {
    context?,                      // the inputs the ranking was grounded on
                                   //   (hairstyle: appearance{faceShape, skinTone, …};
                                   //    grooming: faceShape, beardStyle, beardDensity, beardColor)
    recommendations: { top, alternatives }   // both satisfy the Recommendation envelope
  }
}
```

**Shape B — the sync value object (ensemble + derived-look + insight
families).** The recommendation is the response itself (regenerable, never
persisted unless saved — TRX-2/TRX-7):

```
outfit / event  →  OutfitRecommendation        (bare value object)
daily           →  TodayLook                   (bare value object)
look            →  LookFeed / LookDetail       (feed envelope / bare detail)
wardrobe        →  WardrobeInsight             (bare value object; 204 when empty)
```

**Shared guarantees across both shapes:** owner-only reads (OW-1, 404-not-403);
typed fields only, no internals (§4.9); the embedded DTO always satisfies the
`Recommendation` envelope; a save snapshots the DTO verbatim (§4.8).

### 4.8 Save, feedback, history — the uniform cross-type operations

Because the snapshot **is** the type DTO and the type is carried by
`sourceContext`, these three operations are **type-agnostic** — the mechanism
that prevents per-type API formats:

- **Save (UC-15, endpoint 23 — referenced, owned by M7):**
  `POST /v1/looks/saved` with `SaveLookRequest { lookId?, title,
  sourceContext, snapshot }` + `Idempotency-Key`. `snapshot` is **any** of the
  four family DTOs (verbatim); `sourceContext` is the `type` code (§3.1, e.g.
  `"hairstyle"`). One true transaction (TRX-3): `INSERT saved_looks` +
  `INSERT learning_signals(look_saved)`; optional `source_run_id` provenance
  when saved from a scan. **No per-type save endpoint.**
- **Feedback (UC-32, endpoint 35 — referenced, gated):** `POST /v1/feedback`
  targets a recommendation by `targetLookId` (the `id` from any family) or
  `targetSavedLookId`; rating vocabulary pending the feedback design (M11).
  **No per-type feedback endpoint.**
- **History:** `recommendation_history` (P3, conditional) traces shown/saved
  with a snapshot **of the same shape**; until it exists, `look_saved` signals
  are the only trace. The analysis family additionally keeps its immutable
  history as runs (`GET /v1/analysis/runs`, endpoint 40) — that is run history,
  not a separate recommendation format.

### 4.9 Auth, ownership, privacy — and the no-internals rule

| Requirement | Applies to |
| --- | --- |
| **Auth** (Bearer → `user_id`) | all recommendation-producing endpoints (analysis submits/runs, outfit generate/save, event outfit, today's look, wardrobe insight, discover, saved looks, feedback when mounted). |
| **Public** | none in this surface. |

Authorization is **owner-only (OW-1)** with **404-not-403** (API-10); face and
outfit media and their derived attributes are **CRITICAL** appearance data
(`SECURITY_PRIVACY_DESIGN.md` §3): HTTPS only, image bytes never
logged/echoed, only `MediaRef` travels (MS10.3, ER-4).

**The no-internals rule (binding, C-8/ER-0/F-7/AI-0):** the response never
contains — and the client never sees — internal AI prompts, provider or model
names/ids, sampling parameters, temperature, token counts, raw provider output,
or `CapabilityResult.raw_provider` (internal only). The wire carries only the
typed recommendation fields + container provenance (`engine_version`). A
provider being used is never an API fact. Errors carry only allow-listed
details (§7).

---

## 5. The common contract in the endpoint catalog (reference, not re-defined)

The endpoints are owned by their sibling docs. This table shows how each
surface delivers the `Recommendation` envelope and where the type-specific
fields live:

| Type | Endpoint(s) | Delivery | Container | Envelope core present | Type-specific block |
| --- | --- | --- | --- | --- | --- |
| hairstyle | `POST /v1/analysis/hairstyle` → `GET /v1/analysis/runs/{run_id}` | Shape A (async run) | `result.context` + `result.recommendations{top,alternatives}` | `id/name/description/matchScore/reasons` | styling tips/maintenance/best-for (§4.3) |
| grooming | `POST /v1/analysis/grooming` → run read | Shape A (async run) | `result.context` + `result.recommendations{top,alternatives}` | `id/name/description/matchScore/reasons` | beard/cheekline/eyewear details (§4.3) |
| outfit (analysis) | `POST /v1/analysis/outfit` → run read | Shape A (async run) | `result.sections[]` + `result.detectedItems[]` | **not a `Recommendation`** — analysis sections with per-section `score` (§3.2) | — |
| outfit (generation) | `POST /v1/outfits/generate` | Shape B (sync) | bare `OutfitRecommendation` | `title/description/matchScore/reasons` | components + harmony/fit/occasion (§4.3) |
| event styling | `POST /v1/events/{event_id}/outfit` | Shape B (sync) | bare `OutfitRecommendation` (same DTO) | `title/description/matchScore/reasons` | same as outfit (§4.3) |
| daily outfit | `GET|POST /v1/looks/today` | Shape B (sync) | bare `TodayLook` | `title/description/matchScore(0-100)/reasons` | weather/styleScore/insights/alternatives (§4.3) |
| discover look | `GET /v1/looks`, `GET /v1/looks/{look_id}` | Shape B (sync, feed) | `LookFeed` envelope / bare `LookDetail` | `id/title/description/matchScore(0-100)/recommendationReasons` | ensemble + tags + `isOwned` (§4.3) |
| wardrobe | `GET /v1/wardrobe/insight` | Shape B (sync) | bare `WardrobeInsight` | `title` (lightweight; no score today) | `insight/action/route` (§4.3) |

### 5.1 The common recommendation flow (a sequence of the accepted endpoints — no new endpoint)

```
analyse (async):  POST /v1/analysis/{outfit|hairstyle|grooming} ──202 {run_id}──► poll GET /v1/analysis/runs/{run_id}
                    └─ result: { context?, recommendations: { top, alternatives } }     (Shape A; TRX-5)
generate (sync):  POST /v1/outfits/generate  |  POST /v1/events/{id}/outfit  |  GET|POST /v1/looks/today
                    └─ OutfitRecommendation / TodayLook                                  (Shape B; TRX-2/7)
derive (feed):    GET /v1/looks  |  GET /v1/looks/{look_id}   →  LookFeed / LookDetail   (read-only, BAR-0)
wardrobe insight: GET /v1/wardrobe/insight                     →  WardrobeInsight        (204 when empty)
all types ────────────────────────────────────────────────────────────────────────►
save (any type):  POST /v1/looks/saved (snapshot = the type DTO verbatim + sourceContext) ──TRX-3 frozen snapshot + look_saved
feedback (gated): POST /v1/feedback (targetLookId | targetSavedLookId)  ── raw event, never rewrites the run/snapshot/ranking
history (P3):     recommendation_history trace (conditional)  |  runs history (GET /v1/analysis/runs, analysis family)
```

---

## 6. Validation reference (shared, common fields)

| Field | Rules | Source |
| --- | --- | --- |
| `id` | valid catalog `looks.code` when catalog-backed (PR-3); UUID when generated; the reference for save (`lookId`) and feedback (`targetLookId`) | TABLE_DEFINITIONS `looks` |
| `type` / `sourceContext` | one of the §3.1 vocabulary codes; server-validated on save | §4.6, UC-15 |
| `title` / `name` | non-empty, bounded (`[1,200]` on save) | BC-11 |
| `description` | grounded explanation; never invented (Explanation stage) | DECISION_ENGINE §5.6 |
| `matchScore` | `0..1` (analysis/ensemble) or `0–100` int (derived-look); derived, never client-authored | Scoring stage, §4.4 |
| `confidence` / `tradeOffs` / `expiresAt` | absent today; additive/FUTURE only | AI-0, VALUE_OBJECTS §3.3, §4.5/§4.6 |
| `reasons[]` | grounded bullets (or structured `{title, description}` for discover); length-bounded | Explanation stage |
| `snapshot` (save) | the type DTO verbatim; structural validity of ensemble refs validated at save time | R31, BC-59 |
| `rating` (feedback) | accepted vocabulary — **pending** (§8) | UC-32, feedback design |
| `page`/`page_size` | `[1,100]` (lists) / `cursor`+`limit` (feeds) | API-21/22 |

All validation is **server-side** (Flutter never enforces security) and returns
the **safe client message**, never internals (ER-2).

---

## 7. Error reference (shared)

| `error.code` | HTTP | When | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | poor image / no face / invalid type or fields on any surface | field errors + allowed values in `details` |
| `MEDIA_FAILURE` | 413/422 | image too large / unsupported content-type (analysis family) | `details.maxBytes`; pre-run check |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | run/look/event not owned or never existed | 404-not-403, no existence leak |
| `CONFLICT` | 409 | duplicate save | `details.kind="duplicate"` |
| `EXTERNAL_SERVICE_FAILURE` | 502/503 | AI provider / generation failure | C-8: no provider internals |
| `PROCESSING_FAILURE` | 500 (sync) / run `failed` | pipeline failure (after the 1 automatic retry) | `details.run_id`; the run is a historical failure |
| `RATE_LIMITED` | 429 | any endpoint | + `Retry-After` |

---

## 8. Open decisions (carried forward, unchanged where already recorded)

1. **D-AUTH-1 — auth provider** — unchanged; gates mounting the M12 analysis
   surface (endpoints stay unmounted until the seam lands, API-12).
2. **MS10.3 — media seal** — image submissions (`multipart` → `MediaRef`)
   depend on M16 unsealing; until then the analysis submits are not mounted
   (API-12). No fake 200 before either gate lifts.
3. **Feedback UI + rating vocabulary** — `POST /v1/feedback` (UC-32) is gated
   on an accepted feedback UI (M11); the `rating` vocabulary is defined by the
   feedback design (PR-12).
4. **Trade-offs / warnings catalog** — `tradeOffs` is additive-only (§4.5);
   the envelope reserves the field so all four families adopt it without a
   format change when the domain defines a grounded catalog.
5. **Score-scale normalization** — `matchScore` is 0..1 (analysis/ensemble) vs
   0–100 (derived-look) today (§4.4). Unifying to one scale is an open decision;
   never a silent wire change (API-2). Wardrobe insight has no score today.
6. **`expiresAt` / content validity** — not modeled (§4.6); additive if a
   content-validity feature ships. Media expiry is a storage concern, not an
   API field.
7. **`sourceContext`/`type` vocabulary** — consolidated in §3.1; the exact
   stored set and whether `type` becomes a first-class envelope field at
   implementation is open.
8. **Per-item `createdAt`** — container-level today (§4.6); per-item is
   additive-only.
9. **`recommendation_history` (P3)** — shown/saved trace is conditional; TRX-3
   flips its `saved` flag only when the table exists. Not part of this
   contract.
10. All other open decisions from `API_CONTRACT_RULES.md` §16,
    `HAIRSTYLE_RECOMMENDATION_API.md` §8, `SCAN_API.md` §8, and
    `APPEARANCE_API.md` §8 remain open and are unaffected.

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/RECOMMENDATION_API.md` — the
**common recommendation API contract**. It defines the single `Recommendation`
envelope (§4.1) satisfying the task's ten common fields — recommendation ID,
type, title, description, score, confidence, reasons, warnings/trade-offs,
created_at, expires_at — mapped honestly to the frozen wire (§4.2), the
**type matrix** showing the six task types + discover look collapse to **four
DTO families over one envelope** (§3.3), the **type-specific fields** each
surface adds (§4.3), and the uniform cross-type save/feedback/history
operations (§4.8) that are the mechanism preventing incompatible per-type
formats. Nothing is implemented; no endpoint is added; no frozen shape is
renamed.

**Skills used:** repository + documentation analysis (all seven real mock
shapes — `hairstyle_mock_data.dart`, `grooming_mock_data.dart`,
`outfit_builder_mock_data.dart`, `outfit_scan_mock_data.dart`,
`daily_outfit_mock_data.dart`, `discover_mock_data.dart`,
`wardrobe_mock_data.dart`; `saved_looks`/`looks`/`analysis_runs`/
`recommendation_history` tables; TRX-2/3/5/7; UC-14/15/16/21/24–32;
DECISION_ENGINE stages 4–8; AI_INTEGRATION AI-0; API_CONTRACT_RULES
§12.6/§12.10–§12.13/§8.3/§13.3; API_INVENTORY endpoints 15/23–25/30–33/35/
37–44; ERROR_HANDLING taxonomy; and the sibling contracts
HAIRSTYLE_RECOMMENDATION_API/SCAN_API/APPEARANCE_API) — documentation only.

**Files changed:** `docs/api/RECOMMENDATION_API.md` (new); `CURRENT_STATE.md`
(status).

**Validation run:**
- **Every type traces 1:1 to a real surface + an accepted endpoint.**
  hairstyle→`POST /v1/analysis/hairstyle` (endpoint 37), grooming→38,
  outfit analysis→36/39, outfit generation→41, event→30, daily→31/32, look→43/44,
  wardrobe→15, save→23, feedback→35 (gated). Paths/methods/auth/UC/errors
  identical to `API_CONTRACT_RULES.md` and `API_INVENTORY.md`; no invented
  endpoints (recommendation resource family, per-type save/feedback explicitly
  excluded, §3.3).
- **Wire shapes match the accepted sketches AND the real mock data.** The
  envelope mapping (§4.2) is a translation table, not a rename: every frozen
  field keeps its exact wire name/type (hairstyle/grooming identical to
  APPEARANCE_API §5.1/§5.2; `OutfitRecommendation` identical to the catalog
  and `outfit_builder_mock_data.dart`; discover/daily identical to their mock
  data). The task's ten common fields are mapped to the wire in a table with
  `confidence`, `tradeOffs`, and `expiresAt` honestly marked absent/FUTURE
  (AI-0) — not fabricated.
- **"One envelope, four families" is demonstrated from the real shapes**, not
  asserted: the shared core fields (`id`/title/description/score/reasons) were
  verified present in every family's mock DTO; grooming is hairstyle + 4
  fields; event styling reuses `OutfitRecommendation`; daily and discover share
  the derived-look shape; wardrobe is the lightweight insight. §4.3.
- **No-internals and AI-output-never-truth enforced** (§4.9, §3.2): no
  `Recommendation` table/resource (BAR-0); durable forms are the run result
  (TRX-5) and the save snapshot (TRX-3); save/feedback never mutate a run; no
  prompts, provider/model names, or raw provider output on the wire.
- **Auth/authorization/errors consistent** — all endpoints auth + owner-only
  (OW-1, 404-not-403); frozen 12-category errors; submissions never idempotent
  (§11), save idempotent (TRX-3), reads naturally idempotent.
- **`git status --short`:** `docs/api/` now holds API_CONTRACT_RULES.md,
  API_INVENTORY.md, AUTH_API.md, PROFILE_ONBOARDING_API.md, APPEARANCE_API.md,
  SCAN_API.md, HAIRSTYLE_RECOMMENDATION_API.md, RECOMMENDATION_API.md
  (untracked) + `CURRENT_STATE.md`; no code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- The M12 analysis endpoints are **not mounted** until D-AUTH-1 + the media/
  analysis pipeline exist (API-12 — no fake 200). Feedback is **gated** (M11).
- Confidence, trade-offs, per-item `createdAt`, `expiresAt`, score-scale
  normalization, and the P3 `recommendation_history` trace are
  additive/FUTURE (§8.4–§8.9).
- Other open decisions unchanged: auth provider (D-AUTH-1), User fields,
  Today'sLookRecord (P1), RecommendationHistory (P3), conversation retention,
  K9.1 knowledge shape, media-privacy (MS10.3), feedback design.

**Assumptions recorded:**
- "Common recommendation API contract" = one semantic envelope + four
  family-frozen DTO shapes + type-agnostic save/feedback/history — the minimal
  design that satisfies the task's "avoid incompatible formats" requirement
  without renaming any accepted wire field.
- `type` is derived from the surface and stamped via `sourceContext` at save
  time; it is not a new per-DTO stored field on the frozen shapes.
- Score scales are documented as-is (0..1 vs 0–100); unification is an open
  decision, never a silent change.
- `expiresAt` refers to recommendation content validity only; raw-media
  retention is a storage concern, not an API field.
- The discover look is a read-only presentation of knowledge + learning
  (BAR-0), included because it is a recommendation surface; it is not a
  generation surface.

**Constraints honored:** no implementation, the live assistant contract
untouched (F-5), no invented endpoints, run/DTO shapes kept identical to the
accepted contract and sibling docs, the no-internals rule enforced, the UI
Change Safety Rule (no UI touched), and the Scope rule (this document +
`CURRENT_STATE.md` only).
