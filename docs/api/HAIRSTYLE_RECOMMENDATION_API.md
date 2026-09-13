# Fansivibe — API Contract: Hairstyle Recommendations

> **STEP 6 — API CONTRACT DESIGN.** Defines the **field-level API contract for
> the hairstyle recommendation surface** — the operations that request, poll,
> retrieve, detail, save, feed back on, and regenerate hairstyle
> recommendations, and the **recommendation response contract** (ID, hairstyle
> info, score, confidence, explanation, reasons, trade-offs, profile context,
> model/version metadata). It is the focused companion to `API_CONTRACT_RULES.md`
> (§12.11 analysis, §12.6 saved looks, §12.10 feedback, §8.3 async run object)
> and `API_INVENTORY.md` (endpoints 17/23–25/35/37/39/40), and it sits beside
> the sibling contracts `APPEARANCE_API.md` (A-1, the same hairstyle
> submission), `SCAN_API.md` (S-2, the face→hairstyle scan), and
> `PROFILE_ONBOARDING_API.md` (the profile reads/writes this surface
> references).
>
> **Status: contract design only. Hairstyle recommendations are NOT
> implemented.** No code, no `deps.py`, no routers, no SQL, no AI providers, no
> Flutter changes, no dependencies. The live contract (`GET /health`,
> `POST /v1/assistant/chat`) is preserved unchanged. The analysis endpoints are
> P2 and stay **unmounted** until the auth seam (D-AUTH-1), the media seal
> (MS10.3), and a real analysis pipeline land (API-12); feedback (M11) is
> **feature-gated** and **not mounted**.
>
> **Source of truth:** the real Fansivibe repository and the accepted docs —
> STEP 2 `ACTION_API_INVENTORY.md` (actions 21/22), STEP 3
> `FANSIVIBE_DOMAIN_MODEL_V1.md` (E4 `SavedLook`, E5 `Look`, E6 `AnalysisRun`),
> STEP 4 `TABLE_DEFINITIONS.md` (`analysis_runs`, `saved_looks`, `looks`,
> `feedback_events`*, `recommendation_history`* P3) + `HISTORY_AND_VERSIONING.md`
> (§5.7/§5.8/§5.9) + `TRANSACTION_BOUNDARIES.md` (TRX-3, TRX-5, TRX-6),
> STEP 5 `APPLICATION_USE_CASES.md` (UC-15/25/26/32),
> `DECISION_ENGINE_ARCHITECTURE.md` (stages 5–8: Scoring, Ranking, Explanation,
> Recommendation, Feedback), `AI_INTEGRATION_ARCHITECTURE.md`
> (`HairAnalysisProvider` FUTURE, `CapabilityResult`, AI-0),
> `BACKGROUND_JOB_ARCHITECTURE.md` (§5 job lifecycle), `ERROR_HANDLING.md`
> (12-category taxonomy), STEP 6 `API_CONTRACT_RULES.md` (catalog §12.11/
> §12.6/§12.10, async §8.3, DTO sketches §13) + `API_INVENTORY.md` (endpoints
> 23–25/35/37/39/40), `APPEARANCE_API.md` (A-1/A-3/A-4 — shared submission +
> run reads), and `SCAN_API.md` (S-2 — the face→hairstyle scan lifecycle).

---

## 1. Purpose and scope

This document defines, for every **required hairstyle-recommendation
operation**, the contract attributes the STEP 6 design task asks for:

1. **method**
2. **path**
3. **request schema**
4. **response schema**
5. **authentication requirements**
6. **validation**
7. **errors**
8. **asynchronous behavior**

(plus security considerations, side effects, and domain entities, following
the same convention as the sibling contracts).

The task's operation list is covered operation by operation (§5):

- **creating a hairstyle recommendation request** — §5.1
- **processing status if asynchronous** — §5.2
- **retrieving recommendations** — §5.3
- **retrieving recommendation details** — §5.4
- **saving a recommendation** — §5.5
- **submitting feedback** — §5.6
- **regenerating recommendations if supported** — §5.7

and the **recommendation response contract** (ID, hairstyle information, score,
confidence, explanation, reasons, trade-offs, profile context, model/version
metadata) is defined in §4.3–§4.5 — the single DTO all reads and saves use.

**The two binding design rules of this document:**

1. **A hairstyle recommendation is AI output, never truth** (BAR-0). The
   recommendation is a **value object** produced by the decision engine
   (stages 5–8) from the face profile × the hairstyle catalog; its durable
   forms are the immutable run `result` (TRX-5) and the immutable `SavedLook`
   snapshot (TRX-3). There is **no `Recommendation` table** and no "current
   recommendation" resource — regenerate always produces a **new** run
   (`HISTORY_AND_VERSIONING.md` §5.7/§5.8).
2. **The wire never exposes internals.** No prompts, no provider names, no
   model/sampling parameters, no raw provider output — only the typed
   recommendation fields + `engine_version` provenance (C-8, ER-0/ER-2, F-7,
   AI-0; `CapabilityResult.raw_provider` is internal only). §4.8.

**What it does not do:** implement the analysis module (M12), the saved-look
module (M7), or the feedback module (M11 — feature-gated, not mounted), write
AI providers, modify Flutter, or change the frozen assistant DTOs. The shared
submission and run reads (`POST /v1/analysis/hairstyle`,
`GET /v1/analysis/runs/{run_id}`, `GET /v1/analysis/runs`) are defined in full
in `APPEARANCE_API.md` §5.1/§5.3/§5.4 and `SCAN_API.md` §5.2/§5.5 — this doc
**re-states them in the recommendation vocabulary and keeps the shapes
identical**; it does not re-own them. Save (`POST /v1/looks/saved`), feedback
(`POST /v1/feedback`), and profile reads (`GET /v1/users/me`) are **referenced,
not re-defined**.

### 1.1 Grounding facts (re-verified)

- **The request IS an async analysis run.** `POST /v1/analysis/hairstyle`
  (UC-25 `AnalyzeAppearance` + UC-26 `GenerateHairstyleRecommendations`,
  endpoint 37, action 21) creates an `AnalysisRun` (run_type `hairstyle`) in
  `pending`; the client polls `GET /v1/analysis/runs/{run_id}` until
  `completed | failed` (API-41/42, TRX-5 write-once). Each submission is a new
  run — never idempotent (`API_CONTRACT_RULES.md` §11).
- **The recommendation lives in the run result.** The completed result carries
  `appearance` (the face attributes the recommendations were grounded on) +
  `recommendations: { top, alternatives }` — mirroring `HairstyleAnalysisResult`
  (`hairstyle_mock_data.dart:88-192`). Every `HairstyleRecommendation` carries
  `id, name, description, matchScore, reasons[], stylingTips, maintenance,
  bestFor` (`hairstyle_mock_data.dart:64-86`).
- **Recommendation id = the catalog look code (PR-3).** The mock ids
  (`textured_quiff`, `classic_pompadour`, …) are stable natural keys over the
  E5 `Look` catalog (`TABLE_DEFINITIONS.md` `looks.code`), mirrored in
  `catalog.py`. The id is stable, backend-authored, survives re-seeds, and is
  the reference used by save (`lookId`) and feedback (`targetLookId`).
- **Score is a match score; confidence is NOT computed.** `matchScore` (0..1)
  is a scoring-stage value over profile × catalog
  (`VALUE_OBJECTS.md` §3.2). **Confidence is never computed today** — scores
  are catalog constants (`AI_DATA_FLOW.md` Part D.3, `VALUE_OBJECTS.md` §3.3).
  Confidence is an *optional future field*, absent from responses (AI-0).
- **Explanation and reasons are grounded, never invented.** The engine's
  Explanation stage produces per-candidate "title + reasons + CTA text"
  grounded in score signals / a validated reason catalog
  (`DECISION_ENGINE_ARCHITECTURE.md` §5.6). The wire `description` is the
  explanation text; `reasons[]` are the grounded bullet reasons. **Trade-offs
  are not modeled anywhere in the domain or the mock** — the field is additive
  only, and absent today (§4.3).
- **Profile context and provenance are explicit.** The run result's
  `appearance` block (`faceShape?`, `skinTone?`, `bodyType?`, `styleType?`,
  `sourceRunId`) is the relevant profile context; the run carries
  `engine_version` (provenance, PR-6) and optionally internal `model_version`
  (never surfaced raw, C-8). The current accepted profile is read from
  `GET /v1/users/me` (`ProfileView.styleProfile`, R-1 — referenced).
- **Save is the only durable keeper.** `POST /v1/looks/saved` (UC-15, endpoint
  23, M7) freezes an immutable snapshot (score/reasons) + `look_saved` signal in
  **one transaction** (TRX-3); `source_run_id` links back to the scan
  (`TABLE_DEFINITIONS.md` `saved_looks`). `recommendation_history` (shown/saved
  trace) is **P3, conditional** — not part of this contract.
- **Feedback is feature-gated.** `POST /v1/feedback` (UC-32, endpoint 35, M11)
  is **not mounted** until a feedback UI is accepted (API-12); `feedback_events`
  has no table until then (PR-12). The rating vocabulary is **pending** (§8).
  The assistant card-interaction signal (`POST /v1/assistant/feedback`, UC-23)
  is a *separate*, live-adjacent path for card opened/navigated — referenced,
  not this surface's feedback.
- **Regeneration is not a distinct operation.** There is no
  `RegenerateHairstyle` use case (only UC-29 `RegenerateOutfit`, M13). Regenerate
  = a **new** `POST /v1/analysis/hairstyle` (a new run), and the profile-only
  pass (empty body, no reference field — Phase 28) is the natural re-rank path over the
  stored style_profile (by `user_id`) — consistent with re-scan = new run
  (`HISTORY_AND_VERSIONING.md` §5.7, `SCAN_API.md` §5.6).
- **The hair *profile* is PLANNED, not data** — the same decision as
  `APPEARANCE_API.md` §3.1: no `hair-profile` resource exists; the run is the
  history, and a future hair profile would follow the Face Profile pattern.

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `ACTION_API_INVENTORY.md` | Actions 21 (generate hairstyle recommendation) and 22 (save hairstyle style) → the future endpoints + error conditions + AUTH. |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | E4 `SavedLook` (immutable snapshot), E5 `Look` (hairstyle catalog, stable codes), E6 `AnalysisRun` (the run), E7 `LearningSignal`. |
| `hairstyle_mock_data.dart` | The real `HairstyleRecommendation` / `HairstyleAnalysisResult` shapes the wire mirrors (`id/name/description/matchScore/reasons/stylingTips/maintenance/bestFor`; `appearance` + `top` + `alternatives`). |
| `TABLE_DEFINITIONS.md` | `analysis_runs` (run_type `hairstyle`, status/result/engine_version), `saved_looks` (snapshot, `source_run_id`), `looks` (code/title/payload), `feedback_events`* / `recommendation_history`* P3 (conditional). |
| `HISTORY_AND_VERSIONING.md` | §5.7 scans + §5.8 recommendations + §5.9 feedback: AI output is regenerable, never stored as truth; the durable trace is the save/snapshot. |
| `TRANSACTION_BOUNDARIES.md` | TRX-3 (saved_looks + signal true transaction), TRX-5 (run write-once), TRX-6 (profile projection). |
| `DECISION_ENGINE_ARCHITECTURE.md` | Stages 5–8: Scoring (matchScore), Ranking (top + alternatives), Explanation (grounded reasons, never invented), Recommendation (typed deliverable), Feedback (signal shape, never writes). |
| `AI_INTEGRATION_ARCHITECTURE.md` | `HairAnalysisProvider`/`FaceAnalysisProvider` FUTURE; `CapabilityResult` (status/output/confidence/model_version/raw_provider — raw_provider internal only); AI-0/AI-5/AI-6. |
| `APPLICATION_USE_CASES.md` | UC-25 `AnalyzeAppearance`, UC-26 `GenerateHairstyleRecommendations`, UC-15 `SaveRecommendation`, UC-32 `SubmitRecommendationFeedback` (gated). |
| `BACKGROUND_JOB_ARCHITECTURE.md` | §5 job lifecycle (creation, status pending→completed\|failed, retry, timeout, result persistence). |
| `API_CONTRACT_RULES.md` | Catalog §12.11 (§12.6 saved looks, §12.10 feedback), async §8.3, DTO sketches §13, error §9, idempotency §11, C-8/C-10/C-16. |
| `API_INVENTORY.md` | Endpoints 17/23–25/35/37/39/40; related domain entities per endpoint. |
| `APPEARANCE_API.md` / `SCAN_API.md` | The shared submission (A-1/S-2) and run reads (A-3/A-4, S-5/S-9) — shapes kept identical; `appearance` profile context semantics. |
| `PROFILE_ONBOARDING_API.md` / `AUTH_API.md` | P-2 `PATCH /users/me` (`sourceRunId` rules), R-1 `GET /users/me` — the current profile reads/writes — referenced. |
| `ERROR_HANDLING.md` | 12-category taxonomy: VALIDATION_ERROR (422), AUTHENTICATION_ERROR (401), NOT_FOUND (404), MEDIA_FAILURE (413/422), EXTERNAL_SERVICE_FAILURE (503), PROCESSING_FAILURE (run `failed`), RATE_LIMITED (429). |

---

## 3. Operation selection (define only the required operations)

| # | Candidate operation | Decision | Justification |
| --- | --- | --- | --- |
| H-1 | **Create hairstyle recommendation request** | **Required** — `POST /v1/analysis/hairstyle` | UC-25/26, endpoint 37, action 21. Face image (or profile) → async run → appearance attributes + top/alternative hairstyle recommendations. §5.1. |
| H-2 | **Processing status** | **Required** — `GET /v1/analysis/runs/{run_id}` | Endpoint 39, the polling read; `pending → completed | failed` (TRX-5). §5.2. |
| H-3 | **Retrieve recommendations** | **Required** — `GET /v1/analysis/runs/{run_id}` (`completed`) | The same read; the completed `result` carries the full recommendation set (top + alternatives). §5.3. |
| H-4 | **Retrieve recommendation details** | **Required — within the run result; no separate endpoint** | A recommendation's full detail (description, reasons, styling tips, maintenance, best-for, score) **is** the result snapshot — the details screen reads the same object (`hairstyle_details_screen.dart`). §5.4. |
| H-5 | **Save a recommendation** | **Required (referenced)** — `POST /v1/looks/saved` | UC-15, endpoint 23, action 22. Freezes an immutable snapshot + `look_saved` signal (TRX-3); `source_run_id` provenance. Owned by M7 — referenced, not re-defined. §5.5. |
| H-6 | **Submit feedback** | **Required (referenced, gated)** — `POST /v1/feedback` | UC-32, endpoint 35, action 31. **Not mounted** until a feedback UI is accepted (M11, API-12); `feedback_events` has no table until then. Referenced. §5.6. |
| H-7 | **Regenerate recommendations** | **Pattern, no endpoint** | No `RegenerateHairstyle` UC exists — regenerate = a **new** submission (new run); the profile-only pass (empty body, Phase 28) is the re-rank path. §5.7. |
| — | **Hair *profile* read/write** | **NOT defined now** | PLANNED domain target, no tables (`APPEARANCE_API.md` §3.1). The run is the history. |
| — | **Dedicated "recommendation" resource** (`GET /v1/recommendations/…`) | **NOT defined** | No `Recommendation` entity/table — recommendations are regenerable AI output (BAR-0); occurrence = run + save. |

### 3.1 What the recommendation surface is (and is not)

The hairstyle recommendation surface is the **analysis run + the durable save**:

```
request (H-1) → run (pending) → poll (H-2) → completed result (H-3/H-4)
                                              ├─ recommendations { top, alternatives }  ← retrievable/detailed
                                              └─ appearance (profile context)            ← grounded the ranking
regenerate (H-7) → a NEW run (new result — the old result stays immutable history)
save (H-5) → SavedLook snapshot (the ONLY durable keeper of the recommendation)
feedback (H-6) → feedback_events (P1, gated) — a raw user event, not a truth change
```

There is **no** mutable "current recommendation" the client can read or edit;
there is **no** recommendation table; there is **no** dedicated
`/v1/recommendations/*` resource (BAR-0, `TABLE_DEFINITIONS.md` §8). Everything
below stays inside the accepted inventory.

---

## 4. Shared semantics (apply to every operation below)

### 4.1 Base URL, headers, format

- All endpoints under `/v1` (API-1); JSON bodies `application/json;
  charset=UTF-8`; keys camelCase; timestamps ISO-8601 UTC (API-19). Image
  submissions use `multipart/form-data` with the `image` part (API-36) —
  binary never base64'd into JSON.
- Protected endpoints send `Authorization: Bearer <token>` (API-5). Missing /
  invalid / expired / revoked → `401 AUTHENTICATION_ERROR` +
  `WWW-Authenticate: Bearer` (API-7, ERROR_HANDLING §5.2).
- **No `Idempotency-Key`** on the recommendation request (each call = a new
  run, §11). Save (H-5) **requires** `Idempotency-Key` (TRX-3); feedback (H-6)
  requires it when it ships.
- Every response echoes `X-Request-Id` (OBSERVABILITY §4.1).

### 4.2 The async run and its status

A recommendation request is **async** (the only async surface; sync-by-default,
API-40). Submission returns `202 Accepted` immediately:

```json
{ "run_id": "7a2b3c…" }
```

The client polls `GET /v1/analysis/runs/{run_id}` (H-2) until `status ∈ {
completed, failed }`, then reads the result (H-3/H-4). The task's lifecycle
maps to the frozen wire status exactly as in `SCAN_API.md` §4.2
(CREATED/PROCESSING → `pending`; COMPLETED → `completed`; FAILED → `failed`),
completion is **write-once** (TRX-5, PR-6), and the request is **never
idempotent** (a retried/regenerated submission is a distinct historical run).

```
AnalysisRun {
  run_id*,          // UUID
  run_type*,        // "hairstyle"
  status*,          // "pending" | "completed" | "failed"
  created_at*,      // ISO-8601 UTC
  completed_at?,    // present when completed | failed
  engine_version?,  // provenance — present when completed (PR-6)
  input_media?,     // MediaRef to the face image (when an image was submitted)
  result?,          // immutable snapshot — present ONLY when completed
  error?            // frozen error body — present ONLY when failed
}
```

### 4.3 The recommendation response contract (the task's field list)

Every hairstyle recommendation — the `top` pick, each `alternative`, and the
saved `Snapshot` — uses one DTO. The task's required fields map to the wire as
follows (wire shape mirrors `HairstyleRecommendation`,
`hairstyle_mock_data.dart:64-86`):

```
HairstyleRecommendation {
  id*,              // recommendation ID — the stable catalog look code (PR-3)
                    //   e.g. "textured_quiff"; referenced by save (`lookId`) and feedback (`targetLookId`)
  name*,            // hairstyle information — display name
  description*,     // explanation — why this suits the user (Explanation stage; grounded, never invented)
  matchScore*,      // score — 0..1 (Scoring stage, profile × catalog)
  confidence?,      // FUTURE — NOT computed today (AI-0); optional field, absent from responses
  reasons*,         // string[] — grounded reasons (reason catalog; never invented text)
  stylingTips*,     // hairstyle information — how to style
  maintenance*,     // hairstyle information — upkeep effort
  bestFor*,         // hairstyle information — face shapes it suits
  tradeOffs?,       // NOT modeled today — additive only; absent until a grounded reason catalog defines it
  engineVersion?,   // model/version metadata — run-level provenance (PR-6); optional per-item
}
```

Field-by-field (task item → contract semantics):

| Task requirement | Wire field | Status |
| --- | --- | --- |
| recommendation ID | `id` (catalog code) | **present**, required — stable, backend-authored (PR-3) |
| hairstyle information | `name`, `description`, `stylingTips`, `maintenance`, `bestFor` | **present**, required |
| score | `matchScore` (0..1) | **present**, required (Scoring stage) |
| confidence | `confidence` | **not computed today** (AI-0); optional FUTURE field, absent from responses |
| explanation | `description` (the why-this-suits-you narrative) | **present**, required (Explanation stage) |
| reasons | `reasons[]` (grounded bullets) | **present**, required |
| trade-offs (if available) | `tradeOffs` | **not modeled today** — additive, absent until the domain defines a grounded trade-off catalog |
| relevant profile context | run result `appearance` block + current `StyleProfile` (R-1, Phase 28: no reference field) | **present** at the run level (§4.5) |
| model/version metadata | `engine_version` (run), internal `model_version` | **present** at the run level; internals never surfaced raw (§4.5/§4.8) |

**Honesty rule (AI-0):** a field the domain does not compute today is either
absent (`confidence`) or documented as additive-only (`tradeOffs`) — never
fabricated, never a guessed value.

### 4.4 Scoring, confidence, explanation, reasons

- **Score** (`matchScore`) is a **deterministic scoring-stage value** over
  profile (face shape/skin tone/style DNA) × the hairstyle catalog
  (`DECISION_ENGINE_ARCHITECTURE.md` §5.4; today's rules-based engine tools).
  It is never client-authored and never edited post-creation.
- **Confidence** is a value object (`VALUE_OBJECTS.md` §3.3) that is **not
  computed today** (`AI_DATA_FLOW.md` Part D.3). When a real model computes it
  it appears as an optional `0..1` field inside the result — never an endpoint
  and never a substitute for the match score.
- **Explanation** is the `description` — the human "why this suits you" from
  the Explanation stage, **always grounded in score signals or a validated
  reason catalog**; the engine may let the LLM rewrite *wording only*, never
  structure or scores (BA-8, `DECISION_ENGINE_ARCHITECTURE.md` §5.6).
- **Reasons** (`reasons[]`) are the grounded bullet reasons — same
  never-invented rule. If the LLM enriches text, it enriches only text.

### 4.5 Profile context and model/version metadata

**Relevant profile context** for a hairstyle recommendation is carried at the
run level (the completed `result`):

```
result {
  appearance: {                    // the face attributes the ranking was grounded on
    faceShape?, skinTone?, bodyType?, styleType?,
    confidence?: { value: 0..1, scope: "face" },   // FUTURE; absent today (AI-0)
    sourceRunId,                   // = this run_id (provenance)
  },
  recommendations: {
    top: HairstyleRecommendation,
    alternatives: HairstyleRecommendation[],
  }
}
```

The **current** accepted profile (the user's style DNA view) is read from
`GET /v1/users/me` → `ProfileView.styleProfile` (R-1, `APPEARANCE_API.md` §5.5,
referenced) — it is disjoint from the run's snapshot (§4.4 of
`APPEARANCE_API.md`). A profile-only request carries no reference field (Phase 28); the source is the authenticated user's stored style_profile by user_id.

**Model/version metadata** (provenance, PR-6): the run carries `engine_version`
(exposed), and the pipeline records an internal `model_version` per capability
(`AI_INTEGRATION_ARCHITECTURE.md` §5 `CapabilityResult`) — recorded for audit
but **never exposed by name/model id** (C-8, §4.8). No model/version guess.

### 4.6 Save and feedback semantics

- **Save (H-5) is the only durable keeper.** Saving freezes the recommendation
  into an immutable `SavedLook` snapshot (score + reasons at save time, R31)
  plus the `look_saved` learning signal in **one true transaction** (TRX-3);
  `source_run_id` links the save back to the producing run. Saving does **not**
  alter the run and does **not** create a "current recommendation".
- **Feedback (H-6) is a raw user event, not a truth change.** A rating/comment
  lands in `feedback_events` (append-only) and feeds the derived-preference
  loop; it never rewrites the run, the snapshot, or the ranking directly
  (`DECISION_ENGINE_ARCHITECTURE.md` §5.8; single feedback never flips a hard
  rule). M11 is **gated**: no table, no endpoint until a feedback UI ships.

### 4.7 Error body (frozen, API-28)

```
{ "error": { "code": "<one of the 12>", "message": "<safe client message>", "details": {...} } }
```

`details` is allow-listed only (ER-1): field errors + allowed values (422),
`maxBytes` (413), `run_id` (own run only), `request_id` (500). **Never** the
user's face image, prompts, provider/model names, raw provider responses, or
reasoning traces (C-7/C-8, ER-0/ER-2, AI-0).

### 4.8 Auth, ownership, privacy — and the no-internals rule

| Requirement | Endpoints |
| --- | --- |
| **Auth** (Bearer → `user_id`) | `POST /v1/analysis/hairstyle`, `GET /v1/analysis/runs/{run_id}`, `GET /v1/analysis/runs`, `POST /v1/looks/saved`, `POST /v1/feedback` (when mounted). |
| **Public** | none in this surface. |

Authorization is **owner-only (OW-1)** with **404-not-403** (API-10): every run
and every saved look is scoped to the caller's `user_id`; another user's (or a
non-existent) `run_id`/`saved_look_id` → `404`. Face media and face-derived
attributes are **CRITICAL** appearance data (`SECURITY_PRIVACY_DESIGN.md` §3):
HTTPS only, image bytes never logged/echoed, only the `MediaRef` travels
(MS10.3, ER-4).

**The no-internals rule (binding, C-8/ER-0/F-7/AI-0):** the response never
contains — and the client never sees — **internal AI prompts**, provider or
model **names/ids**, sampling parameters, temperature, token counts, raw
provider output, or the `CapabilityResult.raw_provider` field (which is
internal only, `AI_INTEGRATION_ARCHITECTURE.md` §5). The wire carries only the
typed recommendation fields + `engine_version`; errors carry only allow-listed
details. A provider being used is never an API fact.

---

## 5. Operation contracts

### 5.1 H-1 — Create a hairstyle recommendation request (`AnalyzeAppearance` UC-25 / `GenerateHairstyleRecommendations` UC-26)

- **Method / path:** `POST /v1/analysis/hairstyle` (endpoint 37, action 21)
- **Asynchronous behavior:** **async** — `202 Accepted` + `run_id`; poll H-2
  until `completed | failed`. Each submission is a new run (never idempotent).
- **Request schema** (`multipart/form-data`, Phase 28: no face-profile reference — identical to `APPEARANCE_API.md`
  §5.1 and `SCAN_API.md` §5.2):

```
image:            <file>          // optional; face photo for the image pass (MediaRef after M16)
                                 // absent = profile-only pass over the authenticated user's stored style_profile (by user_id)
```

  - With an image: the run does UC-25 (face analysis → appearance attributes)
    then UC-26 (hairstyle recommendations) — one run, one result.
  - Without an image (profile-only, empty body): recommendation
    pass over the already-stored current profile (no new face attributes) —
    this is the **regenerate** path (§5.7).
- **Response schema:** `202 Accepted` — `AsyncAccepted { run_id* }` (bare, no
  envelope). The completed run's `result` (§4.3/§4.5).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1); face media is private.
- **Validation:**
  - Profile-only pass (no image) resolves the authenticated user's stored
    `style_profile` by `user_id`; missing face data → **422
    INSUFFICIENT_USER_DATA**. Image
    content-type/size checked pre-run → **413/422 MEDIA_FAILURE**.
  - No face detected / poor image → **422 VALIDATION_ERROR** (UC-25).
  - `run_type` produced = `hairstyle` (the endpoint's run_types code); a
    dedicated `face`-only run is reserved, not mounted.
- **Errors:** `202`; `401`; `404` (account gone); `413/422 MEDIA_FAILURE`;
  `422 VALIDATION_ERROR` (no face, invalid input, missing image); `503
  EXTERNAL_SERVICE_FAILURE` (provider — submission); on the poll, the run may
  be `status=failed` with `error.code = PROCESSING_FAILURE` (details.run_id);
  `429 RATE_LIMITED`.
- **Security considerations:** face media is CRITICAL — bytes only into the
  pipeline, stored as `MediaRef`, never logged/echoed (MS10.3, ER-4). Analysis-
  derived attributes are never client-authored truth (C-16). No prompts or
  provider details ever surface (§4.8).
- **Side effects:**
  - **History:** blob → object storage (TRX-1), then an `analysis_runs` row
    (run_type `hairstyle`, pending); completion writes the immutable `result` +
    `engine_version` once (TRX-5).
  - **Projection:** the completed face analysis **applies** the attributes to
    `user_state.style_profile` (latest-wins, TRX-6) — the run is untouched.
  - **Failure:** a failed run writes no `result` and no projection change;
    orphan blobs swept by the cleanup job (TRX-1 §5).
- **Domain entities involved:** E6 `AnalysisRun`; E1.1 `UserState.styleProfile`
  (FaceProfile projection + `sourceRunId`, written by TRX-6); E5 `Look`
  (hairstyle catalog, read-only); E7 `LearningSignal` (`analysis_updated`);
  `MediaRef`; value objects: FaceProfile, HairstyleRecommendation, Score,
  Confidence (FUTURE).

---

### 5.2 H-2 — Processing status (`GetAnalysisRun`)

- **Method / path:** `GET /v1/analysis/runs/{run_id}` (endpoint 39, action 21
  poll)
- **Asynchronous behavior:** **sync** — the polling read for the async
  submission. `status ∈ { pending, completed, failed }` (§4.2).
- **Request schema:** none (`run_id` UUID in path).
- **Response schema:** `200 OK` — `AnalysisRun` (bare; §4.2). While `pending`:
  only `run_id`, `run_type`, `status`, `created_at`. When `failed`: `status`,
  `created_at`, `completed_at`, `error`; no `result`.
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  — another user's / non-existent `run_id` → **404** (404-not-403).
- **Validation:** `run_id` must be a valid UUID; malformed → **422**.
- **Errors:** `200`; `401`; `404 NOT_FOUND`; `422 VALIDATION_ERROR`.
- **Security considerations:** the result is the user's own appearance
  history — owner-only, never logged; internals never surface (§4.8).
- **Side effects:** none — a pure read of the immutable history.
- **Domain entities involved:** E6 `AnalysisRun`.

---

### 5.3 H-3 — Retrieve recommendations (`GetAnalysisRun`, completed)

- **Method / path:** `GET /v1/analysis/runs/{run_id}` (endpoint 39) — the same
  read as H-2; **retrieval** is the `completed` response.
- **Asynchronous behavior:** **sync.**
- **Request schema:** none (`run_id` UUID in path).
- **Response schema:** `200 OK` — `AnalysisRun` with `status="completed"` and
  the immutable `result`:

```
{
  "run_id": "7a2b…", "run_type": "hairstyle", "status": "completed",
  "created_at": "2026-08-10T12:00:00Z",
  "completed_at": "2026-08-10T12:00:05Z",
  "engine_version": "2026.08.1",
  "input_media": { "key": "users/u1/scans/7a2b…/input.jpg", "mediaType": "image/jpeg" },
  "result": {
    "appearance": { "faceShape": "oval", "skinTone": "warm_medium", "bodyType": "lean",
                    "styleType": "modern_classic", "sourceRunId": "7a2b…" },
    "recommendations": {
      "top":      { "id": "textured_quiff", "name": "Textured Quiff", "matchScore": 0.94,
                    "description": "…", "reasons": ["…"], "stylingTips": "…",
                    "maintenance": "Medium • Trim every 4-5 weeks",
                    "bestFor": "Oval, Heart, and Rectangle face shapes" },
      "alternatives": [ { "id": "classic_pompadour", "matchScore": 0.87, … }, … ]
    }
  }
}
```

  The recommendation objects carry the full §4.3 DTO — this **is** the
  retrievable recommendation set. `confidence`/`tradeOffs` are absent today
  (AI-0, §4.3).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (404-not-403).
- **Validation:** `run_id` UUID → else **422**.
- **Errors:** `200`; `401`; `404`; `422 VALIDATION_ERROR`.
- **Security considerations:** owner-only; only the typed DTO travels — no
  prompts, no provider internals (§4.8).
- **Side effects:** none — pure read of the immutable result.
- **Domain entities involved:** E6 `AnalysisRun` (result snapshot); E5 `Look`
  (catalog content behind the ids); value objects: HairstyleRecommendation,
  FaceProfile, Score.

---

### 5.4 H-4 — Retrieve recommendation details (within the run result — no separate endpoint)

- **Method / path:** none invented — details come from `GET
  /v1/analysis/runs/{run_id}` (H-3), selecting a single recommendation by its
  `id`.
- **Why there is no detail endpoint:** the recommendation's full detail
  (description, reasons, styling tips, maintenance, best-for, score) **is** the
  result snapshot — the same object the result screen and the details screen
  render (`hairstyle_details_screen.dart` receives the `HairstyleRecommendation`
  directly). A separate `GET /v1/recommendations/{id}` would invent a resource
  that does not exist (BAR-0, §3.1) and duplicate the immutable snapshot.
- **Response schema:** the single `HairstyleRecommendation` (§4.3) selected by
  `id` from the completed result's `top`/`alternatives`. Its `id` doubles as
  the catalog code for save (`lookId`) and feedback (`targetLookId`).
- **Detail-only enrichment (e.g. an image)**, if ever needed, belongs to the
  catalog/knowledge surface (`GET /v1/knowledge/looks` →
  `LookCard.imageRef`, referenced) — not to the run.
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (404-not-403).
- **Validation:** `run_id` UUID; the selected `id` must exist in the run's
  result → a missing id is a client-local miss, never a new endpoint.
- **Errors:** `200`; `401`; `404` (run); `422 VALIDATION_ERROR`.
- **Security considerations:** details are the user's own recommendation
  history — owner-only; no internals (§4.8).
- **Side effects:** none.
- **Domain entities involved:** E6 `AnalysisRun` (result); E5 `Look` (catalog
  content); value object `HairstyleRecommendation`.

---

### 5.5 H-5 — Save a recommendation (`SaveRecommendation`, UC-15 — referenced)

- **Method / path:** `POST /v1/looks/saved` (endpoint 23, action 22; M7 —
  **referenced, not re-defined**)
- **Asynchronous behavior:** **sync.** `Idempotency-Key` **required** (TRX-3).
- **Request schema** (`SaveLookRequest`):

```
{
  "lookId": "textured_quiff",        // the recommendation's catalog id (from H-3/H-4)
  "title": "Textured Quiff",         // the saved-look title (the recommendation name)
  "sourceContext": "hairstyle",      // source surface (scan analysis)
  "snapshot": { /* the HairstyleRecommendation DTO — score + reasons frozen at save time (R31) */ }
}
```

  When saved from a scan, the server also records `source_run_id` provenance
  to the producing run (`saved_looks.source_run_id`, FK SET NULL — P2).
- **Response schema:** `201 Created` — `SavedLook` (`id`, `lookId?`, `title`,
  `snapshot`, `sourceRunId?`, `createdAt`).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1).
- **Validation:** `lookId` must be a valid catalog code (or absent); `title`
  `[1,200]`; snapshot required; `sourceContext` a known source code.
- **Errors:** `201`; `401`; `404 NOT_FOUND` (look gone); `409 CONFLICT`
  (duplicate save); `422 VALIDATION_ERROR`; `429 RATE_LIMITED`.
- **Security considerations:** the snapshot is the user's own recommendation
  history — owner-only; it freezes AI output as the durable keeper
  (AI-output-never-truth boundary, R31). No internals (§4.8).
- **Side effects:** **TRX-3 true transaction** — `INSERT saved_looks` +
  `INSERT learning_signals(look_saved)` commit together; `recommendation_history.
  saved` flip only when the P3 table exists. The run and the recommendation
  set are **never modified** by a save.
- **Domain entities involved:** E4 `SavedLook` (immutable snapshot); E7
  `LearningSignal` (`look_saved`); E5 `Look` (optional SET NULL FK); E6
  `AnalysisRun` (optional `source_run_id`).

---

### 5.6 H-6 — Submit feedback (`SubmitRecommendationFeedback`, UC-32 — referenced, gated)

- **Method / path:** `POST /v1/feedback` (endpoint 35, action 31; M11 —
  **referenced; NOT mounted** until a feedback UI is accepted, API-12)
- **Asynchronous behavior:** **sync.** `Idempotency-Key` required when it
  ships.
- **Request schema** (`FeedbackCreate`):

```
{
  "rating": "helpful",              // rating tag — exact vocabulary PENDING the feedback design (§8)
  "reason": "prefer a shorter crop", // optional free-text "why"
  "targetLookId": "textured_quiff",  // optional — the recommendation's catalog id
  "targetSavedLookId": "…"           // optional — when feedback targets a saved look
}
```

- **Response schema:** `201 Created` / `204 No-content`.
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1).
- **Validation:** `rating` from the accepted vocabulary (once defined); at most
  one target (`targetLookId` XOR `targetSavedLookId`); `reason` length-bounded.
- **Errors:** `201`/`204`; `401`; `422 VALIDATION_ERROR`; `429 RATE_LIMITED`.
- **Security considerations:** a raw, append-only user event
  (`feedback_events`); free-text `reason` is user content — stored, never
  shared, and **never** injected into the engine's internal prompts (§4.8). No
  internals.
- **Side effects:** single `INSERT feedback_events` (tier 1); feeds the
  derived-preference loop (M10 aggregation) — **never** rewrites the run, the
  snapshot, or the ranking directly (§4.6).
- **Domain entities involved:** `FeedbackEvent` (value object); E7
  `LearningSignal` (optional link); E5 `Look`/E4 `SavedLook` (optional targets,
  SET NULL).
- **Gating:** no `feedback_events` table and no endpoint until the feedback UI
  lands (PR-12, API-12). The assistant card-interaction signal
  (`POST /v1/assistant/feedback`, UC-23, endpoint 17 — `opened`/`navigated`) is
  a separate, card-level path, referenced not re-defined.

---

### 5.7 H-7 — Regenerate recommendations (pattern, no endpoint)

- **Method / path:** none invented — regenerate is a **new submission** to
  `POST /v1/analysis/hairstyle` (H-1).
- **Why:** there is no `RegenerateHairstyle` use case (only UC-29
  `RegenerateOutfit`, M13); recommendations are regenerable AI output and a
  re-run is a **new** `analysis_runs` row — the old run stays immutable history
  (`HISTORY_AND_VERSIONING.md` §5.7/§5.8, `SCAN_API.md` §5.6).
- **Two regenerate forms (both = a new run → 202 {run_id} → poll H-2):**
  1. **Re-submit the image** — the user retakes/refines the face scan.
  2. **Profile-only re-rank** — `POST /v1/analysis/hairstyle` with an empty
     body (no image, no reference field — Phase 28): recommendations re-ranked over the stored
     current profile. This is the natural "recommend again / show alternatives"
     path and the **retry** path after a failure (see `SCAN_API.md` §5.6).
- **Request/response:** identical to H-1/H-3; each run has its own `run_id`,
  `result`, `engine_version`.
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**.
- **Validation/errors:** identical to H-1.
- **Security considerations:** no internals (§4.8); a regenerate never mutates
  an earlier run.
- **Side effects:** a new run row; the profile-only form writes **no** new face
  attributes (no TRX-6 projection change) — only the recommendation run.
- **Domain entities involved:** E6 `AnalysisRun` (new row); E5 `Look`; E1.1
  (read: current profile for the re-rank).

---

### 5.8 The hairstyle recommendation flow (a sequence of the above — no new endpoint)

```
H-1 submit (image pass, or empty body for profile-only pass — Phase 28) ──202 {run_id}──►  H-2 poll ──► completed
    │ (run pending; TRX-1 media)                            │          │
    │                                                       ▼          ▼ H-3 result: { appearance, recommendations{top,alternatives} }
    │                                        TRX-6 on completion        H-4 details: pick a recommendation by id (same snapshot)
    ▼                                           (face → styleProfile)          │
H-7 regenerate: new POST (image pass or empty body for profile-only pass) → NEW run (old result stays immutable)   ▼
H-5 save: POST /v1/looks/saved (lookId, title, snapshot, source_run_id)  ── TRX-3 frozen snapshot + look_saved signal
H-6 feedback: POST /v1/feedback (rating, reason, targetLookId)  ── gated (M11) — raw event, never rewrites the run/snapshot
current profile read: GET /v1/users/me (styleProfile — disjoint from the run snapshot)
```

---

## 6. Validation reference (shared)

| Field | Rules | Source |
| --- | --- | --- |
| `run_type` | `hairstyle` (this surface) | `analysis_runs.run_type` FK |
| `status` | `pending → completed | failed`; write-once guard | TRX-5, CHECK constraint |
| `image` | optional for H-1 (absent = profile-only pass over `style_profile` by `user_id`, Phase 28); face detectable; size/content-type | API-16, UC-25 |
| `id` (recommendation) | valid catalog `looks.code` (PR-3) | TABLE_DEFINITIONS `looks` |
| `matchScore` | `0..1`; derived, never client-authored | Scoring stage |
| `confidence` / `tradeOffs` | absent today; additive/FUTURE only | AI-0, VALUE_OBJECTS §3.3 |
| `lookId` (save) | valid catalog code (or absent); `sourceContext` known source | UC-15 |
| `rating` (feedback) | accepted vocabulary — **pending** (§8) | UC-32, feedback design |
| `run_id` | UUID; owned (404-not-403) | path param, OW-1 |
| `page`/`page_size` | `[1,100]` (history list) | API-22 |

All validation is **server-side** (Flutter never enforces security) and returns
the **safe client message**, never internals (ER-2).

---

## 7. Error reference for this surface

| `error.code` | HTTP | When | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | poor image / no face (H-1); bad UUID/filter (H-2/H-3); invalid save/feedback fields (H-5/H-6) | field errors + allowed values in `details` |
| `MEDIA_FAILURE` | 413/422 | image too large / unsupported content-type (H-1) | `details.maxBytes`; pre-run check |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | run not owned / never existed; look gone on save | 404-not-403, no existence leak |
| `CONFLICT` | 409 | duplicate save (H-5) | `details.kind="duplicate"` |
| `EXTERNAL_SERVICE_FAILURE` | 502/503 | AI provider/submission failure | C-8: no provider internals |
| `PROCESSING_FAILURE` | 500 (sync) / run `failed` | pipeline failure (after the 1 automatic retry) | `details.run_id`; the run is a historical failure |
| `RATE_LIMITED` | 429 | any endpoint | + `Retry-After` |

---

## 8. Open decisions (carried forward, unchanged where already recorded)

1. **D-AUTH-1 — auth provider** — unchanged; gates mounting the whole M12
   analysis surface (endpoints stay unmounted until the seam lands, API-12).
2. **MS10.3 — media seal** — face-image submission (`multipart` → `MediaRef`)
   depends on M16 unsealing; until then H-1 is not mounted (API-12). No fake
   200 before either gate lifts.
3. **Feedback UI + rating vocabulary** — `POST /v1/feedback` (H-6) is gated on
   an accepted feedback UI (M11); the `rating` vocabulary (`feedback_events.
   rating`, `feedback_events` has no table yet) is defined by the feedback
   design (PR-12). Until then H-6 is documented but **not mounted**.
4. **Trade-offs** — **not modeled today** (§4.3): the `tradeOffs` field is
   additive only, and only if the domain defines a grounded trade-off catalog
   (never invented content).
5. **Confidence** — optional field inside run results once real models compute
   it; never an endpoint and never a substitute for `matchScore` (AI-0).
6. **Hair *profile* endpoints** — **deliberately not defined** (PLANNED, no
   tables); if a hair pipeline lands, the profile becomes an embedded
   projection pinned by `source_run_id` — additive (same as `APPEARANCE_API.md`
   §8.6).
7. **`recommendation_history` (P3)** — shown/saved trace is conditional and
   gated by product decision; TRX-3 flips its `saved` flag only when the table
   exists. Not part of this contract.
8. **Per-item `engineVersion`/`model_version`** — provenance is run-level
   `engine_version` today; per-item model metadata is optional/internal and
   never surfaced by name (C-8, §4.5).
9. All other open decisions from `API_CONTRACT_RULES.md` §16,
   `APPEARANCE_API.md` §8, `SCAN_API.md` §8, and `PROFILE_ONBOARDING_API.md`
   §8 remain open and are unaffected.

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/HAIRSTYLE_RECOMMENDATION_API.md` —
the field-level API contract for the hairstyle recommendation surface. It
defines every task operation — **create request** (`POST /v1/analysis/
hairstyle`), **processing status** and **retrieve recommendations**
(`GET /v1/analysis/runs/{run_id}`), **recommendation details** (within the run
result — no separate endpoint, §5.4), **save** (`POST /v1/looks/saved`,
referenced), **feedback** (`POST /v1/feedback`, referenced and gated), and
**regenerate** (a new submission; profile-only re-rank over `style_profile` by `user_id`, Phase 28 — no
endpoint, §5.7). The **recommendation response contract** (§4.3) maps every
task-required field — ID, hairstyle info, score, confidence, explanation,
reasons, trade-offs, profile context, model/version metadata — to the frozen
wire DTO, marking `confidence` (not computed today) and `tradeOffs` (not
modeled) as absent/FUTURE per AI-0, and enforces the **no-internals rule**
(§4.8: no prompts, no provider/model names, no raw provider output). Nothing is
implemented.

**Skills used:** repository + documentation analysis (`hairstyle_mock_data.dart`
recommendation/result shapes, `looks`/`saved_looks`/`feedback_events`/
`recommendation_history` tables, TRX-3/5/6, UC-15/25/26/32,
DECISION_ENGINE_ARCHITECTURE stages 5–8, AI_INTEGRATION `HairAnalysisProvider`
FUTURE + `CapabilityResult` (raw_provider internal-only), API_CONTRACT_RULES
§12.11/§12.6/§12.10/§8.3/§13, API_INVENTORY endpoints 17/23–25/35/37/39/40,
ERROR_HANDLING taxonomy, and the sibling contracts APPEARANCE_API/SCAN_API) —
documentation only.

**Files changed:** `docs/api/HAIRSTYLE_RECOMMENDATION_API.md` (new);
`CURRENT_STATE.md` (status).

**Validation run:**
- **Every defined operation traces 1:1 to the accepted inventory** — H-1→UC-25/
  26 / endpoint 37, H-2/H-3→39, H-5→UC-15 / endpoint 23, H-6→UC-32 / endpoint
  35 (gated), H-7→a new H-1 run (no UC-29-style regenerate exists for
  hairstyle). Paths/methods/auth/UC/errors identical to `API_CONTRACT_RULES.md`
  §12.11/§12.6/§12.10 and `API_INVENTORY.md` §5.12/§5.7/§5.11; the submission
  and run-read shapes are **identical** to `APPEARANCE_API.md` §5.1/§5.3 and
  `SCAN_API.md` §5.2/§5.5 — no field renamed, removed, or retyped (API-2).
- **Wire shapes match the accepted sketches** — `AsyncAccepted`, `AnalysisRun`,
  `SaveLookRequest`/`SavedLook`, `FeedbackCreate` identical to §8.3/§13 and the
  inventory; the recommendation DTO mirrors `HairstyleRecommendation`
  (`hairstyle_mock_data.dart`) exactly. The task's response-field list is
  mapped to the wire in a table (§4.3), with `confidence` and `tradeOffs`
  honestly marked absent/FUTURE (AI-0) — not fabricated.
- **The no-internals rule is structurally enforced** — §4.8 forbids prompts,
  provider/model names, sampling parameters, and raw provider output from the
  wire; `CapabilityResult.raw_provider` stays internal-only
  (AI_INTEGRATION §5). Only typed fields + `engine_version` travel (C-8, ER-0/
  ER-2, F-7).
- **Recommendation-as-AI-output is structurally enforced** — no
  `Recommendation` table/resource (BAR-0); the durable forms are the immutable
  run `result` (TRX-5) and the `SavedLook` snapshot (TRX-3); save/feedback never
  mutate the run; regenerate is a new run. No invented `/v1/recommendations/*`.
- **Auth/authorization/errors consistent** — all endpoints auth + owner-only
  (OW-1, 404-not-403); frozen 12-category errors; 401 + `WWW-Authenticate`,
  429 + `Retry-After`; submissions never idempotent (§11), save idempotent
  (TRX-3), reads/polls naturally idempotent.
- **`git status --short`:** `docs/api/` holds API_CONTRACT_RULES.md,
  API_INVENTORY.md, AUTH_API.md, PROFILE_ONBOARDING_API.md, APPEARANCE_API.md,
  SCAN_API.md, HAIRSTYLE_RECOMMENDATION_API.md (untracked) + `CURRENT_STATE.md`;
  no code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- The M12 analysis endpoints are **not mounted** until D-AUTH-1 + the media/
  analysis pipeline exist; before MS10.3 lifts, no face-image upload path exists
  (API-12 — no fake 200).
- H-6 feedback is **gated** on the feedback UI + rating vocabulary (M11); until
  then `feedback_events` has no table and `/v1/feedback` has no route (PR-12).
- Confidence, trade-offs, per-item model metadata, and the P3
  `recommendation_history` trace are additive/FUTURE (§8.4–§8.8).
- Other open decisions unchanged: auth provider (D-AUTH-1), User fields,
  Today'sLookRecord (P1), RecommendationHistory (P3), conversation retention,
  K9.1 knowledge shape, media-privacy (MS10.3), feedback design.

**Assumptions recorded:**
- A hairstyle recommendation is a value object from the decision engine; its
  `description` is the explanation and `reasons[]` the grounded bullets
  (Explanation stage); both are truthful, never invented.
- `confidence` and `tradeOffs` are absent from responses today (AI-0); the
  contract supports them as optional FUTURE fields without fabricating values.
- Recommendation detail = the immutable run-result snapshot (no separate
  endpoint); detail-only enrichment belongs to the catalog/knowledge surface.
- Save is the only durable keeper (TRX-3 snapshot); feedback is a raw event
  that never rewrites the run/snapshot/ranking; regenerate is always a new run.
- The current face profile/style DNA is always read from `/users/me`; the run
  snapshot (with `appearance` provenance) is the historical record — never
  mixed (§4.5).

**Constraints honored:** no implementation (hairstyle recommendations NOT
created, no AI providers, no media), the live assistant contract untouched
(F-5), no invented APIs (no `/v1/recommendations/*`, no regenerate endpoint, no
hair-profile endpoint — all documented), the run machine and DTO shapes kept
identical to the accepted contract and sibling docs, the no-internals rule
enforced, scope limited to `docs/api/HAIRSTYLE_RECOMMENDATION_API.md` +
`CURRENT_STATE.md`.
