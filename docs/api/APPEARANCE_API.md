# Fansivibe — API Contract: Appearance Intelligence

> **STEP 6 — API CONTRACT DESIGN.** Defines the **field-level API contract for
> the appearance-intelligence surface** — the operations that run appearance
> analyses (face / hairstyle / grooming), read their **immutable historical
> runs**, and the reads/writes that serve the **current** face profile, style
> DNA, style score, and capability progress. It is the focused companion to
> `API_CONTRACT_RULES.md` (§12.11 analysis catalog + §13 P0 sketches) and
> `API_INVENTORY.md` (§5.12 analysis, §5.3 users, §5.10 learning) and sits
> beside the sibling contract `PROFILE_ONBOARDING_API.md`, which owns the
> profile/preferences write surface this doc's profile read/write sections
> reference.
>
> **Status: contract design only. Appearance analysis is NOT implemented.**
> No code, no `deps.py`, no routers, no SQL, no AI providers, no Flutter
> changes, no dependencies. The live contract (`GET /health`,
> `POST /v1/assistant/chat`) is preserved unchanged. Analysis endpoints are
> P2 and stay **unmounted** until the auth seam (D-AUTH-1), the media seal
> (MS10.3), and a real analysis pipeline land (API-12).
>
> **Source of truth:** the real Fansivibe repository and the accepted docs —
> STEP 3 `APPEARANCE_DOMAIN_MODEL.md` (the nine-concept classification),
> `AI_DOMAIN_MODEL.md`, `DOMAIN_STATE_AND_HISTORY.md` (current-vs-history),
> STEP 4 `TABLE_DEFINITIONS.md` (`analysis_runs`, `user_state`,
> `style_score_records`) + `HISTORY_AND_VERSIONING.md` (six storage
> categories), `TRANSACTION_BOUNDARIES.md` (TRX-5 run completion, TRX-6
> projection), `APPLICATION_USE_CASES.md` (UC-25…UC-27), STEP 5
> `AI_INTEGRATION_ARCHITECTURE.md` (FUTURE capability interfaces),
> `ERROR_HANDLING.md` (12-category taxonomy), STEP 6 `API_CONTRACT_RULES.md`
> (catalog §12.11, async §8.3, sketches §13) + `API_INVENTORY.md` (endpoints
> 06/07/34/36–40), `AUTH_API.md` (§5.5 GetProfile), and
> `PROFILE_ONBOARDING_API.md` (P-1/P-2 referenced).

---

## 1. Purpose and scope

This document defines, for every **required** appearance-intelligence
operation, the eight contract attributes the STEP 6 design task asks for:

1. **method**
2. **path**
3. **request schema**
4. **response schema**
5. **authentication requirements**
6. **validation**
7. **errors**
8. **asynchronous behavior** (when applicable)

(plus security considerations, side effects, and domain entities, following
the same convention as the sibling contract `PROFILE_ONBOARDING_API.md`).

It also **selects the operation set**: of the candidate topics in the task
(face profile, hair profile, grooming profile, style DNA, appearance analysis,
appearance score, capability progress), only those the finalized domain model
and the accepted 48-endpoint inventory actually support are defined here.
Concepts the domain classifies as PLANNED (hair/grooming/color profile),
derived-narrative (appearance intelligence), or system-config (capability
progress) are **not** invented into endpoints.

**The one binding design rule of this document — historical AI analyses must
remain distinguishable from current profile state.** The domain model is
unambiguous about this (`DOMAIN_STATE_AND_HISTORY.md` §1: never overwrite
history; `APPEARANCE_DOMAIN_MODEL.md` §3.8: runs are immutable snapshots that
*feed* the current projection, R15). The contract below enforces it with two
**different resource families** and explicit provenance (§4.4):

- **Current profile state** lives under `/users/me` — `ProfileView.styleProfile`
  is the mutable, owner-editable *today* and carries `sourceRunId` provenance.
- **Historical analyses** live under `/analysis/runs*` — `AnalysisRun` rows are
  append-only, immutable, and carry `created_at` + `engine_version`.

A client reading current style data and a client reading analysis history can
never hit the same resource, and neither representation can be mistaken for the
other (§4.4).

**What it does not do:** implement the analysis module (M12), write AI
providers, add media endpoints (M16 is sealed), modify Flutter, or change the
frozen assistant DTOs. The profile read/write endpoints referenced here
(`GET /v1/users/me`, `PATCH /v1/users/me`) are owned by `AUTH_API.md` /
`PROFILE_ONBOARDING_API.md` and are **referenced, not re-defined**.

### 1.1 Grounding facts (re-verified)

- **Only four of the nine appearance concepts have a real (if dead/mock)
  data shape today** (`APPEARANCE_DOMAIN_MODEL.md` §1, §8): **Face Profile**
  (value object, never written — `setFace` has no caller), **Style Profile /
  Style DNA** (target profile + disconnected mock DNA), **Appearance Analysis**
  (dead `AnalysisResult`/`OnboardingResult`, no runs), and **Style Score**
  (in-memory formula). The rest are config, copy, or PLANNED.
- **Hair Profile, Grooming Profile, and Color Profile are PLANNED domain
  targets**, not data. They exist only as `allCapabilities` config entries and
  mock outputs; the domain explicitly says **do not create profile tables** for
  them until a real pipeline writes attributes (P1) — so no hair/grooming/color
  *profile* endpoint is defined (§3.1).
- **Grooming inputs are user preference referencing vocab ids.** The user picks
  `GroomingOption` values (face shape, beard style, density, color —
  `grooming_mock_data.dart:16`), not free text; today they are ephemeral widget
  state. Only the grooming **analysis run** (recommendations) is a server
  operation (§5.2).
- **Appearance analysis = the immutable run.** E6 `AnalysisRun`
  (`TABLE_DEFINITIONS.md` §5): `run_type` ∈ {`outfit`, `face`, `hairstyle`,
  `grooming`} (FK → `run_types`), `status` ∈ {`pending`, `completed`, `failed`}
  (CHECK), `engine_version`, `input_media` (MediaRef, not bytes), `result`
  JSONB (immutable snapshot, NULL until completed), `created_at`,
  `completed_at`. Append-only, write-once completion (TRX-5, PR-5/PR-6).
- **No analysis endpoint is live.** The inventory's four analysis operations
  (36–39/40) are **P2** and async (`202 + run_id` → poll, API-41/42). Every
  analysis provider is **FUTURE** (`AI_INTEGRATION_ARCHITECTURE.md` §5) — AI-0
  honesty: no capability pretends to exist. **No confidence is computed or
  transmitted today** (`AI_DATA_FLOW.md` Part D.3) — scores are catalog
  constants; confidence is an *optional* future value-object field, never an
  endpoint.
- **Style DNA is derived, never stored as truth.** `StyleDnaData`
  (`profile_mock_data.dart:145`) / `StyleDnaContext` are display views
  recomputed from `FaceProfile` (P4/R14). It is **not** a write target: the
  only write path for style attributes is `styleProfile` via `PATCH /users/me`
  (`styleType` self-reported; analysis-derived fields pinned by `sourceRunId`).
- **Style score is derived and owned by the learning surface, not
  appearance.** The formula `60 + wardrobe.length.clamp(0,20) +
  savedLooks.length*2.clamp(0,20)` (`learning_service.dart:224`) is a derived
  cache; its history is the append-only `style_score_records`. The only
  endpoint is `GET /v1/learning/summary` (endpoint 34, M10) — referenced here,
  not re-defined (§5.6). There is **no** "appearance score" in the inventory.
- **Capability progress is system config, not user data.** `allCapabilities`
  (7 capabilities, 2 marked active, `onboarding_data.dart:79`) +
  `HISTORY_AND_VERSIONING.md` §5.12 classify it SYSTEM CONFIGURATION with no
  per-user rows — same decision as `PROFILE_ONBOARDING_API.md` §3.3 (§3.2).
- **"Appearance Intelligence" is UI copy** (`entry_screen.dart:203`,
  `your_analysis_screen.dart:266`) — a derived umbrella/narrative, not data and
  not an endpoint (§3.3).
- **`FaceData` travels frozen inside the assistant contract**
  (`UserContext.face`, `API_CONTRACT_RULES.md` §13.4, F-13) — the KEEP mirror of
  the current face profile for the live assistant; it is read-only transport and
  this surface never changes it.
- **Profile surface already fixed:** `ProfileView.styleProfile = { faceShape?,
  skinTone?, bodyType?, styleType?, sourceRunId? }` (§13.2); the face profile is
  embedded in it (P2/R13, JSONB `user_state.style_profile`, source-run FK is an
  application-level JSONB reference — `TABLE_DEFINITIONS.md` §6).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `APPEARANCE_DOMAIN_MODEL.md` | The nine-concept classification (current vs historical vs derived vs preference vs config); the uniform pattern "AI-generated content → accepted current-profile projection → immutable run as history". |
| `DOMAIN_STATE_AND_HISTORY.md` | Current-vs-history split, decision procedure, reproducibility policy (§6), never-overwrite-history. |
| `TABLE_DEFINITIONS.md` | `analysis_runs` (run_type/status/engine_version/input_media/result), `user_state` (`style_profile` JSONB + `source_run_id`), `style_score_records` (append-only). |
| `HISTORY_AND_VERSIONING.md` | Six storage categories: analysis runs = EVENT/HISTORICAL_RECORD (INSERT-only); `user_state` = CURRENT_STATE projection; score = DERIVED_STATE → snapshots. |
| `TRANSACTION_BOUNDARIES.md` | TRX-5 run completion (guarded write-once), TRX-6 profile projection update + learning signal. |
| `APPLICATION_USE_CASES.md` | UC-25 `AnalyzeAppearance`, UC-26 `GenerateHairstyleRecommendations`, UC-27 `GenerateGroomingRecommendations` (M12, P2). |
| `AI_INTEGRATION_ARCHITECTURE.md` | `FaceAnalysisProvider`/`HairAnalysisProvider`/`GroomingAnalysisProvider` FUTURE; `CapabilityResult` envelope (status/confidence/model_version); AI-0/AI-5/AI-6. |
| `API_CONTRACT_RULES.md` | Catalog §12.11 (methods/paths/auth/UC/errors), §8.3 async run object, §13.2 profile sketches, §9 error contract, C-8/C-10/C-16, API-41/42. |
| `API_INVENTORY.md` | Endpoints 36–40 (§5.12), 06/07 (§5.3), 34 (§5.10); related domain entities per endpoint. |
| `PROFILE_ONBOARDING_API.md` / `AUTH_API.md` | P-1 GetProfile, P-2 UpdateProfile (styleDna rules incl. `sourceRunId`), auth/owner semantics — referenced. |
| `ERROR_HANDLING.md` | 12-category taxonomy: VALIDATION_ERROR (422), AUTHENTICATION_ERROR (401), NOT_FOUND (404), RATE_LIMITED (429), MEDIA_FAILURE (413/422), EXTERNAL_SERVICE_FAILURE (502/503), PROCESSING_FAILURE (500 / run failed). |
| `VALUE_OBJECTS.md` | Score, Confidence, Style Vibe as value objects (never entities); snapshots as the only persistence. |

---

## 3. Operation selection (define only the required operations)

| # | Candidate operation | Decision | Justification |
| --- | --- | --- | --- |
| A-1 | **Face analysis + hairstyle recommendations** | **Required** — `POST /v1/analysis/hairstyle` | UC-25/26, endpoint 37, action 21. Face image → appearance attributes + hairstyle recommendations in one async run; completion applies the face attributes to the current profile (TRX-6). §5.1. |
| A-2 | **Grooming recommendations** | **Required** — `POST /v1/analysis/grooming` | UC-27, endpoint 38, action 23. Grooming options → recommendations; no profile projection change by default. §5.2. |
| A-3 | **Get analysis run** | **Required** — `GET /v1/analysis/runs/{run_id}` | Endpoint 39, poll. The historical run with immutable result; **the** distinguishability read. §5.3. |
| A-4 | **List analysis runs** | **Required** — `GET /v1/analysis/runs` | Endpoint 40, history. §5.4. |
| R-1 | **Get profile (current)** | **Required (referenced)** — `GET /v1/users/me` | UC-6, endpoint 06. Serves the *current* face profile + style DNA (`styleProfile`). Defined in `AUTH_API.md` §5.5 / `PROFILE_ONBOARDING_API.md` §5.1. §5.5. |
| R-2 | **Update profile (current)** | **Required (referenced)** — `PATCH /v1/users/me` | UC-7, endpoint 07. The only way a client writes current style attributes; analysis-derived fields require `sourceRunId`. Defined in `PROFILE_ONBOARDING_API.md` §5.2. §5.5. |
| R-3 | **Style score / learning summary** | **Required (referenced)** — `GET /v1/learning/summary` | Endpoint 34 (M10). The derived "appearance score" surface + streak. Defined with the M10 module. §5.6. |
| — | **Outfit analysis** | **NOT in this surface** | `POST /v1/analysis/outfit` (UC-24, endpoint 36) is the *outfit/wardrobe* surface (media + clothing detection), not appearance intelligence; out of scope here. |
| — | **Hair profile** | **NOT required now** | §3.1. |
| — | **Grooming profile** | **NOT required now** | §3.1. |
| — | **Capability progress API** | **NOT required now** | §3.2. |
| — | **"Appearance Intelligence" endpoint** | **NOT required now** | §3.3. |
| — | **Style DNA write endpoint / confidence endpoint** | **NOT required now** | §3.4. |

### 3.1 Hair / Grooming / Color *profile* endpoints — not defined

The task lists "hair profile" and "grooming profile". The finalized domain
model classifies both as **CURRENT PROFILE STATE (PLANNED)** with **no model in
the product** (`APPEARANCE_DOMAIN_MODEL.md` §3.2/§3.3/§3.5): they exist only as
capability-config entries and mock outputs, and the domain explicitly says
**no profile tables** until a real pipeline writes attributes (P1). **No
`hair-profile` / `grooming-profile` / `color-profile` resource exists**, so no
read/write endpoint for a hair/grooming/color profile is defined — creating one
would both invent a table the schema forbids and duplicate the *analysis run*
that actually produces those attributes.

What the product *does* have is the **analysis runs** that would one day feed
those planned profiles: hairstyle (A-1) and grooming (A-2). The runs are the
history; if hair/grooming profiles are ever added, they follow the Face
Profile pattern exactly — an embedded projection in `styleProfile` pinned by
`source_run_id` (recorded in §8).

### 3.2 Capability progress — config-only, no API

Identical decision to `PROFILE_ONBOARDING_API.md` §3.3. `allCapabilities` is
static system config (7 capabilities, 2 marked active); capability status is
**client-computed** from local config × the user's own data signals; the server
stores **no per-user capability rows**. **No capability endpoint** is defined.
Forward contract: if the catalog ever becomes server-served it belongs under
`/v1/knowledge/*` (M5, additive, K9.1) — still no per-user rows.

### 3.3 "Appearance Intelligence" — narrative, not data

"Appearance Intelligence" (`entry_screen.dart:203`, `your_analysis_screen.dart:266`)
is the **system/UX narrative** over the appearance cluster (profile + analyses
+ capability availability). It has no identity, lifecycle, or storage
(`APPEARANCE_DOMAIN_MODEL.md` §3.6). **No endpoint and no field** is defined
for it; any screen aggregates the real concepts below.

### 3.4 Style DNA write and confidence — no endpoints

- **Style DNA** is **DERIVED INFORMATION** (`APPEARANCE_DOMAIN_MODEL.md` §3.4):
  a display view recomputed from `FaceProfile`. It has no write endpoint —
  the only writes to style attributes are `styleType` (self-reported, via
  R-2) and analysis-derived fields (pinned by `sourceRunId`, via A-1/R-2).
- **Confidence** is a **value object** (`VALUE_OBJECTS.md` §3.3) that is
  **not computed today** (`AI_DATA_FLOW.md` Part D.3). It is an *optional
  future field inside run results*, never a resource.

---

## 4. Shared semantics (apply to every operation below)

### 4.1 Base URL, headers, format

- All endpoints under `/v1` (API-1); JSON bodies `application/json;
  charset=UTF-8`; keys camelCase; timestamps ISO-8601 UTC (API-19). Analysis
  submissions with an image use `multipart/form-data` (API-36).
- Protected endpoints send `Authorization: Bearer <token>` (API-5). Missing /
  invalid / expired / revoked → `401 AUTHENTICATION_ERROR` +
  `WWW-Authenticate: Bearer` (API-7, ERROR_HANDLING §5.2).
- **No `Idempotency-Key`** on analysis submissions — **each call creates a new
  run** (`API_CONTRACT_RULES.md` §11: never idempotent). Reads and polls need
  no key.
- Every response echoes `X-Request-Id` (OBSERVABILITY §4.1).

### 4.2 Asynchronous run model (API-41/42, TRX-5)

Image analysis is the **only async surface** in the API (sync-by-default,
API-40). Every analysis **submission** returns `202 Accepted` immediately:

```json
{ "run_id": "7a2b3c…" }
```

The client polls `GET /v1/analysis/runs/{run_id}` (A-3) until
`status ∈ { completed, failed }`. Completion is **write-once** (TRX-5): the
guarded `UPDATE … WHERE status='pending'` flips the run once; a completed run
is immutable and is never overwritten (PR-6). A `failed` run carries the typed
error in `error` and **no** `result` — the failure is itself part of history
(reproducible). Analysis is **not idempotent**: a retried submission creates a
second run, which is by design (each attempt is a distinct historical record).

### 4.3 Run DTO and status machine

```
AnalysisRun {
  run_id*,          // UUID; the historical record's identity
  run_type*,        // "outfit" | "face" | "hairstyle" | "grooming" (run_types vocab)
  status*,          // "pending" | "completed" | "failed"
  created_at*,      // ISO-8601 UTC
  completed_at?,    // present when completed | failed
  engine_version?,  // provenance — present when completed (PR-6)
  result?,          // immutable typed snapshot — present ONLY when completed
  error?            // frozen error body — present ONLY when failed
}
```

`status` transitions: `pending → completed | failed` (TRX-5). There is no
cancellation and no re-run of an existing run — regenerate = a new submission.

### 4.4 Historical analyses vs current profile state (the distinguishing contract)

This is the document's binding rule (§1). The contract keeps the two piles on
**different resource families** with **no shared field ambiguity**:

| | Current profile state | Historical analysis |
| --- | --- | --- |
| **Resource** | `GET /v1/users/me` → `ProfileView.styleProfile` | `GET /v1/analysis/runs/{run_id}` / `/runs` → `AnalysisRun` |
| **Write path** | `PATCH /v1/users/me` (styleDna) + A-1 completion (TRX-6) | none — `INSERT`/`SELECT` only (PR-5) |
| **Mutability** | mutable, owner-editable | immutable, append-only |
| **Identity** | no id — a projection | `run_id` UUID |
| **Time** | "now" (no timestamp; it is the today) | `created_at`, `completed_at` |
| **Provenance** | `sourceRunId` → the producing run | `engine_version` + inputs → reproducible |
| **Lifecycle** | replaced whole on acceptance (latest-wins, R15) | never overwritten; a new analysis = a new run |
| **Erasure** | edited/deleted freely (owner) | deleted only by account erasure (TRX-8) |

**Guarantees:**

1. **A run result is never the current profile.** `AnalysisRun.result` is a
   frozen snapshot of *what one analysis said at a point in time*; it is
   immutable and versioned. The current face profile is `styleProfile` returned
   by `GET /users/me`, which may differ from any single run (a run can be
   superseded by a newer accepted run, R15 latest-wins — but the older run row
   is untouched).
2. **The current profile always names its source run.** `styleProfile.
   sourceRunId` links the accepted projection back to the producing run; the
   run's `engine_version` makes the past reproducible (PR-6). A profile value
   without a producing run is only the self-reported `styleType` (a user
   preference — never analysis).
3. **Acceptance is a projection write, not a run edit.** A-1 completion applies
   attributes to `styleProfile` in a **separate transaction** (TRX-6) after the
   run row is written (TRX-5); "retake analysis" therefore means *a new run*,
   never a mutation of the old one.
4. **Client never conflates them.** A screen showing "your style today" reads
   `/users/me`; a screen showing "analysis history" reads `/analysis/runs`.
   The DTO shapes are disjoint (`ProfileView` has no `status`/`engine_version`;
   `AnalysisRun` has no `styleProfile`).
5. **Failure history is kept too.** A `failed` run remains a row (with the typed
   error) so a retry decision is auditable; it carries no `result` and never
   touches the projection.

### 4.5 Error body (frozen, API-28)

```
{ "error": { "code": "<one of the 12>", "message": "<safe client message>", "details": {...} } }
```

`details` is allow-listed only (ER-1): field errors + allowed values (422),
`maxBytes` (413), `run_id` (own run only), `request_id` (500). **Never** the
user's face image, run `result` content, prompts, provider/model names, or
analysis internals (C-7/C-8, ER-0/ER-2, AI-0).

### 4.6 Auth, ownership, privacy

| Requirement | Endpoints |
| --- | --- |
| **Auth** (Bearer → `user_id`) | `POST /v1/analysis/hairstyle`, `POST /v1/analysis/grooming`, `GET /v1/analysis/runs/{run_id}`, `GET /v1/analysis/runs`. |
| **Public** | none in this surface. |

Authorization is **owner-only (OW-1)** with **404-not-403** (API-10): every
analysis run is scoped to the caller's `user_id`, and a `run_id` that is not
yours (or that never existed) returns `404`, never `403` and never an existence
hint. Face media and face-derived attributes are **CRITICAL-sensitivity**
appearance data (SECURITY_PRIVACY_DESIGN §3): HTTPS only, owner-only, never
cached on shared storage, **image bytes never logged** and never echoed in
responses or errors — only the `MediaRef` travels (MS10.3, ER-4).

---

## 5. Operation contracts

### 5.1 A-1 — Face analysis + hairstyle recommendations (`AnalyzeAppearance` UC-25 / `GenerateHairstyleRecommendations` UC-26)

- **Method / path:** `POST /v1/analysis/hairstyle` (endpoint 37, action 21)
- **Asynchronous behavior:** **async** — `202 Accepted` + `run_id`; poll A-3
  until `completed | failed`. Each submission is a new run (never idempotent).
- **Request schema** (`multipart/form-data`):

```
image:            <file>          // required; face photo; the evidence (MediaRef after M16)
faceProfileRef?:  "…"             // optional; run a recommendation-only pass over the stored FaceProfile
```

  - With an image: the run does UC-25 (face analysis → appearance attributes)
    then UC-26 (hairstyle recommendations) — one run, one result.
  - Without an image (profile-only, `faceProfileRef` present): recommendation
    pass over the already-stored current profile (no new face attributes).
- **Response schema:** `202 Accepted` — `AsyncAccepted { run_id* }` (bare, no
  envelope). The completed run's `result` (immutable, typed snapshot):

```
AnalysisRun.result (run_type "hairstyle") {
  appearance?: {                       // UC-25 — face attributes
    faceShape?, skinTone?, bodyType?,  // analysis-derived codes
    styleType?,                        // suggested vibe (recommendation, not acceptance)
    confidence?: { value: 0..1, scope: "face" },   // FUTURE; absent today (AI-0)
    sourceRunId                        // = this run_id (provenance)
  },
  recommendations: {                   // UC-26 — hairstyle recommendations
    top: HairstyleRecommendation,      // { id, name, description, matchScore, reasons[],
    alternatives: HairstyleRecommendation[],   //   stylingTips, maintenance, bestFor }
  }
}
```

  The *current* face profile (after acceptance) is **not** this `result` — it is
  `ProfileView.styleProfile` via R-1 (§4.4). `HairstyleRecommendation` mirrors
  `hairstyle_mock_data.dart:64-102` (top + alternatives, scores, reasons).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1); face media is private.
- **Validation:**
  - Image required when no `faceProfileRef`; otherwise **422**. Image
    content-type/size checked pre-run → **413/422 MEDIA_FAILURE** (`details.
    maxBytes`).
  - No face detected / poor image → **422 VALIDATION_ERROR** (UC-25
    `InvalidInputError`).
  - `run_type` produced = `hairstyle` (the endpoint's run_types code); a
    dedicated `face`-only run is reserved, not mounted (§3).
  - Derivation: the resulting `faceShape`/`skinTone`/`bodyType` are
    vocab-validated (K9.1); codes finalized with the knowledge layer (§8).
- **Errors:** `202`; `401`; `404` (account gone); `413/422 MEDIA_FAILURE`
  (image); `422 VALIDATION_ERROR` (no face, invalid input, missing image);
  `503 EXTERNAL_SERVICE_FAILURE` (provider — submission); on the poll, the run
  itself may be `status=failed` with `error.code = PROCESSING_FAILURE`
  (details.run_id) — a failed run is history, not an HTTP 500 on submit.
- **Security considerations:**
  - Face media is CRITICAL — uploaded as bytes only into the pipeline, stored as
    `MediaRef` (never the bytes in PG, PR-8), never logged, never echoed
    (MS10.3, ER-4). The analysis-derived attributes are **never client-authored
    truth** — they arrive inside the immutable run and reach the profile only
    via the guarded completion (C-16/BAR-0).
  - Provider/model internals never surface (C-8, AI-0); the response is the
    typed result + `engine_version` only.
  - 404-not-403 on all owned ids; rate-limited (429) per user.
- **Side effects:**
  - **History:** inserts an `analysis_runs` row (run_type `hairstyle`); on
    completion writes the immutable `result` + `engine_version` once (TRX-5).
  - **Projection:** the completed face analysis **applies** the attributes to
    `user_state.style_profile` (latest-wins, TRX-6) and emits an
    `analysis_updated`/`style_updated` learning signal — the run is untouched
    (§4.4 guarantee 3). A later user override goes through R-2 (`sourceRunId`
    required for derived fields).
  - **Failure:** a failed run writes no `result` and no projection change.
- **Domain entities involved:** E6 `AnalysisRun` (the history); E1.1
  `UserState.styleProfile` (FaceProfile projection + `sourceRunId`, written by
  TRX-6); E5 `Look` (hairstyle catalog, read-only); E7 `LearningSignal`
  (`analysis_updated`); `MediaRef` (input evidence); value objects: FaceProfile,
  HairstyleRecommendation, Confidence (FUTURE).

---

### 5.2 A-2 — Grooming recommendations (`GenerateGroomingRecommendations`, UC-27)

- **Method / path:** `POST /v1/analysis/grooming` (endpoint 38, action 23)
- **Asynchronous behavior:** **async** — `202 Accepted` + `run_id`; poll A-3.
  Stays on the run model for uniformity (BJ-0); each submission is a new run.
- **Request schema** (`application/json`):

```
{
  "options": {                    // required; user preference — GroomingOption vocab ids (not free text)
    "faceShape":  "oval",         // from the grooming input vocabulary
    "beardStyle": "full_beard",
    "density":    "medium",
    "color":      "dark_brown"
  }
}
```

  The options mirror the user's picks in the grooming flow
  (`grooming_mock_data.dart:16` — face shape, beard style, density, color).
- **Response schema:** `202 Accepted` — `AsyncAccepted { run_id* }`. Completed
  run `result` (run_type `grooming`):

```
AnalysisRun.result (run_type "grooming") {
  recommendations: {                   // grooming recommendation rules
    top: GroomingRecommendation,       // { id, name, description, matchScore, reasons[],
    alternatives: GroomingRecommendation[],  //   maintenance, bestFor }
  }
}
```

  Mirrors `GroomingAnalysisResult` (`grooming_mock_data.dart:223`).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  (OW-1).
- **Validation:**
  - Every option must be a **valid `GroomingOption` vocab code** (K9.1);
    unknown/absent code → **422** with allowed values in `details`.
  - `options` object required; missing → **422**.
- **Errors:** `202`; `401`; `404`; `422 VALIDATION_ERROR` (invalid option
  codes); `503 EXTERNAL_SERVICE_FAILURE`; on poll `status=failed` →
  `PROCESSING_FAILURE` (details.run_id); `429 RATE_LIMITED`.
- **Security considerations:** grooming options are low-sensitivity user
  preference (vocab ids only — no free text, no injection surface); results are
  regenerable recommendations, never stored truth (BAR-0). Same owner-only /
  404-not-403 / C-8 posture as A-1.
- **Side effects:**
  - **History:** inserts an `analysis_runs` row (run_type `grooming`), writes
    the immutable result once on completion (TRX-5).
  - **No projection change by default:** grooming recommendations do **not**
    update the current profile (UC-27); if the user later "saves a style", that
    is a saved-look write (M7), not a profile edit (TRX-6 applies only when a
    style is explicitly accepted).
  - **Failure:** no result, no side effects beyond the failed run row.
- **Domain entities involved:** E6 `AnalysisRun` (history); E5 `Look` (grooming
  catalog, read-only); E1.1 `UserState` (read: FaceProfile grooming inputs);
  value objects: GroomingRecommendation, GroomingOption (vocab ref).

---

### 5.3 A-3 — Get analysis run (`GetAnalysisRun`)

- **Method / path:** `GET /v1/analysis/runs/{run_id}` (endpoint 39, actions
  16/21/23 poll)
- **Asynchronous behavior:** **sync** — it is the *polling read* for the async
  submissions above (pending → completed | failed).
- **Request schema:** none (`run_id` UUID in path).
- **Response schema:** `200 OK` — `AnalysisRun` (bare, no envelope; §4.3):

```
{
  "run_id": "7a2b…", "run_type": "hairstyle",
  "status": "completed",
  "created_at": "2026-08-10T12:00:00Z",
  "completed_at": "2026-08-10T12:00:05Z",
  "engine_version": "2026.08.1",
  "result": { /* immutable typed snapshot — only when completed */ }
}
```

  While `pending`: only `run_id`, `run_type`, `status`, `created_at`. When
  `failed`: `status`, `created_at`, `completed_at`, and `error` (the frozen
  error body); **no** `result` (a failed run has no output and still is
  history).
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  — the run must belong to the caller; another user's (or a non-existent)
  `run_id` → **404** (404-not-403, API-10).
- **Validation:** `run_id` must be a valid UUID; malformed → **422**.
- **Errors:** `200`; `401`; `404 NOT_FOUND` (not yours / never existed);
  `422 VALIDATION_ERROR` (bad UUID).
- **Security considerations:** the `result` is the user's own appearance
  history — owner-only, never logged; no other user's run is ever reachable.
  Response never exposes analysis internals beyond the typed snapshot (C-8).
- **Side effects:** none — a pure read of the immutable history.
- **Domain entities involved:** E6 `AnalysisRun`.

---

### 5.4 A-4 — List analysis runs (`ListAnalysisRuns`)

- **Method / path:** `GET /v1/analysis/runs` (endpoint 40, analysis history)
- **Asynchronous behavior:** **sync.**
- **Request schema:** query params `?run_type=&sort=created_at&page=&page_size=`
  (`run_type` optional; sort only by `created_at`; pagination API-20/22).
- **Response schema:** `200 OK` — `ListEnvelope`:

```
{ "items": [ AnalysisRun… ], "page": 1, "page_size": 20, "total": 37 }
```

  List rows may be summary (no `result`) to keep the history read light; detail
  comes from A-3.
- **Authentication requirements:** **auth** (Bearer). Authorization: **owner**
  — only the caller's own runs (OW-1).
- **Validation:** `run_type` must be a valid run_types code → else **422**;
  `page`/`page_size` bounds `[1,100]` (API-22); unknown sort key → **422**.
- **Errors:** `200`; `401`; `404` (account gone); `422 VALIDATION_ERROR`;
  `429 RATE_LIMITED`.
- **Security considerations:** history is the user's own appearance record —
  owner-only; pagination never leaks other users' rows; no content beyond the
  typed DTO.
- **Side effects:** none — pure read.
- **Domain entities involved:** E6 `AnalysisRun`.

---

### 5.5 R-1 / R-2 — Current profile reads and writes (reference)

The *current* face profile and style DNA are served and edited through the
profile surface already contracted in the sibling documents — **referenced, not
re-defined** here:

- **R-1 — `GET /v1/users/me`** (UC-6, endpoint 06) — `AUTH_API.md` §5.5 /
  `PROFILE_ONBOARDING_API.md` §5.1. Returns `ProfileView.styleProfile`
  (`faceShape?`, `skinTone?`, `bodyType?`, `styleType?`, `sourceRunId?`) — the
  **current** face profile + style DNA view. This is the only "what is my style
  today" read; it is disjoint from the analysis-run history (§4.4).
- **R-2 — `PATCH /v1/users/me`** (UC-7, endpoint 07) — `PROFILE_ONBOARDING_API.
  md` §5.2. The only way a client writes current style attributes: `styleType`
  is self-reported (no run); `faceShape`/`skinTone`/`bodyType` are
  analysis-derived and **require `sourceRunId`** (they must pin a real, owned,
  completed run — a client can never invent appearance truth; C-16). Written
  into `user_state.styleProfile` under `If-Match` version guard (409
  `kind="version"`).

Together with A-1, these close the loop: **analysis produces** the historical
run (A-1) → **completion applies** the current projection (TRX-6) → **the user
reads/edits** the current state via R-1/R-2 → **history is read separately**
via A-3/A-4.

### 5.6 R-3 — Style score / learning summary (reference)

The task's "appearance score" is, in the finalized domain model, the **Style
Score** — a **derived, deterministic** value (never AI, never stored as truth)
whose only surface is `GET /v1/learning/summary` (endpoint 34, M10):

```
LearningSummary { styleScore, breakdown, streak, recentSignals }
```

**Referenced, not re-defined** (it belongs to the M10 learning module). Two
contract notes that matter to this document:

1. The current score is a **CACHE** (regenerable: `60 + wardrobe.clamp(0,20) +
   savedLooks*2.clamp(0,20)`); its history is the append-only
   `style_score_records` snapshots — same current-vs-history discipline as §4.4.
2. There is **no** separate "appearance score" endpoint, and the score is
   **not** an appearance-profile value (`APPEARANCE_DOMAIN_MODEL.md` §3.9).

---

### 5.7 The appearance flow (a sequence of the above — no new endpoint)

```
A-1 submit face (multipart) ──202 {run_id}──►  A-3 poll ──► completed
   │                                                  │ result snapshot (immutable, engine_version)
   │ TRX-6 on completion                               ▼
   ▼                                          A-4 history list (all runs, filterable)
current styleProfile  ◄── applied attributes  +── runs never overwritten (§4.4)
   │ R-1 read  (GET /users/me)
   ▼
user edits: R-2 PATCH /users/me (styleType self-reported; derived fields need sourceRunId)
   ▲
A-2 grooming (options) ──202 {run_id}──► A-3 poll ──► recommendations only (no projection)
style score: R-3 GET /learning/summary (derived cache; snapshots in style_score_records)
capability progress: client-computed config × own data (§3.2)
```

---

## 6. Validation reference (shared)

| Field | Rules | Source |
| --- | --- | --- |
| `run_type` | ∈ run_types vocab {`outfit`,`face`,`hairstyle`,`grooming`} | `analysis_runs.run_type` FK, TABLE_DEFINITIONS |
| `status` | `pending → completed | failed`; write-once guard | TRX-5, CHECK constraint |
| image | required for A-1 (or `faceProfileRef`); face detectable; size/content-type | API-16, UC-25 |
| `options.*` | valid `GroomingOption` vocab codes | K9.1 vocab (VALUE_OBJECTS row 8 family) |
| `run_id` | UUID; owned (404-not-403) | path param, OW-1 |
| `sourceRunId` | UUID of an owned, **completed** run; required for derived fields on R-2 | C-16, PROFILE_ONBOARDING §5.2 |
| `page`/`page_size` | `[1,100]` | API-22 |
| derived codes (`faceShape`/`skinTone`/`bodyType`) | vocab-validated (K9.1); codes at §8 | API-14 |

All validation is **server-side** (Flutter never enforces security) and returns
the **safe client message**, never internals (ER-2).

---

## 7. Error reference for this surface

| `error.code` | HTTP | When | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | bad image / no face detected (A-1); invalid grooming option (A-2); bad UUID/filter (A-3/A-4); derived-without-run (R-2) | field errors + allowed values in `details` |
| `MEDIA_FAILURE` | 413/422 | image too large / unsupported content-type | `details.maxBytes`; pre-run check |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | run not owned / never existed; account gone | 404-not-403, no existence leak |
| `EXTERNAL_SERVICE_FAILURE` | 502/503 | AI provider/submission failure | C-8: no provider internals |
| `PROCESSING_FAILURE` | 500 (sync) / run `failed` | analysis pipeline failure | `details.run_id`; the run is a historical failure |
| `RATE_LIMITED` | 429 | any endpoint | + `Retry-After` |

---

## 8. Open decisions (carried forward, unchanged where already recorded)

1. **D-AUTH-1 — auth provider** — unchanged; gates mounting the whole M12
   analysis surface (endpoints stay unmounted until the seam lands, API-12).
2. **MS10.3 — media seal** — face image submission (`multipart` → `MediaRef`)
   depends on M16 unsealing; until then A-1 is not mounted (API-12, same rule
   as the sealed modules). No fake 200 before either gate lifts.
3. **`face` run_type** — a dedicated face-only analysis (run_type `face`, e.g.
   an onboarding scan producing only FaceProfile) has **no endpoint today**;
   the catalog mounts face analysis on `/v1/analysis/hairstyle` (run_type
   `hairstyle`). The vocabulary code is reserved, additive.
4. **Auto-accept on completion** — A-1 applies face attributes to the current
   projection at completion (per inventory 37, TRX-6). If the product instead
   wants an explicit "Save / Apply" acceptance step, it would be additive as a
   `PATCH /v1/users/me` call (R-2) after the run; the run remains the history
   either way.
5. **Analysis-derived vocab codes** — `faceShape`/`skinTone`/`bodyType` value
   codes are finalized with the knowledge layer (K9.1); until then the contract
   pins them to runs and rejects free text (same as `PROFILE_ONBOARDING_API.md`
   §8.6).
6. **Hair / Grooming / Color profile endpoints** — **deliberately not
   defined** (§3.1). If a hair/grooming pipeline lands (P1), the profile becomes
   an embedded projection pinned by `source_run_id` — additive, no new table.
7. **Confidence** — an optional field inside run results once real models
   compute it; never an endpoint (AI-0).
8. **Style Score history reads** — `style_score_records` trends are served by
   the M10 learning surface (R-3) when M10 ships; no appearance-surface
   endpoint.
9. All other open decisions from `API_CONTRACT_RULES.md` §16, `AUTH_API.md` §8,
   and `PROFILE_ONBOARDING_API.md` §8 remain open and are unaffected.

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/APPEARANCE_API.md` — the
field-level API contract for the appearance-intelligence surface: face analysis
+ hairstyle recommendations (`POST /v1/analysis/hairstyle`), grooming
recommendations (`POST /v1/analysis/grooming`), the immutable run history
(`GET /v1/analysis/runs/{run_id}`, `GET /v1/analysis/runs`), with the current
profile reads/writes (`GET`/`PATCH /v1/users/me`) and the style-score surface
(`GET /v1/learning/summary`) **referenced** from the sibling contracts. The
document makes the task's key requirement a **binding rule (§4.4)**: historical
AI analyses and current profile state are different, disjoint resource
families, with run results immutable and the current projection pinned to its
producing run by `sourceRunId`. Four task topics — **hair profile, grooming
profile, capability progress, "Appearance Intelligence"** — are explicitly
**NOT defined as APIs** (§3), consistent with the finalized domain model and
with `PROFILE_ONBOARDING_API.md`. Nothing is implemented.

**Skills used:** repository + documentation analysis (`APPEARANCE_DOMAIN_MODEL`
nine-concept classification, `analysis_runs`/`user_state`/`style_score_records`
tables, TRX-5/TRX-6, UC-25…27, AI_INTEGRATION_ARCHITECTURE FUTURE capability
interfaces, API_CONTRACT_RULES §12.11/§8.3/§13, API_INVENTORY endpoints
36–40/06/07/34, ERROR_HANDLING taxonomy, live `hairstyle_mock_data.dart` /
`grooming_mock_data.dart` / `onboarding_data.dart` / `learning_service.dart`) —
documentation only.

**Files changed:** `docs/api/APPEARANCE_API.md` (new); `CURRENT_STATE.md`
(status).

**Validation run:**
- **Every defined operation traces 1:1 to the accepted inventory** — A-1→UC-25/
  26 / endpoint 37, A-2→UC-27 / 38, A-3→39, A-4→40, R-1/R-2→06/07, R-3→34.
  Paths/methods/auth/UC/errors identical to `API_CONTRACT_RULES.md` §12.11 and
  `API_INVENTORY.md` §5.12/§5.3/§5.10; the async `202 + run_id` + poll pattern
  matches §8.3 and API-41/42; no invented endpoints (hair/grooming/color
  profile, capability progress, "Appearance Intelligence", style-DNA write,
  confidence — all explicitly excluded in §3).
- **Wire shapes match the accepted sketches** — `AnalysisRun`,
  `AsyncAccepted`, and the profile DTOs are identical to §8.3/§13.2; result
  snapshots mirror the real mock shapes (`HairstyleRecommendation`,
  `GroomingRecommendation`). No field removed, renamed, or retyped; additions
  are only documented gating notes (media seal, face run_type), not new stored
  data (API-2).
- **Historical-vs-current is structurally enforced** — two disjoint resource
  families (§4.4), `status`/`engine_version` on runs only, `sourceRunId`
  provenance on the profile only; write-once completion (TRX-5) and separate
  projection write (TRX-6) mean acceptance never mutates a run and history is
  never overwritten (PR-6).
- **Auth/authorization consistent** — all analysis endpoints auth + owner-only
  (OW-1, 404-not-403); frozen 12-category errors; 401 + `WWW-Authenticate`,
  429 + `Retry-After`; image analysis never idempotent (§11), reads/polls
  naturally idempotent.
- **`git status --short`:** `docs/api/` holds API_CONTRACT_RULES.md,
  API_INVENTORY.md, AUTH_API.md, PROFILE_ONBOARDING_API.md, APPEARANCE_API.md
  (untracked) + `CURRENT_STATE.md`; no code, directories, or files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- The M12 analysis endpoints are **not mounted** until D-AUTH-1 + the sync/
  media pipeline exist; before MS10.3 lifts, no face-image upload path exists
  (API-12 — no fake 200).
- `face` run_type endpoint, auto-accept vs explicit save, and the
  analysis-derived vocab codes are decided at M2/P2 implementation (§8.3–8.5).
- Hair/grooming/color profiles and capability progress remain **open
  non-features** (PLANNED / config) — no speculative tables, rows, or endpoints
  (PR-12).
- Other open decisions unchanged: auth provider (D-AUTH-1), User fields,
  Today'sLookRecord (P1), RecommendationHistory (P3), conversation retention,
  K9.1 knowledge shape, media-privacy (MS10.3), feedback design.

**Assumptions recorded:**
- Face analysis is the only analysis that *writes the current projection* (A-1,
  TRX-6); grooming recommendations and future hair/grooming/color analyses only
  write history until a style is explicitly accepted.
- Run `result` snapshots are versioned and immutable; "retake analysis" always
  creates a new run.
- Confidence is absent from results until real models compute it; scores in
  results are match scores, not confidence (AI-0).
- The current face profile and style DNA are always read from `/users/me`, and
  history always from `/analysis/runs*` — never mixed (§4.4).

**Constraints honored:** no implementation (analysis NOT created, no AI
providers, no media), the live assistant contract untouched (F-5, incl. frozen
`UserContext.face`), no invented APIs (all four excluded topics documented),
scope limited to `docs/api/APPEARANCE_API.md` + `CURRENT_STATE.md`.
